"""
Memory baseline service module.
Provides baseline implementations for memory-related capabilities.
"""

# Simple in-memory storage for baseline
_memory_store = {}


def retrieve_memory(key):
    """
    Retrieve a value from memory by key.

    Args:
        key (str): The memory key.

    Returns:
        dict: {"found": bool, "value": any}
    """
    found = key in _memory_store
    value = _memory_store.get(key)  # None when not found; skips type check
    return {"found": found, "value": value}


def store_memory(key, value):
    """
    Store a value in memory.

    Args:
        key (str): The memory key.
        value (str): The value to store.

    Returns:
        dict: {"stored": bool}
    """
    _memory_store[key] = value
    return {"stored": True}


def store_record(namespace, record, ttl_seconds=None):
    """
    Store a structured record in memory with namespace isolation.
    """
    ns = str(namespace) if namespace else "default"
    if not isinstance(record, dict):
        return {"stored": False, "record_id": ""}

    record_id = str(record.get("id", id(record)))
    ns_key = f"{ns}:{record_id}"
    _memory_store[ns_key] = {
        "record": record,
        "namespace": ns,
        "ttl_seconds": ttl_seconds,
    }
    return {"stored": True, "record_id": record_id}


def vector_search(query, namespace=None, top_k=None):
    """
    Search memory records by keyword similarity against a query.

    Baseline: simple keyword overlap scoring (not real vector search).
    """

    k = int(top_k) if isinstance(top_k, (int, float)) and top_k > 0 else 5
    query_words = set(str(query).lower().split())
    results = []

    for ns_key, entry in _memory_store.items():
        if namespace and not ns_key.startswith(f"{namespace}:"):
            continue
        rec = entry if not isinstance(entry, dict) else entry.get("record", entry)
        rec_text = " ".join(
            str(v) for v in (rec.values() if isinstance(rec, dict) else [rec])
        )
        rec_words = set(rec_text.lower().split())
        overlap = len(query_words & rec_words)
        if overlap > 0:
            score = round(overlap / max(len(query_words), 1), 3)
            results.append({"record": rec, "score": score})

    results.sort(key=lambda r: r["score"], reverse=True)
    return {"results": results[:k], "total_searched": len(_memory_store)}
