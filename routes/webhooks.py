import json
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import Application, WebhookEvent, DisbursementAudit, utc_now
from schemas import WebhookPayload, WebhookResponse
from state_machine import transition_application
from config import scoring_config

router = APIRouter()


@router.post("/webhook/disbursement", response_model=WebhookResponse)
def handle_disbursement_webhook(payload: WebhookPayload, db: Session = Depends(get_db)):
    # Check for replay (idempotency on transaction_id)
    existing_event = (
        db.query(WebhookEvent)
        .filter(WebhookEvent.transaction_id == payload.transaction_id)
        .first()
    )
    if existing_event:
        app = db.query(Application).filter(Application.id == existing_event.application_id).first()
        return WebhookResponse(
            message="Webhook replay detected. No state change applied.",
            application_id=payload.application_id,
            new_status=app.status if app else "unknown",
            idempotent=True,
        )

    application = (
        db.query(Application).filter(Application.id == payload.application_id).first()
    )
    if not application:
        raise HTTPException(status_code=404, detail=f"Application {payload.application_id} not found")

    webhook_event = WebhookEvent(
        application_id=payload.application_id,
        transaction_id=payload.transaction_id,
        status=payload.status,
        payload=json.dumps(payload.model_dump(), default=str),
        timestamp=utc_now(),
    )
    db.add(webhook_event)

    if payload.status == "success":
        transition_application(db, application, "disbursed", triggered_by="webhook")

        audit = DisbursementAudit(
            application_id=application.id,
            retry_id=str(uuid.uuid4()),
            attempt_number=application.disbursement_retry_count + 1,
            transaction_id=payload.transaction_id,
            status="success",
            details="Disbursement completed successfully",
        )
        db.add(audit)
        db.commit()

        return WebhookResponse(
            message="Disbursement successful",
            application_id=application.id,
            new_status="disbursed",
        )

    elif payload.status == "failed":
        transition_application(db, application, "disbursement_failed", triggered_by="webhook")

        application.disbursement_retry_count += 1
        retry_id = str(uuid.uuid4())

        audit = DisbursementAudit(
            application_id=application.id,
            retry_id=retry_id,
            attempt_number=application.disbursement_retry_count,
            transaction_id=payload.transaction_id,
            status="failed",
            details=f"Disbursement failed (attempt {application.disbursement_retry_count}/{scoring_config.max_disbursement_retries})",
        )
        db.add(audit)

        if application.disbursement_retry_count < scoring_config.max_disbursement_retries:
            transition_application(
                db, application, "disbursement_queued", triggered_by=f"auto_retry_{retry_id}"
            )
            db.commit()

            return WebhookResponse(
                message=f"Disbursement failed. Auto-retry queued (attempt {application.disbursement_retry_count}/{scoring_config.max_disbursement_retries})",
                application_id=application.id,
                new_status="disbursement_queued",
            )
        else:
            transition_application(
                db, application, "flagged_for_review", triggered_by=f"max_retries_exceeded_{retry_id}"
            )
            db.commit()

            return WebhookResponse(
                message=f"Disbursement failed after {scoring_config.max_disbursement_retries} attempts. Flagged for manual review.",
                application_id=application.id,
                new_status="flagged_for_review",
            )
