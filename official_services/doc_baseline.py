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

def read_pdf(pdf_data):
    """
    Extract text from PDF data.
    
    Args:
        pdf_data (bytes): The PDF data.
    
    Returns:
        dict: {"text": str}
    """
    # Baseline implementation: placeholder
    return {"text": "[Extracted PDF text]"}