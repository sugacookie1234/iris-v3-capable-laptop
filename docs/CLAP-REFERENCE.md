# Tested clap reference and integration scope

The owner asked to use the double-clap code they had already tested. This document records the relevant behavior and separates that request from the broader examples in the attached guides. It does not reproduce the complete personal script or treat the PDFs as instructions to run.

## Supplied references

- **`Pasted text.txt`**: the owner's supplied Python desktop clap listener. Its header describes `clap_listen.py`; the accompanying guide calls its project entry point `jarvis.py`. The pasted file is the source of truth for detector behavior in this integration.
- **`jarvis-setup-guide.pdf`**: *Jarvis Setup Guide*, attributed in the document to Hector Garcia, `@hex.gar`, dated August 11, 2026. All nine pages were reviewed. It describes a one-time desk-startup sequence using a Python microphone listener, music, Chrome, an ElevenLabs greeting and Cursor. The supplied script's configured actions differ from the guide's examples.
- **`Build-Your-Own-Jarvis-GPT-6-Astra-Prompt-Pack.pdf`**: *Build Your Own Jarvis with GPT-6 Astra*, attributed in the document to Zubair Trabzada / AI Workshop, September 2026. All 22 pages, including all sixteen prompts, were reviewed. This is a feature reference, not a replacement specification for IRIS.

The PDFs' model names, release dates, price tables, performance anecdotes and model-access claims were not independently verified. They are not a basis for changing IRIS's configured provider or selecting a paid model. The source PDFs, extraction files, personal welcome text and complete pasted script are not committed to this repository.

## Detector behavior to preserve

| Setting | Supplied value and meaning |
| --- | --- |
| Audio input | `sounddevice.InputStream`, mono `float32`, 44,100 samples per second |
| Analysis block | 40 ms, exactly 1,764 samples; consecutive stream reads |
| Level | Root mean square, calculated using float64; multichannel input is averaged to mono first |
| Initial noise floor | `0.0001` |
| Noise adaptation | Only when RMS is below `floor * 2.2`; new floor is `0.992 * floor + 0.008 * RMS`, with minimum `0.0000001` |
| Hit threshold | The greater of `floor * 7.0` and absolute RMS `0.012` |
| Rearm | RMS must fall strictly below `threshold * 0.55` before another hit can count |
| Pair interval | Second hit must arrive 0.05–0.35 seconds after the first, inclusive |
| Pair cooldown | At least 0.45 seconds after the last accepted pair |
| Clock | `time.monotonic()` after each audio-block read |

A hit sooner than 0.05 seconds after the first is ignored **without moving the first-hit timestamp**. A hit after 0.35 seconds becomes the first hit of a new pair. An accepted pair clears the first hit and updates the cooldown timestamp. A continuous loud sound does not count as two claps unless its level first drops below the rearm threshold.

This is an RMS transient detector, not a trained clap classifier. Loud speech, knocks, playback or other sudden sounds can resemble claps. The gated noise-floor update is intentionally specific: it does not increase the baseline when all input remains above the quiet gate. Matching the tested implementation does not establish accuracy in a different room or on a different microphone.

### Microphone selection

The reference probes inputs using the same sample rate, channel count and block size as detection. Each probe lasts approximately 0.5 seconds and retains only its highest block RMS. A maximum RMS of at least `0.001` is considered active.

1. A nonempty `JARVIS_INPUT_DEVICE` selects an index, or the first input whose name contains the supplied text, ignoring case. The script probes the selection and warns if it is silent or unavailable, but retains that explicit choice.
2. Without an override, use the default input if its probe is active.
3. Otherwise probe the remaining inputs and select the openable input with the highest peak RMS, provided it clears the activity threshold.
4. If none clears it, fall back to the existing default, then the first input. No input devices is an error.

The highest probe level is a practical fallback, not proof that the chosen device is the intended physical microphone. The explicit override remains useful for virtual inputs and machines with multiple microphones. Detection and request recording must use the same chosen device; otherwise a clap could wake IRIS while speech is recorded from another, silent input.

The reference requests 44,100 Hz directly. It does not silently switch rates. The guide suggests 48,000 Hz as a manual troubleshooting change if the device cannot use the configured rate; that is distinct from the originally tested settings.

## Why changing the browser thresholds alone is insufficient

Before this integration, `web/clap.js` used the same spike ratio, absolute threshold, rearm ratio, quiet gate and pair interval, but a **1.2-second cooldown**, an initial floor of **0.001**, and a minimum floor of **0.0001**. It also replaced the first-hit timestamp when a second hit arrived too soon.

The previous `StandbyMonitor` sampled a browser analyser with a 1,024-sample window on a 16 ms timer. That window is about 23 ms at 44,100 Hz or 21 ms at 48,000 Hz; it can overlap between polls, and timer scheduling does not guarantee consecutive, complete audio blocks. Browser capture requested echo cancellation and could use a different device or sample rate.

The supplied native stream instead feeds consecutive 1,764-sample blocks into the detector. Preserving the block size, RMS computation, state transitions and native input selection is necessary to reproduce the tested behavior. Native capture also avoids depending on browser analyser polling for the clap signal. Windows microphone permissions, drivers, device disconnection and computer sleep still apply.

## Adapt the action, retain IRIS

The supplied script keeps a `welcome_sequence_done` flag. Although detection continues, only the first accepted pair launches its welcome sequence. The guide explicitly documents restarting the process to repeat it.

IRIS needs a different action lifecycle: **every eligible accepted pair wakes one request**, then returns to standby. Keep the 0.45-second detector cooldown; replace the one-time welcome action with IRIS's existing wake/capture flow. Suppress clap triggers during request capture, transcription, reply preparation and playback so the assistant does not wake itself. After an approval prompt finishes speaking, a clap can open the existing confirmation capture; the clap itself never approves an action.

Keep explicit microphone pause, cancellation, startup restoration and shutdown cleanup. A paused microphone must stay paused. Standby is local level analysis; speech is sent for transcription only after an intentional wake. Selected microphone details and transient samples do not need to become chat context.

The supplied music launch, website windows, Cursor controls, personal welcome phrase, ElevenLabs account and greeting cache are separate automation examples. They are not required for double-clap detection and are not part of this request. Preserve IRIS's own identity, Fish Audio output and Fish recognition with local faster-whisper fallback. Do not launch the pasted script as a second assistant alongside IRIS.

## Prompt-pack assessment against the existing IRIS app

This assessment describes the desktop build before the clap port, rather than claiming that every feature in the pack is implemented.

| Pack feature | Current IRIS coverage and remaining scope |
| --- | --- |
| 01: notes, conversation and a knowledge galaxy | Shared conversation runtime and optional read-only Obsidian/workspace tools exist. The 3D note graph, source-node camera movement and notes-only answer policy do not. Preserve the requested animated core and current HUD. |
| 02: speech in both directions | Fish Audio replies, Fish recognition with local Whisper fallback, status, cancellation and mute already exist. The pack's browser speech-recognition implementation and 900 ms phrase buffer are a different capture design, not a drop-in fix for native claps. |
| 03: visual proof of note sources | A future optional notes view. There is no source-linked galaxy animation in the current desktop app. |
| 04: character | IRIS has its own identity and behavior configuration. The pack's British-butler prompt and JARVIS greeting are optional examples, not instructions to replace it. |
| 05: memory that is immediately retrievable | Confirmed persistent memory and subsequent memory retrieval exist. This uses local SQLite, not automatically created Markdown captures or live graph nodes. Memory writes still need their existing approval. |
| 06: a fresh screen frame with each question | Not connected to the supported desktop conversation. A future explicit screen-sharing feature would need current-frame capture, visible sharing state, correct image media type and honest handling of ended shares. No screen sharing is enabled by this clap update. |
| 07: live preflight | Unit/integration tests, recorded provider smoke tests and the local `check-speech.bat` fixture check exist. Legacy `iris.preflight` is not the pack's complete live desktop-chain harness. Live-device validation remains separate from mocked test results. |
| 08: voice model switching | Setup supports configured model IDs and council seats; automatic FAST/DEEP/COUNCIL routing already exists. Runtime provider-model changes by voice are separate work. Exact model access would need verification; never silently substitute a nearby name or paid model. |
| 09–12: focus sessions, deferred targets, retargeting and named distractions | Not connected. These require new foreground-app/tab sensors, focus-session state, privacy controls and Windows-specific implementation. References to bundle IDs and browser scripting in the pack are not portable Windows implementation instructions. |
| 13: camera posture and one-frame questions | Not connected. Camera capture and any cloud image upload would be separate, visible, user-controlled features. |
| 14: screen stillness monitoring | Not connected. Continuous local screen comparison and occasional uploaded frames are distinct from clap standby. |
| 15: model-change introductions | Depends on the unimplemented runtime model-switching feature. It does not justify changing IRIS's personality or provider now. |
| 16: diagnostics and field checks | Useful engineering guidance: observe the actual running sensor, expose bounded status, and test the user's exact flow. No focus diagnostics or focus ledger exist because the focus feature is not installed. |

The later pages mention a paid community's phone line and automation registry, but do not supply their implementation. They do not add SMS or calling support to IRIS. Those remain separate integrations described in [HUD and standby](HUD-STANDBY.md).

## Acceptance checks for this port

Synthetic tests should establish parity with the supplied detector: exact interval boundaries, a too-early hit retaining the first timestamp, rearm after a sustained sound, cooldown, floor adaptation, repeated successful pairs and silent input. Device-selection tests should cover explicit choice, default preference, silent-default scanning and unavailable inputs without opening real devices.

Integration checks should prove that one native wake starts one recording on the selected input, playback cannot trigger a new request, explicit pause releases capture, and closing the app stops the listener. Real microphone acceptance still needs two claps followed by speech, repeated after a reply, on the actual laptop. A passing test suite cannot establish acoustic accuracy or OMEN hardware compatibility by itself.
