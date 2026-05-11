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
- `GET /api/v1/auth/yandex/callback` — принять confirmation code от Яндекса.
- `GET /api/v1/auth/yandex/start` — сформировать OAuth-ссылку подключения Яндекса.
- `POST /api/v1/recommendations/{recommendation_id}/preview` — dry-run preview рекомендации.
- `POST /api/v1/approvals` — создать запрос на подтверждение.
- `POST /api/v1/approvals/{approval_id}/approve` — подтвердить preview.
- `POST /api/v1/approvals/{approval_id}/reject` — отклонить preview.
- `GET /api/v1/audit-log` — журнал preview/approval событий.

## Yandex Direct OAuth

Для реального подключения аккаунта нужно зарегистрировать OAuth-приложение Яндекса, запросить доступ к Direct API и задать переменные окружения:

```bash
export YANDEX_CLIENT_ID=<client-id>
export YANDEX_REDIRECT_URI=http://localhost:8000/api/v1/auth/yandex/callback
```

После этого endpoint `GET /api/v1/auth/yandex/start` вернёт `auth_url`, которую пользователь должен открыть для выдачи доступа. Callback v1 пока принимает confirmation code и не хранит токены; обмен code на access token и encrypted token storage — следующий шаг.

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
