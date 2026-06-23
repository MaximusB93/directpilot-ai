from app.services.ai_recommendations import _build_prompt, build_client_ai_context_from_db


def test_ai_prompt_includes_directpilot_knowledge_section():
    prompt = _build_prompt(
        {
            "client": {"id": "client-1", "name": "Demo"},
            "business_context": {"status": "empty"},
            "summary": {
                "selectedGoalIds": ["35371875"],
                "searchQueryInsights": {"totalQueries": 10},
                "yesterdayCampaignSummary": {"hasData": True},
            },
            "conversion_context": {"has_goal_data": False},
        }
    )

    assert "База знаний DirectPilot" in prompt
    assert "direct_data_limitations.md" in prompt
    assert "direct_negative_keywords_rules.md" in prompt
    assert "missingData" in prompt


def test_db_context_builder_adds_knowledge_snippets(monkeypatch):
    class Client:
        id = "client-1"
        name = "Demo"
        direct_login = "demo"
        metrica_counter = "123"
        main_goal_id = None
        conversion_goal_ids = None
        target_cpa = None
        notes = None
        sync_status = "idle"
        sync_error = None
        last_synced_at = None
        sync_version = 0
        yandex_account_id = None
        organization_id = "org-1"

    class QueryResult:
        def order_by(self, *args, **kwargs):
            return self

        def all(self):
            return []

    class DB:
        def get(self, model, item_id):
            return Client() if item_id == "client-1" else None

        def scalar(self, statement):
            return None

        def scalars(self, statement):
            return QueryResult()

    monkeypatch.setattr(
        "app.services.ai_recommendations.build_performance_summary",
        lambda db, client_id: {
            "client": {"id": client_id, "name": "Demo"},
            "campaigns": [],
            "selectedGoalIds": [],
            "hasGoalData": False,
            "syncDiagnostics": {"directGoalDataAvailable": False},
            "searchQueryInsights": {},
            "yesterdayCampaignSummary": {},
        },
    )
    monkeypatch.setattr(
        "app.services.ai_recommendations.build_optimization_plan",
        lambda db, client_id: {"actions": []},
    )

    context = build_client_ai_context_from_db(DB(), "client-1")

    assert "knowledge_snippets" in context
    assert 1 <= len(context["knowledge_snippets"]) <= 5
    assert any(item["source"] == "direct_data_limitations.md" for item in context["knowledge_snippets"])
