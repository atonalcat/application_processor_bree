from typing import Optional
from datetime import datetime

from pydantic import BaseModel, Field


class ApplicationInput(BaseModel):
    applicant_name: str
    email: str
    loan_amount: float = Field(gt=0)
    stated_monthly_income: float = Field(gt=0)
    employment_status: str = Field(pattern="^(employed|self-employed|unemployed)$")
    documented_monthly_income: Optional[float] = None
    bank_ending_balance: Optional[float] = None
    bank_has_overdrafts: Optional[bool] = None
    bank_has_consistent_deposits: Optional[bool] = None
    monthly_withdrawals: Optional[float] = None
    monthly_deposits: Optional[float] = None


class ScoreBreakdown(BaseModel):
    income_verification: dict
    income_level: dict
    account_stability: dict
    employment_status: dict
    debt_to_income: dict
    total_score: float


class StateTransitionResponse(BaseModel):
    from_state: str
    to_state: str
    triggered_by: str
    timestamp: datetime


class ApplicationResponse(BaseModel):
    id: str
    applicant_name: str
    email: str
    loan_amount: float
    status: str
    score: Optional[float] = None
    score_breakdown: Optional[dict] = None
    approved_amount: Optional[float] = None
    review_note: Optional[str] = None
    disbursement_retry_count: int = 0
    created_at: datetime
    updated_at: datetime
    state_history: Optional[list] = None

    model_config = {"from_attributes": True}


class WebhookPayload(BaseModel):
    application_id: str
    status: str = Field(pattern="^(success|failed)$")
    transaction_id: str
    timestamp: datetime


class ReviewInput(BaseModel):
    decision: str = Field(pattern="^(approved|denied|partially_approved)$")
    note: Optional[str] = None
    approved_amount: Optional[float] = Field(default=None, gt=0)


class WebhookResponse(BaseModel):
    message: str
    application_id: str
    new_status: str
    idempotent: bool = False
