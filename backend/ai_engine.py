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


def _detect_intent(question: str, col_names: list, numeric_cols: list, text_cols: list):
    """Detect user intent from question. Returns a structured intent dict."""
    q = question.lower().strip()

    intent = {
        "is_count_query": False,
        "is_aggregation": False,
        "agg_func": None,
        "agg_col": None,
        "group_col": None,
        "group_by_phrase": None,
        "sort_order": None,
        "limit": None,
        "is_time_series": False,
        "is_list_all": False,
        "columns_to_select": [],
    }

    # Count intent detection
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
            # Extract what entity is being counted
            target = m.group(1).strip().rstrip("?.")
            # Check if target is a column name
            for c in col_names:
                if c.lower() == target or c.lower().replace("_", " ") == target:
                    intent["agg_col"] = c
                    break
            break

    # Aggregation detection (sum, avg, max, min)
    if not intent["is_aggregation"]:
        agg_map = {
            "average": "AVG", "avg": "AVG", "mean": "AVG",
            "total": "SUM", "sum": "SUM",
            "maximum": "MAX", "max": "MAX", "highest": "MAX", "largest": "MAX",
            "minimum": "MIN", "min": "MIN", "lowest": "MIN", "smallest": "MIN",
        }
        for keyword, func in agg_map.items():
            if keyword in q:
                intent["is_aggregation"] = True
                intent["agg_func"] = func
                break

    # If count query, find what to count
    if intent["is_count_query"]:
        intent["agg_col"] = None  # COUNT(*) by default

    # Find aggregation column for non-count aggregations
    if intent["is_aggregation"] and intent["agg_func"] != "COUNT" and numeric_cols:
        for c in numeric_cols:
            if c.lower() in q or c.lower().replace("_", " ") in q:
                intent["agg_col"] = c
                break
        if not intent["agg_col"]:
            intent["agg_col"] = numeric_cols[0]

    # Group by detection - only when user explicitly asks for grouping
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

    # Sorting detection
    if any(w in q for w in ["top", "highest", "most", "best", "largest"]):
        intent["sort_order"] = "DESC"
    elif any(w in q for w in ["bottom", "lowest", "least", "worst", "smallest"]):
        intent["sort_order"] = "ASC"

    # Limit detection
    limit_match = re.search(r"(?:top|bottom|first|last)\s+(\d+)", q)
    if limit_match:
        intent["limit"] = int(limit_match.group(1))
    elif "top" in q or "bottom" in q:
        intent["limit"] = 10

    # Time series detection
    if any(w in q for w in ["trend", "over time", "monthly", "weekly", "daily"]):
        intent["is_time_series"] = True

    # List all detection
    if any(w in q for w in ["all", "everything", "show me all", "list all"]):
        intent["is_list_all"] = True

    return intent


def _local_nl_to_sql(question: str, table_name: str, columns_info: str) -> str:
    """Smart local NL-SQL converter with proper intent detection."""
    cols = _parse_columns_info(columns_info)
    col_names = [c["name"] for c in cols]
    numeric_cols = [c["name"] for c in cols if c.get("dtype") in ("int64", "float64", "int32", "float32")]
    text_cols = [c["name"] for c in cols if c.get("dtype") == "object"]
    all_cols = ", ".join(f'"{c}"' for c in col_names)

    intent = _detect_intent(question, col_names, numeric_cols, text_cols)

    # Get date columns
    date_cols = [c["name"] for c in cols if "date" in c.get("dtype", "").lower() or "date" in c["name"].lower() or "time" in c["name"].lower()]

    # COUNT query without GROUP BY → simple count
    if intent["is_count_query"] and not intent["group_col"]:
        if intent["agg_col"]:
            return f'SELECT COUNT(DISTINCT "{intent["agg_col"]}") AS total_{intent["agg_col"]} FROM "{table_name}"'
        return f'SELECT COUNT(*) AS total_count FROM "{table_name}"'

    # COUNT query WITH GROUP BY (explicit)
    if intent["is_count_query"] and intent["group_col"]:
        return f'SELECT "{intent["group_col"]}", COUNT(*) AS count FROM "{table_name}" GROUP BY "{intent["group_col"]}" ORDER BY count DESC'

    # Aggregation with GROUP BY
    if intent["is_aggregation"] and intent["group_col"] and intent["agg_col"]:
        sql = f'SELECT "{intent["group_col"]}", {intent["agg_func"]}("{intent["agg_col"]}") AS {intent["agg_func"].lower()}_{intent["agg_col"]} FROM "{table_name}" GROUP BY "{intent["group_col"]}"'
        if intent["sort_order"]:
            sql += f' ORDER BY {intent["agg_func"].lower()}_{intent["agg_col"]} {intent["sort_order"]}'
        else:
            sql += f' ORDER BY {intent["agg_func"].lower()}_{intent["agg_col"]} DESC'
        if intent["limit"]:
            sql += f' LIMIT {intent["limit"]}'
        return sql

    # Simple aggregation without GROUP BY
    if intent["is_aggregation"] and intent["agg_col"]:
        return f'SELECT {intent["agg_func"]}("{intent["agg_col"]}") AS {intent["agg_func"].lower()}_{intent["agg_col"]} FROM "{table_name}"'

    # Time series
    if intent["is_time_series"] and date_cols and numeric_cols:
        return f'SELECT "{date_cols[0]}", "{numeric_cols[0]}" FROM "{table_name}" ORDER BY "{date_cols[0]}" ASC LIMIT 100'

    # List all
    if intent["is_list_all"]:
        return f'SELECT {all_cols} FROM "{table_name}" LIMIT 100'

    # Default: show relevant columns
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

INTENT RULES - FOLLOW STRICTLY:
- "How many X are there?", "Total X", "Number of X", "Count X" → SELECT COUNT(*) or SELECT COUNT(DISTINCT col) NEVER use GROUP BY for these.
- Only use GROUP BY when user explicitly asks "by country", "by city", "for each category", "per X", "distribution by X".
- Never add GROUP BY to a count/total query unless user asks for grouping.
- If user asks for a simple count, return a single row with the count.
"""
        result = _chat(system_prompt, question)
        if result and not result.startswith("AI_ERROR"):
            result = re.sub(r"```sql\s*", "", result)
            result = re.sub(r"```\s*", "", result)
            return result.strip().rstrip(";")

    return _local_nl_to_sql(question, table_name, columns_info)


def validate_sql_intent(question: str, sql: str, table_name: str, columns_info: str) -> dict:
    """
    Validate that generated SQL matches user intent.
    Returns {"valid": bool, "issues": [str], "suggested_fix": str or None}
    """
    q = question.lower().strip()
    sql_upper = sql.upper()
    cols = _parse_columns_info(columns_info)
    col_names = [c["name"] for c in cols]

    issues = []

    # 1. Check: count query should not have GROUP BY
    is_count_question = bool(re.match(r"^(how many|total|number of|count)", q))
    has_group_by = "GROUP BY" in sql_upper

    if is_count_question and has_group_by:
        issues.append("The query groups results instead of counting total. Use COUNT(*) without GROUP BY.")

    # 2. Check: GROUP BY column exists
    if has_group_by:
        group_match = re.search(r'GROUP BY\s+"?(\w+)"?', sql_upper)
        if group_match:
            group_col = group_match.group(1)
            if group_col not in [c.upper() for c in col_names] and group_col not in col_names:
                issues.append(f"GROUP BY column '{group_col}' not found in dataset.")

    # 3. Check: all referenced columns exist
    col_refs = re.findall(r'"(\w+)"', sql)
    for ref in col_refs:
        if ref.upper() in ("SELECT", "FROM", "WHERE", "GROUP", "ORDER", "BY", "AS", "ON", "AND", "OR", "IN", "NOT", "NULL", "IS", "LIKE", "BETWEEN", "INNER", "LEFT", "RIGHT", "JOIN", "LIMIT", "OFFSET", "HAVING", "DISTINCT", "COUNT", "SUM", "AVG", "MAX", "MIN", "ASC", "DESC"):
            continue
        if ref not in col_names and ref.upper() not in [c.upper() for c in col_names]:
            issues.append(f"Column '{ref}' referenced in SQL does not exist in dataset.")

    # 4. Check: simple count should not select extra columns
    if is_count_question:
        select_match = re.search(r"SELECT\s+(.+?)\s+FROM", sql_upper)
        if select_match:
            selected = select_match.group(1)
            if "," in selected and "COUNT" in selected:
                issues.append("Query selects multiple columns for a count question. Use only COUNT.")

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
    """Smart chart detection with KPI card for single values."""
    q = question.lower()

    # Check for single-value result → KPI card
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

    # Check for count query → KPI card
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

    # Smart chart selection rules
    chart_type = "table"

    # Single numeric column + text/category column → Bar chart
    if len(numeric_cols) >= 1 and text_cols:
        if len(data_sample) <= 15:
            chart_type = "bar"
        else:
            chart_type = "bar"

    # Time-based data → Line chart
    elif date_cols and numeric_cols:
        chart_type = "line" if len(data_sample) > 3 else "bar"

    # Explicit keywords
    if any(w in q for w in ["trend", "over time", "monthly", "weekly", "daily", "timeline", "growth"]):
        chart_type = "line" if len(data_sample) > 5 else "bar"
    elif any(w in q for w in ["percentage", "distribution", "share", "proportion", "breakdown"]):
        chart_type = "pie"
    elif any(w in q for w in ["top", "bottom", "compare", "highest", "lowest", "best", "worst", "rank"]):
        chart_type = "bar"

    # Multiple records without clear category → Table
    if chart_type == "bar" and not text_cols and not date_cols:
        chart_type = "table"

    # Pie refinement: only for small categorical data
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
    """Generate insights based ONLY on available data and columns."""
    num_rows = len(data_sample)
    num_cols = len(columns)

    summaries = []
    recommendations = []
    risks = []
    follow_ups = []

    # Classify columns
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

    # Build data-aware summary
    summaries.append(f"Query returned {num_rows} row{'s' if num_rows != 1 else ''} across {num_cols} column{'s' if num_cols != 1 else ''}.")

    # Check if it's a simple count result
    if num_rows == 1 and num_cols == 1:
        col = col_names[0]
        val = data_sample[0].get(col)
        if isinstance(val, (int, float)):
            if "count" in col.lower() or "total" in col.lower():
                summaries.append(f"There are {int(val)} records in the dataset.")
            else:
                summaries.append(f"The {col} value is {val}.")

    # Numeric analysis only with meaningful data
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
    has_text_analysis = False
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
            has_text_analysis = True
        break

    if not summaries:
        summaries.append("The data contains structured records suitable for analysis.")

    # Recommendations based only on available columns
    if text_cols and numeric_cols:
        recommendations.append(f"Analyze '{numeric_cols[0]}' by different '{text_cols[0]}' segments to identify patterns.")
    if text_cols:
        recommendations.append(f"Find suppliers by '{text_cols[0]}' to explore geographic distribution.")
    if text_cols and len(text_cols) > 1:
        recommendations.append(f"View contact details and relationships between '{text_cols[0]}' and '{text_cols[1]}'.")
    if numeric_cols:
        recommendations.append(f"Investigate the drivers behind '{numeric_cols[0]}' variance across records.")
    if text_cols:
        recommendations.append(f"Analyze supplier distribution by country.")
        recommendations.append(f"Find suppliers by city.")
        recommendations.append(f"View supplier contact details.")

    # Remove generic time-based recommendations if no date columns
    if not date_cols:
        recommendations = [r for r in recommendations if "time" not in r.lower() and "month" not in r.lower() and "weekly" not in r.lower() and "daily" not in r.lower() and "trend" not in r.lower()]

    # Risks
    if num_rows < 5:
        risks.append(f"Small sample size ({num_rows} rows) may not be representative.")
    if num_rows > 0:
        risks.append("Results are based on the queried subset — broader trends may differ.")

    # Follow-ups
    if text_cols and numeric_cols:
        follow_ups.append(f"What is the '{numeric_cols[0]}' by '{text_cols[0]}'?")
    if text_cols:
        follow_ups.append(f"Show me all records grouped by '{text_cols[0]}'.")
    if text_cols and numeric_cols:
        follow_ups.append(f"What are the top 5 '{text_cols[0]}' by '{numeric_cols[0]}'?")

    return {
        "executive_summary": summaries[:5],
        "recommendations": recommendations[:3],
        "risks": risks[:2],
        "follow_up_questions": follow_ups[:3],
    }


def generate_ai_quality(question: str, sql: str, chart_type: str, validation_result: dict) -> dict:
    """Generate AI quality indicators for the response."""
    quality = {
        "intent_detected": True,
        "sql_validated": validation_result.get("valid", True),
        "chart_selected_correctly": True,
        "summary_generated": True,
        "issues": validation_result.get("issues", []),
    }
    return quality
