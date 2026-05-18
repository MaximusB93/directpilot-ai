# DirectPilot AI

Визуальный прототип SaaS-сервиса для автоматизации аудита, мониторинга и оптимизации кампаний Яндекс.Директа с помощью ИИ.

## Локальный запуск

```bash
npm run dev
```

После запуска откройте в браузере:

```text
http://localhost:5173
```

## Проверка проекта

```bash
npm run build
```

Команда запускает статическую проверку ключевых файлов прототипа.

## Backend API

В проект добавлен первый backend-каркас в папке `backend/`. Он пока работает на mock-данных, но уже задаёт будущий контракт API для фронтенда: клиенты, кампании, AI-аудит, рекомендации и интеграции.

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

После запуска доступны:

```text
http://localhost:8000/health
http://localhost:8000/docs
```

## Деплой backend на Vercel

Для Vercel добавлен root-level entrypoint `index.py`, который экспортирует FastAPI-приложение как `app`. Также есть `backend/index.py` на случай, если в настройках Vercel выбран Root Directory = `backend`. Это нужно потому, что Vercel автоматически ищет FastAPI entrypoint в `index.py`, `app.py`, `server.py` или аналогичных путях.

Также добавлен корневой `requirements.txt`, который подключает зависимости из `backend/requirements.txt`, чтобы Vercel установил FastAPI-зависимости при деплое из корня репозитория.

После деплоя backend должен отвечать:

```text
https://directpilot-ai.vercel.app/
https://directpilot-ai.vercel.app/health
https://directpilot-ai.vercel.app/docs
https://directpilot-ai.vercel.app/api/v1/clients
```

Если корневой URL раньше возвращал `{"detail": "not found"}`, это означало, что FastAPI-приложение запущено, но у него не было маршрута `/`. Теперь маршрут `/` отдаёт короткий статус backend и ссылки на основные endpoint'ы.

## Подключение Яндекс.Директа

В backend добавлен первый OAuth entrypoint для подключения аккаунта Яндекса:

```text
GET /api/v1/auth/yandex/start
GET /api/v1/auth/yandex/callback
```

Для реального запуска нужны `DATABASE_URL`, `TOKEN_ENCRYPTION_KEY`, `YANDEX_CLIENT_ID`, `YANDEX_CLIENT_SECRET` и `YANDEX_REDIRECT_URI`. Текущая версия формирует auth URL, меняет confirmation code на OAuth token и сохраняет подключение в Postgres с шифрованием токенов.

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



## Личный кабинет без предзагруженных демо-аккаунтов

В кабинете больше нет заранее созданных клиентов и рекламных показателей. Пользователь добавляет клиента вручную в разделе **Клиенты**: название проекта, логин Яндекс.Директа и ID счётчика Метрики. Это временно сохраняется в `localStorage` как клиентская карточка до подключения backend-хранилища клиентов.

Подключение Яндекса остаётся через backend OAuth-flow: секреты и токены не попадают во frontend. Следующий production-шаг — сохранять связи `client -> yandex direct login -> metrica counter` в базе данных и загружать кампании/цели для выбранного клиента.

OpenRouter API key также нельзя добавлять в код. Его нужно задавать только через переменную окружения `OPENROUTER_API_KEY` на backend/Vercel; static validation дополнительно проверяет, что `sk-or-` не попал во frontend-файлы.

## OpenRouter и AI-модели

AI-слой подключается через backend, чтобы OpenRouter API key не попадал в браузер и GitHub Pages. Frontend вызывает только наши endpoints:

```text
GET /api/v1/ai/openrouter/status
POST /api/v1/ai/openrouter/generate
```

Для production задайте переменные окружения на backend/Vercel:

```text
OPENROUTER_API_KEY=<openrouter-api-key>
OPENROUTER_DEFAULT_MODEL=openrouter/auto
OPENROUTER_ALLOW_CUSTOM_MODELS=true
OPENROUTER_MODELS=openrouter/auto,openai/gpt-4o-mini,anthropic/claude-3.5-sonnet,google/gemini-flash-1.5
OPENROUTER_SITE_URL=https://directpilot-ai.vercel.app
OPENROUTER_APP_NAME=DirectPilot AI
```

Список быстрых вариантов управляется через `OPENROUTER_MODELS`: добавляйте туда модели, которые готовы использовать по качеству, цене и лимитам. Если `OPENROUTER_ALLOW_CUSTOM_MODELS=true`, в интерфейсе кабинета можно выбрать пункт **«Ввести модель вручную»** и указать точный id модели OpenRouter. Лучший UX — держать 3–5 проверенных моделей в выпадающем списке, а ручной ввод использовать для тестов новых моделей без redeploy.

Важно: не вставляйте реальные OpenRouter-ключи в код, README, frontend или Pull Request. Если ключ уже был отправлен в чат или коммит, его нужно отозвать в OpenRouter и выпустить новый.

### Как правильно использовать ИИ в DirectPilot AI

Рекомендуемый путь — не начинать с fine-tuning. Для рекламного продукта лучше идти по этапам:

1. **Данные и контекст.** Нормализовать выгрузки Direct API, Метрики и CRM: расходы, клики, конверсии, цели, выручку, маржу, статусы кампаний, историю изменений.
2. **RAG/контекстное обогащение.** Передавать модели только релевантный срез данных клиента, правила агентства, KPI и ограничения. Это дешевле и безопаснее обучения.
3. **Guardrails.** Запретить модели применять изменения напрямую: только аудит, объяснение, dry-run, diff, approval и журнал действий.
4. **Оценка качества.** Собрать набор эталонных кейсов: хорошие/плохие рекомендации, типовые ошибки, формат ответа. Проверять модели на этом наборе перед заменой default model.
5. **Fine-tuning позже.** Обучать модель стоит только когда накопятся сотни/тысячи проверенных примеров с ожидаемыми ответами. Fine-tuning полезен для стиля, классификации и стабильного формата, но не заменяет свежие данные из API.


### AI-чат через MCP-инструменты

Для интерактивной аналитики добавлен endpoint:

```text
POST /api/v1/ai/chat
```

Чат принимает `client_id`, `message`, выбранную `model` и короткую историю диалога. Backend сам выбирает MCP-инструменты по тексту вопроса: профиль клиента, кампании Яндекс.Директа, цели Яндекс.Метрики, audit issues, рекомендации и интеграции. Сейчас MCP-инструменты используют нормализованные mock-данные и безопасные read-only/fallback-ответы; после подключения реальных Direct/Metrica connectors этот слой можно заменить на реальные tool calls без изменения UI-контракта.

Пример запроса:

```json
{
  "client_id": "furniture",
  "model": "openrouter/auto",
  "message": "Почему растёт CPA и какие цели Метрики проверить?",
  "history": [],
  "client_context": {
    "id": "client-1",
    "name": "Новый клиент",
    "directLogin": "client-login",
    "metricaCounter": "12345"
  }
}
```

Ответ содержит текст аналитики и `tool_traces` — список MCP tools, которые были вызваны для ответа. Если OpenRouter не настроен, чат возвращает deterministic fallback по MCP-контексту, чтобы demo оставалось рабочим без секретов.

### Структурированные AI-рекомендации клиента

Помимо свободного prompt-поля есть продуктовый endpoint, который собирает контекст клиента на backend: профиль клиента, кампании, найденные audit issues, текущие рекомендации и guardrails. Он возвращает структурированный черновик рекомендаций для UI и будущего approval-flow:

```text
POST /api/v1/clients/{client_id}/ai/recommendations
```

Тело запроса опционально:

```json
{ "model": "openrouter/auto", "client_context": { "id": "client-1", "name": "Новый клиент" } }
```

Если `OPENROUTER_API_KEY` не настроен, endpoint не падает: он возвращает безопасный deterministic fallback на mock-данных, чтобы интерфейс рекомендаций можно было демонстрировать без production-секретов. В production OpenRouter-ответ должен оставаться черновиком: специалист проверяет evidence, запускает dry-run/preview и только затем отправляет изменение на approval.

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

## MCP server

В backend добавлен первый read-only MCP-сервер для AI-клиентов. Он запускается через stdio-транспорт FastMCP и отдаёт tools для клиентов, кампаний, аудита, рекомендаций и интеграций на mock-данных.

```bash
cd backend
python -m app.mcp.server
```

## Публикация через GitHub Pages

Проект можно публиковать двумя способами.

### Рекомендуемый вариант: GitHub Actions

В репозитории есть workflow `.github/workflows/pages.yml`. Он запускается после push в `main`, проверяет статический прототип через `npm run build`, собирает артефакт из `index.html`, `src/` и `.nojekyll`, затем публикует его в GitHub Pages.

Чтобы включить этот вариант:

1. Откройте репозиторий на GitHub.
2. Перейдите в **Settings → Pages**.
3. В блоке **Build and deployment** выберите **Source: GitHub Actions**.
4. Смержите pull request в `main` или запустите workflow вручную через **Actions → Deploy GitHub Pages → Run workflow**.
5. После успешного workflow сайт будет доступен по адресу вида:

```text
https://<github-username>.github.io/<repository-name>/
```

### Альтернативный вариант: Deploy from branch

Так как прототип статический и файл `index.html` лежит в корне репозитория, его также можно опубликовать без workflow:

1. Откройте репозиторий на GitHub.
2. Перейдите в **Settings → Pages**.
3. В блоке **Build and deployment** выберите **Source: Deploy from a branch**.
4. В поле **Branch** выберите `main`.
5. В поле папки выберите `/ (root)`.
6. Нажмите **Save**.

## Что добавлено во втором UI-спринте

- Демо-кабинет с боковой навигацией и переключением разделов без backend.
- Dashboard агентства со сводными KPI, AI score, задачами на сегодня и таблицей кампаний.
- Раздел клиентов с mock-портфелем агентства.
- Раздел AI-аудита с приоритетами, доказательствами и рекомендуемыми действиями.
- Раздел рекомендаций с риском, ожидаемым эффектом, объектами и CTA для подтверждения.
- Раздел отчётов и экран политик безопасного автопилота.
- Отдельный файл `src/data.js` с mock-данными для будущего подключения API.

## Что входит в первый UI-прототип

- Лендинг с позиционированием продукта для агентств и PPC-команд.
- Hero-блок с демонстрационным дашбордом эффективности.
- Карточки модулей: аудит, мониторинг, рекомендации, автопилот, чат и отчёты.
- Workflow от read-only режима до безопасного автопилота.
- Блок безопасности с политиками, лимитами и журналом изменений.
