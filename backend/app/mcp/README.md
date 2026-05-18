# DirectPilot MCP Server

Первая версия MCP-сервера для DirectPilot AI. Сервер собран на официальном Python MCP SDK / FastMCP и отдаёт read-only tools на mock-данных backend-сервиса.

## Запуск

```bash
cd backend
python -m app.mcp.server
```

## Пример конфигурации MCP-клиента

```json
{
  "mcpServers": {
    "directpilot-yandex-direct": {
      "command": "python",
      "args": ["-m", "app.mcp.server"],
      "cwd": "/absolute/path/to/directpilot-ai/backend"
    }
  }
}
```

## Tools v1

- `list_clients`
- `get_client`
- `list_campaigns`
- `list_audit_issues`
- `list_recommendations`
- `get_recommendation`
- `list_integrations`
- `list_audit_log`
- `preview_recommendation`

## Ограничения v1

- Read-only tools плюс dry-run preview без применения изменений.
- Данные берутся из `app.services.mock_data`.
- Реальные write-операции в Яндекс.Директе должны добавляться только после policy checks, approval workflow, audit log и rollback snapshots.
