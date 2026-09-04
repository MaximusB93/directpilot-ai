import ast
import math
import random
import sys
from datetime import date, timedelta
from pathlib import Path

from app.services.metrics_core import (
    PeriodMetrics,
    SegmentMetrics,
    build_windows,
    compare,
    decompose_cpa,
    empty_spend,
    estimate_savings,
)

MODULE_PATH = Path(__file__).resolve().parents[1] / "app" / "services" / "metrics_core.py"


def _period(
    *,
    date_from: date = date(2026, 8, 1),
    date_to: date = date(2026, 8, 1),
    cost: float = 0.0,
    impressions: int = 0,
    clicks: int = 0,
    conversions: float | None = 0.0,
) -> PeriodMetrics:
    return PeriodMetrics(
        date_from=date_from,
        date_to=date_to,
        cost=cost,
        impressions=impressions,
        clicks=clicks,
        conversions=conversions,
    )


# ---------------------------------------------------------------------------
# Module isolation: only stdlib imports
# ---------------------------------------------------------------------------


def test_module_imports_only_stdlib() -> None:
    tree = ast.parse(MODULE_PATH.read_text(encoding="utf-8"))
    stdlib = sys.stdlib_module_names
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                assert root in stdlib, f"non-stdlib import: {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            if node.module is None:
                continue
            root = node.module.split(".")[0]
            assert root in stdlib, f"non-stdlib import: {node.module}"


# ---------------------------------------------------------------------------
# 1. Derived metrics at zero denominators return None, never 0, never raise
# ---------------------------------------------------------------------------


def test_ctr_is_none_when_no_impressions() -> None:
    metrics = _period(impressions=0, clicks=0)
    assert metrics.ctr is None


def test_cpc_is_none_when_no_clicks() -> None:
    metrics = _period(cost=100.0, clicks=0)
    assert metrics.cpc is None


def test_cr_is_none_when_no_clicks() -> None:
    metrics = _period(clicks=0, conversions=0.0)
    assert metrics.cr is None


def test_cpa_is_none_when_no_conversions() -> None:
    metrics = _period(cost=100.0, conversions=0.0)
    assert metrics.cpa is None
    metrics_unknown = _period(cost=100.0, conversions=None)
    assert metrics_unknown.cpa is None


def test_no_division_ever_raises() -> None:
    metrics = _period(cost=0.0, impressions=0, clicks=0, conversions=None)
    assert metrics.ctr is None
    assert metrics.cpc is None
    assert metrics.cr is None
    assert metrics.cpa is None


# ---------------------------------------------------------------------------
# 2. conversions=None never becomes 0
# ---------------------------------------------------------------------------


def test_compare_keeps_conversions_none_distinct_from_zero() -> None:
    current = _period(clicks=100, cost=1000.0, conversions=None)
    previous = _period(clicks=100, cost=1000.0, conversions=0.0)
    result = compare(current, previous)
    assert result.conversions.current is None
    assert result.conversions.previous == 0.0
    assert result.conversions.absolute is None
    assert result.conversions.percent is None
    assert result.cr.current is None
    assert result.cpa.current is None


def test_decompose_cpa_none_conversions_yields_unknown() -> None:
    current = _period(cost=1000.0, clicks=100, conversions=None)
    previous = _period(cost=1000.0, clicks=100, conversions=10.0)
    decomposition = decompose_cpa(current, previous)
    assert decomposition.cpa_current is None
    assert decomposition.cpc_contribution is None
    assert decomposition.cr_contribution is None
    assert decomposition.dominant_factor == "unknown"


def test_empty_spend_unknown_conversions_not_counted_as_empty() -> None:
    segments = [
        SegmentMetrics(key="a", label="A", metrics=_period(cost=500.0, clicks=40, conversions=None)),
        SegmentMetrics(key="b", label="B", metrics=_period(cost=300.0, clicks=40, conversions=0.0)),
    ]
    summary = empty_spend(segments)
    assert summary.unknown_cost == 500.0
    assert summary.empty_cost == 300.0
    assert summary.total_cost == 800.0
    assert {item.key for item in summary.segments} == {"b"}


def test_estimate_savings_none_conversions_keeps_conversions_at_risk_none() -> None:
    segment = SegmentMetrics(
        key="a",
        label="A",
        metrics=_period(cost=300.0, clicks=40, conversions=None),
    )
    estimate = estimate_savings(segment, baseline_cpa=None)
    assert estimate.conversions_at_risk is None
    assert estimate.monthly_cost_saved > 0
    assert estimate.confidence == "low"
    assert "неизвестны" in estimate.assumption


# ---------------------------------------------------------------------------
# 3. percent rules around zero/None previous
# ---------------------------------------------------------------------------


def test_percent_is_none_when_previous_is_zero() -> None:
    current = _period(cost=100.0, clicks=10, conversions=5.0)
    previous = _period(cost=0.0, clicks=10, conversions=5.0)
    result = compare(current, previous)
    assert result.cost.percent is None
    assert result.cost.direction == "unknown"


def test_percent_is_none_when_both_zero() -> None:
    current = _period(cost=0.0, clicks=0, conversions=0.0)
    previous = _period(cost=0.0, clicks=0, conversions=0.0)
    result = compare(current, previous)
    assert result.cost.percent is None
    assert result.cost.direction == "unknown"
    assert result.conversions.percent is None
    assert result.conversions.direction == "unknown"


def test_percent_growth_from_zero_is_none_not_infinite() -> None:
    current = _period(conversions=5.0, clicks=100, cost=100.0)
    previous = _period(conversions=0.0, clicks=100, cost=100.0)
    result = compare(current, previous)
    assert result.conversions.percent is None
    assert result.conversions.direction == "unknown"


# ---------------------------------------------------------------------------
# 4. Decomposition convergence
# ---------------------------------------------------------------------------


def _random_valid_period(rng: random.Random) -> PeriodMetrics:
    clicks = rng.randint(50, 5000)
    conversions = rng.uniform(1.0, clicks * 0.2)
    cost = clicks * rng.uniform(5.0, 300.0)
    impressions = clicks * rng.randint(2, 50)
    return _period(cost=cost, impressions=impressions, clicks=clicks, conversions=conversions)


def test_decomposition_converges_on_random_valid_inputs() -> None:
    rng = random.Random(42)
    for _ in range(10):
        current = _random_valid_period(rng)
        previous = _random_valid_period(rng)
        decomposition = decompose_cpa(current, previous)
        assert decomposition.cpa_change is not None
        assert decomposition.cpc_contribution is not None
        assert decomposition.cr_contribution is not None
        total = decomposition.cpc_contribution + decomposition.cr_contribution
        assert math.isclose(total, decomposition.cpa_change, abs_tol=0.01)


def test_decomposition_unchanged_cr_attributes_all_change_to_cpc() -> None:
    previous = _period(cost=1000.0, clicks=100, conversions=10.0)
    current = _period(cost=1500.0, clicks=100, conversions=10.0)
    decomposition = decompose_cpa(current, previous)
    assert decomposition.cr_contribution is not None
    assert math.isclose(decomposition.cr_contribution, 0.0, abs_tol=1e-9)
    assert math.isclose(decomposition.cpc_contribution, decomposition.cpa_change, abs_tol=0.01)
    assert decomposition.dominant_factor == "cpc"


def test_decomposition_unchanged_cpc_attributes_all_change_to_cr() -> None:
    previous = _period(cost=1000.0, clicks=100, conversions=10.0)
    current = _period(cost=2000.0, clicks=200, conversions=10.0)
    decomposition = decompose_cpa(current, previous)
    assert decomposition.cpc_contribution is not None
    assert math.isclose(decomposition.cpc_contribution, 0.0, abs_tol=1e-9)
    assert math.isclose(decomposition.cr_contribution, decomposition.cpa_change, abs_tol=0.01)
    assert decomposition.dominant_factor == "cr"


def test_decomposition_manual_example_from_spec() -> None:
    # "CPA вырос с 6 200 до 8 900 ₽. Из 2 700 ₽ роста 1 900 ₽ дало подорожание
    # клика, 800 ₽ — падение конверсионности." (illustrative numbers from
    # PROJECT_PLAN.md); we only assert the identity holds, not the exact split.
    previous = _period(cost=62000.0, clicks=1000, conversions=10.0)
    current = _period(cost=89000.0, clicks=1000, conversions=10.0)
    decomposition = decompose_cpa(current, previous)
    assert math.isclose(
        decomposition.cpc_contribution + decomposition.cr_contribution,
        decomposition.cpa_change,
        abs_tol=0.01,
    )


# ---------------------------------------------------------------------------
# 5. Significance thresholds match reference points
# ---------------------------------------------------------------------------


def test_significance_threshold_reference_points() -> None:
    cases = [(10, 10, 89.0), (50, 50, 40.0), (200, 200, 20.0), (1000, 1000, 9.0)]
    for n_current, n_previous, expected_pct in cases:
        threshold = 200 * math.sqrt(1 / n_current + 1 / n_previous)
        assert abs(threshold - expected_pct) <= 1.0


def test_change_not_significant_at_low_conversion_count() -> None:
    previous = _period(clicks=1000, cost=10000.0, conversions=12.0)
    current = _period(clicks=1000, cost=10000.0, conversions=12.0 * 1.4)
    result = compare(current, previous)
    assert result.conversions.is_significant is False


def test_change_significant_at_high_conversion_count() -> None:
    previous = _period(clicks=10000, cost=100000.0, conversions=300.0)
    current = _period(clicks=10000, cost=100000.0, conversions=300.0 * 1.4)
    result = compare(current, previous)
    assert result.conversions.is_significant is True


def test_cpa_significance_mirrors_conversions() -> None:
    previous = _period(clicks=1000, cost=10000.0, conversions=12.0)
    current = _period(clicks=1000, cost=10000.0, conversions=12.0 * 1.4)
    result = compare(current, previous)
    assert result.cpa.is_significant == result.conversions.is_significant


def test_cpc_significance_mirrors_clicks() -> None:
    previous = _period(clicks=12, cost=1000.0, conversions=5.0)
    current = _period(clicks=int(12 * 1.4), cost=1000.0, conversions=5.0)
    result = compare(current, previous)
    assert result.cpc.is_significant == result.clicks.is_significant


def test_insufficient_counts_are_never_significant() -> None:
    previous = _period(clicks=0, cost=0.0, conversions=0.0)
    current = _period(clicks=0, cost=0.0, conversions=5.0)
    result = compare(current, previous)
    assert result.clicks.is_significant is False
    assert result.clicks.confidence == "insufficient"


# ---------------------------------------------------------------------------
# 6. Windows
# ---------------------------------------------------------------------------


def test_same_weekday_prev_week_is_exactly_seven_days_back() -> None:
    reference = date(2026, 8, 15)
    windows = build_windows(reference)
    same_weekday_from, same_weekday_to = windows["same_weekday_prev_week"]
    assert same_weekday_from == same_weekday_to == reference - timedelta(days=7)


def test_last28_and_previous28_do_not_overlap_and_have_28_days_each() -> None:
    reference = date(2026, 8, 15)
    windows = build_windows(reference)
    last28_from, last28_to = windows["last28"]
    previous28_from, previous28_to = windows["previous28"]

    assert (last28_to - last28_from).days + 1 == 28
    assert (previous28_to - previous28_from).days + 1 == 28
    assert previous28_to < last28_from
    assert previous28_to == last28_from - timedelta(days=1)


def test_window_boundaries_are_inclusive() -> None:
    reference = date(2026, 8, 15)
    windows = build_windows(reference)
    last7_from, last7_to = windows["last7"]
    assert last7_to == reference
    assert last7_from == reference - timedelta(days=6)
    assert (last7_to - last7_from).days + 1 == 7

    yesterday_from, yesterday_to = windows["yesterday"]
    assert yesterday_from == yesterday_to == reference

    prev_day_from, prev_day_to = windows["prev_day"]
    assert prev_day_from == prev_day_to == reference - timedelta(days=1)


# ---------------------------------------------------------------------------
# 7. Empty spend reliability
# ---------------------------------------------------------------------------


def test_empty_spend_segment_with_few_clicks_is_not_reliable() -> None:
    segments = [
        SegmentMetrics(key="a", label="A", metrics=_period(cost=200.0, clicks=5, conversions=0.0)),
    ]
    summary = empty_spend(segments)
    assert len(summary.segments) == 1
    item = summary.segments[0]
    assert item.reliable is False
    assert item.reason == "insufficient_clicks"


def test_empty_spend_segment_with_enough_clicks_is_reliable() -> None:
    segments = [
        SegmentMetrics(key="a", label="A", metrics=_period(cost=200.0, clicks=40, conversions=0.0)),
    ]
    summary = empty_spend(segments)
    item = summary.segments[0]
    assert item.reliable is True
    assert item.reason is None


def test_empty_spend_drops_zero_cost_segments() -> None:
    segments = [
        SegmentMetrics(key="a", label="A", metrics=_period(cost=0.0, clicks=100, conversions=0.0)),
        SegmentMetrics(key="b", label="B", metrics=_period(cost=100.0, clicks=100, conversions=0.0)),
    ]
    summary = empty_spend(segments)
    assert summary.total_cost == 100.0
    assert {item.key for item in summary.segments} == {"b"}


def test_empty_spend_share_percent_and_ordering() -> None:
    segments = [
        SegmentMetrics(key="a", label="A", metrics=_period(cost=300.0, clicks=100, conversions=0.0)),
        SegmentMetrics(key="b", label="B", metrics=_period(cost=100.0, clicks=100, conversions=0.0)),
        SegmentMetrics(key="c", label="C", metrics=_period(cost=600.0, clicks=100, conversions=5.0)),
    ]
    summary = empty_spend(segments)
    assert summary.total_cost == 1000.0
    assert summary.empty_cost == 400.0
    assert math.isclose(summary.empty_share_pct, 40.0)
    assert [item.key for item in summary.segments] == ["a", "b"]


def test_empty_spend_with_baseline_cr_threshold() -> None:
    # baseline_cr=0.1 -> need clicks >= 3 / 0.1 = 30 for a zero to be reliable.
    segments = [
        SegmentMetrics(key="a", label="A", metrics=_period(cost=100.0, clicks=25, conversions=0.0)),
        SegmentMetrics(key="b", label="B", metrics=_period(cost=100.0, clicks=35, conversions=0.0)),
    ]
    summary = empty_spend(segments, baseline_cr=0.1)
    by_key = {item.key: item for item in summary.segments}
    assert by_key["a"].reliable is False
    assert by_key["b"].reliable is True


# ---------------------------------------------------------------------------
# 8. estimate_savings scales to 30 days
# ---------------------------------------------------------------------------


def test_estimate_savings_scales_short_period_to_30_days() -> None:
    segment = SegmentMetrics(
        key="a",
        label="A",
        metrics=_period(
            date_from=date(2026, 8, 1),
            date_to=date(2026, 8, 7),  # 7 days inclusive
            cost=700.0,
            clicks=100,
            conversions=0.0,
        ),
    )
    estimate = estimate_savings(segment, baseline_cpa=None)
    assert math.isclose(estimate.monthly_cost_saved, 700.0 / 7 * 30)
    assert estimate.conversions_at_risk == 0.0


def test_estimate_savings_scales_long_period_to_30_days() -> None:
    segment = SegmentMetrics(
        key="a",
        label="A",
        metrics=_period(
            date_from=date(2026, 7, 1),
            date_to=date(2026, 8, 29),  # 60 days inclusive
            cost=6000.0,
            clicks=1000,
            conversions=60.0,
        ),
    )
    estimate = estimate_savings(segment, baseline_cpa=None)
    assert math.isclose(estimate.monthly_cost_saved, 6000.0 / 60 * 30)
    assert math.isclose(estimate.conversions_at_risk, 60.0 / 60 * 30)


def test_estimate_savings_single_day_period() -> None:
    segment = SegmentMetrics(
        key="a",
        label="A",
        metrics=_period(
            date_from=date(2026, 8, 1),
            date_to=date(2026, 8, 1),
            cost=100.0,
            clicks=10,
            conversions=1.0,
        ),
    )
    estimate = estimate_savings(segment, baseline_cpa=None)
    assert math.isclose(estimate.monthly_cost_saved, 3000.0)
    assert math.isclose(estimate.conversions_at_risk, 30.0)


def test_estimate_savings_degenerate_period_does_not_raise() -> None:
    segment = SegmentMetrics(
        key="a",
        label="A",
        metrics=_period(
            date_from=date(2026, 8, 10),
            date_to=date(2026, 8, 9),
            cost=1000.0,
            clicks=10,
            conversions=2.0,
        ),
    )
    estimate = estimate_savings(segment, baseline_cpa=None)
    assert estimate.monthly_cost_saved == 0.0
    assert estimate.conversions_at_risk is None
    assert estimate.confidence == "insufficient"


# ---------------------------------------------------------------------------
# Spend materiality and impression-based confidence (TZ-03 part 1)
# ---------------------------------------------------------------------------


def test_large_spend_growth_is_significant() -> None:
    previous = _period(cost=1000.0, clicks=100, conversions=5.0)
    current = _period(cost=10000.0, clicks=100, conversions=5.0)
    result = compare(current, previous)
    assert result.cost.percent == 900.0
    assert result.cost.is_significant is True


def test_small_absolute_spend_growth_is_not_significant() -> None:
    # +200% but only 100 roubles: relatively loud, materially nothing.
    previous = _period(cost=50.0, clicks=100, conversions=5.0)
    current = _period(cost=150.0, clicks=100, conversions=5.0)
    result = compare(current, previous)
    assert result.cost.percent == 200.0
    assert result.cost.is_significant is False


def test_small_relative_spend_growth_is_not_significant() -> None:
    # 5000 roubles more, but only 5% of the window: not a change of behaviour.
    previous = _period(cost=100000.0, clicks=100, conversions=5.0)
    current = _period(cost=105000.0, clicks=100, conversions=5.0)
    result = compare(current, previous)
    assert result.cost.percent == 5.0
    assert result.cost.absolute == 5000.0
    assert result.cost.is_significant is False


def test_spend_significance_needs_both_thresholds() -> None:
    previous = _period(cost=5000.0, clicks=100, conversions=5.0)
    current = _period(cost=6000.0, clicks=100, conversions=5.0)
    result = compare(current, previous)
    assert result.cost.absolute == 1000.0
    assert result.cost.percent == 20.0
    assert result.cost.is_significant is True


def test_impressions_confidence_uses_impressions_not_clicks() -> None:
    previous = _period(impressions=60000, clicks=100, cost=1000.0, conversions=5.0)
    current = _period(impressions=61000, clicks=100, cost=1000.0, conversions=5.0)
    result = compare(current, previous)
    assert result.impressions.confidence == "high"
    assert result.ctr.confidence == "high"
    # Clicks-based metrics keep their own basis.
    assert result.clicks.confidence == "low"


def test_impression_confidence_thresholds() -> None:
    cases = [(60000, "high"), (20000, "medium"), (5000, "low"), (500, "insufficient")]
    for impressions, expected in cases:
        result = compare(
            _period(impressions=impressions, clicks=10, cost=100.0, conversions=1.0),
            _period(impressions=impressions, clicks=10, cost=100.0, conversions=1.0),
        )
        assert result.impressions.confidence == expected, impressions
