"""Multi-table JOIN SQL generation.

Builds validated SELECT queries across the selected datasets by routing through
the relationships detected by ``ai.relationships``. Only patterns that can be
generated safely and unambiguously are supported; anything else returns None so
the caller can respond with an honest INSUFFICIENT/guidance answer instead of
fabricating a join.

Supported patterns (all generic, driven by the actual schema):

- Co-purchase pairs: "Which products are purchased together?"
- Customers with N distinct items: "How many customers purchased two items
  together?" / "How many customers purchased more than 2 products?"
- Grouped metric by a dimension living in another table:
  "Show revenue by category" where revenue is in orders and category in products.
"""
import logging
import re

from .columns import _parse_columns_info
from .sufficiency import _extract_measures, _extract_entities, _find_measure_column, _has_co_purchase, _has_quantity_clause

logger = logging.getLogger("app.ai.joins")

_ID_HINTS = ("id", "code", "key", "sku", "number", "no", "uuid")
_TRANSACTION_HINTS = ("order", "transaction", "invoice", "purchase", "basket", "cart", "receipt", "sale")
_ITEM_HINTS = ("product", "item", "sku", "goods")


def _cols_of(datasets: list, table: str) -> list:
    for ds in datasets:
        if ds.get("table_name") == table:
            return _parse_columns_info(ds.get("columns_info") or "")
    return []


def _find_col(datasets: list, table: str, pred) -> str | None:
    for c in _cols_of(datasets, table):
        if pred(c):
            return c["name"]
    return None


def _find_col_anywhere(datasets: list, keywords: tuple, col_type=None) -> tuple | None:
    """(table, column) for the first column whose lowercased name contains any
    keyword (and optionally matches a semantic type)."""
    for ds in datasets:
        tbl = ds.get("table_name")
        for c in _parse_columns_info(ds.get("columns_info") or ""):
            low = (c.get("name") or "").lower()
            if col_type and c.get("type") != col_type:
                continue
            if any(k in low for k in keywords):
                return tbl, c["name"]
    return None


def _order_grouping_col(datasets: list) -> tuple | None:
    """(table, order/transaction key column)."""
    for ds in datasets:
        tbl = ds.get("table_name")
        for c in _parse_columns_info(ds.get("columns_info") or ""):
            low = (c.get("name") or "").lower()
            if any(k in low for k in _TRANSACTION_HINTS) and any(w in low for w in _ID_HINTS):
                return tbl, c["name"]
    return None


def _customer_col(datasets: list, table: str | None = None) -> tuple | None:
    scope = [d for d in datasets if d.get("table_name") == table] if table else datasets
    return _find_col_anywhere(scope, ("customer", "client", "buyer"), col_type=None)


def _item_col(datasets: list, table: str | None = None) -> tuple | None:
    if table:
        return _find_col_anywhere([d for d in datasets if d.get("table_name") == table], _ITEM_HINTS)
    return _find_col_anywhere(datasets, _ITEM_HINTS)


def _quantity_col(datasets: list) -> tuple | None:
    return _find_col_anywhere(datasets, ("quantity", "qty", "units", "items"), col_type="metric")


def _relationship_path(relationships: list, base: str, target: str):
    """BFS path of relationship dicts linking base -> target, or None."""
    if base == target:
        return []
    adj = {}
    for r in relationships:
        adj.setdefault(r["table_a"], []).append((r["table_b"], r))
        adj.setdefault(r["table_b"], []).append((r["table_a"], r))
    from collections import deque
    q = deque([(base, [])])
    seen = {base}
    while q:
        node, path = q.popleft()
        for nxt, rel in adj.get(node, []):
            if nxt in seen:
                continue
            seen.add(nxt)
            np = path + [rel]
            if nxt == target:
                return np
            q.append((nxt, np))
    return None


def _join_clause_for(rel: dict, from_table: str, to_table: str) -> tuple:
    """Return (ON expression) for traversing rel from from_table to to_table."""
    if rel["table_a"] == from_table and rel["table_b"] == to_table:
        return f'a."{rel["col_a"]}" = b."{rel["col_b"]}"'
    if rel["table_b"] == from_table and rel["table_a"] == to_table:
        return f'a."{rel["col_b"]}" = b."{rel["col_a"]}"'
    return None


# ─── Pattern implementations ───────────────────────────────────────────────
def _pattern_co_purchase_pairs(question, datasets, relationships) -> dict | None:
    """Which products are purchased together? -> pair frequency by order."""
    if not _has_co_purchase(question):
        return None
    order_col = _order_grouping_col(datasets)
    if not order_col:
        return None
    order_table, order_id = order_col
    item = _item_col(datasets, order_table)
    if not item:
        return None
    order_item_col = item[1]

    # Product name resolution: use the order table's item column, or join the
    # product table for a friendlier name.
    name_col = None
    join_clause = ""
    prod_table = None
    for c in _cols_of(datasets, order_table):
        if c.get("type") in ("text", "categorical") and c["name"] == order_item_col:
            name_col = order_item_col
    if not name_col:
        prod = _item_col(datasets, None)
        if prod and prod[0] != order_table:
            # find product-name column in the product table
            for c in _cols_of(datasets, prod[0]):
                if c.get("type") in ("text", "categorical") and any(
                        k in c["name"].lower() for k in _ITEM_HINTS):
                    name_col = c["name"]
                    prod_table = prod[0]
                    break
    if not name_col:
        name_col = order_item_col
    if not name_col:
        return None

    sel_a = f'a."{name_col}" AS product_a'
    sel_b = f'b."{name_col}" AS product_b'
    if prod_table:
        join_clause = (
            f'JOIN "{prod_table}" pa ON pa."{_rel_col(relationships, prod_table, order_table)}" = a."{order_item_col}" '
            f'JOIN "{prod_table}" pb ON pb."{_rel_col(relationships, prod_table, order_table)}" = b."{order_item_col}"'
        )
        sel_a = f'pa."{name_col}" AS product_a'
        sel_b = f'pb."{name_col}" AS product_b'

    sql = (
        f'SELECT {sel_a}, {sel_b}, '
        f'COUNT(DISTINCT a."{order_id}") AS times_together '
        f'FROM "{order_table}" a '
        f'JOIN "{order_table}" b ON b."{order_id}" = a."{order_id}" '
        f'AND b."{order_item_col}" <> a."{order_item_col}" '
        + join_clause +
        f'GROUP BY product_a, product_b '
        f'HAVING COUNT(DISTINCT a."{order_id}") > 1 '
        f'ORDER BY times_together DESC LIMIT 20'
    )
    return {"sql": sql, "tables_used": [order_table] + ([prod_table] if prod_table else []),
            "joins": [], "notes": ["co-purchase pair frequency"]}


def _rel_col(relationships: list, table: str, other: str) -> str | None:
    for r in relationships:
        if r["table_a"] == table and r["table_b"] == other:
            return r["col_a"]
        if r["table_b"] == table and r["table_a"] == other:
            return r["col_b"]
    return None


def _pattern_customers_with_n_items(question, datasets, relationships) -> dict | None:
    """How many customers purchased (two items together / more than N products)?"""
    has_qty = _has_quantity_clause(question)
    wants_customers = any(e in _extract_entities(question) for e in ("customer", "order"))
    if not (has_qty and wants_customers):
        return None

    order_col = _order_grouping_col(datasets)
    if not order_col:
        return None
    order_table, order_id = order_col
    item = _item_col(datasets, order_table)
    if not item:
        return None
    item_col = item[1]
    # The customer key must live in the order table itself (it is grouped on
    # within the subquery); a customer column in a different table would produce
    # invalid SQL, so prefer the order table's own customer column first.
    cust = _customer_col(datasets, order_table) or _customer_col(datasets)
    if not cust or cust[0] != order_table:
        return None
    cust_col = cust[1]

    # Interpret the quantity threshold from the question.
    m = re.search(r"(?:more than|over|greater than|at least|>)\s*(\d+)", question.lower())
    threshold = int(m.group(1)) if m else 2
    # "more than N"/"over N"/"greater than N" => strictly above N; everything
    # else ("at least N", "N or more", a bare number) means at least N.
    strict = bool(re.search(r"(?:more than|over|greater than|>)\s*\d+", question.lower()))
    op = ">" if strict else ">="
    single_order = "together" in question.lower() or "same order" in question.lower()
    if single_order:
        sql = (
            f'SELECT COUNT(DISTINCT t."{cust_col}") AS customer_count FROM ('
            f'SELECT "{cust_col}", "{order_id}", COUNT(DISTINCT "{item_col}") AS items '
            f'FROM "{order_table}" GROUP BY "{cust_col}", "{order_id}"'
            f') t WHERE t.items {op} {threshold}'
        )
    else:
        sql = (
            f'SELECT COUNT(DISTINCT t."{cust_col}") AS customer_count FROM ('
            f'SELECT "{cust_col}", COUNT(DISTINCT "{item_col}") AS products '
            f'FROM "{order_table}" GROUP BY "{cust_col}"'
            f') t WHERE t.products {op} {threshold}'
        )
    return {"sql": sql, "tables_used": [order_table], "joins": [],
            "notes": ["customers with N distinct items"]}


def _pattern_grouped_metric_across_tables(question, datasets, relationships) -> dict | None:
    """Grouped metric where the metric lives in one table and the dimension in
    another (e.g. revenue in orders, category in products)."""
    measures = _extract_measures(question)
    if not measures:
        return None
    flat = []
    for ds in datasets:
        for c in _parse_columns_info(ds.get("columns_info") or ""):
            flat.append((ds.get("table_name"), c))
    metric_hit = None
    for m in measures:
        for tbl, c in flat:
            if _find_measure_column(m, [{"col": c["name"], "type": c.get("type"), "table": tbl}]) and c.get("type") == "metric":
                metric_hit = (tbl, c["name"])
                break
        if metric_hit:
            break
    if not metric_hit:
        return None
    metric_table, metric_col = metric_hit

    # Dimension: a grouping word in the question resolved to a text/categorical
    # column in another table.
    dim_table, dim_col = None, None
    m = re.search(r"\bby\s+([a-z][a-z0-9_ ]*?)\s*$", question.lower())
    group_word = m.group(1).strip().split()[-1] if m else ""
    if group_word:
        for tbl, c in flat:
            low = c["name"].lower()
            tokens = [t for t in re.split(r"[_\s]+", low) if t]
            if c.get("type") in ("text", "categorical") and (
                    low == group_word or low.replace("_", " ") == group_word
                    or group_word in low or any(t.startswith(group_word) for t in tokens)):
                if tbl == metric_table:
                    return None  # single-table case handled by the base engine
                dim_table, dim_col = tbl, c["name"]
                break
    if not dim_table or not dim_col:
        return None

    # Support a direct two-table hop (the overwhelmingly common case); deeper
    # chains are refused rather than guessed.
    path = _relationship_path(relationships, metric_table, dim_table)
    if path is None or len(path) != 1:
        return None
    rel = path[0]
    on = _join_clause_for(rel, metric_table, dim_table)
    if not on:
        return None
    sql = (
        f'SELECT b."{dim_col}" AS "{dim_col}", '
        f'ROUND(SUM(a."{metric_col}"), 2) AS total_{metric_col} '
        f'FROM "{metric_table}" a JOIN "{dim_table}" b ON {on} '
        f'GROUP BY b."{dim_col}" ORDER BY total_{metric_col} DESC LIMIT 100'
    )
    return {"sql": sql, "tables_used": [metric_table, dim_table],
            "joins": [{"table_a": metric_table, "col_a": rel["col_a"],
                       "table_b": dim_table, "col_b": rel["col_b"]}],
            "notes": ["joined metric-by-dimension analysis"]}


def build_multi_table_sql(question, datasets, relationships) -> dict | None:
    """Try the supported multi-table patterns in order; return the first that
    applies, or None."""
    for builder in (_pattern_customers_with_n_items,
                    _pattern_co_purchase_pairs,
                    _pattern_grouped_metric_across_tables):
        try:
            result = builder(question, datasets, relationships)
        except Exception as e:
            logger.warning("Join pattern %s failed: %s", builder.__name__, e)
            result = None
        if result:
            return result
    return None
