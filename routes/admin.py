import secrets
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy.orm import Session

from database import get_db
from models import Application
from schemas import ApplicationResponse, ReviewInput
from state_machine import transition_application
from routes.applications import build_application_response
from config import scoring_config

router = APIRouter(prefix="/admin")
security = HTTPBasic()


def verify_admin(credentials: HTTPBasicCredentials = Depends(security)):
    correct_username = secrets.compare_digest(credentials.username, scoring_config.admin_username)
    correct_password = secrets.compare_digest(credentials.password, scoring_config.admin_password)
    if not (correct_username and correct_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return credentials.username


@router.get("/applications")
def list_applications(
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    admin: str = Depends(verify_admin),
):
    query = db.query(Application)
    if status:
        query = query.filter(Application.status == status)
    query = query.order_by(Application.created_at.desc())
    applications = query.all()

    return [build_application_response(app) for app in applications]


@router.get("/applications/{application_id}")
def get_application(
    application_id: str,
    db: Session = Depends(get_db),
    admin: str = Depends(verify_admin),
):
    application = db.query(Application).filter(Application.id == application_id).first()
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    return build_application_response(application)


@router.post("/applications/{application_id}/review")
def review_application(
    application_id: str,
    review: ReviewInput,
    db: Session = Depends(get_db),
    admin: str = Depends(verify_admin),
):
    application = db.query(Application).filter(Application.id == application_id).first()
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")

    if application.status != "flagged_for_review":
        raise HTTPException(
            status_code=409,
            detail=f"Application is in '{application.status}' state, not 'flagged_for_review'. Cannot review.",
        )

    if review.decision == "partially_approved" and review.approved_amount is None:
        raise HTTPException(
            status_code=400,
            detail="approved_amount is required for partial approval",
        )

    if review.decision == "partially_approved" and review.approved_amount >= application.loan_amount:
        raise HTTPException(
            status_code=400,
            detail="approved_amount must be less than the original loan_amount for partial approval",
        )

    transition_application(db, application, review.decision, triggered_by=f"admin:{admin}")

    application.review_note = review.note
    if review.decision == "partially_approved":
        application.approved_amount = review.approved_amount

    if review.decision in ("approved", "partially_approved"):
        transition_application(db, application, "disbursement_queued", triggered_by=f"admin:{admin}")

    db.commit()
    db.refresh(application)

    return build_application_response(application)
