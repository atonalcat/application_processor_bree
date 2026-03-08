import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    String,
    Float,
    Boolean,
    Integer,
    DateTime,
    Text,
    ForeignKey,
)
from sqlalchemy.orm import relationship

from database import Base


def generate_uuid():
    return str(uuid.uuid4())


def utc_now():
    return datetime.now(timezone.utc)


class Application(Base):
    __tablename__ = "applications"

    id = Column(String, primary_key=True, default=generate_uuid)
    applicant_name = Column(String, nullable=False)
    email = Column(String, nullable=False, index=True)
    loan_amount = Column(Float, nullable=False)
    stated_monthly_income = Column(Float, nullable=False)
    employment_status = Column(String, nullable=False)
    documented_monthly_income = Column(Float, nullable=True)
    bank_ending_balance = Column(Float, nullable=True)
    bank_has_overdrafts = Column(Boolean, nullable=True)
    bank_has_consistent_deposits = Column(Boolean, nullable=True)
    monthly_withdrawals = Column(Float, nullable=True)
    monthly_deposits = Column(Float, nullable=True)

    status = Column(String, nullable=False, default="submitted")
    score = Column(Float, nullable=True)
    score_breakdown = Column(Text, nullable=True)  # JSON string

    # For partial approvals
    approved_amount = Column(Float, nullable=True)
    review_note = Column(Text, nullable=True)

    # Retry tracking for disbursement
    disbursement_retry_count = Column(Integer, default=0)

    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    state_transitions = relationship(
        "StateTransition", back_populates="application", order_by="StateTransition.timestamp"
    )
    webhook_events = relationship("WebhookEvent", back_populates="application")
    disbursement_audits = relationship(
        "DisbursementAudit", back_populates="application", order_by="DisbursementAudit.timestamp"
    )


class StateTransition(Base):
    __tablename__ = "state_transitions"

    id = Column(String, primary_key=True, default=generate_uuid)
    application_id = Column(String, ForeignKey("applications.id"), nullable=False, index=True)
    from_state = Column(String, nullable=False)
    to_state = Column(String, nullable=False)
    triggered_by = Column(String, nullable=False, default="system")
    timestamp = Column(DateTime, default=utc_now)

    application = relationship("Application", back_populates="state_transitions")


class WebhookEvent(Base):
    __tablename__ = "webhook_events"

    id = Column(String, primary_key=True, default=generate_uuid)
    application_id = Column(String, ForeignKey("applications.id"), nullable=False, index=True)
    transaction_id = Column(String, nullable=False, unique=True, index=True)
    status = Column(String, nullable=False)
    payload = Column(Text, nullable=True)  # JSON string
    timestamp = Column(DateTime, default=utc_now)

    application = relationship("Application", back_populates="webhook_events")


class DisbursementAudit(Base):
    __tablename__ = "disbursement_audits"

    id = Column(String, primary_key=True, default=generate_uuid)
    application_id = Column(String, ForeignKey("applications.id"), nullable=False, index=True)
    retry_id = Column(String, nullable=False, default=generate_uuid)
    attempt_number = Column(Integer, nullable=False)
    transaction_id = Column(String, nullable=True)
    status = Column(String, nullable=False)
    details = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=utc_now)

    application = relationship("Application", back_populates="disbursement_audits")
