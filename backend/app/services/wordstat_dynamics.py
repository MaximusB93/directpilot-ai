import hashlib
import json
from datetime import UTC, date, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.connectors.yandex_wordstat import YandexWordstatConnector
from app.models_wordstat import WordstatDynamicsPoint, WordstatQueryBatch, WordstatQueryItem, WordstatRequestLog

ALLOWED_PERIODS = {
    "DAILY": "PERIOD_DAILY",
    "WEEKLY": "PERIOD_WEEKLY",
    "MONTHLY": "PERIOD_MONTHLY",
    "PERIOD_DAILY": "PERIOD_DAILY",
    "PERIOD_WEEKLY": "PERIOD_WEEKLY",
    "PERIOD_MONTHLY": "PERIOD_MONTHLY",
}
ALLOWED_DEVICES = {"DEVICE_ALL", "DEVICE_DESKTOP", "DEVICE_PHONE", "DEVICE_TABLET"}


def normalize_phrase(phrase: str) -> str:
    return " ".join(phrase.strip().lower().replace("ё", "е").split())


def normalize_period(period: str) -> str:
    value = (period or "MONTHLY").strip().upper()
    if value not in ALLOWED_PERIODS:
        raise ValueError("Unsupported Wordstat period. Use DAILY, WEEKLY or MONTHLY.")
    return ALLOWED_PERIODS[value]


def normalize_devices(devices: list[str] | None) -> list[str]:
    if not devices:
        return ["DEVICE_ALL"]
    normalized = [str(item).strip().upper() for item in devices if str(item).strip()]
    invalid = [item for item in normalized if item not in ALLOWED_DEVICES]
    if invalid:
        raise ValueError(f"Unsupported Wordstat device values: {', '.join(invalid)}")
    if "DEVICE_ALL" in normalized and len(normalized) > 1:
        return ["DEVICE_ALL"]
    return normalized or ["DEVICE_ALL"]


def normalize_regions(regions: list[str] | None) -> list[str]:
    return sorted({str(item).strip() for item in (regions or []) if str(item).strip()})


def hash_values(values: list[str]) -> str:
    raw = json.dumps(values, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def request_hash(*, phrase: str, period: str, from_date: date, to_date: date, regions: list[str], devices: list[str]) -> str:
    raw = json.dumps(
        {
            "phrase": normalize_phrase(phrase),
            "period": period,
            "fromDate": from_date.isoformat(),
            "toDate": to_date.isoformat(),
            "regions": regions,
            "devices": devices,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class WordstatDynamicsService:
    def __init__(self, db: Session, connector: YandexWordstatConnector) -> None:
        self.db = db
        self.connector = connector

    def get_batch_dynamics(
        self,
        *,
        phrases: list[str],
        period: str,
        from_date: date,
        to_date: date,
        regions: list[str] | None = None,
        devices: list[str] | None = None,
        organization_id: str | None = None,
        client_id: str | None = None,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        if to_date < from_date:
            raise ValueError("toDate must be greater than or equal to fromDate.")

        period = normalize_period(period)
        regions = normalize_regions(regions)
        devices = normalize_devices(devices)
        regions_hash = hash_values(regions)
        devices_hash = hash_values(devices)
        regions_json = json.dumps(regions, ensure_ascii=False)
        devices_json = json.dumps(devices, ensure_ascii=False)
        phrase_pairs = _unique_phrases(phrases)
        if not phrase_pairs:
            raise ValueError("Add at least one phrase.")

        batch = WordstatQueryBatch(
            organization_id=organization_id,
            client_id=client_id,
            period=period,
            from_date=from_date,
            to_date=to_date,
            regions_hash=regions_hash,
            devices_hash=devices_hash,
            regions_json=regions_json,
            devices_json=devices_json,
            status="running",
            total_phrases=len(phrase_pairs),
        )
        self.db.add(batch)
        self.db.flush()

        series: list[dict[str, Any]] = []
        completed = 0
        failed = 0

        for phrase_original, phrase_normalized in phrase_pairs:
            item = WordstatQueryItem(batch_id=batch.id, phrase=phrase_original, phrase_normalized=phrase_normalized, status="running")
            self.db.add(item)
            self.db.flush()
            try:
                if force_refresh:
                    points = self._refresh_phrase(
                        phrase_original=phrase_original,
                        phrase_normalized=phrase_normalized,
                        period=period,
                        from_date=from_date,
                        to_date=to_date,
                        regions=regions,
                        devices=devices,
                        regions_hash=regions_hash,
                        devices_hash=devices_hash,
                        regions_json=regions_json,
                        devices_json=devices_json,
                    )
                    source = "api"
                else:
                    points = self._cached_points(
                        phrase_normalized=phrase_normalized,
                        period=period,
                        from_date=from_date,
                        to_date=to_date,
                        regions_hash=regions_hash,
                        devices_hash=devices_hash,
                    )
                    source = "cache"
                    if not points:
                        points = self._refresh_phrase(
                            phrase_original=phrase_original,
                            phrase_normalized=phrase_normalized,
                            period=period,
                            from_date=from_date,
                            to_date=to_date,
                            regions=regions,
                            devices=devices,
                            regions_hash=regions_hash,
                            devices_hash=devices_hash,
                            regions_json=regions_json,
                            devices_json=devices_json,
                        )
                        source = "api"

                response_points = _enrich_points(points)
                item.status = "completed"
                item.points_loaded = len(response_points)
                completed += 1
                series.append(
                    {
                        "phrase": phrase_original,
                        "phraseNormalized": phrase_normalized,
                        "source": source,
                        "points": response_points,
                    }
                )
            except Exception as exc:  # noqa: BLE001 - endpoint should return partial batch result
                item.status = "failed"
                item.error_message = str(exc)
                failed += 1
                series.append(
                    {
                        "phrase": phrase_original,
                        "phraseNormalized": phrase_normalized,
                        "source": "error",
                        "error": str(exc),
                        "points": [],
                    }
                )

        batch.completed_phrases = completed
        batch.failed_phrases = failed
        batch.status = "completed" if failed == 0 else "partial" if completed else "failed"
        batch.updated_at = datetime.now(UTC)
        self.db.commit()

        return {
            "batchId": batch.id,
            "status": batch.status,
            "meta": {
                "period": period,
                "fromDate": from_date.isoformat(),
                "toDate": to_date.isoformat(),
                "regions": regions,
                "devices": devices,
                "totalPhrases": len(phrase_pairs),
                "completedPhrases": completed,
                "failedPhrases": failed,
            },
            "series": series,
            "summary": _build_summary(series),
        }

    def _cached_points(
        self,
        *,
        phrase_normalized: str,
        period: str,
        from_date: date,
        to_date: date,
        regions_hash: str,
        devices_hash: str,
    ) -> list[WordstatDynamicsPoint]:
        query = (
            select(WordstatDynamicsPoint)
            .where(
                WordstatDynamicsPoint.phrase_normalized == phrase_normalized,
                WordstatDynamicsPoint.period == period,
                WordstatDynamicsPoint.stat_date >= from_date,
                WordstatDynamicsPoint.stat_date <= to_date,
                WordstatDynamicsPoint.regions_hash == regions_hash,
                WordstatDynamicsPoint.devices_hash == devices_hash,
            )
            .order_by(WordstatDynamicsPoint.stat_date.asc())
        )
        return list(self.db.scalars(query).all())

    def _refresh_phrase(
        self,
        *,
        phrase_original: str,
        phrase_normalized: str,
        period: str,
        from_date: date,
        to_date: date,
        regions: list[str],
        devices: list[str],
        regions_hash: str,
        devices_hash: str,
        regions_json: str,
        devices_json: str,
    ) -> list[WordstatDynamicsPoint]:
        started_at = datetime.now(UTC)
        req_hash = request_hash(
            phrase=phrase_original,
            period=period,
            from_date=from_date,
            to_date=to_date,
            regions=regions,
            devices=devices,
        )
        log = WordstatRequestLog(
            provider="yandex_search_api",
            method="dynamics",
            phrase=phrase_original,
            request_hash=req_hash,
            status="started",
            started_at=started_at,
        )
        self.db.add(log)
        self.db.flush()
        try:
            raw_points = self.connector.get_dynamics(
                phrase=phrase_original,
                period=period,
                from_date=from_date,
                to_date=to_date,
                regions=regions,
                devices=devices,
            )
            self.db.execute(
                delete(WordstatDynamicsPoint).where(
                    WordstatDynamicsPoint.phrase_normalized == phrase_normalized,
                    WordstatDynamicsPoint.period == period,
                    WordstatDynamicsPoint.stat_date >= from_date,
                    WordstatDynamicsPoint.stat_date <= to_date,
                    WordstatDynamicsPoint.regions_hash == regions_hash,
                    WordstatDynamicsPoint.devices_hash == devices_hash,
                )
            )
            saved: list[WordstatDynamicsPoint] = []
            for raw in raw_points:
                stat_date = _parse_api_date(raw.get("date"))
                point = WordstatDynamicsPoint(
                    id=str(uuid4()),
                    phrase_original=phrase_original,
                    phrase_normalized=phrase_normalized,
                    period=period,
                    stat_date=stat_date,
                    count=_safe_int(raw.get("count")),
                    share=_safe_float(raw.get("share")),
                    regions_hash=regions_hash,
                    devices_hash=devices_hash,
                    regions_json=regions_json,
                    devices_json=devices_json,
                )
                self.db.add(point)
                saved.append(point)
            log.status = "completed"
            log.http_status = 200
            log.finished_at = datetime.now(UTC)
            self.db.flush()
            return saved
        except Exception as exc:
            log.status = "failed"
            log.error_message = str(exc)
            log.finished_at = datetime.now(UTC)
            self.db.flush()
            raise


def _unique_phrases(phrases: list[str]) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    seen: set[str] = set()
    for phrase in phrases:
        original = str(phrase or "").strip()
        normalized = normalize_phrase(original)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append((original, normalized))
    return result


def _parse_api_date(value: Any) -> date:
    raw = str(value or "")
    if not raw:
        raise ValueError("Wordstat point has empty date.")
    return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()


def _safe_int(value: Any) -> int:
    if value in {None, ""}:
        return 0
    return int(float(str(value).replace(",", ".")))


def _safe_float(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    return float(str(value).replace(",", "."))


def _enrich_points(points: list[WordstatDynamicsPoint]) -> list[dict[str, Any]]:
    ordered = sorted(points, key=lambda item: item.stat_date)
    first_count = next((point.count for point in ordered if point.count), None)
    by_month = {(point.stat_date.year, point.stat_date.month): point for point in ordered}
    enriched: list[dict[str, Any]] = []
    previous_count: int | None = None
    for point in ordered:
        yoy_point = by_month.get((point.stat_date.year - 1, point.stat_date.month))
        enriched.append(
            {
                "date": point.stat_date.isoformat(),
                "count": point.count,
                "share": point.share,
                "mom": _percent_delta(point.count, previous_count),
                "yoy": _percent_delta(point.count, yoy_point.count if yoy_point else None),
                "index": round(point.count / first_count * 100, 2) if first_count else None,
            }
        )
        previous_count = point.count
    return enriched


def _percent_delta(current: int | float | None, previous: int | float | None) -> float | None:
    if previous in {None, 0} or current is None:
        return None
    return round((float(current) - float(previous)) / float(previous) * 100, 2)


def _build_summary(series: list[dict[str, Any]]) -> dict[str, Any]:
    totals = []
    for item in series:
        points = item.get("points") or []
        if not points:
            continue
        first = points[0].get("count") or 0
        last = points[-1].get("count") or 0
        total = sum(point.get("count") or 0 for point in points)
        growth_percent = _percent_delta(last, first)
        totals.append(
            {
                "phrase": item.get("phrase"),
                "total": total,
                "firstCount": first,
                "lastCount": last,
                "growthPercent": growth_percent,
                "maxCount": max(point.get("count") or 0 for point in points),
            }
        )
    if not totals:
        return {"topGrowthPhrase": None, "topDeclinePhrase": None, "maxCountPhrase": None}
    growth_candidates = [item for item in totals if item["growthPercent"] is not None]
    return {
        "topGrowthPhrase": max(growth_candidates, key=lambda item: item["growthPercent"])["phrase"] if growth_candidates else None,
        "topDeclinePhrase": min(growth_candidates, key=lambda item: item["growthPercent"])["phrase"] if growth_candidates else None,
        "maxCountPhrase": max(totals, key=lambda item: item["total"])["phrase"],
        "phrases": totals,
    }
