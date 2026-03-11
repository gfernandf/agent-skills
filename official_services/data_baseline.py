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