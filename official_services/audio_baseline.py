"""
Audio baseline service module.
Provides baseline implementations for audio-related capabilities.
"""

from pathlib import Path
import time

from runtime.observability import elapsed_ms, log_event

_MAX_AUDIO_BYTES = 100 * 1024 * 1024  # 100 MB
_SUPPORTED_AUDIO_EXTENSIONS = {".wav", ".mp3", ".ogg", ".flac", ".m4a", ".aac", ".opus"}


def _load_audio_bytes(audio_data):
    """Load bytes directly or from a local file path. Returns (bytes|None, path_str|None, error|None)."""
    if isinstance(audio_data, (bytes, bytearray)):
        payload = bytes(audio_data)
        if len(payload) > _MAX_AUDIO_BYTES:
            return (
                None,
                None,
                f"Audio input exceeds maximum allowed size ({_MAX_AUDIO_BYTES // (1024 * 1024)} MB).",
            )
        return payload, None, None

    if isinstance(audio_data, str):
        source = audio_data.strip()
        if not source:
            return (
                None,
                None,
                "Invalid input: 'audio' must be a non-empty string or bytes.",
            )

        path = Path(source)
        if not path.is_file():
            return None, None, None  # Treat as opaque source descriptor

        if path.suffix.lower() not in _SUPPORTED_AUDIO_EXTENSIONS:
            return (
                None,
                None,
                f"Unsupported audio format: '{path.suffix}'. Supported: {', '.join(sorted(_SUPPORTED_AUDIO_EXTENSIONS))}.",
            )

        file_size = path.stat().st_size
        if file_size > _MAX_AUDIO_BYTES:
            return (
                None,
                None,
                f"File exceeds maximum allowed size ({_MAX_AUDIO_BYTES // (1024 * 1024)} MB).",
            )

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
    start_time = time.perf_counter()

    def _finish(payload, status, error_type=None):
        log_event(
            "service.audio.speech.transcribe",
            status=status,
            input_type=type(audio_data).__name__,
            duration_ms=elapsed_ms(start_time),
            error_type=error_type,
        )
        return payload

    log_event(
        "service.audio.speech.transcribe.start", input_type=type(audio_data).__name__
    )

    if audio_data is None:
        return _finish(
            {"transcript": "No audio provided."}, "rejected", "ValidationError"
        )

    payload, source_path, error = _load_audio_bytes(audio_data)

    if error:
        return _finish({"transcript": f"Error: {error}"}, "rejected", "ValidationError")

    if payload is not None:
        size = len(payload)
        if source_path:
            return _finish(
                {"transcript": f"Transcription of '{source_path}' ({size} bytes)."},
                "completed",
            )
        return _finish(
            {"transcript": f"Transcription of in-memory audio ({size} bytes)."},
            "completed",
        )

    # Opaque string descriptor fallback
    source = str(audio_data).strip()
    if not source:
        return _finish(
            {"transcript": "No audio provided."}, "rejected", "ValidationError"
        )
    return _finish(
        {"transcript": f"Transcription from source descriptor: {source}."}, "completed"
    )


def synthesize_speech(text, language=None, voice=None):
    """
    Text-to-speech baseline.

    The baseline cannot produce real audio — it returns a placeholder WAV
    descriptor with metadata. Production bindings should use a real TTS
    engine (e.g. OpenAI TTS, Azure Speech, Google TTS).

    Args:
        text (str): Text to synthesize.
        language (str): Target locale (e.g. "en-US").
        voice (str): Voice identifier (unused in baseline).

    Returns:
        dict with 'audio' and 'metadata'.
    """
    lang = language or "en-US"
    text = text or ""
    words = text.split()
    char_count = len(text)
    word_count = len(words)
    # Rough estimate: ~150 words per minute → ~400ms per word
    estimated_duration_ms = max(word_count * 400, 500)

    return {
        "audio": {
            "data": b"RIFF\x00\x00\x00\x00WAVEfmt ",  # minimal WAV header placeholder
            "format": "wav",
            "duration_ms": estimated_duration_ms,
        },
        "metadata": {
            "language": lang,
            "voice_used": voice or "baseline-default",
            "char_count": char_count,
            "word_count": word_count,
        },
    }
