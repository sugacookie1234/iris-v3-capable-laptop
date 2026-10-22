"""Fish Audio REST text-to-speech adapter.

The adapter generates audio only; playback is supplied by an explicitly
injected local sink. No microphone capture, audio persistence, or automatic
upload beyond the requested Fish Audio TTS call is performed here.
"""
from __future__ import annotations

import os
import base64
import hashlib
import ntpath
import math
import re
import shutil
import sys
import subprocess
import struct
from dataclasses import dataclass, replace
import tempfile
import wave
from enum import StrEnum
from io import BytesIO
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from iris.voice.adapters import VoiceBackendError
from iris.voice.protocols import AudioSink, LocalSpeechSynthesizer


FISH_AUDIO_TTS_URL = "https://api.fish.audio/v1/tts"
DEFAULT_FISH_VOICE_ID = "88b183bfbdda44a09ad4474712b967f4"
DEFAULT_FISH_MODEL = "s2.1-pro-free"
MAX_TTS_CHARACTERS = 10_000
MAX_AUDIO_BYTES = 10 * 1024 * 1024
_PLAYBACK_PREROLL_MS = 150
_FISH_STREAM_RIFF_SIZE = 4_294_967_076
_FISH_STREAM_DATA_SIZE = 4_294_967_040


def normalize_tts_text(text: str) -> str:
    """Render only standalone canonical IRIS names for speech pronunciation.

    URL/path separators and identifier characters are boundaries we deliberately
    reject, so provider text such as ``/IRIS-v2`` or ``IRIS_MODEL`` is unchanged.
    """
    boundary = r"A-Za-z0-9_./\\:"
    text = re.sub(
        rf"(?<![{boundary}])I\.R\.I\.S\.(?![{boundary}])",
        "Iris",
        text,
    )
    return re.sub(
        rf"(?<![{boundary}])IRIS(?![{boundary}])",
        "Iris",
        text,
    )


class PlaybackFailureCategory(StrEnum):
    """Safe categories for diagnosing local playback failures."""

    MALFORMED_WAV = "malformed_wav"
    UNSUPPORTED_WAV_ENCODING = "unsupported_wav_encoding"
    UNSUPPORTED_WAV_PARAMETERS = "unsupported_wav_parameters"
    INVALID_WAV_SAMPLES = "invalid_wav_samples"
    NON_AUDIO_RESPONSE = "non_audio_response"
    JSON_ERROR_RESPONSE = "json_error_response"
    OVERSIZED_AUDIO = "oversized_audio"
    MISSING_WINDOWS_PYTHON = "missing_windows_python"
    MISSING_WINSOUND = "missing_winsound"
    MISSING_POWERSHELL = "missing_powershell"
    MISSING_WSLPATH = "missing_wslpath"
    WINDOWS_TEMP_DISCOVERY = "windows_temp_discovery"
    WINDOWS_TEMP_PATH_CONVERSION = "windows_temp_path_conversion"
    WAV_FILE_INACCESSIBLE = "wav_file_inaccessible"
    POWERSHELL_INVOCATION = "powershell_invocation"
    SOUNDPLAYER_LOAD = "soundplayer_load"
    WAV_ACCESS = "wav_access"
    PLAYBACK_DEVICE = "playback_device"
    POWERSHELL_SOUNDPLAYER = "powershell_soundplayer"
    CHILD_PROCESS_TIMEOUT = "child_process_timeout"
    CHILD_PROCESS_NONZERO_EXIT = "child_process_nonzero_exit"
    GENERAL = "general_playback"


class StandardLibraryAudioSink:
    """Play Fish WAV bytes locally through a standard-library platform backend."""

    def __init__(self) -> None:
        self._device = None
        self._stopped = False

    def play(self, audio: bytes, *, audio_format: str = "wav") -> None:
        if audio_format.lower() != "wav":
            raise LocalPlaybackError("The standard-library sink supports WAV audio only.")
        try:
            with wave.open(BytesIO(audio), "rb") as wav:
                channels, width, rate = wav.getnchannels(), wav.getsampwidth(), wav.getframerate()
                frames = wav.readframes(wav.getnframes())
        except (wave.Error, EOFError, ValueError) as exc:
            raise LocalPlaybackError("Local playback requires valid WAV audio.") from exc
        self._stopped = False
        if sys.platform == "win32":
            try:
                import winsound
                winsound.PlaySound(audio, winsound.SND_MEMORY)
                return
            except (ImportError, OSError) as exc:
                raise LocalPlaybackError("Windows local audio playback is unavailable.") from exc
        if _running_under_wsl():
            raise LocalPlaybackError(
                "WSL local audio playback is unavailable by default; configure and inject a local sink."
            )
        try:
            import ossaudiodev
            device = ossaudiodev.open("w")
            self._device = device
            try:
                device.setparameters(ossaudiodev.AFMT_S16_LE if width == 2 else ossaudiodev.AFMT_U8,
                                     channels, rate)
                if not self._stopped:
                    device.writeall(frames)
            finally:
                device.close()
                self._device = None
        except (ImportError, OSError, AttributeError) as exc:
            raise LocalPlaybackError("Local audio playback requires an available OSS device.") from exc

    def __call__(self, audio: bytes) -> None:
        """Compatibility shim for the original callable sink contract."""
        self.play(audio, audio_format="wav")

    def stop(self) -> None:
        self._stopped = True
        device = self._device
        if device is not None:
            try:
                device.close()
            except Exception:
                pass
            self._device = None

    def close(self) -> None:
        self.stop()


@dataclass(frozen=True)
class WavFormat:
    """Allowlisted numeric diagnostics only: no samples, metadata, or paths."""

    format_tag: int
    encoding_tag: int
    channels: int
    sample_rate: int
    bits_per_sample: int
    valid_bits: int
    channel_mask: int
    frame_count: int


@dataclass(frozen=True)
class WavDiagnostic:
    """Numeric/header-only WAV facts; no audio bytes or paths are retained."""

    riff_marker: str
    wave_marker: str
    declared_riff_size: int | None
    actual_byte_length: int
    chunk_ids: tuple[str, ...]
    chunk_sizes: tuple[int, ...]
    audio_format_tag: int | None
    channels: int | None
    sample_rate: int | None
    bits_per_sample: int | None
    data_length: int | None


@dataclass(frozen=True)
class PcmDiagnostics:
    """Numeric-only diagnostics for normalized 16-bit PCM audio."""

    frame_count: int
    duration_seconds: float
    nonzero_sample_count: int
    peak_abs_amplitude: int
    rms_level: float


@dataclass(frozen=True)
class AudioPlaybackDiagnostics:
    """Public, read-only numeric playback diagnostics; no raw audio or paths."""

    byte_length: int
    frame_count: int
    duration_seconds: float
    nonzero_sample_count: int
    peak_abs_amplitude: int
    rms_level: float
    checksum: str
    backend: str | None
    output_device_category: str | None


@dataclass(frozen=True)
class AudioResponseMetadata:
    """Safe response facts used for diagnostics; never includes response bytes."""

    content_type: str
    byte_length: int
    magic: str


def _audio_response_metadata(content_type: str | None, audio: bytes) -> AudioResponseMetadata:
    raw_type = (content_type or "").split(";", 1)[0].strip().lower()
    safe_type = raw_type if re.fullmatch(r"[a-z0-9.+_-]+/[a-z0-9.+_-]+", raw_type) else "unknown"
    prefix = audio[:4]
    if audio.startswith(b"RIFF"):
        magic = "RIFF"
    elif audio.startswith(b"ID3"):
        magic = "ID3"
    elif audio.startswith(b"OggS"):
        magic = "OggS"
    elif audio.startswith(b"fLaC"):
        magic = "fLaC"
    elif audio.startswith(b"\x1f\x8b"):
        magic = "GZIP"
    elif audio.startswith((b"{", b"[")):
        magic = "JSON"
    elif len(audio) >= 2 and prefix[0] == 0xFF and prefix[1] & 0xE0 == 0xE0:
        magic = "MPEG"
    else:
        magic = "OTHER"
    return AudioResponseMetadata(safe_type, len(audio), magic)


def _response_content_type(response) -> str:
    headers = getattr(response, "headers", None)
    if headers is None:
        return ""
    try:
        return str(headers.get("Content-Type", ""))
    except Exception:
        return ""


def _safe_fourcc(value: bytes) -> str:
    if len(value) != 4:
        return "????"
    return value.decode("ascii", "replace") if all(32 <= c < 127 for c in value) else value.hex()


def _wav_diagnostic(audio: bytes) -> WavDiagnostic:
    """Collect bounded RIFF facts without interpreting payload bytes."""
    actual = len(audio) if isinstance(audio, bytes) else 0
    riff = audio[:4].decode("ascii", "replace") if isinstance(audio, bytes) else ""
    wave_marker = audio[8:12].decode("ascii", "replace") if isinstance(audio, bytes) else ""
    declared = struct.unpack_from("<I", audio, 4)[0] if isinstance(audio, bytes) and len(audio) >= 8 else None
    ids: list[str] = []
    sizes: list[int] = []
    fmt_tag = channels = rate = bits = data_len = None
    limit = min(actual, declared + 8) if declared is not None else actual
    offset = 12
    while isinstance(audio, bytes) and offset + 8 <= limit and len(ids) < 64:
        chunk_id = audio[offset:offset + 4]
        size = struct.unpack_from("<I", audio, offset + 4)[0]
        ids.append(_safe_fourcc(chunk_id)); sizes.append(size)
        start = offset + 8
        if chunk_id == b"fmt " and start + 16 <= actual:
            fmt_tag, channels, rate, _, _, bits = struct.unpack_from("<HHIIHH", audio, start)
        if chunk_id == b"data":
            data_len = size
        if size > limit - start:
            break
        offset = start + size + (size & 1)
    return WavDiagnostic(riff, wave_marker, declared, actual, tuple(ids), tuple(sizes),
                         fmt_tag, channels, rate, bits, data_len)


def _inspect_windows_wav(audio: bytes) -> tuple[WavFormat, memoryview]:
    """Parse bounded RIFF chunks without trusting sizes or copying metadata."""
    def malformed():
        raise LocalPlaybackError("WAV audio is malformed, truncated, empty, or oversized.",
                                 category=PlaybackFailureCategory.MALFORMED_WAV,
                                 diagnostic=_wav_diagnostic(audio))

    if (not isinstance(audio, bytes) or not 12 <= len(audio) <= MAX_AUDIO_BYTES or
            audio[:4] != b"RIFF" or audio[8:12] != b"WAVE"):
        malformed()
    declared_size = struct.unpack_from("<I", audio, 4)[0]
    streaming_placeholder = declared_size == _FISH_STREAM_RIFF_SIZE
    if declared_size < 4 or (declared_size + 8 > len(audio) and not streaming_placeholder):
        malformed()
    # RIFF may legally have trailing bytes after its declared payload; the
    # standard-library wave reader ignores them.
    end = len(audio) if streaming_placeholder else declared_size + 8
    fmt = data = None
    last_kind = None
    offset = 12
    while offset < end:
        if offset + 8 > end:
            malformed()
        kind = audio[offset:offset + 4]
        last_kind = kind
        size = struct.unpack_from("<I", audio, offset + 4)[0]
        start = offset + 8
        if start > end or (not streaming_placeholder and start + size > end):
            malformed()
        if kind == b"fmt ":
            if fmt is not None or data is not None:
                malformed()
            fmt = memoryview(audio)[start:start + size]
        elif kind == b"data":
            if fmt is None or data is not None:
                malformed()
            if streaming_placeholder:
                if size != _FISH_STREAM_DATA_SIZE or start >= len(audio):
                    malformed()
                # Fish leaves a max-sized placeholder in the header while
                # streaming the actual data to EOF; normalize to bytes present.
                size = len(audio) - start
            elif start + size > end:
                malformed()
            data = memoryview(audio)[start:start + size]
            if streaming_placeholder and start + size != len(audio):
                malformed()
        offset = start + size + (size & 1)
        # Some wave writers omit padding on the final odd-sized data chunk.
        if offset == end + 1 and kind == b"data" and start + size == end:
            offset = end
        if offset > end:
            malformed()
    if fmt is None or len(fmt) < 16 or data is None or not len(data):
        malformed()
    if streaming_placeholder and last_kind != b"data":
        malformed()
    tag, channels, rate, byte_rate, align, bits = struct.unpack_from("<HHIIHH", fmt)
    encoding, valid_bits, mask = tag, bits, 0
    if len(fmt) != 16:
        if len(fmt) < 18 or struct.unpack_from("<H", fmt, 16)[0] != len(fmt) - 18:
            malformed()
    if tag == 0xFFFE:
        if len(fmt) < 40:
            malformed()
        valid_bits, mask = struct.unpack_from("<HI", fmt, 18)
        guid = bytes(fmt[24:40])
        # Only standard PCM/IEEE float subtypes are interpreted.
        encoding = (struct.unpack_from("<I", guid)[0]
                    if guid[4:] == bytes.fromhex("00001000800000aa00389b71") else -1)
    if (not channels or not rate or not align or len(data) % align or
            byte_rate != rate * align):
        malformed()
    info = WavFormat(tag, encoding, channels, rate, bits, valid_bits, mask, len(data) // align)
    if encoding in (1, 3) and align != channels * ((bits + 7) // 8):
        malformed()
    return info, data


def _normalize_windows_wav(info: WavFormat, data: memoryview) -> bytes:
    """Produce classic 16-bit PCM using wave; no codec or resampling guesses."""
    if info.encoding_tag not in (1, 3):
        raise LocalPlaybackError("WAV encoding is unsupported; uncompressed PCM or IEEE float is required.",
                                 category=PlaybackFailureCategory.UNSUPPORTED_WAV_ENCODING)
    widths = (8, 16, 24, 32) if info.encoding_tag == 1 else (32, 64)
    if (info.channels not in (1, 2) or
            info.sample_rate not in (8000, 11025, 16000, 22050, 24000, 32000, 44100, 48000) or
            info.bits_per_sample not in widths or info.valid_bits != info.bits_per_sample or
            info.channel_mask not in ((0, 4) if info.channels == 1 else (0, 3))):
        raise LocalPlaybackError(
            "WAV parameters are unsupported; use mono/stereo, a standard 8–48 kHz rate, and full-width PCM or float samples.",
            category=PlaybackFailureCategory.UNSUPPORTED_WAV_PARAMETERS,
        )
    sample_count = info.frame_count * info.channels
    if sample_count * 2 + 44 > MAX_AUDIO_BYTES:
        raise LocalPlaybackError("Normalized WAV audio exceeds the playback size limit.",
                                 category=PlaybackFailureCategory.UNSUPPORTED_WAV_PARAMETERS)
    pcm = bytearray(sample_count * 2)
    width = info.bits_per_sample // 8
    for index in range(sample_count):
        offset = index * width
        if info.encoding_tag == 3:
            value = struct.unpack_from("<f" if width == 4 else "<d", data, offset)[0]
            if not math.isfinite(value):
                raise LocalPlaybackError("WAV float samples contain non-finite values.",
                                         category=PlaybackFailureCategory.INVALID_WAV_SAMPLES)
            value = round(max(-1.0, min(1.0, value)) * 32768)
            value = max(-32768, min(32767, value))
        elif width == 1:
            value = (data[offset] - 128) << 8
        else:
            value = int.from_bytes(data[offset:offset + width], "little", signed=True)
            value >>= info.bits_per_sample - 16
        struct.pack_into("<h", pcm, index * 2, value)
    output = BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(info.channels)
        wav.setsampwidth(2)
        wav.setframerate(info.sample_rate)
        wav.writeframes(pcm)
    return output.getvalue()


def _pcm_diagnostics(audio: bytes) -> PcmDiagnostics:
    with wave.open(BytesIO(audio), "rb") as wav:
        frame_count = wav.getnframes()
        channels = wav.getnchannels()
        rate = wav.getframerate()
        samples = wav.readframes(frame_count)
    values = struct.unpack("<" + "h" * (len(samples) // 2), samples) if samples else ()
    nonzero = sum(value != 0 for value in values)
    peak = max((abs(value) for value in values), default=0)
    rms = math.sqrt(sum(value * value for value in values) / len(values)) if values else 0.0
    return PcmDiagnostics(
        frame_count=frame_count,
        duration_seconds=round(frame_count / rate, 6) if rate else 0.0,
        nonzero_sample_count=nonzero,
        peak_abs_amplitude=peak,
        rms_level=round(rms, 6),
    )


def _audio_playback_diagnostics(audio: bytes, *, backend: str | None,
                                output_device_category: str | None) -> AudioPlaybackDiagnostics:
    pcm = _pcm_diagnostics(audio)
    return AudioPlaybackDiagnostics(
        byte_length=len(audio),
        frame_count=pcm.frame_count,
        duration_seconds=pcm.duration_seconds,
        nonzero_sample_count=pcm.nonzero_sample_count,
        peak_abs_amplitude=pcm.peak_abs_amplitude,
        rms_level=pcm.rms_level,
        checksum=hashlib.sha256(audio).hexdigest()[:16],
        backend=backend,
        output_device_category=output_device_category,
    )


def _canonicalize_pcm_wav(audio: bytes) -> bytes:
    """Convert normalized PCM to conservative mono/16-bit/8 kHz WAV."""
    with wave.open(BytesIO(audio), "rb") as wav:
        channels = wav.getnchannels()
        rate = wav.getframerate()
        frames = wav.getnframes()
        raw = wav.readframes(frames)
    values = struct.unpack("<" + "h" * (len(raw) // 2), raw) if raw else ()
    target_frames = max(1, round(frames * 8000 / rate)) if frames else 0
    mono = []
    for index in range(target_frames):
        source = min(frames - 1, int(index * rate / 8000))
        start = source * channels
        samples = values[start:start + channels]
        mono.append(round(sum(samples) / len(samples)) if samples else 0)
    output = BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(struct.pack("<" + "h" * len(mono), *mono) if mono else b"")
    return output.getvalue()


def _with_playback_preroll(audio: bytes) -> bytes:
    """Prefix 150 ms of digital silence to a separate normalized PCM buffer."""
    with wave.open(BytesIO(audio), "rb") as wav:
        channels = wav.getnchannels()
        rate = wav.getframerate()
        width = wav.getsampwidth()
        silence_frames = (rate * _PLAYBACK_PREROLL_MS + 500) // 1000
        silence_bytes = silence_frames * channels * width
        if len(audio) + silence_bytes > MAX_AUDIO_BYTES:
            raise LocalPlaybackError(
                "WAV audio with playback pre-roll exceeds the playback size limit.",
                category=PlaybackFailureCategory.OVERSIZED_AUDIO,
            )
        frames = wav.readframes(wav.getnframes())
    output = BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(width)
        wav.setframerate(rate)
        wav.writeframes(b"\0" * silence_bytes + frames)
    return output.getvalue()


# Fixed child code: paths are data in argv, never interpolated into code.
_WINDOWS_AUDIO_SCRIPT = """import sys
if sys.argv[1] == 'temp':
    try:
        import tempfile
        print(tempfile.gettempdir())
    except Exception:
        sys.exit(44)
else:
    try:
        import winsound
    except ImportError:
        sys.exit(41)
    if sys.platform != 'win32':
        sys.exit(41)
    try:
        with open(sys.argv[2], 'rb') as audio:
            audio.read(1)
    except OSError:
        sys.exit(42)
    try:
        winsound.PlaySound(sys.argv[2], winsound.SND_FILENAME | winsound.SND_SYNC | winsound.SND_NODEFAULT)
    except Exception:
        sys.exit(43)
"""

# Keep the encoded command fixed; the path is data read from stdin, not code
# or an unsupported trailing -EncodedCommand argument.
_POWERSHELL_AUDIO_SCRIPT = r'''$ErrorActionPreference = 'Stop'
$wavPath = [Console]::In.ReadLine()
try {
    if (-not (Test-Path -LiteralPath $wavPath -PathType Leaf)) { exit 40 }
    try { if ([IO.FileInfo]::new($wavPath).Length -le 0) { exit 40 } } catch { exit 40 }
    $player = New-Object System.Media.SoundPlayer
    $player.SoundLocation = $wavPath
    try { $player.Load(); [Console]::WriteLine('IRIS_SOUNDPLAYER_LOAD_OK') } catch {
        [Console]::WriteLine('IRIS_SOUNDPLAYER_LOAD_EXCEPTION'); exit 42
    }
    try { $player.PlaySync(); [Console]::WriteLine('IRIS_PLAYSYNC_OK') } catch {
        [Console]::WriteLine('IRIS_PLAYSYNC_EXCEPTION'); exit 43
    }
    exit 0
} catch { exit 43 }
'''
_POWERSHELL_MARKERS = frozenset({
    "IRIS_SOUNDPLAYER_LOAD_OK", "IRIS_SOUNDPLAYER_LOAD_EXCEPTION",
    "IRIS_PLAYSYNC_OK", "IRIS_PLAYSYNC_EXCEPTION",
})


def _encode_powershell_command(script: str) -> str:
    """Encode PowerShell as UTF-16LE for -EncodedCommand, avoiding quoting."""
    return base64.b64encode(script.encode("utf-16le")).decode("ascii")
_POWERSHELL_TEMP_SCRIPT = "[Console]::Write([IO.Path]::GetTempPath())"


class WindowsInteropAudioSink:
    """Opt-in synchronous Windows Python/winsound playback, including from WSL.

    ``powershell`` or ``player`` may explicitly select a backend. The default
    prefers PowerShell SoundPlayer and falls back to Windows Python/winsound.
    Original rate/channels are preserved unless ``canonicalize=True``. Both
    modes prepend 150 ms of silence to the temporary playback copy only.
    """

    def __init__(self, *, player: str | None = None, powershell: str | None = None,
                 wslpath: str | None = None,
                 timeout_seconds: float = 60.0, canonicalize: bool = False) -> None:
        if (type(timeout_seconds) not in (int, float) or
                not math.isfinite(timeout_seconds) or timeout_seconds <= 0):
            raise ValueError("Windows interop playback timeout must be positive and finite.")
        if type(canonicalize) is not bool:
            raise ValueError("canonicalize must be a boolean.")
        self.player = player
        self.powershell = powershell
        self.wslpath = wslpath
        self.timeout_seconds = float(timeout_seconds)
        self.canonicalize = canonicalize
        self._process = None
        self._temporary_path: str | None = None
        self.last_wav_format: WavFormat | None = None
        self.last_wav_diagnostic: WavDiagnostic | None = None
        # Safe, bounded playback diagnostics for local troubleshooting.  These
        # deliberately contain no paths, stderr, audio bytes, or credentials.
        self.last_backend: str | None = None
        self.last_normalized_byte_length: int | None = None
        self.last_playback_exit_code: int | None = None
        self.last_playback_failure_category: PlaybackFailureCategory | None = None
        self.last_playback_marker: str | None = None
        self.last_pcm_diagnostics: PcmDiagnostics | None = None
        self.last_output_device_category: str | None = None
        self._last_audio_diagnostics: AudioPlaybackDiagnostics | None = None
        self.last_staged_audio_diagnostics: AudioPlaybackDiagnostics | None = None
        self.last_staged_file_accessible: bool | None = None
        self.last_staged_byte_length: int | None = None

    @property
    def last_audio_diagnostics(self) -> AudioPlaybackDiagnostics | None:
        """Return safe diagnostics from the most recent playback attempt."""
        return self._last_audio_diagnostics

    def play_ab(self, audio: bytes, *,
                before_play: Callable[[str], None] | None = None
                ) -> tuple[AudioPlaybackDiagnostics, AudioPlaybackDiagnostics]:
        """Play one PCM16 response as A (original) then B (mono 8 kHz).

        Original sample bytes/rate/channels are preserved in A, after the
        playback-only silence prefix. No request or retained audio.
        A successful process does not confirm audibility; the caller listens.
        """
        info, _ = _inspect_windows_wav(audio)
        if info.encoding_tag != 1 or info.bits_per_sample != 16:
            raise LocalPlaybackError(
                "A/B playback requires validated 16-bit PCM WAV audio.",
                category=PlaybackFailureCategory.UNSUPPORTED_WAV_ENCODING,
            )
        results = []
        for label, canonicalize in (("A_original", False), ("B_canonical_8khz", True)):
            if before_play is not None:
                before_play(label)
            self.play(audio, canonicalize=canonicalize)
            results.append(self.last_audio_diagnostics)
        return results[0], results[1]

    def play(self, audio: bytes, *, audio_format: str = "wav",
             canonicalize: bool | None = None) -> None:
        if canonicalize is None:
            canonicalize = self.canonicalize
        if type(canonicalize) is not bool:
            raise ValueError("canonicalize must be a boolean.")
        self.last_wav_format = None
        self.last_wav_diagnostic = _wav_diagnostic(audio)
        self.last_backend = None
        self.last_normalized_byte_length = None
        self.last_playback_exit_code = None
        self.last_playback_failure_category = None
        self.last_playback_marker = None
        self.last_pcm_diagnostics = None
        self.last_output_device_category = "default_output_device"
        self._last_audio_diagnostics = None
        self.last_staged_audio_diagnostics = None
        self.last_staged_file_accessible = None
        self.last_staged_byte_length = None
        if audio_format.lower() != "wav":
            raise LocalPlaybackError("Windows interop playback supports WAV audio only.")
        info, frames = _inspect_windows_wav(audio)
        self.last_wav_format = info
        audio = _normalize_windows_wav(info, frames)
        if canonicalize:
            audio = _canonicalize_pcm_wav(audio)
        audio = _with_playback_preroll(audio)
        self.last_normalized_byte_length = len(audio)
        self.last_pcm_diagnostics = _pcm_diagnostics(audio)
        backend = "python"
        executable = self.player
        if executable is None:
            executable = self.powershell or _find_windows_powershell()
            backend = "powershell" if executable is not None else "python"
            if executable is None:
                executable = _find_windows_player()
        if executable is None:
            raise LocalPlaybackError(
                "Windows Python is unavailable; install Windows Python and expose python.exe or py.exe, or set player explicitly.",
                category=PlaybackFailureCategory.MISSING_WINDOWS_PYTHON,
            )
        # Retain only allowlisted backend names, never arbitrary basenames.
        backend_name = ntpath.basename(executable).lower()
        self.last_backend = (backend_name if backend_name in
                             {"powershell.exe", "pwsh.exe", "python.exe", "py.exe"}
                             else backend)
        self._last_audio_diagnostics = AudioPlaybackDiagnostics(
            byte_length=len(audio),
            frame_count=self.last_pcm_diagnostics.frame_count,
            duration_seconds=self.last_pcm_diagnostics.duration_seconds,
            nonzero_sample_count=self.last_pcm_diagnostics.nonzero_sample_count,
            peak_abs_amplitude=self.last_pcm_diagnostics.peak_abs_amplitude,
            rms_level=self.last_pcm_diagnostics.rms_level,
            checksum=hashlib.sha256(audio).hexdigest()[:16],
            backend=self.last_backend,
            output_device_category=self.last_output_device_category,
        )
        temporary_path = None
        try:
            if backend == "powershell":
                # Reuse native Windows Python solely to discover a local temp
                # directory when available; PowerShell remains the playback
                # backend. This avoids staging into a WSL/UNC-backed path.
                temp_provider = _find_windows_player()
                if temp_provider is not None:
                    temporary_directory = _windows_local_temp_directory(
                        temp_provider, self.wslpath, self.timeout_seconds
                    )
                else:
                    temporary_directory = _windows_local_temp_directory_powershell(
                        executable, self.wslpath, self.timeout_seconds
                    )
            else:
                temporary_directory = _windows_local_temp_directory(
                    executable, self.wslpath, self.timeout_seconds
                )
            try:
                with tempfile.NamedTemporaryFile(
                    prefix="iris-fish-", suffix=".wav", dir=temporary_directory, delete=False
                ) as handle:
                    # Remember the file before writing so write/flush errors also clean up.
                    temporary_path = handle.name
                    self._temporary_path = temporary_path
                    handle.write(audio)
                    handle.flush()
                    self.last_staged_byte_length = os.fstat(handle.fileno()).st_size
                    self.last_staged_file_accessible = self.last_staged_byte_length == len(audio)
                    with open(temporary_path, "rb") as staged:
                        staged_audio = staged.read(MAX_AUDIO_BYTES + 1)
                    if self.last_staged_file_accessible and len(staged_audio) == len(audio):
                        self.last_staged_audio_diagnostics = _audio_playback_diagnostics(
                            staged_audio,
                            backend=self.last_backend,
                            output_device_category=self.last_output_device_category,
                        )
            except OSError:
                raise LocalPlaybackError(
                    "Windows interop playback could not access its temporary WAV file.",
                    category=PlaybackFailureCategory.WAV_FILE_INACCESSIBLE,
                ) from None
            windows_path = _convert_to_windows_path(temporary_path, self.wslpath, self.timeout_seconds)
            if backend == "powershell":
                command = [executable, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                           "-EncodedCommand", _encode_powershell_command(_POWERSHELL_AUDIO_SCRIPT)]
            else:
                command = [executable, "-I", "-c", _WINDOWS_AUDIO_SCRIPT, "play", windows_path]
            self._process = subprocess.Popen(
                command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                stdin=subprocess.PIPE if backend == "powershell" else subprocess.DEVNULL,
            )
            if backend == "powershell":
                communicated = self._process.communicate(input=windows_path + "\n", timeout=self.timeout_seconds)
            else:
                communicated = self._process.communicate(timeout=self.timeout_seconds)
            stdout = communicated[0] if isinstance(communicated, (tuple, list)) and communicated else ""
            markers = [line.strip() for line in stdout.splitlines()
                       if line.strip() in _POWERSHELL_MARKERS] if isinstance(stdout, str) else []
            marker = markers[-1] if backend == "powershell" and markers else None
            self.last_playback_marker = marker
            # Keep only the exit status and fixed markers, never child output.
            return_code = self._process.returncode
            if return_code is None:
                return_code = self._process.poll()
            self.last_playback_exit_code = return_code
            # communicate returns stdout/stderr, not the process exit status.
            if return_code != 0 or (backend == "powershell" and marker != "IRIS_PLAYSYNC_OK"):
                if backend == "powershell":
                    if return_code == 40:
                        category, message = _classify_powershell_process_failure(40)
                    elif marker == "IRIS_PLAYSYNC_EXCEPTION":
                        category, message = _classify_powershell_process_failure(43)
                    elif marker == "IRIS_SOUNDPLAYER_LOAD_EXCEPTION":
                        category, message = _classify_powershell_process_failure(42)
                    else:
                        category, message = (
                            PlaybackFailureCategory.CHILD_PROCESS_NONZERO_EXIT,
                            "Windows PowerShell playback process exited unsuccessfully.",
                        )
                else:
                    category, message = _classify_windows_process_failure(return_code)
                raise LocalPlaybackError(message, category=category)
        except LocalPlaybackError as exc:
            self.last_playback_failure_category = exc.category
            if exc.category == PlaybackFailureCategory.PLAYBACK_DEVICE:
                self.last_output_device_category = PlaybackFailureCategory.PLAYBACK_DEVICE.value
                if self._last_audio_diagnostics is not None:
                    self._last_audio_diagnostics = replace(
                        self._last_audio_diagnostics,
                        output_device_category=self.last_output_device_category,
                    )
            raise
        except FileNotFoundError:
            raise LocalPlaybackError(
                "Windows playback backend is unavailable; configure PowerShell or Windows Python.",
                category=(PlaybackFailureCategory.MISSING_POWERSHELL if backend == "powershell"
                           else PlaybackFailureCategory.MISSING_WINDOWS_PYTHON),
            ) from None
        except subprocess.TimeoutExpired:
            self.last_playback_failure_category = PlaybackFailureCategory.CHILD_PROCESS_TIMEOUT
            raise LocalPlaybackError(
                "Windows interop playback timed out.",
                category=PlaybackFailureCategory.CHILD_PROCESS_TIMEOUT,
            ) from None
        except (OSError, subprocess.SubprocessError):
            self.last_playback_failure_category = PlaybackFailureCategory.GENERAL
            raise LocalPlaybackError(
                "Windows interop playback process failed.",
                category=PlaybackFailureCategory.GENERAL,
            ) from None
        finally:
            process = self._process
            self._process = None
            try:
                if process is not None and process.poll() is None:
                    process.kill()
                    process.wait(timeout=5)
            except (OSError, subprocess.SubprocessError):
                raise LocalPlaybackError("Windows playback process could not be stopped.") from None
            finally:
                self._temporary_path = None
                if temporary_path is not None:
                    try:
                        os.unlink(temporary_path)
                    except FileNotFoundError:
                        pass
                    except OSError:
                        raise LocalPlaybackError(
                            "Temporary playback audio could not be cleaned up.",
                            category=PlaybackFailureCategory.WAV_FILE_INACCESSIBLE,
                        ) from None

    def stop(self) -> None:
        process = self._process
        if process is not None and process.poll() is None:
            try:
                process.terminate()
            except OSError:
                pass

    def close(self) -> None:
        self.stop()

    def __call__(self, audio: bytes) -> None:
        self.play(audio, audio_format="wav")


class FishAudioError(VoiceBackendError):
    """A sanitized Fish Audio request/provider failure."""

    def __init__(self, message: str, *, category: PlaybackFailureCategory | None = None):
        super().__init__(message)
        self.category = category


class FishAudioPlaybackError(VoiceBackendError):
    """A sanitized local audio validation, device, or sink failure."""

    def __init__(self, message: str, *, category: PlaybackFailureCategory = PlaybackFailureCategory.GENERAL,
                 diagnostic: WavDiagnostic | None = None):
        super().__init__(message)
        self.category = category
        self.diagnostic = diagnostic if category == PlaybackFailureCategory.MALFORMED_WAV else None


# Public descriptive alias for callers that use a provider-independent name.
LocalPlaybackError = FishAudioPlaybackError


class FishAudioSynthesizer(LocalSpeechSynthesizer):
    """Synthesize one text segment with Fish Audio and pass MP3 bytes to a sink."""

    def __init__(self, *, audio_sink: AudioSink | Callable[[bytes], None] | None = None,
                 voice_id: str = DEFAULT_FISH_VOICE_ID,
                 model: str | None = None, audio_format: str | None = None,
                 timeout_seconds: float = 30.0):
        if not isinstance(voice_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,128}", voice_id):
            raise ValueError("Fish Audio voice ID must be a bounded identifier.")
        if type(timeout_seconds) not in (int, float) or timeout_seconds <= 0:
            raise ValueError("Fish Audio timeout must be positive.")
        self.voice_id = voice_id
        self.model = model or os.environ.get("IRIS_FISH_MODEL", DEFAULT_FISH_MODEL)
        self.audio_format = (audio_format or os.environ.get("IRIS_FISH_FORMAT", "mp3")).lower()
        if self.audio_format not in {"mp3", "wav"}:
            raise ValueError("Fish Audio format must be mp3 or wav.")
        self.timeout_seconds = float(timeout_seconds)
        self.audio_sink = audio_sink
        self._stopped = False
        self.last_audio_metadata: AudioResponseMetadata | None = None

    def speak(self, text: str) -> None:
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Fish Audio requires non-empty text.")
        if len(text) > MAX_TTS_CHARACTERS:
            raise ValueError(f"Fish Audio text is limited to {MAX_TTS_CHARACTERS} characters.")
        api_key = os.environ.get("IRIS_FISH_API_KEY", "").strip()
        if not api_key:
            raise FishAudioError("IRIS_FISH_API_KEY is not configured.")
        if self.audio_sink is None:
            raise LocalPlaybackError("Fish Audio audio_sink is not configured; provide a local playback sink.")
        speech_text = normalize_tts_text(text)
        request = Request(
            FISH_AUDIO_TTS_URL,
            data=(f'{{"text":{_json_string(speech_text)},"reference_id":{_json_string(self.voice_id)},'
                   f'"format":{_json_string(self.audio_format)}}}').encode("utf-8"),
            # Keep the wire request aligned with Fish Audio's documented curl
            # shape. urllib supplies its own transport headers as needed.
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json",
                     "model": self.model},
            method="POST",
        )
        self._stopped = False
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                if not 200 <= response.status < 300:
                    raise FishAudioError(f"Fish Audio returned HTTP {response.status}.")
                content_type = _response_content_type(response)
                audio = response.read(MAX_AUDIO_BYTES + 1)
        except FishAudioError:
            raise
        except HTTPError as exc:
            status = exc.code
            try:
                exc.close()
            except Exception:
                pass
            if status in (401, 403):
                raise FishAudioError("Fish Audio authentication failed; check IRIS_FISH_API_KEY.") from exc
            if status == 429:
                raise FishAudioError("Fish Audio rate limit reached; retry later.") from exc
            raise FishAudioError(f"Fish Audio provider returned HTTP {status}.") from exc
        except (TimeoutError, URLError, OSError) as exc:
            raise FishAudioError("Fish Audio request failed or timed out.") from exc
        if self._stopped:
            return
        self.last_audio_metadata = _audio_response_metadata(content_type, audio)
        metadata = self.last_audio_metadata
        if metadata.magic == "JSON":
            raise FishAudioError(
                "Fish Audio returned a JSON error response instead of audio.",
                category=PlaybackFailureCategory.JSON_ERROR_RESPONSE,
            )
        if metadata.byte_length > MAX_AUDIO_BYTES:
            raise LocalPlaybackError(
                f"Fish Audio returned oversized {self.audio_format.upper()} audio.",
                category=PlaybackFailureCategory.OVERSIZED_AUDIO,
            )
        expected_magic = "RIFF" if self.audio_format == "wav" else metadata.magic
        valid_audio = metadata.magic == expected_magic if self.audio_format == "wav" else metadata.magic in {"ID3", "MPEG"}
        if not valid_audio:
            raise LocalPlaybackError(
                f"Fish Audio returned non-{self.audio_format.upper()} data ({metadata.magic}, {metadata.byte_length} bytes).",
                category=PlaybackFailureCategory.NON_AUDIO_RESPONSE,
            )
        try:
            sink = self.audio_sink
            play = getattr(sink, "play", None)
            if callable(play):
                play(audio, audio_format=self.audio_format)
            else:
                # Preserve the pre-existing callable sink API for integrations.
                sink(audio)  # type: ignore[misc]
        except Exception as exc:
            if isinstance(exc, LocalPlaybackError):
                raise
            raise LocalPlaybackError("Local Fish Audio playback failed.") from exc

    def stop(self) -> None:
        self._stopped = True
        sink = self.audio_sink
        stop = getattr(sink, "stop", None)
        if callable(stop):
            stop()

    def close(self) -> None:
        sink = self.audio_sink
        close = getattr(sink, "close", None)
        if callable(close):
            close()


def _json_string(value: str) -> str:
    import json
    return json.dumps(value, ensure_ascii=False)


def _classify_windows_process_failure(return_code: int) -> tuple[PlaybackFailureCategory, str]:
    """Only fixed native-child exit codes become public diagnostics; never stderr."""
    return {
        41: (PlaybackFailureCategory.MISSING_WINSOUND,
             "Windows Python winsound backend is unavailable; use a native Windows Python installation."),
        42: (PlaybackFailureCategory.WAV_ACCESS,
             "Windows Python could not access the WAV audio."),
        43: (PlaybackFailureCategory.PLAYBACK_DEVICE,
             "Windows audio playback failed; check the WAV format and output device."),
        44: (PlaybackFailureCategory.WINDOWS_TEMP_PATH_CONVERSION,
             "Windows Python could not locate its local temporary directory."),
    }.get(return_code, (
        PlaybackFailureCategory.CHILD_PROCESS_NONZERO_EXIT,
        "Windows interop playback process exited unsuccessfully.",
    ))


def _classify_powershell_process_failure(return_code: int) -> tuple[PlaybackFailureCategory, str]:
    return {
        40: (PlaybackFailureCategory.WAV_ACCESS,
             "Windows SoundPlayer could not access the staged WAV audio."),
        42: (PlaybackFailureCategory.SOUNDPLAYER_LOAD,
             "Windows SoundPlayer could not load the WAV audio."),
        43: (PlaybackFailureCategory.PLAYBACK_DEVICE,
             "Windows SoundPlayer playback failed; check the output device."),
    }.get(return_code, (
        PlaybackFailureCategory.POWERSHELL_SOUNDPLAYER,
        "Windows PowerShell audio playback failed.",
    ))


def _looks_like_audio(audio: bytes, audio_format: str) -> bool:
    if audio_format == "wav":
        return audio.startswith(b"RIFF") and audio[8:12] == b"WAVE"
    return audio.startswith(b"ID3") or (len(audio) >= 2 and audio[0] == 0xFF and audio[1] & 0xE0 == 0xE0)


def _running_under_wsl() -> bool:
    """Detect WSL without assuming PulseAudio, ALSA, or Windows tools exist."""
    return bool(os.environ.get("WSL_INTEROP") or os.environ.get("WSL_DISTRO_NAME"))


def _find_windows_player() -> str | None:
    for candidate in ("python.exe", "py.exe"):
        found = shutil.which(candidate)
        if found:
            return found
    return None


def _find_windows_powershell() -> str | None:
    for candidate in ("powershell.exe", "pwsh.exe"):
        found = shutil.which(candidate)
        if found:
            return found
    return None


def _convert_to_windows_path(path: str, converter: str | None = None, timeout: float = 60.0) -> str:
    if not _running_under_wsl():
        return path
    converter = converter or shutil.which("wslpath")
    if converter is None:
        raise LocalPlaybackError(
            "WSL playback is unavailable because wslpath was not found; configure a Windows audio sink.",
            category=PlaybackFailureCategory.MISSING_WSLPATH,
        )
    try:
        result = subprocess.run(
            [converter, "-w", path], check=True, capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise
    except (OSError, subprocess.SubprocessError):
        raise LocalPlaybackError(
            "WSL could not convert the temporary audio path for Windows playback.",
            category=PlaybackFailureCategory.WINDOWS_TEMP_PATH_CONVERSION,
        ) from None
    converted = result.stdout.strip()
    drive, tail = ntpath.splitdrive(converted)
    if (not re.fullmatch(r"[A-Za-z]:", drive) or not tail.startswith("\\") or
            any(c in converted for c in "\r\n\0")):
        raise LocalPlaybackError(
            "WSL returned no usable Windows audio path.",
            category=PlaybackFailureCategory.WINDOWS_TEMP_PATH_CONVERSION,
        )
    return converted


def _windows_local_temp_directory(player: str, converter: str | None = None,
                                  timeout: float = 60.0) -> str:
    """Ask native Python for its temp directory, then map the local drive into WSL."""
    if not _running_under_wsl():
        return tempfile.gettempdir()
    converter = converter or shutil.which("wslpath")
    if converter is None:
        raise LocalPlaybackError(
            "WSL playback requires wslpath; install the WSL path conversion tool.",
            category=PlaybackFailureCategory.MISSING_WSLPATH,
        )
    result = subprocess.run(
        [player, "-I", "-c", _WINDOWS_AUDIO_SCRIPT, "temp"],
        capture_output=True, text=True, timeout=timeout,
    )
    if result.returncode != 0:
        raise LocalPlaybackError(
            "Windows temporary directory discovery failed.",
            category=PlaybackFailureCategory.WINDOWS_TEMP_DISCOVERY,
        )
    windows_temp = result.stdout.strip()
    drive, tail = ntpath.splitdrive(windows_temp)
    if (not re.fullmatch(r"[A-Za-z]:", drive) or not tail.startswith("\\") or
            any(c in windows_temp for c in "\r\n\0")):
        raise LocalPlaybackError(
            "Windows returned no usable local temporary directory.",
            category=PlaybackFailureCategory.WINDOWS_TEMP_PATH_CONVERSION,
        )
    try:
        mapped = subprocess.run(
            [converter, "-u", windows_temp], check=True, capture_output=True, text=True,
            timeout=timeout,
        ).stdout.strip()
    except subprocess.TimeoutExpired:
        raise
    except (OSError, subprocess.SubprocessError):
        raise LocalPlaybackError(
            "Could not map the Windows local temporary directory for playback.",
            category=PlaybackFailureCategory.WINDOWS_TEMP_PATH_CONVERSION,
        ) from None
    if not mapped or not os.path.isdir(mapped):
        raise LocalPlaybackError(
            "The Windows temporary directory is not accessible from WSL.",
            category=PlaybackFailureCategory.WINDOWS_TEMP_PATH_CONVERSION,
        )
    return mapped


def _windows_local_temp_directory_powershell(powershell: str, converter: str | None = None,
                                             timeout: float = 60.0) -> str:
    """Discover a Windows temp directory, with cmd.exe fallback, then map it."""
    if not _running_under_wsl():
        return tempfile.gettempdir()
    converter = converter or shutil.which("wslpath")
    if converter is None:
        raise LocalPlaybackError(
            "WSL playback requires wslpath; install the WSL path conversion tool.",
            category=PlaybackFailureCategory.MISSING_WSLPATH,
        )
    windows_temp = ""
    try:
        result = subprocess.run(
            [powershell, "-NoProfile", "-NonInteractive", "-Command", _POWERSHELL_TEMP_SCRIPT],
            capture_output=True, text=True, timeout=timeout,
        )
        if result.returncode == 0:
            candidate = result.stdout.strip()
            drive, tail = ntpath.splitdrive(candidate)
            if re.fullmatch(r"[A-Za-z]:", drive) and tail.startswith("\\") and not any(
                    c in candidate for c in "\r\n\0"):
                windows_temp = candidate
    except subprocess.TimeoutExpired:
        pass
    except (OSError, subprocess.SubprocessError):
        pass
    if not windows_temp:
        try:
            result = subprocess.run(
                ["cmd.exe", "/c", "echo", "%TEMP%"],
                capture_output=True, text=True, timeout=timeout,
            )
            if result.returncode == 0:
                candidate = result.stdout.strip()
                drive, tail = ntpath.splitdrive(candidate)
                if re.fullmatch(r"[A-Za-z]:", drive) and tail.startswith("\\") and not any(
                        c in candidate for c in "\r\n\0"):
                    windows_temp = candidate
        except subprocess.TimeoutExpired:
            pass
        except (OSError, subprocess.SubprocessError):
            pass
    if not windows_temp:
        raise LocalPlaybackError(
            "Windows temporary directory discovery failed.",
            category=PlaybackFailureCategory.WINDOWS_TEMP_DISCOVERY,
        )
    try:
        mapped = subprocess.run(
            [converter, "-u", windows_temp], check=True, capture_output=True, text=True,
            timeout=timeout,
        ).stdout.strip()
    except subprocess.TimeoutExpired:
        raise
    except (OSError, subprocess.SubprocessError):
        raise LocalPlaybackError(
            "Could not map the Windows local temporary directory for playback.",
            category=PlaybackFailureCategory.WINDOWS_TEMP_PATH_CONVERSION,
        ) from None
    if not mapped or not os.path.isdir(mapped):
        raise LocalPlaybackError(
            "The Windows temporary directory is not accessible from WSL.",
            category=PlaybackFailureCategory.WINDOWS_TEMP_PATH_CONVERSION,
        )
    return mapped
