"""Semantic analysis of generated SQL result columns.

Every column returned by a query is labelled with a semantic type so numbers are
never formatted blindly:

- ``count``      -> COUNT(...) aggregates and ``*_count`` aliases (never currency)
- ``currency``   -> sums/averages/min/max of monetary dataset columns (₹/$/€ when detected)
- ``percentage`` -> share expressions (``* 100``) and percentage aliases
- ``number``     -> plain numeric values (quantities, ages, ids, scores, ...)
- ``date``       -> date/time columns
- ``text``       -> strings / categories

The parser is deliberately lightweight (regex + top-level tokeniser): the
pipeline only ever deals with single-statement SELECTs with no subqueries, so a
full SQL grammar is not needed. It understands COUNT / SUM / AVG / MIN / MAX,
GROUP BY, ORDER BY aliases, calculated columns, CASE expressions, percentages,
rankings and date aggregations.
"""
import re

# ─── Name semantics ────────────────────────────────────────────────────────
_MONETARY_KEYWORDS = (
    "amount", "revenue", "sales", "price", "cost", "expense", "profit",
    "salary", "income", "spend", "value", "fee", "payout", "budget",
)

# Strongly non-monetary nouns that must NEVER receive currency formatting even
# when a dataset-level currency exists (e.g. a suppliers dataset).
_NON_MONETARY_HINTS = (
    "count", "quantity", "qty", "age", "year", "rank", "percent", "pct",
    "share", "ratio", "score", "index", "units", "number", "weight", "size",
)


def is_monetary_name(name: str) -> bool:
    """True when a column name clearly denotes money."""
    low = name.lower().replace("_", " ")
    return any(k in low for k in _MONETARY_KEYWORDS)


# "count" matched only as a whole word (boundary-separated), so country /
# account / counter / discount never qualify as record counts.
_COUNT_WORD_RE = re.compile(r"(^|[_\-/\s\d])count(s|ed)?($|[_\-/\s\d])")
_COUNT_CAMEL_RE = re.compile(r"[a-z\d_]Count(s|ed)?$")


def is_count_name(name: str) -> bool:
    """True when a column name clearly denotes a record count."""
    low = name.lower()
    if _COUNT_WORD_RE.search(low):
        return True
    if _COUNT_CAMEL_RE.search(name):
        return True
    if low.startswith("unique_") or low.startswith("distinct_"):
        return True
    return low in ("total_records", "num_records", "records", "num", "n")


def is_percentage_name(name: str) -> bool:
    """True when a column name clearly denotes a percentage/ratio value.

    Unambiguous keywords (percent/pct/conversion/completion) always qualify;
    ambiguous ones (rate/margin/ratio/growth/yield/share/proportion) qualify only
    when the name is not monetary (so "share price" stays a currency).
    """
    low = name.lower()
    if any(k in low for k in ("percent", "pct", "conversion", "completion")):
        return True
    if any(k in low for k in ("rate", "margin", "ratio", "growth", "yield", "share", "proportion")):
        return not is_monetary_name(name)
    return False


def infer_semantic_type(name: str) -> str:
    """Name-based fallback when the SQL expression cannot be parsed."""
    if not name:
        return "text"
    if is_count_name(name):
        return "count"
    if is_percentage_name(name):
        return "percentage"
    if is_monetary_name(name):
        return "currency"
    return "number"


# ─── Lightweight SQL SELECT parsing ─────────────────────────────────────────
def _split_top_level(text: str, sep: str = ",") -> list:
    """Split ``text`` on ``sep`` outside quotes and parentheses."""
    parts, buf, depth, in_quote, quote_char = [], [], 0, False, ""
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if in_quote:
            buf.append(ch)
            if ch == quote_char:
                if i + 1 < n and text[i + 1] == quote_char:
                    buf.append(text[i + 1])
                    i += 1
                else:
                    in_quote = False
        elif ch in ("'", '"'):
            in_quote, quote_char = True, ch
            buf.append(ch)
        elif ch == "(":
            depth += 1
            buf.append(ch)
        elif ch == ")":
            depth = max(0, depth - 1)
            buf.append(ch)
        elif ch == sep and depth == 0:
            parts.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
        i += 1
    parts.append("".join(buf).strip())
    return [p for p in parts if p]


def _extract_select_clause(sql: str) -> str:
    """Return the text between SELECT and the first top-level FROM."""
    m = re.search(r"\bSELECT\b", sql, re.IGNORECASE)
    if not m:
        return ""
    start = m.end()
    depth, in_quote, quote_char = 0, False, ""
    i, n = start, len(sql)
    while i < n:
        if not in_quote and depth == 0 and i > start:
            fm = re.match(r"\bFROM\b", sql[i:], re.IGNORECASE)
            if fm:
                return sql[start:i].strip()
        ch = sql[i]
        if in_quote:
            if ch == quote_char:
                if i + 1 < n and sql[i + 1] == quote_char:
                    i += 2
                    continue
                in_quote = False
        elif ch in ("'", '"'):
            in_quote, quote_char = True, ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        i += 1
    return sql[start:].strip()


def _extract_select_items(sql: str) -> list:
    """Return the individual SELECT-list expressions, in order."""
    clause = _extract_select_clause(sql)
    if not clause:
        return []
    return _split_top_level(clause)


def _alias_for_item(item: str):
    """Return the alias declared by a SELECT item, or None.

    Handles ``expr AS alias``, ``expr AS "alias"`` and the implicit alias of a
    bare column reference (``"city"`` aliases to ``city``).
    """
    m = re.search(r"\bAS\s+[\"']?([A-Za-z_][A-Za-z0-9_]*)[\"']?\s*$", item, re.IGNORECASE)
    if m:
        return m.group(1)
    stripped = item.strip()
    m = re.match(r'^"([A-Za-z_][A-Za-z0-9_]*)"$', stripped)
    if m:
        return m.group(1)
    m = re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", stripped)
    if m:
        return stripped
    return None


def select_aliases(sql: str) -> set:
    """All aliases defined in the SELECT clause (lowercased).

    Includes implicit aliases (a bare ``"city"`` reference aliases to ``city``)
    and explicit ``AS`` aliases. GROUP BY / ORDER BY references may use either.
    """
    aliases = set()
    for item in _extract_select_items(sql):
        a = _alias_for_item(item)
        if a:
            aliases.add(a.lower())
    return aliases


def declared_aliases(sql: str) -> set:
    """Only aliases explicitly declared with ``AS`` (lowercased).

    These are derived names (``COUNT(*) AS supplier_count``) that must NEVER be
    validated as if they were physical dataset columns. Bare SELECT references
    (``"city"``) are NOT included: they must still exist as real columns.
    """
    aliases = set()
    for item in _extract_select_items(sql):
        m = re.search(r"\bAS\s+[\"']?([A-Za-z_][A-Za-z0-9_]*)[\"']?\s*$", item, re.IGNORECASE)
        if m:
            aliases.add(m.group(1).lower())
    return aliases


# ─── Semantic typing of expressions ─────────────────────────────────────────
_FUNC_WRAPPERS = ("ROUND", "COALESCE", "NULLIF", "ABS", "CAST", "CEIL", "FLOOR")


def _unwrap(expr: str) -> str:
    """Peel off benign numeric wrappers so the inner semantics are visible."""
    prev = None
    while prev != expr:
        prev = expr
        m = re.match(r"^([A-Za-z_]+)\s*\((.*)\)$", expr, re.DOTALL)
        if m and m.group(1).upper() in _FUNC_WRAPPERS:
            expr = m.group(2)
    return expr


def _meta_currency(col: str, col_meta_map: dict) -> bool:
    meta = col_meta_map.get(col)
    if meta and str(meta.get("type") or "") == "metric":
        return is_monetary_name(col)
    return is_monetary_name(col)


def _expr_semantic_type(item: str, col_meta_map: dict) -> str:
    """Semantic type of a single SELECT expression."""
    alias = _alias_for_item(item)
    expr = _unwrap(item)

    e_upper = expr.upper()
    if re.search(r"\bCOUNT\s*\(", e_upper):
        return "count"
    if re.search(r"\*\s*100", expr):
        return "percentage"
    if alias and is_percentage_name(alias):
        return "percentage"

    # Aggregate function over a column / CASE expression.
    m = re.search(r"\b(SUM|AVG|MIN|MAX)\s*\((.*)\)\s*$", expr, re.IGNORECASE | re.DOTALL)
    if m:
        inner = m.group(2).strip()
        col = inner.strip().strip('"').strip("'")
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", col):
            if _meta_currency(col, col_meta_map):
                return "currency"
            if is_count_name(col):
                return "count"
            return "number"
        for cname in re.findall(r'"([A-Za-z_][A-Za-z0-9_]*)"', inner):
            if _meta_currency(cname, col_meta_map):
                return "currency"
        return "number"

    # Raw quoted column.
    m = re.match(r'^"([A-Za-z_][A-Za-z0-9_]*)"$', expr.strip())
    if m:
        col = m.group(1)
        meta = col_meta_map.get(col)
        if meta:
            ctype = str(meta.get("type") or "")
            if ctype == "date":
                return "date"
            if ctype in ("categorical", "text", "id"):
                return "text"
            if ctype == "metric":
                return "currency" if is_monetary_name(col) else "number"
        return "currency" if is_monetary_name(col) else "number"

    return "number"


def analyze_sql_semantics(sql: str, result_columns: list, cols_meta: list,
                          data_sample: list = None) -> dict:
    """Map each result column to its semantic type.

    SELECT-list expressions align positionally with ``result_columns`` (SQLAlchemy
    returns keys in SELECT order). Columns that cannot be parsed are inferred from
    their name and, for strings, from the returned data.
    """
    col_meta_map = {c.get("name"): c for c in (cols_meta or []) if c.get("name")}
    items = _extract_select_items(sql)
    per_item = [_expr_semantic_type(it, col_meta_map) for it in items]

    semantics = {}
    data = data_sample or []
    for i, col in enumerate(result_columns or []):
        st = per_item[i] if i < len(per_item) else None
        if not st or st == "number":
            name_st = infer_semantic_type(col)
            if st == "number" and name_st != "number":
                st = name_st
            elif not st:
                st = name_st
        if st == "number":
            vals = [r.get(col) for r in data if r.get(col) is not None]
            if vals and all(isinstance(v, (int, float)) for v in vals):
                st = "count" if all(v == int(v) for v in vals) and is_count_name(col) else "number"
        semantics[col] = st or "number"
    return semantics


# ─── Semantic-aware formatting ──────────────────────────────────────────────
def format_number(value, currency=None) -> str:
    """Human-friendly number: no decimals for whole numbers, 2 otherwise."""
    if value is None:
        return ""
    try:
        fv = float(value)
    except (TypeError, ValueError):
        return str(value)
    if fv == int(fv) and abs(fv) < 1e15:
        body = f"{int(fv):,}"
    else:
        body = f"{fv:,.2f}"
    return f"{currency}{body}" if currency else body


def format_semantic_value(value, semantic: str, currency=None) -> str:
    """Format a value according to its semantic type.

    COUNT results are always whole integers and NEVER receive a currency symbol;
    only ``currency``-typed columns are formatted as money.
    """
    if value is None:
        return ""
    try:
        fv = float(value)
    except (TypeError, ValueError):
        return str(value)
    if semantic == "count":
        return f"{int(round(fv)):,}"
    if semantic == "percentage":
        return format_number(fv, None)
    if semantic == "currency":
        return format_number(fv, currency)
    return format_number(fv, None)
