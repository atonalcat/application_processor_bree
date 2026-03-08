from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
import asyncio

from fastapi import FastAPI

from database import init_db, SessionLocal
from models import Application
from state_machine import transition_application
from errors import register_error_handlers
from config import scoring_config
from routes import applications, webhooks, admin


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    task = asyncio.create_task(disbursement_timeout_checker())
    yield
    task.cancel()


app = FastAPI(
    title="Loan Application Processor",
    description="AI-Powered Loan Application Processor — Backend",
    version="1.0.0",
    lifespan=lifespan,
)

register_error_handlers(app)

app.include_router(applications.router)
app.include_router(webhooks.router)
app.include_router(admin.router)


@app.get("/health")
def health_check():
    return {"status": "healthy"}


async def disbursement_timeout_checker():
    """Background task that flags applications stuck in disbursement_queued
    past the configured timeout for manual review."""
    while True:
        await asyncio.sleep(60)
        try:
            db = SessionLocal()
            cutoff = datetime.now(timezone.utc) - timedelta(
                minutes=scoring_config.disbursement_timeout_minutes
            )
            stuck_apps = (
                db.query(Application)
                .filter(
                    Application.status == "disbursement_queued",
                    Application.updated_at <= cutoff,
                )
                .all()
            )
            for app_record in stuck_apps:
                transition_application(
                    db, app_record, "disbursement_failed", triggered_by="timeout_checker"
                )
                transition_application(
                    db, app_record, "flagged_for_review", triggered_by="timeout_checker"
                )
            if stuck_apps:
                db.commit()
            db.close()
        except Exception:
            pass
