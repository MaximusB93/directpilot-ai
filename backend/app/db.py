from collections.abc import Generator
import logging

from sqlalchemy import create_engine, text
from sqlalchemy.exc import ArgumentError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

logger = logging.getLogger(__name__)


def _normalize_database_url(url: str) -> str:
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


class Base(DeclarativeBase):
    pass


def _safe_database_error(exc: Exception) -> str:
    message = f"{type(exc).__name__}: {exc}"
    if settings.database_url:
        message = message.replace(settings.database_url, "[DATABASE_URL]")
    return message


database_engine_error: str | None = None
try:
    engine = create_engine(_normalize_database_url(settings.database_url), pool_pre_ping=True) if settings.database_url else None
except (ArgumentError, ValueError) as exc:
    database_engine_error = _safe_database_error(exc)
    logger.exception("DATABASE_URL is configured but SQLAlchemy could not create an engine.")
    engine = None
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False) if engine else None

AI_AUDIT_JOB_SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS ai_audit_jobs (
        id VARCHAR(36) PRIMARY KEY,
        organization_id VARCHAR(36) NOT NULL,
        client_id VARCHAR(64) NOT NULL,
        created_by_user_id VARCHAR(36),
        created_by_email VARCHAR(255),
        status VARCHAR(32) NOT NULL DEFAULT 'queued',
        current_stage VARCHAR(32) NOT NULL DEFAULT 'collect_context',
        progress_percent INTEGER NOT NULL DEFAULT 0,
        requested_scope VARCHAR(64) NOT NULL DEFAULT 'full_account',
        requested_period VARCHAR(64) NOT NULL DEFAULT 'last_30_days',
        selected_campaign_name VARCHAR(255),
        model VARCHAR(255) NOT NULL,
        returned_model VARCHAR(255),
        ai_preset VARCHAR(32) NOT NULL DEFAULT 'balanced',
        max_tokens INTEGER NOT NULL DEFAULT 2500,
        system_prompt_version VARCHAR(64) NOT NULL,
        system_prompt_hash VARCHAR(128) NOT NULL,
        input_options_json TEXT NOT NULL DEFAULT '{}',
        context_snapshot_json TEXT,
        prompt_snapshot_json TEXT,
        result_json TEXT,
        answer_text TEXT,
        error_code VARCHAR(128),
        error_message TEXT,
        retryable BOOLEAN NOT NULL DEFAULT FALSE,
        timings_json TEXT NOT NULL DEFAULT '{}',
        stage_version INTEGER NOT NULL DEFAULT 0,
        stage_started_at TIMESTAMPTZ,
        stage_lease_expires_at TIMESTAMPTZ,
        stage_execution_token VARCHAR(36),
        stage_attempt INTEGER NOT NULL DEFAULT 0,
        cancel_requested BOOLEAN NOT NULL DEFAULT FALSE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        started_at TIMESTAMPTZ,
        completed_at TIMESTAMPTZ,
        expires_at TIMESTAMPTZ
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_ai_audit_jobs_organization_id ON ai_audit_jobs (organization_id)",
    "CREATE INDEX IF NOT EXISTS ix_ai_audit_jobs_client_id ON ai_audit_jobs (client_id)",
    "CREATE INDEX IF NOT EXISTS ix_ai_audit_jobs_status ON ai_audit_jobs (status)",
    "CREATE INDEX IF NOT EXISTS ix_ai_audit_jobs_expires_at ON ai_audit_jobs (expires_at)",
    "ALTER TABLE ai_audit_jobs ADD COLUMN IF NOT EXISTS stage_started_at TIMESTAMPTZ",
    "ALTER TABLE ai_audit_jobs ADD COLUMN IF NOT EXISTS stage_lease_expires_at TIMESTAMPTZ",
    "ALTER TABLE ai_audit_jobs ADD COLUMN IF NOT EXISTS stage_execution_token VARCHAR(36)",
    "ALTER TABLE ai_audit_jobs ADD COLUMN IF NOT EXISTS stage_attempt INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE ai_audit_jobs ADD COLUMN IF NOT EXISTS cancel_requested BOOLEAN NOT NULL DEFAULT FALSE",
    """
    CREATE TABLE IF NOT EXISTS ai_audit_evidence_results (
        id VARCHAR(36) PRIMARY KEY,
        audit_job_id VARCHAR(36) NOT NULL,
        organization_id VARCHAR(36) NOT NULL,
        client_id VARCHAR(64) NOT NULL,
        evidence_kind VARCHAR(32) NOT NULL,
        request_id VARCHAR(128) NOT NULL,
        hypothesis_id VARCHAR(128),
        capability_id VARCHAR(64),
        status VARCHAR(32) NOT NULL,
        result_json TEXT NOT NULL DEFAULT '{}',
        rows_count INTEGER NOT NULL DEFAULT 0,
        fetched_at TIMESTAMPTZ,
        expires_at TIMESTAMPTZ NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT uq_ai_audit_evidence_request UNIQUE (audit_job_id, evidence_kind, request_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_ai_audit_evidence_job_id ON ai_audit_evidence_results (audit_job_id)",
    "CREATE INDEX IF NOT EXISTS ix_ai_audit_evidence_organization_id ON ai_audit_evidence_results (organization_id)",
    "CREATE INDEX IF NOT EXISTS ix_ai_audit_evidence_client_id ON ai_audit_evidence_results (client_id)",
    "CREATE INDEX IF NOT EXISTS ix_ai_audit_evidence_kind ON ai_audit_evidence_results (evidence_kind)",
    "CREATE INDEX IF NOT EXISTS ix_ai_audit_evidence_expires_at ON ai_audit_evidence_results (expires_at)",
)

DIRECT_READ_SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS direct_read_cache (
        id VARCHAR(36) PRIMARY KEY,
        client_id VARCHAR(64) NOT NULL,
        request_hash VARCHAR(64) NOT NULL,
        capability_id VARCHAR(64) NOT NULL,
        source VARCHAR(64) NOT NULL,
        original_status VARCHAR(32) NOT NULL DEFAULT 'collected',
        error_code VARCHAR(128),
        capability_schema_version VARCHAR(32) NOT NULL DEFAULT 'v1',
        direct_api_knowledge_version VARCHAR(32) NOT NULL DEFAULT 'v1',
        normalization_version VARCHAR(32) NOT NULL DEFAULT 'v1',
        source_type VARCHAR(32),
        report_type VARCHAR(128),
        service VARCHAR(64),
        api_fields_hash VARCHAR(64),
        result_json TEXT NOT NULL DEFAULT '[]',
        period_json TEXT NOT NULL DEFAULT '{}',
        rows_count INTEGER NOT NULL DEFAULT 0,
        partial BOOLEAN NOT NULL DEFAULT FALSE,
        warnings_json TEXT NOT NULL DEFAULT '[]',
        fetched_at TIMESTAMPTZ NOT NULL,
        expires_at TIMESTAMPTZ NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT uq_direct_read_cache_client_request UNIQUE (client_id, request_hash)
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_direct_read_cache_client_id ON direct_read_cache (client_id)",
    "CREATE INDEX IF NOT EXISTS ix_direct_read_cache_request_hash ON direct_read_cache (request_hash)",
    "CREATE INDEX IF NOT EXISTS ix_direct_read_cache_capability_id ON direct_read_cache (capability_id)",
    "CREATE INDEX IF NOT EXISTS ix_direct_read_cache_expires_at ON direct_read_cache (expires_at)",
    "ALTER TABLE direct_read_cache ADD COLUMN IF NOT EXISTS original_status VARCHAR(32) NOT NULL DEFAULT 'collected'",
    "ALTER TABLE direct_read_cache ADD COLUMN IF NOT EXISTS error_code VARCHAR(128)",
    "ALTER TABLE direct_read_cache ADD COLUMN IF NOT EXISTS capability_schema_version VARCHAR(32) NOT NULL DEFAULT 'v1'",
    "ALTER TABLE direct_read_cache ADD COLUMN IF NOT EXISTS direct_api_knowledge_version VARCHAR(32) NOT NULL DEFAULT 'v1'",
    "ALTER TABLE direct_read_cache ADD COLUMN IF NOT EXISTS normalization_version VARCHAR(32) NOT NULL DEFAULT 'v1'",
    "ALTER TABLE direct_read_cache ADD COLUMN IF NOT EXISTS source_type VARCHAR(32)",
    "ALTER TABLE direct_read_cache ADD COLUMN IF NOT EXISTS report_type VARCHAR(128)",
    "ALTER TABLE direct_read_cache ADD COLUMN IF NOT EXISTS service VARCHAR(64)",
    "ALTER TABLE direct_read_cache ADD COLUMN IF NOT EXISTS api_fields_hash VARCHAR(64)",
    """
    CREATE TABLE IF NOT EXISTS direct_report_jobs (
        id VARCHAR(36) PRIMARY KEY,
        audit_job_id VARCHAR(36),
        client_id VARCHAR(64) NOT NULL,
        capability_id VARCHAR(64) NOT NULL,
        request_hash VARCHAR(64) NOT NULL,
        report_name VARCHAR(255) NOT NULL,
        report_spec_json TEXT NOT NULL,
        status VARCHAR(32) NOT NULL DEFAULT 'queued',
        retry_after_seconds INTEGER NOT NULL DEFAULT 1,
        attempts INTEGER NOT NULL DEFAULT 0,
        queue_full_attempts INTEGER NOT NULL DEFAULT 0,
        first_queue_full_at TIMESTAMPTZ,
        last_queue_full_at TIMESTAMPTZ,
        rows_count INTEGER NOT NULL DEFAULT 0,
        next_offset INTEGER NOT NULL DEFAULT 0,
        rows_collected INTEGER NOT NULL DEFAULT 0,
        limited_by INTEGER,
        pages_completed INTEGER NOT NULL DEFAULT 0,
        partial BOOLEAN NOT NULL DEFAULT FALSE,
        row_limit_reached BOOLEAN NOT NULL DEFAULT FALSE,
        result_snapshot_json TEXT,
        error_code VARCHAR(128),
        error_message TEXT,
        next_retry_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        completed_at TIMESTAMPTZ,
        expires_at TIMESTAMPTZ,
        CONSTRAINT uq_direct_report_jobs_client_request UNIQUE (client_id, request_hash)
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_direct_report_jobs_audit_job_id ON direct_report_jobs (audit_job_id)",
    "CREATE INDEX IF NOT EXISTS ix_direct_report_jobs_client_id ON direct_report_jobs (client_id)",
    "CREATE INDEX IF NOT EXISTS ix_direct_report_jobs_request_hash ON direct_report_jobs (request_hash)",
    "CREATE INDEX IF NOT EXISTS ix_direct_report_jobs_capability_id ON direct_report_jobs (capability_id)",
    "CREATE INDEX IF NOT EXISTS ix_direct_report_jobs_status ON direct_report_jobs (status)",
    "CREATE INDEX IF NOT EXISTS ix_direct_report_jobs_next_retry_at ON direct_report_jobs (next_retry_at)",
    "CREATE INDEX IF NOT EXISTS ix_direct_report_jobs_expires_at ON direct_report_jobs (expires_at)",
    "ALTER TABLE direct_report_jobs ADD COLUMN IF NOT EXISTS next_offset INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE direct_report_jobs ADD COLUMN IF NOT EXISTS rows_collected INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE direct_report_jobs ADD COLUMN IF NOT EXISTS limited_by INTEGER",
    "ALTER TABLE direct_report_jobs ADD COLUMN IF NOT EXISTS pages_completed INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE direct_report_jobs ADD COLUMN IF NOT EXISTS partial BOOLEAN NOT NULL DEFAULT FALSE",
    "ALTER TABLE direct_report_jobs ADD COLUMN IF NOT EXISTS row_limit_reached BOOLEAN NOT NULL DEFAULT FALSE",
    "ALTER TABLE direct_report_jobs ADD COLUMN IF NOT EXISTS queue_full_attempts INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE direct_report_jobs ADD COLUMN IF NOT EXISTS first_queue_full_at TIMESTAMPTZ",
    "ALTER TABLE direct_report_jobs ADD COLUMN IF NOT EXISTS last_queue_full_at TIMESTAMPTZ",
)


def check_db_connection() -> None:
    if database_engine_error:
        raise RuntimeError(database_engine_error)
    if engine is None:
        return
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))


def init_db(*, run_schema_patch: bool = True) -> None:
    if database_engine_error:
        raise RuntimeError(database_engine_error)
    if engine is None:
        return
    if not run_schema_patch:
        check_db_connection()
        ensure_ai_audit_job_schema()
        ensure_direct_read_schema()
        return
    import app.models  # noqa: F401
    import app.models_wordstat  # noqa: F401
    import app.models_workflow  # noqa: F401

    Base.metadata.create_all(bind=engine)
    ensure_mvp_schema()
    ensure_direct_read_schema()


def ensure_ai_audit_job_schema() -> None:
    if engine is None:
        return
    with engine.begin() as connection:
        for statement in AI_AUDIT_JOB_SCHEMA_STATEMENTS:
            connection.execute(text(statement))


def ensure_direct_read_schema() -> None:
    if engine is None:
        return
    with engine.begin() as connection:
        for statement in DIRECT_READ_SCHEMA_STATEMENTS:
            connection.execute(text(statement))


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
        *AI_AUDIT_JOB_SCHEMA_STATEMENTS,
        """
        CREATE TABLE IF NOT EXISTS wordstat_query_batches (
            id VARCHAR(36) PRIMARY KEY,
            organization_id VARCHAR(36),
            client_id VARCHAR(64),
            period VARCHAR(32) NOT NULL,
            from_date DATE NOT NULL,
            to_date DATE NOT NULL,
            regions_hash VARCHAR(64) NOT NULL,
            devices_hash VARCHAR(64) NOT NULL,
            regions_json TEXT,
            devices_json TEXT,
            status VARCHAR(32) NOT NULL DEFAULT 'created',
            total_phrases INTEGER NOT NULL DEFAULT 0,
            completed_phrases INTEGER NOT NULL DEFAULT 0,
            failed_phrases INTEGER NOT NULL DEFAULT 0,
            error_message TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_wordstat_query_batches_organization_id ON wordstat_query_batches (organization_id)",
        "CREATE INDEX IF NOT EXISTS ix_wordstat_query_batches_client_id ON wordstat_query_batches (client_id)",
        """
        CREATE TABLE IF NOT EXISTS wordstat_query_items (
            id VARCHAR(36) PRIMARY KEY,
            batch_id VARCHAR(36) NOT NULL,
            phrase TEXT NOT NULL,
            phrase_normalized TEXT NOT NULL,
            status VARCHAR(32) NOT NULL DEFAULT 'created',
            points_loaded INTEGER NOT NULL DEFAULT 0,
            error_message TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_wordstat_query_items_batch_id ON wordstat_query_items (batch_id)",
        """
        CREATE TABLE IF NOT EXISTS wordstat_dynamics (
            id VARCHAR(36) PRIMARY KEY,
            phrase_original TEXT NOT NULL,
            phrase_normalized TEXT NOT NULL,
            period VARCHAR(32) NOT NULL,
            stat_date DATE NOT NULL,
            count INTEGER NOT NULL DEFAULT 0,
            share FLOAT,
            regions_hash VARCHAR(64) NOT NULL,
            devices_hash VARCHAR(64) NOT NULL,
            regions_json TEXT,
            devices_json TEXT,
            loaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_wordstat_dynamics_cache_key UNIQUE (phrase_normalized, period, stat_date, regions_hash, devices_hash)
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_wordstat_dynamics_phrase_normalized ON wordstat_dynamics (phrase_normalized)",
        "CREATE INDEX IF NOT EXISTS ix_wordstat_dynamics_period ON wordstat_dynamics (period)",
        "CREATE INDEX IF NOT EXISTS ix_wordstat_dynamics_stat_date ON wordstat_dynamics (stat_date)",
        "CREATE INDEX IF NOT EXISTS ix_wordstat_dynamics_regions_hash ON wordstat_dynamics (regions_hash)",
        "CREATE INDEX IF NOT EXISTS ix_wordstat_dynamics_devices_hash ON wordstat_dynamics (devices_hash)",
        """
        CREATE TABLE IF NOT EXISTS wordstat_request_log (
            id VARCHAR(36) PRIMARY KEY,
            provider VARCHAR(64) NOT NULL DEFAULT 'yandex_search_api',
            method VARCHAR(64) NOT NULL DEFAULT 'dynamics',
            phrase TEXT,
            request_hash VARCHAR(64) NOT NULL,
            http_status INTEGER,
            status VARCHAR(32) NOT NULL DEFAULT 'started',
            error_message TEXT,
            started_at TIMESTAMPTZ NOT NULL,
            finished_at TIMESTAMPTZ
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_wordstat_request_log_request_hash ON wordstat_request_log (request_hash)",
    ]
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def get_db() -> Generator[Session, None, None]:
    if SessionLocal is None:
        raise RuntimeError(database_engine_error or "DATABASE_URL is not configured")
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
