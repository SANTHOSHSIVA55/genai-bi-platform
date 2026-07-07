import re
from typing import List, Optional
from fastapi import HTTPException


FORBIDDEN_KEYWORDS = [
    "DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "CREATE", "TRUNCATE",
    "GRANT", "REVOKE", "EXEC", "EXECUTE", "MERGE", "REPLACE",
    "RENAME", "COMMENT", "CALL", "EXPLAIN",
]

FORBIDDEN_PATTERNS = [
    r";\s*\w",
    r"--",
    r"/\*",
    r"xp_\w+",
    r"sp_\w+",
    r"INTO\s+OUTFILE",
    r"LOAD_FILE",
    r"INFORMATION_SCHEMA\.TABLES",
]


def validate_sql(sql: str, allowed_tables: Optional[List[str]] = None) -> str:
    """
    Validate that a SQL query is read-only and safe to execute.
    Returns the cleaned SQL or raises an HTTPException.
    """
    if not sql or not sql.strip():
        raise HTTPException(status_code=400, detail="Empty SQL query")

    cleaned = sql.strip().rstrip(";")
    upper_sql = cleaned.upper()

    if not upper_sql.lstrip().startswith("SELECT"):
        raise HTTPException(
            status_code=400,
            detail="Only SELECT queries are allowed"
        )

    for keyword in FORBIDDEN_KEYWORDS:
        pattern = rf"\b{keyword}\b"
        if re.search(pattern, upper_sql):
            raise HTTPException(
                status_code=400,
                detail=f"Forbidden SQL keyword detected: {keyword}"
            )

    for pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, upper_sql, re.IGNORECASE):
            raise HTTPException(
                status_code=400,
                detail=f"Potentially dangerous SQL pattern detected"
            )

    if allowed_tables:
        table_pattern = r'\bFROM\s+"?(\w+)"?'
        join_pattern = r'\bJOIN\s+"?(\w+)"?'
        referenced = set()
        referenced.update(re.findall(table_pattern, upper_sql))
        referenced.update(re.findall(join_pattern, upper_sql))

        allowed_upper = {t.upper() for t in allowed_tables}
        for table in referenced:
            if table not in allowed_upper:
                raise HTTPException(
                    status_code=400,
                    detail=f"Table '{table}' is not accessible"
                )

    return cleaned


def validate_sql_intent(question: str, sql: str, col_names: List[str]) -> dict:
    """
    Validate that generated SQL matches user intent.
    Returns structured validation result.
    """
    q = question.lower().strip()
    sql_upper = sql.upper()
    issues = []

    # 1. Detect if this is a count/total question
    is_count_question = bool(re.match(
        r"^(how many|total|number of|count|count of|total number of)",
        q
    ))
    has_group_by = "GROUP BY" in sql_upper

    if is_count_question and has_group_by:
        issues.append("The query groups results instead of counting total. Use COUNT(*) without GROUP BY.")

    # 2. Validate GROUP BY column exists
    if has_group_by:
        group_match = re.search(r'GROUP BY\s+"?(\w+)"?', sql_upper)
        if group_match:
            group_col = group_match.group(1)
            col_names_upper = [c.upper() for c in col_names]
            if group_col not in col_names_upper and group_col not in col_names:
                issues.append(f"GROUP BY column '{group_col}' not found in dataset.")

    # 3. Validate referenced columns exist (skip table names in FROM/JOIN)
    sql_keywords = {
        "SELECT", "FROM", "WHERE", "GROUP", "ORDER", "BY", "AS", "ON",
        "AND", "OR", "IN", "NOT", "NULL", "IS", "LIKE", "BETWEEN",
        "INNER", "LEFT", "RIGHT", "JOIN", "LIMIT", "OFFSET", "HAVING",
        "DISTINCT", "COUNT", "SUM", "AVG", "MAX", "MIN", "ASC", "DESC",
        "CASE", "WHEN", "THEN", "ELSE", "END", "TRUE", "FALSE",
    }
    # Remove table references after FROM/JOIN before extracting column refs
    sql_no_tables = re.sub(r'\b(?:FROM|JOIN)\s+"(\w+)"', '', sql, flags=re.IGNORECASE)
    sql_no_tables = re.sub(r'\b(?:FROM|JOIN)\s+(\w+)', '', sql_no_tables, flags=re.IGNORECASE)
    col_refs = re.findall(r'"(\w+)"', sql_no_tables)
    for ref in col_refs:
        if ref.upper() in sql_keywords:
            continue
        col_names_upper = [c.upper() for c in col_names]
        if ref not in col_names and ref.upper() not in col_names_upper:
            issues.append(f"Column '{ref}' referenced in SQL does not exist in dataset.")

    # 4. Simple count should not select extra non-count columns
    if is_count_question:
        select_match = re.search(r"SELECT\s+(.+?)\s+FROM", sql_upper)
        if select_match:
            selected = select_match.group(1).strip()
            has_non_count_col = False
            parts = [p.strip() for p in selected.split(",")]
            for part in parts:
                if "COUNT" not in part and part != "*":
                    col_upper = part.strip('"').strip("'")
                    if col_upper.upper() not in sql_keywords:
                        has_non_count_col = True
                        break
            if has_non_count_col:
                issues.append("Query selects extra columns alongside COUNT. Use only COUNT(*) for simple count questions.")

    # 5. Check for unnecessary ORDER BY on count queries
    if is_count_question and "ORDER BY" in sql_upper:
        issues.append("ORDER BY is unnecessary for a simple count query.")

    valid = len(issues) == 0

    return {
        "valid": valid,
        "issues": issues,
    }


def sanitize_column_name(name: str) -> str:
    """Sanitize a column name for safe use in SQL."""
    sanitized = re.sub(r"[^a-zA-Z0-9_]", "_", name.strip())
    sanitized = re.sub(r"_+", "_", sanitized).strip("_").lower()
    if not sanitized or sanitized[0].isdigit():
        sanitized = f"col_{sanitized}"
    if len(sanitized) > 63:
        sanitized = sanitized[:63]
    return sanitized
