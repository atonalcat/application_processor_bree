from pydantic_settings import BaseSettings


class ScoringConfig(BaseSettings):
    income_verification_weight: float = 0.30
    income_level_weight: float = 0.25
    account_stability_weight: float = 0.20
    employment_status_weight: float = 0.15
    debt_to_income_weight: float = 0.10

    # 10% tolerance in either direction from stated income.
    # If documented income is within +/- 10% of stated income, full marks.
    # Rationale: the verification check guards against both over-reporting
    # (fraud) and under-reporting (data entry errors). A symmetric tolerance
    # is the most conservative and fair interpretation.
    income_tolerance: float = 0.10

    auto_approve_threshold: int = 75
    manual_review_threshold: int = 50

    duplicate_window_minutes: int = 5
    disbursement_timeout_minutes: int = 30
    max_disbursement_retries: int = 3

    admin_username: str = "admin"
    admin_password: str = "admin"

    model_config = {"env_prefix": "LOAN_"}


scoring_config = ScoringConfig()
