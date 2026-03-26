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
    Baseline: regex-based capitalized phrase extraction (degraded mode).
    """
    if not text:
        return {"entities": [], "_fallback": True}
    # Extract capitalized multi-word phrases as candidate entities
    candidates = re.findall(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b", text)
    seen = set()
    entities = []
    for c in candidates:
        key = c.lower()
        if key not in seen:
            seen.add(key)
            entities.append({"text": c, "type": "OTHER"})
    return {"entities": entities[:30], "_fallback": True}


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
        text = document.decode("utf-8", errors="ignore")
    else:
        text = document

    # Remove script and style tags and their content first (these contain no useful text)
    text = re.sub(
        r"<script[^>]*>.*?</script>", " ", text, flags=re.DOTALL | re.IGNORECASE
    )
    text = re.sub(
        r"<style[^>]*>.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE
    )
    text = re.sub(
        r"<noscript[^>]*>.*?</noscript>", " ", text, flags=re.DOTALL | re.IGNORECASE
    )
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.DOTALL)  # Remove HTML comments

    # Remove common non-content tags
    text = re.sub(r"<head[^>]*>.*?</head>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<nav[^>]*>.*?</nav>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(
        r"<footer[^>]*>.*?</footer>", " ", text, flags=re.DOTALL | re.IGNORECASE
    )

    # Remove HTML tags
    text = re.sub(r"<[^>]+>", " ", text)

    # Decode HTML entities
    text = text.replace("&nbsp;", " ")
    text = text.replace("&amp;", "&")
    text = text.replace("&lt;", "<")
    text = text.replace("&gt;", ">")
    text = text.replace("&quot;", '"')
    text = text.replace("&#39;", "'")

    # Collapse multiple whitespace
    text = re.sub(r"\s+", " ", text)
    text = text.strip()

    return {"text": text}


def extract_keywords(text):
    """
    Extract keywords from text.
    Baseline: frequency-weighted unique terms (degraded mode, no TF-IDF).
    """
    stop_words = {
        "the",
        "a",
        "an",
        "and",
        "or",
        "but",
        "in",
        "on",
        "at",
        "to",
        "for",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "can",
        "of",
        "with",
        "by",
        "from",
        "as",
        "it",
        "its",
        "that",
        "which",
        "who",
        "what",
        "where",
        "when",
        "why",
        "how",
        "this",
        "these",
        "those",
        "not",
        "no",
        "so",
        "if",
        "than",
        "then",
        "also",
        "about",
        "up",
        "out",
        "just",
        "into",
        "more",
        "other",
        "some",
        "such",
        "only",
        "over",
        "very",
        "own",
        "all",
        "each",
        "every",
        "both",
        "few",
        "many",
        "most",
        "any",
        "new",
        "one",
        "two",
        "first",
        "last",
        "our",
        "your",
        "their",
        "we",
        "they",
        "you",
        "he",
        "she",
        "my",
        "his",
        "her",
        "its",
        "said",
        "like",
        "well",
        "back",
        "much",
        "made",
        "after",
        "year",
        "years",
        "make",
        "way",
        "been",
        "through",
        "between",
        "being",
        "market",
        "report",
        "data",
        "based",
        "according",
        "using",
    }
    # Clean and tokenize
    cleaned = re.sub(r"[^a-zA-Z\s]", " ", text.lower())
    words = [w for w in cleaned.split() if w not in stop_words and len(w) > 3]
    # Frequency count
    freq = {}
    for w in words:
        freq[w] = freq.get(w, 0) + 1
    # Sort by frequency descending
    ranked = sorted(freq.items(), key=lambda x: x[1], reverse=True)
    keywords = [w for w, _ in ranked[:20]]
    return {"keywords": keywords, "_fallback": True}


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
    sentences = re.split(r"[.!?]+", text)
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
    if summary and not summary.endswith("."):
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
        format_template = re.sub(r"\{\{(\w+)\}\}", r"{\1}", template)
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


def merge_texts(items, separator=None, include_headers=None):
    """
    Merge multiple text items into a single text block.

    Args:
        items (list): Items with 'content' field (string). May include 'id'
            and 'title' for section headers.
        separator (str): Separator between items. Defaults to double newline.
        include_headers (bool): Include titles as headers. Defaults to True
            when items have titles.

    Returns:
        dict: {"text": str, "item_count": int}
    """
    if separator is None:
        separator = "\n\n"

    # Auto-detect include_headers if not specified
    if include_headers is None:
        include_headers = any(
            it.get("title") for it in (items or []) if isinstance(it, dict)
        )

    parts = []
    count = 0

    for item in items or []:
        if not isinstance(item, dict):
            continue
        content = item.get("content", "")
        if not content:
            continue

        count += 1
        if include_headers and item.get("title"):
            parts.append(f"## {item['title']}\n{content}")
        else:
            parts.append(content)

    return {
        "text": separator.join(parts),
        "item_count": count,
    }


def generate_text(instruction, context=None, max_length=None):
    """
    Generate text from an instruction and optional context.
    Baseline: echoes the instruction with context prefix (degraded mode).
    """
    parts = []
    if context:
        parts.append(f"Context — {context[:200]}.")
    parts.append(instruction)
    text = " ".join(parts)
    if max_length and len(text) > max_length:
        text = text[:max_length]
    return {"text": text, "_fallback": True}


def rewrite_text(text, goal):
    """
    Rewrite text applying a transformation directive.
    Baseline: returns original text annotated with the goal (degraded mode).
    """
    return {"text": f"({goal}) {text}", "_fallback": True}


def answer_question(question, context):
    """
    Answer a question given a context passage.
    Baseline: returns the first sentence of the context as the answer (degraded mode).
    """
    if not context:
        return {"answer": "", "confidence": 0.0, "_fallback": True}
    sentences = re.split(r"(?<=[.!?])\s+", context.strip())
    answer = sentences[0] if sentences else context[:200]
    return {"answer": answer, "confidence": 0.5, "_fallback": True}
