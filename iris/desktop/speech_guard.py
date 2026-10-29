"""Local speech/noise and transcript checks. No downloads, uploads or recordings saved."""
import io
import math
import threading
import unicodedata
import wave

_vad_lock = threading.Lock()


def has_speech(audio):
    """Check already validated 16 kHz mono PCM with bundled CPU Silero VAD.

    Loudness alone cannot distinguish a fan, click or clap from a spoken word.
    Keep the duration short enough for commands such as 'stop' and 'no'.
    """
    try:
        import numpy as np
        with wave.open(io.BytesIO(audio), 'rb') as source:
            samples = np.frombuffer(source.readframes(source.getnframes()), dtype='<i2').astype(np.float32) / 32768.0
        if len(samples) < 2560 or not np.any(samples):
            return False
        from faster_whisper.vad import get_speech_timestamps, VadOptions
        with _vad_lock:
            chunks = get_speech_timestamps(samples, sampling_rate=16000,
                vad_options=VadOptions(threshold=.6, min_speech_duration_ms=160,
                    min_silence_duration_ms=160, speech_pad_ms=0))
        return any(chunk['end'] - chunk['start'] >= 2560 for chunk in chunks)
    except (ImportError, OSError, RuntimeError, ValueError):
        # Do not silently upload unclassified room noise when the guard is broken.
        raise ValueError('The local speech check is unavailable. Run setup.bat to repair voice input; typing still works.') from None


def accepted_text(text, language, detected_language=None):
    """Reject empty/event-only output and conflicts with the chosen English mode.

    Fish's language field is only a hint. Missing language metadata is allowed
    for short commands; a script check catches predominantly non-Latin output.
    Automatic language mode deliberately permits multilingual speech.
    """
    text = text.strip()
    if not any(char.isalnum() for char in text):
        return ''
    if text.startswith('[') and text.endswith(']'):
        return ''  # An audio-event annotation is not an owner command.
    if language == 'en':
        if isinstance(detected_language, str) and detected_language.strip().lower() not in {'', 'en', 'eng', 'english', 'und'}:
            return ''
        letters = [char for char in text if char.isalpha()]
        non_latin = sum('LATIN' not in unicodedata.name(char, '') for char in letters)
        if letters and non_latin > len(letters) / 2:
            return ''
    return text


def confident_segment(segment):
    """Do not accept uncertain/repetitive Whisper decodes as spoken commands."""
    for name, default, allowed in (
        ('no_speech_prob', 0.0, lambda value: 0 <= value < .6),
        ('avg_logprob', 0.0, lambda value: value >= -1.0),
        ('compression_ratio', 1.0, lambda value: 0 <= value <= 2.4),
    ):
        value = getattr(segment, name, default)
        if not isinstance(value, (int, float)) or not math.isfinite(value) or not allowed(value):
            return False
    return True
