from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


RiskLevel = Literal["low", "medium", "high", "unknown"]


class EvalExpected(BaseModel):
    model_config = ConfigDict(extra="forbid")

    should_find: list[str] = Field(default_factory=list)
    should_recommend: list[str] = Field(default_factory=list)
    should_not_do: list[str] = Field(default_factory=list)
    risk_level: RiskLevel | None = None
    requires_human_approval: bool | None = None

    @model_validator(mode="after")
    def validate_assertions(self) -> "EvalExpected":
        if not self.should_find and not self.should_not_do:
            raise ValueError("Eval expected must define should_find or should_not_do.")
        return self


class EvalCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    task: str = Field(min_length=1)
    input_data: dict[str, Any] = Field(min_length=1)
    expected: EvalExpected
    tags: list[str] = Field(default_factory=list)


class EvalCaseScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    score: float = Field(ge=0, le=100)
    max_score: float = 100.0
    passed: bool
    matched_should_find: list[str] = Field(default_factory=list)
    missed_should_find: list[str] = Field(default_factory=list)
    matched_should_recommend: list[str] = Field(default_factory=list)
    missed_should_recommend: list[str] = Field(default_factory=list)
    dangerous_violations: list[str] = Field(default_factory=list)
    has_dangerous_violation: bool = False
    risk_level_expected: RiskLevel | None = None
    risk_level_actual: str | None = None
    approval_expected: bool | None = None
    approval_actual: bool | None = None
    notes: list[str] = Field(default_factory=list)


class EvalRunReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    model: str
    total_cases: int
    passed_cases: int
    failed_cases: int
    average_score: float
    dangerous_violations_count: int
    case_scores: list[EvalCaseScore] = Field(default_factory=list)
