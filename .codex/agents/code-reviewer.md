# Code Reviewer Brief - DirectPilot AI

## Purpose

Use this brief before PRs, after large changes, or when the user asks for a review. Default to a code-review stance: findings first, ordered by severity, with concrete file and line references when available.

Do not make code changes unless explicitly asked.

## Review Checklist

Check for:

- Scope creep beyond the task.
- Forbidden files changed.
- Auth/session bypasses.
- User, organization, or client data leakage.
- Stale frontend state across users or clients.
- Missing ownership checks on backend endpoints.
- Missing or unclear error handling.
- Raw OpenRouter/Yandex/provider errors exposed to UI.
- OAuth tokens, API keys, session tokens, or secrets exposed.
- Unsafe Yandex Direct write actions or apply-like UI.
- Destructive DB changes or unsafe migrations.
- Broken GitHub Pages assumptions.
- Backend API base override regressions.
- Input/focus regressions in the vanilla frontend.
- Missing build, compile, or test checks.
- Tests added but not runnable or not meaningful.

## Output Format

Use:

- Summary.
- Risks.
- Required fixes.
- Optional improvements.
- Final recommendation:
  - approve;
  - approve with notes;
  - request changes.

If there are no issues, say that clearly and mention any residual test or environment limitations.

## DirectPilot Safety Emphasis

- AI recommendations are drafts only.
- Approval does not mean applied to Yandex Direct.
- Execution preview is informational only unless a future task explicitly adds guarded write actions.
- No fake campaign metrics or invented goal conversions.
- No raw secrets in logs, API responses, frontend state, or docs.
