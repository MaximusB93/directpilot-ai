from __future__ import annotations

import asyncio
import ipaddress
import json
import re
import socket
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
from fastapi import HTTPException, status

from app.core.config import settings
from app.services.openrouter import generate_openrouter_response

MAX_URLS = 5
MAX_PAGE_BYTES = 450_000
MAX_TEXT_CHARS_PER_PAGE = 9_000
MAX_PROMPT_CHARS = 26_000
REQUEST_TIMEOUT_SECONDS = 12
USER_AGENT = "DirectPilotAI-BusinessContextBot/0.1"

BUSINESS_CONTEXT_FIELDS = [
    "brandName",
    "businessNiche",
    "productSummary",
    "targetAudience",
    "geography",
    "seasonality",
    "mainOffers",
    "conversionActions",
    "averageOrderValue",
    "leadValueNotes",
    "businessConstraints",
    "negativeTopics",
    "landingPageNotes",
    "competitorNotes",
    "aiSummary",
    "sourceNotes",
]

BLOCKED_HOSTS = {"localhost", "local", "0.0.0.0"}
BLOCKED_HOST_SUFFIXES = (".local", ".localhost", ".internal", ".lan", ".home")


@dataclass
class ExtractedPage:
    url: str
    final_url: str | None = None
    status_code: int | None = None
    title: str | None = None
    description: str | None = None
    text: str | None = None
    error: str | None = None


class ReadableHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_stack: list[str] = []
        self._title_capture = False
        self._title_parts: list[str] = []
        self._text_parts: list[str] = []
        self.description: str | None = None

    @property
    def title(self) -> str | None:
        title = _normalize_text(" ".join(self._title_parts))
        return title or None

    @property
    def text(self) -> str:
        return _normalize_text(" ".join(self._text_parts))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg", "canvas", "iframe"}:
            self._skip_stack.append(tag)
        if tag == "title":
            self._title_capture = True
        if tag == "meta":
            attrs_dict = {str(key).lower(): value for key, value in attrs}
            name = (attrs_dict.get("name") or attrs_dict.get("property") or "").lower()
            if name in {"description", "og:description"} and attrs_dict.get("content"):
                self.description = _normalize_text(attrs_dict["content"] or "") or self.description

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "title":
            self._title_capture = False
        if self._skip_stack and tag == self._skip_stack[-1]:
            self._skip_stack.pop()

    def handle_data(self, data: str) -> None:
        if self._skip_stack:
            return
        text = data.strip()
        if not text:
            return
        if self._title_capture:
            self._title_parts.append(text)
        else:
            self._text_parts.append(text)


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _parse_json_object(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("AI response does not contain a JSON object")
    return json.loads(text[start : end + 1])


def _validate_url(raw_url: str) -> str:
    value = (raw_url or "").strip()
    if not value:
        raise ValueError("Empty URL")
    if not re.match(r"^https?://", value, flags=re.IGNORECASE):
        value = f"https://{value}"
    parsed = urlparse(value)
    host = (parsed.hostname or "").strip().lower()
    if parsed.scheme not in {"http", "https"} or not host:
        raise ValueError("Only http/https URLs are allowed")
    if parsed.username or parsed.password:
        raise ValueError("URLs with credentials are not allowed")
    if host in BLOCKED_HOSTS or any(host.endswith(suffix) for suffix in BLOCKED_HOST_SUFFIXES):
        raise ValueError("Local/internal hosts are not allowed")
    _validate_host_is_public(host)
    return parsed.geturl()


def _validate_host_is_public(host: str) -> None:
    try:
        ip = ipaddress.ip_address(host)
        _ensure_public_ip(ip)
        return
    except ValueError:
        pass

    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError(f"Host cannot be resolved: {host}") from exc
    resolved_ips = {item[4][0] for item in infos}
    if not resolved_ips:
        raise ValueError(f"Host cannot be resolved: {host}")
    for raw_ip in resolved_ips:
        _ensure_public_ip(ipaddress.ip_address(raw_ip))


def _ensure_public_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> None:
    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
        raise ValueError("Private/internal IP addresses are not allowed")


def _extract_html(html: str, url: str, status_code: int) -> ExtractedPage:
    parser = ReadableHtmlParser()
    parser.feed(html[:MAX_PAGE_BYTES])
    text = parser.text[:MAX_TEXT_CHARS_PER_PAGE]
    return ExtractedPage(
        url=url,
        final_url=url,
        status_code=status_code,
        title=parser.title,
        description=parser.description,
        text=text,
    )


async def _fetch_page(client: httpx.AsyncClient, raw_url: str) -> ExtractedPage:
    try:
        url = _validate_url(raw_url)
        current_url = url
        response: httpx.Response | None = None
        for _ in range(3):
            response = await client.get(
                current_url,
                headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
                follow_redirects=False,
            )
            if response.status_code in {301, 302, 303, 307, 308} and response.headers.get("location"):
                current_url = _validate_url(urljoin(current_url, response.headers["location"]))
                continue
            break
        if response is None:
            raise ValueError("No response")
        content_type = response.headers.get("content-type", "").lower()
        if "text/html" not in content_type and "application/xhtml" not in content_type:
            return ExtractedPage(url=url, final_url=str(response.url), status_code=response.status_code, error="URL did not return HTML")
        text = response.text[:MAX_PAGE_BYTES]
        page = _extract_html(text, str(response.url), response.status_code)
        page.url = url
        page.final_url = str(response.url)
        return page
    except Exception as exc:
        return ExtractedPage(url=raw_url, error=str(exc)[:300])


def _build_prompt(client_name: str, pages: list[ExtractedPage]) -> str:
    page_blocks = []
    for index, page in enumerate(pages, start=1):
        if page.error:
            page_blocks.append(f"[{index}] URL: {page.url}\nERROR: {page.error}")
            continue
        page_blocks.append(
            "\n".join(
                [
                    f"[{index}] URL: {page.final_url or page.url}",
                    f"Title: {page.title or '—'}",
                    f"Description: {page.description or '—'}",
                    f"Text: {(page.text or '')[:MAX_TEXT_CHARS_PER_PAGE]}",
                ]
            )
        )
    content = "\n\n---\n\n".join(page_blocks)[:MAX_PROMPT_CHARS]
    fields = ", ".join(BUSINESS_CONTEXT_FIELDS)
    return f"""
Ты DirectPilot AI. Заполни черновик бизнес-контекста по текстам страниц сайта клиента.
Клиент: {client_name}

Правила:
- Верни только валидный JSON-объект, без markdown.
- Заполняй только факты, которые можно вывести из страниц. Не выдумывай цены, географию, аудитории и сезонность.
- Если данных нет, ставь null.
- Поля должны быть строками или null.
- aiSummary: короткая сводка 3-5 предложений.
- sourceNotes: перечисли URL и ограничения анализа.
- landingPageNotes: укажи найденные посадочные страницы, офферы, формы/CTA, важные блоки.
- negativeTopics: только явно нерелевантные темы или явные ограничения, если они есть на сайте.
- businessConstraints: только явные ограничения: регионы, условия, сроки, бронирование, наличие, юридические требования.

Поля JSON: {fields}

Тексты страниц:
{content}
""".strip()


async def build_business_context_autofill(client_name: str, urls: list[str]) -> dict[str, Any]:
    clean_urls = [item.strip() for item in urls if item and item.strip()]
    if not clean_urls:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Добавьте хотя бы одну ссылку на сайт.")
    if len(clean_urls) > MAX_URLS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"За один раз можно обработать не больше {MAX_URLS} ссылок.")

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
        pages = await asyncio.gather(*[_fetch_page(client, url) for url in clean_urls])

    readable_pages = [page for page in pages if page.text and not page.error]
    if not readable_pages:
        return {
            "draft": {field: None for field in BUSINESS_CONTEXT_FIELDS},
            "sources": [_page_source(page) for page in pages],
            "warnings": ["Не удалось получить читаемый HTML-текст по переданным ссылкам."],
        }

    prompt = _build_prompt(client_name, pages)
    try:
        ai_result = await generate_openrouter_response(settings.openrouter_default_model, prompt, max_tokens=2200)
        parsed = _parse_json_object(str(ai_result.get("content") or ""))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"AI не вернул корректный JSON: {str(exc)[:200]}") from exc

    draft = {field: _clean_field(parsed.get(field)) for field in BUSINESS_CONTEXT_FIELDS}
    return {
        "draft": draft,
        "sources": [_page_source(page) for page in pages],
        "warnings": _quality_warnings(draft, pages),
    }


def _clean_field(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        value = "; ".join(str(item).strip() for item in value if str(item).strip())
    text = _normalize_text(str(value))
    return text[:4000] or None


def _page_source(page: ExtractedPage) -> dict[str, Any]:
    return {
        "url": page.url,
        "finalUrl": page.final_url,
        "statusCode": page.status_code,
        "title": page.title,
        "textLength": len(page.text or ""),
        "error": page.error,
    }


def _quality_warnings(draft: dict[str, Any], pages: list[ExtractedPage]) -> list[str]:
    warnings: list[str] = []
    if any(page.error for page in pages):
        warnings.append("Часть страниц не удалось прочитать; проверьте список источников.")
    filled = sum(1 for value in draft.values() if value)
    if filled < 6:
        warnings.append("Контекст заполнен частично: на страницах мало явных данных о бизнесе.")
    if not draft.get("geography"):
        warnings.append("География не найдена явно; лучше проверить вручную.")
    if not draft.get("seasonality"):
        warnings.append("Сезонность не найдена явно; лучше проверить вручную.")
    return warnings
