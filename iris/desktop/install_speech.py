"""Install the pinned official Vosk English model into ignored local storage."""
import hashlib
from pathlib import Path
import tempfile
import urllib.request
import zipfile
from iris.desktop.transcription import MODEL_PATH

URL = 'https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip'
SHA256 = '30f26242c4eb449f948e42cb302dd7a686cb29a3423a8367f99ff41780942498'


def install(archive=None):
    if (MODEL_PATH / 'am/final.mdl').is_file() and (MODEL_PATH / 'conf/model.conf').is_file():
        print('Local speech model is ready.')
        return
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=MODEL_PATH.parent) as temporary:
        root = Path(temporary)
        source = Path(archive) if archive else root / 'model.zip'
        if not archive:
            print('Downloading the 40 MB local English speech model...')
            with urllib.request.urlopen(URL, timeout=120) as response, source.open('wb') as output:
                total = 0
                while chunk := response.read(1024 * 1024):
                    total += len(chunk)
                    if total > 60 * 1024 * 1024:
                        raise ValueError('Speech model download exceeded its size limit.')
                    output.write(chunk)
        if hashlib.sha256(source.read_bytes()).hexdigest() != SHA256:
            raise ValueError('Speech model checksum did not match. No model installed.')
        with zipfile.ZipFile(source) as bundle:
            for entry in bundle.infolist():
                target = (root / entry.filename).resolve()
                if not target.is_relative_to(root.resolve()):
                    raise ValueError('Invalid speech model archive path.')
            bundle.extractall(root)
        (root / MODEL_PATH.name).rename(MODEL_PATH)
    print('Local speech model installed. Microphone audio stays on this computer.')


if __name__ == '__main__':
    try:
        install()
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        print('Speech setup failed:', error)
        raise SystemExit(1)
