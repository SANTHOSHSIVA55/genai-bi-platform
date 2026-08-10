"""Schema-aware question generation and result-aware follow-up questions.

The BI assistant must never suggest questions that require columns the dataset
does not have. This module inspects the dataset's stored column metadata
(``Dataset.columns_info``) and the current question/result to generate questions
that are grounded in the actual schema and data.
"""
import re


# ─── Column classification ───────────────────────────────────────────────
def _is_id_name(name: str) -> bool:
    low = name.lower().strip()
    return any(kw in low for kw in ("id", "code", "key", "sku", "uuid", "hash"))


_DATE_HINT = ("date", "time", "day", "month", "year", "quarter", "week", "created_at", "timestamp")


def _is_date_like(name: str) -> bool:
    low = name.lower().strip()
    return any(h in low for h in _DATE_HINT)


def classify_columns(cols_meta: list) -> dict:
    """Classify parsed column metadata into semantic groups.

    Returns dict with lists: numeric, categorical, date, text, boolean, id.
    Falls back gracefully to name/sample heuristics when metadata is sparse.
    """
    numeric, categorical, date, text, boolean, id_cols = [], [], [], [], [], []
    for c in cols_meta or []:
        name = str(c.get("name", ""))
        if not name:
            continue
        ctype = str(c.get("type", ""))
        dtype = str(c.get("dtype", ""))
        if ctype == "metric" or dtype in ("float64", "int64", "float32", "int32", "int8", "int16"):
            numeric.append(name)
        elif ctype == "date" or _is_date_like(name):
            date.append(name)
        elif ctype == "categorical":
            categorical.append(name)
        elif ctype == "text":
            text.append(name)
        elif ctype == "id" or _is_id_name(name):
            id_cols.append(name)
        elif dtype == "bool":
            boolean.append(name)
        else:
            text.append(name)

    # If metadata is missing, infer from names/samples.
    if not (numeric or categorical or date or text or boolean):
        for c in cols_meta or []:
            name = str(c.get("name", ""))
            dtype = str(c.get("dtype", ""))
            if _is_id_name(name):
                id_cols.append(name)
            elif _is_date_like(name):
                date.append(name)
            elif dtype in ("float64", "int64", "float32", "int32"):
                numeric.append(name)
            else:
                samples = c.get("sample_values") or []
                ratio = 0
                total = int(c.get("non_null", 0) or 0) + int(c.get("missing", 0) or 0) or 1
                nunique = int(c.get("unique", 0) or 0)
                if total > 0:
                    ratio = nunique / total
                if ratio and ratio < 0.3:
                    categorical.append(name)
                else:
                    text.append(name)

    return {
        "numeric": numeric,
        "categorical": categorical,
        "date": date,
        "text": text,
        "boolean": boolean,
        "id": id_cols,
    }


# ─── Primary column selection ────────────────────────────────────────────
def _preferred_metric(numeric: list) -> str:
    prefer = ("amount", "total", "spend", "price", "revenue", "cost", "sum", "sales", "value")
    for c in numeric:
        low = c.lower()
        if any(p in low for p in prefer):
            return c
    return numeric[0] if numeric else ""


def _preferred_category(categorical: list) -> str:
    prefer = ("category", "type", "group", "segment", "department", "class", "region", "status")
    for c in categorical:
        low = c.lower()
        if any(p in low for p in prefer):
            return c
    return categorical[0] if categorical else ""


def _top_values(cols_meta: list, col_name: str) -> list:
    for c in cols_meta or []:
        if c.get("name") == col_name:
            tv = c.get("top_values") or {}
            if tv:
                return sorted(tv, key=lambda k: tv[k], reverse=True)
    return []


# ─── Quick questions (schema-aware) ───────────────────────────────────────
def generate_quick_questions(cols_meta: list) -> dict:
    """Generate grouped quick questions that are grounded in the dataset schema."""
    groups = classify_columns(cols_meta)
    num = groups["numeric"]
    cat = groups["categorical"]
    date = groups["date"]
    text = groups["text"]

    metric = _preferred_metric(num)
    dimension = _preferred_category(cat)
    top_cat_vals = _top_values(cols_meta, dimension) if dimension else []
    labels = {"numeric": num, "categorical": cat, "date": date, "text": text}

    overview, category, insights = [], [], []

    # Overview
    if metric:
        overview.append(f"What is the total {metric}?")
        overview.append(f"What is the average {metric}?")
        overview.append(f"What is the highest {metric}?")
    if num or cat:
        overview.append("How many records are there in total?")

    # Category analysis
    if metric and dimension:
        category.append(f"Which {dimension} has the highest {metric}?")
        category.append(f"Show {metric} by {dimension}.")
        category.append(f"Compare {metric} across {dimension}.")
        if top_cat_vals:
            category.append(f"What percentage of total {metric} is {top_cat_vals[0]}?")
    elif cat:
        category.append(f"How many records are there per {dimension or cat[0]}?")

    # Insights / deep dives
    if metric:
        insights.append(f"What are the top 5 records by {metric}?")
    if metric and dimension:
        insights.append(f"Which {dimension} contributes the most to {metric}?")
        insights.append(f"Give me 5 key insights.")
        insights.append(f"How do the top {dimension} compare with the lowest?")
    if date:
        insights.append(f"Show {metric or 'metrics'} over time.")
        insights.append(f"Which period had the highest {metric or 'activity'}?")
    if text and not insights:
        insights.append(f"What are the most common values in {text[0]}?")

    return {
        "overview": overview[:4],
        "category": category[:4],
        "insights": insights[:4],
        "_groups": labels,
    }


# ─── Result-aware follow-ups ──────────────────────────────────────────────
def _normalized(q: str) -> str:
    return re.sub(r"[^a-z0-9]", "", q.lower())


def _current_theme(question: str) -> str:
    q = question.lower()
    if any(w in q for w in ("trend", "over time", "monthly", "weekly", "daily", "yearly", "timeline")):
        return "trend"
    if any(w in q for w in ("top ", "top5", "top 5", "top 10", "bottom", "rank", "best", "worst", "highest", "lowest")):
        return "ranking"
    if any(w in q for w in ("compare", "comparison", "across", "vs", "versus")):
        return "comparison"
    if any(w in q for w in ("average", "avg", "mean")):
        return "average"
    if any(w in q for w in ("how many", "total number", "number of", "count of", "how much")):
        return "aggregate"
    if any(w in q for w in ("percentage", "percent", "share", "proportion", "%")):
        return "share"
    return "general"


def generate_follow_ups(question: str, cols_meta: list) -> list:
    """Generate follow-up questions that depend on the current question AND the
    dataset schema, never on invented columns."""
    groups = classify_columns(cols_meta)
    num = groups["numeric"]
    cat = groups["categorical"]
    date = groups["date"]

    metric = _preferred_metric(num)
    dimension = _preferred_category(cat)
    top_vals = _top_values(cols_meta, dimension) if dimension else []
    theme = _current_theme(question)
    base = _normalized(question)

    candidates: list = []

    def add(q: str) -> None:
        if q and _normalized(q) != base and q not in candidates:
            candidates.append(q)

    if theme == "trend":
        if metric and date:
            add(f"Show {metric} by month.")
            add(f"Which period had the highest {metric}?")
        add(f"Show {metric or 'metrics'} by {dimension}." if dimension else f"Show {metric or 'all metrics'} over time.")
        add(f"What is the total {metric}?" if metric else "What are the total records?")
    elif theme == "ranking":
        if metric and dimension:
            add(f"What percentage of total {metric} does the top {dimension} represent?")
            add(f"Show all {dimension} ranked by {metric}.")
            add(f"How does the top {dimension} compare with the second-highest?")
            add(f"What is the average {metric} across all {dimension}?")
        else:
            add(f"Show {metric or 'metrics'} distribution.")
            add(f"What is the total {metric}?" if metric else "How many records are there?")
    elif theme == "comparison":
        if metric and dimension:
            add(f"What share of total {metric} does each {dimension} represent?")
            add(f"Rank all {dimension} by {metric}.")
            add(f"What is the average {metric} overall?")
            add(f"Which {dimension} has the lowest {metric}?")
        else:
            add(f"Show {metric or 'metrics'} by {dimension or cat[0] if cat else 'category'}.")
    elif theme == "average":
        if metric and dimension:
            add(f"How does the average {metric} vary by {dimension}?")
            add(f"What is the highest {metric}?")
            add(f"How many records are there in total?")
        else:
            add(f"What is the highest {metric}?" if metric else "What is the total record count?")
            add(f"Show {metric or 'metrics'} distribution." if metric else "How many records are there?")
    elif theme in ("aggregate", "share"):
        if metric and dimension:
            add(f"Which {dimension} has the highest {metric}?")
            add(f"Show {metric} by {dimension}.")
            add(f"What are the top 5 records by {metric}?")
            if top_vals:
                add(f"What percentage of total {metric} is {top_vals[0]}?")
        elif metric:
            add(f"Show {metric} by {dimension or (cat[0] if cat else '')}." if (dimension or cat) else f"Show {metric} records.")
            add(f"What is the highest {metric}?")
            add("How many records are there in total?")
        else:
            add("What are the most common records in this dataset?")
    else:
        # general theme -> schema-aware overview questions
        if metric:
            add(f"What is the total {metric}?")
        if metric and dimension:
            add(f"Show {metric} by {dimension}.")
            add(f"What are the top 5 records by {metric}?")
        if date:
            add(f"Show {metric or 'metrics'} over time.")
        if not candidates:
            add("What data columns are available for analysis?")

    # Never suggest a trend follow-up unless the schema has date capability.
    filtered = [q for q in candidates if not ("trend" in q.lower() or "over time" in q.lower() or "period" in q.lower()) or bool(date)]
    return filtered[:5]


def generate_guidance_questions(cols_meta: list) -> list:
    """Fallback suggestion set for vague questions."""
    qg = generate_quick_questions(cols_meta)
    out = qg["overview"] + qg["category"] + qg["insights"]
    return out[:5]
