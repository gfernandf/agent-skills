"""
Text baseline service module.
Provides baseline implementations for text-related capabilities.
"""

def classify_text(text, categories):
    """
    Classify text into one of the given categories.
    
    Args:
        text (str): The text to classify.
        categories (list): List of possible categories.
    
    Returns:
        dict: {"category": str, "confidence": float}
    """
    # Baseline implementation: select first category
    category = categories[0] if categories else "unknown"
    return {"category": category, "confidence": 1.0}

def embed_text(text):
    """
    Generate an embedding vector for the text.
    
    Args:
        text (str): The text to embed.
    
    Returns:
        dict: {"embedding": list}
    """
    # Baseline implementation: simple hash-based embedding
    embedding = [hash(text + str(i)) % 1000 for i in range(10)]
    return {"embedding": embedding}

def extract_entities(text):
    """
    Extract named entities from text.
    
    Args:
        text (str): The text to analyze.
    
    Returns:
        dict: {"entities": list}
    """
    # Baseline implementation: empty list
    return {"entities": []}

def extract_text(document):
    """
    Extract text from a document.
    
    Args:
        document (bytes): The document data.
    
    Returns:
        dict: {"text": str}
    """
    # Baseline implementation: placeholder
    return {"text": "[Extracted text]"}

def extract_keywords(text):
    """
    Extract keywords from text.
    
    Args:
        text (str): The text to analyze.
    
    Returns:
        dict: {"keywords": list}
    """
    # Baseline implementation: split by spaces and take first 5
    words = text.split()[:5]
    return {"keywords": words}

def detect_language(text):
    """
    Detect the language of the text.
    
    Args:
        text (str): The text to analyze.
    
    Returns:
        dict: {"language": str}
    """
    # Baseline implementation: assume English
    return {"language": "en"}

def summarize_text(text, max_length=None):
    """
    Summarize the text.
    
    Args:
        text (str): The text to summarize.
        max_length (int, optional): Maximum length of the summary.
    
    Returns:
        dict: {"summary": str}
    """
    # Baseline implementation: truncate text if max_length provided, else return all
    if max_length is None:
        # Default to returning first 500 chars as summary
        max_length = 500
    summary = text[:max_length] if len(text) > max_length else text
    return {"summary": summary}

def template_text(template, variables):
    """
    Fill a template with variables.
    
    Args:
        template (str): The template string.
        variables (dict): The variables to substitute.
    
    Returns:
        dict: {"templated_text": str}
    """
    # Baseline implementation: simple string formatting
    templated = template.format(**variables)
    return {"templated_text": templated}

def translate_text(text, target_language):
    """
    Translate text to the target language.
    
    Args:
        text (str): The text to translate.
        target_language (str): The target language code.
    
    Returns:
        dict: {"translated_text": str}
    """
    # Baseline implementation: return original text
    return {"translated_text": text}