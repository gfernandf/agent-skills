"""
Audio baseline service module.
Provides baseline implementations for audio-related capabilities.
"""

from pathlib import Path

_MAX_AUDIO_BYTES = 100 * 1024 * 1024   # 100 MB
_SUPPORTED_AUDIO_EXTENSIONS = {".wav", ".mp3", ".ogg", ".flac", ".m4a", ".aac", ".opus"}


def _load_audio_bytes(audio_data):
    """Load bytes directly or from a local file path. Returns (bytes|None, path_str|None, error|None)."""
    if isinstance(audio_data, (bytes, bytearray)):
        payload = bytes(audio_data)
        if len(payload) > _MAX_AUDIO_BYTES:
            return None, None, f"Audio input exceeds maximum allowed size ({_MAX_AUDIO_BYTES // (1024*1024)} MB)."
        return payload, None, None

    if isinstance(audio_data, str):
        source = audio_data.strip()
        if not source:
            return None, None, "Invalid input: 'audio' must be a non-empty string or bytes."

        path = Path(source)
        if not path.is_file():
            return None, None, None   # Treat as opaque source descriptor

        if path.suffix.lower() not in _SUPPORTED_AUDIO_EXTENSIONS:
            return None, None, f"Unsupported audio format: '{path.suffix}'. Supported: {', '.join(sorted(_SUPPORTED_AUDIO_EXTENSIONS))}."

        file_size = path.stat().st_size
        if file_size > _MAX_AUDIO_BYTES:
            return None, None, f"File exceeds maximum allowed size ({_MAX_AUDIO_BYTES // (1024*1024)} MB)."

        return path.read_bytes(), str(path), None

    return None, None, "Invalid input: 'audio' must be bytes or a file path string."

def transcribe_audio(audio_data):
    """
    Transcribe audio data to text.

    Args:
        audio_data (bytes | str): Raw audio bytes or path to an audio file.

    Returns:
        dict: {"transcript": str}
    """
    if audio_data is None:
        return {"transcript": "No audio provided."}

    payload, source_path, error = _load_audio_bytes(audio_data)

    if error:
        return {"transcript": f"Error: {error}"}

    if payload is not None:
        size = len(payload)
        if source_path:
            return {"transcript": f"Transcription of '{source_path}' ({size} bytes)."}
        return {"transcript": f"Transcription of in-memory audio ({size} bytes)."}

    # Opaque string descriptor fallback
    source = str(audio_data).strip()
    if not source:
        return {"transcript": "No audio provided."}
    return {"transcript": f"Transcription from source descriptor: {source}."}