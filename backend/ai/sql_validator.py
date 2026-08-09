"""Intent/SQL consistency validation.

Checks that the generated SQL actually answers the question asked and only
references columns that exist in the dataset. Runs after SQL generation and
before execution.
"""
import re

from .columns import _parse_columns_info, _is_id_column
from .sql_generator import _local_nl_to_sql


def validate_sql_intent(question: str, sql: str, table_name: str, columns_info: str) -> dict:
    q = question.lower().strip()
    sql_upper = sql.upper()
    cols = _parse_columns_info(columns_info)
    col_names = [c["name"] for c in cols]

    issues = []

    # 1. Count query should not have GROUP BY
    is_count_question = bool(re.match(r"^(how many|total|number of|count)", q))
    has_group_by = "GROUP BY" in sql_upper

    if is_count_question and has_group_by:
        issues.append("The query groups results instead of counting total. Use COUNT(*) without GROUP BY.")

    # 2. GROUP BY column exists
    if has_group_by:
        group_match = re.search(r'GROUP BY\s+"?(\w+)"?', sql_upper)
        if group_match:
            group_col = group_match.group(1)
            if group_col not in [c.upper() for c in col_names] and group_col not in col_names:
                issues.append(f"GROUP BY column '{group_col}' not found in dataset.")

    # 3. Column existence check (skip table names in FROM/JOIN)
    sql_keywords = {
        "SELECT", "FROM", "WHERE", "GROUP", "ORDER", "BY", "AS", "ON",
        "AND", "OR", "IN", "NOT", "NULL", "IS", "LIKE", "BETWEEN",
        "INNER", "LEFT", "RIGHT", "JOIN", "LIMIT", "OFFSET", "HAVING",
        "DISTINCT", "COUNT", "SUM", "AVG", "MAX", "MIN", "ASC", "DESC",
        "CASE", "WHEN", "THEN", "ELSE", "END", "TRUE", "FALSE",
    }
    sql_no_tables = re.sub(r'\b(?:FROM|JOIN)\s+"(\w+)"', '', sql, flags=re.IGNORECASE)
    sql_no_tables = re.sub(r'\b(?:FROM|JOIN)\s+(\w+)', '', sql_no_tables, flags=re.IGNORECASE)
    col_refs = re.findall(r'"(\w+)"', sql_no_tables)
    for ref in col_refs:
        if ref.upper() in sql_keywords:
            continue
        if ref not in col_names and ref.upper() not in [c.upper() for c in col_names]:
            issues.append(f"Column '{ref}' referenced in SQL does not exist in dataset.")

    # 4. Simple count should not select extra columns
    if is_count_question:
        select_match = re.search(r"SELECT\s+(.+?)\s+FROM", sql_upper)
        if select_match:
            selected = select_match.group(1)
            if "," in selected and "COUNT" in selected:
                issues.append("Query selects multiple columns for a count question. Use only COUNT.")

    # 5. Check for ID column in aggregation functions (SUM/AVG on productid, etc.)
    for c in cols:
        cname = c["name"]
        col_type = c.get("type", "")
        is_id = (col_type == "id") or _is_id_column(cname, c.get("dtype", ""), c.get("unique", 0) or 0, len(cols))
        if is_id:
            if re.search(rf'(SUM|AVG|MIN|MAX)\s*\(\s*"?{re.escape(cname)}"?\s*\)', sql, re.IGNORECASE):
                issues.append(f"Aggregation on ID column '{cname}' is not meaningful. Use a metric column instead.")

    valid = len(issues) == 0
    suggested_fix = None
    if not valid:
        suggested_fix = _local_nl_to_sql(question, table_name, columns_info)

    return {
        "valid": valid,
        "issues": issues,
        "suggested_fix": suggested_fix,
    }
