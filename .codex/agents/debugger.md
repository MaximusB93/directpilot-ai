# Debugger Brief - DirectPilot AI

## Purpose

Use this brief for CI failures, tracebacks, API 500s, frontend broken state, OAuth issues, sync failures, OpenRouter errors, Yandex errors, and regression investigation.

## First Step: Collect Exact Evidence

Do not guess. Start by collecting the exact error:

- command output;
- browser console message;
- network response payload and status;
- backend logs;
- failing endpoint and method;
- selected client id and logged-in email when relevant;
- current branch and `git status`;
- recent diff if the failure followed a change.

## Isolation Checklist

Classify the issue as one or more of:

- frontend state/render issue;
- backend API issue;
- DB schema issue;
- auth/session issue;
- client ownership/scoping issue;
- third-party API issue;
- deployment/environment issue;
- stale cache or GitHub Pages artifact issue.

## Known DirectPilot Patterns

- OpenRouter 429 usually means rate limit or provider overload, especially for free/custom models.
- CORS can hide a backend 500 from the browser; inspect the real network response and backend logs.
- Git branch/path confusion must be solved before editing.
- Yandex OAuth callback success but missing account often means workspace binding or organization scoping issue.
- `create_all` does not add new columns to existing Postgres tables; check safe schema patches.
- Client data appearing under another email usually means missing organization filter or unscoped localStorage.
- Input losing focus often comes from app-level click handlers or rerendering around native inputs.

## Expected Output

Provide:

- root cause;
- minimal fix;
- affected files;
- verification steps;
- residual risk.

## Boundaries

- Avoid broad rewrites.
- Do not change architecture unless the evidence requires it.
- Do not add fake data to hide sync or API failures.
- Do not expose secrets while debugging.
- Do not add Yandex Direct write actions while fixing read-only or approval flows.
