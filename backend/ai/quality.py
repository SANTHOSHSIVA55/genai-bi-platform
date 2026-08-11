"""AI quality scoring for the query pipeline.

Confidence is a human-readable level (High / Medium / Low) derived from the
actual pipeline state — intent detection, schema capability, SQL validity,
execution success and chart choice. A number is never invented: 100% is only
possible when every stage genuinely succeeded.
"""
import re

from .columns import _parse_columns_info, _validate_business_question


def _resolve_level(score: float) -> str:
    if score >= 80:
        return "High"
    if score >= 55:
        return "Medium"
    return "Low"


def generate_ai_quality(question: str, sql: str, chart_type: str, validation_result: dict,
                        data_length: int, sql_success: bool = True, columns_info: str = "",
                        sufficiency_verdict: dict = None, result_verdict: dict = None) -> dict:
    q = question.lower().strip()
    issues = validation_result.get("issues", [])[:]

    # Sufficiency gate: an INSUFFICIENT/AMBIGUOUS verdict means the pipeline must
    # not be presented as a confident success even if a query happened to run.
    suf_status = (sufficiency_verdict or {}).get("status")
    if suf_status == "insufficient":
        issues.append("The uploaded data cannot answer this question; required data is missing.")
    elif suf_status == "ambiguous":
        issues.append("The question is ambiguous; clarification is needed before answering.")

    # Post-execution question<->result check: a semantically wrong answer is a
    # hard failure regardless of SQL validity.
    result_status = (result_verdict or {}).get("status")
    if result_status == "invalid":
        issues.append(result_verdict.get("reason") or "The result does not answer the question.")
    elif result_status == "questionable":
        issues.append((result_verdict or {}).get("reason") or "The result only partially answers the question.")

    cols_meta = _parse_columns_info(columns_info) if columns_info else []
    biz_validation = _validate_business_question(question, cols_meta) if cols_meta else {}
    business_intent = biz_validation.get("business_intent")
    can_answer = biz_validation.get("can_answer", True)
    missing_cap = biz_validation.get("missing_capability")

    intent_detected = bool(
        re.search(r"(how many|total|count|compare|comparison|top|bottom|rank|average|sum|trend|correlation|analyze|overview|summary)", q)
    )

    sql_generated = bool(sql and not sql.startswith("AI_ERROR"))
    sql_validated = validation_result.get("valid", True)

    chart_selected_correctly = chart_type not in ("table",) or data_length > 0
    summary_generated = True
    recommendations_generated = True
    follow_up_generated = True
    sql_executed_successfully = sql_success
    capability_match = can_answer
    visualization_quality = chart_type in ("kpi", "bar", "line", "pie", "area", "donut")

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
    overall_score = round((total_achieved / total_possible) * 100, 1) if total_possible > 0 else 0.0

    reasons = []
    if business_intent and not can_answer:
        missing_label = missing_cap.replace("_", " ").title() if missing_cap else "Requested business domain"
        issues.append(f"{missing_label} analysis cannot be fully performed - required data columns are not available in this dataset.")
        reasons.append(f"dataset cannot fully answer the '{missing_label}' analysis")
        overall_score = min(overall_score, 55.0)
        overall_score = round(overall_score * 0.7, 1)

    if not intent_detected:
        reasons.append("question intent could not be reliably determined")
    if not sql_generated:
        reasons.append("SQL generation failed")
    if sql and not sql_validated:
        reasons.append("generated SQL did not pass validation")
    if not sql_executed_successfully:
        reasons.append("SQL execution failed")
    if result_status in ("invalid", "questionable"):
        reasons.append(result_verdict.get("reason") or "result does not fully answer the question")
        overall_score = min(overall_score, 55.0 if result_status == "questionable" else 30.0)
        overall_score = round(overall_score * (0.6 if result_status == "questionable" else 0.4), 1)
    if suf_status in ("insufficient", "ambiguous"):
        reasons.append("question cannot be fully answered from the uploaded data")
        overall_score = min(overall_score, 40.0)
        overall_score = round(overall_score * 0.5, 1)
    if chart_type == "table" and data_length == 0:
        reasons.append("no rows returned, so no chart was possible")
    if overall_score < 80 and not reasons:
        reasons.append("some pipeline steps did not fully succeed")

    confidence_level = _resolve_level(overall_score)
    if not reasons and confidence_level == "High":
        reasons.append("all pipeline stages completed successfully")

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
        "confidence_level": confidence_level,
        "confidence_reason": "; ".join(reasons[:3]),
        "step_scores": steps,
        "issues": issues,
    }
