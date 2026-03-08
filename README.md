# Loan Application Processor

Backend scoring engine, state machine, and disbursement orchestration layer for a loan processing system. Built with Python, FastAPI, and SQLite.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Start the server
uvicorn main:app --reload

# Run tests
pytest tests/test_scenarios.py -v
```

The server runs at `http://127.0.0.1:8000`. Interactive API docs are available at `http://127.0.0.1:8000/docs`.

## Architecture

```
main.py                  FastAPI app, lifespan, background tasks
config.py                All scoring weights/thresholds/timeouts (Pydantic BaseSettings)
scoring.py               5-factor weighted scoring engine
state_machine.py         Transition graph with enforcement
errors.py                Typed error classes + exception handlers
database.py              SQLite via SQLAlchemy
models.py                ORM models (applications, state_transitions, webhook_events, disbursement_audits)
schemas.py               Pydantic request/response validation
routes/
  applications.py        POST /applications (submit + auto-process)
  webhooks.py            POST /webhook/disbursement
  admin.py               Admin CRUD + review (basic auth)
scripts/
  simulate_disbursement.py   Webhook simulator CLI
tests/
  test_scenarios.py      All 8 spec scenarios + state machine + admin tests
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/applications` | Submit a loan application (auto-scores and transitions) |
| POST | `/webhook/disbursement` | Receive disbursement result from external payment system |
| GET | `/admin/applications?status=...` | List applications (filterable by status) |
| GET | `/admin/applications/:id` | Full application detail with score breakdown |
| POST | `/admin/applications/:id/review` | Admin approve/deny/partially_approve |
| GET | `/health` | Health check |

Admin endpoints use HTTP Basic Auth (default: `admin` / `admin`, configurable via `LOAN_ADMIN_USERNAME` / `LOAN_ADMIN_PASSWORD` env vars).

## Scoring Engine

Applications are scored on 5 weighted factors. All weights and thresholds are configurable via environment variables (prefix `LOAN_`).

| Factor | Weight | Logic |
|--------|--------|-------|
| Income Verification | 30% | `score = max(0, 100 - (deviation / tolerance) * 25)`. Null data = 50 (neutral). |
| Income Level | 25% | Binary: income >= 3x loan amount = 100, otherwise = 0 |
| Account Stability | 20% | Three sub-checks (positive balance, no overdrafts, consistent deposits) at ~33 pts each. Null = 50% of sub-score. |
| Employment Status | 15% | employed = 100, self-employed = 50, unemployed = 0 |
| Debt-to-Income | 10% | withdrawal/deposit ratio. <= 0.3 = 100, >= 1.0 = 0, linear between. Null = 50. |

**Decision thresholds** (configurable in `config.py` or via env):
- Score >= 75: Auto-approve
- Score 50-74: Flag for manual review
- Score < 50: Auto-deny

## Design Decisions

### Income Tolerance Interpretation

The spec states income verification uses a "10% tolerance." I interpreted this as **10% in either direction from stated income** (symmetric tolerance).

**Rationale:** A symmetric tolerance forgives small mismatches in both directions, which reflects how real-world income data works. Pay stubs, bank deposits, and stated salary rarely match exactly due to rounding, variable pay, bonuses, or simple data entry differences. If someone states $5,000/mo but their documents show $4,800 (slight over-report) or $5,400 (slight under-report), both should be treated as acceptable -- the applicant isn't being dishonest, the data just has natural variance. A one-directional tolerance (e.g., only forgiving documented income *below* stated) would unfairly penalize applicants who under-reported on their form. The bidirectional approach is more lenient and fair to applicants while still catching genuinely fraudulent mismatches (e.g., claiming $10,000 when documents show $1,400).

The scoring curve is: `score = max(0, 100 - (deviation / tolerance) * 25)`. This means:
- 0% deviation: perfect score (100)
- At tolerance (10%): strong score (75)
- At 4x tolerance (40%): score drops to 0

This gradual falloff avoids a harsh cliff at the tolerance boundary while still heavily penalizing large mismatches.

### Null/Missing Data Handling

When financial documentation is missing (null), factors are scored at **50 (neutral)** rather than 0. Missing data represents *uncertainty*, not a negative signal. This naturally routes incomplete applications to manual review (50-74 range) rather than auto-denying them for lack of information. A missing document is fundamentally different from a document that shows bad numbers.

### Income Level as Binary Threshold

The income level factor uses a binary pass/fail (income >= 3x loan = 100, otherwise = 0) rather than a gradual scale. This reflects real underwriting practice where the 3x income rule is a hard qualification gate. An applicant covering only 23% of the threshold is not "23% qualified" -- they fundamentally cannot afford the loan.

### Retry Idempotency vs. Audit Trail

The spec presents a conflict: webhook replays should be idempotent (no-op), but each retry needs a unique audit record.

**Resolution:** Idempotency and audit tracking operate on different keys:

- **Idempotency** is keyed on `transaction_id` in the `webhook_events` table. The same `transaction_id` replayed produces no state change and no error (HTTP 200 with `idempotent: true`).
- **Audit trail** uses the `disbursement_audits` table with a unique `retry_id` (UUID) per attempt. Each new retry from the payment system arrives with a *new* `transaction_id`, generating a distinct audit record.

The distinction: a **replay** (network retry of the same webhook) has the same `transaction_id` and is a no-op. A **retry** (new disbursement attempt after failure) has a new `transaction_id` and creates a new audit entry. These are fundamentally different events that the system correctly differentiates.

### State Machine: Adding `partially_approved`

The state machine is a simple `dict[str, set[str]]` mapping each state to its allowed next states. Adding `partially_approved` required exactly two changes:
1. Add `"partially_approved"` to `flagged_for_review`'s transition set
2. Add a `"partially_approved": {"disbursement_queued"}` entry

No existing applications are affected because their prior states and transitions remain valid. The migration is additive -- no schema changes, no data migration, no code rewrites.

### Disbursement Timeout

A background task polls every 60 seconds for applications stuck in `disbursement_queued` past a configurable timeout (default: 30 minutes). These are transitioned through `disbursement_failed` to `flagged_for_review` for manual investigation.

## Configuration

All settings are configurable via environment variables (prefix `LOAN_`):

| Variable | Default | Description |
|----------|---------|-------------|
| `LOAN_INCOME_VERIFICATION_WEIGHT` | 0.30 | Weight for income verification factor |
| `LOAN_INCOME_LEVEL_WEIGHT` | 0.25 | Weight for income level factor |
| `LOAN_ACCOUNT_STABILITY_WEIGHT` | 0.20 | Weight for account stability factor |
| `LOAN_EMPLOYMENT_STATUS_WEIGHT` | 0.15 | Weight for employment status factor |
| `LOAN_DEBT_TO_INCOME_WEIGHT` | 0.10 | Weight for debt-to-income factor |
| `LOAN_INCOME_TOLERANCE` | 0.10 | Tolerance for income verification (10%) |
| `LOAN_AUTO_APPROVE_THRESHOLD` | 75 | Score threshold for auto-approval |
| `LOAN_MANUAL_REVIEW_THRESHOLD` | 50 | Score threshold for manual review |
| `LOAN_DUPLICATE_WINDOW_MINUTES` | 5 | Window for duplicate detection |
| `LOAN_DISBURSEMENT_TIMEOUT_MINUTES` | 30 | Timeout before flagging stuck disbursements |
| `LOAN_MAX_DISBURSEMENT_RETRIES` | 3 | Max auto-retries before escalation |
| `LOAN_ADMIN_USERNAME` | admin | Basic auth username |
| `LOAN_ADMIN_PASSWORD` | admin | Basic auth password |

## Webhook Simulator

```bash
# Run all scenarios (success, failure, replay) for an application
python scripts/simulate_disbursement.py <application_id>

# Run a specific scenario
python scripts/simulate_disbursement.py <application_id> --scenario success
python scripts/simulate_disbursement.py <application_id> --scenario failure
python scripts/simulate_disbursement.py <application_id> --scenario replay --transaction-id <txn_id>
```

## Test Scenarios

All 8 spec-required scenarios are implemented in `tests/test_scenarios.py`:

| # | Applicant | Scenario | Expected |
|---|-----------|----------|----------|
| 1 | Jane Doe | Strong financials, $1,500 loan | Auto-approve |
| 2 | Bob Smith | Weak financials, $2,000 loan | Auto-deny |
| 3 | Bob Smith | Weak financials, $300 loan | Flag for review |
| 4 | Jane Doe | Strong financials, $4,500 loan | Flag for review |
| 5 | Carol Tester | No documents, $1,000 loan | Flag for review |
| 6 | Dave Liar | Income mismatch, $2,000 loan | Auto-deny |
| 7 | Jane Doe | Duplicate resubmission | Rejected |
| 8 | Webhook | Same transaction_id replayed | Idempotent |

Additional tests cover: invalid state transitions, admin review flow, partial approval, webhook retry escalation, and admin auth.

## Open Questions (Discussed)

**What if a disbursement webhook never arrives?**
A background task checks for applications stuck in `disbursement_queued` past a configurable timeout (default 30 min). Stuck applications are transitioned to `flagged_for_review`.

**If scoring weights changed, would existing approved applications need re-evaluation?**
Not automatically. The score and breakdown are stored at time of evaluation. A policy decision could trigger batch re-evaluation, but retroactive changes to approved/disbursed loans raise legal and business concerns that go beyond the scoring engine.

**How would you extend this for multiple document types?**
Add a `documents` table with a `document_type` enum (pay_stub, tax_return, offer_letter, bank_statement). The scoring engine would accept a list of documents and extract relevant fields per type. The `documented_monthly_income` field would be computed from the best available document.

**What would change for 10,000 applications/day?**
Replace SQLite with PostgreSQL, add database connection pooling, use a proper task queue (Celery/Redis) for async scoring and disbursement instead of in-process background tasks, and add rate limiting on submission endpoints.
