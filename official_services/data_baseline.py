"""
Data baseline service module.
Provides baseline implementations for data-related capabilities.
"""

import json


def parse_json(json_string):
    """
    Parse a JSON string into a Python object.

    Args:
        json_string (str): The JSON string to parse.

    Returns:
        dict: {"parsed_data": dict}
    """
    try:
        parsed = json.loads(json_string)
        return {"data": parsed}
    except json.JSONDecodeError as e:
        return {"data": {"error": str(e)}}


def validate_schema(data, schema):
    """
    Validate data against a JSON schema.

    Args:
        data (dict): The data to validate.
        schema (dict): The JSON schema.

    Returns:
        dict: {"valid": bool, "errors": list}
    """
    # Baseline implementation: simple validation
    errors = []
    if not isinstance(data, dict):
        errors.append("Data must be a dictionary")
    # Add more validation logic as needed
    return {"valid": len(errors) == 0, "errors": errors}


def deduplicate_records(records, key_fields=None):
    """
    Deduplicate records by key fields or full-record signature.

    Args:
        records (list): List of record objects.
        key_fields (list | None): Optional list of keys used for deduplication.

    Returns:
        dict: {"records": list, "duplicates": int}
    """
    if not isinstance(records, list):
        return {"records": [], "duplicates": 0}

    normalized_keys = key_fields if isinstance(key_fields, list) else []
    seen = set()
    deduped = []
    duplicates = 0

    for item in records:
        if not isinstance(item, dict):
            signature = json.dumps(item, sort_keys=True, default=str)
        elif normalized_keys:
            key_obj = {k: item.get(k) for k in normalized_keys if isinstance(k, str)}
            signature = json.dumps(key_obj, sort_keys=True, default=str)
        else:
            signature = json.dumps(item, sort_keys=True, default=str)

        if signature in seen:
            duplicates += 1
            continue

        seen.add(signature)
        deduped.append(item)

    return {"records": deduped, "duplicates": duplicates}


def transform_records(records, mapping):
    """
    Transform records by applying field renames, projections, defaults,
    and computed fields.

    Args:
        records (list): Input records.
        mapping (dict): Transformation spec with optional keys:
            rename, select, defaults, computed.

    Returns:
        dict: {"records": list, "transform_summary": dict}
    """
    if not isinstance(records, list):
        return {"records": [], "transform_summary": {"records_in": 0, "records_out": 0}}

    rename_map = mapping.get("rename", {}) if isinstance(mapping, dict) else {}
    select_fields = mapping.get("select") if isinstance(mapping, dict) else None
    defaults = mapping.get("defaults", {}) if isinstance(mapping, dict) else {}
    computed = mapping.get("computed", {}) if isinstance(mapping, dict) else {}

    fields_renamed = 0
    fields_added = 0
    fields_dropped = 0

    transformed = []
    for record in records:
        if not isinstance(record, dict):
            transformed.append(record)
            continue

        row = dict(record)

        # Apply renames
        for old_key, new_key in rename_map.items():
            if old_key in row:
                row[new_key] = row.pop(old_key)
                fields_renamed += 1

        # Apply defaults
        for key, default_val in defaults.items():
            if key not in row:
                row[key] = default_val
                fields_added += 1

        # Apply computed fields (simple {{field}} template)
        import re

        for key, template in computed.items():
            value = re.sub(
                r"\{\{(\w+)\}\}", lambda m: str(row.get(m.group(1), "")), template
            )
            row[key] = value
            fields_added += 1

        # Apply projection (select)
        if isinstance(select_fields, list):
            before = len(row)
            row = {k: v for k, v in row.items() if k in select_fields}
            fields_dropped += before - len(row)

        transformed.append(row)

    return {
        "records": transformed,
        "transform_summary": {
            "records_in": len(records),
            "records_out": len(transformed),
            "fields_renamed": fields_renamed,
            "fields_added": fields_added,
            "fields_dropped": fields_dropped,
        },
    }


def map_array(items, expression, context=None):
    """Apply an expression to each element in an array (baseline: identity)."""
    results = []
    for item in items or []:
        results.append(item)
    return {"items": results, "item_count": len(results)}


def map_fields(record, mapping, drop_unmapped=False):
    """Rename/alias fields in a record."""
    if not isinstance(record, dict):
        return {"record": record, "fields_mapped": 0}
    result = {}
    mapped = 0
    for old_key, new_key in (mapping or {}).items():
        if old_key in record:
            result[new_key] = record[old_key]
            mapped += 1
    if not drop_unmapped:
        for k, v in record.items():
            if k not in (mapping or {}):
                result[k] = v
    return {"record": result, "fields_mapped": mapped}


def join_records(records_a, records_b, key_field, join_type=None):
    """Join two record sets on a key field."""
    jtype = (join_type or "inner").lower()
    index_b = {}
    for rec in records_b or []:
        key = rec.get(key_field)
        if key is not None:
            index_b.setdefault(key, []).append(rec)

    joined = []
    matched_keys = set()
    for rec_a in records_a or []:
        key = rec_a.get(key_field)
        matches = index_b.get(key, [])
        if matches:
            matched_keys.add(key)
            for rec_b in matches:
                merged = {**rec_a, **rec_b}
                joined.append(merged)
        elif jtype in ("left", "outer"):
            joined.append(dict(rec_a))

    if jtype in ("right", "outer"):
        for rec_b in records_b or []:
            key = rec_b.get(key_field)
            if key not in matched_keys:
                joined.append(dict(rec_b))

    return {"records": joined, "record_count": len(joined), "join_type": jtype}


def merge_records(records, strategy=None):
    """Deep-merge a list of records into one."""
    strat = strategy or "shallow"
    result = {}
    for rec in records or []:
        if not isinstance(rec, dict):
            continue
        if strat == "deep":
            for k, v in rec.items():
                if k in result and isinstance(result[k], dict) and isinstance(v, dict):
                    result[k] = {**result[k], **v}
                else:
                    result[k] = v
        else:
            result.update(rec)
    return {"record": result, "strategy": strat}
