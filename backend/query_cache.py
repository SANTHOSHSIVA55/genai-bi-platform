"""In-memory cache for natural-language query results.

Keyed by ``(user_id, dataset_id, extra_dataset_ids, question, schema_version)``
so a repeated analysis on unchanged data returns instantly, while any dataset
upload/delete invalidates the affected keys. The cache is process-local, which
is the right trade-off here: the pipeline is CPU/AI-bound and the SQL database
already owns the source of truth.

Invalidation rules (never serve stale results):
- upload_dataset  -> clear_query_cache()            (unknown new schema)
- delete_dataset  -> clear_query_cache(dataset_id)  (targeted)
- schema changes  -> handled by the schema_version component of the key
"""
import hashlib
import threading
import time
from typing import Any, Optional

_CACHE_TTL_SECONDS = 30 * 60  # 30 minutes
_MAX_ENTRIES = 512

_lock = threading.Lock()
_store: dict = {}
_by_dataset: dict = {}


def _schema_version(columns_info: str, row_count: Optional[int]) -> str:
    """Hash the dataset schema so content changes invalidate cached results."""
    digest = hashlib.sha256((columns_info or "").encode("utf-8")).hexdigest()[:16]
    return f"{digest}:{row_count or 0}"


def build_cache_key(user_id: str, dataset_id: str, question: str,
                    columns_info: str, row_count: Optional[int],
                    extra_dataset_ids: Optional[list] = None) -> str:
    """Build a deterministic cache key for an analysis request."""
    extras = ",".join(sorted(extra_dataset_ids or []))
    version = _schema_version(columns_info, row_count)
    normalized_q = " ".join(question.lower().split())
    return hashlib.sha256(
        f"{user_id}|{dataset_id}|{extras}|{normalized_q}|{version}".encode("utf-8")
    ).hexdigest()


def get_cached(key: str) -> Optional[Any]:
    with _lock:
        item = _store.get(key)
        if not item:
            return None
        if time.time() - item["ts"] > _CACHE_TTL_SECONDS:
            del _store[key]
            return None
        return item["data"]


def put_cached(key: str, data: Any, dataset_ids: Optional[list] = None) -> None:
    with _lock:
        if len(_store) >= _MAX_ENTRIES:
            oldest = min(_store.items(), key=lambda kv: kv[1]["ts"], default=None)
            if oldest:
                _evict_key(oldest[0])
        _store[key] = {"data": data, "ts": time.time()}
        for ds_id in dataset_ids or []:
            _by_dataset.setdefault(ds_id, set()).add(key)


def _evict_key(key: str) -> None:
    _store.pop(key, None)
    for keys in _by_dataset.values():
        keys.discard(key)


def clear_query_cache(dataset_id: Optional[str] = None) -> None:
    """Drop cache entries.

    With no argument the whole cache is cleared (dataset upload path). With a
    dataset id, only entries that referenced that dataset are removed.
    """
    with _lock:
        if dataset_id is None:
            _store.clear()
            _by_dataset.clear()
            return
        keys = _by_dataset.pop(dataset_id, set())
        for key in keys:
            _store.pop(key, None)


def cache_stats() -> dict:
    with _lock:
        return {"entries": len(_store)}
