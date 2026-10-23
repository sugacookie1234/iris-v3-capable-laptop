"""Explicit local speech profiles; runtime never downloads models."""
from pathlib import Path

MODEL_ROOT = Path(__file__).resolve().parents[2] / '.local/models'
MODELS = {
    'large-v3-turbo': ('dropbox-dash/faster-whisper-large-v3-turbo', '0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf'),
    'small.en': ('Systran/faster-whisper-small.en', 'd1d751a5f8271d482d14ca55d9e2deeebbae577f'),
}


def speech_options(settings):
    model = settings.get('IRIS_STT_MODEL', 'large-v3-turbo').strip()
    device = settings.get('IRIS_STT_DEVICE', 'auto').strip().lower()
    language = settings.get('IRIS_STT_LANGUAGE', 'en').strip().lower()
    if model not in MODELS:
        raise ValueError('Choose large-v3-turbo or small.en for local speech.')
    if device not in ('auto', 'cpu', 'cuda'):
        raise ValueError('Speech device must be auto, cpu, or cuda.')
    if language not in ('en', 'auto'):
        raise ValueError('Speech language must be en or auto.')
    if model == 'small.en' and language != 'en':
        raise ValueError('small.en requires English; use large-v3-turbo for language detection.')
    return model, device, language


def model_path(name):
    if name not in MODELS:
        raise ValueError('Unknown local speech model.')
    return MODEL_ROOT / ('faster-whisper-' + name)
