import json
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from models import Application, utc_now
from schemas import ApplicationInput, ApplicationResponse
from scoring import calculate_score, get_decision
from state_machine import transition_application
from errors import DuplicateApplicationError
from config import scoring_config

router = APIRouter()


def check_duplicate(db: Session, email: str, loan_amount: float) -> Application | None:
    """Check for a duplicate application (same email + loan amount within the configured window)."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=scoring_config.duplicate_window_minutes)
    existing = (
        db.query(Application)
        .filter(
            Application.email == email,
            Application.loan_amount == loan_amount,
            Application.created_at >= cutoff,
        )
        .first()
    )
    return existing


@router.post("/applications", response_model=ApplicationResponse)
def submit_application(input_data: ApplicationInput, db: Session = Depends(get_db)):
    duplicate = check_duplicate(db, input_data.email, input_data.loan_amount)
    if duplicate:
        raise DuplicateApplicationError(duplicate.id, input_data.email, input_data.loan_amount)

    application = Application(
        applicant_name=input_data.applicant_name,
        email=input_data.email,
        loan_amount=input_data.loan_amount,
        stated_monthly_income=input_data.stated_monthly_income,
        employment_status=input_data.employment_status,
        documented_monthly_income=input_data.documented_monthly_income,
        bank_ending_balance=input_data.bank_ending_balance,
        bank_has_overdrafts=input_data.bank_has_overdrafts,
        bank_has_consistent_deposits=input_data.bank_has_consistent_deposits,
        monthly_withdrawals=input_data.monthly_withdrawals,
        monthly_deposits=input_data.monthly_deposits,
    )
    db.add(application)
    db.flush()

    transition_application(db, application, "processing", triggered_by="system")

    score_result = calculate_score(input_data.model_dump())
    application.score = score_result["total_score"]
    application.score_breakdown = json.dumps(score_result["breakdown"])

    decision = get_decision(score_result["total_score"])
    transition_application(db, application, decision, triggered_by="scoring_engine")

    if decision == "approved":
        transition_application(db, application, "disbursement_queued", triggered_by="system")

    db.commit()
    db.refresh(application)

    return build_application_response(application)


def build_application_response(application: Application) -> dict:
    breakdown = None
    if application.score_breakdown:
        breakdown = json.loads(application.score_breakdown)

    state_history = [
        {
            "from_state": t.from_state,
            "to_state": t.to_state,
            "triggered_by": t.triggered_by,
            "timestamp": t.timestamp.isoformat() if t.timestamp else None,
        }
        for t in application.state_transitions
    ]

    return {
        "id": application.id,
        "applicant_name": application.applicant_name,
        "email": application.email,
        "loan_amount": application.loan_amount,
        "status": application.status,
        "score": application.score,
        "score_breakdown": breakdown,
        "approved_amount": application.approved_amount,
        "review_note": application.review_note,
        "disbursement_retry_count": application.disbursement_retry_count,
        "created_at": application.created_at,
        "updated_at": application.updated_at,
        "state_history": state_history,
    }
