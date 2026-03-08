from fastapi import Request
from fastapi.responses import JSONResponse


class InvalidStateTransitionError(Exception):
    def __init__(self, application_id: str, from_state: str, to_state: str):
        self.application_id = application_id
        self.from_state = from_state
        self.to_state = to_state
        super().__init__(
            f"Invalid state transition for application {application_id}: "
            f"'{from_state}' -> '{to_state}'"
        )


class DuplicateApplicationError(Exception):
    def __init__(self, original_id: str, email: str, loan_amount: float):
        self.original_id = original_id
        self.email = email
        self.loan_amount = loan_amount
        super().__init__(
            f"Duplicate application: email={email}, loan_amount={loan_amount}. "
            f"Original application ID: {original_id}"
        )


class WebhookReplayError(Exception):
    def __init__(self, transaction_id: str):
        self.transaction_id = transaction_id
        super().__init__(
            f"Webhook replay detected for transaction_id={transaction_id}. "
            "No state change applied."
        )


def register_error_handlers(app):
    @app.exception_handler(InvalidStateTransitionError)
    async def handle_invalid_transition(request: Request, exc: InvalidStateTransitionError):
        return JSONResponse(
            status_code=409,
            content={
                "error": "InvalidStateTransitionError",
                "message": str(exc),
                "details": {
                    "application_id": exc.application_id,
                    "from_state": exc.from_state,
                    "to_state": exc.to_state,
                },
            },
        )

    @app.exception_handler(DuplicateApplicationError)
    async def handle_duplicate(request: Request, exc: DuplicateApplicationError):
        return JSONResponse(
            status_code=409,
            content={
                "error": "DuplicateApplicationError",
                "message": str(exc),
                "details": {
                    "original_application_id": exc.original_id,
                    "email": exc.email,
                    "loan_amount": exc.loan_amount,
                },
            },
        )

    @app.exception_handler(WebhookReplayError)
    async def handle_webhook_replay(request: Request, exc: WebhookReplayError):
        return JSONResponse(
            status_code=200,
            content={
                "error": "WebhookReplayError",
                "message": str(exc),
                "details": {
                    "transaction_id": exc.transaction_id,
                    "idempotent": True,
                },
            },
        )
