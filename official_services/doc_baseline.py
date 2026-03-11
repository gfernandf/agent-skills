"""
Document baseline service module.
Provides baseline implementations for document-related capabilities.
"""

import os

_MAX_PDF_BYTES = 50 * 1024 * 1024   # 50 MB
_MAX_PDF_PAGES = 500


def chunk_document(text, chunk_size):
    """
    Chunk a document into smaller pieces.
    
    Args:
        text (str): The document text.
        chunk_size (int): The size of each chunk.
    
    Returns:
        dict: {"chunks": list}
    """
    chunks = [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]
    return {"chunks": chunks}

def read_pdf(path):
    """
    Extract text from a PDF file.

    Args:
        path (str): The path to the PDF file.

    Returns:
        dict: {"text": str, "metadata": dict}
    """
    if not isinstance(path, str) or not path.strip():
        return {"text": "Invalid input: 'path' must be a non-empty string.", "metadata": {}}

    # Normalise and validate path (no directory traversal)
    norm = os.path.realpath(path)
    if not os.path.isfile(norm):
        return {"text": f"File not found: {path}", "metadata": {}}

    file_size = os.path.getsize(norm)
    if file_size > _MAX_PDF_BYTES:
        return {
            "text": f"File exceeds maximum allowed size ({_MAX_PDF_BYTES // (1024*1024)} MB).",
            "metadata": {}
        }

    try:
        from PyPDF2 import PdfReader

        reader = PdfReader(norm)
        page_count = len(reader.pages)
        pages_to_read = min(page_count, _MAX_PDF_PAGES)

        text_parts = []
        for page in reader.pages[:pages_to_read]:
            page_text = page.extract_text() or ""
            text_parts.append(page_text)

        text = "\n".join(text_parts).strip()

        metadata = {"pages": page_count, "pages_read": pages_to_read}
        if reader.metadata:
            metadata.update({
                "title": reader.metadata.title,
                "author": reader.metadata.author,
                "subject": reader.metadata.subject,
                "creator": reader.metadata.creator,
                "producer": reader.metadata.producer,
            })

        return {"text": text, "metadata": metadata}
    except Exception as e:
        return {"text": f"Error reading PDF: {type(e).__name__}: {e}", "metadata": {}}