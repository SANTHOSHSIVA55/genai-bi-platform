"""Conversation context resolution for the AI Data Analyst.

Users should be able to drill down without repeating the metric, dimension or
filter from their previous question:

    User: "What is total sales?"      ->  SUM(sales)
    User: "Show me by region"         ->  sales grouped by region
    User: "Which one is worst?"       ->  region with the lowest sales
    User: "Why?"                      ->  grounded comparison view of sales by region

Rewrites are deliberately conservative and fully grounded in the columns that
actually exist in the dataset. When the follow-up cannot be resolved safely the
original question is returned unchanged and the rest of the pipeline (feasibility
gate, sufficiency gate, guidance) handles it honestly.
"""
import re

from .columns import _simple_stem


def _metric_cols(cols_meta):
    return [c.get("name") for c in (cols_meta or []) if c.get("type") == "metric"]


def _cat_cols(cols_meta):
    return [c.get("name") for c in (cols_meta or [])
            if c.get("type") in ("categorical", "text")]


def _find_col_in_phrase(phrase, cols):
    """Match any column name in a phrase (fuzzy, stem-aware)."""
    if not phrase:
        return None
    for w in re.findall(r"[a-z0-9_]+", phrase.lower()):
        stem = _simple_stem(w)
        for c in cols:
            cl = c.lower()
            cl_clean = cl.replace("_", " ")
            c_stem = _simple_stem(cl)
            c_clean_stem = _simple_stem(cl_clean)
            if cl == w or cl_clean == w or c_stem == stem or c_clean_stem == stem:
                return c
            if len(stem) >= 3 and (c_stem.startswith(stem) or stem.startswith(c_stem)):
                return c
    return None


def _previous_metric(previous, cols_meta):
    metrics = _metric_cols(cols_meta)
    if not metrics:
        return None
    q = previous.get("question") or ""
    hit = _find_col_in_phrase(q, metrics)
    if hit:
        return hit
    sql = previous.get("sql") or ""
    for match in re.finditer(r"(SUM|AVG|MIN|MAX|COUNT)\s*\(\s*\"?([A-Za-z0-9_]+)\"?\s*\)",
                             sql, re.IGNORECASE):
        name = match.group(2)
        for c in metrics:
            if c.lower() == name.lower():
                return c
    return metrics[0]


def _previous_dimension(previous, cols_meta):
    cats = _cat_cols(cols_meta)
    if not cats:
        return None
    q = previous.get("question") or ""
    hit = _find_col_in_phrase(q, cats)
    if hit:
        return hit
    sql = previous.get("sql") or ""
    group_match = re.search(r"GROUP\s+BY\s+\"?([A-Za-z0-9_]+)\"?", sql, re.IGNORECASE)
    if group_match:
        name = group_match.group(1)
        for c in cats:
            if c.lower() == name.lower():
                return c
    return cats[0]


def _previous_aggfunc(previous):
    sql = previous.get("sql") or ""
    for func in ("AVG", "COUNT", "MIN", "MAX", "SUM"):
        if re.search(func + r"\s*\(", sql, re.IGNORECASE):
            return func
    return "SUM"


_AGG_WORD = {
    "SUM": "total",
    "AVG": "average",
    "COUNT": "number of",
    "MIN": "minimum",
    "MAX": "maximum",
}

_SUPERLATIVE = {
    "worst": "lowest",
    "best": "highest",
    "lowest": "lowest",
    "highest": "highest",
    "least": "lowest",
    "most": "highest",
    "smallest": "lowest",
    "largest": "highest",
    "bottom": "lowest",
    "top": "highest",
}


def _is_self_contained(question, cols_meta):
    """A question that already names its metric/aggregation is left alone."""
    q = question.lower()
    metrics = _metric_cols(cols_meta)
    if _find_col_in_phrase(q, metrics):
        return True
    for kw in ("total", "average", "avg", "sum", "count", "min ", " max ",
               "maximum", "minimum", "how many", "number of", "median",
               "stddev", "trend", "over time", "monthly", "correlation",
               "compare", "vs ", "versus", "what is the average", "mean "):
        if kw in q:
            return True
    return False


def resolve_followup_question(question: str, previous: dict, cols_meta: list) -> str:
    """Return the effective question, possibly rewritten using conversation
    context. ``previous`` is a compact dict of the last assistant turn with
    ``question``, ``sql``, ``columns`` and ``dataset_id`` keys."""
    q = (question or "").strip()
    if not q or not previous or not cols_meta:
        return q
    ql = q.lower()
    metrics = _metric_cols(cols_meta)
    cats = _cat_cols(cols_meta)

    metric = _previous_metric(previous, cols_meta)
    if not metric:
        return q
    dim = _previous_dimension(previous, cols_meta)
    agg = _previous_aggfunc(previous)
    aggword = _AGG_WORD.get(agg, "total")

    # RULE C — "why ... ?": answer with a grounded comparison view instead of
    # fabricating a cause. Falls back to the original question (guidance path)
    # when there is no prior dimension to compare against. Checked before the
    # self-contained guard so "why did revenue decrease" still resolves.
    if re.match(r"^(?:why|how comes|what happened|what changed)\b", ql) and dim:
        return f"Show {aggword} {metric} by {dim}"

    if _is_self_contained(question, cols_meta):
        return q

    # RULE B — comparative follow-ups: "which is worst?", "which one is best?",
    # "who had the lowest?", "show me the worst".
    superlative = None
    m = re.search(r"\b(?:worst|best|lowest|highest|least|most|smallest|largest|bottom|top)\b", ql)
    if m:
        superlative = _SUPERLATIVE.get(m.group(0))
    if superlative and dim:
        qm = re.match(r"^(?:show|which|who|what)\b", ql)
        if qm or re.match(r"^one\b", ql):
            return f"Which {dim} has the {superlative} {metric}?"

    # RULE D — "top 5" / "bottom 10" without a metric.
    m = re.match(r"^(?:show\s+)?(?:me\s+)?(?:the\s+)?(top|bottom)\s+(\d+)\s*(.*?)$", ql)
    if m:
        order, limit, rest = m.group(1), m.group(2), m.group(3).strip()
        target = dim or (cats[0] if cats else "")
        metric_phrase = metric if rest == "" or _find_col_in_phrase(rest, metrics) else rest
        target_phrase = target or (rest or metric_phrase)
        return f"Show {order} {limit} {target_phrase} by {metric_phrase}"

    # RULE A — implicit grouping: "by region", "show me by region",
    # "break it down by region", "now by region", "group by region".
    group_match = (
        re.match(r"^by\s+(.+)", ql)
        or re.match(r"^(?:per|for each|for every|for\s+each)\s+(.+)", ql)
        or re.match(r"^(?:show|display|give|see|break|group|now|and)\s+(?:me\s+)?(?:it\s+)?(?:down\s+)?(?:by|per|for each)\s+(.+)", ql)
    )
    if group_match:
        dim = _find_col_in_phrase(group_match.group(1), cats) or dim
        if dim:
            return f"Show {aggword} {metric} by {dim}"

    # RULE E — "show me the details / breakdown / full data" -> prior view.
    if re.match(r"^(?:show|display|give|get)\s+(?:me\s+)?(?:the\s+)?(?:full\s+)?(?:details?|breakdown|data|list|records|rows)$", ql) and dim:
        return f"Show {aggword} {metric} by {dim}"

    return q
