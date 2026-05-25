# Backend Architect Brief - DirectPilot AI

## Purpose

Use this brief for FastAPI, SQLAlchemy, auth scoping, API schemas, database models, sync logic, Yandex integrations, OpenRouter backend behavior, and backend safety.

DirectPilot AI uses a FastAPI backend deployed on Vercel, PostgreSQL when configured, and SQLAlchemy models. There is no Alembic setup yet.

## Core Backend Rules

- Keep routers thin: validate input, check ownership, call services, return schemas.
- Keep business logic in services when feasible.
- Preserve `Authorization: Bearer <session_token>` session auth.
- Preserve the MVP model: one email = one workspace/organization.
- Protect client ownership checks on every client-specific endpoint.
- Never expose OAuth tokens, API keys, session hashes, or raw secrets.
- Never return raw provider payloads if they contain sensitive or confusing implementation details.
- Prefer clear JSON errors over raw 500s.
- Do not introduce fake/demo campaign data into authenticated backend flows.

## Database Rules

- SQLAlchemy models are the persistence shape.
- No destructive migrations.
- Safe MVP schema patches only:
  - `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`
  - safe table creation through SQLAlchemy/create-all-compatible additions
  - no drop, truncate, destructive alter, or data deletion outside the explicit task
- Existing data must not be dropped.
- Add tests for data ownership and migration-sensitive behavior when feasible.

## Auth And Ownership

- Protected endpoints must require current authenticated user/session.
- Query clients by both `client_id` and current organization.
- User A must not see, update, sync, delete, bind, preview, approve, or analyze User B's data.
- Local fallback/demo behavior must not influence authenticated backend ownership logic.

## Yandex Rules

- Yandex OAuth tokens must remain backend-only.
- OAuth tokens must not appear in API responses or frontend state.
- A Yandex account is connected at workspace level but must be explicitly bound to a client.
- Sync must use only the account bound to the selected client.
- Do not fall back to the latest global token.
- No Yandex Direct write actions unless explicitly approved by the roadmap and the current task.
- Until then, optimization actions are drafts, approvals, and previews only.

## Checks

Always run:

```bash
python -m compileall -q backend/app index.py backend/index.py
python -m compileall -q backend/tests
```

Run tests when available:

```bash
python -m pytest -q backend/tests
```

If `pytest` is not installed locally, say so honestly.

## Testing Guidance

Add or update tests when feasible for:

- auth/session requirements;
- client ownership;
- cross-user data isolation;
- schema patch behavior;
- sync safety and no fake data;
- Yandex account binding;
- normalized third-party provider errors;
- approval and execution-preview safety.
