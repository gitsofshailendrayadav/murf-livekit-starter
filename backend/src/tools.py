from datetime import datetime


def check_scheme_eligibility(
    scheme_name: str,
    age: int,
    annual_income: float,
    state: str,
    is_student: bool,
) -> dict:
    """
    Check basic eligibility for a financial/government scheme.

    Use this tool when the caller asks whether they may be eligible
    for a scheme and provides the required personal eligibility details.

    This tool uses a local demo eligibility dataset.
    It does not connect to a live government database.

    Args:
        scheme_name: Name of the scheme the caller wants to check.
        age: Age of the caller.
        annual_income: Approximate annual household income in INR.
        state: Indian state of residence.
        is_student: Whether the caller is currently a student.

    Returns:
        A dictionary containing the eligibility result and explanation.
    """

    checked_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    scheme = scheme_name.lower().strip()

    # Local demo rule set
    if "student" in scheme or "education" in scheme:
        if is_student and age >= 18 and annual_income <= 800000:
            return {
                "success": True,
                "eligible": True,
                "scheme": scheme_name,
                "reason": (
                    "Based on the information provided, you meet "
                    "the basic demo eligibility conditions."
                ),
                "checked_at": checked_at,
                "data_source": "Local demo eligibility dataset",
            }

        return {
            "success": True,
            "eligible": False,
            "scheme": scheme_name,
            "reason": (
                "Based on the information provided, you do not meet "
                "the basic demo eligibility conditions."
            ),
            "checked_at": checked_at,
            "data_source": "Local demo eligibility dataset",
        }

    # Unknown scheme
    return {
        "success": False,
        "eligible": None,
        "scheme": scheme_name,
        "reason": (
            "I don't have eligibility rules for this scheme in my "
            "current dataset, so I don't want to guess."
        ),
        "checked_at": checked_at,
        "data_source": "Local demo eligibility dataset",
    }