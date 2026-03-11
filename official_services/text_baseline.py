"""
Text baseline service module.
Provides baseline implementations for text-related capabilities.
"""

import re

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
    label = categories[0] if categories else "unknown"
    return {"label": label, "confidence": 1.0}

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
    Extract text from a document (HTML content).
    
    Args:
        document (str): The document/HTML data.
    
    Returns:
        dict: {"text": str}
    """
    # If document is bytes, decode it
    if isinstance(document, bytes):
        text = document.decode('utf-8', errors='ignore')
    else:
        text = document
    
    # Remove script and style tags and their content first (these contain no useful text)
    text = re.sub(r'<script[^>]*>.*?</script>', ' ', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style[^>]*>.*?</style>', ' ', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<noscript[^>]*>.*?</noscript>', ' ', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<!--.*?-->', ' ', text, flags=re.DOTALL)  # Remove HTML comments
    
    # Remove common non-content tags
    text = re.sub(r'<head[^>]*>.*?</head>', ' ', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<nav[^>]*>.*?</nav>', ' ', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<footer[^>]*>.*?</footer>', ' ', text, flags=re.DOTALL | re.IGNORECASE)
    
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', ' ', text)
    
    # Decode HTML entities
    text = text.replace('&nbsp;', ' ')
    text = text.replace('&amp;', '&')
    text = text.replace('&lt;', '<')
    text = text.replace('&gt;', '>')
    text = text.replace('&quot;', '"')
    text = text.replace('&#39;', "'")
    
    # Collapse multiple whitespace
    text = re.sub(r'\s+', ' ', text)
    text = text.strip()
    
    return {"text": text}

def extract_keywords(text):
    """
    Extract keywords from text.
    
    Args:
        text (str): The text to analyze.
    
    Returns:
        dict: {"keywords": list}
    """
    # Remove common stop words and extract meaningful words
    stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'can', 'of', 'with', 'by', 'from', 'as', 'it', 'that', 'which', 'who', 'what', 'where', 'when', 'why', 'how'}
    
    # Convert to lowercase and split
    words = text.lower().split()
    
    # Filter out stop words and short words
    keywords = [w for w in words if w not in stop_words and len(w) > 3]
    
    # Return top 10 unique keywords
    unique_keywords = []
    seen = set()
    for kw in keywords:
        if kw not in seen:
            unique_keywords.append(kw)
            seen.add(kw)
            if len(unique_keywords) >= 10:
                break
    
    return {"keywords": unique_keywords}

def detect_language(text):
    """
    Detect the language of the text.
    
    Args:
        text (str): The text to analyze.
    
    Returns:
        dict: {"language": str}
    """
    # Baseline implementation: assume English (would use langdetect in production)
    return {"language": "en", "confidence": 0.99}

def summarize_text(text, max_length=None):
    """
    Summarize the text.
    
    Args:
        text (str): The text to summarize.
        max_length (int, optional): Maximum length of the summary.
    
    Returns:
        dict: {"summary": str}
    """
    # If text is empty or very short, return as is
    if not text or len(text.split()) < 3:
        return {"summary": text}
    
    # Split into sentences
    sentences = re.split(r'[.!?]+', text)
    sentences = [s.strip() for s in sentences if s.strip()]
    
    if not sentences:
        return {"summary": text}
    
    # Default max_length to 500 characters
    if max_length is None:
        max_length = 500
    
    # Build summary by adding complete sentences until max_length
    summary = ""
    for sentence in sentences:
        if len(summary) + len(sentence) + 2 < max_length:
            if summary:
                summary += ". "
            summary += sentence
        else:
            break
    
    # Add period if needed
    if summary and not summary.endswith('.'):
        summary += "."
    
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
    # Use template string formatting with {{variable}} style
    try:
        # Replace {{variable}} with {variable} for format
        format_template = re.sub(r'\{\{(\w+)\}\}', r'{\1}', template)
        templated = format_template.format(**variables)
    except KeyError:
        templated = template
    
    return {"text": templated}

def translate_text(text, target_language):
    """
    Translate text to the target language.
    
    Args:
        text (str): The text to translate.
        target_language (str): The target language code.
    
    Returns:
        dict: {"translated_text": str}
    """
    # Baseline implementation: return original text (would use translation API in production)
    return {"translation": text}