"""Metrics core: period comparison, CPA decomposition, significance, empty spend.

Single source of truth for "where is CPA lost, and by how many roubles" across all
DirectPilot modes (morning digest, full audit, investigation, impact tracking).

Hard constraint (see docs/specs/TZ-01-metrics-core.md): this module must stay
dependency-free — standard library and ``dataclasses`` only. No DB, no network,
no ``app.core.config.settings``, no ``app.models``. That is what makes it testable
without any environment, and it must stay that way so every other service can
share one arithmetic core instead of re-deriving it.

``conversions = None`` means "unknown" and ``conversions = 0`` means "confirmed
zero". These two states are never collapsed into each other anywhere below.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta


# ---------------------------------------------------------------------------
# Period metrics
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PeriodMetrics:
    date_from: date
    date_to: date
    cost: float
    impressions: int
    clicks: int
    conversions: float | None  # None = conversion data unavailable for this period

    @property
    def ctr(self) -> float | None:
        if not self.impressions:
            return None
        return self.clicks / self.impressions * 100

    @property
    def cpc(self) -> float | None:
        if not self.clicks:
            return None
        return self.cost / self.clicks

    @property
    def cr(self) -> float | None:
        if self.conversions is None or not self.clicks:
            return None
        return self.conversions / self.clicks * 100

    @property
    def cpa(self) -> float | None:
        if self.conversions is None or not self.conversions:
            return None
        return self.cost / self.conversions

    @property
    def days(self) -> int:
        return (self.date_to - self.date_from).days + 1


# ---------------------------------------------------------------------------
# Comparison windows
# ---------------------------------------------------------------------------


def build_windows(reference_date: date) -> dict[str, tuple[date, date]]:
    """Return the standard set of comparison windows anchored on ``reference_date``.

    ``reference_date`` is the last day with data (usually yesterday). Daily
    comparisons must use ``same_weekday_prev_week``, never ``prev_day`` — weekly
    seasonality dominates any trend in ad accounts, so "Tuesday vs Monday" produces
    false swings. ``prev_day`` is returned for display only.
    """

    return {
        "yesterday": (reference_date, reference_date),
        "same_weekday_prev_week": (
            reference_date - timedelta(days=7),
            reference_date - timedelta(days=7),
        ),
        "prev_day": (reference_date - timedelta(days=1), reference_date - timedelta(days=1)),
        "last7": (reference_date - timedelta(days=6), reference_date),
        "previous7": (reference_date - timedelta(days=13), reference_date - timedelta(days=7)),
        "last28": (reference_date - timedelta(days=27), reference_date),
        "previous28": (reference_date - timedelta(days=55), reference_date - timedelta(days=28)),
        "last90": (reference_date - timedelta(days=89), reference_date),
    }


# ---------------------------------------------------------------------------
# Period comparison
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MetricDelta:
    current: float | None
    previous: float | None
    absolute: float | None
    percent: float | None
    direction: str  # "up" | "down" | "flat" | "unknown"
    is_significant: bool
    confidence: str  # "high" | "medium" | "low" | "insufficient"


@dataclass(frozen=True)
class MetricComparison:
    cost: MetricDelta
    impressions: MetricDelta
    clicks: MetricDelta
    ctr: MetricDelta
    cpc: MetricDelta
    conversions: MetricDelta
    cr: MetricDelta
    cpa: MetricDelta


# Spend is measured exactly — there is no sampling noise in it, so the Poisson
# test that suits conversions makes no sense here. The question for spend is not
# "is this change real" but "is this change material", and materiality needs both
# a relative and an absolute floor: 50 rouble growing to 150 is +200% and still
# nothing worth a morning digest slot.
COST_MATERIALITY_PCT = 20.0
COST_MATERIALITY_ABS = 1000.0


def _cost_significant(absolute: float | None, percent: float | None) -> bool:
    if absolute is None or percent is None:
        return False
    return abs(percent) >= COST_MATERIALITY_PCT and abs(absolute) >= COST_MATERIALITY_ABS


def _percent(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None or previous == 0:
        return None
    return (current - previous) / previous * 100


def _absolute(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None:
        return None
    return current - previous


def _direction(current: float | None, previous: float | None, percent: float | None) -> str:
    if current is None or previous is None or percent is None:
        return "unknown"
    if abs(percent) < 1:
        return "flat"
    return "up" if percent > 0 else "down"


def _make_delta(
    current: float | None,
    previous: float | None,
    *,
    is_significant: bool,
    confidence: str,
) -> MetricDelta:
    percent = _percent(current, previous)
    return MetricDelta(
        current=current,
        previous=previous,
        absolute=_absolute(current, previous),
        percent=percent,
        direction=_direction(current, previous, percent),
        is_significant=is_significant and percent is not None,
        confidence=confidence,
    )


def _poisson_significant(
    n_current: float | None, n_previous: float | None, percent: float | None
) -> bool:
    if n_current is None or n_previous is None or n_current < 1 or n_previous < 1:
        return False
    if percent is None:
        return False
    threshold_pct = 200 * math.sqrt(1 / n_current + 1 / n_previous)
    return abs(percent) > threshold_pct


def _binomial_significant(
    numerator_current: float | None,
    denominator_current: float | None,
    numerator_previous: float | None,
    denominator_previous: float | None,
) -> bool:
    if (
        numerator_current is None
        or numerator_previous is None
        or denominator_current is None
        or denominator_previous is None
        or denominator_current < 1
        or denominator_previous < 1
    ):
        return False
    p_current = numerator_current / denominator_current
    p_previous = numerator_previous / denominator_previous
    p_pooled = (numerator_current + numerator_previous) / (denominator_current + denominator_previous)
    se = math.sqrt(p_pooled * (1 - p_pooled) * (1 / denominator_current + 1 / denominator_previous))
    if se == 0:
        return False
    return abs(p_current - p_previous) > 2 * se


def _confidence_by_conversions(n_current: float | None, n_previous: float | None) -> str:
    if n_current is None or n_previous is None:
        return "insufficient"
    n = min(n_current, n_previous)
    if n >= 50:
        return "high"
    if n >= 15:
        return "medium"
    if n >= 3:
        return "low"
    return "insufficient"


def _confidence_by_clicks(n_current: float | None, n_previous: float | None) -> str:
    if n_current is None or n_previous is None:
        return "insufficient"
    n = min(n_current, n_previous)
    if n >= 1000:
        return "high"
    if n >= 300:
        return "medium"
    if n >= 50:
        return "low"
    return "insufficient"


def _confidence_by_impressions(n_current: float | None, n_previous: float | None) -> str:
    """Confidence for impression-based metrics, judged on their own denominator.

    Impressions and CTR were previously judged on clicks, which sits on a scale
    two orders of magnitude smaller and reported "insufficient" for volumes that
    are plainly large enough.
    """
    if n_current is None or n_previous is None:
        return "insufficient"
    n = min(n_current, n_previous)
    if n >= 50_000:
        return "high"
    if n >= 10_000:
        return "medium"
    if n >= 1_000:
        return "low"
    return "insufficient"


def compare(current: PeriodMetrics, previous: PeriodMetrics) -> MetricComparison:
    """Compare two periods metric by metric.

    Significance follows docs/specs/TZ-01-metrics-core.md section 4: counting
    metrics (impressions, clicks, conversions) use a Poisson noise threshold,
    share metrics (ctr, cr) use a binomial standard error, and derived metrics
    (cpc, cpa) inherit significance from the count they are built on (clicks,
    conversions respectively) rather than getting their own test. Spend is the
    exception: it is exact, so it is judged on materiality instead of noise.
    """

    clicks_conf = _confidence_by_clicks(current.clicks, previous.clicks)
    conversions_conf = _confidence_by_conversions(current.conversions, previous.conversions)
    impressions_conf = _confidence_by_impressions(current.impressions, previous.impressions)

    cost_sig = _cost_significant(
        _absolute(current.cost, previous.cost), _percent(current.cost, previous.cost)
    )

    impressions_pct = _percent(current.impressions, previous.impressions)
    impressions_sig = _poisson_significant(current.impressions, previous.impressions, impressions_pct)

    clicks_pct = _percent(current.clicks, previous.clicks)
    clicks_sig = _poisson_significant(current.clicks, previous.clicks, clicks_pct)

    conversions_pct = _percent(current.conversions, previous.conversions)
    conversions_sig = _poisson_significant(current.conversions, previous.conversions, conversions_pct)

    ctr_sig = _binomial_significant(current.clicks, current.impressions, previous.clicks, previous.impressions)
    cr_sig = _binomial_significant(current.conversions, current.clicks, previous.conversions, previous.clicks)

    return MetricComparison(
        cost=_make_delta(current.cost, previous.cost, is_significant=cost_sig, confidence=clicks_conf),
        impressions=_make_delta(
            current.impressions, previous.impressions, is_significant=impressions_sig, confidence=impressions_conf
        ),
        clicks=_make_delta(current.clicks, previous.clicks, is_significant=clicks_sig, confidence=clicks_conf),
        ctr=_make_delta(current.ctr, previous.ctr, is_significant=ctr_sig, confidence=impressions_conf),
        cpc=_make_delta(current.cpc, previous.cpc, is_significant=clicks_sig, confidence=clicks_conf),
        conversions=_make_delta(
            current.conversions, previous.conversions, is_significant=conversions_sig, confidence=conversions_conf
        ),
        cr=_make_delta(current.cr, previous.cr, is_significant=cr_sig, confidence=conversions_conf),
        cpa=_make_delta(
            current.cpa, previous.cpa, is_significant=conversions_sig, confidence=conversions_conf
        ),
    )


# ---------------------------------------------------------------------------
# CPA decomposition
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CpaDecomposition:
    cpa_previous: float | None
    cpa_current: float | None
    cpa_change: float | None
    cpc_contribution: float | None
    cr_contribution: float | None
    dominant_factor: str  # "cpc" | "cr" | "both" | "unknown"


def _cr_fraction(period: PeriodMetrics) -> float | None:
    if period.conversions is None or not period.clicks:
        return None
    return period.conversions / period.clicks


def decompose_cpa(current: PeriodMetrics, previous: PeriodMetrics) -> CpaDecomposition:
    """Split the change in CPA into a CPC part and a CR part, without remainder.

    Identity: CPA = cost / conversions = CPC / CR (CR as a fraction, not a
    percent). Algebraically::

        cpc_contribution + cr_contribution
            = (cpc_c - cpc_p) / cr_p + cpc_c * (1 / cr_c - 1 / cr_p)
            = cpc_c / cr_c - cpc_p / cr_p
            = cpa_current - cpa_previous

    so the two contributions always sum to the exact CPA change when both
    periods have a defined CPC and CR.
    """

    cpa_previous = previous.cpa
    cpa_current = current.cpa
    cpa_change = (
        cpa_current - cpa_previous if cpa_current is not None and cpa_previous is not None else None
    )

    cpc_previous = previous.cpc
    cpc_current = current.cpc
    cr_previous = _cr_fraction(previous)
    cr_current = _cr_fraction(current)

    inputs_known = (
        cpc_previous is not None
        and cpc_current is not None
        and cr_previous is not None
        and cr_current is not None
        and cr_previous != 0
        and cr_current != 0
    )

    if not inputs_known:
        return CpaDecomposition(
            cpa_previous=cpa_previous,
            cpa_current=cpa_current,
            cpa_change=cpa_change,
            cpc_contribution=None,
            cr_contribution=None,
            dominant_factor="unknown",
        )

    cpc_contribution = (cpc_current - cpc_previous) / cr_previous
    cr_contribution = cpc_current * (1 / cr_current - 1 / cr_previous)

    total_abs = abs(cpc_contribution) + abs(cr_contribution)
    if total_abs == 0:
        dominant_factor = "both"
    elif abs(cpc_contribution) / total_abs > 0.65:
        dominant_factor = "cpc"
    elif abs(cr_contribution) / total_abs > 0.65:
        dominant_factor = "cr"
    else:
        dominant_factor = "both"

    return CpaDecomposition(
        cpa_previous=cpa_previous,
        cpa_current=cpa_current,
        cpa_change=cpa_change,
        cpc_contribution=cpc_contribution,
        cr_contribution=cr_contribution,
        dominant_factor=dominant_factor,
    )


# ---------------------------------------------------------------------------
# Empty spend
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SegmentMetrics:
    key: str
    label: str
    metrics: PeriodMetrics


@dataclass(frozen=True)
class EmptySpendItem:
    key: str
    label: str
    cost: float
    clicks: int
    reliable: bool
    reason: str | None


@dataclass(frozen=True)
class EmptySpendSummary:
    total_cost: float
    empty_cost: float
    empty_share_pct: float
    unknown_cost: float
    segments: list[EmptySpendItem]


def empty_spend(
    segments: list[SegmentMetrics], *, baseline_cr: float | None = None
) -> EmptySpendSummary:
    """Find spend that produced zero conversions.

    Segments with ``conversions is None`` are unknown, not empty: their cost
    goes to ``unknown_cost`` and they never contribute to ``empty_cost`` or the
    returned segment list. A zero-conversion segment is only ``reliable`` once
    it has enough clicks that a true zero would be expected to show at least
    three conversions (``clicks >= 3 / baseline_cr``), or 30 clicks when no
    account baseline CR is known.
    """

    priced = [segment for segment in segments if segment.metrics.cost != 0]

    total_cost = sum(segment.metrics.cost for segment in priced)
    empty_cost = sum(
        segment.metrics.cost for segment in priced if segment.metrics.conversions == 0
    )
    unknown_cost = sum(
        segment.metrics.cost for segment in priced if segment.metrics.conversions is None
    )
    empty_share_pct = (empty_cost / total_cost * 100) if total_cost else 0.0

    threshold_clicks = (3 / baseline_cr) if baseline_cr else 30

    items = [
        EmptySpendItem(
            key=segment.key,
            label=segment.label,
            cost=segment.metrics.cost,
            clicks=segment.metrics.clicks,
            reliable=segment.metrics.clicks >= threshold_clicks,
            reason=None if segment.metrics.clicks >= threshold_clicks else "insufficient_clicks",
        )
        for segment in priced
        if segment.metrics.conversions == 0
    ]
    items.sort(key=lambda item: item.cost, reverse=True)

    return EmptySpendSummary(
        total_cost=total_cost,
        empty_cost=empty_cost,
        empty_share_pct=empty_share_pct,
        unknown_cost=unknown_cost,
        segments=items,
    )


# ---------------------------------------------------------------------------
# Savings estimate
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SavingsEstimate:
    monthly_cost_saved: float
    conversions_at_risk: float | None
    confidence: str
    assumption: str


def estimate_savings(segment: SegmentMetrics, *, baseline_cpa: float | None) -> SavingsEstimate:
    """Project a segment's cost (and, if known, conversions) onto a 30-day month."""

    metrics = segment.metrics
    if metrics.days <= 0:
        # Degenerate period (date_to before date_from). No division may raise here:
        # a missing result is None or zero, never an exception (see TZ-01 section 1).
        return SavingsEstimate(
            monthly_cost_saved=0.0,
            conversions_at_risk=None,
            confidence="insufficient",
            assumption="период сегмента вырожден: date_to раньше date_from, оценка не построена",
        )

    monthly_cost_saved = metrics.cost / metrics.days * 30

    if metrics.conversions is None:
        return SavingsEstimate(
            monthly_cost_saved=monthly_cost_saved,
            conversions_at_risk=None,
            confidence="low",
            assumption="конверсии по сегменту неизвестны, оценка построена только на расходе",
        )

    conversions_at_risk = metrics.conversions / metrics.days * 30
    confidence = _confidence_by_conversions(metrics.conversions, metrics.conversions)
    assumption = "оценка построена на фактических расходе и конверсиях сегмента за период"
    if baseline_cpa is not None:
        assumption += f", ориентир CPA аккаунта {baseline_cpa:.2f}"

    return SavingsEstimate(
        monthly_cost_saved=monthly_cost_saved,
        conversions_at_risk=conversions_at_risk,
        confidence=confidence,
        assumption=assumption,
    )
