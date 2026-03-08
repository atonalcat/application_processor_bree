from config import scoring_config


def score_income_verification(stated: float, documented: float | None) -> dict:
    """Score how well documented income matches stated income.

    Interpretation of '10% tolerance': documented income must be within
    +/- 10% of stated income for full marks. This symmetric interpretation
    guards against both over-reporting (fraud) and under-reporting (errors).

    When documented income is missing entirely, we return a neutral score of 50
    rather than 0 -- missing data represents uncertainty, not a negative signal.
    A mismatch (like Dave Liar) is scored harshly; absence of data is scored
    neutrally and typically routes to manual review via the total score.

    Scoring curve: score = max(0, 100 - (deviation / tolerance) * 25)
      - 0% deviation  -> 100
      - At tolerance   -> 75
      - At 4x tolerance -> 0
    """
    if documented is None:
        return {"raw_score": 50, "reason": "No documented income provided (neutral)"}

    if stated == 0:
        return {"raw_score": 0, "reason": "Stated income is zero"}

    deviation = abs(documented - stated) / stated
    raw_score = max(0.0, 100 - (deviation / scoring_config.income_tolerance) * 25)

    if deviation <= scoring_config.income_tolerance:
        reason = f"Documented income within tolerance ({deviation:.1%} deviation)"
    else:
        reason = f"Income deviation of {deviation:.1%} exceeds {scoring_config.income_tolerance:.0%} tolerance"

    return {"raw_score": round(raw_score, 2), "reason": reason}


def score_income_level(monthly_income: float, loan_amount: float) -> dict:
    """Score whether monthly income is at least 3x the loan amount.

    Binary threshold: income must meet or exceed 3x the loan amount.
    This reflects underwriting practice where the 3x rule is a hard
    qualification gate, not a sliding scale.
    """
    target = 3 * loan_amount

    if target == 0:
        return {"raw_score": 100, "reason": "Zero loan amount"}

    ratio = monthly_income / target

    if ratio >= 1.0:
        return {
            "raw_score": 100,
            "reason": f"Income is {ratio:.2f}x the required 3x loan amount (meets threshold)",
        }

    return {
        "raw_score": 0,
        "reason": f"Income is {ratio:.2f}x the required 3x loan amount (below threshold)",
    }


def score_account_stability(
    ending_balance: float | None,
    has_overdrafts: bool | None,
    has_consistent_deposits: bool | None,
) -> dict:
    """Score account stability based on three sub-factors (~33 points each).

    When a sub-factor's data is missing (null), it receives 50% of its
    possible points -- representing uncertainty rather than a negative signal.
    """
    sub_scores = {}

    if ending_balance is None:
        sub_scores["positive_balance"] = 16.67
    elif ending_balance > 0:
        sub_scores["positive_balance"] = 33.33
    else:
        sub_scores["positive_balance"] = 0

    if has_overdrafts is None:
        sub_scores["no_overdrafts"] = 16.67
    elif not has_overdrafts:
        sub_scores["no_overdrafts"] = 33.33
    else:
        sub_scores["no_overdrafts"] = 0

    if has_consistent_deposits is None:
        sub_scores["consistent_deposits"] = 16.67
    elif has_consistent_deposits:
        sub_scores["consistent_deposits"] = 33.34
    else:
        sub_scores["consistent_deposits"] = 0

    total = sum(sub_scores.values())

    return {
        "raw_score": round(total, 2),
        "reason": f"Sub-scores: {sub_scores}",
    }


def score_employment_status(status: str) -> dict:
    """Score employment status: employed=100, self-employed=50, unemployed=0."""
    scores = {"employed": 100, "self-employed": 50, "unemployed": 0}
    raw_score = scores.get(status, 0)
    return {"raw_score": raw_score, "reason": f"Employment status: {status}"}


def score_debt_to_income(withdrawals: float | None, deposits: float | None) -> dict:
    """Score debt-to-income using withdrawals/deposits as a proxy.

    When bank data is missing, returns a neutral score of 50 (uncertainty).

    Lower ratio is better:
      ratio <= 0.3 -> 100
      ratio >= 1.0 -> 0
      Linear interpolation between.
    """
    if withdrawals is None or deposits is None or deposits == 0:
        return {"raw_score": 50, "reason": "Insufficient bank data (neutral)"}

    ratio = withdrawals / deposits

    if ratio <= 0.3:
        raw_score = 100.0
    elif ratio >= 1.0:
        raw_score = 0.0
    else:
        raw_score = max(0, (1.0 - ratio) / 0.7 * 100)

    return {
        "raw_score": round(raw_score, 2),
        "reason": f"Withdrawal/deposit ratio: {ratio:.2f}",
    }


def calculate_score(application_data: dict) -> dict:
    """Run all scoring factors and return total score + breakdown."""
    iv = score_income_verification(
        application_data["stated_monthly_income"],
        application_data.get("documented_monthly_income"),
    )
    il = score_income_level(
        application_data["stated_monthly_income"],
        application_data["loan_amount"],
    )
    ast = score_account_stability(
        application_data.get("bank_ending_balance"),
        application_data.get("bank_has_overdrafts"),
        application_data.get("bank_has_consistent_deposits"),
    )
    es = score_employment_status(application_data["employment_status"])
    dti = score_debt_to_income(
        application_data.get("monthly_withdrawals"),
        application_data.get("monthly_deposits"),
    )

    weights = {
        "income_verification": scoring_config.income_verification_weight,
        "income_level": scoring_config.income_level_weight,
        "account_stability": scoring_config.account_stability_weight,
        "employment_status": scoring_config.employment_status_weight,
        "debt_to_income": scoring_config.debt_to_income_weight,
    }

    factors = {
        "income_verification": iv,
        "income_level": il,
        "account_stability": ast,
        "employment_status": es,
        "debt_to_income": dti,
    }

    total_score = 0
    for key, factor in factors.items():
        weighted = factor["raw_score"] * weights[key]
        factor["weight"] = weights[key]
        factor["weighted_score"] = round(weighted, 2)
        total_score += weighted

    total_score = round(total_score, 2)

    return {
        "total_score": total_score,
        "breakdown": factors,
    }


def get_decision(score: float) -> str:
    """Map a score to a decision based on configurable thresholds."""
    if score >= scoring_config.auto_approve_threshold:
        return "approved"
    elif score >= scoring_config.manual_review_threshold:
        return "flagged_for_review"
    else:
        return "denied"
