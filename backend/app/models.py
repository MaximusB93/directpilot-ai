from datetime import date, datetime
from uuid import uuid4

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _uuid() -> str:
    return str(uuid4())


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="DirectPilot AI")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    users: Mapped[list["User"]] = relationship(back_populates="organization")
    accounts: Mapped[list["ConnectedAccount"]] = relationship(back_populates="organization")
    clients: Mapped[list["ClientAccount"]] = relationship(back_populates="organization")


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    external_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False, default="yandex")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    organization: Mapped[Organization] = relationship(back_populates="users")


class ClientAccount(Base):
    __tablename__ = "client_accounts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[str | None] = mapped_column(ForeignKey("organizations.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    segment: Mapped[str] = mapped_column(String(128), nullable=False, default="Клиент")
    direct_login: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metrica_counter: Mapped[str | None] = mapped_column(String(255), nullable=True)
    yandex_account_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    target_cpa: Mapped[int | None] = mapped_column(Integer, nullable=True)
    main_goal_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    conversion_goal_ids: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(128), nullable=False, default="Ожидает подключения данных")
    sync_status: Mapped[str] = mapped_column(String(64), nullable=False, default="never_synced")
    sync_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sync_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    organization: Mapped[Organization | None] = relationship(back_populates="clients")


class ClientBusinessContext(Base):
    __tablename__ = "client_business_contexts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    client_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    brand_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    business_niche: Mapped[str | None] = mapped_column(Text, nullable=True)
    product_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_audience: Mapped[str | None] = mapped_column(Text, nullable=True)
    geography: Mapped[str | None] = mapped_column(Text, nullable=True)
    seasonality: Mapped[str | None] = mapped_column(Text, nullable=True)
    main_offers: Mapped[str | None] = mapped_column(Text, nullable=True)
    conversion_actions: Mapped[str | None] = mapped_column(Text, nullable=True)
    average_order_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    lead_value_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    business_constraints: Mapped[str | None] = mapped_column(Text, nullable=True)
    negative_topics: Mapped[str | None] = mapped_column(Text, nullable=True)
    landing_page_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    competitor_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    manual_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    memory_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_ai_update_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ConnectedAccount(Base):
    __tablename__ = "connected_accounts"
    __table_args__ = (UniqueConstraint("provider", "external_user_id", name="uq_connected_accounts_provider_user"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False, default="yandex")
    external_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    login: Mapped[str | None] = mapped_column(String(255), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="connected")
    scope: Mapped[str | None] = mapped_column(Text, nullable=True)
    connected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    organization: Mapped[Organization] = relationship(back_populates="accounts")
    tokens: Mapped[list["OAuthToken"]] = relationship(back_populates="account", cascade="all, delete-orphan")


class OAuthToken(Base):
    __tablename__ = "oauth_tokens"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    account_id: Mapped[str] = mapped_column(ForeignKey("connected_accounts.id"), nullable=False)
    token_type: Mapped[str] = mapped_column(String(64), nullable=False, default="bearer")
    access_token_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    scope: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    account: Mapped[ConnectedAccount] = relationship(back_populates="tokens")


class EmailAuthCode(Base):
    __tablename__ = "email_auth_codes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    code_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(default=0, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class SyncJob(Base):
    __tablename__ = "sync_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    client_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False, default="yandex_direct")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    period_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    period_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rows_loaded: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class DirectCampaignPeriodStat(Base):
    __tablename__ = "direct_campaign_period_stats"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    client_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    campaign_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    campaign_name: Mapped[str] = mapped_column(String(255), nullable=False)
    period_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_to: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    impressions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    clicks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost: Mapped[float] = mapped_column(nullable=False, default=0.0)
    ctr: Mapped[float] = mapped_column(nullable=False, default=0.0)
    avg_cpc: Mapped[float] = mapped_column(nullable=False, default=0.0)
    conversions: Mapped[float] = mapped_column(nullable=False, default=0.0)
    cost_per_conversion: Mapped[float | None] = mapped_column(nullable=True)
    conversion_rate: Mapped[float | None] = mapped_column(nullable=True)
    goal_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    goal_conversions: Mapped[float | None] = mapped_column(nullable=True)
    goal_revenue: Mapped[float | None] = mapped_column(nullable=True)
    goal_cpa: Mapped[float | None] = mapped_column(nullable=True)
    conversion_source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    goal_ids: Mapped[str | None] = mapped_column(Text, nullable=True)
    conversion_warning: Mapped[str | None] = mapped_column(Text, nullable=True)
    loaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class DirectSearchQueryPeriodStat(Base):
    __tablename__ = "direct_search_query_period_stats"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    client_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    campaign_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    campaign_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ad_group_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    ad_group_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    period_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_to: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    impressions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    clicks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost: Mapped[float] = mapped_column(nullable=False, default=0.0)
    ctr: Mapped[float] = mapped_column(nullable=False, default=0.0)
    avg_cpc: Mapped[float] = mapped_column(nullable=False, default=0.0)
    conversions: Mapped[float] = mapped_column(nullable=False, default=0.0)
    goal_ids: Mapped[str | None] = mapped_column(Text, nullable=True)
    goal_conversions: Mapped[float | None] = mapped_column(nullable=True)
    goal_cpa: Mapped[float | None] = mapped_column(nullable=True)
    conversion_source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    issue_flags: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommended_negative_keyword: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommendation_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    loaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class DirectCampaignDailyStat(Base):
    __tablename__ = "direct_campaign_daily_stats"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    client_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    stat_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    campaign_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    campaign_name: Mapped[str] = mapped_column(String(255), nullable=False)
    impressions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    clicks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost: Mapped[float] = mapped_column(nullable=False, default=0.0)
    ctr: Mapped[float] = mapped_column(nullable=False, default=0.0)
    avg_cpc: Mapped[float] = mapped_column(nullable=False, default=0.0)
    goal_ids: Mapped[str | None] = mapped_column(Text, nullable=True)
    goal_conversions: Mapped[float | None] = mapped_column(nullable=True)
    goal_cpa: Mapped[float | None] = mapped_column(nullable=True)
    conversion_rate: Mapped[float | None] = mapped_column(nullable=True)
    issue_flags: Mapped[str | None] = mapped_column(Text, nullable=True)
    loaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class OptimizationActionDraft(Base):
    __tablename__ = "optimization_action_drafts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    client_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="rule_based")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    severity: Mapped[str | None] = mapped_column(String(32), nullable=True)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    campaign_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    issue: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    draft_action: Mapped[str] = mapped_column(Text, nullable=False)
    action_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    requires_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    can_apply_automatically: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    safety_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OptimizationActionEvent(Base):
    __tablename__ = "optimization_action_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    action_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    client_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
