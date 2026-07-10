from __future__ import annotations

import asyncio
import html as html_lib
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

from app.core.config import DEFAULT_PRODUCTION_AI_MODEL, settings
from app.services.openrouter import generate_openrouter_response

MAX_URLS = 5
MAX_PAGE_BYTES = 650_000
MAX_TEXT_CHARS_PER_PAGE = 10_000
MAX_PROMPT_CHARS = 28_000
REQUEST_TIMEOUT_SECONDS = 15
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36 "
    "DirectPilotAI/0.1"
)
MIN_USEFUL_TEXT_CHARS = 80

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
REQUEST_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.6",
    "Cache-Control": "no-cache",
}


@dataclass
class ExtractedPage:
    url: str
    final_url: str | None = None
    status_code: int | None = None
    title: str | None = None
    description: str | None = None
    text: str | None = None
    content_length: int = 0
    content_sample: str | None = None
    extraction_method: str | None = None
    error: str | None = None


class ReadableHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_stack: list[str] = []
        self._title_capture = False
        self._ld_json_capture = False
        self._title_parts: list[str] = []
        self._text_parts: list[str] = []
        self._ld_json_parts: list[str] = []
        self.description: str | None = None
        self.og_title: str | None = None

    @property
    def title(self) -> str | None:
        title = _normalize_text(" ".join(self._title_parts)) or self.og_title
        return title or None

    @property
    def text(self) -> str:
        parts = [*self._text_parts]
        structured_text = _json_ld_to_text(" ".join(self._ld_json_parts))
        if structured_text:
            parts.append(structured_text)
        return _normalize_text(" ".join(parts))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attrs_dict = {str(key).lower(): value for key, value in attrs}
        if tag == "script" and "ld+json" in str(attrs_dict.get("type") or "").lower():
            self._ld_json_capture = True
            return
        if tag in {"script", "style", "noscript", "svg", "canvas", "iframe"}:
            self._skip_stack.append(tag)
        if tag == "title":
            self._title_capture = True
        if tag == "meta":
            name = (attrs_dict.get("name") or attrs_dict.get("property") or "").lower()
            content = attrs_dict.get("content")
            if name in {"description", "og:description", "twitter:description"} and content:
                self.description = _normalize_text(content) or self.description
            if name in {"og:title", "twitter:title"} and content:
                self.og_title = _normalize_text(content) or self.og_title

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "title":
            self._title_capture = False
        if tag == "script" and self._ld_json_capture:
            self._ld_json_capture = False
        if self._skip_stack and tag == self._skip_stack[-1]:
            self._skip_stack.pop()

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if not text:
            return
        if self._ld_json_capture:
            self._ld_json_parts.append(text)
            return
        if self._skip_stack:
            return
        if self._title_capture:
            self._title_parts.append(text)
        else:
            self._text_parts.append(text)


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", html_lib.unescape(value or "")).strip()


def _parse_json_object(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("AI response does not contain a JSON object")
    return json.loads(text[start : end + 1])


def _json_ld_to_text(raw_json: str) -> str:
    if not raw_json.strip():
        return ""
    chunks: list[str] = []
    for match in re.finditer(r"\{.*?\}", raw_json, flags=re.DOTALL):
        try:
            data = json.loads(match.group(0))
        except Exception:
            continue
        chunks.extend(_flatten_json_ld(data))
    return _normalize_text(" ".join(chunks))


def _flatten_json_ld(value: Any) -> list[str]:
    chunks: list[str] = []
    if isinstance(value, dict):
        for key in ["name", "alternateName", "description", "address", "telephone", "email", "priceRange"]:
            item = value.get(key)
            if isinstance(item, str):
                chunks.append(item)
            elif isinstance(item, dict):
                chunks.extend(_flatten_json_ld(item))
        for key in ["offers", "department", "areaServed", "makesOffer"]:
            if key in value:
                chunks.extend(_flatten_json_ld(value[key]))
    elif isinstance(value, list):
        for item in value:
            chunks.extend(_flatten_json_ld(item))
    elif isinstance(value, str):
        chunks.append(value)
    return chunks


def _regex_extract_text(html: str) -> str:
    source = html[:MAX_PAGE_BYTES]
    source = re.sub(r"<script\b(?![^>]*ld\+json)[\s\S]*?</script>", " ", source, flags=re.IGNORECASE)
    source = re.sub(r"<style\b[\s\S]*?</style>", " ", source, flags=re.IGNORECASE)
    source = re.sub(r"<(?:noscript|svg|canvas|iframe)\b[\s\S]*?</(?:noscript|svg|canvas|iframe)>", " ", source, flags=re.IGNORECASE)
    source = re.sub(r"<br\s*/?>", " ", source, flags=re.IGNORECASE)
    source = re.sub(r"</(?:p|div|section|article|li|h1|h2|h3|h4|h5|h6|tr|td|th)>", " ", source, flags=re.IGNORECASE)
    source = re.sub(r"<[^>]+>", " ", source)
    return _normalize_text(source)


def _extract_title_fallback(html: str) -> str | None:
    for pattern in [
        r"<title[^>]*>([\s\S]*?)</title>",
        r"<meta[^>]+property=['\"]og:title['\"][^>]+content=['\"]([^'\"]+)['\"]",
        r"<meta[^>]+name=['\"]twitter:title['\"][^>]+content=['\"]([^'\"]+)['\"]",
    ]:
        match = re.search(pattern, html, flags=re.IGNORECASE)
        if match:
            return _normalize_text(match.group(1)) or None
    return None


def _extract_description_fallback(html: str) -> str | None:
    for pattern in [
        r"<meta[^>]+name=['\"]description['\"][^>]+content=['\"]([^'\"]+)['\"]",
        r"<meta[^>]+property=['\"]og:description['\"][^>]+content=['\"]([^'\"]+)['\"]",
        r"<meta[^>]+name=['\"]twitter:description['\"][^>]+content=['\"]([^'\"]+)['\"]",
    ]:
        match = re.search(pattern, html, flags=re.IGNORECASE)
        if match:
            return _normalize_text(match.group(1)) or None
    return None


def _content_sample(html: str) -> str | None:
    sample = _normalize_text(re.sub(r"<[^>]+>", " ", html[:4_000]))
    return sample[:500] or None


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


def _decode_response_body(response: httpx.Response) -> str:
    body = response.content[:MAX_PAGE_BYTES]
    encoding = response.encoding or "utf-8"
    try:
        return body.decode(encoding, errors="replace")
    except LookupError:
        return body.decode("utf-8", errors="replace")


def _extract_html(html: str, url: str, status_code: int) -> ExtractedPage:
    parser = ReadableHtmlParser()
    parser.feed(html[:MAX_PAGE_BYTES])
    parser_text = parser.text
    regex_text = _regex_extract_text(html)
    text = parser_text if len(parser_text) >= len(regex_text) else regex_text
    title = parser.title or _extract_title_fallback(html)
    description = parser.description or _extract_description_fallback(html)
    combined_parts = [title or "", description or "", text]
    combined_text = _normalize_text(". ".join(item for item in combined_parts if item))[:MAX_TEXT_CHARS_PER_PAGE]
    method = "html_parser"
    if not parser_text and regex_text:
        method = "regex_fallback"
    if len(combined_text) < MIN_USEFUL_TEXT_CHARS and (title or description):
        method = "metadata_only"
    return ExtractedPage(
        url=url,
        final_url=url,
        status_code=status_code,
        title=title,
        description=description,
        text=combined_text,
        content_length=len(html),
        content_sample=_content_sample(html),
        extraction_method=method,
    )


async def _fetch_page(client: httpx.AsyncClient, raw_url: str) -> ExtractedPage:
    try:
        url = _validate_url(raw_url)
        current_url = url
        response: httpx.Response | None = None
        for _ in range(4):
            response = await client.get(current_url, headers=REQUEST_HEADERS, follow_redirects=False)
            if response.status_code in {301, 302, 303, 307, 308} and response.headers.get("location"):
                current_url = _validate_url(urljoin(current_url, response.headers["location"]))
                continue
            break
        if response is None:
            raise ValueError("No response")
        content_type = response.headers.get("content-type", "").lower()
        body_text = _decode_response_body(response)
        looks_like_html = "<html" in body_text.lower() or "<!doctype" in body_text.lower() or "<title" in body_text.lower()
        if "text/html" not in content_type and "application/xhtml" not in content_type and not looks_like_html:
            return ExtractedPage(
                url=url,
                final_url=str(response.url),
                status_code=response.status_code,
                content_length=len(body_text),
                content_sample=_content_sample(body_text),
                error="URL did not return HTML",
            )
        page = _extract_html(body_text, str(response.url), response.status_code)
        page.url = url
        page.final_url = str(response.url)
        return page
    except Exception as exc:
        return ExtractedPage(url=raw_url, error=str(exc)[:300])


def _build_prompt(client_name: str, pages: list[ExtractedPage]) -> str:
    page_blocks = []
    for index, page in enumerate(pages, start=1):
        if page.error:
            page_blocks.append(f"[{index}] URL: {page.url}\nERROR: {page.error}\nSample: {page.content_sample or '—'}")
            continue
        page_blocks.append(
            "\n".join(
                [
                    f"[{index}] URL: {page.final_url or page.url}",
                    f"Status: {page.status_code or '—'}",
                    f"Extraction: {page.extraction_method or '—'}",
                    f"Title: {page.title or '—'}",
                    f"Description: {page.description or '—'}",
                    f"Text: {(page.text or page.content_sample or '')[:MAX_TEXT_CHARS_PER_PAGE]}",
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
- Если страница содержит только metadata/title/description, заполняй только те поля, которые можно безопасно вывести из metadata.
- aiSummary: короткая сводка 3-5 предложений.
- sourceNotes: перечисли URL, способ извлечения и ограничения анализа.
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

    usable_pages = [page for page in pages if not page.error and (page.text or page.title or page.description or page.content_sample)]
    if not usable_pages:
        return {
            "draft": {field: None for field in BUSINESS_CONTEXT_FIELDS},
            "sources": [_page_source(page) for page in pages],
            "warnings": ["Не удалось получить читаемый HTML-текст или metadata по переданным ссылкам."],
        }

    prompt = _build_prompt(client_name, pages)
    try:
        ai_result = await generate_openrouter_response(DEFAULT_PRODUCTION_AI_MODEL, prompt, max_tokens=2200)
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
        "contentLength": page.content_length,
        "contentSample": page.content_sample,
        "extractionMethod": page.extraction_method,
        "error": page.error,
    }


def _quality_warnings(draft: dict[str, Any], pages: list[ExtractedPage]) -> list[str]:
    warnings: list[str] = []
    if any(page.error for page in pages):
        warnings.append("Часть страниц не удалось прочитать; проверьте список источников.")
    if any((page.content_length and len(page.text or "") < MIN_USEFUL_TEXT_CHARS) for page in pages if not page.error):
        warnings.append("По части страниц найдено мало текста; возможно, сайт рендерится JavaScript-ом или ограничивает HTML для ботов.")
    filled = sum(1 for value in draft.values() if value)
    if filled < 6:
        warnings.append("Контекст заполнен частично: на страницах мало явных данных о бизнесе.")
    if not draft.get("geography"):
        warnings.append("География не найдена явно; лучше проверить вручную.")
    if not draft.get("seasonality"):
        warnings.append("Сезонность не найдена явно; лучше проверить вручную.")
    return warnings
