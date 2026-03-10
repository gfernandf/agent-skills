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
        dict: {"value": str}
    """
    value = _memory_store.get(key, "")
    return {"value": value}

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