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
    """Call the LLM if available, otherwise return empty."""
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


# ─────────────────────────────────────────────────────
#  LOCAL NL → SQL ENGINE (works without OpenAI)
# ─────────────────────────────────────────────────────

def _parse_columns_info(columns_info: str) -> list:
    """Parse columns_info JSON string to list of column dicts."""
    try:
        return json.loads(columns_info) if columns_info else []
    except json.JSONDecodeError:
        return []


def _local_nl_to_sql(question: str, table_name: str, columns_info: str) -> str:
    """Smart local NL→SQL converter using keyword matching."""
    cols = _parse_columns_info(columns_info)
    col_names = [c["name"] for c in cols]
    numeric_cols = [c["name"] for c in cols if c.get("dtype") in ("int64", "float64", "int32", "float32")]
    text_cols = [c["name"] for c in cols if c.get("dtype") == "object"]

    q = question.lower().strip()
    all_cols = ", ".join(f'"{c}"' for c in col_names)

    # Detect aggregation
    agg_map = {
        "average": "AVG", "avg": "AVG", "mean": "AVG",
        "total": "SUM", "sum": "SUM",
        "count": "COUNT", "how many": "COUNT",
        "maximum": "MAX", "max": "MAX", "highest": "MAX", "largest": "MAX",
        "minimum": "MIN", "min": "MIN", "lowest": "MIN", "smallest": "MIN",
    }

    agg_func = None
    for keyword, func in agg_map.items():
        if keyword in q:
            agg_func = func
            break

    # Detect grouping
    group_col = None
    for kw in ["by", "per", "for each", "group by", "grouped by", "broken down by"]:
        if kw in q:
            idx = q.index(kw) + len(kw)
            rest = q[idx:].strip()
            # Try to match a column name
            for c in col_names:
                if c.lower() in rest or c.lower().replace("_", " ") in rest:
                    group_col = c
                    break
            if group_col:
                break

    # Detect sorting
    sort_order = None
    if any(w in q for w in ["top", "highest", "most", "best", "largest"]):
        sort_order = "DESC"
    elif any(w in q for w in ["bottom", "lowest", "least", "worst", "smallest"]):
        sort_order = "ASC"

    # Detect limit
    limit = None
    limit_match = re.search(r"(?:top|bottom|first|last)\s+(\d+)", q)
    if limit_match:
        limit = int(limit_match.group(1))
    elif "top" in q or "bottom" in q:
        limit = 10

    # Detect target column for agg
    agg_col = None
    if numeric_cols:
        for c in numeric_cols:
            if c.lower() in q or c.lower().replace("_", " ") in q:
                agg_col = c
                break
        if not agg_col:
            agg_col = numeric_cols[0]

    # If no group_col detected, try to find text columns mentioned
    if not group_col and text_cols:
        for c in text_cols:
            if c.lower() in q or c.lower().replace("_", " ") in q:
                group_col = c
                break
        if not group_col and agg_func:
            group_col = text_cols[0] if text_cols else None

    # ─── Build SQL ───
    if agg_func and group_col and agg_col:
        # Aggregation + grouping
        sql = f'SELECT "{group_col}", {agg_func}("{agg_col}") as {agg_func.lower()}_{agg_col} FROM "{table_name}" GROUP BY "{group_col}"'
        if sort_order:
            sql += f' ORDER BY {agg_func.lower()}_{agg_col} {sort_order}'
        else:
            sql += f' ORDER BY {agg_func.lower()}_{agg_col} DESC'
        if limit:
            sql += f' LIMIT {limit}'
        return sql

    elif agg_func and agg_col:
        # Simple aggregation
        return f'SELECT {agg_func}("{agg_col}") as {agg_func.lower()}_{agg_col} FROM "{table_name}"'

    elif any(w in q for w in ["trend", "over time", "monthly", "weekly", "daily"]):
        # Time series
        date_cols = [c["name"] for c in cols if "date" in c.get("dtype", "").lower() or "date" in c["name"].lower() or "time" in c["name"].lower()]
        if date_cols and numeric_cols:
            return f'SELECT "{date_cols[0]}", "{numeric_cols[0]}" FROM "{table_name}" ORDER BY "{date_cols[0]}" ASC LIMIT 100'

    elif any(w in q for w in ["all", "everything", "show me all", "list all"]):
        return f'SELECT {all_cols} FROM "{table_name}" LIMIT 100'

    # Default: return top rows with optional sorting
    if sort_order and numeric_cols:
        sort_col = agg_col or numeric_cols[0]
        return f'SELECT {all_cols} FROM "{table_name}" ORDER BY "{sort_col}" {sort_order} LIMIT {limit or 10}'

    return f'SELECT {all_cols} FROM "{table_name}" LIMIT {limit or 20}'


# ─────────────────────────────────────────────────────
#  PUBLIC API
# ─────────────────────────────────────────────────────

def nl_to_sql(question: str, table_name: str, columns_info: str) -> str:
    """Convert natural language to SQL. Uses OpenAI if available, else local engine."""
    if USE_AI:
        system_prompt = f"""You are a SQL expert. Convert the user's natural language question into a valid SQL SELECT query.

RULES:
- ONLY generate SELECT statements. Never generate INSERT, UPDATE, DELETE, DROP, or any DDL.
- The table name is: "{table_name}"
- Available columns and their metadata: {columns_info}
- Use double quotes around table and column names.
- Return ONLY the SQL query, nothing else. No markdown, no explanation.
- Limit results to 1000 rows maximum.
- If aggregation is asked, use appropriate GROUP BY.
"""
        result = _chat(system_prompt, question)
        if result and not result.startswith("AI_ERROR"):
            result = re.sub(r"```sql\s*", "", result)
            result = re.sub(r"```\s*", "", result)
            return result.strip().rstrip(";")

    # Fallback to local engine
    return _local_nl_to_sql(question, table_name, columns_info)


def detect_chart_type(question: str, columns: list, data_sample: list) -> dict:
    """Auto-detect chart type. Uses OpenAI if available, else smart heuristic."""
    if USE_AI:
        system_prompt = """You are a data visualization expert. Return a JSON object with:
{"chart_type": "bar"|"line"|"pie"|"area"|"table", "x_axis": "col", "y_axis": "col", "title": "Title"}
Rules:
- Use "pie" only for categorical data with few groups (2-8)
- Use "line" or "area" for time-series or ordered data
- Use "bar" for comparisons across categories
- Use "table" for complex multi-column data
Return ONLY JSON, no markdown."""
        user_msg = f"Question: {question}\nColumns: {json.dumps(columns)}\nSample: {json.dumps(data_sample[:3])}"
        result = _chat(system_prompt, user_msg)
        if result and not result.startswith("AI_ERROR"):
            try:
                result = re.sub(r"```json\s*", "", result)
                result = re.sub(r"```\s*", "", result)
                parsed = json.loads(result)
                if parsed.get("chart_type") in ("bar", "line", "pie", "area", "table"):
                    return parsed
            except json.JSONDecodeError:
                pass

    # ─── Local heuristic ───
    q = question.lower()

    # Classify columns by type from data
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

    # Pick axes
    x_axis = columns[0] if columns else ""
    y_axis = columns[1] if len(columns) > 1 else columns[0] if columns else ""

    if text_cols:
        x_axis = text_cols[0]
    elif date_cols:
        x_axis = date_cols[0]
    if numeric_cols:
        y_axis = numeric_cols[0]

    # Detect chart type from question keywords
    chart_type = "table"

    if any(w in q for w in ["percentage", "distribution", "share", "proportion", "breakdown", "composition"]):
        chart_type = "pie"
    elif any(w in q for w in ["trend", "over time", "monthly", "weekly", "daily", "timeline", "growth"]):
        chart_type = "line" if len(data_sample) > 5 else "bar"
    elif any(w in q for w in ["area", "cumulative", "stacked"]):
        chart_type = "area"
    elif any(w in q for w in ["top", "bottom", "compare", "by", "per", "highest", "lowest", "best", "worst", "rank"]):
        chart_type = "bar"
    elif any(w in q for w in ["show", "list", "display", "get", "find"]):
        if len(numeric_cols) >= 1 and (text_cols or date_cols):
            chart_type = "bar"
        elif len(columns) <= 3:
            chart_type = "bar"
    elif len(numeric_cols) >= 1 and (text_cols or date_cols):
        chart_type = "bar"
    elif len(data_sample) <= 1:
        chart_type = "table"

    # Refine pie: only if few categories
    if chart_type == "pie" and text_cols:
        unique_vals = set(row.get(text_cols[0]) for row in data_sample if row.get(text_cols[0]) is not None)
        if len(unique_vals) > 10:
            chart_type = "bar"

    # Title
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
    """Generate business insights. Uses OpenAI if available, else local analysis."""
    if USE_AI:
        system_prompt = """You are a senior business analyst AI. Return a JSON object:
{"executive_summary": ["...", "..."], "recommendations": ["...", "..."], "risks": ["...", "..."], "follow_up_questions": ["...", "..."]}
Rules:
- Be specific: reference actual values, column names, and numbers from the data
- Keep executive_summary to 3-5 items, each 1-2 sentences
- Keep recommendations to 3 actionable items
- Keep risks to 2 items
- Follow-up questions should be specific and drillable
Return ONLY JSON, no markdown."""
        user_msg = f"Question: {question}\nColumns: {json.dumps(columns)}\nData (first 15 rows): {json.dumps(data_sample[:15])}\nTotal rows: {len(data_sample)}"
        result = _chat(system_prompt, user_msg, temperature=0.4)
        if result and not result.startswith("AI_ERROR"):
            try:
                result = re.sub(r"```json\s*", "", result)
                result = re.sub(r"```\s*", "", result)
                insights = json.loads(result)
                return {
                    "executive_summary": insights.get("executive_summary", [])[:5],
                    "recommendations": insights.get("recommendations", [])[:3],
                    "risks": insights.get("risks", [])[:2],
                    "follow_up_questions": insights.get("follow_up_questions", [])[:3],
                }
            except json.JSONDecodeError:
                pass

    # ─── Smart local insights generation ───
    num_rows = len(data_sample)
    num_cols = len(columns)

    summaries = []
    recommendations = []
    risks = []
    follow_ups = []

    # Classify columns
    numeric_cols = []
    text_cols = []
    for col in columns:
        vals = [row.get(col) for row in data_sample if isinstance(row.get(col), (int, float))]
        if len(vals) > num_rows * 0.5:
            numeric_cols.append(col)
        else:
            text_cols.append(col)

    # Summary based on row/column count
    summaries.append(f"Query returned {num_rows} row{'s' if num_rows != 1 else ''} across {num_cols} column{'s' if num_cols != 1 else ''}.")

    # Analyze numeric columns
    for col in numeric_cols:
        values = [row.get(col) for row in data_sample if isinstance(row.get(col), (int, float))]
        if not values:
            continue
        total = sum(values)
        avg_val = total / len(values)
        max_val = max(values)
        min_val = min(values)
        summaries.append(f"'{col}' ranges from {min_val:,.2f} to {max_val:,.2f} (average: {avg_val:,.2f}).")

        if max_val > avg_val * 3:
            summaries.append(f"Outlier detected: max value in '{col}' is {max_val/avg_val:.1f}x above average.")
        if len(values) > 1:
            sorted_vals = sorted(values, reverse=True)
            top_pct = sorted_vals[0] / total * 100 if total > 0 else 0
            if top_pct > 30:
                summaries.append(f"Top entry accounts for {top_pct:.0f}% of total '{col}', indicating high concentration.")
        break  # Only analyze first numeric column in summary

    # Analyze text columns for distribution
    for col in text_cols:
        val_counts = {}
        for row in data_sample:
            v = row.get(col)
            if v is not None:
                val_counts[str(v)] = val_counts.get(str(v), 0) + 1
        if val_counts:
            top_val = max(val_counts, key=val_counts.get)
            top_count = val_counts[top_val]
            unique_count = len(val_counts)
            summaries.append(f"Top '{col}' is '{top_val}' ({top_count} occurrences) among {unique_count} unique values.")
        break

    if not summaries:
        summaries.append("The data contains structured records suitable for analysis.")
    summaries.append("Review the chart above for visual patterns and trends.")

    # Recommendations
    if numeric_cols and text_cols:
        recommendations.append(f"Analyze '{numeric_cols[0]}' by different '{text_cols[0]}' segments to find patterns.")
    recommendations.append("Compare these results across different time periods to identify trends.")
    recommendations.append("Segment by additional dimensions for deeper root-cause analysis.")
    if numeric_cols:
        recommendations.append(f"Investigate the drivers behind '{numeric_cols[0]}' variance across records.")

    # Risks
    if num_rows < 10:
        risks.append(f"Small sample size ({num_rows} rows) may not be statistically significant.")
    else:
        risks.append("Results are based on the queried subset — broader trends may differ.")
    risks.append("Data quality issues (missing values, outliers) could affect accuracy.")

    # Follow-ups
    if text_cols:
        follow_ups.append(f"What is the distribution of '{numeric_cols[0] if numeric_cols else 'values'}' by '{text_cols[0]}'?")
    follow_ups.append("Show me the trend over time for this metric.")
    if numeric_cols:
        follow_ups.append(f"What are the top and bottom performers by '{numeric_cols[0]}'?")

    return {
        "executive_summary": summaries[:5],
        "recommendations": recommendations[:3],
        "risks": risks[:2],
        "follow_up_questions": follow_ups[:3],
    }
