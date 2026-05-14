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
