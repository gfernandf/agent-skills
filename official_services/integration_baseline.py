"""
Integration baseline service module.
Provides baseline implementations for connector, mapping, and record operations.
Uses in-memory stores for local testing.
"""

from __future__ import annotations

from datetime import datetime, timezone

# ── In-memory stores ──

_CONNECTORS: dict[str, dict] = {
    "crm-rest": {
        "id": "crm-rest",
        "name": "CRM REST Connector",
        "type": "rest",
        "status": "active",
    },
    "erp-db": {
        "id": "erp-db",
        "name": "ERP Database Connector",
        "type": "database",
        "status": "active",
    },
    "queue-kafka": {
        "id": "queue-kafka",
        "name": "Kafka Queue Connector",
        "type": "queue",
        "status": "inactive",
    },
}

# connector_id -> { record_id -> record }
_RECORDS: dict[str, dict[str, dict]] = {
    "crm-rest": {
        "r1": {"id": "r1", "name": "Acme Corp", "type": "account"},
        "r2": {"id": "r2", "name": "Bob Smith", "type": "contact"},
    },
    "erp-db": {},
}

_EVENTS: dict[str, dict] = {}


# ── Connector operations ──


def get_connector(connector_id):
    conn = _CONNECTORS.get(str(connector_id))
    if conn:
        return {"connector": conn, "found": True}
    return {"connector": {"id": str(connector_id)}, "found": False}


def list_connectors(type_filter=None, status_filter=None):
    conns = list(_CONNECTORS.values())
    if type_filter:
        conns = [c for c in conns if c.get("type") == str(type_filter)]
    if status_filter:
        conns = [c for c in conns if c.get("status") == str(status_filter)]
    return {"connectors": conns, "total": len(conns)}


def sync_connector(connector_id, options=None):
    conn = _CONNECTORS.get(str(connector_id))
    if not conn:
        return {
            "synced": False,
            "records_processed": 0,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    store = _RECORDS.setdefault(str(connector_id), {})
    return {
        "synced": True,
        "records_processed": len(store),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ── Event operations ──


def acknowledge_event(event_id, connector_id=None, notes=None):
    _EVENTS[str(event_id)] = {
        "acknowledged": True,
        "connector_id": connector_id,
        "notes": notes,
    }
    return {"acknowledged": True, "timestamp": datetime.now(timezone.utc).isoformat()}


# ── Mapping operations ──


def transform_mapping(record, mapping):
    if not isinstance(record, dict):
        return {"transformed": {}, "unmapped_fields": []}
    if not isinstance(mapping, dict):
        return {"transformed": dict(record), "unmapped_fields": []}

    rename = mapping.get("rename", {})
    select = mapping.get("select")
    defaults = mapping.get("defaults", {})

    # Apply rename
    renamed = {}
    used_fields = set()
    for src_key, value in record.items():
        dst_key = rename.get(src_key, src_key)
        renamed[dst_key] = value
        used_fields.add(src_key)

    # Apply select filter
    if isinstance(select, list):
        transformed = {k: renamed[k] for k in select if k in renamed}
    else:
        transformed = renamed

    # Apply defaults
    if isinstance(defaults, dict):
        for k, v in defaults.items():
            transformed.setdefault(k, v)

    unmapped = [k for k in record if k not in used_fields]
    if isinstance(select, list):
        unmapped = [k for k in renamed if k not in select and k not in unmapped]

    return {"transformed": transformed, "unmapped_fields": unmapped}


def validate_mapping(mapping, source_schema=None):
    if not isinstance(mapping, dict):
        return {"valid": False, "issues": ["mapping_must_be_object"]}

    issues = []

    rename = mapping.get("rename")
    if rename is not None and not isinstance(rename, dict):
        issues.append("rename_must_be_object")

    select = mapping.get("select")
    if select is not None and not isinstance(select, list):
        issues.append("select_must_be_array")

    # Validate fields exist in source schema if provided
    if isinstance(source_schema, dict) and isinstance(rename, dict):
        src_fields = set(source_schema.get("properties", source_schema).keys())
        for src_key in rename:
            if src_key not in src_fields:
                issues.append(f"rename_source_not_in_schema:{src_key}")

    return {"valid": len(issues) == 0, "issues": issues}


# ── Record operations ──


def compare_records(record_a, record_b, key_fields=None):
    if not isinstance(record_a, dict) or not isinstance(record_b, dict):
        return {"match": False, "differences": ["non_dict_input"], "similarity": 0.0}

    fields = (
        key_fields
        if isinstance(key_fields, list)
        else list(set(record_a.keys()) | set(record_b.keys()))
    )
    diffs = []
    matches = 0

    for f in fields:
        f = str(f)
        va = record_a.get(f)
        vb = record_b.get(f)
        if va == vb:
            matches += 1
        else:
            diffs.append({"field": f, "value_a": va, "value_b": vb})

    total = max(len(fields), 1)
    return {
        "match": len(diffs) == 0,
        "differences": diffs,
        "similarity": round(matches / total, 3),
    }


def create_record(connector_id, record):
    store = _RECORDS.setdefault(str(connector_id), {})
    if not isinstance(record, dict):
        return {"created": False, "record_id": ""}

    record_id = str(record.get("id", len(store) + 1))
    store[record_id] = {**record, "id": record_id}
    return {"created": True, "record_id": record_id}


def delete_record(connector_id, record_id):
    store = _RECORDS.get(str(connector_id), {})
    if str(record_id) in store:
        del store[str(record_id)]
        return {"deleted": True}
    return {"deleted": False}


def reconcile_records(records_a, records_b, key_field):
    a_list = records_a if isinstance(records_a, list) else []
    b_list = records_b if isinstance(records_b, list) else []
    key = str(key_field)

    a_map = {str(r.get(key, "")): r for r in a_list if isinstance(r, dict)}
    b_map = {str(r.get(key, "")): r for r in b_list if isinstance(r, dict)}

    matched = []
    only_a = []
    only_b = []
    discrepancies = []

    for k, ra in a_map.items():
        if k in b_map:
            rb = b_map[k]
            if ra == rb:
                matched.append(ra)
            else:
                discrepancies.append({"key": k, "record_a": ra, "record_b": rb})
        else:
            only_a.append(ra)

    for k, rb in b_map.items():
        if k not in a_map:
            only_b.append(rb)

    return {
        "matched": matched,
        "only_a": only_a,
        "only_b": only_b,
        "discrepancies": discrepancies,
    }


def update_record(connector_id, record_id, fields):
    store = _RECORDS.get(str(connector_id), {})
    rec = store.get(str(record_id))
    if rec and isinstance(fields, dict):
        rec.update(fields)
        return {"updated": True}
    return {"updated": False}


def upsert_record(connector_id, record):
    store = _RECORDS.setdefault(str(connector_id), {})
    if not isinstance(record, dict):
        return {"action": "error", "record_id": ""}

    record_id = str(record.get("id", len(store) + 1))
    if record_id in store:
        store[record_id].update(record)
        return {"action": "updated", "record_id": record_id}
    else:
        store[record_id] = {**record, "id": record_id}
        return {"action": "created", "record_id": record_id}
