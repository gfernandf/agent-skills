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
