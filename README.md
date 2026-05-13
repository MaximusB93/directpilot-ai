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

Для реального запуска нужны `YANDEX_CLIENT_ID` и `YANDEX_REDIRECT_URI`. Текущая версия формирует auth URL и принимает confirmation code; обмен кода на токен и безопасное хранение токенов добавим следующим шагом.

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
