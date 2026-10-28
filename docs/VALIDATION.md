# Validation — October 27, 2026

## Automatic organization and reminders

The complete Windows suite passed: **741 tests, OK, 4 skipped**, in 125.76 seconds.
After the final local phrase and request-saving changes, all **66 affected
organizer/integration tests passed**, in 26.25 seconds.
All seven desktop JavaScript checks passed. Dependency consistency, JavaScript
syntax, whitespace checks and the configured-secret scan passed. No saved key,
token or PIN values appeared in publishable files.

The new checks cover background capture without delaying chat, grounded tasks and
goals, deadline clarification, duplicate suppression, revision-aware undo, and
Markdown note capture/edit/move with protected paths and preimages. Reminder checks
cover overdue catch-up, completion and rescheduling, durable delivery state,
notification limits, pause/shutdown, optional SMS activation, STOP, and uncertain
provider submissions. Desktop checks cover authenticated APIs, failed reminder
acknowledgement retries, resolved questions, unavailable vaults and visible errors.
Tests use temporary stores and fake notification/phone clients; they do not edit
the owner's vault or send SMS/calls. The Windows notification script also passed
PowerShell parsing; a visible system notification has not been verified.

Two separately approved live model checks sent only two synthetic statements about
an Orion prototype and learning French. The first returned no saved actions and
no error; its original plan was not retained. After a grounded-title fix, the
second proposed and saved one task, but omitted the note and misclassified the
long-term goal. This verifies the live provider/write path, not reliable semantic
coverage. Safe rejection diagnostics now distinguish empty plans from rejected
proposals. No SMS, calls or actual vault edits occurred in either test.

Firm sustained commitments and direct personal project facts now have local
parsing. An end-to-end check with network access disabled created the intended
Markdown note and goal, read them back from temporary storage, and undid both.
Simple questions, greetings and duplicate messages skip an extra organization
request. Mixed fact/question messages remain eligible for capture. General model
extraction can still miss or misclassify unusual wording; Activity reports actual
saved changes.

Automatic organization and desktop reminders are enabled in the development
account, with its existing `D:\I.R.I.S` Obsidian vault selected. Optional reminder
SMS is requested but inactive because Twilio is not configured. These encrypted
account settings are not committed and must be configured again on the OMEN.
The updated native desktop window launched and Windows reported it responding.
Authenticated loopback checks confirmed organization/reminders enabled, no
organization error, a working notes endpoint and SMS disabled. No live microphone
or acoustic double-clap acceptance check was performed during this update.

## Previous validation — October 26, 2026

## Optional SMS and phone bridge

The complete Windows suite passed: **629 tests, OK, 4 skipped**, in 125.28 seconds.
The new phone-specific suite has **101 passing tests**. All six desktop JavaScript
checks passed. Dependency consistency, whitespace checks and the configured-key,
token and PIN scan passed; no saved credential values appeared in publishable files.

Phone checks use fake model/transport clients and actual local HTTP requests signed
with the real Twilio SDK. They cover account/participant/signature validation, exact
public-origin signing despite spoofed proxy headers, malformed requests, separation
from desktop APIs, asynchronous SMS and voice flows, duplicate delivery, three PIN
attempts with retry-safe tokens, cross-call token isolation, call termination/expiry,
late answers, STOP/START and replay suppression, send uncertainty, recovery, bounded
queues and local retention. Setup and CLI tests verify local credential entry and
explicit outgoing-notification previews without external communication.

Twilio SDK **9.12.0** was installed into the existing virtual environment as an
optional dependency. The real local `iris.phone status` command confirmed the phone
service is disabled. No phone account, number or public tunnel was created, no real
SMS or call was sent, and no provider/carrier delivery has been verified. Activation
requires an eligible provider account/number, phone credentials and a public HTTPS
origin. Canadian onboarding considerations and the precise limitations are in
[PHONE.md](PHONE.md).

## Previous validation — October 25, 2026

## Public web research

After adding explicit web commands, the full Windows suite passed: **528 tests,
OK, 4 skipped**, in 56.54 seconds. Web tests cover opt-in plugin requests, endpoint
restrictions, source annotations, missing sources, safe source URLs, quota errors,
query-only context, conversation history, and isolation from local tools. The UI
test renders source titles as text and rejects unsupported link schemes. JavaScript
syntax and diff checks passed.

One live research request using the existing OpenRouter configuration successfully
returned the official sounddevice documentation with three source links in about
five seconds. This verified the configured web plugin and model together. No user
documents, saved memories, prior conversations or audio were included in the probe.
Search incurs OpenRouter charges; no Fish Audio request was made by this probe.

Web access currently requires an explicit search command. Ordinary conversation
and council responses are not silently web-grounded. See [WEB-RESEARCH.md](WEB-RESEARCH.md).

## Tested native clap port

The full Windows suite passed: **519 tests, OK, 4 skipped**, in 68.53 seconds.
All six desktop JavaScript checks passed, including native wake acknowledgement,
sequential ownership heartbeats, cancellation and matching the request microphone.
Additional UI checks confirm that late permission grants release their temporary
stream after pause or page exit. Dependency consistency and diff checks passed.

A bounded local hardware check opened **Microphone Array (Realtek Audio** at
44,100 Hz in 40 ms blocks, stayed healthy for three seconds after startup, and
stopped successfully. This check kept wake detection busy, wrote no audio, and
uploaded nothing. It confirms capture access, not acoustic double-clap accuracy.
Repeated clap-to-speech behavior and minimized operation still need a physical
trial, especially on the target OMEN.

The supplied Python source and both PDF guides were reviewed. Source tuning and
device probing were retained; callback delivery permits bounded cancellation.
The source's one-time app-launching welcome was replaced with repeated IRIS wakes.
The review and intentional differences are in [CLAP-REFERENCE.md](CLAP-REFERENCE.md).

## Standby and voice-command follow-up

The affected Windows desktop, recognition, transcription, routing and widget suite
passed: **80 tests, OK**, in 5.42 seconds. The initial restricted-account run could
not exercise Windows DPAPI; it passed when run under the normal signed-in account.
JavaScript checks cover permission-gated native standby restoration, remembering
an explicit mic pause, audio suspension indicators, pending-resume cancellation,
overlapping requests, and an old playback rejection arriving after a replacement.

The local command checks now include “What time is it?” and polite IRIS prefixes,
without routing ordinary local widget requests to the chat provider. Weather checks
cover concurrent location requests, permission denial, unavailable readings, and old
responses arriving after a newer location. Missing values remain unavailable; voice
responses distinguish permission failures from weather service failures.
All five JavaScript contract checks passed. Closing the interface invalidates a
pending location result before it can start a weather request, and suppresses late
weather updates. Syntax and diff checks passed; configured credentials were absent
from publishable files.

Native auto-restoration is covered by simulated permission/window tests. Real
microphone permissions, clap accuracy and audio behavior on the OMEN still need
hardware acceptance. The desktop app keeps the initial permission/start interaction;
only later launches with existing permission can restore standby automatically.

## Previous validation — October 24, 2026

## Standalone Windows launcher

Final Windows suite: **481 tests, OK, 4 skipped**, in 116.23 seconds. All five
JavaScript contract checks passed, along with syntax checks and `pip check`.
New launcher tests exercise real loopback server startup/shutdown with a simulated
renderer, renderer-failure cleanup, duplicate-instance prevention, the embedded
navigation boundary, and Chrome-only external link selection.

The actual pywebview 6.2.1 / WebView2 desktop window launched on the development
Windows host. Windows reported **I.R.I.S. — Personal Intelligence** responding,
and the app logged its document-loaded event on port 8766. Authenticated HTTP
checks confirmed the current interface, Fish recognition configuration and four
available market rows. No microphone recording or paid chat request was used for
these desktop-launch checks. No configured credentials matched publishable files.

This session's UI-control tools exposed neither Chrome nor native Windows windows,
so visual layout, location permission and actual microphone/clap behavior were not
verified through those tools. Minimized clap sampling has an app-local background
timer setting but still requires a microphone test. OMEN hardware acceptance remains
outstanding. [Desktop setup and limitations](DESKTOP-APP.md) describes the launch path.

## Minimal HUD, automatic routing and standby

Windows unit/integration suite: **476 tests, OK, 4 skipped**, in 77.43 seconds.
The four skips remain legacy POSIX modules. JavaScript checks cover automatic
routing requests, microphone permission races, stopping tracks, output mute versus
microphone pause, playback replacement, and rejecting voice approvals recorded
before an action appeared or for a replaced action. Synthetic clap tests are not
real-room microphone acceptance.

Weather tests cover coordinate validation/rounding, bounded fixed upstream requests,
cache expiration and unavailable data. Market tests reject intraday bars and expose
dated daily closes and partial failures. Live read-only checks returned Open-Meteo
weather for an explicit test coordinate (not the user's location) and daily closes
for SPY, QQQ, DIA and IWM from Yahoo Finance. Browser location permission and actual
microphone/clap accuracy still require checks on the user's hardware.

## Previous validation — October 23, 2026

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

## Voice turns and tray update — 2026-10-28

- Focused voice, app and standby JavaScript checks pass: silence discard,
  pause-to-send, a bounded recording limit, follow-up cancellation, stale recorder
  callbacks, typed-chat draft preservation, and explicit approval wake behavior.
- A real Chrome audio pipeline using an internally generated tone followed by
  silence produced one WAV transcription request to a fake local handler. A silent
  stream produced zero requests. No physical microphone or provider was used.
- Ten focused Python desktop/tray tests pass. An isolated Windows WebView2/WinForms
  check confirmed close-to-tray, continuing timers while hidden, reopening and Quit.
- These checks do not establish real-room speech/noise discrimination, audible
  playback or OMEN performance. Voice interruption currently uses the core or Space;
  speaking over playback does not automatically interrupt it. Model output still
  completes before speech is requested; this update reduces input waiting time.
- Start with Windows is an optional tray setting; no login registration was enabled
  by these tests.

## Remaining manual acceptance

### Design adoption and governed desktop slice — 2026-10-28

Code revision: [`b63853c640b64f7adcebf10573e7cdb006b46bff`](https://github.com/sugacookie1234/iris-v3-capable-laptop/commit/b63853c640b64f7adcebf10573e7cdb006b46bff).
Scope: CAP-21 fixed Windows actions, a CAP-15 explicit workspace precursor, and M0 design adoption.

- `python -m unittest tests.test_desktop_commands tests.test_desktop_action_tools tests.test_windows_controls tests.test_desktop tests.test_tools -q`: **53 passed** under the normal Windows account. Native path tests require that account rather than the restricted sandbox token.
- `node tests/desktop_app_check.cjs`: passed, including shorter spoken summaries with complete visual results and the existing Send/voice/approval regressions.
- Tests use fake applications and temporary records. Real ToolExecutor workers exercise permission rejection, invalid targets, exact approval snapshots, replay rejection, configured-folder binding and partial workspace results. Local command tests confirm zero model calls and no automatic-organizer side effects.
- Native CoreAudio volume **read** succeeded on the development computer. No live volume changes, app-launch routine, new provider calls or phone actions were performed during these tests. Actual OMEN action acceptance remains outstanding.
- The supplied design package and addendum were imported as architecture documents, with preserved original vault snapshots. Seven new vault notes were written and their contents verified; the personal profile is outside the repository and was not added to the confirmed-memory store or sent to a provider.
- The design docs and new adapter/dispatcher sources were checked against configured secret values: zero matches. This check does not substitute for the separate decision to exclude all personal profile data from Git.
- Rollback: the preceding source baseline is `9db02a7`. The action slice introduces no database migration or new dependency. Vault imports are separate Markdown notes and can be removed independently; existing notes were not overwritten.

### Earlier hardware and integration acceptance still outstanding

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
