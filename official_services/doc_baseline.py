"""
Document baseline service module.
Provides baseline implementations for document-related capabilities.
"""

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
    try:
        from PyPDF2 import PdfReader

        reader = PdfReader(path)
        text = ""
        for page in reader.pages:
            page_text = page.extract_text() or ""
            text += page_text + "\n"
        
        metadata = {}
        if reader.metadata:
            metadata = {
                "title": reader.metadata.title,
                "author": reader.metadata.author,
                "subject": reader.metadata.subject,
                "creator": reader.metadata.creator,
                "producer": reader.metadata.producer,
                "pages": len(reader.pages)
            }
        
        return {"text": text.strip(), "metadata": metadata}
    except Exception as e:
        return {"text": "Error reading PDF: file not found or invalid", "metadata": {}}