"""NL -> SQL generation.

Uses the configured LLM provider when available and falls back to a local
rule-based engine that is fully deterministic and testable.
"""
import logging
import re

from .columns import _match_col, _parse_columns_info, _get_column_type, _validate_business_question
from .intent import _detect_intent
from .provider import USE_AI, chat
from .questions import _preferred_metric

logger = logging.getLogger("app.ai.sql_generator")


def _local_nl_to_sql(question: str, table_name: str, columns_info: str) -> str:
    q = question.lower()
    cols = _parse_columns_info(columns_info)
    col_names = [c["name"] for c in cols]
    total_rows_from_info = max((c.get("unique", 0) or 0) for c in cols) if cols else 0
    numeric_cols_all = [c["name"] for c in cols if c.get("dtype") in ("int64", "float64", "int32", "float32")]
    text_cols_all = [c["name"] for c in cols if c.get("dtype") in ("object", "str", "string")]
    all_cols = ", ".join(f'"{c}"' for c in col_names)

    date_cols = [c["name"] for c in cols if "date" in c.get("dtype", "").lower() or "date" in c["name"].lower() or "time" in c["name"].lower()]

    # ------- CLASSIFY COLUMNS (avoid ID columns in aggregations) -------
    metric_cols = []
    id_cols = []
    cat_cols = []
    for c in cols:
        ctype = _get_column_type(c["name"], c.get("dtype", ""), c.get("unique", 0) or 0, total_rows_from_info)
        if ctype == "id":
            id_cols.append(c["name"])
        elif ctype == "metric":
            metric_cols.append(c["name"])
        elif ctype == "categorical":
            cat_cols.append(c["name"])

    # Prefer real metrics for aggregations, not IDs
    numeric_cols = metric_cols if metric_cols else [c for c in numeric_cols_all if c not in id_cols]
    text_cols = cat_cols if cat_cols else text_cols_all

    # Intent detection is fed the classified columns so that e.g. a generic
    # "category" maps onto the single categorical column via fallback rules.
    intent = _detect_intent(question, col_names, numeric_cols, text_cols)

    # Map intent agg_col away from IDs
    if intent["agg_col"] and intent["agg_col"] in id_cols and metric_cols:
        intent["agg_col"] = metric_cols[0]

    # ------- CAPABILITY-AWARE BUSINESS VALIDATION -------
    # Check if the question requires data the dataset doesn't have
    biz_validation = _validate_business_question(question, cols)
    business_intent_missing = biz_validation.get("missing_capability")

    # For ranking and aggregation intents, if the required business data is missing,
    # fall back to a general overview rather than generating misleading SQL.
    sales_intents = ["sales_analysis", "inventory_analysis", "financial_analysis", "performance_analysis"]
    if business_intent_missing in sales_intents and intent.get("intent_type") in ("ranking", "aggregation", "comparison"):
        intent["intent_type"] = "analysis"
        intent["is_ranking"] = False
        intent["is_aggregation"] = False
        intent["is_comparison"] = False

    # Numeric filters ("revenue above 10000") -> WHERE clause injected after FROM.
    where = _build_where(intent)

    def _finish(sql: str) -> str:
        if where and sql:
            m = re.search(r'\bFROM\s+"[A-Za-z0-9_]+"', sql)
            if m:
                return sql[:m.end()] + " WHERE " + where + sql[m.end():]
        return sql

    # COMPREHENSIVE ANALYSIS INTENT
    if intent["intent_type"] == "analysis":
        select_parts = [f'COUNT(*) AS total_records']
        if cat_cols:
            select_parts.append(f'COUNT(DISTINCT "{cat_cols[0]}") AS unique_{cat_cols[0].replace(" ", "_")}')
        for m in metric_cols[:3]:
            select_parts.append(f'ROUND(AVG("{m}"), 2) AS avg_{m}')
            select_parts.append(f'MIN("{m}") AS min_{m}')
            select_parts.append(f'MAX("{m}") AS max_{m}')
            select_parts.append(f'ROUND(SUM("{m}"), 2) AS total_{m}')
        if not select_parts:
            select_parts = [f'COUNT(*) AS total_records']
        select_clause = ", ".join(select_parts)
        return _finish(f'SELECT {select_clause} FROM "{table_name}"')

    # PERCENTAGE / SHARE: "What percentage of total X is Y?" -> single row
    if cat_cols and metric_cols and any(kw in q for kw in ("percentage", "percent", "proportion", "what %", "% of", "share")):
        # Grouped share: "What percentage of <metric> comes from each <dim>?"
        # or "... by <dim>?" -> one share row per dimension value, ordered
        # descending, using the metric named in the question (else preferred).
        dim_phrase = None
        m = re.search(r"\b(?:each|per)\s+([a-z][a-z0-9_ ]*?)(?:\s+(?:comes|is|accounts|was|were|for|of)\b|\s*\??$)", q)
        if not m:
            m = re.search(r"\bby\s+([a-z][a-z0-9_ ]*?)\s*\??$", q)
        if m:
            dim_phrase = m.group(1).strip()
        group_share = None
        if dim_phrase:
            for w in re.findall(r"\w+", dim_phrase):
                group_share = _match_col(w, cat_cols) or _match_col(w, col_names)
                if group_share:
                    break
        if group_share:
            metric = None
            for c in metric_cols:
                if c.lower() in q or c.lower().replace("_", " ") in q:
                    metric = c
                    break
            if not metric:
                metric = _preferred_metric(metric_cols)
            return _finish(
                f'SELECT "{group_share}", '
                f'ROUND(SUM("{metric}") * 100.0 / NULLIF(SUM("{metric}"), 0), 2) AS percentage '
                f'FROM "{table_name}" GROUP BY "{group_share}" ORDER BY percentage DESC LIMIT 100'
            )
        target = None
        quoted = re.search(r"['\"]([^'\"]+)['\"]", question)
        if quoted:
            target = quoted.group(1)
        else:
            # Prefer the value after the trailing "is/are/for" ("... is Food?"),
            # falling back to "of" for constructions like "share of Food?".
            m = None
            for kw in ("is", "are", "for"):
                matches = list(re.finditer(r"\b" + re.escape(kw) + r"\s+([a-zA-Z][\w\s]*?)\s*\??$", q))
                if matches:
                    m = matches[-1]
                    break
            if not m:
                m = re.search(r"\bof\s+([a-zA-Z][\w\s]*?)\s*\??$", q)
            if m:
                candidate = m.group(1).strip()
                candidate = re.sub(r"^(?:in|for|of|on|at|is|are)\s+", "", candidate).strip()
                for c in cols:
                    if c["name"] == cat_cols[0] and c.get("top_values"):
                        for known in c["top_values"]:
                            if known.lower() == candidate.lower():
                                target = known
                                break
                        if target:
                            break
        if target:
            # The denominator should be the primary metric. `intent["agg_col"]` is
            # unreliable here (the target value's name may match a split column,
            # e.g. a "food" column named like the value "Food"), so derive it from
            # metric columns that are mentioned in the question but are NOT the target.
            target_low = target.lower()
            metric = None
            for c in metric_cols:
                c_low = c.lower()
                c_low_clean = c_low.replace("_", " ")
                if (c_low in q or c_low_clean in q) and c_low != target_low and c_low_clean != target_low:
                    metric = c
                    break
            if not metric:
                metric = _preferred_metric(metric_cols)
            dim = cat_cols[0]
            esc = target.replace("'", "''")
            return _finish(
                f'SELECT "{dim}" AS dimension, '
                f'ROUND(SUM(CASE WHEN "{dim}" = \'{esc}\' THEN "{metric}" ELSE 0 END) * 100.0 '
                f'/ NULLIF(SUM("{metric}"), 0), 2) AS percentage, '
                f'ROUND(SUM("{metric}"), 2) AS total_{metric} '
                f'FROM "{table_name}"'
            )

    # COUNT without GROUP BY
    if intent["is_count_query"] and not intent["group_col"]:
        if intent["agg_col"]:
            return _finish(f'SELECT COUNT(DISTINCT "{intent["agg_col"]}") AS total_{intent["agg_col"]} FROM "{table_name}"')
        return _finish(f'SELECT COUNT(*) AS total_count FROM "{table_name}"')

    # COUNT with GROUP BY
    if intent["is_count_query"] and intent["group_col"]:
        order = intent["sort_order"] or "DESC"
        alias = intent.get("entity") or "count"
        limit = intent.get("limit") or 1000
        return _finish(f'SELECT "{intent["group_col"]}", COUNT(*) AS {alias} FROM "{table_name}" GROUP BY "{intent["group_col"]}" ORDER BY {alias} {order} LIMIT {limit}')

    # COMPARISON: aggregate metric grouped by dimension
    if intent["intent_type"] == "comparison" and intent["group_col"] and intent["agg_col"]:
        alias = f'{intent["agg_func"].lower()}_{intent["agg_col"]}'
        sql = f'SELECT "{intent["group_col"]}", {intent["agg_func"]}("{intent["agg_col"]}") AS {alias} FROM "{table_name}" GROUP BY "{intent["group_col"]}" ORDER BY {alias} DESC'
        return _finish(sql)

    # RANKING: sort by metric
    if intent["intent_type"] == "ranking":
        # "Which category has the highest total X?" -> grouped aggregate, one row
        if intent.get("is_aggregation_rank") and intent["group_col"] and intent["agg_col"]:
            func = intent["agg_func"] or "SUM"
            alias = f'{func.lower()}_{intent["agg_col"]}'
            sql = f'SELECT "{intent["group_col"]}", {func}("{intent["agg_col"]}") AS {alias} FROM "{table_name}" GROUP BY 1 ORDER BY {alias} {intent["sort_order"] or "DESC"}'
            if intent["limit"]:
                sql += f' LIMIT {intent["limit"]}'
            return _finish(sql)
        select_cols = all_cols
        if intent["group_col"] and intent["agg_col"]:
            select_cols = f'"{intent["group_col"]}", "{intent["agg_col"]}"'
        sql = f'SELECT {select_cols} FROM "{table_name}"'
        sort_col = intent["agg_col"] if intent["agg_col"] else (numeric_cols[0] if numeric_cols else col_names[0])
        sql += f' ORDER BY "{sort_col}" {intent["sort_order"] or "DESC"}'
        sql += f' LIMIT {intent["limit"] or 10}'
        return _finish(sql)

    # Aggregation with GROUP BY
    if intent["is_aggregation"] and intent["group_col"] and intent["agg_col"]:
        alias = f'{intent["agg_func"].lower()}_{intent["agg_col"]}'
        sql = f'SELECT "{intent["group_col"]}", {intent["agg_func"]}("{intent["agg_col"]}") AS {alias} FROM "{table_name}" GROUP BY "{intent["group_col"]}" ORDER BY {alias} DESC'
        if intent["limit"]:
            sql += f' LIMIT {intent["limit"]}'
        return _finish(sql)

    # Aggregation without GROUP BY
    if intent["is_aggregation"] and intent["agg_col"]:
        return _finish(f'SELECT {intent["agg_func"]}("{intent["agg_col"]}") AS {intent["agg_func"].lower()}_{intent["agg_col"]} FROM "{table_name}"')

    # Time series
    if intent["is_time_series"] and date_cols and numeric_cols:
        return _finish(f'SELECT "{date_cols[0]}", "{numeric_cols[0]}" FROM "{table_name}" ORDER BY "{date_cols[0]}" ASC LIMIT 100')

    # List all
    if intent["is_list_all"]:
        return _finish(f'SELECT {all_cols} FROM "{table_name}" LIMIT 100')

    # Sort-only queries
    if intent["sort_order"] and numeric_cols:
        sort_col = numeric_cols[0]
        return _finish(f'SELECT {all_cols} FROM "{table_name}" ORDER BY "{sort_col}" {intent["sort_order"]} LIMIT {intent["limit"] or 10}')

    return _finish(f'SELECT {all_cols} FROM "{table_name}" LIMIT {intent["limit"] or 20}')


def _build_where(intent: dict) -> str:
    """Render the intent's numeric filter as a ``"col" op value`` WHERE clause."""
    f = intent.get("filter")
    if not f:
        return ""
    val = f.get("value")
    if isinstance(val, float) and val == int(val):
        val_str = str(int(val))
    else:
        val_str = repr(val)
    return f'"{f["column"]}" {f["op"]} {val_str}'


def nl_to_sql(question: str, table_name: str, columns_info: str) -> str:
    if USE_AI:
        system_prompt = f"""You are a SQL expert. Convert the user's natural language question into a valid SQL SELECT query.

CRITICAL RULES:
- ONLY generate SELECT statements.
- Table name: "{table_name}"
- Available columns and metadata: {columns_info}
- Use double quotes around table and column names.
- Return ONLY the SQL query, nothing else. No markdown, no explanation.
- Limit results to 1000 rows maximum.

COLUMN CLASSIFICATION RULES (from metadata):
- 'id' type columns (productid, customerid, code, key, sku) are IDENTIFIERS, NOT numeric metrics.
- NEVER use SUM(), AVG(), MIN(), MAX() on ID columns - they are meaningless.
- 'metric' type columns are real numeric values suitable for SUM, AVG, MIN, MAX.
- 'categorical' type columns are labels for GROUP BY operations.
- 'date' type columns should be used for time-series analysis.

INTENT RULES - FOLLOW STRICTLY:
- "How many X are there?", "Total X", "Number of X", "Count X" -> SELECT COUNT(*) or SELECT COUNT(DISTINCT col) NEVER use GROUP BY for these.
- Only use GROUP BY when user explicitly asks "by country", "by city", "for each category", "per X", "distribution by X".
- Never add GROUP BY to a count/total query unless user asks for grouping.
- If user asks for a simple count, return a single row with the count.
- "Compare X across Y", "X comparison by Y" -> SELECT Y, SUM(X) ... GROUP BY Y ORDER BY SUM(X) DESC
- "Top N X by Y" -> SELECT X, Y ... ORDER BY Y DESC LIMIT N
- "Rank X by Y" -> SELECT X, Y ... ORDER BY Y DESC
- "Which Y has the highest/lowest X" -> SELECT Y, SUM(X) AS total_X FROM ... GROUP BY Y ORDER BY total_X DESC LIMIT 1
- "Analyze", "Summary", "Overview", "Describe", "Give me N key insights", "Key metrics" -> SELECT COUNT(*), AVG(metrics), MIN(metrics), MAX(metrics) in a single row
- "What percentage/share/proportion of X is Y?" -> SELECT the categorical column, SUM(CASE WHEN col='Y' THEN metric ELSE 0 END)*100.0/NULLIF(SUM(metric),0) AS percentage, and SUM(metric) AS total, in a single row. Never a GROUP BY here unless multiple values are requested.
- If the question asks about a time trend (trend/over time/monthly/weekly/daily) but the dataset has NO date/time/month/year column, respond with exactly: AI_ERROR_NO_DATE (no SQL).
- NEVER invent column names. Only reference columns listed in the metadata above.
"""
        result = chat(system_prompt, question)
        if result and not result.startswith("AI_ERROR"):
            result = re.sub(r"```sql\s*", "", result)
            result = re.sub(r"```\s*", "", result)
            return _canonicalize_table_refs(result.strip().rstrip(";"), table_name)

    return _local_nl_to_sql(question, table_name, columns_info)


def _canonicalize_table_refs(sql: str, table_name: str) -> str:
    """Force every reference to the one allowed table to its canonical quoted,
    exact-case form. LLMs frequently upper-case or drop quotes around the table
    name (e.g. ``FROM DS_ABC...``); the safety validator matches the table
    reference case-sensitively, so an off-case reference gets rejected even
    though the intent is valid."""
    # Matches "tbl", `tbl`, [tbl], or bare tbl with any casing, and rewrites
    # it to the canonical "tbl".
    pattern = re.compile(
        r'(?i)(?:")(?P<name>' + re.escape(table_name) + r')(?:")'
        r'|(?:`)(?P<name2>' + re.escape(table_name) + r')(?:`)'
        r'|(?:\b)(?P<name3>' + re.escape(table_name) + r')(?:\b)'
    )
    return pattern.sub(lambda m: f'"{table_name}"', sql)
