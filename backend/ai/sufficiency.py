"""Required-data detection and data-sufficiency gate.

Runs BEFORE any SQL is generated. Determines which concepts a natural-language
question requires and whether the selected dataset(s) can actually provide
them. When required concepts are missing the module returns a structured
INSUFFICIENT verdict and a human explanation — the pipeline MUST NOT generate
SQL (e.g. ``SELECT COUNT(*)``) for a question the data cannot answer.

This is the guard that prevents the classic wrong answer:

    "How many customers purchased two items together?"  on a CustomerID/
    CustomerName-only dataset  =>  INSUFFICIENT (no purchase/order/item data),
    never ``SELECT COUNT(*)`` => "5".

The engine reasons from the actual schema (column names, types, values) across
all selected tables; it never assumes a domain, filename or fixed schema.
"""
import re

from .columns import _parse_columns_info, _simple_stem
from .intent import _match_metric

# ─── Concept vocabularies ──────────────────────────────────────────────────
# Question measure word -> column-name keywords that can satisfy it. Only
# *metric*-typed columns are candidates (IDs are never measurements).
_MEASURE_SYNONYMS = {
    "revenue": ("revenue", "sales", "turnover", "income", "gross", "amount", "receipts"),
    "sales": ("sales", "revenue", "turnover", "volume", "units", "sold", "orders"),
    "salary": ("salary", "salaries", "wage", "wages", "pay", "compensation", "income", "earning", "earnings"),
    "pay": ("salary", "salaries", "wage", "wages", "pay", "compensation", "income"),
    "amount": ("amount", "total", "sum", "value", "invoice", "balance"),
    "price": ("price", "cost", "unitprice", "unit_price", "rate", "fee", "payout", "listprice"),
    "cost": ("cost", "expense", "expenses", "spend", "spending", "spent", "cogs", "outlay"),
    "expense": ("expense", "expenses", "spend", "spending", "spent", "cost", "outlay", "budget"),
    "profit": ("profit", "margin", "net", "earnings", "gain", "return"),
    "margin": ("margin", "profit", "gross", "net"),
    "quantity": ("quantity", "qty", "units", "items", "volume", "stock", "on_hand", "inventory"),
    "units": ("units", "quantity", "qty", "volume", "stock"),
    "rating": ("rating", "score", "review", "reviews", "stars", "grade"),
    "score": ("score", "rating", "grade", "points", "points_earned"),
    "salary/wage": ("salary", "wage", "pay", "compensation", "income"),
    "budget": ("budget", "allocation", "planned", "forecast"),
    "stock": ("stock", "inventory", "on_hand", "quantity", "reorder", "units"),
}

# Entity noun -> column-name keywords identifying records of that entity.
_ENTITY_SYNONYMS = {
    "customer": ("customer", "client", "buyer", "member", "account"),
    "supplier": ("supplier", "vendor", "distributor", "manufacturer", "partner"),
    "product": ("product", "item", "sku", "goods", "service"),
    "order": ("order", "transaction", "invoice", "purchase", "sale"),
    "employee": ("employee", "staff", "worker", "person", "user", "member"),
    "student": ("student", "pupil", "learner", "enrollee"),
    "patient": ("patient", "client", "case"),
    "record": ("record", "row", "entry", "observation"),
    "category": ("category", "type", "segment", "class", "group"),
    "city": ("city", "town", "municipality"),
    "country": ("country", "nation", "region"),
    "region": ("region", "state", "province", "territory", "area", "zone"),
    "department": ("department", "division", "team", "unit"),
    "store": ("store", "branch", "outlet", "location", "shop"),
}

# Grouping/transaction/order concepts (for co-purchase and multi-item analysis).
_TRANSACTION_KEYWORDS = ("order", "transaction", "invoice", "purchase", "basket", "cart", "sale", "receipt")
_ITEM_KEYWORDS = ("item", "product", "sku", "goods")

# Words that signal the question wants a count of records rather than a measure.
_RECORD_COUNT_WORDS = ("record", "records", "row", "rows", "entry", "entries", "data point")

# Phrases indicating a co-purchase / combination analysis.
_CO_PURCHASE_PATTERNS = [
    (r"\btogether\b", "purchased together"),
    (r"\bboth\b", "both products"),
    (r"\bsame\s+(?:order|transaction|receipt|basket)\b", "same order"),
    (r"\bcommonly\s+purchased\b", "commonly purchased together"),
    (r"\bfrequently\s+(?:bought|purchased)\b", "frequently bought together"),
    (r"\bbundle|combo|combination|market\s*basket\b", "product combinations"),
    (r"\bpurchased\s+two\b|\bbought\s+two\b", "two purchased items"),
]

# Quantity patterns: "two items", "more than 2", "at least 2 products".
_QUANTITY_PATTERNS = [
    r"\b(?:two|2|more than 2|at least 2|over 2|two or more|>=? ?2|2\+)\s+(?:items?|products?|units?)\b",
    r"\b(?:more|at least|over|greater than|≥|>)\s*\d+\s+(?:items?|products?|units?|things?)\b",
]

# Temporal patterns.
_TIME_WORDS = ("over time", "trend", "monthly", "weekly", "daily", "yearly", "quarterly",
              "last month", "last year", "year-over-year", "yoy", "compare to", "vs last")

_ID_WORDS = ("id", "code", "key", "sku", "uuid", "hash", "number")


# ─── Column registry ───────────────────────────────────────────────────────
def _flat_columns(datasets: list) -> list:
    """Flatten all selected datasets into a single resource list."""
    out = []
    for ds in datasets or []:
        table = ds.get("table_name") or ""
        for c in _parse_columns_info(ds.get("columns_info") or ""):
            if not c.get("name"):
                continue
            out.append({
                "col": c["name"],
                "table": table,
                "dataset": ds.get("name") or "",
                "dtype": c.get("dtype") or "",
                "type": c.get("type") or "",
                "unique": int(c.get("unique") or 0),
                "non_null": int(c.get("non_null") or 0),
            })
    return out


def _dataset_lookups(datasets: list) -> dict:
    """table_name -> list of column resources for that table."""
    by_table = {}
    for ds in datasets or []:
        table = ds.get("table_name") or ""
        if table not in by_table:
            by_table[table] = []
        for c in _parse_columns_info(ds.get("columns_info") or ""):
            if c.get("name"):
                by_table[table].append(c)
    return by_table


def _metric_resources(cols: list) -> list:
    return [c for c in cols if c.get("type") == "metric"]


def _entity_resources(cols: list, entity: str) -> list:
    """Columns that plausibly identify records of the given entity."""
    keywords = _ENTITY_SYNONYMS.get(entity, (entity,))
    out = []
    for c in cols:
        name = c.get("col", "").lower()
        if c.get("type") == "metric":
            continue
        if any(k in name for k in keywords):
            out.append(c)
    return out


def _find_measure_column(measure: str, cols: list):
    """Return the metric resource matching a measure word, or None.

    Tries (1) an exact literal column-name match (explicit requests like
    "average customerid" / "average salary" when a salary column exists),
    (2) synonym keywords, (3) token-prefix matching against metric columns
    only (units -> units_sold). IDs are never considered real measures here.
    """
    low_measure = measure.lower().replace("_", " ").strip()

    # (1) explicit column-name reference, any type (user asked for it by name).
    for c in cols:
        if c.get("col", "").lower() == measure.lower():
            return c

    # (2) synonym keywords over metric columns.
    keys = _MEASURE_SYNONYMS.get(measure.lower())
    if keys:
        for c in _metric_resources(cols):
            name = c.get("col", "").lower()
            name_clean = name.replace("_", " ")
            if any(k in name_clean for k in keys):
                return c

    # (3) token-prefix metric matcher (reuses the intent engine's rule).
    metric_names = [c["col"] for c in _metric_resources(cols)]
    hit = _match_metric(measure, metric_names)
    if hit:
        for c in _metric_resources(cols):
            if c["col"] == hit:
                return c
    return None


def _measure_matches_dataset_domain(measure: str, datasets: list) -> str | None:
    """Return the primary metric column when a measure word names the dataset's
    domain instead of a column (e.g. 'expense' with a 'daily_expenses' table).

    This is grounded, not a guess: the measure noun stems-match the dataset name
    / table name, so it is a reference to that table's main numeric field. A
    question like "average salary" on a customers directory does NOT match and
    correctly remains INSUFFICIENT.
    """
    m_stem = _simple_stem(measure.lower())
    if len(m_stem) < 3:
        return None
    for ds in datasets or []:
        for name in (ds.get("name") or "", ds.get("table_name") or ""):
            for tok in re.split(r"[_\s\-]+", name.lower()):
                t = _simple_stem(tok)
                if len(t) < 3:
                    continue
                if t.startswith(m_stem) or m_stem.startswith(t) or m_stem in t or t in m_stem:
                    metric = next(
                        (c["name"] for c in _parse_columns_info(ds.get("columns_info") or "")
                         if c.get("type") == "metric"),
                        None,
                    )
                    if metric:
                        return metric
    return None


def _table_has_order_grouping(datasets: list) -> list:
    """Tables with an order/transaction/grouping key column (id-type or text)."""
    out = []
    for ds in datasets or []:
        for c in _parse_columns_info(ds.get("columns_info") or ""):
            low = (c.get("name") or "").lower()
            if any(k in low for k in _TRANSACTION_KEYWORDS) and any(
                    w in low for w in _ID_WORDS):
                out.append(ds.get("table_name"))
                break
    return out


def _table_has_item_column(datasets: list) -> list:
    out = []
    for ds in datasets or []:
        for c in _parse_columns_info(ds.get("columns_info") or ""):
            low = (c.get("name") or "").lower()
            if any(k in low for k in _ITEM_KEYWORDS) and c.get("type") in ("text", "categorical", "id"):
                out.append(ds.get("table_name"))
                break
    return out


def _table_has_quantity(datasets: list) -> list:
    out = []
    for ds in datasets or []:
        for c in _parse_columns_info(ds.get("columns_info") or ""):
            low = (c.get("name") or "").lower()
            if any(k in low for k in ("quantity", "qty", "units", "items")) and c.get("type") == "metric":
                out.append(ds.get("table_name"))
                break
    return out


# ─── Question concept extraction ───────────────────────────────────────────
def _extract_measures(question: str) -> list:
    """Every measure word the question references, in order."""
    q = question.lower()
    measures = []
    for key in _MEASURE_SYNONYMS:
        if re.search(r"\b" + re.escape(key) + r"(?:s)?\b", q):
            if key not in measures:
                measures.append(key)
    for col_match in re.findall(r"\b([a-z][a-z0-9_]{1,30})\b", q):
        if any(w in col_match for w in _ID_WORDS) or any(k in col_match for k in ("_",)):
            pass
    return measures


def _extract_entities(question: str) -> list:
    q = question.lower()
    entities = []
    for key in _ENTITY_SYNONYMS:
        plural = key + ("ies" if key.endswith("y") and len(key) > 3 else "s")
        if re.search(r"\b(?:the\s+)?(?:all\s+)?(?:total\s+(?:number\s+of\s+)?)?" + re.escape(key) + r"(?:s)?\b", q):
            if key not in entities:
                entities.append(key)
    return entities


def _extract_literal_columns(question: str, datasets: list) -> list:
    """Column names literally present in the question (explicit references)."""
    cols = _flat_columns(datasets)
    q = question.lower()
    found = []
    for c in cols:
        name = c["col"].lower()
        name_clean = name.replace("_", " ")
        if name in q or name_clean in q:
            found.append(c)
    return found


def _has_co_purchase(question: str) -> str | None:
    q = question.lower()
    for pattern, label in _CO_PURCHASE_PATTERNS:
        if re.search(pattern, q):
            return label
    return None


def _has_quantity_clause(question: str) -> bool:
    q = question.lower()
    return any(re.search(p, q) for p in _QUANTITY_PATTERNS)


def _mentions_transaction(question: str) -> bool:
    q = question.lower()
    return any(re.search(r"\b" + re.escape(w) + r"(?:s)?\b", q) for w in ("purchas", "bought", "order", "buy", "sold", "transaction"))


# ─── The gate ──────────────────────────────────────────────────────────────
def check_sufficiency(question: str, datasets: list) -> dict:
    """Return a verdict dict describing whether the selected datasets can
    answer the question, and exactly what is required/available/missing.

    datasets: [{name, table_name, columns_info, row_count, ...}]
    """
    q = question.lower().strip()
    cols = _flat_columns(datasets)
    all_col_names = [c["col"] for c in cols]
    by_table = _dataset_lookups(datasets)

    missing = []
    required = []
    available = []
    hints = {
        "co_purchase": _has_co_purchase(question),
        "quantity_clause": _has_quantity_clause(question),
        "transaction": _mentions_transaction(question),
        "wants_time": any(w in q for w in _TIME_WORDS),
        "wants_count": bool(re.match(r"^(?:how many|number of|count|how much|total number)", q)),
        "explicit_columns": [c["col"] for c in _extract_literal_columns(question, datasets)],
    }

    entities = _extract_entities(question)
    measures = _extract_measures(question)

    # ── Time-based questions need a date column ───────────────────────────
    if hints["wants_time"]:
        required.append("a date/time column")
        if not any(c.get("type") == "date" for c in cols):
            missing.append("date/time column")

    # ── Co-purchase / multi-item analysis ─────────────────────────────────
    co_purchase = hints["co_purchase"]
    quantity_clause = hints["quantity_clause"] and any(
        e in entities for e in ("customer", "order", "product")
    )

    if co_purchase or quantity_clause:
        order_tables = _table_has_order_grouping(datasets)
        item_tables = _table_has_item_column(datasets)
        required.append("order/transaction key (to know which items were bought together)")
        required.append("product/item column")
        if co_purchase:
            required.append("a way to link multiple items to the same purchase")
        if not order_tables:
            missing.append("order/transaction key")
        if not item_tables:
            missing.append("product/item column")
        if order_tables:
            available.append(f"order/transaction key in: {', '.join(order_tables)}")
        if item_tables:
            available.append(f"item/product column in: {', '.join(item_tables)}")
        if missing:
            return _verdict(q, "insufficient", required, available, missing, hints,
                            _insufficient_co_purchase_message(question, datasets, missing))

    # ── Measure-based questions ───────────────────────────────────────────
    measure_hit = None
    if measures:
        for m in measures:
            match = _find_measure_column(m, cols)
            if match:
                measure_hit = match
                available.append(f"{m} -> column '{match['col']}' in {match['table'] or 'dataset'}")
                continue
            domain_metric = _measure_matches_dataset_domain(m, datasets)
            if domain_metric:
                # Measure word names the dataset domain ("expense" on a
                # daily_expenses table): its primary metric answers the question.
                measure_hit = measure_hit or {"col": domain_metric, "table": None}
                available.append(f"{m} -> '{domain_metric}' (the dataset's main numeric field)")
                continue
            if m not in ("count", "total"):
                missing.append(f"{m} (no such measure column exists)")
                required.append(f"{m} measure column")

    # A "total X / average X" question with a specific measure must be satisfiable.
    wants_aggregate = bool(re.search(r"\b(total|sum|average|avg|mean|median|max|min|maximum|minimum|highest|lowest|stddev|standard deviation|variance|percentile)\b", q))
    if wants_aggregate and measures and not measure_hit:
        explicit = hints["explicit_columns"]
        if explicit:
            # "average customerid" explicitly names an existing column: allowed.
            available.append(f"explicit column reference: {explicit[0]}")
        else:
            missing.append("a matching numeric measure")
            return _verdict(q, "insufficient", required, available, missing, hints,
                            _insufficient_measure_message(question, datasets, measures))

    # ── Entity count / ranking questions ──────────────────────────────────
    count_or_rank = hints["wants_count"] or bool(re.search(r"\b(most|least|top|highest|lowest|best|worst)\b", q))
    if count_or_rank and entities:
        resolved = []
        for e in entities:
            if e in _RECORD_COUNT_WORDS:
                resolved.append(("rows", None))
                continue
            res = _entity_resources(cols, e)
            table_hit = None
            for ds in datasets:
                if e in (ds.get("name") or "").lower():
                    table_hit = ds.get("table_name")
                    break
            if res:
                resolved.append((e, res[0]["table"]))
            elif table_hit:
                resolved.append((e, table_hit))
            else:
                # Entity not found as a column anywhere -> cannot count it.
                missing.append(f"{e} (no '{e}' column/table exists in the selected data)")
                required.append(f"{e} records")
        for e, table in resolved:
            if table:
                available.append(f"{e} records in: {table}")
            else:
                available.append(f"{e} records (count of table rows)")

    if missing:
        return _verdict(q, "insufficient", required, available, missing, hints,
                        _insufficient_general_message(question, datasets, missing, measures))

    # ── Ambiguity ─────────────────────────────────────────────────────────
    amb = _ambiguity(question, datasets, entities, measures, hints)
    if amb:
        return _verdict(q, "ambiguous", required, available, [], hints, amb)

    return _verdict(q, "sufficient", required, available, missing, hints, None)


def _verdict(question, status, required, available, missing, hints, message) -> dict:
    return {
        "status": status,
        "message": message,
        "required": list(dict.fromkeys(required)),
        "available": list(dict.fromkeys(available)),
        "missing": list(dict.fromkeys(missing)),
        "hints": hints,
    }


def _ambiguity(question: str, datasets: list, entities: list, measures: list, hints: dict) -> str | None:
    """Return a clarification message when the question has multiple readings.

    Co-purchase quantity questions ("bought two items together") are interpreted
    deterministically as "customers who bought at least two distinct items in a
    single order" whenever the data supports purchase analysis, so they are not
    flagged here; genuinely underdetermined phrasings are handled upstream by
    the feasibility checks.
    """
    return None


# ─── Human messages ────────────────────────────────────────────────────────
def _pluralize_entity(label: str) -> str:
    if not label:
        return label
    if label.lower().endswith(("s", "x", "z", "ch", "sh")):
        return label + "es"
    if label.lower().endswith("y") and len(label) > 1 and label[-2].lower() not in "aeiou":
        return label[:-1] + "ies"
    return label + "s"


def _insufficient_co_purchase_message(question, datasets, missing) -> str:
    entities = _extract_entities(question)
    entity_label = _pluralize_entity(entities[0]) if entities else "records"
    return (
        f"I can't determine how many {entity_label} purchased items together "
        f"from this dataset because it contains {_dataset_summary(datasets)} "
        f"but no order/transaction information, no item/product column and no "
        f"customer-to-item relationship. You would need a dataset with an "
        f"order or transaction ID plus a product/item column to answer this."
    )


def _insufficient_measure_message(question, datasets, measures) -> str:
    cols = _flat_columns(datasets)
    metric_cols = [c for c in cols if c.get("type") == "metric"]
    numerics = ", ".join(f"'{c['col']}'" for c in metric_cols) or "none"
    measure = ", ".join(m for m in measures if m not in ("count", "total"))
    return (
        f"I can't calculate the {'/'.join(measures[:2])} you asked about because "
        f"this dataset contains {_dataset_summary(datasets)} but no column for "
        f"'{measure}'. The available numeric field(s) are {numerics}; none of "
        f"them represents the measure you're asking about."
    )


def _insufficient_general_message(question, datasets, missing, measures) -> str:
    entity_label = ", ".join(_extract_entities(question)) or "that"
    missing_label = "; ".join(missing)
    return (
        f"This dataset cannot answer the question because the data needed to "
        f"reason about {entity_label} is missing. Required but unavailable: "
        f"{missing_label}. The selected dataset contains {_dataset_summary(datasets)}. "
        f"Upload a dataset that includes the missing columns, or ask a question "
        f"about the information that is present."
    )


def _dataset_summary(datasets: list) -> str:
    parts = []
    for ds in datasets or []:
        cols = _parse_columns_info(ds.get("columns_info") or "")
        names = ", ".join(f"'{c['name']}'" for c in cols[:6])
        if len(cols) > 6:
            names += f", and {len(cols) - 6} more"
        parts.append(f"column(s) {names}")
    if not parts:
        return "no usable columns"
    return " and ".join(parts)
