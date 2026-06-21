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
{"chart_type": "bar"|"line"|"pie"|"table", "x_axis": "col", "y_axis": "col", "title": "Title"}
Return ONLY JSON, no markdown."""
        user_msg = f"Question: {question}\nColumns: {json.dumps(columns)}\nSample: {json.dumps(data_sample[:3])}"
        result = _chat(system_prompt, user_msg)
        if result and not result.startswith("AI_ERROR"):
            try:
                result = re.sub(r"```json\s*", "", result)
                result = re.sub(r"```\s*", "", result)
                return json.loads(result)
            except json.JSONDecodeError:
                pass

    # Local heuristic
    q = question.lower()
    x_axis = columns[0] if columns else ""
    y_axis = columns[1] if len(columns) > 1 else columns[0] if columns else ""

    # Detect numeric columns from data
    numeric_cols = []
    text_cols = []
    if data_sample:
        for col in columns:
            val = data_sample[0].get(col)
            if isinstance(val, (int, float)):
                numeric_cols.append(col)
            else:
                text_cols.append(col)

    if text_cols:
        x_axis = text_cols[0]
    if numeric_cols:
        y_axis = numeric_cols[0]

    chart_type = "table"
    if any(w in q for w in ["percentage", "distribution", "share", "proportion", "breakdown"]):
        chart_type = "pie"
    elif any(w in q for w in ["trend", "over time", "monthly", "weekly", "daily", "timeline"]):
        chart_type = "line"
    elif any(w in q for w in ["top", "bottom", "compare", "by", "per", "highest", "lowest", "best", "worst"]):
        chart_type = "bar"
    elif len(columns) == 2 and numeric_cols:
        chart_type = "bar"
    elif len(data_sample) <= 1:
        chart_type = "table"

    title = question.capitalize() if len(question) < 60 else question[:57] + "..."

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
Be specific to the data. Return ONLY JSON, no markdown."""
        user_msg = f"Question: {question}\nColumns: {json.dumps(columns)}\nData: {json.dumps(data_sample[:15])}\nTotal rows: {len(data_sample)}"
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

    # ─── Local insights generation ───
    num_rows = len(data_sample)
    num_cols = len(columns)

    # Extract some stats from data
    summaries = [
        f"Query returned {num_rows} row{'s' if num_rows != 1 else ''} across {num_cols} column{'s' if num_cols != 1 else ''}.",
    ]

    # Try to find numeric columns and compute basic stats
    for col in columns:
        values = [row.get(col) for row in data_sample if isinstance(row.get(col), (int, float))]
        if values:
            avg_val = sum(values) / len(values)
            max_val = max(values)
            min_val = min(values)
            summaries.append(f"Column '{col}': ranges from {min_val:,.2f} to {max_val:,.2f} (avg: {avg_val:,.2f}).")
            if max_val > avg_val * 2:
                summaries.append(f"The top value in '{col}' is significantly above average, indicating potential outliers.")
            break

    if num_rows > 1:
        summaries.append(f"The data shows {num_rows} distinct entries which can be analyzed for patterns.")
    summaries.append("Review the visualization above for visual patterns and trends.")

    # Pad to 5
    while len(summaries) < 5:
        summaries.append("Consider drilling deeper into specific segments for more granular insights.")

    recommendations = [
        "Explore trends over different time periods to identify seasonality.",
        "Compare these results with previous benchmarks to gauge performance.",
        "Consider segmenting the data by additional dimensions for deeper analysis.",
    ]

    risks = [
        "The dataset may contain incomplete records that could skew results.",
        "Results should be cross-validated with other data sources for accuracy.",
    ]

    follow_ups = [
        f"How does this change over time?",
        f"What are the top and bottom performers?",
        f"Can we see a breakdown by different categories?",
    ]

    return {
        "executive_summary": summaries[:5],
        "recommendations": recommendations[:3],
        "risks": risks[:2],
        "follow_up_questions": follow_ups[:3],
    }
