"""
Audio baseline service module.
Provides baseline implementations for audio-related capabilities.
"""

from pathlib import Path


def _load_audio_bytes(audio_data):
    """Load bytes directly or from a local file path."""
    if isinstance(audio_data, (bytes, bytearray)):
        return bytes(audio_data), None

    if isinstance(audio_data, str):
        source = audio_data.strip()
        if not source:
            return None, "No audio provided."

        path = Path(source)
        if path.is_file():
            return path.read_bytes(), str(path)
        return None, None

    return None, None

def transcribe_audio(audio_data):
    """
    Transcribe audio data to text.
    
    Args:
        audio_data (bytes): The audio data.
    
    Returns:
        dict: {"text": str}
    """
    # Baseline implementation: deterministic pseudo-transcript based on input size/type
    if audio_data is None:
        return {"text": "No audio provided."}

    payload, source_path = _load_audio_bytes(audio_data)
    if payload is not None:
        size = len(payload)
        if source_path:
            return {"text": f"Audio transcription completed from file '{source_path}'. Bytes read: {size}."}
        size = len(audio_data)
        return {"text": f"Audio transcription completed. Input bytes: {size}."}

    # If a path/string is provided, treat it as a source descriptor.
    source = str(audio_data).strip()
    if not source:
        return {"text": "No audio provided."}
    return {"text": f"Audio transcription completed from source: {source}."}