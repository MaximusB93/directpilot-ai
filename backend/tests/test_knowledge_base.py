import inspect

from app.services import knowledge_base
from app.services.knowledge_base import load_knowledge_documents, select_knowledge_snippets


def _sources(snippets):
    return {item["source"] for item in snippets}


def test_budget_query_returns_budget_safety_rules():
    snippets = select_knowledge_snippets("Что делать с бюджетом и ставками?", {}, limit=5)

    assert "direct_budget_safety_rules.md" in _sources(snippets)


def test_negative_keyword_query_returns_negative_keyword_rules():
    snippets = select_knowledge_snippets("Проанализируй поисковые запросы и минус-слова", {}, limit=5)

    assert "direct_negative_keywords_rules.md" in _sources(snippets)


def test_yesterday_context_returns_analysis_and_limitations():
    snippets = select_knowledge_snippets(
        "Разбери вчера",
        {"yesterday_campaign_summary": {"hasData": True, "date": "2026-06-22"}},
        limit=5,
    )

    sources = _sources(snippets)
    assert "direct_analysis_rules.md" in sources
    assert "direct_data_limitations.md" in sources


def test_empty_business_context_returns_data_limitations():
    snippets = select_knowledge_snippets(
        "",
        {"business_context": {"status": "empty"}},
        limit=5,
    )

    assert "direct_data_limitations.md" in _sources(snippets)


def test_snippet_selection_is_limited_to_five():
    snippets = select_knowledge_snippets(
        "вчера сводка бюджет ставки расход минус поисковые запросы CPA CTR CPC CR конверсии",
        {"business_context": {"status": "empty"}, "search_query_insights": {"totalQueries": 10}},
        limit=20,
    )

    assert 1 <= len(snippets) <= 5


def test_knowledge_documents_load_without_external_retrieval():
    documents = load_knowledge_documents()
    source = inspect.getsource(knowledge_base)

    assert len(documents) == 5
    assert "requests" not in source
    assert "httpx" not in source
    assert "openai" not in source.lower()
    assert "embedding" not in source.lower()
