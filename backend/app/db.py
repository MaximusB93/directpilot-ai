from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


def _normalize_database_url(url: str) -> str:
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


class Base(DeclarativeBase):
    pass


engine = create_engine(_normalize_database_url(settings.database_url), pool_pre_ping=True) if settings.database_url else None
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False) if engine else None


def init_db() -> None:
    if engine is None:
        return
    import app.models  # noqa: F401
    import app.models_workflow  # noqa: F401

    Base.metadata.create_all(bind=engine)
    ensure_mvp_schema()


def ensure_mvp_schema() -> None:
    if engine is None:
        return

    # Temporary MVP schema patch for existing Postgres databases.
    # Replace this with Alembic migrations once migrations are introduced.
    statements = [
        "ALTER TABLE client_accounts ADD COLUMN IF NOT EXISTS sync_status VARCHAR(64) NOT NULL DEFAULT 'never_synced'",
        "ALTER TABLE client_accounts ADD COLUMN IF NOT EXISTS sync_error TEXT",
        "ALTER TABLE client_accounts ADD COLUMN IF NOT EXISTS last_synced_at TIMESTAMPTZ",
        "ALTER TABLE client_accounts ADD COLUMN IF NOT EXISTS sync_version INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE client_accounts ADD COLUMN IF NOT EXISTS yandex_account_id VARCHAR(36)",
        "ALTER TABLE client_accounts ADD COLUMN IF NOT EXISTS target_cpa INTEGER",
        "ALTER TABLE client_accounts ADD COLUMN IF NOT EXISTS main_goal_id VARCHAR(64)",
        "ALTER TABLE client_accounts ADD COLUMN IF NOT EXISTS conversion_goal_ids TEXT",
        "ALTER TABLE client_accounts ADD COLUMN IF NOT EXISTS notes TEXT",
        "ALTER TABLE direct_campaign_period_stats ADD COLUMN IF NOT EXISTS goal_id VARCHAR(64)",
        "ALTER TABLE direct_campaign_period_stats ADD COLUMN IF NOT EXISTS goal_conversions FLOAT",
        "ALTER TABLE direct_campaign_period_stats ADD COLUMN IF NOT EXISTS goal_revenue FLOAT",
        "ALTER TABLE direct_campaign_period_stats ADD COLUMN IF NOT EXISTS goal_cpa FLOAT",
        "ALTER TABLE direct_campaign_period_stats ADD COLUMN IF NOT EXISTS conversion_source VARCHAR(64)",
        "ALTER TABLE direct_campaign_period_stats ADD COLUMN IF NOT EXISTS goal_ids TEXT",
        "ALTER TABLE direct_campaign_period_stats ADD COLUMN IF NOT EXISTS conversion_warning TEXT",
        """
        CREATE TABLE IF NOT EXISTS direct_search_query_period_stats (
            id VARCHAR(36) PRIMARY KEY,
            client_id VARCHAR(64) NOT NULL,
            campaign_id VARCHAR(64),
            campaign_name VARCHAR(255),
            ad_group_id VARCHAR(64),
            ad_group_name VARCHAR(255),
            query TEXT NOT NULL,
            period_from TIMESTAMPTZ NOT NULL,
            period_to TIMESTAMPTZ NOT NULL,
            impressions INTEGER NOT NULL DEFAULT 0,
            clicks INTEGER NOT NULL DEFAULT 0,
            cost FLOAT NOT NULL DEFAULT 0,
            ctr FLOAT NOT NULL DEFAULT 0,
            avg_cpc FLOAT NOT NULL DEFAULT 0,
            conversions FLOAT NOT NULL DEFAULT 0,
            goal_ids TEXT,
            goal_conversions FLOAT,
            goal_cpa FLOAT,
            conversion_source VARCHAR(64),
            issue_flags TEXT,
            recommended_negative_keyword TEXT,
            recommendation_reason TEXT,
            loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_direct_search_query_period_stats_client_id ON direct_search_query_period_stats (client_id)",
        "CREATE INDEX IF NOT EXISTS ix_direct_search_query_period_stats_campaign_id ON direct_search_query_period_stats (campaign_id)",
        "CREATE INDEX IF NOT EXISTS ix_direct_search_query_period_stats_ad_group_id ON direct_search_query_period_stats (ad_group_id)",
        """
        CREATE TABLE IF NOT EXISTS direct_campaign_daily_stats (
            id VARCHAR(36) PRIMARY KEY,
            client_id VARCHAR(64) NOT NULL,
            stat_date DATE NOT NULL,
            campaign_id VARCHAR(64) NOT NULL,
            campaign_name VARCHAR(255) NOT NULL,
            impressions INTEGER NOT NULL DEFAULT 0,
            clicks INTEGER NOT NULL DEFAULT 0,
            cost FLOAT NOT NULL DEFAULT 0,
            ctr FLOAT NOT NULL DEFAULT 0,
            avg_cpc FLOAT NOT NULL DEFAULT 0,
            goal_ids TEXT,
            goal_conversions FLOAT,
            goal_cpa FLOAT,
            conversion_rate FLOAT,
            issue_flags TEXT,
            loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_direct_campaign_daily_stats_client_id ON direct_campaign_daily_stats (client_id)",
        "CREATE INDEX IF NOT EXISTS ix_direct_campaign_daily_stats_stat_date ON direct_campaign_daily_stats (stat_date)",
        "CREATE INDEX IF NOT EXISTS ix_direct_campaign_daily_stats_campaign_id ON direct_campaign_daily_stats (campaign_id)",
        """
        CREATE TABLE IF NOT EXISTS optimization_action_drafts (
            id VARCHAR(36) PRIMARY KEY,
            organization_id VARCHAR(36),
            client_id VARCHAR(64) NOT NULL,
            source VARCHAR(64) NOT NULL DEFAULT 'rule_based',
            status VARCHAR(32) NOT NULL DEFAULT 'draft',
            severity VARCHAR(32),
            category VARCHAR(64),
            campaign_name VARCHAR(255),
            issue TEXT NOT NULL,
            evidence TEXT,
            draft_action TEXT NOT NULL,
            action_type VARCHAR(64),
            requires_approval BOOLEAN NOT NULL DEFAULT TRUE,
            can_apply_automatically BOOLEAN NOT NULL DEFAULT FALSE,
            safety_note TEXT,
            user_comment TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            reviewed_at TIMESTAMPTZ,
            approved_at TIMESTAMPTZ,
            rejected_at TIMESTAMPTZ
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_optimization_action_drafts_organization_id ON optimization_action_drafts (organization_id)",
        "CREATE INDEX IF NOT EXISTS ix_optimization_action_drafts_client_id ON optimization_action_drafts (client_id)",
        """
        CREATE TABLE IF NOT EXISTS optimization_action_events (
            id VARCHAR(36) PRIMARY KEY,
            action_id VARCHAR(36) NOT NULL,
            organization_id VARCHAR(36),
            client_id VARCHAR(64) NOT NULL,
            event_type VARCHAR(64) NOT NULL,
            from_status VARCHAR(32),
            to_status VARCHAR(32),
            comment TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_optimization_action_events_action_id ON optimization_action_events (action_id)",
        "CREATE INDEX IF NOT EXISTS ix_optimization_action_events_organization_id ON optimization_action_events (organization_id)",
        "CREATE INDEX IF NOT EXISTS ix_optimization_action_events_client_id ON optimization_action_events (client_id)",
        """
        CREATE TABLE IF NOT EXISTS client_business_contexts (
            id VARCHAR(36) PRIMARY KEY,
            client_id VARCHAR(64) NOT NULL UNIQUE,
            brand_name TEXT,
            business_niche TEXT,
            product_summary TEXT,
            target_audience TEXT,
            geography TEXT,
            seasonality TEXT,
            main_offers TEXT,
            conversion_actions TEXT,
            average_order_value TEXT,
            lead_value_notes TEXT,
            business_constraints TEXT,
            negative_topics TEXT,
            landing_page_notes TEXT,
            competitor_notes TEXT,
            ai_summary TEXT,
            manual_notes TEXT,
            memory_notes TEXT,
            source_notes TEXT,
            last_ai_update_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_client_business_contexts_client_id ON client_business_contexts (client_id)",
    ]
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def get_db() -> Generator[Session, None, None]:
    if SessionLocal is None:
        raise RuntimeError("DATABASE_URL is not configured")
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_optional_db() -> Generator[Session | None, None, None]:
    if SessionLocal is None:
        yield None
        return
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
