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
- `GET /api/v1/auth/yandex/status` — статус подключённых Яндекс-аккаунтов.
- `GET /api/v1/yandex-direct/connection` — проверить наличие токена для Direct API.
- `GET /api/v1/yandex-direct/campaigns` — получить кампании через read-only Direct API connector.
- `POST /api/v1/recommendations/{recommendation_id}/preview` — dry-run preview рекомендации.
- `POST /api/v1/approvals` — создать запрос на подтверждение.
- `POST /api/v1/approvals/{approval_id}/approve` — подтвердить preview.
- `POST /api/v1/approvals/{approval_id}/reject` — отклонить preview.
- `GET /api/v1/audit-log` — журнал preview/approval событий.

## Деплой на Vercel

Backend можно деплоить из корня репозитория на Vercel. Для этого в корне есть:

- `index.py` — entrypoint, который экспортирует FastAPI-приложение `app`;
- `backend/index.py` — такой же entrypoint для варианта, где Root Directory в Vercel установлен как `backend`;
- `requirements.txt` — подключает зависимости из `backend/requirements.txt`.

Проверочные URL после деплоя:

```text
/
/health
/docs
/api/v1/clients
/api/v1/recommendations
```

Корневой route `/` добавлен специально для Vercel-домена, чтобы открытие `https://directpilot-ai.vercel.app/` показывало статус API, а не стандартный FastAPI 404 `{"detail":"Not Found"}`.

## Yandex Direct OAuth

Для реального подключения аккаунта нужно зарегистрировать OAuth-приложение Яндекса, запросить доступ к Direct API и задать переменные окружения:

```bash
export DATABASE_URL=postgresql+psycopg://<db-user>:<db-password>@<db-host>:5432/<db-name>
export TOKEN_ENCRYPTION_KEY=<fernet-key>
export YANDEX_CLIENT_ID=<client-id>
export YANDEX_CLIENT_SECRET=<client-secret>
export YANDEX_REDIRECT_URI=http://localhost:8000/api/v1/auth/yandex/callback
```

После этого endpoint `GET /api/v1/auth/yandex/start` вернёт `auth_url`, которую пользователь должен открыть для выдачи доступа. Callback меняет confirmation code на access token, получает информацию Яндекс ID и сохраняет OAuth token в Postgres в зашифрованном виде.

## Реальное подключение Яндекс.Директа и Postgres

Backend теперь поддерживает production-путь подключения Яндекса:

1. `GET /api/v1/auth/yandex/start` формирует OAuth URL со scopes `direct:api`, `metrika:read`, `login:info`.
2. `GET /api/v1/auth/yandex/callback` меняет `code` на OAuth token, получает базовую информацию Яндекс ID и сохраняет подключение.
3. OAuth tokens сохраняются в Postgres в зашифрованном виде.
4. `GET /api/v1/auth/yandex/status` показывает подключённые аккаунты.
5. `GET /api/v1/yandex-direct/connection` проверяет наличие токена для Direct API.
6. `GET /api/v1/yandex-direct/campaigns` делает первый read-only запрос в Yandex Direct API.
7. `GET /api/v1/yandex-direct/reports/campaigns?days=30` получает кампанийную статистику из Yandex Direct Reports API: показы, клики, расход, CTR, средний CPC и конверсии.

Для Vercel нужно добавить Environment Variables без коммита секретов в репозиторий:

```text
ENVIRONMENT=production
DATABASE_URL=postgresql+psycopg://<db-user>:<db-password>@<db-host>:5432/<db-name>
TOKEN_ENCRYPTION_KEY=<fernet-key>
YANDEX_CLIENT_ID=<client-id>
YANDEX_CLIENT_SECRET=<client-secret>
YANDEX_REDIRECT_URI=https://directpilot-ai.vercel.app/api/v1/auth/yandex/callback
YANDEX_OAUTH_SCOPES=direct:api metrika:read login:info
```

Ключ шифрования можно сгенерировать локально:

```bash
python - <<'PY'
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode())
PY
```



Если `/api/v1/auth/yandex/start` возвращает `auth_url`, где `client_id` выглядит как `%E2%80%A2%E2%80%A2...`, значит в `YANDEX_CLIENT_ID` случайно вставлено замаскированное значение из UI Vercel. Нужно нажать Edit у переменной и вставить реальный Client ID из кабинета Яндекса. Backend теперь считает такие значения невалидными и возвращает понятное сообщение вместо генерации OAuth URL с bullets.

Для проверки реально задеплоенных маршрутов есть диагностический endpoint:

```text
GET /api/v1/debug/routes
```



Проверить первый отчёт по кампаниям после подключения аккаунта:

```text
GET /api/v1/yandex-direct/reports/campaigns?days=30
```



Если в аккаунте нет свежих кампаний, можно запросить весь доступный период статистики:

```text
GET /api/v1/yandex-direct/reports/campaigns?date_range=ALL_TIME
```

Важно: Yandex Direct хранит статистику за три года до текущего месяца. Если запросить слишком старую дату, например `date_from` раньше доступного периода, backend вернёт понятную ошибку с минимальной допустимой датой вместо общего `400 Bad Request` от Direct API.



По умолчанию отчёты запрашиваются с `processing_mode=auto`: если Яндекс не может построить отчёт online, он ставит отчёт в offline-очередь, а backend несколько раз повторяет тот же запрос в пределах `max_wait_seconds`. Если отчёт ещё не готов, повторите тот же URL позже.

```text
GET /api/v1/yandex-direct/reports/campaigns?date_from=2025-11-01&date_to=2025-12-31&processing_mode=auto&max_wait_seconds=20
```

Для агентских аккаунтов можно передать логин клиента:

```text
GET /api/v1/yandex-direct/reports/campaigns?days=30&client_login=<client-login>
```

Секреты, пароль базы и OAuth secret нельзя коммитить в Git. Примеры переменных без реальных значений лежат в `.env.example` и `backend/.env.example`.



## Email-авторизация

Добавлен passwordless-вход по email-коду:

```text
POST /api/v1/auth/email/request-code
POST /api/v1/auth/email/verify-code
```

Для отправки писем в production задайте SMTP-переменные окружения:

```text
SMTP_HOST=<smtp-host>
SMTP_PORT=587
SMTP_USERNAME=<smtp-username>
SMTP_PASSWORD=<smtp-password>
SMTP_FROM_EMAIL=noreply@directpilot.ai
SMTP_USE_TLS=true
```

Для локальной разработки можно временно включить `EMAIL_AUTH_DEV_MODE=true`; тогда код вернётся в `dev_code` в ответе API, но в production так делать нельзя.

### Где взять SMTP-переменные

SMTP — это данные почтового сервера, через который backend отправляет письма с кодом входа. Их нужно брать не в Vercel, а у почтового провайдера/сервиса рассылок:

- если у вас корпоративная почта на домене — в настройках почты домена, например Яндекс 360, Google Workspace, Zoho и т.п.;
- если хотите transactional email — в сервисах Postmark, Mailgun, SendGrid, Brevo и аналогах;
- `SMTP_HOST` — адрес SMTP-сервера провайдера;
- `SMTP_PORT` — обычно `587` для TLS/STARTTLS;
- `SMTP_USERNAME` — логин SMTP-ящика или API user;
- `SMTP_PASSWORD` — пароль приложения/API key SMTP;
- `SMTP_FROM_EMAIL` — адрес отправителя, например `noreply@your-domain.ru`;
- `SMTP_USE_TLS=true` — включить защищённое соединение.

`EMAIL_AUTH_DEV_MODE=true` — только режим разработки: backend не отправляет письмо, а возвращает код в поле `dev_code` ответа API. Это удобно локально, но в production так делать нельзя, потому что код входа будет виден в ответе браузеру.

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
