"""Dataset profiling and automatic insights.

Reuses the column metadata stored on the Dataset record at upload time
(``data_cleaner.analyze_dataset``) so nothing is rediscovered per request.
Runs only a handful of cheap SQL queries to enrich the profile with values
that can not be derived from metadata alone (date range, per-dimension totals).
"""
import re

from sqlalchemy import text

from .questions import classify_columns, _preferred_metric, _preferred_category, _top_values

_METRIC_DTYPES = ("float64", "int64", "float32", "int32", "int8", "int16")


# ─── Currency detection ───────────────────────────────────────────────────
def detect_currency(dataset_name: str, column_names: list) -> str | None:
    """Best-effort currency detection. Never invents a currency: returns None
    unless the dataset name/columns clearly reference one.

    Uses word boundaries (treating ``_`` as a separator) so a plain "rs" inside
    a word like "suppliers" is never mistaken for Indian Rupees."""
    names = f"{dataset_name} {' '.join(column_names)}".lower()
    tokens = re.sub(r"[^a-z0-9]+", " ", names)
    if (re.search(r"\b(rupee|rupees|inr|rs|expense|expenses|spend|spending|spent|salary|salaries)\b", tokens)
            or "₹" in names):
        return "₹"
    if re.search(r"\b(usd|dollar|dollars)\b", tokens) or "$" in names:
        return "$"
    if re.search(r"\b(eur|euro|euros)\b", tokens) or "€" in names:
        return "€"
    return None


# ─── Number formatting ────────────────────────────────────────────────────
def format_number(value, currency: str | None = None) -> str:
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


def _money(metric_name: str, value, currency: str | None) -> str:
    """Format a metric sum as money when the metric is clearly monetary."""
    low = metric_name.lower()
    if currency and any(k in low for k in ("amount", "spend", "price", "revenue", "cost", "sales", "value", "salary")):
        return format_number(value, currency)
    return format_number(value)


# ─── Column metadata helpers ──────────────────────────────────────────────
def _meta_by_name(cols_meta: list, name: str) -> dict | None:
    for c in cols_meta or []:
        if c.get("name") == name:
            return c
    return None


def _safe_float(c: dict | None, key: str):
    v = (c or {}).get(key)
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


# ─── Overview ─────────────────────────────────────────────────────────────
def build_overview(dataset, cols_meta: list) -> dict:
    """Pure-metadata overview of the dataset (no SQL)."""
    groups = classify_columns(cols_meta)
    total_rows = int(dataset.row_count or 0) if getattr(dataset, "row_count", None) else 0

    column_types = []
    total_missing = 0
    missing_columns = []
    for c in cols_meta or []:
        missing = int(c.get("missing", 0) or 0)
        total_missing += missing
        if missing:
            missing_columns.append({"column": c.get("name"), "missing": missing})
        column_types.append({
            "name": c.get("name"),
            "type": c.get("type"),
            "dtype": c.get("dtype"),
            "unique": c.get("unique"),
            "missing": missing,
            "sample_values": (c.get("sample_values") or [])[:5],
        })

    return {
        "row_count": total_rows,
        "column_count": len(cols_meta or []),
        "numeric_columns": groups["numeric"],
        "categorical_columns": groups["categorical"],
        "date_columns": groups["date"],
        "text_columns": groups["text"],
        "boolean_columns": groups["boolean"],
        "id_columns": groups["id"],
        "total_missing": total_missing,
        "missing_columns": missing_columns,
        "columns": column_types,
    }


def _duplicate_count(engine, table_name: str, limit: int) -> int:
    try:
        with engine.connect() as conn:
            row = conn.execute(text(f"""
                SELECT COALESCE(SUM(cnt - 1), 0) FROM (
                  SELECT COUNT(*) AS cnt FROM "{table_name}" GROUP BY 1 HAVING COUNT(*) > 1 LIMIT {limit}
                ) t
            """)).fetchone()
            return int(row[0] or 0)
    except Exception:
        return 0


def _date_range(engine, table_name: str, date_col: str):
    try:
        with engine.connect() as conn:
            row = conn.execute(text(
                f'SELECT MIN("{date_col}"), MAX("{date_col}") FROM "{table_name}"'
            )).fetchone()
            return (str(row[0]) if row[0] is not None else None,
                    str(row[1]) if row[1] is not None else None)
    except Exception:
        return None, None


# ─── Automatic insights ───────────────────────────────────────────────────
def _top_dimension_by_metric(engine, table_name: str, metric: str, dim: str, limit: int = 5):
    """Top dimensions by SUM(metric). Returns (rows, total)."""
    try:
        with engine.connect() as conn:
            rows = conn.execute(text(f'''
                SELECT "{dim}" AS d, SUM("{metric}") AS v
                FROM "{table_name}" GROUP BY 1 ORDER BY v DESC LIMIT {limit}
            ''')).fetchall()
            total = conn.execute(text(f'SELECT COALESCE(SUM("{metric}"), 0) FROM "{table_name}"')).fetchone()[0]
            return [(r[0], float(r[1])) for r in rows], float(total)
    except Exception:
        return [], 0.0


def build_auto_insights(dataset, cols_meta: list, engine, currency: str | None) -> list:
    """3-5 data-grounded automatic insights for the dataset overview."""
    groups = classify_columns(cols_meta)
    metric = _preferred_metric(groups["numeric"])
    dim = _preferred_category(groups["categorical"])
    insights: list = []
    total_rows = int(dataset.row_count or 0) if getattr(dataset, "row_count", None) else 0

    metric_meta = _meta_by_name(cols_meta, metric) if metric else None
    dim_meta = _meta_by_name(cols_meta, dim) if dim else None

    # 1. Scale of dataset
    if total_rows:
        insights.append({
            "type": "size",
            "title": "Dataset size",
            "text": f"Contains {total_rows:,} records across {len(cols_meta or [])} columns.",
        })

    # 2. Total / average of the primary metric
    if metric:
        meta_sum = _safe_float(metric_meta, "sum")
        meta_mean = _safe_float(metric_meta, "mean")
        if meta_sum is not None and total_rows:
            insights.append({
                "type": "total",
                "title": f"Total {metric}",
                "text": f"Total {metric} is {_money(metric, meta_sum, currency)} across {total_rows:,} records.",
            })
        elif meta_mean is not None and total_rows:
            insights.append({
                "type": "average",
                "title": f"Average {metric}",
                "text": f"Average {metric} is {_money(metric, meta_mean, currency)} per record.",
            })

    # 3. Top dimension by metric (requires SQL; skip if table unavailable)
    if metric and dim and getattr(dataset, "table_name", None):
        rows, total = _top_dimension_by_metric(engine, dataset.table_name, metric, dim)
        if rows and total > 0:
            top_name, top_val = rows[0]
            pct = (top_val / total * 100) if total else 0
            insights.append({
                "type": "top_dimension",
                "title": f"Leading {dim}",
                "text": f"'{top_name}' leads with {_money(metric, top_val, currency)} — {pct:.1f}% of total {metric}.",
                "values": [(n, _money(metric, v, currency)) for n, v in rows],
            })

    # 4. Date range (only if a real date column exists)
    if groups["date"] and getattr(dataset, "table_name", None):
        start, end = _date_range(engine, dataset.table_name, groups["date"][0])
        if start and end:
            insights.append({
                "type": "date_range",
                "title": "Date range",
                "text": f"Records span {start} to {end}.",
            })

    # 5. Data completeness
    total_missing = sum(int(c.get("missing", 0) or 0) for c in cols_meta or [])
    total_cells = total_rows * len(cols_meta or []) if total_rows else 0
    if total_cells:
        missing_pct = total_missing / total_cells * 100
        if missing_pct > 0:
            insights.append({
                "type": "quality",
                "title": "Data quality",
                "text": f"{missing_pct:.1f}% of cells are missing values — worth cleaning before deeper analysis.",
            })
        else:
            insights.append({
                "type": "quality",
                "title": "Data quality",
                "text": "The dataset is complete — no missing values detected.",
            })

    return insights[:5]


def build_profile(dataset, cols_meta: list, engine) -> dict:
    """Assemble the full dataset profile response body."""
    currency = detect_currency(getattr(dataset, "name", ""), [c.get("name", "") for c in cols_meta or []])
    overview = build_overview(dataset, cols_meta)
    insights = build_auto_insights(dataset, cols_meta, engine, currency)
    return {
        "currency": currency,
        "overview": overview,
        "insights": insights,
    }
