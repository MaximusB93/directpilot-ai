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

## Что дальше

1. Подключить реальное хранилище: PostgreSQL для сущностей и ClickHouse для статистики.
2. Реализовать OAuth Яндекса и безопасное хранение токенов.
3. Добавить connector к Yandex Direct API и Yandex Metrica API.
4. Перевести frontend с mock-данных на эти endpoint'ы.
