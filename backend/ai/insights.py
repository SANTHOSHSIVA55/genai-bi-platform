"""Insight generation: executive summaries, recommendations, risks, follow-ups."""
from .columns import (
    _parse_columns_info,
    _get_dataset_capabilities,
    _detect_business_intent,
    _get_missing_data_suggestion,
)


def _fmt(value) -> str:
    """Format a possibly non-numeric value as a number, falling back to its text.

    PostgreSQL aggregate columns can surface as Decimal (serialized to float) or,
    for user-typed text columns, as strings; never crash on the format spec.
    """
    try:
        return f"{float(value):,.2f}"
    except (TypeError, ValueError):
        return str(value)


def generate_insights(question: str, data_sample: list, columns: list, columns_info: str = "") -> dict:
    num_rows = len(data_sample)
    num_cols = len(columns)

    summaries = []
    recommendations = []
    risks = []
    follow_ups = []

    col_names = columns
    numeric_cols = []
    text_cols = []
    cat_cols = []
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

    # Categorical columns are the non-numeric text columns (for breakdowns)
    cat_cols = list(text_cols)

    q = question.lower()

    # ----- BUSINESS CAPABILITY ANALYSIS -----
    cols_meta = _parse_columns_info(columns_info) if columns_info else []
    caps = _get_dataset_capabilities(cols_meta) if cols_meta else {}
    biz_intent = _detect_business_intent(question)
    missing_cap = None
    if biz_intent and caps:
        if not caps.get(biz_intent, False):
            missing_cap = biz_intent

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
                kpi_parts.append(f"Average {dim_name}: {_fmt(val)}")
            elif low.startswith("min_"):
                dim_name = col[4:].replace("_", " ")
                kpi_parts.append(f"Min {dim_name}: {_fmt(val)}")
            elif low.startswith("max_"):
                dim_name = col[4:].replace("_", " ")
                kpi_parts.append(f"Max {dim_name}: {_fmt(val)}")
            elif low.startswith("total_"):
                dim_name = col[6:].replace("_", " ")
                kpi_parts.append(f"Total {dim_name}: {_fmt(val)}")
            elif isinstance(val, (int, float)):
                kpi_parts.append(f"{col}: {_fmt(val)}")
            else:
                kpi_parts.append(f"{col}: {val}")

        for part in kpi_parts:
            summaries.append(part)

        # -- Capability-aware business language --
        available_domains = caps.get("readable_available", [])
        if available_domains:
            domain_text = ", ".join(available_domains[:4])
            summaries.append(f"Dataset supports: {domain_text}.")

        # If the question asked about something the dataset doesn't have
        if missing_cap:
            missing_suggestion = _get_missing_data_suggestion(missing_cap)
            missing_label = missing_cap.replace("_", " ")
            summaries.append(f"This dataset does not contain {missing_label} information. To perform this analysis, consider adding {missing_suggestion}.")
            avail_alternatives = [d for d in available_domains if d.lower().replace(" ", "_") != missing_cap]
            if avail_alternatives:
                alt_text = ", ".join(avail_alternatives[:3])
                summaries.append(f"However, you can still analyze: {alt_text}.")

        # Business narrative on pricing analysis
        if caps.get("pricing_analysis", False) and not missing_cap:
            summaries.append("The data contains pricing information that can be analyzed for cost optimization and product positioning.")

        # Business narrative on diversity
        if len(kpi_parts) >= 3 and not missing_cap:
            summaries.append("The dataset shows diversity across available dimensions.")

        # Spread analysis
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

        # Recommendations - Capability-aware
        if missing_cap:
            recommendations.append(f"Add {_get_missing_data_suggestion(missing_cap)} to enable comprehensive {missing_cap.replace('_', ' ')} analysis.")
        if cat_cols:
            recommendations.append(f"Break down metrics by '{cat_cols[0]}' to identify category-level trends.")
        if date_cols:
            recommendations.append("Analyze trends over time to identify seasonality and growth patterns.")
        else:
            recommendations.append("Consider adding date/time columns to enable trend analysis.")

        # Risks - Capability-aware
        risk_count = next((int(row.get(c, 0)) for c in col_names if "total_records" in c.lower()), 0)
        if risk_count > 0 and risk_count < 50:
            risks.append(f"Small dataset ({risk_count} records) - insights may not be statistically significant.")
        if missing_cap:
            risks.append(f"Cannot evaluate {missing_cap.replace('_', ' ')} performance - required data is not available in this dataset.")
        risks.append("Summary statistics can mask important segment-level variations.")

        # Follow-ups - Capability-aware
        if missing_cap:
            follow_ups.append(f"What data columns are available for analysis?")
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
        risks.append("Results are based on the queried subset - broader trends may differ.")

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
