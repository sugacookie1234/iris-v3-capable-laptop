"""Test local speech on a public fixture without uploading it to Fish Audio."""
import io
from pathlib import Path
import time
import wave
from iris.desktop.transcription import transcribe, speech_status
from iris.local_config import effective_environment


def sample_audio():
    from faster_whisper.audio import decode_audio
    fixture = Path(__file__).resolve().parents[2] / 'tests/fixtures/harvard.wav'
    samples = decode_audio(str(fixture), sampling_rate=16000)[:6 * 16000]
    output = io.BytesIO()
    with wave.open(output, 'wb') as target:
        target.setnchannels(1)
        target.setsampwidth(2)
        target.setframerate(16000)
        target.writeframes((samples.clip(-1, 1) * 32767).astype('<i2').tobytes())
    return output.getvalue()


def main():
    settings = effective_environment()
    audio = sample_audio()
    print('Testing local speech on a six-second public recording. First load can take a while.', flush=True)
    started = time.monotonic()
    text = transcribe(settings, audio, 'audio/wav')
    status = speech_status()
    print(f"Model: {status['model']}; device: {status['device']}; precision: {status['compute_type']}")
    if status['fallback']:
        print(status['fallback'])
    print(f'Elapsed including model load: {time.monotonic() - started:.1f}s')
    print('Recognized:', text)
    if not text:
        raise ValueError('No words were recognized from the public sample.')
    print('Local inference passed. Test your microphone in IRIS next.')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, ImportError) as error:
        print('Local speech check failed:', error)
        raise SystemExit(1)
