"""Local faster-whisper transcription with explicit device status and CPU fallback."""
import io
import ctypes
import os
from pathlib import Path
import sysconfig
import threading
import wave
from iris.desktop.speech_config import model_path, speech_options
from iris.desktop.speech_guard import has_speech, accepted_text, confident_segment

MAX_AUDIO_BYTES = 1100000
_lock = threading.Lock()
_model = None
_model_key = None
_dll_handles = []
_gpu_libraries_ready = False
_status = {'engine': 'faster-whisper', 'model': None, 'device': 'not loaded',
           'compute_type': None, 'fallback': None}


def speech_status():
    return dict(_status)


def _prepare_gpu_libraries():
    global _gpu_libraries_ready
    if os.name != 'nt' or _gpu_libraries_ready:
        return
    directory = Path(sysconfig.get_path('purelib')) / 'nvidia/cublas/bin'
    if directory.is_dir():
        _dll_handles.append(os.add_dll_directory(str(directory)))
        os.environ['PATH'] = str(directory) + os.pathsep + os.environ.get('PATH', '')
        # CTranslate2 uses LoadLibraryA; preload the pinned DLLs rather than an older CUDA_PATH.
        for filename in ('cublasLt64_12.dll', 'cublas64_12.dll'):
            _dll_handles.append(ctypes.WinDLL(str(directory / filename)))
    _gpu_libraries_ready = True


def _load_model(settings, force_cpu=False, fallback_reason=None):
    global _model, _model_key, _status
    name, requested, _ = speech_options(settings)
    key = (name, requested)
    if _model is not None and _model_key == key and not force_cpu:
        return _model
    path = model_path(name)
    if not all((path / file).is_file() for file in ('model.bin', 'config.json', 'tokenizer.json')):
        raise ValueError('Local Whisper model is missing. Run setup.bat to install voice input.')
    try:
        import ctranslate2
        from faster_whisper import WhisperModel
    except (ImportError, OSError):
        raise ValueError('Whisper could not load. Run setup.bat; Windows may also need the Microsoft Visual C++ runtime.') from None
    device, compute = 'cpu', 'int8'
    reason = fallback_reason
    if requested != 'cpu' and not force_cpu:
        try:
            if ctranslate2.get_cuda_device_count() > 0:
                _prepare_gpu_libraries()
                if 'float16' not in ctranslate2.get_supported_compute_types('cuda'):
                    raise RuntimeError('GPU does not offer float16.')
                device, compute = 'cuda', 'float16'
            elif requested == 'cuda':
                raise RuntimeError('No CUDA device.')
            else:
                reason = 'No NVIDIA device is available; using CPU.'
        except (RuntimeError, OSError):
            if requested == 'cuda':
                raise ValueError('NVIDIA speech is unavailable. Update the NVIDIA driver and run setup.bat, or choose auto/CPU.') from None
            reason = 'NVIDIA initialization failed; using CPU. Check the driver and GPU libraries.'
    _model = None
    _model_key = None
    _status = {'engine': 'faster-whisper', 'model': name, 'device': 'not loaded',
               'compute_type': None, 'fallback': reason}
    try:
        loaded = WhisperModel(str(path), device=device, compute_type=compute,
                              local_files_only=True, num_workers=1)
    except (RuntimeError, OSError):
        if requested == 'auto' and device == 'cuda':
            return _load_model(settings, force_cpu=True,
                               fallback_reason='NVIDIA model loading failed; using CPU. Check driver, libraries and available GPU memory.')
        raise ValueError('Whisper model could not load. Run setup.bat to check the model and device; try auto/CPU if NVIDIA is unavailable.') from None
    _model, _model_key = loaded, key
    _status = {'engine': 'faster-whisper', 'model': name, 'device': device,
               'compute_type': compute, 'fallback': reason}
    return loaded


def _recognize(model, audio, language):
    # Inference runs in the segment iterator, so consume it inside the retry boundary.
    segments, info = model.transcribe(io.BytesIO(audio), language=None if language == 'auto' else language,
        beam_size=5, temperature=0.0, vad_filter=True,
        vad_parameters={'threshold': .6, 'min_speech_duration_ms': 160, 'min_silence_duration_ms': 160},
        condition_on_previous_text=False, no_speech_threshold=0.6)
    pieces = []
    for segment in segments:
        if segment.text.strip() and not confident_segment(segment):
            # Reject the whole turn, not a fragment that could change its meaning
            # (for example by dropping an uncertain 'do not'). Consume the iterator
            # first so lazy GPU failures still use the existing CPU retry boundary.
            pieces.append(None)
        else:
            pieces.append(segment.text.strip())
    if None in pieces:
        return ''
    return accepted_text(' '.join(pieces), language, getattr(info, 'language', None))


def validate_audio(audio, content_type):
    if content_type.split(';')[0].strip().lower() != 'audio/wav' or not 44 <= len(audio) <= MAX_AUDIO_BYTES:
        raise ValueError('Record a short spoken request in WAV format.')
    try:
        with wave.open(io.BytesIO(audio), 'rb') as source:
            if (source.getnchannels(), source.getsampwidth(), source.getframerate()) != (1, 2, 16000):
                raise ValueError('Voice input requires 16 kHz mono PCM audio.')
            if source.getnframes() > 16000 * 31 or source.getcomptype() != 'NONE':
                raise ValueError('Keep spoken requests under 30 seconds.')
            if len(source.readframes(source.getnframes())) != source.getnframes() * 2:
                raise ValueError('Recording was incomplete.')
    except (wave.Error, EOFError):
        raise ValueError('The microphone recording could not be decoded.') from None


def transcribe(settings, audio, content_type):
    _, requested, language = speech_options(settings)
    validate_audio(audio, content_type)
    if not _lock.acquire(blocking=False):
        raise ValueError('IRIS is transcribing another recording. Try again shortly.')
    try:
        if not has_speech(audio):
            return ''
        model = _load_model(settings)
        try:
            return _recognize(model, audio, language)
        except (RuntimeError, OSError):
            if requested != 'auto' or _status['device'] != 'cuda':
                raise ValueError('Whisper could not transcribe this recording. Check the speech device in setup.bat.') from None
            model = None
            model = _load_model(settings, force_cpu=True,
                fallback_reason='NVIDIA transcription failed; using CPU. Check GPU libraries, driver and memory.')
            try:
                return _recognize(model, audio, language)
            except (RuntimeError, OSError):
                raise ValueError('CPU transcription also failed. Try a shorter recording or the small.en profile.') from None
    finally:
        _lock.release()
