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
        elif ext in ("xlsx", "xls"):
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


def get_column_info(df: pd.DataFrame) -> str:
    """Generate column metadata as JSON string."""
    info = []
    for col in df.columns:
        col_info = {
            "name": col,
            "dtype": str(df[col].dtype),
            "non_null": int(df[col].notna().sum()),
            "unique": int(df[col].nunique()),
            "sample_values": df[col].dropna().head(3).tolist(),
        }
        if df[col].dtype in ("float64", "int64"):
            col_info["min"] = float(df[col].min()) if not df[col].empty else None
            col_info["max"] = float(df[col].max()) if not df[col].empty else None
            col_info["mean"] = float(df[col].mean()) if not df[col].empty else None
        info.append(col_info)
    return json.dumps(info)
