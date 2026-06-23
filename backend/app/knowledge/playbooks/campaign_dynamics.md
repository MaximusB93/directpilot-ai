# Campaign Dynamics Playbook v1

Use this playbook for read-only Yandex Direct dynamics analysis.

## Analysis order

1. Data quality: check whether cached daily campaign stats cover last 7, 14, and 30 days.
2. Account overview: compare last7 vs previous7, last14 vs previous14, and inspect last30.
3. Campaign segmentation: identify campaigns that worsened, improved, or have too little data.
4. Cause hypotheses: connect metric changes to likely next-level data needs.
5. Drill-down plan: decide whether to inspect search queries, keywords, ads, landing pages, goals, devices, geo, demographics, bids, budget, or moderation/status.
6. Safe action plan: produce draft/manual-review recommendations only.

## Metrics

- Cost
- Impressions
- Clicks
- CTR
- Avg CPC
- Selected goal conversions
- CPA by selected goals
- Conversion rate by selected goals

## Rules

- Spend without conversions: cost > 0, selected goal conversions = 0, and clicks >= 10.
- High CPA: CPA by selected goals is above target CPA by more than 25%.
- CPA growth: CPA by selected goals increased by more than 30%.
- Conversion drop: selected goal conversions dropped by more than 30% while cost is stable or growing.
- CTR drop: CTR dropped by more than 20% with enough impressions.
- CPC growth: average CPC increased by more than 25%.
- Volume drop: clicks or impressions dropped by more than 30%.
- Promising growth: conversions grew and CPA is below target.
- Low data: impressions or clicks are too low for strong conclusions.

## Drill-down mapping

- Low CTR -> ads, keywords, search queries.
- High CPA -> search queries, ad groups, goals, landing pages.
- Spend without conversions -> search queries, goals, landing pages, strategy.
- CPC growth -> bids, auction pressure, competitors, strategy.
- Volume drop -> budget, impressions, bids, moderation/status.
- Conversion drop -> goals, landing pages, query intent, ad relevance.

## Safety

- Do not apply changes to Yandex Direct.
- Do not suggest automatic bid, budget, campaign, keyword, or negative-keyword changes.
- All recommendations are dry-run drafts for manual review and approval.
- Do not invent trend causes when daily data is missing.
