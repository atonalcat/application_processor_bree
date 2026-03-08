"""
Webhook Disbursement Simulator

Sends simulated disbursement webhooks to the loan processor API.
Demonstrates success, failure, and replay (idempotency) scenarios.

Usage:
    python scripts/simulate_disbursement.py <application_id> [--scenario success|failure|replay|all]
    python scripts/simulate_disbursement.py <application_id> --scenario all

Defaults to --scenario all if not specified.
"""

import argparse
import sys
import uuid
from datetime import datetime, timezone

import requests

BASE_URL = "http://127.0.0.1:8000"
WEBHOOK_URL = f"{BASE_URL}/webhook/disbursement"


def send_webhook(application_id: str, status: str, transaction_id: str):
    payload = {
        "application_id": application_id,
        "status": status,
        "transaction_id": transaction_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    print(f"\n{'='*60}")
    print(f"Sending {status.upper()} webhook")
    print(f"  application_id: {application_id}")
    print(f"  transaction_id: {transaction_id}")
    print(f"{'='*60}")

    try:
        response = requests.post(WEBHOOK_URL, json=payload)
        print(f"  Status Code: {response.status_code}")
        print(f"  Response: {response.json()}")
        return response
    except requests.exceptions.ConnectionError:
        print("  ERROR: Could not connect to the server. Is it running?")
        sys.exit(1)


def scenario_success(application_id: str):
    print("\n>>> SCENARIO: Successful Disbursement")
    txn_id = f"txn_{uuid.uuid4().hex[:12]}"
    send_webhook(application_id, "success", txn_id)
    return txn_id


def scenario_failure(application_id: str):
    print("\n>>> SCENARIO: Failed Disbursement (triggers auto-retry)")
    txn_id = f"txn_{uuid.uuid4().hex[:12]}"
    send_webhook(application_id, "failed", txn_id)
    return txn_id


def scenario_replay(application_id: str, transaction_id: str):
    print("\n>>> SCENARIO: Webhook Replay (same transaction_id, should be idempotent)")
    send_webhook(application_id, "success", transaction_id)


def scenario_all(application_id: str):
    print("\n" + "#" * 60)
    print("# RUNNING ALL WEBHOOK SCENARIOS")
    print("#" * 60)

    # 1. Failure webhook
    scenario_failure(application_id)

    # 2. Another failure (retry)
    txn_id2 = f"txn_{uuid.uuid4().hex[:12]}"
    print("\n>>> SCENARIO: Second Failure (retry #2)")
    send_webhook(application_id, "failed", txn_id2)

    # 3. Success webhook
    txn_id_success = scenario_success(application_id)

    # 4. Replay the success (idempotency test)
    scenario_replay(application_id, txn_id_success)

    print("\n" + "#" * 60)
    print("# ALL SCENARIOS COMPLETE")
    print("#" * 60)


def main():
    parser = argparse.ArgumentParser(description="Simulate disbursement webhooks")
    parser.add_argument("application_id", help="The application ID to send webhooks for")
    parser.add_argument(
        "--scenario",
        choices=["success", "failure", "replay", "all"],
        default="all",
        help="Which scenario to run (default: all)",
    )
    parser.add_argument(
        "--transaction-id",
        help="Transaction ID to use (required for replay scenario)",
    )

    args = parser.parse_args()

    if args.scenario == "success":
        scenario_success(args.application_id)
    elif args.scenario == "failure":
        scenario_failure(args.application_id)
    elif args.scenario == "replay":
        if not args.transaction_id:
            print("ERROR: --transaction-id is required for replay scenario")
            sys.exit(1)
        scenario_replay(args.application_id, args.transaction_id)
    else:
        scenario_all(args.application_id)


if __name__ == "__main__":
    main()
