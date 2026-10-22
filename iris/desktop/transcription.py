"""Bounded local Vosk transcription; microphone audio never leaves this server."""
import io
import json
from pathlib import Path
import threading
import wave

MAX_AUDIO_BYTES = 1100000
MODEL_PATH = Path(__file__).resolve().parents[2] / '.local/models/vosk-model-small-en-us-0.15'
_lock = threading.Lock()
_model = None


def transcribe(settings, audio, content_type):
    if content_type.split(';')[0].strip().lower() != 'audio/wav' or not 44 <= len(audio) <= MAX_AUDIO_BYTES:
        raise ValueError('Record a short spoken request in WAV format.')
    try:
        with wave.open(io.BytesIO(audio), 'rb') as source:
            if (source.getnchannels(), source.getsampwidth(), source.getframerate()) != (1, 2, 16000):
                raise ValueError('Voice input requires 16 kHz mono PCM audio.')
            if source.getnframes() > 16000 * 31 or source.getcomptype() != 'NONE':
                raise ValueError('Keep spoken requests under 30 seconds.')
            pcm = source.readframes(source.getnframes())
            if len(pcm) != source.getnframes() * 2:
                raise ValueError('Recording was incomplete.')
    except (wave.Error, EOFError):
        raise ValueError('The microphone recording could not be decoded.') from None
    if not MODEL_PATH.is_dir():
        raise ValueError('Local speech model is missing. Run setup.bat to install voice input.')
    try:
        from vosk import Model, KaldiRecognizer, SetLogLevel
    except ImportError:
        raise ValueError('Local speech recognition is missing. Run setup.bat.') from None
    if not _lock.acquire(blocking=False):
        raise ValueError('IRIS is transcribing another recording. Try again shortly.')
    try:
        global _model
        if _model is None:
            SetLogLevel(-1)
            _model = Model(str(MODEL_PATH))
        recognizer = KaldiRecognizer(_model, 16000)
        parts = []
        for offset in range(0, len(pcm), 8000):
            if recognizer.AcceptWaveform(pcm[offset:offset+8000]):
                parts.append(json.loads(recognizer.Result()).get('text', ''))
        parts.append(json.loads(recognizer.FinalResult()).get('text', ''))
        return ' '.join(part for part in parts if part).strip()
    finally:
        _lock.release()
