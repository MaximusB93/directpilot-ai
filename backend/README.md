# DirectPilot AI Backend

Минимальный backend-каркас для будущего API DirectPilot AI. Сейчас API работает на mock-данных и повторяет сущности фронтенд-прототипа: клиенты, кампании, AI-аудит, рекомендации, отчёты, интеграции и безопасный автопилот.

## Локальный запуск

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

После запуска:

```text
http://localhost:8000/health
http://localhost:8000/docs
```

## Первые endpoint'ы

- `GET /health` — health-check сервиса.
- `GET /api/v1/clients` — список клиентов агентства.
- `GET /api/v1/clients/{client_id}` — карточка клиента.
- `GET /api/v1/clients/{client_id}/campaigns` — кампании клиента.
- `GET /api/v1/audit/issues` — mock AI-аудит.
- `GET /api/v1/recommendations` — список рекомендаций.
- `GET /api/v1/recommendations/{recommendation_id}` — детальная рекомендация.
- `GET /api/v1/integrations` — статусы будущих интеграций.
- `POST /api/v1/recommendations/{recommendation_id}/preview` — dry-run preview рекомендации.
- `POST /api/v1/approvals` — создать запрос на подтверждение.
- `POST /api/v1/approvals/{approval_id}/approve` — подтвердить preview.
- `POST /api/v1/approvals/{approval_id}/reject` — отклонить preview.
- `GET /api/v1/audit-log` — журнал preview/approval событий.

## MCP server v1

Добавлен read-only MCP-сервер на FastMCP поверх mock-данных backend-сервиса. Он предназначен для AI-клиентов и будущих агентов, которым нужно безопасно читать клиентов, кампании, аудит, рекомендации и интеграции.

```bash
cd backend
python -m app.mcp.server
```

MCP tools ничего не меняют в Яндекс.Директе. В v2 добавлен только dry-run preview и чтение audit log; реальные write-операции должны появляться только после policy checks, approval workflow и rollback snapshots.

## Что дальше

1. Подключить реальное хранилище: PostgreSQL для сущностей и ClickHouse для статистики.
2. Реализовать OAuth Яндекса и безопасное хранение токенов.
3. Добавить connector к Yandex Direct API и Yandex Metrica API.
4. Перевести frontend с mock-данных на эти endpoint'ы.
