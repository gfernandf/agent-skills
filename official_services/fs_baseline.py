"""
Filesystem baseline service module.
Provides baseline implementations for filesystem-related capabilities.
"""

def read_file(path):
    """
    Read the contents of a file.
    
    Args:
        path (str): The file path.
    
    Returns:
        dict: {"content": str}
    """
    try:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        return {"content": content}
    except Exception as e:
        return {"content": f"Error reading file: {str(e)}"}