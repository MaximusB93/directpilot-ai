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


class ClientCreateRequest(BaseModel):
    id: str | None = None
    name: str = Field(min_length=1, max_length=255)
    direct_login: str | None = None
    metrica_counter: str | None = None
    yandex_account_id: str | None = None
    target_cpa: int | None = None
    main_goal_id: str | None = None
    conversion_goal_ids: str | None = None
    notes: str | None = None
    segment: str = "Клиент"


class ClientAccountResponse(BaseModel):
    id: str
    name: str
    segment: str
    spend: str = "—"
    leads: int = 0
    cpa: str = "—"
    roas: str = "—"
    trend: str = "Ожидает синхронизации"
    score: int = 0
    status: str
    directLogin: str = "Не подключен"
    metricaCounter: str = "Не подключен"
    yandexAccountId: str | None = None
    targetCpa: int | None = None
    mainGoalId: str | None = None
    conversionGoalIds: str | None = None
    notes: str | None = None
    syncStatus: str = "never_synced"
    syncError: str | None = None
    lastSyncedAt: str | None = None
    syncVersion: int = 0


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
    policy_violations: list[str] = Field(default_factory=list)
    risk_score: int = Field(default=0, ge=0, le=100)


class ApprovalCreateRequest(BaseModel):
    preview_id: str
    requested_by: str = "ppc-specialist"
    requested_by_role: str = "specialist"


class ApprovalDecisionRequest(BaseModel):
    decided_by: str = "ppc-lead"
    decided_by_role: str = "lead"
    comment: str | None = None


class ApprovalRecord(BaseModel):
    id: str
    preview_id: str
    recommendation_id: str
    client_id: str
    requested_by: str
    requested_by_role: str = "specialist"
    status: str
    created_at: str
    policy_violations: list[str] = Field(default_factory=list)
    risk_score: int = Field(default=0, ge=0, le=100)
    decided_by: str | None = None
    decided_at: str | None = None
    comment: str | None = None




class RecommendationImpactCreateRequest(BaseModel):
    recommendation_id: str
    client_id: str
    expected_impact: str
    observed_impact: str
    window_days: int = Field(default=7, ge=1, le=90)
    created_by: str = "ppc-specialist"

class RecommendationImpactEvent(BaseModel):
    id: str
    recommendation_id: str
    client_id: str
    expected_impact: str
    observed_impact: str
    window_days: int
    created_by: str
    created_at: str


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


class ClientYandexBindingRequest(BaseModel):
    yandex_account_id: str


class ClientYandexBindingStatus(BaseModel):
    status: str
    client_id: str
    yandex_account_id: str | None = None


class ClientYandexIntegrationStatus(BaseModel):
    client_id: str
    connected: bool
    bound_account: ConnectedYandexAccount | None = None
    available_accounts: list[ConnectedYandexAccount]
    message: str


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


class AuthMeResponse(BaseModel):
    authenticated: bool
    email: str
    organization_id: str
    user_id: str


class AiModelOption(BaseModel):
    id: str
    name: str
    description: str
    label: str | None = None
    provider: str | None = None
    cost_tier: str = "unknown"
    recommended_for: list[str] = Field(default_factory=list)


class AiModelPreset(BaseModel):
    id: str
    label: str
    purpose: str
    default_model: str
    max_tokens: int
    cost_tier: str
    warning: str | None = None


class AiStatusResponse(BaseModel):
    configured: bool
    default_model: str
    models: list[AiModelOption]
    presets: list[AiModelPreset] = Field(default_factory=list)
    recommended_default_preset: str = "economy"
    recommended_default_model: str | None = None
    allow_custom_models: bool
    message: str


class AiPromptRequest(BaseModel):
    model: str | None = None
    ai_preset: str | None = None
    max_tokens: int | None = Field(default=None, ge=1, le=5000)
    prompt: str = Field(min_length=10, max_length=4000)


class AiClientRecommendationRequest(BaseModel):
    model: str | None = None
    ai_preset: str | None = None
    max_tokens: int | None = Field(default=None, ge=1, le=5000)
    client_context: dict | None = None


class AiGeneratedRecommendation(BaseModel):
    title: str
    evidence: list[str]
    risk: str
    expected_impact: str
    next_step: str
    requires_approval: bool


class AiRecommendationResponse(BaseModel):
    client_id: str
    source: str
    model: str | None = None
    summary: str
    recommendations: list[AiGeneratedRecommendation]
    raw_response: str | None = None
    error: bool = False
    error_code: str | None = None
    message: str | None = None
    retryable: bool = False
    suggested_preset: str | None = None


class AiChatMessage(BaseModel):
    role: str
    content: str = Field(min_length=1, max_length=4000)


class AiChatRequest(BaseModel):
    client_id: str = "furniture"
    model: str | None = None
    ai_preset: str | None = None
    max_tokens: int | None = Field(default=None, ge=1, le=5000)
    message: str = Field(min_length=2, max_length=4000)
    history: list[AiChatMessage] = Field(default_factory=list)
    client_context: dict | None = None
    selected_campaign_name: str | None = None


class AiToolTrace(BaseModel):
    name: str
    arguments: dict
    result: object


class AiChatResponse(BaseModel):
    client_id: str
    model: str | None = None
    source: str
    answer: str
    tool_traces: list[AiToolTrace]
    error: bool = False
    error_code: str | None = None
    message: str | None = None
    retryable: bool = False
    suggested_preset: str | None = None


class AiPromptResponse(BaseModel):
    model: str
    content: str = ""
    usage: dict | None = None
    id: str | None = None
    error: bool = False
    error_code: str | None = None
    message: str | None = None
    retryable: bool = False
    suggested_preset: str | None = None


class SyncJobResponse(BaseModel):
    id: str
    client_id: str
    source_type: str
    status: str
    period_from: str | None = None
    period_to: str | None = None
    rows_loaded: int
    error: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    created_at: str


class ClientPerformanceSummaryResponse(BaseModel):
    client: dict
    period: dict | None = None
    totals: dict
    campaigns: list[dict]
    message: str
    selectedGoalId: str | None = None
    selectedGoalIds: list[str] = Field(default_factory=list)
    hasGoalData: bool = False
    goalConversionsTotal: float = 0.0
    totalConversionsFallback: float = 0.0
    conversionsSourceMessage: str | None = None
    goalDataWarnings: list[str] = Field(default_factory=list)


class OptimizationActionDraft(BaseModel):
    id: str
    severity: str
    category: str
    campaign_name: str | None = None
    issue: str
    evidence: str
    draft_action: str
    action_type: str = "manual_review"
    requires_approval: bool = True
    can_apply_automatically: bool = False
    safety_note: str


class OptimizationPlanResponse(BaseModel):
    client_id: str
    selected_goal_id: str | None = None
    has_data: bool
    has_goal_data: bool
    summary: str
    actions: list[OptimizationActionDraft]


class OptimizationActionDraftCreate(BaseModel):
    source: str = "manual"
    severity: str | None = None
    category: str | None = None
    campaign_name: str | None = None
    issue: str = Field(min_length=1)
    evidence: str | None = None
    draft_action: str = Field(min_length=1)
    action_type: str | None = "manual_review"
    requires_approval: bool = True
    can_apply_automatically: bool = False
    safety_note: str | None = None
    user_comment: str | None = None


class OptimizationActionDraftUpdateStatus(BaseModel):
    status: str | None = None
    user_comment: str | None = None


class OptimizationActionEventResponse(BaseModel):
    id: str
    actionId: str
    organizationId: str | None = None
    clientId: str
    eventType: str
    fromStatus: str | None = None
    toStatus: str | None = None
    comment: str | None = None
    createdAt: str


class OptimizationActionDraftResponse(BaseModel):
    id: str
    organizationId: str | None = None
    clientId: str
    source: str
    status: str
    severity: str | None = None
    category: str | None = None
    campaignName: str | None = None
    issue: str
    evidence: str | None = None
    draftAction: str
    actionType: str | None = None
    requiresApproval: bool
    canApplyAutomatically: bool
    safetyNote: str | None = None
    userComment: str | None = None
    createdAt: str
    updatedAt: str | None = None
    reviewedAt: str | None = None
    approvedAt: str | None = None
    rejectedAt: str | None = None


class OptimizationActionDraftListResponse(BaseModel):
    actions: list[OptimizationActionDraftResponse]


class OptimizationActionExecutionPreviewResponse(BaseModel):
    action_id: str
    client_id: str
    status: str
    can_preview: bool
    can_apply: bool = False
    apply_enabled: bool = False
    action_type: str | None = None
    campaign_name: str | None = None
    summary: str
    would_do: list[str] = Field(default_factory=list)
    required_data: list[str] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)
    safety_checks: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    next_step: str
