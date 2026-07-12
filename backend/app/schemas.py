from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


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


class ClientBusinessContextResponse(BaseModel):
    id: str
    clientId: str
    brandName: str | None = None
    businessNiche: str | None = None
    productSummary: str | None = None
    targetAudience: str | None = None
    geography: str | None = None
    seasonality: str | None = None
    mainOffers: str | None = None
    conversionActions: str | None = None
    averageOrderValue: str | None = None
    leadValueNotes: str | None = None
    businessConstraints: str | None = None
    negativeTopics: str | None = None
    landingPageNotes: str | None = None
    competitorNotes: str | None = None
    aiSummary: str | None = None
    manualNotes: str | None = None
    memoryNotes: str | None = None
    sourceNotes: str | None = None
    lastAiUpdateAt: str | None = None
    createdAt: str | None = None
    updatedAt: str | None = None


class ClientBusinessContextUpdate(BaseModel):
    brandName: str | None = None
    businessNiche: str | None = None
    productSummary: str | None = None
    targetAudience: str | None = None
    geography: str | None = None
    seasonality: str | None = None
    mainOffers: str | None = None
    conversionActions: str | None = None
    averageOrderValue: str | None = None
    leadValueNotes: str | None = None
    businessConstraints: str | None = None
    negativeTopics: str | None = None
    landingPageNotes: str | None = None
    competitorNotes: str | None = None
    aiSummary: str | None = None
    manualNotes: str | None = None
    memoryNotes: str | None = None
    sourceNotes: str | None = None


class ClientMemoryNoteCreate(BaseModel):
    note: str = Field(min_length=1, max_length=10000)


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
    database_configured: bool | None = None
    database_initialized: bool | None = None
    database_error: str | None = None


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
    inspect_request: bool = False


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


class AiStructuredFinding(BaseModel):
    type: str
    entityType: str = "unknown"
    entityId: str | None = None
    entityName: str | None = None
    metric: str | None = None
    problem: str
    evidence: str
    recommendation: str
    risk: str = "medium"


class AiStructuredAction(BaseModel):
    type: str
    entityType: str = "unknown"
    entityId: str | None = None
    description: str
    requiresHumanApproval: bool = True


class AiStructuredRecommendation(BaseModel):
    summary: str
    confidence: str = "medium"
    riskLevel: str = "medium"
    missingData: list[str] = Field(default_factory=list)
    findings: list[AiStructuredFinding] = Field(default_factory=list)
    actions: list[AiStructuredAction] = Field(default_factory=list)
    safetyNotes: list[str] = Field(default_factory=list)


class AiRecommendationResponse(BaseModel):
    client_id: str
    source: str
    model: str | None = None
    summary: str
    recommendations: list[AiGeneratedRecommendation]
    structured_output: AiStructuredRecommendation | None = None
    validation_warnings: list[str] = Field(default_factory=list)
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
    compact_context: bool = True
    tool_results_mode: str = "summary"
    chat_history_limit: int = Field(default=3, ge=0, le=8)
    search_query_limit: int | None = Field(default=20, ge=1, le=200)
    inspect_request: bool = False


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
    requestDebug: dict | None = None
    requestTrace: dict | None = None
    suggested_action: str | None = None


class AiAuditOptions(BaseModel):
    include_search_queries: bool = True
    include_dynamics: bool = True
    include_tracking: bool = True
    include_recommendations: bool = True


class AiAuditCreateRequest(BaseModel):
    client_id: str
    scope: str = "full_account"
    period: str = "last_30_days"
    selected_campaign_name: str | None = None
    model: str | None = None
    ai_preset: str | None = None
    max_tokens: int | None = Field(default=None, ge=1, le=10000)
    options: AiAuditOptions = Field(default_factory=AiAuditOptions)


class AiAuditAdvanceRequest(BaseModel):
    retry: bool = False
    compact_retry: bool = False


class AiAuditPeriod(BaseModel):
    date_from: str | None = None
    date_to: str | None = None
    days: int | None = None
    comparison_date_from: str | None = None
    comparison_date_to: str | None = None


class AiAuditCoverageItem(BaseModel):
    available: bool = False
    total: int | None = None
    analyzed: int = 0
    source: str | None = None
    period: dict | None = None
    reason: str | None = None
    limitations: list[str] = Field(default_factory=list)


class AiAuditMeta(BaseModel):
    period: AiAuditPeriod = Field(default_factory=AiAuditPeriod)
    data_coverage: dict[str, AiAuditCoverageItem] = Field(default_factory=dict)
    model: str | None = None
    output_budget_tokens: int = 10000


class AiAuditDataQuality(BaseModel):
    status: str = "partial"
    facts: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class AiAuditFinding(BaseModel):
    hypothesis_id: str | None = None
    verification_status: Literal["confirmed", "partially_confirmed", "rejected", "unverified", "not_applicable"] | None = None
    campaign_name: str | None = None
    campaign_type: str = "unknown"
    analysis_level: str = "campaign"
    problem: str
    fact: str
    evidence: list[str] = Field(default_factory=list, max_length=5)
    hypothesis: str | None = None
    confidence: str = "low"
    risk: str = "medium"
    recommendation: str
    requires_human_approval: bool = True
    next_data_needed: list[str] = Field(default_factory=list, max_length=5)


class AiAuditAction(BaseModel):
    priority: int
    hypothesis_id: str | None = None
    action: str
    scope: str
    reason: str
    mode: str = "manual_review"
    requires_human_approval: bool = True


class AiAuditDrilldownSummary(BaseModel):
    analyzed_levels: list[str] = Field(default_factory=list)
    not_analyzed_levels: list[str] = Field(default_factory=list)
    next_data_needed: list[str] = Field(default_factory=list)


class AiAuditResult(BaseModel):
    meta: AiAuditMeta = Field(default_factory=AiAuditMeta)
    executive_summary: str
    data_quality: AiAuditDataQuality = Field(default_factory=AiAuditDataQuality)
    critical_findings: list[AiAuditFinding] = Field(default_factory=list, max_length=5)
    opportunities: list[AiAuditFinding] = Field(default_factory=list, max_length=5)
    insufficient_data_campaigns: list[str] = Field(default_factory=list)
    tracking_and_goals: dict = Field(default_factory=dict)
    drilldown_summary: AiAuditDrilldownSummary = Field(default_factory=AiAuditDrilldownSummary)
    action_plan: list[AiAuditAction] = Field(default_factory=list, max_length=10)
    prohibited_actions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    conclusion: str


class AuditDataRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    hypothesis_id: str
    campaign_name: str
    campaign_family: Literal["search", "yan", "unknown"]
    campaign_subtype: Literal["search", "brand_search", "yan_prospecting", "yan_retargeting", "unknown"]
    dimension: Literal[
        "ad_groups", "keywords", "search_queries", "ads", "landing_pages", "placements",
        "audiences", "retargeting_segments", "audience_exclusions", "devices", "geo",
        "demographics", "frequency", "goals", "conversion_sources", "lead_quality",
    ]
    reason: str
    period: AiAuditPeriod = Field(default_factory=AiAuditPeriod)
    filters: dict = Field(default_factory=dict)
    metrics: list[str] = Field(default_factory=list)
    priority: Literal["low", "medium", "high"] = "medium"
    required_for_conclusion: bool = False


class AuditDataRequestResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    hypothesis_id: str
    dimension: str
    status: Literal[
        "collected", "not_applicable", "unavailable", "unsupported", "insufficient_data",
        "failed", "skipped_budget_limit",
    ]
    source: str | None = None
    rows_analyzed: int = 0
    data: list[dict] = Field(default_factory=list)
    summary: str = ""
    limitations: list[str] = Field(default_factory=list)
    error_code: str | None = None


class AuditInvestigationHypothesis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hypothesis_id: str
    campaign_name: str
    campaign_family: Literal["search", "yan", "unknown"]
    campaign_subtype: Literal["search", "brand_search", "yan_prospecting", "yan_retargeting", "unknown"]
    observed_fact: str
    hypothesis: str
    current_status: Literal["unverified"] = "unverified"
    data_requests: list[AuditDataRequest] = Field(default_factory=list, max_length=4)


class AuditInvestigationPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hypotheses: list[AuditInvestigationHypothesis] = Field(default_factory=list, max_length=5)


class AuditHypothesisVerification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hypothesis_id: str
    status: Literal["confirmed", "partially_confirmed", "rejected", "unverified", "not_applicable"]
    verification_summary: str
    supporting_evidence: list[str] = Field(default_factory=list)
    contradicting_evidence: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    remaining_data_needed: list[str] = Field(default_factory=list)


class AuditHypothesisVerificationSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verifications: list[AuditHypothesisVerification] = Field(default_factory=list, max_length=5)


class AiAuditJobResponse(BaseModel):
    job_id: str
    client_id: str
    status: str
    current_stage: str
    progress_percent: int
    poll_after_ms: int = 1800
    requested_scope: str
    requested_period: str
    selected_campaign_name: str | None = None
    model: str
    returned_model: str | None = None
    ai_preset: str
    max_tokens: int
    system_prompt_version: str
    system_prompt_hash: str
    context_metadata: dict = Field(default_factory=dict)
    timings: dict = Field(default_factory=dict)
    result: dict | None = None
    answer: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    retryable: bool = False
    created_at: str | None = None
    updated_at: str | None = None
    completed_at: str | None = None
    expires_at: str | None = None


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
    requestDebug: dict | None = None


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
    syncDiagnostics: dict = Field(default_factory=dict)
    searchQueryInsights: dict = Field(default_factory=dict)
    yesterdayCampaignSummary: dict = Field(default_factory=dict)
    businessContextStatus: dict = Field(default_factory=dict)
    yandexDirectAudit: dict = Field(default_factory=dict)


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
