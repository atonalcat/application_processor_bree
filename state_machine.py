from sqlalchemy.orm import Session

from models import Application, StateTransition, utc_now
from errors import InvalidStateTransitionError

# Every valid transition in the system. Adding a new state (like partially_approved)
# only requires adding entries here -- no other code changes needed.
VALID_TRANSITIONS: dict[str, set[str]] = {
    "submitted": {"processing"},
    "processing": {"approved", "denied", "flagged_for_review"},
    "flagged_for_review": {"approved", "denied", "partially_approved"},
    "approved": {"disbursement_queued"},
    "partially_approved": {"disbursement_queued"},
    "disbursement_queued": {"disbursed", "disbursement_failed"},
    "disbursement_failed": {"disbursement_queued", "flagged_for_review"},
    # Terminal states have no outgoing transitions
    "denied": set(),
    "disbursed": set(),
}


def validate_transition(from_state: str, to_state: str) -> bool:
    allowed = VALID_TRANSITIONS.get(from_state, set())
    return to_state in allowed


def transition_application(
    db: Session,
    application: Application,
    to_state: str,
    triggered_by: str = "system",
) -> Application:
    """Transition an application to a new state, enforcing the state machine.

    Raises InvalidStateTransitionError if the transition is not allowed.
    Records the transition in the state_transitions audit table.
    """
    from_state = application.status

    if not validate_transition(from_state, to_state):
        raise InvalidStateTransitionError(application.id, from_state, to_state)

    transition_record = StateTransition(
        application_id=application.id,
        from_state=from_state,
        to_state=to_state,
        triggered_by=triggered_by,
        timestamp=utc_now(),
    )

    application.status = to_state
    application.updated_at = utc_now()

    db.add(transition_record)
    db.flush()

    return application
