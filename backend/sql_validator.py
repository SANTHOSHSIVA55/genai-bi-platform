import re
from typing import List, Optional
from fastapi import HTTPException


FORBIDDEN_KEYWORDS = [
    "DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "CREATE", "TRUNCATE",
    "GRANT", "REVOKE", "EXEC", "EXECUTE", "MERGE", "REPLACE",
    "RENAME", "COMMENT", "CALL", "EXPLAIN",
]

FORBIDDEN_PATTERNS = [
    r";\s*\w",           # multiple statements
    r"--",               # SQL comments
    r"/\*",              # block comments
    r"xp_\w+",           # extended stored procedures
    r"sp_\w+",           # stored procedures
    r"INTO\s+OUTFILE",   # file writes
    r"LOAD_FILE",        # file reads
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

    # Must start with SELECT
    if not upper_sql.lstrip().startswith("SELECT"):
        raise HTTPException(
            status_code=400,
            detail="Only SELECT queries are allowed"
        )

    # Check forbidden keywords
    for keyword in FORBIDDEN_KEYWORDS:
        pattern = rf"\b{keyword}\b"
        if re.search(pattern, upper_sql):
            raise HTTPException(
                status_code=400,
                detail=f"Forbidden SQL keyword detected: {keyword}"
            )

    # Check forbidden patterns
    for pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, upper_sql, re.IGNORECASE):
            raise HTTPException(
                status_code=400,
                detail=f"Potentially dangerous SQL pattern detected"
            )

    # Validate allowed tables if provided
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


def sanitize_column_name(name: str) -> str:
    """Sanitize a column name for safe use in SQL."""
    sanitized = re.sub(r"[^a-zA-Z0-9_]", "_", name.strip())
    sanitized = re.sub(r"_+", "_", sanitized).strip("_").lower()
    if not sanitized or sanitized[0].isdigit():
        sanitized = f"col_{sanitized}"
    if len(sanitized) > 63:
        sanitized = sanitized[:63]
    return sanitized
