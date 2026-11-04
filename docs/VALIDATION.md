# Validation

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

## 2026-10-28 — Action receipts, capability inventory and fresh software baseline

Scope: CAP-30/31 initial desktop slices and M0 offline baseline. Code revision:
[`fd040ee`](https://github.com/sugacookie1234/iris-v3-capable-laptop/commit/fd040ee621bf4b60962145afd4534869120e9930).
Hardware/provider acceptance is separate.

- `.venv/Scripts/python.exe -m unittest discover -s tests -q`: **796 run, 792 passed,
  four skipped**, 71.754 seconds. Ran with normal Windows account access so DPAPI
  and the existing Windows safe-path fixtures could work. No paid provider test.
- After adding inventory HTTP authentication and actual host-workflow coverage:
  `python -m unittest tests.test_action_history tests.test_desktop_capabilities -q`:
  **17 passed**, including retention, deletion, interrupted receipts, unknown timeout
  effects, partial results, secret/content omission, authority preservation, no
  model/organizer call, and exclusion of receipts from future model context.
- Seven JavaScript checks passed: `desktop_clap_check.cjs`, `desktop_voice_check.cjs`,
  `desktop_standby_check.cjs`, `desktop_app_check.cjs`, `desktop_dashboard_check.cjs`,
  `desktop_organizer_check.cjs`, `desktop_native_standby_check.cjs`. Re-ran the app
  check after the help-text update; passed.
- Earlier focused Python run: **57 passed** across the two new modules plus desktop
  commands, action tools, server/runtime and executor authority tests.
- Restarted the actual native desktop app on the development host. Authenticated
  local HTTP checks passed for the capability endpoint, “What can you do?”, read-only
  system-volume inspection and “What have you done today?”. The volume readback
  appeared as a verified receipt. These checks made zero model/provider calls and
  changed no system volume or external account state.
- Development-host OMEN acceptance is not inferred. No real app launches, volume
  changes, SMS, calls, provider-credit checks or microphone uploads were test actions.

See [coverage and privacy details](ACTION-HISTORY.md). Generic success is not
verification; the existing authority layer remains unchanged. Receipt coverage
starts at installation and excludes the separately tracked automatic organizer.

## 2026-10-28 — Reject noise and unexpected-language voice transcripts

Code: [`8930ca0`](https://github.com/sugacookie1234/iris-v3-capable-laptop/commit/8930ca026b2bf1431cfcdd03808c86225c9df32a).

Scope: CAP-07/08. The installed language setting was already `en`; Fish ASR treats
that as a hint and the old adapter accepted its text without checking language.
See [Fish's language contract](https://docs.fish.audio/features/speech-to-text#language).

- Added bundled CPU Silero VAD before Fish upload and local decoding. Quiet,
  non-speech and sub-160 ms recordings are discarded; a failed detector does not
  silently allow cloud upload. No extra dependency, download or provider call.
- English mode validates Fish's reported language and script; automatic language
  remains multilingual. Whisper rejects uncertain/repetitive segments as a whole
  turn to avoid turning a partial negation into a command. Rejected Fish output
  does not trigger a fallback decode.
- Automatic capture returns quietly to standby on an empty/rejected transcript;
  manual capture retains no-speech feedback. Timer gaps cannot count as observed
  speech duration. Existing 160 ms endpoint sensitivity is preserved.
- `python -m unittest tests.test_speech_guard tests.test_desktop_recognition tests.test_desktop_transcription -q`:
  **40 passed**, including real bundled VAD checks against silence, hum, tone,
  synthetic claps and random noise, plus public speech at normal and 10% amplitude.
- Full offline suite: **809 run, 805 passed, four skipped**, 72.492 seconds under
  the normal Windows account. No paid ASR or LLM requests and no private audio.
- `desktop_voice_check.cjs`, `desktop_app_check.cjs`, `desktop_standby_check.cjs`,
  and `desktop_native_standby_check.cjs`: passed.
- Actual installed `small.en` CPU Whisper decoded the six-second public Harvard
  fixture with the new confidence checks in 9.93 seconds including cold model load.
  This confirms fallback inference, not real-time speed or OMEN microphone accuracy.
- Independent code review found no blockers. Real-room false-positive/miss rates,
  background TV speech and very short/soft utterances still require microphone trials.
- Restarted the native app and posted a generated one-second silent WAV to its
  authenticated transcription endpoint: empty text, `speech-guard` CPU decision,
  no provider request. The changed-file configured-secret scan found zero matches.

## 2026-10-29 — Vault retrieval, paged reading and CAP-32 foundation

- Rechecked the supplied zip's four design documents, the architecture addendum,
  and the personal profile against the configured vault. All design bytes match;
  the profile body matches after its preserved provenance header and newline
  normalization. The profile stayed outside Git and no test uploaded it to a model.
- Confirmed the cause of missing context: encoded spaces were not decoded and
  notes above 16 KiB were skipped. The repaired adapter retrieves the profile and
  prioritizes the master design/addendum with bounded labelled excerpts.
- Focused vault/desktop tests: **43 passed**, 13.916 seconds. Added coverage for
  encoded paths, traversal, large-note excerpts, whole-file credential screening,
  title ranking, bounded failed reads, paged revision checks, ambiguity and local
  replies bypassing provider history and automatic organization.
- Full offline suite after preview integration: **827 run, 823 passed, four skipped**,
  211.329 seconds with normal Windows permissions. Synthetic notes/fake providers;
  no paid ASR or LLM request. The native Windows path tests require normal account access.
- `node tests/desktop_app_check.cjs`: passed, covering the existing send, audio,
  approval, standby and UI command regressions after the help update.
- Independent review found an unbounded failed-candidate read regression; fixed
  with attempted-path deduplication and a bounded attempt count, then tested.
- Restarted the real native app. Authenticated local HTTP checks passed for
  `Check Obsidian`, profile search/title resolution, and all **five profile pages**,
  compared against the actual local file without printing its contents. Every
  response used the LOCAL route. The briefing preview returned executed=false
  and executable=false, with zero model calls.
- CAP-32 validator tests cover immutable snapshots, typed arguments, missing
  permissions, unknown tools, external/writing tools, dependency cycles and budget
  limits. This is a proposal/preview foundation, **not** a verified three-step run.
- Changed files contained zero matches against configured secret values. No new
  dependency, database migration or modification of original imported notes.
- Rollback source baseline: `ba74329`. Hardware microphone/OMEN acceptance and
  full task execution remain outstanding; see [vault usage](OBSIDIAN-READING.md).

## 2026-10-29 — Restrained voice and executed source briefings

- Speech-only cleanup removes recognized sigh/laugh/breath/performance cues and
  neutralizes free-form square-bracket instructions while preserving ordinary
  parentheticals, link labels and literal technical content. Chat text is unchanged.
  Fish requests use documented temperature 0.3/top-p 0.7 with the existing voice
  and model. The identity prompt also calls for restrained plain speech.
- Device fallback receives the same cleaned text; cue-only output skips synthesis.
  A missing cleaned ticket does not resurrect raw cues. Expanded literal bracket
  speech remains subject to the CLI request-size limit.
- Initial combined voice, identity, briefing and runtime checks: **100 passed**.
  Full offline suite: **846 run, 842 passed, four skipped**, 82.609 seconds with
  normal Windows permissions. After the final rendered-size guard, **60 focused
  speech tests passed**. No paid model/speech requests or private audio.
- `node tests/desktop_app_check.cjs`: passed, including new clean-device-fallback,
  cue-only silence and failed-ticket regressions plus prior chat/standby checks.
- New briefing tests cover real temporary-vault search/read/draft execution,
  metadata-only receipts, instruction-like source text, bounded coverage, no matches,
  source changes, failed dependencies, malformed outputs, exact excerpt spans,
  cancellation callback and deadline expiry. Runtime tests confirm no provider
  or organizer call and no source content in later model history.
- Independent review found no blockers in the notes recipe or authority/privacy
  integration. This is a fixed foreground recipe, not a durable general agent.
- IRIS was closed, so the updated native app was launched. Authenticated loopback
  checks confirmed cleaned voice text and skipped cue-only audio without fetching
  audio. A real design-note briefing completed search → three reads → draft with
  source revision/excerpt verification. It correctly reported **partial coverage**
  because selection is bounded to three notes. All validation requests were local.
- No synthesis/listening trial was performed; removal of spontaneous sounds baked
  into the voice model is not claimed. See [delivery limits](VOICE-DELIVERY.md).
- Zero configured-secret matches in changed files. No new dependencies, vault
  changes or database migration. Rollback baseline: `f96db0d`.

## 2026-10-30 — Durable background notes jobs

- Final complete suite: **897 run, 893 passed, four skipped**, 139.303 seconds
  with normal Windows permissions and the native app closed during the run.
  Command: `.venv\Scripts\python.exe -m unittest discover -s tests -q`.
- Added the fixed notes recipe's encrypted local job store and single bounded
  worker, with metadata progress, cancellation, explicit retry/restart recovery,
  retention/deletion and request deduplication. Chat releases its turn immediately.
  Private result contents are opened explicitly and stay outside model history.
- Focused supervisor suite: **26 passed**, including real Windows DPAPI and its
  SQLite rollback journal, no automatic replay, current-source resume, cancellation
  races, stale callbacks, queue limits, retention, failed writes/encryption and
  unreadable-topic isolation. Synthetic fixtures only.
- Runtime/authentication/launcher/receipt/cancellation checks: **50 passed** after
  final integration. Shared desktop/browser ownership is acquired before storage
  recovery; failed port binding no longer closes the runtime used by the next port.
- All **eight desktop JavaScript checks passed**, covering single-inflight polling,
  stale-response guards, quiet deduplicated notices, reload/unload, approval priority,
  Cancel/Resume/Delete, and explicit text-only result rendering. Existing voice,
  microphone, dashboard, organization and standby checks remained passing.
- Two full-suite attempts exposed older timing-sensitive fixtures: a two-second
  worker-start allowance in a receipt privacy test, and a two-second local HTTP
  snapshot allowance in a HUD privacy/state test. Their budgets are now ten seconds;
  actual timeout/cancellation tests are unchanged. The receipt test also explicitly
  checks successful execution before assessing verification metadata.
- The HUD failure exposed cleanup being skipped if its final prompt raises.
  Cleanup now runs in `finally`; a new synthetic regression verifies that session,
  sink, owned memory store and HUD all close. **26 focused receipt/HUD/cleanup
  checks passed** after these corrections.
- Local native-host acceptance completed a real architecture briefing: search,
  three reads and source-checked draft; **partial** coverage, three sources and
  **zero model calls**. Listing omitted result bodies; explicit detail retrieval
  confirmed revision/excerpt checks. An initial five-second polling request timed
  out during the concurrent full suite; subsequent list/detail checks passed.
- After the final suite, a fresh native-host check queued its reply in **0.055
  seconds**, observed the running state, confirmed chat availability, and completed
  all five stages with three sources and zero model calls. The earlier completed
  result survived reopening with one attempt; it was then deleted as test cleanup.
  The fresh architecture briefing remains available in Jobs. IRIS was left running.
- Native visual inspection was unavailable: the computer-use JavaScript helper
  could not initialize its assets, including after reset. The interface evidence
  above is automated DOM testing and authenticated HTTP, not a screenshot review.
- No paid model/speech/phone requests were used for validation. A separate ignored
  `.local/jobs.sqlite3` was added; existing databases and source notes are unchanged.
  Configured-secret scan found zero matches in publishable changes. Source rollback
  baseline: `fd9acb1`; see [job storage and rollback](BACKGROUND-JOBS.md).

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
- Obsidian imports and local reads are verified on the current development host;
  the OMEN installation still needs its own correct vault path and index.
- Google Workspace and general Windows computer-control MCP connections remain
  unimplemented. See [integration screening](INTEGRATIONS.md). No external
  account actions, arbitrary commands, or autonomous background work are claimed.

The cloud-default build needs no local GPU model. The RTX 5060 can be considered
for an optional local endpoint later, after checking its actual available VRAM.
# 2026-11-03: reviewed task memory (CAP-33 first slice)

Visual foundation checkpoint: `python -m unittest tests.test_visuals
tests.test_desktop_capabilities` passed 12 tests; `node
tests/desktop_app_check.cjs` passed. Added arithmetic tests cover monthly/end-month
contributions, zero rate, invalid numbers and malformed specifications. Added to
CAP-34 corpus, but the expanded evaluation and full suite have not yet been rerun.
No actual display/microphone or new renderer DOM acceptance is claimed.

- Full local regression: **921 tests run, 917 passed, four skipped**, 236.755 seconds.
- Final focused task-memory/API and capability checks: **13 passed**, including
  missing-source-verification rejection added after the full run began.
- All **nine** desktop JavaScript checks passed, including task-memory rendering,
  stale panel responses, duplicate clicks, approval priority and text-only output.
- Store checks cover metadata validation, restart deduplication, current-revision
  reviews, dispute revocation, same-vault reuse, retention, deletion markers and
  overflow, concurrent reviews, and unchanged personal-memory exports.
- Integration checks cover authenticated/origin-checked controls, capture failure
  recovery without losing completed results, local planning and exclusion from
  model history. No paid provider, voice, SMS or call request was made.
- Configured-secret scan: zero matches in changed source, tests and docs.
- Native app acceptance: current task-memory asset served; one retained briefing
  reconciled into a pending review item. No owner review decision was changed.
- This validates fixed notes-recipe metadata and preview reuse, not general
  learning quality, independent fact checking, microphone quality or OMEN hardware.

## 2026-11-03: evaluation and business feasibility sprint

Branch: `sprint/evaluation-business-os`, based on `b4e5c96`. Main is not merged.
Evaluation foundation commit: `8fc9499`. CAP-34 and CAP-28 remain IN-PROGRESS.

Commands and outcomes:

```powershell
.venv\Scripts\python.exe -m unittest tests.test_evaluation
# 2 passed (gate failures, duplicates, missing cases and summary behavior)
.venv\Scripts\python.exe -m unittest tests.test_business tests.test_desktop_business tests.test_evaluation tests.test_desktop_capabilities
# 24 passed
.venv\Scripts\python.exe -m unittest discover -s tests
# 935 run: 931 passed, 4 skipped; 108.385 seconds
Get-ChildItem tests/desktop_*_check.cjs | ForEach-Object { node $_.FullName; if ($LASTEXITCODE) { exit $LASTEXITCODE } }
# All 10 checks passed
node tests/desktop_app_check.cjs
# Passed again after adding Business panel routing/stale-response/approval checks
.venv\Scripts\python.exe -m iris.generalist.evaluation --output .local/evaluation-business-a
.venv\Scripts\python.exe -m iris.generalist.evaluation --output .local/evaluation-business-b
# Both PASS: 70/70 baseline, 70/70 candidate, zero regressions
# SHA-256 comparison: results.json files byte-identical
```

The financial scenario suite independently checks exact decimal results, zero
margin, conservative cash needs, sensitivity, missing costs, contradictory and
injected evidence. Workspace/API checks cover persistence, backup/restore,
idempotency, stale edits, malformed inputs, origin/session rejection and receipt
privacy. No test assertion was weakened to make a failure pass; an initially
unclosed SQLite backup fixture was corrected to close both connections.

Native app was started on this development branch. Read-only loopback smoke check
confirmed native host, current Business asset, zero saved business projects and
the existing single Task memory item still pending. No real project was seeded,
no owner review decision altered, and no commercial or paid provider call made.
This is HTTP host acceptance plus automated DOM tests, not human visual or OMEN
hardware acceptance. All broader microphone, provider and connector limits remain.

Evaluation finding: reviewed memory adds coverage guidance but produces the same
executable plan. No correctness gain or generalized learning improvement is proven.
Gate metrics are asserted contract outcomes, not market validation or LLM quality.
No promotion, source modification or permission expansion follows an evaluation.
Configured-secret scan found zero matches in changed source/tests/docs.

See [business limits](BUSINESS-WORKSPACE.md), [evaluation scope](OFFLINE-EVALUATION.md)
and [next sprint backlog](SPRINT-BACKLOG.md). Business data is plaintext, local,
bounded and indefinite; export/delete UI and live evidence verification remain open.


## Security hardening checkpoint
Baseline 593cddf. Added raw loopback security tests for framing, duplicate headers/JSON, non-finite numbers, rejected bodies, public binding and worker capacity. Nine focused security/business tests pass after the Windows rejected-body drain correction. All ten desktop checks pass. Full suite run: 945 tests, 941 passed, four skipped (126.346 seconds). Final wall-clock drain refinement was subsequently covered by the nine focused tests; see .local/security-final-tests.log for the additional full run. No paid calls, external penetration testing, data migration or native hardware acceptance. Changed-file configured-secret scan: zero matches. Comprehensive dependency/phone audit and protected-storage migration remain open; SECURITY.md is the operator guide and evidence-based risk register.

Personality update 6c36f54: 13 identity/personality tests and desktop application DOM check passed. No live model-quality evaluation or voice-model change. Subsequent bootstrap continuation: 28 bootstrap, desktop, native startup and security tests passed (10.250s), including real synthetic cookie exchange in the fake native renderer. Full suite and physical native/browser microphone acceptance remain pending.

## Conversation sprint checkpoint
Full Python suite: 959 run, 955 passed, four skipped (101.842 seconds). All ten desktop JavaScript checks passed. Offline evaluation expanded with conversation and speech fixtures: 82/82 in each arm, zero regressions. Final punctuation/repeated-greeting refinement: 11 focused tests passed; the full suite had already loaded the prior greeting implementation. Combined speech/organizer repair suite: 71 passed. Initial full run exposed inline-code cue loss; fixed without weakening its assertion. No paid APIs, native-window/microphone acceptance or owner data changes. See CONVERSATION-SPRINT.md for exact scope and unfinished phases. Changed-file configured-secret scan found zero matches.

## Natural clock and admission limits (2026-11-03)
32 focused clock, desktop, bootstrap, HTTP-security and usage-limit tests passed. Initial restricted run had one Windows DPAPI environment error; rerun with Windows account protection available passed. No provider calls or hardware acceptance. Structured clock speech is tested through the actual TTS request payload; arbitrary prose date/currency conversion remains conservative.

Visual-security continuation: all eleven desktop JavaScript checks passed, including exact-field rejection and hostile text/numeric fixtures in the new simulated DOM test. Full Python suite: 969 run, 965 passed, four skipped (112.820s). No hardware or live-provider tests.

Durable provider slice: 19 provider-ledger/Council tests passed, including cross-instance concurrency, restart counts, failed calls, cancellation, unavailable storage, abandoned-reservation recovery and fan-out bounds. Full regression rerun in progress; no paid calls.

Provider regression: 975 run, 971 passed, four skipped (104.582s), before the final owner-recovery test and backup addition. Subsequent focused provider/Council run: 19 passed. Encrypted backup: five tests passed using temporary stores and synthetic DPAPI payloads. No real owner backup/restoration performed.

## Security continuation final regression
Full suite: 982 run, 978 passed, four skipped (99.923s), covering encrypted backups,
provider admission, Council bounds and phone framing. The subsequent phone-launcher
policy injection and test split passed 23 focused tests. All eleven desktop JS checks
passed; pip check reports no broken requirements. Configured-secret diff scan: zero
matches (not a Git-history audit). No hardware, carrier or billable provider tests.
Expanded evaluation initially failed 2/93 cases per arm because its blanket generate
mock intercepted adapter tests. Kept the guard intact and moved those unchanged
adapter assertions to test_provider_adapter.py, retained in full unittest discovery.
The offline corpus covers ledger contracts and clock payloads; it does not exercise
actual provider generation. Final rerun results are in SECURITY-CONTINUATION.md.

Final expanded CAP-34 gate: PASS, 92/92 per arm, zero regressions. Detailed exact checkpoint and residual risks: SECURITY-CONTINUATION.md.


## Orchestration closeout validation
Baseline 875bbed: 983 run, 979 passed, four skipped (101.987s). Provider closure
focus: 103 passed; combined provider/skill/privacy focus: 112 passed. Existing
ToolExecutor + cancellation + new authority/skill tests: 24 passed. Final skill
and authority suite: eight passed, including independent Decimal arithmetic.
All eleven desktop JS checks pass. Expanded CAP-34: 100/100 each arm, zero regressions.
First full integrated run: 993 run, two errors, four skipped. One legacy test required
private local command output in model history; revised it to require verified local
response evidence and empty cloud history. The other exposed Windows TCP reset on
rejected phone framing; fixed with a bounded 50ms wall-clock drain, preserving rejection.
After fixes, 33 focused tests pass. Final full rerun is recorded below when complete.
No real owner-data operations, external providers or hardware acceptance performed.

Final corrected regression: 994 run, 990 passed, four skipped (101.607s), .local/orchestration-verified.log. All eleven desktop checks passed. CAP-34: 100/100 per arm, zero regressions. Seventeen phone-server tests include bounded rejected-body timing. Sprint-range configured-secret scan: zero matches. No hardware acceptance, real provider calls or owner-data migration.

## Native Visual Workspace initial checks
Focused initial orchestration/bootstrap/native-app/visual checks: 21 passed. Integrated workspace/bootstrap/orchestration: 19 passed after public-context synchronization. Six workspace tests cover replay, invalid/stale/expired updates, concurrent edits, closed-form contributions and native lifecycle mocks. Actual local WebView2 synthetic smoke rendered SVG, updated one child, submitted UI principal changes, closed/reopened while retaining main, with zero provider calls. Initial smoke exit failed only on delayed WebView2 cache cleanup; the verified synthetic folder was later removed. No microphone/audio/OMEN/multi-monitor acceptance claimed. Final full regression and evaluation results follow.

Native workspace first full run: 1002 run, 998 passed, four skipped (180.014s).
All twelve desktop JS checks passed. CAP-34: 106/106 per arm, zero regressions.
Follow-up focus and lease-renewal changes: 22 focused native/state/bootstrap tests
passed. Second real WebView2 smoke passed SVG, keyboard-activation flag, same-window
update, UI principal submission, main continuity and reopen, with zero provider calls;
only synthetic profile cleanup was deferred by WebView2. Physical keyboard, audio and
multi-monitor acceptance remain outstanding. Final post-refinement regression follows.
