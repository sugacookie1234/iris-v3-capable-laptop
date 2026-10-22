# Validation — October 22, 2026

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
