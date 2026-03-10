"""
Filesystem baseline service module.
Provides baseline implementations for filesystem-related capabilities.
"""

def read_file(path, mode=None):
    """
    Read the contents of a file.
    
    Args:
        path (str): The file path.
        mode (str): "text" or "binary". Defaults to "text".
    
    Returns:
        dict: {"content": str} for text mode, {"bytes": bytes} for binary mode.
    """
    try:
        if mode == "binary":
            with open(path, 'rb') as f:
                content = f.read()
            return {"bytes": content}
        else:
            # Default to text mode
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            return {"content": content}
    except Exception as e:
        # For error, return content with error message, as per original
        return {"content": f"Error reading file: {str(e)}"}