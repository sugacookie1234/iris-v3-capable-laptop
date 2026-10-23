"""Download pinned Whisper models; optionally install NVIDIA's Windows runtime."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
from iris.desktop.speech_config import MODELS, model_path, speech_options
from iris.local_config import effective_environment


def install(settings=None, gpu_libraries=False):
    settings = effective_environment() if settings is None else settings
    name, device, _ = speech_options(settings)
    if gpu_libraries and os.name == 'nt' and device != 'cpu':
        import ctranslate2
        try:
            has_gpu = ctranslate2.get_cuda_device_count() > 0
        except (RuntimeError, OSError):
            has_gpu = False
        if has_gpu or device == 'cuda':
            print('Installing the NVIDIA speech runtime...')
            subprocess.run([sys.executable, '-m', 'pip', 'install', '-r',
                            str(Path(__file__).resolve().parents[2] / 'requirements-gpu.txt')], check=True)
        else:
            print('No NVIDIA device detected here. The local model can use CPU.')
    from huggingface_hub import snapshot_download
    repository, revision = MODELS[name]
    destination = model_path(name)
    print(f'Downloading/verifying {name}. The large model is about 1.6 GB; small.en about 0.5 GB.')
    snapshot_download(repo_id=repository, revision=revision, local_dir=str(destination),
                      allow_patterns=['model.bin', 'config.json', 'tokenizer.json',
                                      'vocabulary.*', 'preprocessor_config.json'])
    if not all((destination / part).is_file() and (destination / part).stat().st_size > 0
               for part in ('model.bin', 'config.json', 'tokenizer.json')):
        raise ValueError('Speech model download is incomplete. Run setup again.')
    print('Local Whisper fallback installed. Run check-speech.bat to verify inference on this computer.')
    return destination


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gpu-libraries', action='store_true')
    args = parser.parse_args()
    try:
        install(gpu_libraries=args.gpu_libraries)
    except Exception:
        print('Speech setup failed. Check the connection, free disk space and Python installation, then retry.')
        raise SystemExit(1)
