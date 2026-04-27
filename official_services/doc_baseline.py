"""
Document baseline service module.
Provides baseline implementations for document-related capabilities.
"""

import os
import time

from runtime.observability import elapsed_ms, log_event


def resolve_corpus_sources(items):
    from official_services.web_baseline import _repair_mojibake

    resolved = []
    for raw_item in items or []:
        item = dict(raw_item)
        if item.get("content"):
            item["content"] = _repair_mojibake(item["content"])
            resolved.append(item)
            continue

        source_ref = item.get("source_ref") or {}
        ref_type = source_ref.get("type", "")
        location = source_ref.get("location", "")
        if ref_type == "pdf_path":
            result = read_pdf(location)
            item["content"] = result.get("text", "")
            item.setdefault("type", "report")
            pdf_meta = result.get("metadata") or {}
            if pdf_meta.get("title"):
                item.setdefault("title", pdf_meta["title"])

        elif ref_type == "fs_path":
            try:
                norm = os.path.realpath(location)
                if not os.path.isfile(norm):
                    item["content"] = ""
                    item["resolution_error"] = f"File not found: {location}"
                else:
                    with open(norm, "r", encoding="utf-8", errors="replace") as f:
                        item["content"] = f.read()
                item.setdefault("type", "report")
            except Exception as exc:
                item["content"] = ""
                item["resolution_error"] = f"Error reading file: {exc}"

        elif ref_type == "url":
            try:
                from official_services.web_baseline import fetch_webpage
                from official_services.text_baseline import extract_text

                fetch_result = fetch_webpage(location)
                status = fetch_result.get("status", 0)
                raw_content = fetch_result.get("content", "")
                if status >= 400 or not raw_content:
                    # Fallback to snippet from metadata if fetch failed
                    snippet = (item.get("metadata") or {}).get("snippet", "")
                    item["content"] = _repair_mojibake(snippet)
                    item["resolution_error"] = (
                        f"Fetch failed (HTTP {status}): {raw_content[:200]}"
                    )
                else:
                    # Strip HTML to plain text for LLM consumption
                    cleaned = extract_text(raw_content)
                    text = (
                        cleaned.get("text", raw_content)
                        if isinstance(cleaned, dict)
                        else raw_content
                    )
                    # Truncate to 15KB to avoid token limits downstream
                    if len(text) > 15000:
                        text = text[:15000] + "\n[... truncated]"
                    item["content"] = text
                item.setdefault("type", "web_page")
            except Exception as exc:
                snippet = (item.get("metadata") or {}).get("snippet", "")
                item["content"] = _repair_mojibake(snippet)
                item["resolution_error"] = f"Error fetching URL: {exc}"

        elif ref_type == "raw_text":
            item["content"] = location
            item.setdefault("type", "raw_text")

        else:
            # memory_key and unknown types: pass through, add warning
            item.setdefault("content", "")
            if ref_type:
                item["resolution_warning"] = (
                    f"source_ref.type '{ref_type}' cannot be resolved locally; "
                    "content left empty."
                )

        resolved.append(item)

    return {"items": resolved}


_MAX_PDF_BYTES = 50 * 1024 * 1024  # 50 MB
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
    chunk_size = int(chunk_size)
    chunks = [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]
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
            "service.pdf.document.read",
            status=status,
            file_path=path,
            pages=(metadata.get("pages") if isinstance(metadata, dict) else None),
            pages_read=(
                metadata.get("pages_read") if isinstance(metadata, dict) else None
            ),
            duration_ms=elapsed_ms(start_time),
            error_type=error_type,
        )
        return payload

    log_event("service.pdf.document.read.start", file_path=path)

    if not isinstance(path, str) or not path.strip():
        return _finish(
            {
                "text": "Invalid input: 'path' must be a non-empty string.",
                "metadata": {},
            },
            "rejected",
            "ValidationError",
        )

    # Normalise and validate path (no directory traversal)
    norm = os.path.realpath(path)
    if not os.path.isfile(norm):
        return _finish(
            {"text": f"File not found: {path}", "metadata": {}},
            "rejected",
            "FileNotFound",
        )

    file_size = os.path.getsize(norm)
    if file_size > _MAX_PDF_BYTES:
        return _finish(
            {
                "text": f"File exceeds maximum allowed size ({_MAX_PDF_BYTES // (1024 * 1024)} MB).",
                "metadata": {},
            },
            "rejected",
            "PayloadTooLarge",
        )

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
            metadata.update(
                {
                    "title": reader.metadata.title,
                    "author": reader.metadata.author,
                    "subject": reader.metadata.subject,
                    "creator": reader.metadata.creator,
                    "producer": reader.metadata.producer,
                }
            )

        return _finish({"text": text, "metadata": metadata}, "completed")
    except Exception as e:
        return _finish(
            {"text": f"Error reading PDF: {type(e).__name__}: {e}", "metadata": {}},
            "failed",
            type(e).__name__,
        )


def generate_document(instruction, context=None, sections=None, format=None):
    """Generate a document from an instruction (baseline: template-based)."""
    fmt = format or "markdown"
    parts = []
    parts.append(f"# {instruction[:80]}")
    if context:
        parts.append(f"\n{context}\n")
    if sections:
        for sec in sections:
            if isinstance(sec, dict):
                parts.append(
                    f"## {sec.get('title', 'Section')}\n{sec.get('content', '')}"
                )
            else:
                parts.append(f"## {sec}")
    if not context and not sections:
        parts.append(f"\n[Baseline] Document content for: {instruction}")
    text = "\n\n".join(parts)
    return {"document": text, "format": fmt, "_fallback": True}
