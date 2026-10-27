# I.R.I.S. v3 — Capable Laptop

IRIS's identity, reasoning council, persistent memory and local tools, connected to
the animated voice interface and streaming Fish Audio playback from the JARVIS prototype.
It opens as its own **Windows desktop app**, with optional Google Chrome browser mode.

Target laptop: **HP OMEN 16 · Intel Core 7 240H · 16 GB RAM · NVIDIA RTX 5060 · 1 TB SSD**.
The default uses cloud reasoning and Fish Audio voice recognition, with local faster-whisper as a fallback.
Setup downloads the local speech model and installs the NVIDIA runtime when a compatible GPU is detected.
It can also run on less powerful Windows computers. It has not yet been tested on the OMEN itself.

## Install on the OMEN

1. Install **64-bit Python 3.13** from [python.org](https://www.python.org/downloads/windows/) (3.11–3.13 supported).
   Enable the Python launcher/PATH option. The desktop window uses Microsoft's WebView2 Runtime,
   normally included with Windows 11. See [desktop setup](docs/DESKTOP-APP.md) if it is missing.
2. Clone this private repository with your GitHub account, or use **Code → Download ZIP**
   and extract it to a normal local folder, such as `C:\Users\you\Projects\iris-v3-capable-laptop`.
3. Double-click **`setup.bat`**. It creates an isolated environment, configures recognition, and downloads a pinned Whisper model (about 1.6 GB for the OMEN default).
4. Enter your provider key and Fish Audio key at the hidden prompts. Choose the model and voice.
5. Double-click **`start-iris.bat`**. IRIS opens in its own window with no browser tab or address bar.
   Keep the app running; closing its window stops IRIS. To use Chrome instead, run **`start-iris-browser.bat`**.
6. Click **Start standby** and allow microphone access. Double clap to speak, or hold **Space**.
   Click **Use my location** to enable local weather. Typing also works.
   Later desktop launches restore standby if permission is still granted; **Pause mic** stays paused.

Keys are deliberately **not included in the repository**. Enter them again on the OMEN;
the current computer's encrypted configuration cannot be decrypted by another Windows account.
Run `setup.bat` again to change model IDs, voice, recognition provider, timezone or Obsidian path.
Run **`check-speech.bat`** to test the local fallback on a public recording and see the actual GPU/CPU device.

## What works through the unified interface

- IRIS's own personality and behavior modes; no JARVIS roleplay prompt.
- Text and speech use the same conversation history, memory context and tool boundary.
- **Internet research:** say “Search the web for…” or type `/search your question`.
  Uses the configured OpenRouter account and returns clickable source links. Search has a
  separate OpenRouter charge; Fish Audio credit does not pay for it. Ordinary chat does not
  browse automatically. See [web research](docs/WEB-RESEARCH.md).
- **Optional SMS and calls:** a separate phone connection supports incoming text conversations,
  PIN-protected incoming calls, and manually confirmed outgoing notifications to your own number.
  It requires a suitable Twilio number/account and a public HTTPS tunnel; it is disabled until
  configured. Run `setup-phone.bat`, then `start-phone.bat`. See [phone setup](docs/PHONE.md)
  for Canadian number requirements. Phone conversations currently have no access to desktop tools or memories.
- Fish Audio streams to the app without waiting for the complete audio file.
- **Automatic reasoning:** routine requests use FAST; analysis uses DEEP; complex decisions may use
  COUNCIL for independent answers, anonymous reviews and synthesis. You can explicitly ask for the council.
  Say “show council review” to inspect the results. Council makes five provider requests.
  The initial seats may use the same model with distinct roles; setup supports different model IDs.
- **Memories:** propose a fact, confirm it, retrieve it in later conversations, or forget it.
  `/remember ...` and `/memories` work from the chat as well.
- **Automatic organization:** when enabled in setup, ordinary conversation can create and update
  tasks, goals and useful notes without a separate command or repeated approval. Deadlines generate
  desktop reminders, with optional owner-only SMS after Twilio setup. Activity shows changes and Undo.
  The organizer runs in the background; unclear deadlines need clarification. See [automatic organization](docs/AUTOMATIC-ORGANIZATION.md).
- **Tasks/goals:** list, create, complete or remove local tasks and manage goals through chat.
  They persist locally. Writes ask for approval when automatic organization is disabled.
- **Optional Obsidian:** read/search a configured vault. Automatic notes are organized under `IRIS/`;
  exact-path edits preserve human text and have backups/undo. Without a vault, IRIS uses a local notebook.
- **Double-clap standby:** enabled after the initial microphone permission/Start standby click.
  Uses the supplied tested Python listener: 44.1 kHz input and consecutive 40 ms blocks.
  Input probing and request recording share the selected microphone. Run `setup.bat` after updating.
  Two claps activate an eight-second recognition window. Idle monitoring measures levels locally;
  speech playback and request capture suspend clap detection. “Mute” silences replies; **Pause mic**
  stops listening. Detection needs testing with your microphone.
- Minimal HUD with a larger local clock, location-based weather and SPY/QQQ/DIA/IWM daily closes.
  Market prices are dated, in USD and **not live quotes**. See [HUD and standby](docs/HUD-STANDBY.md)
  for voice commands, sources, location handling and future SMS/call integration.
- **New chat** clears session history, not saved memories or tasks.

Try: “What is your name?”, “Add a task to test IRIS on my OMEN”, or
“Ask the council to compare a cloud-first and local-first assistant for my laptop.”

Microphone audio is recorded by the interface and converted to WAV. By default it goes to Fish Audio's
`transcribe-1-pro` API. Missing credit, rejected keys, rate limits, network failures and invalid responses
automatically fall back to local faster-whisper. Each new recording tries Fish again, so adding credit
restores cloud recognition without changing settings. The UI reports which engine handled the last recording.
Choose **local** recognition in setup to keep audio on the computer. IRIS does not save recordings;
Fish's own data handling applies to cloud requests. Your chat provider receives the transcript and relevant
memory/context. Fish Audio receives reply text for spoken output. Clap level detection stays on the computer.

## Models and hardware

The initial model ID is the free OpenRouter model tested during development,
`nvidia/nemotron-3.5-lightning:free`. Availability and rate limits can change.
An unavailable or rate-limited model produces an error; IRIS does not silently choose a paid model.
Use `setup.bat` to select any available model on your chosen OpenAI-compatible endpoint.

The Fish default is `s2.1-pro-free`; its documented free period ends November 30, 2026.
If it stops working, select a supported model and check your Fish account pricing/quota.
No credit purchase or automatic top-up is configured by this project.

Voice IDs: `41f0953d7a6b4c078445c7e65d620eeb` is the voice from the working JARVIS prototype;
`88b183bfbdda44a09ad4474712b967f4` was used in the earlier IRIS configuration. Choose either in setup.
Changing voice does not change IRIS's identity.

Local speech defaults to **large-v3-turbo**, with NVIDIA float16 acceleration and CPU int8 fallback.
The smaller **small.en** model is available in setup for lighter English recognition. GPU memory and drivers
still matter; no VRAM amount or OMEN performance is assumed. See [OMEN speech setup](docs/SPEECH-OMEN.md).

## Local data and boundaries

The server binds only to `127.0.0.1`, normally port **8766** (next available port if busy).
It checks Host, browser origin and a session cookie; API writes also require a same-origin custom header.
Voice URLs contain short-lived one-use tickets, not response text or API keys.

On Windows, `.local/config.dpapi` uses Windows DPAPI encryption for the current account.
`.local/` also contains SQLite memories, tasks and goals and is ignored by Git.
Those SQLite records are local plaintext; DPAPI protects configuration, not all personal records.
Do not publish `.local/`, API keys, or personal vault contents.

Desktop entry points use native Windows file handles for bounded workspace/vault/calendar reads
and notebook writes, rejecting symbolic links, junctions and unsafe relative paths. Enabled automatic
organization has standing permission for its bounded, reversible local actions. Other governed actions
retain their approval checks. A council answer does not itself authorize a tool action.

## Scope

This build merges the two working foundations. It does **not** install the separate Google Workspace,
Windows computer-control, or other MCP repositories from the earlier research list. External accounts,
general desktop automation and unrestricted shell execution are not connected. IRIS reports this honestly.

The retained v2 code includes experimental WSL one-shot voice, standalone HUD, readiness and reminder
entry points. They are not the supported Windows launch path; use `start-iris.bat` for the merged app.
Standby and reminders work while the interface is running and the computer is awake. Windows startup,
a system background service, voice wake words and autonomous desktop missions are not connected.
The optional SMS/call bridge needs its own provider setup.

## Development and validation

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -q
node tests/desktop_clap_check.cjs
node tests/desktop_voice_check.cjs
node tests/desktop_standby_check.cjs
node tests/desktop_app_check.cjs
node tests/desktop_dashboard_check.cjs
node tests/desktop_organizer_check.cjs
.venv\Scripts\python.exe -m iris.desktop.server --no-browser
```

Windows-specific encryption tests must run under a normal signed-in Windows account.
POSIX permission/PTY/alarm tests are explicitly skipped on Windows and retained for the legacy paths.
Most provider tests use fakes. Real-provider smoke results and remaining manual checks are recorded
in `docs/VALIDATION.md`; a passing unit suite is not microphone or OMEN hardware acceptance.

## Source attribution

IRIS core and identity were supplied by the repository owner in `IRIS-v2.zip`.
The HUD design originated in [AKCodez/make-your-own-jarvis](https://github.com/AKCodez/make-your-own-jarvis);
its MIT license is preserved in `docs/JARVIS-LICENSE.txt`.
The council has an existing custom IRIS implementation; see `docs/council-reference.md` for the
comparison with Karpathy's project. No third-party assistant stack was wholesale imported.

## Voice input troubleshooting

Restart the app after updating (or refresh Chrome in browser mode). Click the core, allow microphone access, speak, then click it again
to submit; the timed window also stops after eight seconds. Hold Space away from the text box for
push-to-talk (up to 30 seconds). Escape or Pause mic discards the recording.
If the model is missing, run `setup.bat` again. Speech input uses the default Windows microphone.
Fish recognition requires API credit, separate from its website subscription. Local Whisper needs no
transcription key or credits. The first local request loads the model and can be slower; CPU fallback
with the large model can be slow on older computers. The footer shows Fish, NVIDIA GPU or CPU and
reports fallback reasons. Run `check-speech.bat` after setup on the OMEN; microphone accuracy still
needs checking with your voice. Models are downloaded into ignored local storage, not committed.
