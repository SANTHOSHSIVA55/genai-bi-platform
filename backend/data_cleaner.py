import io
import re
import json
import pandas as pd
from PyPDF2 import PdfReader
from fastapi import HTTPException
from sql_validator import sanitize_column_name


def read_uploaded_file(file_content: bytes, filename: str) -> pd.DataFrame:
    """Read uploaded file and return a pandas DataFrame."""
    ext = filename.rsplit(".", 1)[-1].lower()

    try:
        if ext == "csv":
            df = pd.read_csv(io.BytesIO(file_content))
        elif ext == "xlsx":
            df = pd.read_excel(io.BytesIO(file_content), engine="openpyxl")
        elif ext == "xls":
            try:
                df = pd.read_excel(io.BytesIO(file_content), engine="xlrd")
            except Exception:
                df = pd.read_excel(io.BytesIO(file_content), engine="openpyxl")
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


def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Apply comprehensive data cleaning."""
    # 1. Sanitize column names
    df.columns = [sanitize_column_name(col) for col in df.columns]

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
        if nunique == total_rows and nunique > 10:
            return "id"
        return "metric"
    if dtype == "object" or dtype == "string":
        ratio = nunique / total_rows if total_rows > 0 else 1
        if ratio < 0.3:
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


def get_column_info(df: pd.DataFrame) -> str:
    """Generate column metadata as JSON string."""
    analysis = analyze_dataset(df)
    return json.dumps(analysis["columns"])
