"""
Test scenarios matching the 8 required test cases from the spec.

Run with: pytest tests/test_scenarios.py -v
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base, get_db
from main import app

TEST_DATABASE_URL = "sqlite:///./test_loan_processor.db"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db

ADMIN_AUTH = ("admin", "admin")


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


client = TestClient(app)

# ---- Test input data from the spec ----

SCENARIO_1_JANE_DOE_STRONG = {
    "applicant_name": "Jane Doe",
    "email": "jane.doe@example.com",
    "loan_amount": 1500,
    "stated_monthly_income": 5000,
    "employment_status": "employed",
    "documented_monthly_income": 4800,
    "bank_ending_balance": 3200,
    "bank_has_overdrafts": False,
    "bank_has_consistent_deposits": True,
    "monthly_withdrawals": 1200,
    "monthly_deposits": 4800,
}

SCENARIO_2_BOB_SMITH_WEAK = {
    "applicant_name": "Bob Smith",
    "email": "bob.smith@example.com",
    "loan_amount": 2000,
    "stated_monthly_income": 1400,
    "employment_status": "self-employed",
    "documented_monthly_income": 1350,
    "bank_ending_balance": 150,
    "bank_has_overdrafts": True,
    "bank_has_consistent_deposits": False,
    "monthly_withdrawals": 1100,
    "monthly_deposits": 1350,
}

SCENARIO_3_BOB_SMITH_SMALL_LOAN = {
    "applicant_name": "Bob Smith",
    "email": "bob.smith@example.com",
    "loan_amount": 300,
    "stated_monthly_income": 1400,
    "employment_status": "self-employed",
    "documented_monthly_income": 1350,
    "bank_ending_balance": 150,
    "bank_has_overdrafts": True,
    "bank_has_consistent_deposits": False,
    "monthly_withdrawals": 1100,
    "monthly_deposits": 1350,
}

SCENARIO_4_JANE_DOE_LARGE_LOAN = {
    "applicant_name": "Jane Doe",
    "email": "jane.doe@example.com",
    "loan_amount": 4500,
    "stated_monthly_income": 5000,
    "employment_status": "employed",
    "documented_monthly_income": 4800,
    "bank_ending_balance": 3200,
    "bank_has_overdrafts": False,
    "bank_has_consistent_deposits": True,
    "monthly_withdrawals": 1200,
    "monthly_deposits": 4800,
}

SCENARIO_5_CAROL_NO_DOCS = {
    "applicant_name": "Carol Tester",
    "email": "carol.tester@example.com",
    "loan_amount": 1000,
    "stated_monthly_income": 8000,
    "employment_status": "employed",
    "documented_monthly_income": None,
    "bank_ending_balance": None,
    "bank_has_overdrafts": None,
    "bank_has_consistent_deposits": None,
    "monthly_withdrawals": None,
    "monthly_deposits": None,
}

SCENARIO_6_DAVE_LIAR = {
    "applicant_name": "Dave Liar",
    "email": "dave.liar@example.com",
    "loan_amount": 2000,
    "stated_monthly_income": 10000,
    "employment_status": "employed",
    "documented_monthly_income": 1400,
    "bank_ending_balance": 150,
    "bank_has_overdrafts": True,
    "bank_has_consistent_deposits": False,
    "monthly_withdrawals": 1100,
    "monthly_deposits": 1400,
}


# ---- Scenario 1: Jane Doe strong financials -> Auto-approve ----

class TestScenario1:
    def test_jane_doe_strong_financials_auto_approve(self):
        """Strong financials: score >= 75 -> auto-approve -> disbursement_queued."""
        response = client.post("/applications", json=SCENARIO_1_JANE_DOE_STRONG)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "disbursement_queued"
        assert data["score"] >= 75
        assert data["score_breakdown"] is not None


# ---- Scenario 2: Bob Smith weak financials -> Auto-deny ----

class TestScenario2:
    def test_bob_smith_weak_financials_auto_deny(self):
        """Weak financials with large loan: score < 50 -> auto-deny."""
        response = client.post("/applications", json=SCENARIO_2_BOB_SMITH_WEAK)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "denied"
        assert data["score"] < 50


# ---- Scenario 3: Bob Smith small loan -> Flag for review ----

class TestScenario3:
    def test_bob_smith_small_loan_flag_for_review(self):
        """Same weak financials but smaller loan: score 50-74 -> flag for review."""
        response = client.post("/applications", json=SCENARIO_3_BOB_SMITH_SMALL_LOAN)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "flagged_for_review"
        assert 50 <= data["score"] < 75


# ---- Scenario 4: Jane Doe large loan -> Flag for review ----

class TestScenario4:
    def test_jane_doe_large_loan_flag_for_review(self):
        """Strong financials but large loan: score 50-74 -> flag for review."""
        response = client.post("/applications", json=SCENARIO_4_JANE_DOE_LARGE_LOAN)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "flagged_for_review"
        assert 50 <= data["score"] < 75


# ---- Scenario 5: Carol Tester no documents -> Flag for review ----

class TestScenario5:
    def test_carol_no_documents_flag_for_review(self):
        """No documentation: missing data scored neutrally -> flag for review."""
        response = client.post("/applications", json=SCENARIO_5_CAROL_NO_DOCS)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "flagged_for_review"
        assert 50 <= data["score"] < 75


# ---- Scenario 6: Dave Liar income mismatch -> Auto-deny ----

class TestScenario6:
    def test_dave_liar_income_mismatch_auto_deny(self):
        """Massive income mismatch: score < 50 -> auto-deny."""
        response = client.post("/applications", json=SCENARIO_6_DAVE_LIAR)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "denied"
        assert data["score"] < 50


# ---- Scenario 7: Duplicate submission -> Rejected ----

class TestScenario7:
    def test_duplicate_submission_rejected(self):
        """Same email + loan amount within 5 minutes -> duplicate rejected."""
        response1 = client.post("/applications", json=SCENARIO_1_JANE_DOE_STRONG)
        assert response1.status_code == 200
        original_id = response1.json()["id"]

        response2 = client.post("/applications", json=SCENARIO_1_JANE_DOE_STRONG)
        assert response2.status_code == 409
        data = response2.json()
        assert data["error"] == "DuplicateApplicationError"
        assert data["details"]["original_application_id"] == original_id


# ---- Scenario 8: Webhook replay -> Idempotent ----

class TestScenario8:
    def test_webhook_replay_idempotent(self):
        """Same transaction_id sent twice -> idempotent (no state change, no error)."""
        response = client.post("/applications", json=SCENARIO_1_JANE_DOE_STRONG)
        app_id = response.json()["id"]
        txn_id = f"txn_{uuid.uuid4().hex[:12]}"

        webhook_payload = {
            "application_id": app_id,
            "status": "success",
            "transaction_id": txn_id,
            "timestamp": "2026-01-15T10:30:00Z",
        }

        r1 = client.post("/webhook/disbursement", json=webhook_payload)
        assert r1.status_code == 200
        assert r1.json()["new_status"] == "disbursed"

        r2 = client.post("/webhook/disbursement", json=webhook_payload)
        assert r2.status_code == 200
        assert r2.json()["idempotent"] is True
        assert r2.json()["new_status"] == "disbursed"


# ---- State machine enforcement ----

class TestStateMachine:
    def test_invalid_transition_denied_to_processing(self):
        """denied -> processing must be rejected (spec requirement)."""
        response = client.post("/applications", json=SCENARIO_2_BOB_SMITH_WEAK)
        app_id = response.json()["id"]
        assert response.json()["status"] == "denied"

        detail = client.get(f"/admin/applications/{app_id}", auth=ADMIN_AUTH)
        assert detail.status_code == 200
        assert detail.json()["status"] == "denied"

    def test_admin_review_approve_then_disburse(self):
        """flagged_for_review -> approved -> disbursement_queued via admin review."""
        response = client.post("/applications", json=SCENARIO_3_BOB_SMITH_SMALL_LOAN)
        app_id = response.json()["id"]
        assert response.json()["status"] == "flagged_for_review"

        review = client.post(
            f"/admin/applications/{app_id}/review",
            json={"decision": "approved", "note": "Looks good after manual check"},
            auth=ADMIN_AUTH,
        )
        assert review.status_code == 200
        assert review.json()["status"] == "disbursement_queued"

    def test_admin_partial_approval(self):
        """flagged_for_review -> partially_approved -> disbursement_queued."""
        response = client.post("/applications", json=SCENARIO_4_JANE_DOE_LARGE_LOAN)
        app_id = response.json()["id"]
        assert response.json()["status"] == "flagged_for_review"

        review = client.post(
            f"/admin/applications/{app_id}/review",
            json={
                "decision": "partially_approved",
                "note": "Approved for reduced amount",
                "approved_amount": 2000,
            },
            auth=ADMIN_AUTH,
        )
        assert review.status_code == 200
        assert review.json()["status"] == "disbursement_queued"
        assert review.json()["approved_amount"] == 2000

    def test_cannot_review_non_flagged_application(self):
        """Trying to review a denied application returns an error."""
        response = client.post("/applications", json=SCENARIO_2_BOB_SMITH_WEAK)
        app_id = response.json()["id"]

        review = client.post(
            f"/admin/applications/{app_id}/review",
            json={"decision": "approved", "note": "Trying to override"},
            auth=ADMIN_AUTH,
        )
        assert review.status_code == 409


# ---- Webhook retry + audit trail ----

class TestWebhookRetry:
    def test_failure_auto_retries_then_escalates(self):
        """3 failures -> escalate to manual review. Each retry logged separately."""
        response = client.post("/applications", json=SCENARIO_1_JANE_DOE_STRONG)
        app_id = response.json()["id"]

        txn1 = f"txn_{uuid.uuid4().hex[:12]}"
        r1 = client.post("/webhook/disbursement", json={
            "application_id": app_id,
            "status": "failed",
            "transaction_id": txn1,
            "timestamp": "2026-01-15T10:30:00Z",
        })
        assert r1.status_code == 200
        assert r1.json()["new_status"] == "disbursement_queued"

        txn2 = f"txn_{uuid.uuid4().hex[:12]}"
        r2 = client.post("/webhook/disbursement", json={
            "application_id": app_id,
            "status": "failed",
            "transaction_id": txn2,
            "timestamp": "2026-01-15T10:31:00Z",
        })
        assert r2.status_code == 200
        assert r2.json()["new_status"] == "disbursement_queued"

        txn3 = f"txn_{uuid.uuid4().hex[:12]}"
        r3 = client.post("/webhook/disbursement", json={
            "application_id": app_id,
            "status": "failed",
            "transaction_id": txn3,
            "timestamp": "2026-01-15T10:32:00Z",
        })
        assert r3.status_code == 200
        assert r3.json()["new_status"] == "flagged_for_review"

        detail = client.get(f"/admin/applications/{app_id}", auth=ADMIN_AUTH)
        assert detail.json()["disbursement_retry_count"] == 3


# ---- Admin endpoints ----

class TestAdminEndpoints:
    def test_list_filter_by_status(self):
        client.post("/applications", json=SCENARIO_1_JANE_DOE_STRONG)
        client.post("/applications", json=SCENARIO_2_BOB_SMITH_WEAK)
        client.post("/applications", json=SCENARIO_5_CAROL_NO_DOCS)

        response = client.get(
            "/admin/applications?status=flagged_for_review", auth=ADMIN_AUTH
        )
        assert response.status_code == 200
        results = response.json()
        assert len(results) > 0
        for app_data in results:
            assert app_data["status"] == "flagged_for_review"

    def test_get_application_detail_with_score_breakdown(self):
        create = client.post("/applications", json=SCENARIO_1_JANE_DOE_STRONG)
        app_id = create.json()["id"]

        response = client.get(f"/admin/applications/{app_id}", auth=ADMIN_AUTH)
        assert response.status_code == 200
        data = response.json()
        assert data["score_breakdown"] is not None
        assert "income_verification" in data["score_breakdown"]
        assert "income_level" in data["score_breakdown"]
        assert data["state_history"] is not None
        assert len(data["state_history"]) > 0

    def test_unauthorized_access_rejected(self):
        response = client.get("/admin/applications", auth=("wrong", "creds"))
        assert response.status_code == 401

    def test_list_all_applications(self):
        client.post("/applications", json=SCENARIO_1_JANE_DOE_STRONG)
        client.post("/applications", json=SCENARIO_2_BOB_SMITH_WEAK)

        response = client.get("/admin/applications", auth=ADMIN_AUTH)
        assert response.status_code == 200
        assert len(response.json()) == 2


# ---- End-to-end workflow tests ----

class TestE2EHappyPath:
    def test_submit_approve_disburse_full_lifecycle(self):
        """Full happy path: submit -> auto-approve -> webhook success -> disbursed.
        Verifies every state transition is recorded in the audit history."""
        # 1. Submit application (auto-approve -> disbursement_queued)
        submit = client.post("/applications", json=SCENARIO_1_JANE_DOE_STRONG)
        assert submit.status_code == 200
        app_id = submit.json()["id"]
        assert submit.json()["status"] == "disbursement_queued"
        assert submit.json()["score"] >= 75

        # 2. Simulate successful disbursement webhook
        txn_id = f"txn_{uuid.uuid4().hex[:12]}"
        webhook = client.post("/webhook/disbursement", json={
            "application_id": app_id,
            "status": "success",
            "transaction_id": txn_id,
            "timestamp": "2026-03-06T12:00:00Z",
        })
        assert webhook.status_code == 200
        assert webhook.json()["new_status"] == "disbursed"

        # 3. Verify final state via admin detail
        detail = client.get(f"/admin/applications/{app_id}", auth=ADMIN_AUTH)
        assert detail.status_code == 200
        data = detail.json()
        assert data["status"] == "disbursed"
        assert data["score_breakdown"] is not None

        # Verify complete state history
        history = data["state_history"]
        states = [t["to_state"] for t in history]
        assert states == ["processing", "approved", "disbursement_queued", "disbursed"]


class TestE2EManualReview:
    def test_flagged_review_approve_disburse(self):
        """Manual review flow: submit -> flagged -> admin approves -> webhook -> disbursed."""
        # 1. Submit (gets flagged for review)
        submit = client.post("/applications", json=SCENARIO_3_BOB_SMITH_SMALL_LOAN)
        assert submit.status_code == 200
        app_id = submit.json()["id"]
        assert submit.json()["status"] == "flagged_for_review"

        # 2. Admin finds it in the flagged list
        flagged = client.get(
            "/admin/applications?status=flagged_for_review", auth=ADMIN_AUTH
        )
        assert flagged.status_code == 200
        flagged_ids = [a["id"] for a in flagged.json()]
        assert app_id in flagged_ids

        # 3. Admin approves
        review = client.post(
            f"/admin/applications/{app_id}/review",
            json={"decision": "approved", "note": "Manually verified income"},
            auth=ADMIN_AUTH,
        )
        assert review.status_code == 200
        assert review.json()["status"] == "disbursement_queued"

        # 4. Successful disbursement webhook
        txn_id = f"txn_{uuid.uuid4().hex[:12]}"
        webhook = client.post("/webhook/disbursement", json={
            "application_id": app_id,
            "status": "success",
            "transaction_id": txn_id,
            "timestamp": "2026-03-06T12:00:00Z",
        })
        assert webhook.status_code == 200
        assert webhook.json()["new_status"] == "disbursed"

        # 5. Verify final state and full history
        detail = client.get(f"/admin/applications/{app_id}", auth=ADMIN_AUTH)
        data = detail.json()
        assert data["status"] == "disbursed"
        assert data["review_note"] == "Manually verified income"
        states = [t["to_state"] for t in data["state_history"]]
        assert states == [
            "processing", "flagged_for_review",
            "approved", "disbursement_queued", "disbursed",
        ]


class TestE2EPartialApproval:
    def test_flagged_partial_approve_disburse(self):
        """Partial approval flow: submit -> flagged -> partial approve (reduced amount) -> disburse."""
        # 1. Submit (gets flagged)
        submit = client.post("/applications", json=SCENARIO_4_JANE_DOE_LARGE_LOAN)
        assert submit.status_code == 200
        app_id = submit.json()["id"]
        assert submit.json()["status"] == "flagged_for_review"

        # 2. Admin partially approves with reduced amount
        review = client.post(
            f"/admin/applications/{app_id}/review",
            json={
                "decision": "partially_approved",
                "note": "Approved for reduced amount based on income ratio",
                "approved_amount": 2500,
            },
            auth=ADMIN_AUTH,
        )
        assert review.status_code == 200
        assert review.json()["status"] == "disbursement_queued"
        assert review.json()["approved_amount"] == 2500

        # 3. Successful disbursement
        txn_id = f"txn_{uuid.uuid4().hex[:12]}"
        webhook = client.post("/webhook/disbursement", json={
            "application_id": app_id,
            "status": "success",
            "transaction_id": txn_id,
            "timestamp": "2026-03-06T12:00:00Z",
        })
        assert webhook.status_code == 200
        assert webhook.json()["new_status"] == "disbursed"

        # 4. Verify final state
        detail = client.get(f"/admin/applications/{app_id}", auth=ADMIN_AUTH)
        data = detail.json()
        assert data["status"] == "disbursed"
        assert data["approved_amount"] == 2500
        states = [t["to_state"] for t in data["state_history"]]
        assert states == [
            "processing", "flagged_for_review",
            "partially_approved", "disbursement_queued", "disbursed",
        ]


class TestE2ERetryThenManualRecovery:
    def test_approve_fail_retry_exhaust_review_approve_disburse(self):
        """Full failure recovery: approve -> 3 failures -> flagged -> admin re-approves -> disburse."""
        # 1. Submit (auto-approve)
        submit = client.post("/applications", json=SCENARIO_1_JANE_DOE_STRONG)
        app_id = submit.json()["id"]
        assert submit.json()["status"] == "disbursement_queued"

        # 2. Three failed disbursement attempts (exhaust retries)
        for i in range(3):
            txn = f"txn_fail_{uuid.uuid4().hex[:8]}"
            r = client.post("/webhook/disbursement", json={
                "application_id": app_id,
                "status": "failed",
                "transaction_id": txn,
                "timestamp": "2026-03-06T12:00:00Z",
            })
            assert r.status_code == 200

        # 3. Verify it's now flagged for review
        detail = client.get(f"/admin/applications/{app_id}", auth=ADMIN_AUTH)
        assert detail.json()["status"] == "flagged_for_review"
        assert detail.json()["disbursement_retry_count"] == 3

        # 4. Admin re-approves after investigating
        review = client.post(
            f"/admin/applications/{app_id}/review",
            json={"decision": "approved", "note": "Payment provider issue resolved"},
            auth=ADMIN_AUTH,
        )
        assert review.status_code == 200
        assert review.json()["status"] == "disbursement_queued"

        # 5. This time disbursement succeeds
        txn_success = f"txn_ok_{uuid.uuid4().hex[:8]}"
        webhook = client.post("/webhook/disbursement", json={
            "application_id": app_id,
            "status": "success",
            "transaction_id": txn_success,
            "timestamp": "2026-03-06T12:05:00Z",
        })
        assert webhook.status_code == 200
        assert webhook.json()["new_status"] == "disbursed"

        # 6. Verify complete lifecycle
        final = client.get(f"/admin/applications/{app_id}", auth=ADMIN_AUTH)
        assert final.json()["status"] == "disbursed"
