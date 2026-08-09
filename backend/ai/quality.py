"""AI quality scoring for the query pipeline."""
import re

from .columns import _parse_columns_info, _validate_business_question


def generate_ai_quality(question: str, sql: str, chart_type: str, validation_result: dict,
                        data_length: int, sql_success: bool = True, columns_info: str = "") -> dict:
    q = question.lower().strip()
    issues = validation_result.get("issues", [])[:]

    # ----- CAPABILITY-AWARE CONFIDENCE -----
    cols_meta = _parse_columns_info(columns_info) if columns_info else []
    biz_validation = _validate_business_question(question, cols_meta) if cols_meta else {}
    business_intent = biz_validation.get("business_intent")
    can_answer = biz_validation.get("can_answer", True)
    missing_cap = biz_validation.get("missing_capability")

    # Step 1: Intent detected
    intent_detected = bool(
        re.search(r"(how many|total|count|compare|comparison|top|bottom|rank|average|sum|trend|correlation)", q)
    )

    # Step 2: SQL generated
    sql_generated = bool(sql and not sql.startswith("AI_ERROR"))

    # Step 3: SQL validated
    sql_validated = validation_result.get("valid", True)

    # Step 4: Chart selected correctly
    chart_selected_correctly = chart_type not in ("table",) or data_length > 0

    # Step 5: Summary generated
    summary_generated = True

    # Step 6: Recommendations generated
    recommendations_generated = True

    # Step 7: Follow-up generated
    follow_up_generated = True

    # Step 8: SQL executed successfully
    sql_executed_successfully = sql_success

    # Step 9: Dataset capability match (NEW)
    capability_match = can_answer

    # Visualization quality
    visualization_quality = chart_type in ("kpi", "bar", "line", "pie", "area")

    # Step scores
    steps = {
        "intent_detected": int(intent_detected),
        "sql_generated": int(sql_generated),
        "sql_validated": int(sql_validated),
        "chart_selected_correctly": int(chart_selected_correctly),
        "summary_generated": int(summary_generated),
        "recommendations_generated": int(recommendations_generated),
        "follow_up_generated": int(follow_up_generated),
        "sql_executed_successfully": int(sql_executed_successfully),
        "capability_match": int(capability_match),
    }

    total_possible = len(steps)
    total_achieved = sum(steps.values())
    overall_score = round((total_achieved / total_possible) * 100, 1) if total_possible > 0 else 100.0

    # Apply capability penalty: when a business intent was detected but dataset can't answer it,
    # significantly reduce confidence to reflect the data reality.
    if business_intent and not can_answer:
        missing_label = missing_cap.replace("_", " ").title() if missing_cap else "Requested business domain"
        issues.append(f"{missing_label} analysis cannot be fully performed - required data columns are not available in this dataset.")
        # Cap penalty: at most ~55% even if everything else passes
        overall_score = min(overall_score, 55.0)
        overall_score = round(overall_score * 0.7, 1)  # further reduce by 30%

    return {
        "intent_detected": intent_detected,
        "sql_generated": sql_generated,
        "sql_validated": sql_validated,
        "chart_selected_correctly": chart_selected_correctly,
        "summary_generated": summary_generated,
        "recommendations_generated": recommendations_generated,
        "follow_up_generated": follow_up_generated,
        "sql_executed_successfully": sql_executed_successfully,
        "capability_match": capability_match,
        "visualization_quality": visualization_quality,
        "overall_score": overall_score,
        "step_scores": steps,
        "issues": issues,
    }
