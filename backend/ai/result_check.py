"""Question<->result semantic validation.

Runs AFTER SQL execution as a second net: even when a query is valid SQL and
returns rows, the answer may still be wrong (e.g. ``COUNT(*)`` answering "what
is the average salary?", or a plain count answering a co-purchase question).
Every wrong-answer pattern the pipeline must never show is checked here so the
frontend can surface a low-confidence / failed state instead of presenting a
plausible-looking number.

The sufficiency gate (``ai.sufficiency``) is the primary prevention layer; this
module is the post-execution verification layer.
"""
import re

from .columns import _parse_columns_info
from .semantics import analyze_sql_semantics, infer_semantic_type

_MEASURE_PATTERNS = (
    r"\b(average|avg|mean|median|total|sum|sum of|max|min|highest|lowest|largest|smallest)\b",
    r"total\s+(revenue|sales|amount|salary|profit|cost|value)",
)
_COUNT_PATTERNS = (r"^(how many|number of|count of|total count)",)
_CO_PURCHASE_PATTERNS = (
    r"\b(purchased|bought|bought together|buy together|purchased together|bought together|co-?purchase|together|in the same (order|purchase|transaction))\b",
)
_TIME_PATTERNS = (
    r"\b(over time|trend|by (month|year|quarter|week|day|date)|monthly|yearly|weekly|daily|each month|each year|per (month|year|week|day)|time series)\b",
)
_COMPARE_PATTERNS = (r"\b(compare|comparison|vs\.?|versus|difference between|differ from)\b",)
_PERCENT_PATTERNS = (r"\b(percentage|percent|share of|what %|what pct)\b",)


def _matches(question: str, patterns: tuple) -> bool:
    q = question.lower().strip()
    return any(re.search(p, q) for p in patterns)


def _result_semantics(result_columns: list, result_rows: list,
                      cols_meta: list, sql: str) -> dict:
    """Semantic type per result column."""
    if sql:
        return analyze_sql_semantics(sql, result_columns, cols_meta, result_rows or [])
    return {c: infer_semantic_type(c) for c in (result_columns or [])}


def _only_aggregate_columns(result_columns: list, semantics: dict) -> bool:
    """True when every result column is numeric/aggregate (no dimension)."""
    agg_types = ("count", "currency", "percentage", "number")
    cols = result_columns or []
    return bool(cols) and all(semantics.get(c) in agg_types for c in cols)


def validate_result(question: str, result_columns: list, result_rows: list,
                    cols_meta: list, sql: str = "") -> dict:
    """Check the executed result actually answers the question.

    Returns ``{status: valid|questionable|invalid, issues: [...], notes: [...],
    reason: str}``. ``invalid`` means the answer must NOT be presented as a
    success; ``questionable`` means it can be shown but flagged.
    """
    q = question.lower().strip()
    if not result_columns:
        return {"status": "invalid", "issues": ["no columns returned"],
                "notes": [], "reason": "Query returned no data."}

    semantics = _result_semantics(result_columns, result_rows, cols_meta, sql)
    issues, notes = [], []
    n_rows = len(result_rows or [])

    is_count_question = _matches(q, _COUNT_PATTERNS)
    wants_measure = _matches(q, _MEASURE_PATTERNS)
    wants_co_purchase = _matches(q, _CO_PURCHASE_PATTERNS)
    wants_time = _matches(q, _TIME_PATTERNS)
    wants_compare = _matches(q, _COMPARE_PATTERNS)
    wants_percent = _matches(q, _PERCENT_PATTERNS)

    # 1. Measure question answered with a bare count (critical wrong-answer
    #    pattern: "average salary" -> COUNT(*)). A count is only wrong when it
    #    is the entire result: a grouped breakdown ("total customers by
    #    country") or a result that also carries a real measure column is a
    #    legitimate answer to a measure question.
    if wants_measure and not is_count_question:
        count_cols = [c for c, st in semantics.items() if st == "count"]
        if count_cols and len(count_cols) == len(result_columns or []):
            issues.append(
                f"Question asks for a measure ('{question.strip()}') but the result is a record "
                f"count ({', '.join(count_cols)}). A count is not a valid answer for a measure question."
            )

    # 2. Co-purchase question must return a pair of items, not a single total.
    #    (A count question like "How many customers purchased two items
    #    together?" is legitimately answered by a customer count, so it is
    #    exempt; only pair-listing questions require the item pair columns.)
    if wants_co_purchase and not is_count_question:
        lower_cols = [str(c).lower() for c in result_columns]
        pair_cols = [c for c in lower_cols if c.startswith(("product_a", "item_a", "a.", "b."))]
        if not (any(c.endswith("_a") for c in lower_cols) and any(c.endswith("_b") for c in lower_cols)):
            if _only_aggregate_columns(result_columns, semantics):
                issues.append(
                    "Co-purchase question ('purchased together') must return the pair of items that "
                    "were bought together. A single total/count does not answer it."
                )
            else:
                notes.append("Co-purchase question: result does not expose an explicit item pair.")

    # 3. Time/trend question must have a date dimension in the result.
    if wants_time:
        has_date_col = any(st == "date" for st in semantics.values())
        date_like = any(any(k in str(c).lower() for k in ("date", "month", "year", "week", "day", "time")) for c in result_columns)
        if not (has_date_col or date_like):
            issues.append(
                "Question asks about a trend/over-time change but the result has no date/time "
                "dimension to show the change over time."
            )

    # 4. Comparison question needs at least two comparable values.
    if wants_compare and n_rows < 2 and not any(st in ("currency", "number") for st in list(semantics.values())[:1]):
        notes.append("Comparison question: only one value returned; consider comparing against a baseline.")

    # 5. Percentage question should return a percentage-typed column.
    if wants_percent and n_rows > 0:
        has_pct = any(st == "percentage" for st in semantics.values())
        if not has_pct:
            notes.append("Percentage question: result does not contain an explicit percentage column.")

    # 6. Grouped question with a single row is fine only when the user asked
    #    for the top result; otherwise flag sparseness as a note.
    wants_grouping = any(w in q for w in (" by ", " per ", " each ", "distribution"))
    if wants_grouping and n_rows == 1:
        notes.append("Only one group returned; the grouping may be too granular.")

    if issues:
        status = "invalid"
    elif notes:
        status = "questionable"
    else:
        status = "valid"

    reason = ""
    if status == "invalid":
        reason = issues[0]
    elif status == "questionable":
        reason = notes[0]

    return {"status": status, "issues": issues, "notes": notes, "reason": reason}
