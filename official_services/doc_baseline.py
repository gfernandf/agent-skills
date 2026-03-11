"""
Document baseline service module.
Provides baseline implementations for document-related capabilities.
"""

import os
import time

from runtime.observability import elapsed_ms, log_event

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
    start_time = time.perf_counter()

    def _finish(payload, status, error_type=None):
        metadata = payload.get("metadata") if isinstance(payload, dict) else {}
        log_event(
            "service.pdf.read",
            status=status,
            file_path=path,
            pages=(metadata.get("pages") if isinstance(metadata, dict) else None),
            pages_read=(metadata.get("pages_read") if isinstance(metadata, dict) else None),
            duration_ms=elapsed_ms(start_time),
            error_type=error_type,
        )
        return payload

    log_event("service.pdf.read.start", file_path=path)

    if not isinstance(path, str) or not path.strip():
        return _finish({"text": "Invalid input: 'path' must be a non-empty string.", "metadata": {}}, "rejected", "ValidationError")

    # Normalise and validate path (no directory traversal)
    norm = os.path.realpath(path)
    if not os.path.isfile(norm):
        return _finish({"text": f"File not found: {path}", "metadata": {}}, "rejected", "FileNotFound")

    file_size = os.path.getsize(norm)
    if file_size > _MAX_PDF_BYTES:
        return _finish({
            "text": f"File exceeds maximum allowed size ({_MAX_PDF_BYTES // (1024*1024)} MB).",
            "metadata": {}
        }, "rejected", "PayloadTooLarge")

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

        return _finish({"text": text, "metadata": metadata}, "completed")
    except Exception as e:
        return _finish({"text": f"Error reading PDF: {type(e).__name__}: {e}", "metadata": {}}, "failed", type(e).__name__)