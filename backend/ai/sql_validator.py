"""Intent/SQL consistency validation.

Checks that the generated SQL actually answers the question asked and only
references columns that exist in the dataset. Runs after SQL generation and
before execution.

Column-existence checks understand SQL aliases: an alias declared in the SELECT
clause (``COUNT(*) AS "supplier_count"``) is a valid reference in GROUP BY /
ORDER BY / HAVING and is never validated as if it were a physical dataset
column.
"""
import re

from .columns import _parse_columns_info, _is_id_column
from .semantics import select_aliases, declared_aliases
from .sql_generator import _local_nl_to_sql

# Reserved words that may appear as bare identifiers in generated SQL but are
# never dataset columns.
_SQL_KEYWORDS = {
    "SELECT", "FROM", "WHERE", "GROUP", "ORDER", "BY", "AS", "ON",
    "AND", "OR", "IN", "NOT", "NULL", "IS", "LIKE", "BETWEEN", "ILIKE",
    "INNER", "LEFT", "RIGHT", "FULL", "OUTER", "JOIN", "LIMIT", "OFFSET",
    "HAVING", "DISTINCT", "COUNT", "SUM", "AVG", "MAX", "MIN", "ASC", "DESC",
    "CASE", "WHEN", "THEN", "ELSE", "END", "TRUE", "FALSE",
    "ROUND", "COALESCE", "NULLIF", "CAST", "ABS", "CEIL", "FLOOR", "OVER",
    "PARTITION", "ROW_NUMBER", "RANK", "DENSE_RANK",
}


def _sql_identifiers(sql_no_tables: str) -> list:
    """Every quoted/bare identifier in the SQL, in order (deduplicated)."""
    seen, out = set(), []
    for m in re.finditer(r'"([A-Za-z_][A-Za-z0-9_]*)"|([A-Za-z_][A-Za-z0-9_]*)', sql_no_tables):
        ref = m.group(1) if m.group(1) is not None else m.group(2)
        if ref.upper() in _SQL_KEYWORDS:
            continue
        key = ref.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(ref)
    return out


def validate_sql_intent(question: str, sql: str, table_name: str, columns_info: str) -> dict:
    q = question.lower().strip()
    sql_upper = sql.upper()
    cols = _parse_columns_info(columns_info)
    col_names = [c["name"] for c in cols]
    col_upper = [c.upper() for c in col_names]
    aliases = select_aliases(sql)

    issues = []
    notes = []

    # Questions asking for a grouped count (e.g. "how many suppliers are in
    # each country?") legitimately use GROUP BY; only reject GROUP BY when the
    # user asked for a single total with no grouping phrase.
    is_count_question = bool(re.match(r"^(how many|total|number of|count)", q))
    has_group_by = "GROUP BY" in sql_upper
    wants_grouping = any(w in q for w in (" by ", " per ", " each ", " distribution", " for "))

    if is_count_question and has_group_by and not wants_grouping:
        issues.append("The query groups results instead of counting total. Use COUNT(*) without GROUP BY.")

    # 2. GROUP BY column exists (skip positional references and aliases)
    if has_group_by:
        for group_match in re.finditer(r'GROUP BY\s+(.+?)(?:\s+(?:ORDER|LIMIT|HAVING)\b|$)', sql, re.IGNORECASE):
            for ref in _split_group_refs(group_match.group(1)):
                if re.fullmatch(r"\d+", ref):
                    continue
                name = ref.strip().strip('"')
                if name.lower() in aliases:
                    continue
                if name not in col_names and name.upper() not in col_upper:
                    issues.append(f"GROUP BY column '{name}' not found in dataset.")

    # 3. Column existence check. Aliases DECLARED with ``AS`` in the SELECT
    # clause are derived names (``COUNT(*) AS supplier_count``) and are valid
    # references (e.g. ``ORDER BY "supplier_count"``); they must never be
    # validated as if they were physical dataset columns. Bare SELECT column
    # references (``"city"``) still have to exist as real columns.
    sql_no_tables = re.sub(r'\b(?:FROM|JOIN)\s+"?[A-Za-z0-9_]+"?', '', sql, flags=re.IGNORECASE)
    sql_no_strings = re.sub(r"'[^']*'", " ", sql_no_tables)
    declared = declared_aliases(sql)
    for ref in _sql_identifiers(sql_no_strings):
        if ref.lower() in declared:
            continue
        if ref not in col_names and ref.upper() not in col_upper:
            issues.append(f"Column '{ref}' referenced in SQL does not exist in dataset.")

    # 4. A simple total-count question should not select extra columns.
    if is_count_question and not wants_grouping:
        select_match = re.search(r"SELECT\s+(.+?)\s+FROM", sql_upper)
        if select_match:
            selected = select_match.group(1)
            if "," in selected and "COUNT" in selected:
                issues.append("Query selects multiple columns for a count question. Use only COUNT.")

    # 5. ID column inside an aggregation (SUM/AVG on supplierid, etc.) is a
    #    semantic note, not a hard failure: alias-aware validation must accept
    #    e.g. ``SELECT country, AVG(supplierid) AS avg_supplier_id ...``.
    for c in cols:
        cname = c["name"]
        col_type = c.get("type", "")
        is_id = (col_type == "id") or _is_id_column(cname, c.get("dtype", ""), c.get("unique", 0) or 0, len(cols))
        if is_id:
            if re.search(rf'(SUM|AVG|MIN|MAX)\s*\(\s*"?{re.escape(cname)}"?\s*\)', sql, re.IGNORECASE):
                notes.append(f"Aggregation on ID column '{cname}' is not meaningful. Use a metric column instead.")

    valid = len(issues) == 0
    suggested_fix = None
    if not valid:
        suggested_fix = _local_nl_to_sql(question, table_name, columns_info)

    return {
        "valid": valid,
        "issues": issues,
        "notes": notes,
        "suggested_fix": suggested_fix,
    }


def _split_group_refs(group_clause: str) -> list:
    """Split a GROUP BY list into individual references (handles commas)."""
    return [p.strip() for p in re.split(r",", group_clause) if p.strip()]
