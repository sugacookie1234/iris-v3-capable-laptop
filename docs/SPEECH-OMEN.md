# Local speech recognition on the HP OMEN 16

IRIS tries **Fish Audio transcribe-1-pro first**, then **faster-whisper** locally if
the cloud service fails, times out, rejects the key or has no API credit. Set
recognition to **local** in `setup.bat` to skip Fish entirely. The target is Windows
on the HP OMEN 16 with an Intel Core 7 240H, 16 GB RAM, an RTX 5060 and a 1 TB SSD.
This is a suitable machine to try the GPU profile, but **the actual OMEN has not
been tested**. Its microphone quality, available GPU memory, driver and runtime
libraries still determine the result. No particular VRAM amount is assumed.

Local speech recognition does not need a Fish Audio subscription, API credit or a
transcription key. Model installation requires an internet connection; subsequent
local recognition runs on the computer. With the default Fish setting, microphone
recordings are sent to Fish Audio and billed against API credit. The reasoning provider and Fish Audio speaking
voice remain separate services and can still require network access and credit.

## Recommended profile

| Setting | OMEN default | Lighter alternative |
| --- | --- | --- |
| Recognition model | `large-v3-turbo` | `small.en` for English |
| Device | Automatic; try NVIDIA GPU, then CPU if necessary | CPU is supported |
| GPU precision | `float16` | `float16` |
| CPU precision | `int8` | `int8` |

The default model is a candidate for better recognition of natural speech than
the previous small Vosk model. Accuracy and response time must be measured with
your own voice; neither a package installation nor a single sample establishes
microphone quality. If CPU fallback makes the large model too slow, choose the
lighter English model explicitly rather than silently substituting it.

The `large-v3-turbo` files come from
[`dropbox-dash/faster-whisper-large-v3-turbo`](https://huggingface.co/dropbox-dash/faster-whisper-large-v3-turbo/tree/0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf),
revision `0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf`. The download is approximately
1.62 GB. The older `mobiuslabsgmbh` repository name in faster-whisper's model map
redirects to this repository. The optional English model is
[`Systran/faster-whisper-small.en`](https://huggingface.co/Systran/faster-whisper-small.en).
Keep several GB free for the environment, model and download cache.

## Windows GPU compatibility

The package versions selected for this build are
[`faster-whisper==1.2.1`](https://pypi.org/project/faster-whisper/1.2.1/) and
[`ctranslate2==4.8.3`](https://pypi.org/project/ctranslate2/4.8.3/).
CTranslate2 publishes native Windows x86-64 wheels for Python 3.11, 3.12 and 3.13.
Use a 64-bit Python installation.

NVIDIA lists the RTX 5060 as compute capability 12.0 (Blackwell).
The pinned CTranslate2 Windows build uses CUDA 12.8 and dynamic cuBLAS loading.
A current NVIDIA driver supporting the laptop GPU is required; a driver merely
appearing in Device Manager does not prove inference works.
See [NVIDIA's GPU table](https://developer.nvidia.com/cuda/gpus) and the
[CTranslate2 Windows build definition](https://github.com/OpenNMT/CTranslate2/blob/v4.8.3/python/tools/prepare_build_environment_windows.sh).

For the pinned Windows wheel, the optional NVIDIA runtime package is
[`nvidia-cublas-cu12==12.9.2.10`](https://pypi.org/project/nvidia-cublas-cu12/12.9.2.10/),
available from NVIDIA's PyPI account as a Windows wheel. It is a roughly 553 MB
download. Its DLL directory must be available to the running Python process.
There is no need to install the full CUDA development toolkit just to compile
this application: the published wheel is already compiled.

Older faster-whisper instructions require cuDNN 9. The pinned CTranslate2 build
uses its own CUDA convolution implementation with `WITH_CUDNN=OFF`; cuDNN is
optional for this build. Its build configuration also uses CMake's default
static CUDA runtime, so a separate `cudart` package is not expected. These are
conclusions from the pinned upstream build source, not a successful GPU test on
your OMEN. See the
[4.6.3 release notes](https://github.com/OpenNMT/CTranslate2/releases/tag/v4.6.3)
and [CMake CUDA runtime documentation](https://cmake.org/cmake/help/latest/module/FindCUDA.html).

Some old CTranslate2 releases had Blackwell INT8 failures. Upstream restored
INT8 with a padding fix in 4.7.0. This build starts with GPU `float16`; it does
not depend on that older problematic path. See
[upstream fix #1982](https://github.com/OpenNMT/CTranslate2/pull/1982).

## First test on the OMEN

1. Run `setup.bat` in the repository and let the speech model download finish.
2. Run `check-speech.bat`. This tests local Whisper on a public recording without
   contacting Fish, reports the actual device, and includes model loading in its timing.
   Then run `start-iris.bat`, open IRIS, and grant microphone permission.
3. Choose a quiet room and use the microphone close to your mouth. Hold Space
   outside the typing box, say a complete sentence, and release it.
4. Check the recognized text before approving any proposed task or memory change.
5. Try several different sentences, including names and numbers you often use.
   Then repeat one with the laptop's normal fan noise. This gives a more useful
   check than a single successful recording.

The first recognition can take longer while the model loads and CUDA prepares
its kernels. GPU detection is only a preliminary check: model loading and an
actual transcription must succeed before treating GPU recognition as working.
If the GPU cannot initialize, local CPU recognition should remain available and
the interface should report that fallback. It must not silently send audio to a
different cloud transcription provider. Fish is the configured primary; fallback stays local.

If recognition is slow, first check whether it is using CPU fallback. If words
are missing or incorrect, check the selected Windows microphone and input level,
then compare the same short sentence with a headset microphone. A more capable
model cannot reconstruct words that the microphone never captured clearly.

## Developer verification

Use `ctranslate2.get_cuda_device_count()` and
`ctranslate2.get_supported_compute_types("cuda", 0)` as preliminary checks.
Handle detection, model-load and inference errors separately. Faster-whisper
returns a generator, so successful `transcribe(...)` construction alone is not
an inference test: consume the segments before recording success.
See [compute-type discovery](https://opennmt.net/CTranslate2/python/ctranslate2.get_supported_compute_types.html)
and [faster-whisper usage](https://github.com/SYSTRAN/faster-whisper#usage).

Unit tests can verify selection, fallback and input validation on another
computer. They cannot establish RTX 5060 latency, thermal behavior, microphone
permissions or recognition accuracy on this laptop. Record those observations
after testing the OMEN itself.
