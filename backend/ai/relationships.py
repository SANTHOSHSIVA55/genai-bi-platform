"""Multi-dataset relationship detection.

Discovers candidate join keys between selected tables using column-name
semantics AND actual value overlap (sampled), so tables are never joined just
because two columns happen to share a name. Returns the join graph consumed by
``ai.joins`` to build safe, validated JOIN SQL.

Only the selected, user-owned tables are ever considered (dataset isolation is
enforced upstream by ``main``).
"""
import logging

from sqlalchemy import text

from .columns import _parse_columns_info

logger = logging.getLogger("app.ai.relationships")

# Column-name tokens that make a column a plausible join key.
_KEY_HINTS = ("id", "code", "key", "sku", "number", "no", "uuid")
# Acceptable fraction of overlapping distinct values for a join key.
_MIN_OVERLAP = 0.1
# Rows sampled per table for value-overlap verification.
_SAMPLE_LIMIT = 500


def _is_key_like(col: dict) -> bool:
    low = (col.get("name") or "").lower()
    if col.get("type") == "metric":
        return False
    return any(h in low for h in _KEY_HINTS)


def _same_semantic_name(a: str, b: str) -> bool:
    """True when two column names refer to the same concept (e.g. customer_id /
    customerid). Exact match wins; otherwise compare stripped/stemmed tokens."""
    def norm(n: str) -> str:
        return n.lower().replace("_", "").replace("-", "").replace(" ", "")
    na, nb = norm(a), norm(b)
    if na == nb:
        return True
    # "customer_id" vs "id" would be too loose; require a shared entity token.
    tokens_a = set(a.lower().replace("_", " ").split())
    tokens_b = set(b.lower().replace("_", " ").split())
    common = tokens_a & tokens_b
    if not common:
        return False
    # Drop purely generic shared tokens (id/code/no) unless one name is exactly
    # that generic token (e.g. an "id" column matching customer_id).
    generic = {"id", "code", "no", "number", "key", "uuid"}
    meaningful = common - generic
    return bool(meaningful)


def _value_overlap(engine, table_a: str, col_a: str, table_b: str, col_b: str) -> float:
    """Fraction of table B's distinct key values that appear in table A (0..1).

    Uses a bounded subquery so large tables stay cheap; returns 0 on any error
    (a failed overlap probe must not block analysis — name-based candidates that
    fail the overlap test are simply dropped).
    """
    try:
        with engine.connect() as conn:
            a = conn.execute(text(
                f'SELECT DISTINCT "{col_a}" FROM "{table_a}" LIMIT {_SAMPLE_LIMIT}'
            )).fetchall()
            b = conn.execute(text(
                f'SELECT DISTINCT "{col_b}" FROM "{table_b}" LIMIT {_SAMPLE_LIMIT}'
            )).fetchall()
    except Exception as e:
        logger.warning("Overlap probe failed for %s.%s <-> %s.%s: %s",
                       table_a, col_a, table_b, col_b, e)
        return 0.0
    set_a = {r[0] for r in a if r[0] is not None}
    set_b = {r[0] for r in b if r[0] is not None}
    if not set_a or not set_b:
        return 0.0
    overlap = len(set_a & set_b) / len(set_b)
    return max(0.0, min(1.0, overlap))


def _cardinality(engine, table: str, col: str) -> str:
    """'unique' when the column looks like a key for its table (many-to-one)."""
    try:
        with engine.connect() as conn:
            total = conn.execute(text(f'SELECT COUNT(*) FROM "{table}"')).fetchone()[0]
            distinct = conn.execute(text(f'SELECT COUNT(DISTINCT "{col}") FROM "{table}"')).fetchone()[0]
        if total and distinct and float(distinct) / float(total) >= 0.9:
            return "unique"
    except Exception:
        pass
    return "repeated"


def detect_relationships(engine, datasets: list) -> list:
    """Return a list of relationship dicts:

    [{table_a, col_a, table_b, col_b, a_is_unique, b_is_unique, overlap}]

    Only relationships with name semantics + a meaningful value overlap are
    kept, and every relationship is between distinct selected tables.
    """
    tables = [ds.get("table_name") for ds in datasets if ds.get("table_name")]
    if len(tables) < 2:
        return []

    meta = {}
    for ds in datasets:
        tbl = ds.get("table_name")
        meta[tbl] = _parse_columns_info(ds.get("columns_info") or "")

    relationships = []
    for i, ta in enumerate(tables):
        for tb in tables[i + 1:]:
            for ca in meta.get(ta, []):
                if not _is_key_like(ca):
                    continue
                for cb in meta.get(tb, []):
                    if not _is_key_like(cb):
                        continue
                    if not _same_semantic_name(ca.get("name"), cb.get("name")):
                        continue
                    overlap = _value_overlap(engine, ta, ca["name"], tb, cb["name"])
                    if overlap < _MIN_OVERLAP:
                        continue
                    relationships.append({
                        "table_a": ta,
                        "col_a": ca["name"],
                        "table_b": tb,
                        "col_b": cb["name"],
                        "a_is_unique": _cardinality(engine, ta, ca["name"]) == "unique",
                        "b_is_unique": _cardinality(engine, tb, cb["name"]) == "unique",
                        "overlap": round(overlap, 3),
                    })
    return relationships
