import os
import json
import re
import random
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
USE_AI = bool(OPENAI_API_KEY and len(OPENAI_API_KEY.strip()) > 10)

client = None
MODEL = os.getenv("OPENAI_MODEL", "gpt-4")

if USE_AI:
    try:
        from openai import OpenAI
        client = OpenAI(
            api_key=OPENAI_API_KEY,
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        )
        print("[AI] OpenAI API connected")
    except ImportError:
        print("[AI] OpenAI package not installed, using local fallback")
        USE_AI = False
else:
    print("[AI] No OpenAI API key set, using smart local fallback for NL -> SQL")


def _chat(system: str, user: str, temperature: float = 0.2) -> str:
    if not USE_AI or not client:
        return ""
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
            max_tokens=2048,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"AI_ERROR: {str(e)}"


def _parse_columns_info(columns_info: str) -> list:
    try:
        return json.loads(columns_info) if columns_info else []
    except json.JSONDecodeError:
        return []


def _is_id_column(col_name: str, dtype: str = "", nunique: int = 0, total_rows: int = 0) -> bool:
    low = col_name.lower().strip()
    id_keywords = ["id", "code", "key", "sku", "uuid", "hash"]
    if any(kw in low for kw in id_keywords):
        return True
    if dtype in ("int64", "int32") and total_rows > 0 and nunique == total_rows and nunique > 10:
        return True
    return False


def _get_column_type(col_name: str, dtype: str, nunique: int, total_rows: int) -> str:
    low = col_name.lower().strip()
    if _is_id_column(col_name, dtype, nunique, total_rows):
        return "id"
    if "date" in low or "time" in low:
        return "date"
    if dtype in ("float64", "int64", "float32", "int32"):
        return "metric"
    if dtype == "object":
        ratio = nunique / total_rows if total_rows > 0 else 1
        if ratio < 0.3:
            return "categorical"
        return "text"
    return "text"


def _simple_stem(word: str) -> str:
    w = word.lower().strip()
    if w.endswith('ies') and len(w) > 4:
        return w[:-3] + 'y'
    if w.endswith('ses') and len(w) > 4:
        return w[:-2]
    if w.endswith('s') and not w.endswith('ss') and len(w) > 3:
        return w[:-1]
    return w


def _match_col(text: str, col_names: list) -> Optional[str]:
    stem = _simple_stem(text.strip())
    for c in col_names:
        c_lower = c.lower()
        c_clean = c_lower.replace('_', ' ')
        if c_lower == stem or c_clean == stem:
            return c
        c_stem = _simple_stem(c_lower)
        if c_stem == stem:
            return c
        c_clean_stem = _simple_stem(c_clean)
        if c_clean_stem == stem:
            return c
    return None


def _detect_intent(question: str, col_names: list, numeric_cols: list, text_cols: list):
    q = question.lower().strip()

    intent = {
        "intent_type": "list",
        "is_count_query": False,
        "is_aggregation": False,
        "is_comparison": False,
        "is_ranking": False,
        "is_time_series": False,
        "is_correlation": False,
        "is_list_all": False,
        "agg_func": None,
        "agg_col": None,
        "group_col": None,
        "group_by_phrase": None,
        "sort_order": None,
        "limit": None,
        "columns_to_select": [],
    }

    # 1. COUNT detection
    count_patterns = [
        r"^how many\s+(.+)\s+are there\??$",
        r"^how many\s+(.+)\??$",
        r"^total\s+(.+)$",
        r"^number of\s+(.+)$",
        r"^count\s+(.+)$",
        r"^count of\s+(.+)$",
        r"^total number of\s+(.+)$",
        r"^what is the total number of\s+(.+)$",
        r"^give me the count of\s+(.+)$",
    ]
    for pattern in count_patterns:
        m = re.match(pattern, q)
        if m:
            intent["is_count_query"] = True
            intent["is_aggregation"] = True
            intent["agg_func"] = "COUNT"
            intent["intent_type"] = "count"
            target = m.group(1).strip().rstrip("?.")
            for c in col_names:
                if c.lower() == target or c.lower().replace("_", " ") == target:
                    intent["agg_col"] = c
                    break
            break

    # 2. COMPARISON: "compare X across Y", "X comparison by Y"
    if intent["intent_type"] == "list":
        compare_match = re.search(r'\bcompare\s+(.+?)\s+(?:across|by|with|against)\s+(.+)', q)
        if not compare_match:
            compare_match = re.search(r'(.+?)\s+comparison\s+(?:across|by|of|between|with)\s+(.+)', q)

        if compare_match:
            metric_phrase = compare_match.group(1).strip()
            group_phrase = compare_match.group(2).strip()

            agg_keywords = {
                'average': 'AVG', 'avg': 'AVG', 'mean': 'AVG',
                'total': 'SUM', 'sum': 'SUM',
                'maximum': 'MAX', 'max': 'MAX', 'highest': 'MAX',
                'minimum': 'MIN', 'min': 'MIN', 'lowest': 'MIN',
                'count': 'COUNT',
            }
            for kw, func in agg_keywords.items():
                if kw in metric_phrase:
                    intent['agg_func'] = func
                    metric_phrase = re.sub(r'\b' + kw + r'\b', '', metric_phrase).strip()
                    break

            if not intent['agg_func']:
                intent['agg_func'] = 'SUM'

            words = re.findall(r'\w+', metric_phrase)
            for w in words:
                intent['agg_col'] = _match_col(w, numeric_cols)
                if intent['agg_col']:
                    break
            if not intent['agg_col']:
                for w in re.findall(r'\w+', metric_phrase):
                    intent['agg_col'] = _match_col(w, col_names)
                    if intent['agg_col']:
                        break

            for w in re.findall(r'\w+', group_phrase):
                intent['group_col'] = _match_col(w, text_cols)
                if intent['group_col']:
                    break
            if not intent['group_col']:
                for w in re.findall(r'\w+', group_phrase):
                    intent['group_col'] = _match_col(w, col_names)
                    if intent['group_col']:
                        break

            if intent['agg_col'] and intent['group_col']:
                intent['intent_type'] = 'comparison'
                intent['is_comparison'] = True
                intent['is_aggregation'] = True
                intent['sort_order'] = 'DESC'

    # 3. RANKING: "top N X by Y", "rank X by Y", "bottom N X by Y"
    if intent['intent_type'] == 'list':
        rank_match = re.search(r'(?:top|bottom|rank(?:ed)?|best|worst|highest|lowest)\s+(\d+)?\s*(.+?)\s+by\s+(.+)', q)
        if not rank_match:
            rank_match = re.search(r'(?:top|bottom|rank(?:ed)?|best|worst|highest|lowest)\s+(\d+)\s+(.+)', q)

        if rank_match:
            limit_str = rank_match.group(1)
            entity_phrase = rank_match.group(2).strip()
            metric_phrase = rank_match.group(3).strip() if rank_match.lastindex and rank_match.lastindex >= 3 else entity_phrase

            intent['intent_type'] = 'ranking'
            intent['is_ranking'] = True
            intent['limit'] = int(limit_str) if limit_str else 10

            if any(w in q for w in ['top', 'best', 'highest', 'largest']):
                intent['sort_order'] = 'DESC'
            else:
                intent['sort_order'] = 'ASC'

            for w in re.findall(r'\w+', metric_phrase):
                intent['agg_col'] = _match_col(w, numeric_cols)
                if intent['agg_col']:
                    break
            for w in re.findall(r'\w+', entity_phrase):
                intent['group_col'] = _match_col(w, text_cols)
                if intent['group_col']:
                    break
            if not intent['group_col']:
                for w in re.findall(r'\w+', entity_phrase):
                    intent['group_col'] = _match_col(w, col_names)
                    if intent['group_col']:
                        break

            if intent['group_col'] and not intent['agg_col'] and numeric_cols:
                intent['agg_col'] = numeric_cols[0]

    # 4. AGGREGATION (non-comparison)
    if intent['intent_type'] == 'list':
        agg_map = {
            'average': 'AVG', 'avg': 'AVG', 'mean': 'AVG',
            'total': 'SUM', 'sum': 'SUM',
            'maximum': 'MAX', 'max': 'MAX', 'highest': 'MAX', 'largest': 'MAX',
            'minimum': 'MIN', 'min': 'MIN', 'lowest': 'MIN', 'smallest': 'MIN',
        }
        for keyword, func in agg_map.items():
            if keyword in q:
                intent['is_aggregation'] = True
                intent['agg_func'] = func
                break

        if intent['is_aggregation']:
            intent['intent_type'] = 'aggregation'
            for c in numeric_cols:
                if c.lower() in q or c.lower().replace('_', ' ') in q:
                    intent['agg_col'] = c
                    break
            if not intent['agg_col'] and numeric_cols:
                intent['agg_col'] = numeric_cols[0]

    # 5. GROUP BY detection
    group_phrases = [
        r"by\s+(\w+(?:\s+\w+)*)\s*$",
        r"per\s+(\w+(?:\s+\w+)*)",
        r"for each\s+(\w+(?:\s+\w+)*)",
        r"grouped by\s+(\w+(?:\s+\w+)*)",
        r"broken down by\s+(\w+(?:\s+\w+)*)",
        r"distribution\s+(?:by|of|per)\s+(\w+(?:\s+\w+)*)",
        r"group by\s+(\w+(?:\s+\w+)*)",
    ]
    for phrase in group_phrases:
        m = re.search(phrase, q)
        if m:
            group_target = m.group(1).strip()
            intent["group_by_phrase"] = group_target
            for c in col_names:
                if c.lower() == group_target or c.lower().replace("_", " ") == group_target:
                    intent["group_col"] = c
                    break
            if intent["group_col"]:
                break

    # 6. Sorting
    if any(w in q for w in ["top", "highest", "most", "best", "largest"]):
        intent["sort_order"] = "DESC"
    elif any(w in q for w in ["bottom", "lowest", "least", "worst", "smallest"]):
        intent["sort_order"] = "ASC"

    # 7. Limit
    limit_match = re.search(r"(?:top|bottom|first|last)\s+(\d+)", q)
    if limit_match:
        intent["limit"] = int(limit_match.group(1))
    elif "top" in q or "bottom" in q:
        intent["limit"] = 10

    # 8. Time series
    if any(w in q for w in ["trend", "over time", "monthly", "weekly", "daily", "timeline", "growth"]):
        intent["is_time_series"] = True
        if intent["intent_type"] == "list":
            intent["intent_type"] = "time_series"

    # 9. ANALYSIS / SUMMARY / OVERVIEW — catch-all for comprehensive business review
    analysis_keywords = [
        "analyze", "analysis", "summary", "overview", "describe",
        "tell me about", "business review", "business overview",
        "report", "review", "dashboard", "profile", "breakdown"
    ]
    if intent["intent_type"] == "list":
        for kw in analysis_keywords:
            if kw in q:
                intent["intent_type"] = "analysis"
                break

    # 10. Correlation
    if any(w in q for w in ["correlation", "relationship", "vs", "versus", "scatter"]):
        intent["is_correlation"] = True
        if intent["intent_type"] == "list":
            intent["intent_type"] = "correlation"

    # 10. List all
    if any(w in q for w in ["all", "everything", "show me all", "list all"]):
        intent["is_list_all"] = True

    return intent


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
- NEVER use SUM(), AVG(), MIN(), MAX() on ID columns — they are meaningless.
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
        result = _chat(system_prompt, question)
        if result and not result.startswith("AI_ERROR"):
            result = re.sub(r"```sql\s*", "", result)
            result = re.sub(r"```\s*", "", result)
            return result.strip().rstrip(";")

    return _local_nl_to_sql(question, table_name, columns_info)


def validate_sql_intent(question: str, sql: str, table_name: str, columns_info: str) -> dict:
    q = question.lower().strip()
    sql_upper = sql.upper()
    cols = _parse_columns_info(columns_info)
    col_names = [c["name"] for c in cols]

    issues = []

    # 1. Count query should not have GROUP BY
    is_count_question = bool(re.match(r"^(how many|total|number of|count)", q))
    has_group_by = "GROUP BY" in sql_upper

    if is_count_question and has_group_by:
        issues.append("The query groups results instead of counting total. Use COUNT(*) without GROUP BY.")

    # 2. GROUP BY column exists
    if has_group_by:
        group_match = re.search(r'GROUP BY\s+"?(\w+)"?', sql_upper)
        if group_match:
            group_col = group_match.group(1)
            if group_col not in [c.upper() for c in col_names] and group_col not in col_names:
                issues.append(f"GROUP BY column '{group_col}' not found in dataset.")

    # 3. Column existence check (skip table names in FROM/JOIN)
    sql_keywords = {
        "SELECT", "FROM", "WHERE", "GROUP", "ORDER", "BY", "AS", "ON",
        "AND", "OR", "IN", "NOT", "NULL", "IS", "LIKE", "BETWEEN",
        "INNER", "LEFT", "RIGHT", "JOIN", "LIMIT", "OFFSET", "HAVING",
        "DISTINCT", "COUNT", "SUM", "AVG", "MAX", "MIN", "ASC", "DESC",
        "CASE", "WHEN", "THEN", "ELSE", "END", "TRUE", "FALSE",
    }
    sql_no_tables = re.sub(r'\b(?:FROM|JOIN)\s+"(\w+)"', '', sql, flags=re.IGNORECASE)
    sql_no_tables = re.sub(r'\b(?:FROM|JOIN)\s+(\w+)', '', sql_no_tables, flags=re.IGNORECASE)
    col_refs = re.findall(r'"(\w+)"', sql_no_tables)
    for ref in col_refs:
        if ref.upper() in sql_keywords:
            continue
        if ref not in col_names and ref.upper() not in [c.upper() for c in col_names]:
            issues.append(f"Column '{ref}' referenced in SQL does not exist in dataset.")

    # 4. Simple count should not select extra columns
    if is_count_question:
        select_match = re.search(r"SELECT\s+(.+?)\s+FROM", sql_upper)
        if select_match:
            selected = select_match.group(1)
            if "," in selected and "COUNT" in selected:
                issues.append("Query selects multiple columns for a count question. Use only COUNT.")

    # 5. Check for ID column in aggregation functions (SUM/AVG on productid, etc.)
    for c in cols:
        cname = c["name"]
        col_type = c.get("type", "")
        is_id = (col_type == "id") or _is_id_column(cname, c.get("dtype", ""), c.get("unique", 0) or 0, len(cols))
        if is_id:
            if re.search(rf'(SUM|AVG|MIN|MAX)\s*\(\s*"?{re.escape(cname)}"?\s*\)', sql, re.IGNORECASE):
                issues.append(f"Aggregation on ID column '{cname}' is not meaningful. Use a metric column instead.")

    valid = len(issues) == 0
    suggested_fix = None
    if not valid:
        suggested_fix = _local_nl_to_sql(question, table_name, columns_info)

    return {
        "valid": valid,
        "issues": issues,
        "suggested_fix": suggested_fix,
    }


def detect_chart_type(question: str, columns: list, data_sample: list) -> dict:
    q = question.lower()

    # Single value -> KPI
    if len(data_sample) == 1 and len(columns) == 1:
        col_name = columns[0]
        val = data_sample[0].get(col_name)
        if isinstance(val, (int, float)):
            return {
                "chart_type": "kpi",
                "x_axis": col_name,
                "y_axis": col_name,
                "title": question.strip().capitalize(),
                "description": f"Single value result for: {question}",
            }

    # Count query -> KPI
    if any(kw in q for kw in ["how many", "total", "number of", "count"]):
        if len(data_sample) <= 1:
            col_name = columns[0] if columns else "value"
            return {
                "chart_type": "kpi",
                "x_axis": col_name,
                "y_axis": col_name,
                "title": question.strip().capitalize(),
                "description": f"Count result for: {question}",
            }

    # Classify columns
    numeric_cols = []
    text_cols = []
    date_cols = []
    if data_sample:
        for col in columns:
            vals = [row.get(col) for row in data_sample if row.get(col) is not None]
            if not vals:
                continue
            sample_val = vals[0]
            col_lower = col.lower()
            if any(kw in col_lower for kw in ("date", "time", "day", "month", "year", "quarter", "week")):
                date_cols.append(col)
            elif isinstance(sample_val, (int, float)):
                numeric_cols.append(col)
            else:
                text_cols.append(col)

    x_axis = columns[0] if columns else ""
    y_axis = columns[1] if len(columns) > 1 else columns[0] if columns else ""

    if text_cols:
        x_axis = text_cols[0]
    elif date_cols:
        x_axis = date_cols[0]
    if numeric_cols:
        y_axis = numeric_cols[0]

    chart_type = "table"

    # Intent-based chart selection
    is_comparison = any(w in q for w in ["compare", "comparison", "across", "by region", "by category"])
    is_ranking = any(w in q for w in ["top", "bottom", "rank", "best", "worst", "highest", "lowest"])
    is_trend = any(w in q for w in ["trend", "over time", "monthly", "weekly", "daily", "timeline", "growth"])
    is_distribution = any(w in q for w in ["percentage", "distribution", "share", "proportion", "breakdown"])
    is_correlation = any(w in q for w in ["correlation", "relationship", "vs", "versus", "scatter"])

    # Comparison -> bar chart (use horizontal bar for rankings)
    if is_comparison and text_cols and numeric_cols:
        chart_type = "bar"

    # Ranking -> bar chart (horizontal)
    if is_ranking and text_cols and numeric_cols:
        chart_type = "bar"

    # Trend -> line chart
    if is_trend and (date_cols or text_cols) and numeric_cols:
        chart_type = "line"
        if date_cols:
            x_axis = date_cols[0]

    # Distribution -> pie chart (small cardinality only)
    if is_distribution and text_cols:
        unique_vals = set(row.get(text_cols[0]) for row in data_sample if row.get(text_cols[0]) is not None)
        if len(unique_vals) <= 10:
            chart_type = "pie"
        else:
            chart_type = "bar"

    # Correlation -> treat as bar (scatter requires two numeric cols)
    if is_correlation:
        chart_type = "bar"

    # Default: text + numeric -> bar
    if chart_type == "table" and text_cols and numeric_cols:
        chart_type = "bar"

    # Time-based data + numeric -> line
    if chart_type == "table" and date_cols and numeric_cols:
        chart_type = "line" if len(data_sample) > 3 else "bar"

    # No category and no date -> table
    if chart_type == "bar" and not text_cols and not date_cols:
        chart_type = "table"

    # Pie refinement
    if chart_type == "pie" and text_cols:
        unique_vals = set(row.get(text_cols[0]) for row in data_sample if row.get(text_cols[0]) is not None)
        if len(unique_vals) > 10:
            chart_type = "bar"

    title = question.strip().capitalize()
    if len(title) > 60:
        title = title[:57] + "..."

    return {
        "chart_type": chart_type,
        "x_axis": x_axis,
        "y_axis": y_axis,
        "title": title,
        "description": f"Visualization for: {question}",
    }


def generate_insights(question: str, data_sample: list, columns: list) -> dict:
    num_rows = len(data_sample)
    num_cols = len(columns)

    summaries = []
    recommendations = []
    risks = []
    follow_ups = []

    col_names = columns
    numeric_cols = []
    text_cols = []
    date_cols = []

    for col in columns:
        vals = [row.get(col) for row in data_sample if isinstance(row.get(col), (int, float))]
        if len(vals) > num_rows * 0.5:
            numeric_cols.append(col)
        else:
            text_cols.append(col)
        col_lower = col.lower()
        if any(kw in col_lower for kw in ("date", "time", "day", "month", "year", "quarter", "week")):
            date_cols.append(col)

    q = question.lower()

    # Detect intent type for smarter insights
    is_analysis = any(w in q for w in ["analyze", "analysis", "summary", "overview", "describe", "tell me about", "business review"])
    is_comparison = "comparison" in q or "compare" in q or "across" in q
    is_ranking = any(w in q for w in ["top ", "bottom ", "rank", "best", "worst"])
    is_count = any(w in q for w in ["how many", "total", "number of", "count"])

    # Single-value KPI result
    if num_rows == 1 and num_cols == 1:
        col = col_names[0]
        val = data_sample[0].get(col)
        if isinstance(val, (int, float)):
            if "count" in col.lower() or "total" in col.lower():
                summaries.append(f"There are {int(val)} records in the dataset.")
            else:
                summaries.append(f"The {col} value is {val:,.2f}.")
            recommendations.append(f"Break down this metric by available dimensions for deeper analysis.")
            if text_cols:
                follow_ups.append(f"Show this metric by {text_cols[0]}.")
            follow_ups.append(f"What is the trend of {col} over time?")
            return {
                "executive_summary": summaries[:5],
                "recommendations": recommendations[:3],
                "risks": risks[:2],
                "follow_up_questions": follow_ups[:3],
            }

    # Comprehensive analysis / business summary (single-row multi-column KPI result)
    if is_analysis and num_rows == 1:
        row = data_sample[0]
        kpi_parts = []
        for col in col_names:
            low = col.lower()
            val = row.get(col)
            if val is None:
                continue
            if "total_records" in low or "count" in low:
                kpi_parts.append(f"Total records: {int(val):,}")
            elif "unique" in low or "distinct" in low:
                dim_name = col.replace("unique_", "").replace("_", " ")
                kpi_parts.append(f"Unique {dim_name}: {int(val):,}")
            elif low.startswith("avg_"):
                dim_name = col[4:].replace("_", " ")
                kpi_parts.append(f"Average {dim_name}: {val:,.2f}")
            elif low.startswith("min_"):
                dim_name = col[4:].replace("_", " ")
                kpi_parts.append(f"Min {dim_name}: {val:,.2f}")
            elif low.startswith("max_"):
                dim_name = col[4:].replace("_", " ")
                kpi_parts.append(f"Max {dim_name}: {val:,.2f}")
            elif low.startswith("total_"):
                dim_name = col[6:].replace("_", " ")
                kpi_parts.append(f"Total {dim_name}: {val:,.2f}")
            elif isinstance(val, (int, float)):
                kpi_parts.append(f"{col}: {val:,.2f}")
            else:
                kpi_parts.append(f"{col}: {val}")

        for part in kpi_parts:
            summaries.append(part)

        # Generate business narrative
        if len(kpi_parts) >= 3:
            summaries.append("The dataset shows healthy diversity across these dimensions.")

        if numeric_cols and len(numeric_cols) >= 2:
            avg_col = next((c for c in col_names if c.startswith("avg_")), None)
            max_col = next((c for c in col_names if c.startswith("max_")), None)
            if avg_col and max_col:
                avg_val = row.get(avg_col, 0) or 0
                max_val = row.get(max_col, 0) or 0
                if max_val > 0:
                    ratio = avg_val / max_val if max_val else 0
                    if ratio < 0.3:
                        summaries.append("Significant spread exists between average and maximum values, indicating high-value outliers.")

        # Recommendations
        if cat_cols:
            recommendations.append(f"Break down metrics by '{cat_cols[0]}' to identify category-level trends.")
        if date_cols:
            recommendations.append("Analyze trends over time to identify seasonality and growth patterns.")
        recommendations.append("Compare top-performing segments against average to identify best practices.")

        # Risks
        risk_count = next((int(row.get(c, 0)) for c in col_names if "total_records" in c.lower()), 0)
        if risk_count > 0 and risk_count < 50:
            risks.append(f"Small dataset ({risk_count} records) — insights may not be statistically significant.")
        risks.append("Summary statistics can mask important segment-level variations.")

        # Follow-ups
        if cat_cols:
            follow_ups.append(f"Show distribution of key metrics by {cat_cols[0]}.")
        if numeric_cols:
            follow_ups.append(f"What are the top 10 records by {numeric_cols[0]}?")
        if date_cols:
            follow_ups.append(f"Show trend of {numeric_cols[0] if numeric_cols else 'metrics'} over time.")

        return {
            "executive_summary": summaries[:8],
            "recommendations": recommendations[:3],
            "risks": risks[:2],
            "follow_up_questions": follow_ups[:3],
        }

    # Comparison insights (e.g., "profit comparison across regions")
    if is_comparison and len(text_cols) >= 1 and len(numeric_cols) >= 1:
        dim_col = text_cols[0]
        metric_col = numeric_cols[0]

        values = [(row.get(dim_col, "Unknown"), row.get(metric_col, 0) or 0) for row in data_sample]
        values.sort(key=lambda x: x[1], reverse=True)

        if len(values) >= 1:
            top_name, top_val = values[0]
            summaries.append(f"'{top_name}' leads with {top_val:,.2f} in '{metric_col}'.")

        if len(values) >= 2:
            second_name, second_val = values[1]
            summaries.append(f"'{second_name}' follows with {second_val:,.2f}.")

        if len(values) >= 3:
            bottom_name, bottom_val = values[-1]
            summaries.append(f"'{bottom_name}' has the lowest at {bottom_val:,.2f}.")

        if len(values) >= 2:
            total = sum(v for _, v in values)
            top_pct = (top_val / total * 100) if total > 0 else 0
            summaries.append(f"'{top_name}' accounts for {top_pct:.0f}% of total '{metric_col}'.")

        avg_val = sum(v for _, v in values) / len(values) if values else 0
        summaries.append(f"The average '{metric_col}' across all {dim_col}s is {avg_val:,.2f}.")

        # Query-context recommendations
        if len(values) >= 2:
            recommendations.append(f"Drill down into '{top_name}' to identify what drives its high {metric_col}.")
            recommendations.append(f"Analyze why '{values[-1][0]}' underperforms and explore improvement opportunities.")
        if date_cols:
            recommendations.append(f"Compare {metric_col} trends over time for top and bottom {dim_col}s.")

        # Query-context follow-ups
        if date_cols:
            follow_ups.append(f"Show {metric_col} trend over time for '{top_name}'.")
        follow_ups.append(f"Compare {metric_col} across all {dim_col}s.")
        if len(numeric_cols) > 1:
            follow_ups.append(f"Show correlation between {numeric_cols[0]} and {numeric_cols[1]}.")

        return {
            "executive_summary": summaries[:5],
            "recommendations": recommendations[:3],
            "risks": risks[:2],
            "follow_up_questions": follow_ups[:3],
        }

    # Ranking insights (e.g., "top 5 products by revenue")
    if is_ranking and len(numeric_cols) >= 1:
        metric_col = numeric_cols[0]

        values = [row.get(metric_col, 0) or 0 for row in data_sample]
        if values:
            max_val = max(values)
            min_val = min(values)
            avg_val = sum(values) / len(values)

            if num_rows <= 20:
                summaries.append(f"'{metric_col}' ranges from {min_val:,.2f} to {max_val:,.2f} (average: {avg_val:,.2f}).")
            else:
                summaries.append(f"Showing top {num_rows} records by '{metric_col}'.")

            if text_cols:
                top_row = max(data_sample, key=lambda r: r.get(metric_col, 0) or 0)
                top_name = top_row.get(text_cols[0], "Unknown")
                summaries.append(f"'{top_name}' tops the list with {max_val:,.2f}.")

                if num_rows > 1:
                    bottom_row = min(data_sample, key=lambda r: r.get(metric_col, 0) or 0)
                    bottom_name = bottom_row.get(text_cols[0], "Unknown")
                    summaries.append(f"'{bottom_name}' ranks last with {min_val:,.2f}.")

        # Query-context recommendations
        if text_cols:
            recommendations.append(f"Explore what differentiates top-performing {text_cols[0]}s from the rest.")
            if date_cols:
                recommendations.append(f"Analyze {metric_col} trends over time for the top {text_cols[0]}s.")
        recommendations.append(f"Consider which {metric_col} drivers can be optimized for better results.")

        # Follow-ups
        if text_cols:
            follow_ups.append(f"Show distribution of {metric_col} by {text_cols[0]}.")
            follow_ups.append(f"What factors contribute to {metric_col} performance?")
        if date_cols:
            follow_ups.append(f"Show {metric_col} trend over time.")

        return {
            "executive_summary": summaries[:5],
            "recommendations": recommendations[:3],
            "risks": risks[:2],
            "follow_up_questions": follow_ups[:3],
        }

    # Default: data-driven insights
    summaries.append(f"Query returned {num_rows} row{'s' if num_rows != 1 else ''} across {num_cols} column{'s' if num_cols != 1 else ''}.")

    for col in numeric_cols:
        values = [row.get(col) for row in data_sample if isinstance(row.get(col), (int, float))]
        if not values or len(values) < 2:
            continue
        total = sum(values)
        avg_val = total / len(values)
        max_val = max(values)
        min_val = min(values)

        if len(values) >= 2:
            summaries.append(f"'{col}' ranges from {min_val:,.2f} to {max_val:,.2f} (average: {avg_val:,.2f}).")

        if len(values) > 1 and num_rows > 1:
            sorted_vals = sorted(values, reverse=True)
            if sorted_vals[0] != sorted_vals[-1]:
                top_pct = sorted_vals[0] / total * 100 if total > 0 else 0
                if top_pct > 50:
                    summaries.append(f"Top entry accounts for {top_pct:.0f}% of total '{col}'.")
        break

    # Text column distribution
    for col in text_cols:
        val_counts = {}
        for row in data_sample:
            v = row.get(col)
            if v is not None:
                val_counts[str(v)] = val_counts.get(str(v), 0) + 1
        if val_counts and len(val_counts) >= 1:
            top_val = max(val_counts, key=val_counts.get)
            top_count = val_counts[top_val]
            unique_count = len(val_counts)
            if unique_count > 1:
                summaries.append(f"Top '{col}' is '{top_val}' ({top_count} occurrences) among {unique_count} unique values.")
            else:
                summaries.append(f"'{col}' has a single value: '{top_val}'.")
        break

    if not summaries:
        summaries.append("The data contains structured records suitable for analysis.")

    # Query-context recommendations
    if text_cols and numeric_cols:
        recommendations.append(f"Analyze '{numeric_cols[0]}' by '{text_cols[0]}' to identify patterns.")
    if date_cols and numeric_cols:
        recommendations.append(f"Track '{numeric_cols[0]}' over time to identify trends.")
    if text_cols:
        recommendations.append(f"Explore the distribution of records by '{text_cols[0]}'.")

    # Risks
    if num_rows < 5:
        risks.append(f"Small sample size ({num_rows} rows) may not be representative.")
    if num_rows > 0:
        risks.append("Results are based on the queried subset — broader trends may differ.")

    # Follow-ups
    if text_cols and numeric_cols:
        follow_ups.append(f"What is the '{numeric_cols[0]}' by '{text_cols[0]}'?")
    if date_cols and numeric_cols:
        follow_ups.append(f"Show '{numeric_cols[0]}' trend over time.")
    if text_cols and numeric_cols:
        follow_ups.append(f"What are the top 5 '{text_cols[0]}' by '{numeric_cols[0]}'?")

    return {
        "executive_summary": summaries[:5],
        "recommendations": recommendations[:3],
        "risks": risks[:2],
        "follow_up_questions": follow_ups[:3],
    }


def generate_ai_quality(question: str, sql: str, chart_type: str, validation_result: dict,
                        data_length: int, sql_success: bool = True) -> dict:
    q = question.lower().strip()
    issues = validation_result.get("issues", [])[:]

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
    }

    total_possible = len(steps)
    total_achieved = sum(steps.values())
    overall_score = round((total_achieved / total_possible) * 100, 1) if total_possible > 0 else 100.0

    return {
        "intent_detected": intent_detected,
        "sql_generated": sql_generated,
        "sql_validated": sql_validated,
        "chart_selected_correctly": chart_selected_correctly,
        "summary_generated": summary_generated,
        "recommendations_generated": recommendations_generated,
        "follow_up_generated": follow_up_generated,
        "sql_executed_successfully": sql_executed_successfully,
        "visualization_quality": visualization_quality,
        "overall_score": overall_score,
        "step_scores": steps,
        "issues": issues,
    }
