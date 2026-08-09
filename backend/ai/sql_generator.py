"""NL -> SQL generation.

Uses the configured LLM provider when available and falls back to a local
rule-based engine that is fully deterministic and testable.
"""
import logging
import re

from .columns import _parse_columns_info, _get_column_type, _validate_business_question
from .intent import _detect_intent
from .provider import USE_AI, chat

logger = logging.getLogger("app.ai.sql_generator")


def _local_nl_to_sql(question: str, table_name: str, columns_info: str) -> str:
    cols = _parse_columns_info(columns_info)
    col_names = [c["name"] for c in cols]
    total_rows_from_info = max((c.get("unique", 0) or 0) for c in cols) if cols else 0
    numeric_cols_all = [c["name"] for c in cols if c.get("dtype") in ("int64", "float64", "int32", "float32")]
    text_cols_all = [c["name"] for c in cols if c.get("dtype") == "object"]
    all_cols = ", ".join(f'"{c}"' for c in col_names)

    intent = _detect_intent(question, col_names, numeric_cols_all, text_cols_all)

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
        return f'SELECT {select_clause} FROM "{table_name}"'

    # COUNT without GROUP BY
    if intent["is_count_query"] and not intent["group_col"]:
        if intent["agg_col"]:
            return f'SELECT COUNT(DISTINCT "{intent["agg_col"]}") AS total_{intent["agg_col"]} FROM "{table_name}"'
        return f'SELECT COUNT(*) AS total_count FROM "{table_name}"'

    # COUNT with GROUP BY
    if intent["is_count_query"] and intent["group_col"]:
        return f'SELECT "{intent["group_col"]}", COUNT(*) AS count FROM "{table_name}" GROUP BY "{intent["group_col"]}" ORDER BY count DESC'

    # COMPARISON: aggregate metric grouped by dimension
    if intent["intent_type"] == "comparison" and intent["group_col"] and intent["agg_col"]:
        alias = f'{intent["agg_func"].lower()}_{intent["agg_col"]}'
        sql = f'SELECT "{intent["group_col"]}", {intent["agg_func"]}("{intent["agg_col"]}") AS {alias} FROM "{table_name}" GROUP BY "{intent["group_col"]}" ORDER BY {alias} DESC'
        return sql

    # RANKING: sort by metric
    if intent["intent_type"] == "ranking":
        select_cols = all_cols
        if intent["group_col"] and intent["agg_col"]:
            select_cols = f'"{intent["group_col"]}", "{intent["agg_col"]}"'
        sql = f'SELECT {select_cols} FROM "{table_name}"'
        sort_col = intent["agg_col"] if intent["agg_col"] else (numeric_cols[0] if numeric_cols else col_names[0])
        sql += f' ORDER BY "{sort_col}" {intent["sort_order"] or "DESC"}'
        sql += f' LIMIT {intent["limit"] or 10}'
        return sql

    # Aggregation with GROUP BY
    if intent["is_aggregation"] and intent["group_col"] and intent["agg_col"]:
        alias = f'{intent["agg_func"].lower()}_{intent["agg_col"]}'
        sql = f'SELECT "{intent["group_col"]}", {intent["agg_func"]}("{intent["agg_col"]}") AS {alias} FROM "{table_name}" GROUP BY "{intent["group_col"]}" ORDER BY {alias} DESC'
        if intent["limit"]:
            sql += f' LIMIT {intent["limit"]}'
        return sql

    # Aggregation without GROUP BY
    if intent["is_aggregation"] and intent["agg_col"]:
        return f'SELECT {intent["agg_func"]}("{intent["agg_col"]}") AS {intent["agg_func"].lower()}_{intent["agg_col"]} FROM "{table_name}"'

    # Time series
    if intent["is_time_series"] and date_cols and numeric_cols:
        return f'SELECT "{date_cols[0]}", "{numeric_cols[0]}" FROM "{table_name}" ORDER BY "{date_cols[0]}" ASC LIMIT 100'

    # List all
    if intent["is_list_all"]:
        return f'SELECT {all_cols} FROM "{table_name}" LIMIT 100'

    # Sort-only queries
    if intent["sort_order"] and numeric_cols:
        sort_col = numeric_cols[0]
        return f'SELECT {all_cols} FROM "{table_name}" ORDER BY "{sort_col}" {intent["sort_order"]} LIMIT {intent["limit"] or 10}'

    return f'SELECT {all_cols} FROM "{table_name}" LIMIT {intent["limit"] or 20}'


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
- "Analyze", "Summary", "Overview", "Describe" -> SELECT COUNT(*), AVG(metrics), MIN(metrics), MAX(metrics) in a single row
"""
        result = chat(system_prompt, question)
        if result and not result.startswith("AI_ERROR"):
            result = re.sub(r"```sql\s*", "", result)
            result = re.sub(r"```\s*", "", result)
            return result.strip().rstrip(";")

    return _local_nl_to_sql(question, table_name, columns_info)
