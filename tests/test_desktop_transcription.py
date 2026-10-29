import io
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import wave

from iris.desktop import transcription as module


def wav(rate=16000, channels=1, seconds=.1, width=2):
    output = io.BytesIO()
    with wave.open(output, 'wb') as stream:
        stream.setnchannels(channels)
        stream.setsampwidth(width)
        stream.setframerate(rate)
        stream.writeframes(b'\0' * int(rate * channels * seconds * width))
    return output.getvalue()


def recognizer(*texts):
    model = Mock()
    model.transcribe.side_effect = lambda *_args, **_kwargs: (
        iter(SimpleNamespace(text=text) for text in texts),
        SimpleNamespace(language='en'),
    )
    return model


class LocalTranscriptionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name)
        for filename in ('model.bin', 'config.json', 'tokenizer.json'):
            (self.path / filename).write_text('{}', encoding='utf-8')
        self.model = recognizer(' Hello', ' IRIS. ')
        self.factory = Mock(return_value=self.model)
        self.cuda_count = Mock(return_value=0)
        self.compute_types = Mock(return_value={'float16', 'int8', 'float32'})
        fake_whisper = SimpleNamespace(WhisperModel=self.factory)
        fake_ctranslate = SimpleNamespace(
            get_cuda_device_count=self.cuda_count,
            get_supported_compute_types=self.compute_types,
        )
        patches = [
            patch.object(module, 'has_speech', return_value=True),
            patch.object(module, 'model_path', return_value=self.path, create=True),
            patch.object(module, '_model', None),
            patch.object(module, '_model_key', None, create=True),
            patch.object(module, '_status', {
                'model': None, 'device': None,
                'compute_type': None, 'fallback': None,
            }, create=True),
            patch.dict('sys.modules', {
                'faster_whisper': fake_whisper, 'ctranslate2': fake_ctranslate,
            }),
            patch('urllib.request.urlopen', side_effect=AssertionError('No network allowed')),
        ]
        for patched in patches:
            patched.start()
            self.addCleanup(patched.stop)

    def test_invalid_recordings_never_reach_recognizer(self):
        invalid = [
            (b'bad', 'audio/wav'), (b'x' * 44, 'audio/wav'),
            (wav(), 'audio/webm'), (wav(8000), 'audio/wav'),
            (wav(channels=2), 'audio/wav'), (wav(width=1), 'audio/wav'),
            (wav(seconds=32), 'audio/wav'), (wav()[:-2], 'audio/wav'),
            (b'\0' * (module.MAX_AUDIO_BYTES + 1), 'audio/wav'),
        ]
        for audio, kind in invalid:
            with self.subTest(kind=kind, size=len(audio)):
                with self.assertRaises(ValueError):
                    module.transcribe({}, audio, kind)
        self.factory.assert_not_called()

    def test_missing_model_has_actionable_error(self):
        (self.path / 'model.bin').unlink()
        with self.assertRaisesRegex(ValueError, 'setup.bat'):
            module.transcribe({}, wav(), 'audio/wav')
        self.factory.assert_not_called()

    def test_broken_gpu_libraries_do_not_disable_cpu_fallback(self):
        self.cuda_count.return_value = 1
        with patch.object(module, '_prepare_gpu_libraries', side_effect=OSError('Missing DLL')):
            self.assertEqual(module.transcribe({}, wav(), 'audio/wav'), 'Hello IRIS.')
        self.assertEqual(self.factory.call_args.kwargs['device'], 'cpu')
        self.assertIn('initialization failed', module.speech_status()['fallback'])

    def test_invalid_model_and_device_settings_do_not_load_a_model(self):
        for settings in (
            {'IRIS_STT_MODEL': '../../untrusted-model'},
            {'IRIS_STT_DEVICE': 'unexpected'},
        ):
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                module.transcribe(settings, wav(), 'audio/wav')
        self.factory.assert_not_called()

    def test_cpu_recognizer_combines_segments_without_network(self):
        self.assertEqual(module.transcribe({}, wav(), 'audio/wav'), 'Hello IRIS.')
        self.factory.assert_called_once_with(
            str(self.path), device='cpu', compute_type='int8',
            local_files_only=True, num_workers=1,
        )
        options = self.model.transcribe.call_args.kwargs
        self.assertEqual(options['beam_size'], 5)
        self.assertEqual(options['language'], 'en')
        self.assertTrue(options['vad_filter'])
        self.assertFalse(options['condition_on_previous_text'])
        self.assertEqual(options['no_speech_threshold'], .6)
        status = module.speech_status()
        self.assertEqual(status['model'], 'large-v3-turbo')
        self.assertEqual(status['device'], 'cpu')
        self.assertEqual(status['compute_type'], 'int8')

    def test_auto_language_does_not_force_english(self):
        module.transcribe({'IRIS_STT_LANGUAGE': 'auto'}, wav(), 'audio/wav')
        self.assertIsNone(self.model.transcribe.call_args.kwargs['language'])

    def test_silence_does_not_invent_a_transcript(self):
        self.factory.return_value = recognizer()
        self.assertEqual(module.transcribe({}, wav(), 'audio/wav'), '')

    def test_noise_is_rejected_before_loading_whisper(self):
        with patch.object(module, 'has_speech', return_value=False):
            self.assertEqual(module.transcribe({}, wav(), 'audio/wav'), '')
        self.factory.assert_not_called()

    def test_uncertain_segment_discards_entire_turn_instead_of_partial_command(self):
        for metric, value in (('no_speech_prob', .8), ('avg_logprob', -1.5),
                              ('compression_ratio', 3.0), ('avg_logprob', float('nan'))):
            with self.subTest(metric=metric):
                self.model.transcribe.side_effect = lambda *_a, **_k: (
                    iter([SimpleNamespace(text='Do not', **{metric: value}),
                          SimpleNamespace(text='open Chrome')]), SimpleNamespace(language='en'))
                self.assertEqual(module.transcribe({}, wav(), 'audio/wav'), '')

    def test_thirty_one_seconds_and_wav_content_type_parameters_are_accepted(self):
        self.assertEqual(
            module.transcribe({}, wav(seconds=31), 'audio/wav; codecs=pcm'),
            'Hello IRIS.',
        )

    def test_auto_uses_nvidia_gpu_when_float16_is_supported(self):
        self.cuda_count.return_value = 1
        module.transcribe({}, wav(), 'audio/wav')
        self.factory.assert_called_once_with(
            str(self.path), device='cuda', compute_type='float16',
            local_files_only=True, num_workers=1,
        )
        self.assertEqual(module.speech_status()['device'], 'cuda')
        self.assertFalse(module.speech_status()['fallback'])

    def test_auto_uses_cpu_when_gpu_cannot_run_float16(self):
        self.cuda_count.return_value = 1
        self.compute_types.return_value = {'float32'}
        module.transcribe({}, wav(), 'audio/wav')
        self.assertEqual(self.factory.call_args.kwargs['device'], 'cpu')

    def test_explicit_cpu_does_not_choose_available_gpu(self):
        self.cuda_count.return_value = 1
        module.transcribe({'IRIS_STT_DEVICE': 'cpu'}, wav(), 'audio/wav')
        self.assertEqual(self.factory.call_args.kwargs['device'], 'cpu')

    def test_gpu_load_failure_falls_back_without_changing_selected_model(self):
        self.cuda_count.return_value = 1
        self.factory.side_effect = [RuntimeError('CUDA library missing'), self.model]
        self.assertEqual(module.transcribe({}, wav(), 'audio/wav'), 'Hello IRIS.')
        self.assertEqual(self.factory.call_count, 2)
        first, second = self.factory.call_args_list
        self.assertEqual(first.kwargs['device'], 'cuda')
        self.assertEqual(second.kwargs['device'], 'cpu')
        self.assertEqual(first.args, second.args)
        self.assertEqual(module.speech_status()['model'], 'large-v3-turbo')
        self.assertTrue(module.speech_status()['fallback'])
        module.transcribe({}, wav(), 'audio/wav')
        self.assertEqual(self.factory.call_count, 2)

    def test_lazy_gpu_failure_retries_complete_recording_once_on_cpu(self):
        self.cuda_count.return_value = 1

        def interrupted_segments():
            yield SimpleNamespace(text='Discard this partial result')
            raise RuntimeError('CUDA failed while decoding')

        gpu = Mock()
        gpu.transcribe.return_value = (interrupted_segments(), SimpleNamespace(language='en'))
        cpu = recognizer('Complete CPU result.')
        self.factory.side_effect = [gpu, cpu]
        self.assertEqual(
            module.transcribe({}, wav(), 'audio/wav'), 'Complete CPU result.',
        )
        self.assertEqual(self.factory.call_count, 2)
        self.assertEqual(module.speech_status()['device'], 'cpu')
        self.assertTrue(module.speech_status()['fallback'])
        module.transcribe({}, wav(), 'audio/wav')
        self.assertEqual(self.factory.call_count, 2)

    def test_explicit_cuda_failure_does_not_silently_switch_to_cpu(self):
        self.cuda_count.return_value = 1
        self.factory.side_effect = RuntimeError('CUDA library missing')
        with self.assertRaisesRegex(ValueError, r'(?i)CUDA|NVIDIA|GPU'):
            module.transcribe({'IRIS_STT_DEVICE': 'cuda'}, wav(), 'audio/wav')
        self.assertEqual(self.factory.call_count, 1)
        self.assertEqual(self.factory.call_args.kwargs['device'], 'cuda')

    def test_cpu_fallback_failure_stops_after_one_retry(self):
        self.cuda_count.return_value = 1
        gpu = recognizer()
        gpu.transcribe.side_effect = RuntimeError('CUDA decoder failed')
        cpu = recognizer()
        cpu.transcribe.side_effect = RuntimeError('CPU decoder failed')
        self.factory.side_effect = [gpu, cpu]
        with self.assertRaises(ValueError):
            module.transcribe({}, wav(), 'audio/wav')
        self.assertEqual(self.factory.call_count, 2)
        self.assertEqual(cpu.transcribe.call_count, 1)

    def test_second_simultaneous_recording_is_rejected(self):
        module._lock.acquire()
        try:
            with self.assertRaisesRegex(ValueError, 'another recording'):
                module.transcribe({}, wav(), 'audio/wav')
        finally:
            module._lock.release()
        self.factory.assert_not_called()

    def test_model_is_reused_but_changed_selection_reloads_it(self):
        module.transcribe({}, wav(), 'audio/wav')
        module.transcribe({}, wav(), 'audio/wav')
        self.assertEqual(self.factory.call_count, 1)
        module.transcribe({'IRIS_STT_MODEL': 'small.en'}, wav(), 'audio/wav')
        self.assertEqual(self.factory.call_count, 2)
        self.assertEqual(module.speech_status()['model'], 'small.en')

    def test_failed_transcription_releases_lock_for_next_recording(self):
        self.model.transcribe.side_effect = RuntimeError('Decoder failed')
        with self.assertRaises(ValueError):
            module.transcribe({'IRIS_STT_DEVICE': 'cpu'}, wav(), 'audio/wav')
        self.model.transcribe.side_effect = None
        self.model.transcribe.return_value = (
            iter([SimpleNamespace(text='Recovered.')]), SimpleNamespace(language='en'),
        )
        self.assertEqual(
            module.transcribe({'IRIS_STT_DEVICE': 'cpu'}, wav(), 'audio/wav'),
            'Recovered.',
        )
