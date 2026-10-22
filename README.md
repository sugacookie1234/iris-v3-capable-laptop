# I.R.I.S. v3 — Capable Laptop

IRIS's identity, reasoning council, persistent memory and local tools, connected to
the Edge voice interface and streaming Fish Audio playback from the JARVIS prototype.

Target laptop: **HP OMEN 16 · Intel Core 7 240H · 16 GB RAM · NVIDIA RTX 5060 · 1 TB SSD**.
The default runs cloud models and does not need CUDA, Ollama, WSL or a GPU model download. Voice input uses a small local Vosk model.
It can also run on less powerful Windows computers. It has not yet been tested on the OMEN itself.

## Install on the OMEN

1. Install **Python 3.11 or newer** from [python.org](https://www.python.org/downloads/windows/).
   Enable the Python launcher/PATH option. Edge is the recommended browser.
2. Clone this private repository with your GitHub account, or use **Code → Download ZIP**
   and extract it to a normal local folder, such as `C:\Users\you\Projects\iris-v3-capable-laptop`.
3. Double-click **`setup.bat`**. It creates an isolated environment, installs dependencies, and downloads a verified 40 MB English speech model.
4. Enter your provider key and Fish Audio key at the hidden prompts. Choose the model and voice.
5. Double-click **`start-iris.bat`**. Keep its launcher running. Edge opens IRIS automatically.
6. Click **Wake IRIS**, allow microphone access, and hold **Space** to speak. Typing also works.

Keys are deliberately **not included in the repository**. Enter them again on the OMEN;
the current computer's encrypted configuration cannot be decrypted by another Windows account.
Run `setup.bat` again to change model IDs, voice, timezone or Obsidian path.

## What works through the unified interface

- IRIS's own personality and behavior modes; no JARVIS roleplay prompt.
- Text and browser speech use the same conversation history, memory context and tool boundary.
- Fish Audio streams to the browser without waiting for the complete audio file.
- **Auto** uses normal routing; **Council** forces independent answers, anonymous reviews and synthesis.
  The review button shows candidate answers and evaluations. Council makes five provider requests.
  The initial seats may use the same model with distinct roles; setup supports different model IDs.
- **Memories:** propose a fact, confirm it, retrieve it in later conversations, or forget it.
  `/remember ...` and `/memories` work from the chat as well.
- **Tasks/goals:** ask to list, create, complete or remove local tasks, and manage goals through chat.
  Mutations require a browser approval tied to the actual action. Tasks and goals persist locally.
- **Optional Obsidian:** read/search a configured vault. Knowledge retrieval starts from `vault index.md`.
  No Obsidian app/plugin is necessary for these existing read-only tools.
- **Optional double clap:** enable it explicitly in the interface. Two claps activate an eight-second
  recognition window. It monitors levels only while the tab is visible and IRIS is idle.
  **Mute** stops clap monitoring, speech input and playback. Detection needs testing with your microphone.
- **New chat** clears session history, not saved memories or tasks.

Try: “What is your name?”, “Add a task to test IRIS on my OMEN”, or select Council and
ask “Compare a cloud-first and local-first assistant for my laptop.”

Microphone audio is recorded in the browser, converted to WAV and transcribed locally with Vosk.
Recordings are kept in memory only; no cloud transcription account is needed. Fish Audio receives spoken response text; your configured reasoning provider receives the request
and relevant memory/context. Clap level detection itself stays in the browser.

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

The RTX 5060 is not required for this version. A local model endpoint can be configured later;
model sizing must be based on actual GPU VRAM and available system memory. No VRAM amount is assumed.

## Local data and boundaries

The server binds only to `127.0.0.1`, normally port **8766** (next available port if busy).
It checks Host, browser origin and a session cookie; API writes also require a same-origin custom header.
Voice URLs contain short-lived one-use tickets, not response text or API keys.

On Windows, `.local/config.dpapi` uses Windows DPAPI encryption for the current account.
`.local/` also contains SQLite memories, tasks and goals and is ignored by Git.
Those SQLite records are local plaintext; DPAPI protects configuration, not all personal records.
Do not publish `.local/`, API keys, or personal vault contents.

New desktop entry points use native Windows file handles for bounded workspace/vault/calendar reads,
rejecting symbolic links, junctions and unsafe relative paths. Model-proposed writes use immutable,
single-use browser approval. A council answer does not itself authorize a tool action.

## Scope

This build merges the two working foundations. It does **not** install the separate Google Workspace,
Windows computer-control, or other MCP repositories from the earlier research list. External accounts,
general desktop automation and unrestricted shell execution are not connected. IRIS reports this honestly.

The retained v2 code includes experimental WSL one-shot voice, standalone HUD, readiness and reminder
entry points. They are not the supported Windows launch path; use `start-iris.bat` for the merged app.
No automatic startup, always-on background listening or autonomous desktop missions are enabled.

## Development and validation

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -q
node tests/desktop_clap_check.cjs
node tests/desktop_voice_check.cjs
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

Refresh the page after updating. Click the core, allow microphone access, speak, then click it again
to submit; the timed window also stops after eight seconds. Hold Space away from the text box for
push-to-talk (up to 30 seconds). Escape or Mute discards the recording.
If the model is missing, run `setup.bat` again. Speech input uses the default Windows microphone.
Local English recognition needs no Fish credit, but accents/noise can affect accuracy.
The speech model is [Vosk small English 0.15](https://alphacephei.com/vosk/models), licensed Apache 2.0,
downloaded into ignored local storage; it is not bundled into the repository.
