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


class IntegrationStatus(BaseModel):
    id: str
    name: str
    status: str
    description: str
    next_action: str


class HealthResponse(BaseModel):
    status: str
    service: str
    environment: str
