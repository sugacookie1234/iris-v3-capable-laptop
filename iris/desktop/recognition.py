"""Fish ASR first, with a bounded request and a local Whisper fallback."""
import json
import http.client
import secrets
import threading
import urllib.error
import urllib.request
from iris.desktop import transcription as local

MAX_AUDIO_BYTES = local.MAX_AUDIO_BYTES
_lock = threading.Lock()
_status = {'engine': None, 'model': None, 'device': 'not loaded', 'compute_type': None, 'fallback': None}


class FishRecognitionError(ValueError):
    pass


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None  # Never forward microphone audio or credentials to another endpoint.


def _fish_transcribe(settings, audio):
    key = settings.get('IRIS_FISH_API_KEY', '').strip()
    if not key:
        raise FishRecognitionError('No Fish Audio key is configured.')
    boundary = 'iris-' + secrets.token_hex(16)
    fields = {'ignore_timestamps': 'true', 'diarize': 'false', 'tag_audio_events': 'false'}
    if settings.get('IRIS_STT_LANGUAGE', 'en') == 'en':
        fields['language'] = 'en'
    form = ''.join(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'
                   for name, value in fields.items())
    body = (form + f'--{boundary}\r\nContent-Disposition: form-data; name="audio"; filename="request.wav"\r\n'
            'Content-Type: audio/wav\r\n\r\n').encode() + audio + f'\r\n--{boundary}--\r\n'.encode()
    request = urllib.request.Request('https://api.fish.audio/v1/asr', data=body, method='POST',
        headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'multipart/form-data; boundary=' + boundary,
                 'model': 'transcribe-1-pro'})
    try:
        with urllib.request.build_opener(_NoRedirect()).open(request, timeout=12) as response:
            raw = response.read(64001)
        if len(raw) > 64000:
            raise ValueError('Oversized response')
        result = json.loads(raw)
        if not isinstance(result, dict) or not isinstance(result.get('text'), str):
            raise ValueError('Missing transcript')
        return result['text'].strip()
    except urllib.error.HTTPError as error:
        code = error.code
        error.close()
        message = {401: 'Fish Audio rejected the API key.', 403: 'Fish Audio denied access.',
                   402: 'Fish Audio API credit is unavailable.', 429: 'Fish Audio is rate limited.'}.get(
                       code, 'Fish Audio recognition is temporarily unavailable.')
        raise FishRecognitionError(message) from None
    except (urllib.error.URLError, OSError, TimeoutError, http.client.HTTPException):
        raise FishRecognitionError('Fish Audio could not be reached in time.') from None
    except (ValueError, UnicodeError):
        raise FishRecognitionError('Fish Audio returned an invalid transcript.') from None


def speech_status(settings=None):
    status = dict(_status)
    if settings is not None:
        model, device, _ = local.speech_options(settings)
        status.update(configured_provider=settings.get('IRIS_STT_PROVIDER', 'fish'),
                      configured_model=model, configured_device=device)
    return status


def transcribe(settings, audio, content_type):
    global _status
    local.validate_audio(audio, content_type)
    provider = settings.get('IRIS_STT_PROVIDER', 'fish').strip().lower()
    if provider not in ('fish', 'local'):
        raise ValueError('Voice recognition must be fish or local. Run setup.bat.')
    if not _lock.acquire(blocking=False):
        raise ValueError('IRIS is transcribing another recording. Try again shortly.')
    try:
        reason = None
        if provider == 'fish':
            try:
                text = _fish_transcribe(settings, audio)
                _status = {'engine': 'fish', 'model': 'transcribe-1-pro', 'device': 'cloud',
                           'compute_type': None, 'fallback': None}
                return text  # Empty means silence, not a reason to send another request.
            except FishRecognitionError as error:
                reason = str(error)
        try:
            text = local.transcribe(settings, audio, content_type)
        except ValueError as error:
            _status = {'engine': None, 'model': None, 'device': 'unavailable',
                       'compute_type': None, 'fallback': reason}
            if reason:
                raise ValueError(reason + ' Local fallback failed: ' + str(error)) from None
            raise
        _status = local.speech_status()
        if reason:
            _status['fallback'] = reason + ' Using local Whisper.' + (
                ' ' + _status['fallback'] if _status.get('fallback') else '')
        return text
    finally:
        _lock.release()
