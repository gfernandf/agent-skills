"""
Image baseline service module.
Provides baseline implementations for image-related capabilities.
"""

def generate_caption(image_data):
    """
    Generate a caption for an image.
    
    Args:
        image_data (bytes): The image data.
    
    Returns:
        dict: {"caption": str}
    """
    # Baseline implementation: placeholder
    return {"caption": "[Generated image caption]"}

def classify_image(image_data):
    """
    Classify an image.
    
    Args:
        image_data (bytes): The image data.
    
    Returns:
        dict: {"class": str, "confidence": float}
    """
    # Baseline implementation: placeholder
    return {"class": "unknown", "confidence": 0.0}