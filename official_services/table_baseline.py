"""
Table baseline service module.
Provides baseline implementations for table-related capabilities.
"""

def filter_table(table_data, filter_criteria):
    """
    Filter table data based on criteria.
    
    Args:
        table_data (list): The table data as a list of rows.
        filter_criteria (dict): The filter criteria.
    
    Returns:
        dict: {"filtered_table": list}
    """
    # Baseline implementation: return all data (no filtering)
    return {"table": table_data}


def sort_table(table_data, sort_by):
    """
    Sort table rows by one or more columns.

    Args:
        table_data (list): Table rows as list of dicts.
        sort_by (list): Sort specs, each with 'field' and optional 'order'.

    Returns:
        dict: {"table": list}
    """
    if not isinstance(table_data, list) or not table_data:
        return {"table": table_data or []}
    if not isinstance(sort_by, list) or not sort_by:
        return {"table": table_data}

    # Build a composite sort key — process specs in reverse priority order
    result = list(table_data)
    for spec in reversed(sort_by):
        field = spec.get("field", "")
        descending = spec.get("order", "asc").lower() == "desc"
        result.sort(key=lambda row, f=field: (row.get(f) is None, row.get(f, "")), reverse=descending)

    return {"table": result}


def aggregate_table(table_data, aggregations, group_by=None):
    """
    Compute aggregate values over table columns.

    Args:
        table_data (list): Table rows as list of dicts.
        aggregations (list): Each has 'field' and 'function' (sum/avg/min/max/count).
        group_by (str): Optional column to group by.

    Returns:
        dict: {"results": list, "row_count": int}
    """
    if not isinstance(table_data, list):
        return {"results": [], "row_count": 0}
    if not isinstance(aggregations, list) or not aggregations:
        return {"results": [], "row_count": len(table_data)}

    # Group rows
    groups = {}
    for row in table_data:
        key = row.get(group_by, "__all__") if group_by else "__all__"
        groups.setdefault(key, []).append(row)

    results = []
    for key, rows in groups.items():
        entry = {}
        if group_by:
            entry[group_by] = key
        for agg in aggregations:
            field = agg.get("field", "")
            func = agg.get("function", "count").lower()
            values = [r.get(field) for r in rows if r.get(field) is not None]
            numeric = [v for v in values if isinstance(v, (int, float))]
            result_key = f"{field}_{func}"
            if func == "count":
                entry[result_key] = len(values)
            elif func == "sum":
                entry[result_key] = sum(numeric) if numeric else 0
            elif func == "avg":
                entry[result_key] = round(sum(numeric) / len(numeric), 2) if numeric else 0
            elif func == "min":
                entry[result_key] = min(numeric) if numeric else None
            elif func == "max":
                entry[result_key] = max(numeric) if numeric else None
            else:
                entry[result_key] = None
        results.append(entry)

    return {"results": results, "row_count": len(table_data)}