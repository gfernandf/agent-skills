"""
Image baseline service module.
Provides baseline implementations for image-related capabilities.
"""

from pathlib import Path


def _load_image_bytes(image_data):
    """Load bytes directly or from a local file path."""
    if isinstance(image_data, (bytes, bytearray)):
        return bytes(image_data), None

    if isinstance(image_data, str):
        source = image_data.strip()
        if not source:
            return None, None

        path = Path(source)
        if path.is_file():
            return path.read_bytes(), str(path)
        return None, None

    return None, None


def _infer_image_kind(payload):
    """Infer a basic image format from magic bytes."""
    if payload.startswith(b"\x89PNG\r\n\x1a\n"):
        return "PNG"
    if payload.startswith(b"\xff\xd8\xff"):
        return "JPEG"
    if payload.startswith(b"GIF87a") or payload.startswith(b"GIF89a"):
        return "GIF"
    return "unknown"

def generate_caption(image_data):
    """
    Generate a caption for an image.
    
    Args:
        image_data (bytes): The image data.
    
    Returns:
        dict: {"caption": str}
    """
    # Baseline implementation: deterministic caption based on input characteristics
    if image_data is None:
        return {"caption": "An image with no readable content."}

    payload, source_path = _load_image_bytes(image_data)
    if payload is not None:
        size = len(payload)
        if size == 0:
            return {"caption": "An empty image payload."}
        image_kind = _infer_image_kind(payload)
        if source_path:
            return {"caption": f"A {image_kind} image loaded from '{source_path}' containing {size} bytes."}
        return {"caption": f"A {image_kind} image payload containing {size} bytes."}

    source = str(image_data).strip()
    if not source:
        return {"caption": "An image with no readable content."}
    return {"caption": f"An image referenced by: {source}."}

def classify_image(image_data):
    """
    Classify an image.
    
    Args:
        image_data (bytes): The image data.
    
    Returns:
        dict: {"class": str, "confidence": float}
    """
    # Baseline implementation: placeholder
    return {"label": "unknown", "confidence": 0.0}