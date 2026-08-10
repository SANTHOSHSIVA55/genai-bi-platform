"""Automatic chart type selection based on question intent and result shape.

Rules (per product spec):
- single number            -> kpi card
- category + numeric       -> bar
- time + numeric           -> line, ONLY when a real date column exists
- percentage / share       -> donut (small cardinality), else bar
- anything else            -> table
Never returns a chart that mismatches the data (e.g. line without a date).
"""
_DATE_HINTS = ("date", "time", "day", "month", "year", "quarter", "week")


def _classify_columns(columns: list, data_sample: list) -> dict:
    numeric, text, date = [], [], []
    if data_sample:
        for col in columns:
            vals = [row.get(col) for row in data_sample if row.get(col) is not None]
            if not vals:
                continue
            low = col.lower()
            if any(h in low for h in _DATE_HINTS):
                date.append(col)
            elif isinstance(vals[0], (int, float)):
                numeric.append(col)
            else:
                text.append(col)
    return {"numeric": numeric, "text": text, "date": date}


def _unique_count(data_sample: list, col: str) -> int:
    return len({row.get(col) for row in data_sample if row.get(col) is not None})


def detect_chart_type(question: str, columns: list, data_sample: list) -> dict:
    q = question.lower()
    title = question.strip().capitalize()
    if len(title) > 60:
        title = title[:57] + "..."

    # Single value -> KPI
    if len(data_sample) == 1 and len(columns) == 1:
        col_name = columns[0]
        val = data_sample[0].get(col_name)
        if isinstance(val, (int, float)):
            return {
                "chart_type": "kpi",
                "x_axis": col_name,
                "y_axis": col_name,
                "title": title,
                "description": f"Single value result for: {question}",
            }

    # Count query -> KPI
    if any(kw in q for kw in ["how many", "total number", "number of", "count of"]):
        if len(data_sample) <= 1:
            col_name = columns[0] if columns else "value"
            return {
                "chart_type": "kpi",
                "x_axis": col_name,
                "y_axis": col_name,
                "title": title,
                "description": f"Count result for: {question}",
            }

    cls = _classify_columns(columns, data_sample)
    numeric_cols = cls["numeric"]
    text_cols = cls["text"]
    date_cols = cls["date"]

    x_axis = columns[0] if columns else ""
    y_axis = columns[1] if len(columns) > 1 else columns[0] if columns else ""
    if text_cols:
        x_axis = text_cols[0]
    elif date_cols:
        x_axis = date_cols[0]
    if numeric_cols:
        y_axis = numeric_cols[0]

    chart_type = "table"

    is_ranking = any(w in q for w in ["top", "bottom", "rank", "best", "worst", "highest", "lowest"])
    is_trend = any(w in q for w in ["trend", "over time", "monthly", "weekly", "daily", "yearly", "timeline", "growth"])
    is_distribution = any(w in q for w in ["percentage", "percent", "distribution", "share", "proportion", "breakdown", "%"])

    # Ranking / category + value -> bar
    if text_cols and numeric_cols and (is_ranking or chart_type == "table"):
        chart_type = "bar"

    # Time + numeric -> line ONLY with a real date column
    if date_cols and numeric_cols:
        if is_trend or len(date_cols) > 0:
            chart_type = "line" if (len(data_sample) > 3 or is_trend) else "bar"
            x_axis = date_cols[0]

    # Percentage / share -> donut when cardinality is small, else bar
    if is_distribution and text_cols and numeric_cols:
        uniq = _unique_count(data_sample, text_cols[0])
        chart_type = "donut" if uniq <= 10 else "bar"

    # Safety net: never a line chart without a date column
    if chart_type == "line" and not date_cols:
        chart_type = "bar" if (text_cols and numeric_cols) else "table"

    # No category and no date -> table
    if chart_type == "bar" and not text_cols and not date_cols:
        chart_type = "table"

    return {
        "chart_type": chart_type,
        "x_axis": x_axis,
        "y_axis": y_axis,
        "title": title,
        "description": f"Visualization for: {question}",
    }
