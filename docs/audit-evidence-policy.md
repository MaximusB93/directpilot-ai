# Audit Evidence Coverage Policy

DirectPilot uses a deterministic, versioned evidence policy before producing a
causal Yandex Direct audit conclusion. The runtime source of truth is
`backend/app/services/audit_evidence_policy.py`.

## Runtime Contract

The current policy version is `audit-evidence-v1`.

For every trusted campaign signal, the policy records:

- campaign family and subtype;
- required, conditional, and forbidden evidence dimensions;
- resolved read-only capability;
- collection status and analyzed row count;
- safe limitation or reason code when evidence is unavailable.

Mandatory requests reserve the request budget before optional AI suggestions.
AI suggestions cannot remove mandatory requests. Duplicate requests are merged,
and dimensions forbidden for a campaign subtype are rejected.

Budget selection is deterministic and does not start with campaign names:

- P0: tracking prerequisites and spend without conversions;
- P1: active performance, query, placement, budget, and brand-share problems;
- P2: learning-safety and low-data signals;
- P3: stable/no-action campaigns.

Within a signal, requirements are ordered by causal dimension, trusted
deviation when available, and campaign name only as the final stable
tie-breaker. Baseline-satisfied requirements do not consume the request budget.
If the budget is exhausted, lower-priority requirements remain visible as
blocked with `mandatory_request_budget_exhausted`.

The AI planner remains responsible for proposing useful investigation branches.
The mandatory backend planner is different: it derives non-optional evidence
from trusted signals and campaign subtype, then merges those requests with the
AI proposal. Helper fallback follows the same policy.

The policy uses only capabilities registered in
`yandex_direct_read_capabilities.py`. It does not introduce Yandex Direct write
operations.

## Completion States

- `complete`: every mandatory dimension is satisfied or not applicable.
- `partial_coverage`: collection finished, but one or more mandatory dimensions
  are only partially available.
- `blocked_missing_evidence`: required evidence is still missing, blocked, or
  outside the safe request budget. The final provider call is skipped and a
  conservative backend result is returned.
- `legacy_unknown`: a completed historical job has no coverage registry. It is
  shown as legacy and is not reopened automatically.

Unavailable or invalid conversion values are never converted to zero. A known
zero remains zero; unknown data remains unavailable.

## Dataset Governance

The reviewed XLSX evaluation dataset is external development input, not an
application dependency.

- `synthetic_dev` may be used to design and review generalized mappings.
- `synthetic_test` is used only to regression-check the finished policy.
- `synthetic_holdout` content must not be read or used for policy design,
  prompts, fixtures, or few-shot examples.
- expert reasoning, expert problem statements, and expected AI behavior are not
  copied into production runtime.
- XLSX files are not packaged with the backend and production never reads them.

Run the explicit validator from the repository root:

```powershell
python scripts/validate_audit_evidence_policy.py "C:\path\to\AI_Direct_Eval_Cases_filled_ru_reviewed_v3_1.xlsx"
```

The locally reviewed `v3_2` workbook supplied for this change is treated as
the reviewed equivalent of the canonical `v3_1` dataset named in the policy
requirements. Neither filename is a runtime dependency.

The validator checks policy integrity, dev/test case coverage, campaign type
mapping, and recommendation-code mapping. For holdout rows it reads only the
split marker and reports the count.

## Runtime Signal Activation

Policy presence is not treated as runtime coverage. Every canonical signal must
have a trusted fact metric emitted by `build_observed_facts`, a hypothesis type
allowed by the current Pydantic schema, or an explicit documented
`not_auto_detectable` declaration.

Eight signals currently have deterministic activation paths. Two remain
explicitly unavailable for automatic detection:

- `learning_strategy_do_not_touch`: the current Direct baseline exposes
  strategy configuration but no trusted strategy-learning state;
- `brand_campaign_cannibalization`: DirectPilot has no calculated brand share,
  organic incrementality, or SEO evidence and never infers cannibalization from
  a campaign name.

Their evidence rules remain versioned for future trusted detectors, but they do
not activate in production today. Policy self-validation fails if another
canonical signal lacks both a real activation path and this explicit status.

## Review Checklist

When changing the policy:

1. Keep internal signal IDs and campaign subtype IDs stable where possible.
2. Map semantic dimensions only to registered read-only capabilities.
3. Keep search-only evidence out of YAN rules and YAN-only evidence out of
   search rules.
4. Add or update focused policy tests.
5. Run the external validator without adding the dataset to Git.
6. Confirm the frontend exposes only safe coverage summaries, never raw rows,
   request IDs, tokens, or provider payloads.

To add a signal, first add its stable canonical code and trusted fact or
hypothesis mapping. Then define rules for every applicable campaign subtype and
add policy tests. To add a requirement, map its semantic dimension to an
existing read-only capability before using it in a rule.

## Preview Smoke

Keep the PR in Draft until a production-shaped Preview audit confirms:

1. Search high-CPA campaigns request groups, group performance, keywords,
   keyword performance, and search queries.
2. YAN campaigns do not request search-only evidence.
3. The request trace does not repeat the same campaign/capability call during
   completion remediation.
4. Partial and blocked requirements are visible in the coverage checklist.
5. `blocked_missing_evidence` returns a safe backend result without a final
   provider call or a Yandex Direct write action.
