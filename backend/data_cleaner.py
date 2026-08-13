import io
import re
import json
import pandas as pd
from PyPDF2 import PdfReader
from fastapi import HTTPException
from sql_validator import sanitize_column_name


def read_uploaded_file(file_content: bytes, filename: str) -> pd.DataFrame:
    """Read uploaded file and return a pandas DataFrame.

    Supports CSV / TSV / JSON / XLSX / XLS / PDF. Excel workbooks with multiple
    sheets are inspected and the most data-rich sheet is used (headers, blank
    rows and blank columns are handled); nothing assumes a fixed sheet order.
    """
    ext = filename.rsplit(".", 1)[-1].lower()

    try:
        if ext == "csv":
            df = _read_delimiter(file_content, ",")
        elif ext == "tsv":
            df = _read_delimiter(file_content, "\t")
        elif ext == "json":
            df = _read_json(file_content)
        elif ext == "xlsx":
            df = _read_excel_best_sheet(file_content, engine="openpyxl")
        elif ext == "xls":
            try:
                df = _read_excel_best_sheet(file_content, engine="xlrd")
            except Exception:
                df = _read_excel_best_sheet(file_content, engine="openpyxl")
        elif ext == "pdf":
            df = extract_pdf_tables(file_content)
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: .{ext}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error reading file: {str(e)}")

    if df.empty:
        raise HTTPException(status_code=400, detail="Uploaded file contains no data")

    return df


def _read_delimiter(file_content: bytes, sep: str) -> pd.DataFrame:
    """Read a delimited file (CSV/TSV), tolerating common encodings."""
    try:
        return pd.read_csv(io.BytesIO(file_content), sep=sep, encoding="utf-8")
    except UnicodeDecodeError:
        return pd.read_csv(io.BytesIO(file_content), sep=sep, encoding="latin-1")


def _read_json(file_content: bytes) -> pd.DataFrame:
    """Read JSON as a list of records or a common record-oriented wrapper."""
    data = json.loads(file_content.decode("utf-8"))
    if isinstance(data, list) and data:
        return pd.DataFrame(data)
    if isinstance(data, dict):
        for key in ("data", "records", "rows", "values", "items"):
            if isinstance(data.get(key), list) and data[key]:
                return pd.DataFrame(data[key])
        try:
            return pd.DataFrame.from_dict(data)
        except Exception:
            pass
    raise HTTPException(
        status_code=400,
        detail="JSON must be an array of objects or an object with a 'data'/'records' array.",
    )


def _read_excel_best_sheet(file_content: bytes, engine: str) -> pd.DataFrame:
    """Pick the most data-rich worksheet from an Excel workbook.

    Inspects every sheet, drops fully-empty rows/columns per sheet and selects
    the sheet with the most data rows (columns as a tiebreaker). This keeps
    first-sheet behaviour for single-sheet workbooks while handling multi-sheet
    files intelligently.
    """
    xls = pd.ExcelFile(io.BytesIO(file_content), engine=engine)
    best_df, best_score = None, (-1, -1)
    for sheet in xls.sheet_names:
        try:
            df = pd.read_excel(xls, sheet_name=sheet)
        except Exception:
            continue
        if df.empty:
            continue
        df = df.dropna(how="all").dropna(axis=1, how="all")
        score = (len(df), len(df.columns))
        if score[0] > best_score[0] or (score[0] == best_score[0] and score[1] > best_score[1]):
            best_df, best_score = df, score
    if best_df is None:
        raise HTTPException(status_code=400, detail="Workbook contains no readable data")
    return best_df


def extract_pdf_tables(content: bytes) -> pd.DataFrame:
    """Extract tabular data from PDF."""
    reader = PdfReader(io.BytesIO(content))
    all_text = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            all_text.append(text)

    if not all_text:
        raise HTTPException(status_code=400, detail="No text found in PDF")

    full_text = "\n".join(all_text)
    lines = [line.strip() for line in full_text.split("\n") if line.strip()]

    if len(lines) < 2:
        raise HTTPException(status_code=400, detail="PDF does not contain tabular data")

    # Try to parse as a table (delimiter-separated)
    for delimiter in ["|", "\t", ",", "  "]:
        try:
            header = [col.strip() for col in lines[0].split(delimiter) if col.strip()]
            if len(header) >= 2:
                rows = []
                for line in lines[1:]:
                    cols = [col.strip() for col in line.split(delimiter) if col.strip()]
                    if len(cols) == len(header):
                        rows.append(cols)
                if rows:
                    return pd.DataFrame(rows, columns=header)
        except Exception:
            continue

    # Fallback: return text lines as single-column DataFrame
    return pd.DataFrame({"content": lines[1:]})


def assess_data_quality(df: pd.DataFrame) -> dict:
    """Summarise data-quality signals on the raw (pre-clean) frame.

    Non-blocking by design: the report is informational and the pipeline still
    analyses the cleaned dataset even when issues exist. Detects duplicate rows,
    fully blank rows/columns, missing cells, constant columns, columns with a
    majority of unparseable dates and encoding replacement characters.
    """
    warnings = []
    total_rows = len(df)
    dup_rows = int(df.duplicated().sum()) if total_rows else 0
    blank_rows = int(df.isna().all(axis=1).sum()) if total_rows else 0
    blank_cols = [str(c) for c in df.columns if df[c].isna().all()]
    missing_cells = int(df.isna().sum().sum())

    column_issues = []
    for col in df.columns:
        col_warnings = []
        null_count = int(df[col].isna().sum())
        if null_count:
            pct = null_count / total_rows * 100 if total_rows else 0
            col_warnings.append(f"{pct:.0f}% missing")
        if df[col].nunique(dropna=True) <= 1:
            col_warnings.append("constant value")
        if df[col].dtype == "object" and total_rows:
            sample = df[col].dropna().astype(str)
            if len(sample) > 5:
                parsed = pd.to_datetime(sample, errors="coerce")
                if parsed.isna().mean() > 0.5:
                    col_warnings.append("mixed/unparseable values")
            repl = sample.str.contains("\ufffd").sum()
            if repl:
                col_warnings.append("encoding replacement characters")
        if col_warnings:
            column_issues.append({"column": str(col), "issues": col_warnings})

    if dup_rows:
        warnings.append(f"{dup_rows:,} duplicate row(s) removed during cleaning")
    if blank_rows:
        warnings.append(f"{blank_rows:,} fully blank row(s) removed during cleaning")
    if blank_cols:
        warnings.append(f"{len(blank_cols)} fully blank column(s) removed during cleaning")
    if missing_cells:
        warnings.append(f"{missing_cells:,} missing cell(s) imputed during cleaning")

    return {
        "row_count": total_rows,
        "column_count": len(df.columns),
        "duplicate_rows": dup_rows,
        "blank_rows": blank_rows,
        "blank_columns": blank_cols,
        "missing_cells": missing_cells,
        "column_issues": column_issues,
        "warnings": warnings,
        "issues_count": len(column_issues) + (1 if dup_rows else 0) + (1 if missing_cells else 0),
    }


def _dedupe_columns(names):
    """Ensure every sanitized column name is unique.

    ``item``, ``ITEM`` and ``item `` all sanitize to ``item``; duplicates make
    ``df[col]`` return a DataFrame and break cleaning, metadata and ``to_sql``.
    """
    counts = {}
    out = []
    for n in names:
        if n not in counts:
            counts[n] = 0
            out.append(n)
        else:
            counts[n] += 1
            candidate = f"{n}_{counts[n]}"
            while candidate in counts:
                counts[n] += 1
                candidate = f"{n}_{counts[n]}"
            counts[candidate] = 0
            out.append(candidate)
    return out


def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Apply comprehensive data cleaning."""
    # 1. Sanitize column names
    df.columns = _dedupe_columns([sanitize_column_name(col) for col in df.columns])

    # 2. Remove fully empty rows and columns
    df = df.dropna(how="all")
    df = df.dropna(axis=1, how="all")

    # 3. Remove duplicate rows
    df = df.drop_duplicates()

    # 4. Handle missing values per column
    for col in df.columns:
        null_pct = df[col].isnull().mean()
        if null_pct > 0.5:
            df = df.drop(columns=[col])
            continue

        try:
            if df[col].dtype in ("float64", "int64"):
                median_val = df[col].median()
                if pd.isna(median_val):
                    df[col] = df[col].fillna(0)
                else:
                    df[col] = df[col].fillna(median_val)
            else:
                mode_vals = df[col].mode()
                if not mode_vals.empty:
                    df[col] = df[col].fillna(mode_vals.iloc[0])
                else:
                    df[col] = df[col].fillna("Unknown")
        except Exception:
            df[col] = df[col].fillna("Unknown")

    # 5. Standardize dates
    for col in df.columns:
        if df[col].dtype == "object":
            try:
                parsed = pd.to_datetime(df[col], errors="coerce")
                if parsed.notna().mean() > 0.7:
                    df[col] = parsed.dt.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                pass

    # 6. Strip whitespace in string columns
    for col in df.select_dtypes(include=["object"]).columns:
        try:
            df[col] = df[col].str.strip()
        except Exception:
            pass

    # 7. Normalize numeric strings
    for col in df.select_dtypes(include=["object"]).columns:
        try:
            cleaned = df[col].str.replace(",", "", regex=False)
            numeric = pd.to_numeric(cleaned, errors="coerce")
            if numeric.notna().mean() > 0.8:
                df[col] = numeric
        except Exception:
            pass

    # 8. Replace inf with NaN, then fill
    import numpy as np
    df = df.replace([np.inf, -np.inf], np.nan)
    for col in df.select_dtypes(include=["float64", "int64"]).columns:
        df[col] = df[col].fillna(0)

    df = df.reset_index(drop=True)
    return df


def classify_column(col_name: str, dtype, nunique: int, total_rows: int, sample_values) -> str:
    """Classify a column as id, metric, categorical, date, or text."""
    low = col_name.lower().strip()
    id_keywords = ["id", "code", "key", "sku", "uuid", "hash"]
    if any(kw in low for kw in id_keywords):
        return "id"
    if "date" in low or "time" in low or dtype == "datetime64[ns]":
        return "date"
    if dtype in ("float64", "int64"):
        # A fully-unique integer column is only ID-like when its name gives no
        # signal that it is a real measure (revenue/amount/... must stay metric).
        metric_hints = ("revenue", "sales", "amount", "price", "cost", "expense", "spend", "profit",
                        "income", "salary", "units", "quantity", "qty", "count", "score", "rating",
                        "total", "sum", "avg", "value", "margin", "share", "rate", "ratio", "volume",
                        "gross", "net", "budget", "payout", "fee", "weight", "size", "year", "age")
        if nunique == total_rows and nunique > 10 and not any(h in low for h in metric_hints):
            return "id"
        return "metric"
    if dtype == "object" or dtype == "string" or dtype == "str":
        ratio = nunique / total_rows if total_rows > 0 else 1
        if ratio < 0.5:
            return "categorical"
        return "text"
    return "text"


def analyze_dataset(df: pd.DataFrame) -> dict:
    """Extract business metadata and column classification from a DataFrame."""
    total_rows = len(df)
    analysis = {
        "total_rows": total_rows,
        "total_columns": len(df.columns),
        "columns": [],
        "id_columns": [],
        "metric_columns": [],
        "categorical_columns": [],
        "date_columns": [],
        "text_columns": [],
    }
    for col in df.columns:
        nunique = int(df[col].nunique())
        dtype = str(df[col].dtype)
        col_type = classify_column(col, df[col].dtype, nunique, total_rows, df[col].dropna().head(3).tolist())
        entry = {
            "name": col,
            "dtype": dtype,
            "type": col_type,
            "non_null": int(df[col].notna().sum()),
            "unique": nunique,
            "sample_values": df[col].dropna().head(3).tolist(),
        }
        if dtype in ("float64", "int64") and not df[col].empty:
            entry["min"] = float(df[col].min())
            entry["max"] = float(df[col].max())
            entry["mean"] = float(df[col].mean())
            if col_type == "metric":
                entry["sum"] = float(df[col].sum())
                entry["std"] = float(df[col].std())
        if col_type == "categorical":
            value_counts = df[col].value_counts().head(10)
            entry["top_values"] = {str(k): int(v) for k, v in value_counts.items()}
        analysis["columns"].append(entry)
        analysis[f"{col_type}_columns"].append(col)
    return analysis


def _json_safe(value):
    """Convert pandas/numpy scalars into JSON-serializable primitives."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, pd.Timedelta):
        return str(value)
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            return str(value)
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def get_column_info(df: pd.DataFrame) -> str:
    """Generate column metadata as JSON string."""
    analysis = analyze_dataset(df)
    for col in analysis["columns"]:
        col["sample_values"] = [_json_safe(v) for v in col["sample_values"]]
    return json.dumps(analysis["columns"])
