import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import wave
from iris.desktop import transcription as module


def wav(rate=16000, channels=1, seconds=.1):
    output=io.BytesIO()
    with wave.open(output,'wb') as stream:
        stream.setnchannels(channels);stream.setsampwidth(2);stream.setframerate(rate)
        stream.writeframes(b'\0\0' * int(rate*channels*seconds))
    return output.getvalue()


class LocalTranscriptionTests(unittest.TestCase):
    def test_invalid_recordings_never_reach_recognizer(self):
        for audio,kind in [(b'bad','audio/wav'),(wav(),'audio/webm'),(wav(8000),'audio/wav'),
                           (wav(channels=2),'audio/wav'),(wav(seconds=32),'audio/wav')]:
            with self.subTest(kind=kind, size=len(audio)), self.assertRaises(ValueError):
                module.transcribe({},audio,kind)

    def test_missing_model_has_actionable_error(self):
        with patch.object(module,'MODEL_PATH',Path('missing-test-speech-model')):
            with self.assertRaisesRegex(ValueError,'setup.bat'):
                module.transcribe({},wav(),'audio/wav')

    def test_local_recognizer_combines_results_without_network(self):
        class Recognizer:
            def __init__(self,*_): pass
            def AcceptWaveform(self,_): return True
            def Result(self): return json.dumps({'text':'hello'})
            def FinalResult(self): return json.dumps({'text':'iris'})
        fake=SimpleNamespace(Model=lambda _:object(),KaldiRecognizer=Recognizer,SetLogLevel=lambda _:None)
        with tempfile.TemporaryDirectory() as directory, patch.object(module,'MODEL_PATH',Path(directory)), \
             patch.object(module,'_model',None),patch.dict('sys.modules',{'vosk':fake}), \
             patch('urllib.request.urlopen',side_effect=AssertionError('No network allowed')):
            self.assertEqual(module.transcribe({},wav(),'audio/wav'),'hello iris')

    def test_second_simultaneous_recording_is_rejected(self):
        fake=SimpleNamespace(Model=None,KaldiRecognizer=None,SetLogLevel=None)
        with tempfile.TemporaryDirectory() as directory, patch.object(module,'MODEL_PATH',Path(directory)), \
             patch.dict('sys.modules',{'vosk':fake}):
            module._lock.acquire()
            try:
                with self.assertRaisesRegex(ValueError,'another recording'):
                    module.transcribe({},wav(),'audio/wav')
            finally:
                module._lock.release()
