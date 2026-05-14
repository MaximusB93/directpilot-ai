from pydantic import BaseModel, Field


class ClientSummary(BaseModel):
    id: str
    name: str
    segment: str
    spend: str
    leads: int
    cpa: str
    roas: str
    trend: str
    score: int = Field(ge=0, le=100)
    status: str


class AgencyMetric(BaseModel):
    label: str
    value: str
    delta: str


class Campaign(BaseModel):
    name: str
    spend: str
    leads: int
    cpa: str
    status: str


class AuditIssue(BaseModel):
    priority: str
    title: str
    object: str
    evidence: str
    action: str


class AffectedItem(BaseModel):
    type: str
    name: str
    campaign: str
    spend: str
    conversions: int
    action: str


class RecommendationDiff(BaseModel):
    before: str
    after: str


class Recommendation(BaseModel):
    id: str
    risk: str
    impact: str
    title: str
    reason: str
    objects: str
    mode: str
    status: str
    evidence: list[str]
    affected_items: list[AffectedItem]
    diff: RecommendationDiff


class PlannedChange(BaseModel):
    object_type: str
    object_name: str
    campaign: str
    before: str
    after: str
    action: str


class ChangePreview(BaseModel):
    id: str
    recommendation_id: str
    client_id: str
    risk: str
    requires_approval: bool
    summary: str
    changes: list[PlannedChange]


class ApprovalCreateRequest(BaseModel):
    preview_id: str
    requested_by: str = "ppc-specialist"


class ApprovalDecisionRequest(BaseModel):
    decided_by: str = "ppc-lead"
    comment: str | None = None


class ApprovalRecord(BaseModel):
    id: str
    preview_id: str
    recommendation_id: str
    client_id: str
    requested_by: str
    status: str
    created_at: str
    decided_by: str | None = None
    decided_at: str | None = None
    comment: str | None = None


class AuditLogEvent(BaseModel):
    id: str
    type: str
    actor: str
    description: str
    created_at: str
    entity_id: str | None = None


class IntegrationStatus(BaseModel):
    id: str
    name: str
    status: str
    description: str
    next_action: str


class YandexAuthStartResponse(BaseModel):
    configured: bool
    auth_url: str | None = None
    state: str
    message: str




class YandexTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int | None = None
    refresh_token: str | None = None
    scope: str | None = None


class YandexUserInfo(BaseModel):
    id: str | None = None
    login: str | None = None
    client_id: str | None = None
    display_name: str | None = None
    real_name: str | None = None
    default_email: str | None = None


class ConnectedYandexAccount(BaseModel):
    id: str
    provider: str = "yandex"
    status: str
    login: str | None = None
    display_name: str | None = None
    external_user_id: str | None = None
    scope: str | None = None
    connected_at: str
    updated_at: str
    token_expires_at: str | None = None


class YandexConnectionStatus(BaseModel):
    configured: bool
    database_configured: bool
    token_storage_configured: bool
    connected: bool
    accounts: list[ConnectedYandexAccount]
    message: str


class YandexAuthCallbackResponse(BaseModel):
    status: str
    code_received: bool
    state: str | None = None
    message: str
    account: ConnectedYandexAccount | None = None


class HealthResponse(BaseModel):
    status: str
    service: str
    environment: str


class YandexDirectConnectionCheck(BaseModel):
    configured: bool
    can_call_api: bool
    message: str


class YandexDirectCampaign(BaseModel):
    id: str
    name: str
    status: str
    state: str | None = None
    type: str | None = None


class YandexCampaignReportRow(BaseModel):
    campaign_id: str
    campaign_name: str
    impressions: int
    clicks: int
    cost: float
    ctr: float
    avg_cpc: float
    conversions: float
    cost_per_conversion: float | None = None
    conversion_rate: float | None = None


class EmailCodeRequest(BaseModel):
    email: str


class EmailCodeRequestResponse(BaseModel):
    status: str
    message: str
    expires_in_seconds: int
    dev_code: str | None = None


class EmailCodeVerifyRequest(BaseModel):
    email: str
    code: str


class EmailCodeVerifyResponse(BaseModel):
    authenticated: bool
    email: str
    session_token: str
    expires_at: str
