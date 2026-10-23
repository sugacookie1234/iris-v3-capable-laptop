# Validation — October 23, 2026

## Fish recognition with local Whisper fallback

The supported Windows interface now records mono 16 kHz WAV and tries Fish Audio
`transcribe-1-pro` first. It disables speaker labels, emotion tags and timestamps
for short assistant requests. API credit, authentication, rate-limit, network and
response-format failures fall back to local faster-whisper. A local-only setting
skips the cloud request. Each new recording retries Fish.

A real six-second public recording succeeded against the saved Fish key after
credit was added: 0.85 seconds for the API request in one observed run. It returned
“The stale smell of old beer lingers. It takes heat to bring out the...”
This establishes that ASR credit was usable at test time, not an account-balance
estimate or a promise about future latency. See the
[Fish ASR contract](https://docs.fish.audio/api-reference/endpoint/openapi-v1/speech-to-text).

Local `large-v3-turbo` also recognized the same sample using CPU int8, taking
100.0 seconds including model load on the development Dell. The current Dell is
configured with `small.en`; the repository's OMEN default remains `large-v3-turbo`
with automatic NVIDIA float16 selection and CPU int8 recovery. Model download and
successful CPU inference do not establish RTX 5060 compatibility in practice;
run `check-speech.bat` on the actual OMEN.

The running authenticated `/api/transcribe` endpoint also used real Fish ASR
successfully in 0.82 seconds. A simulated Fish credit failure then exercised the
actual local `small.en` model (no simulated transcript): the sample was recognized
in 18.44 seconds including model load on this Dell, and status identified CPU
fallback. These are individual measurements, not latency guarantees.

Final Windows suite: **451 tests, OK, 4 skipped**, in 156.26 seconds. The first
full run hit an automation worker timeout and a Windows connection reset; both
passed individually and the complete rerun passed. Browser voice/clap checks,
JavaScript syntax and dependency consistency checks passed. No configured API
keys were found in publishable files. The four skipped modules are legacy
POSIX-only tests. No real OMEN GPU or microphone acceptance is claimed.

The initial live check exposed PyAV 19 removing an argument used by faster-whisper
1.2.1. The environment and requirements now pin the compatible PyAV 16.1.0.
Whisper runtime tests cover CPU/GPU selection, missing GPU libraries, failures
while loading and while consuming the inference generator, bounded fallback,
model caching, language selection, malformed audio and concurrent requests.
Fish routing tests cover successful cloud requests, silence, local-only mode,
missing keys, 401/402/403/429/5xx responses, timeout recovery, malformed responses,
redirect rejection, and a missing local model. Browser tests retain fetch-receiver
and microphone cancellation checks and verify recognition-status callbacks.

The running interface displayed “Fish recognition · local Whisper fallback”.
Microphone accuracy with the user's own voice and actual OMEN GPU operation remain
manual acceptance checks. Fish receives microphone recordings in the default
mode; IRIS does not save them locally. Local-only mode does not upload audio.
The reasoning provider still receives the recognized transcript and context.

## Previous validation — October 22, 2026

The following records describe the earlier Vosk build and the existing reasoning,
voice-output and local-tool integration. The recognition path above supersedes Vosk.

## Voice-input repair

Browser speech recognition returned a network error. Fish transcription was
also tested with a public fixture but required account credit. Neither is used
for the repaired voice-input path: MediaRecorder captures microphone audio,
the browser converts it to mono 16 kHz WAV, and the loopback server transcribes
it locally with Vosk small English 0.15. Raw audio is not saved or sent to a cloud
service. The resulting chat transcript still goes to the configured chat provider.

The official model archive is downloaded during setup and checked against a pinned
SHA-256 digest. A six-second public speech fixture was correctly transcribed
both directly and through the running authenticated `/api/transcribe` endpoint.
JavaScript tests cover capture, WAV encoding, denied permissions, early key
release, cancellation during conversion, and suppressing cancelled requests.
Actual microphone quality remains a user/device acceptance check.

Target: HP OMEN 16, Intel Core 7 240H, 16 GB RAM, RTX 5060, 1 TB SSD.
Development checks ran on the available Windows Dell Latitude, using Python 3.13.1.
The OMEN itself has not been available for hardware acceptance.

## Automated checks

- Windows unit/integration suite: **425 tests run, OK, 4 skipped**, in 71.93 s.
  GitHub Actions repeats the suite for future commits. Four legacy
  POSIX-only modules are skipped (private POSIX file permissions, PTY setup,
  signal-alarm readiness, and pipe-select reminder runner). The supported Windows
  desktop path has separate tests, including DPAPI encryption.
- Browser clap detector: timing, rearm, cooldown and invalid sample tests pass.
- JavaScript syntax checks pass.
- Desktop contracts cover shared conversation history, council routing, memory
  approval/retrieval, replay rejection, unsuccessful actions, origin/session
  checks, one-use speech tickets, and delivery of the first speech bytes while
  the upstream response is still generating.
- The candidate source files were checked against the actual locally configured
  provider keys: no matches. `.local/`, credentials, databases and environments
  are excluded from Git.

## Live checks

- OpenRouter default model returned a complete two-sentence response in 0.91 s
  in one observed run. This is a sample, not a latency guarantee.
- The default model's hidden reasoning is disabled to preserve the small voice
  reply budget. Other models keep their provider defaults. Responses stopped
  by a token limit are reported explicitly instead of presented as complete.
  [OpenRouter reasoning reference](https://openrouter.ai/docs/guides/best-practices/reasoning-tokens).
- Live council completed in 12.07 s with two candidate answers, one accepted
  peer ranking, and chairman synthesis. One peer review was not usable; the
  council tolerates this and exposes partial failures in its review panel.
  Default seats share a model; configure different models in setup if desired.
- Fish Audio returned MP3 audio with first bytes in 1.69 s in one observed run,
  using the supplied JARVIS voice. This is measured from requesting speech,
  after the text reply; it does not include model generation or playback buffering.
- A real task request in a disposable database requested approval while there
  were zero saved tasks, then saved exactly one task after approval and confirmed it.
- Browser text chat displayed IRIS's identity response; the memory dialog loaded.
  A compact-window layout overlap was found and fixed.

## Remaining manual acceptance

- Run setup and launch on the actual OMEN. Keys must be entered on that machine;
  Windows account encryption is not portable with a repository download.
- Native Edge automation could not be initialized on the development host.
  UI checks used the Codex in-app browser. Its original speech service reported a
  network error and has now been replaced with local recognition. Actual microphone
  capture still needs a user/device check.
- Check audible playback, interruptions, microphone permission, push-to-talk,
  and double-clap thresholds in Edge with the OMEN microphone. Synthetic clap
  tests do not establish real-room detection accuracy.
- Obsidian requires a real vault path and suitable index; tests use fixtures.
- Google Workspace and general Windows computer-control MCP connections remain
  unimplemented. See [integration screening](INTEGRATIONS.md). No external
  account actions, arbitrary commands, or autonomous background work are claimed.

The cloud-default build needs no local GPU model. The RTX 5060 can be considered
for an optional local endpoint later, after checking its actual available VRAM.
