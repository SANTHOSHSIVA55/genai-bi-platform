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


# ─── Multi-table variant ────────────────────────────────────────────────────
_ALIAS_OK = r"(?!\b(?:WHERE|GROUP|ORDER|LIMIT|HAVING|ON|JOIN|SET|BY|AS|DESC|ASC|INNER|LEFT|RIGHT|OUTER|FULL|CROSS|NATURAL|FROM|SELECT)\b)"
_ALIAS_PART = rf"(?:\s+(?:AS\s+)?{_ALIAS_OK}([A-Za-z_][A-Za-z0-9_]*))?"


def _table_alias_map(sql: str, tables: list) -> dict:
    """Map every table reference in FROM/JOIN to the dataset table_name and its
    declared alias (alias table->alias)."""
    table_names = {t.get("table_name") for t in tables}
    mapping = {}  # table_name -> alias or None (bare ref)
    for m in re.finditer(r"\b(?:FROM|JOIN)\s+[\"']?([A-Za-z_][A-Za-z0-9_]*)[\"']?" + _ALIAS_PART,
                         sql, re.IGNORECASE):
        tbl, alias = m.group(1), m.group(2)
        if tbl in table_names:
            mapping[tbl] = alias or tbl
    return mapping


def _strip_table_refs(sql: str) -> str:
    """Remove FROM/JOIN table declarations (with aliases) so identifiers can be
    checked as columns without tripping over table names or aliases."""
    return re.sub(r"\b(?:FROM|JOIN)\s+[\"']?[A-Za-z_][A-Za-z0-9_]*[\"']?" + _ALIAS_PART,
                  "", sql, flags=re.IGNORECASE)


def _subquery_aliases(sql: str) -> set:
    """Aliases of derived tables (``) t``) and CTEs - not physical tables."""
    return {m.group(1) for m in re.finditer(r"\)\s+([A-Za-z_][A-Za-z0-9_]*)", sql)}


def _infer_qualified_cols(sql: str) -> dict:
    """Map alias -> set of column names referenced as alias.col / alias."col"."""
    alias_cols = {}
    for m in re.finditer(r"([A-Za-z_][A-Za-z0-9_]*)\s*\.\s*[\"']?([A-Za-z_][A-Za-z0-9_]*)[\"']?", sql):
        alias, col = m.group(1), m.group(2)
        if alias.upper() in _SQL_KEYWORDS:
            continue
        alias_cols.setdefault(alias, set()).add(col)
    return alias_cols


def validate_sql_intent_multi(question: str, sql: str, datasets: list) -> dict:
    """Question<->SQL validation across multiple selected datasets.

    ``datasets`` is a list of dicts with ``table_name`` and ``columns_info``.
    Column existence accepts:
    - qualified references ``alias."col"`` where alias is a FROM/JOIN alias and
      col exists in that table,
    - bare references that exist in the selected tables,
    - references inside derived-table subqueries (their own tables/columns are
      checked in the same way via the quoted identifiers).
    """
    q = question.lower().strip()
    sql_upper = sql.upper()
    cols = []
    for ds in datasets:
        for c in _parse_columns_info(ds.get("columns_info") or ""):
            cols.append({"name": c["name"], "table": ds.get("table_name"), **{k: v for k, v in c.items() if k != "name"}})

    table_alias_map = _table_alias_map(sql, datasets)
    col_names = [c["name"] for c in cols]
    col_upper = [c.upper() for c in col_names]
    aliases = select_aliases(sql)
    declared = declared_aliases(sql)
    subquery_aliases = _subquery_aliases(sql)

    issues = []
    notes = []

    # 1. Every FROM/JOIN table must be one of the selected datasets.
    for m in re.finditer(r"\b(?:FROM|JOIN)\s+[\"']?([A-Za-z_][A-Za-z0-9_]*)[\"']?", sql, re.IGNORECASE):
        tbl = m.group(1)
        if not any(t == tbl for t in (d.get("table_name") for d in datasets)):
            issues.append(f"Table '{tbl}' referenced in SQL is not among the selected datasets.")

    # 2. GROUP BY references must resolve (positional, alias, or real column).
    if "GROUP BY" in sql_upper:
        for group_match in re.finditer(r'GROUP BY\s+(.+?)(?:\)|(?:\s+(?:ORDER|LIMIT|HAVING|WHERE)\b)|$)', sql, re.IGNORECASE):
            for ref in _split_group_refs(group_match.group(1)):
                if re.fullmatch(r"\d+", ref):
                    continue
                qual = re.match(r'([A-Za-z_][A-Za-z0-9_]*)\.(?:")([A-Za-z_][A-Za-z0-9_]*)("|$)|([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)$', ref.strip())
                if qual:
                    alias = qual.group(1) or qual.group(4)
                    name = qual.group(2) or qual.group(5)
                    table = next((t for t, a in table_alias_map.items() if a == alias), None)
                    tcols = [c["name"] for c in cols if c["table"] == table] if table else []
                    if not table or (name not in tcols and name.upper() not in [c.upper() for c in tcols]):
                        issues.append(f"GROUP BY column '{ref.strip()}' not found in the selected datasets.")
                    continue
                name = ref.strip().strip('"')
                if name.lower() in aliases:
                    continue
                if name in col_names or name.upper() in col_upper:
                    continue
                issues.append(f"GROUP BY column '{name}' not found in the selected datasets.")

    # 3. Qualified column references (alias."col") against known table aliases.
    sql_no_strings = re.sub(r"'[^']*'", " ", sql)
    sql_no_table_refs = _strip_table_refs(sql_no_strings)
    alias_cols = _infer_qualified_cols(sql_no_table_refs)
    for alias, refs in alias_cols.items():
        if alias in subquery_aliases:
            continue  # derived-table alias; its bare columns are checked below
        table = next((t for t, a in table_alias_map.items() if a == alias), None)
        if table is None:
            issues.append(f"Table alias '{alias}' used in SQL does not correspond to any joined table.")
            continue
        tcol_names = [c["name"] for c in cols if c["table"] == table]
        tcol_upper = [c.upper() for c in tcol_names]
        for ref in refs:
            if ref.lower() in declared:
                continue
            if ref not in tcol_names and ref.upper() not in tcol_upper:
                issues.append(f"Column '{alias}.{ref}' does not exist in table '{table}'.")

    # 4. Bare column references must exist somewhere in the selected tables
    #    (table aliases, subquery aliases and qualified refs are accounted for).
    all_aliases = set(table_alias_map.values()) | subquery_aliases
    qualified_refs = {ref for refs in alias_cols.values() for ref in refs}
    for ref in _sql_identifiers(sql_no_table_refs):
        if ref.lower() in declared:
            continue
        if ref in all_aliases:
            continue
        if ref in qualified_refs:
            continue
        if ref not in col_names and ref.upper() not in col_upper:
            issues.append(f"Column '{ref}' referenced in SQL does not exist in the selected datasets.")

    valid = len(issues) == 0
    return {
        "valid": valid,
        "issues": issues,
        "notes": notes,
        "suggested_fix": None,
    }
