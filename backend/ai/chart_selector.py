"""Automatic chart type selection based on question intent and result shape."""


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
