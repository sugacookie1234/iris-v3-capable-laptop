# IRIS desktop HUD and standby

The desktop keeps the animated core and gives the surrounding screen a quieter layout: a large clock, local weather, a broad U.S. market watchlist, and the conversation. Reasoning selection is automatic. Most controls are available as spoken or typed commands; microphone and location permissions still need an initial click.

## Start standby

1. Run `start-iris.bat` to open the standalone Windows app. Optional Chrome mode uses `start-iris-browser.bat`.
2. On first use, click **Start Standby** and allow microphone access. The desktop app
   restores standby on later launches when permission is still granted; an explicit
   microphone pause stays paused. Chrome mode starts with a click each time.
3. Double clap, wait for **Listening**, then speak. Local sound-level detection sends your request after about 1.1 seconds of silence following speech, with a thirty-second recording limit. Clicking the core starts the same automatic recording; clicking again sends it immediately. Holding Space records until release, with a thirty-second limit, when the cursor is outside a text field or dialog.

After a spoken reply finishes, IRIS leaves a short echo gap and shows **Anything else?** for five seconds. Start your follow-up during that window; it uses the same pause-to-send detection. If you stay quiet, the recording is discarded locally without a transcription or model request. A wake with no speech expires after six seconds. “That’s all” ends follow-up listening while keeping double-clap standby enabled. Typed replies, reminders and action confirmations do not automatically open a follow-up window. New action confirmations cancel any automatic recording and require a deliberate wake.

Click the core or hold Space to interrupt playback. Automatic interruption by speaking over IRIS is not implemented. Escape, Pause mic and typed requests cancel pending follow-up listening. Sound-level detection is a lightweight heuristic, not a speech-recognition model: noise and nearby voices can trigger it, and long pauses can end a sentence early. Hold Space for manual control when needed.

Double-clap detection stays enabled after activation. Standby checks sound levels locally and discards the samples; it does not continuously upload room audio. A wake starts a separate request recording, which normally goes to Fish Audio. If Fish recognition fails, IRIS tries the installed local faster-whisper model. The first local fallback can take longer while the model loads. The displayed speech status identifies the backend used. See [OMEN speech setup](SPEECH-OMEN.md) for local model and GPU setup.

Clap detection pauses while IRIS records, transcribes, processes a normal request, prepares a reply, or speaks. It resumes when IRIS is ready again. A pending approval is an exception: after IRIS finishes reading the action, double clap can wake it to receive the approval or cancellation.

The Python listener uses the supplied tested detector: mono 44,100 Hz, consecutive 40 ms blocks, a 50–350 ms double-clap gap and a 450 ms cooldown. It probes the default input, then scans other inputs if the default is silent. Speech recording matches that selected microphone; an ambiguous match gives an error instead of recording from an unrelated input. Set the process environment variable `IRIS_INPUT_DEVICE` to an input name or index to override selection; the source's `JARVIS_INPUT_DEVICE` is also accepted. Run `setup.bat` after pulling this update to install sounddevice and NumPy. See [source comparison and guide review](CLAP-REFERENCE.md).

Keep IRIS running and the laptop awake. Closing the desktop window hides it in the Windows tray; **Quit IRIS** in the tray menu stops its server and microphone. The tray also offers optional **Start with Windows**. Native capture runs outside the window's audio analyser; a short heartbeat lease releases capture if the interface disconnects. A second window cannot take over a running listener. Microphone disconnection, device sleep and OS permissions can still interrupt standby; tap the core after fixing the interruption. This is not a Windows background service, cannot wake a sleeping laptop, and saying “IRIS” alone is not a wake word. See [desktop app](DESKTOP-APP.md).

**Mute** silences spoken replies while retaining double-clap standby. **Pause mic** stops monitoring and cancels recording; use the core or **Resume mic** to restore it. A paused microphone cannot hear “unmute.” Escape stops the current recording or speech without permanently pausing standby.

Playback audio suspension does not stop the native clap detector. Tap the core to
resume playback audio when needed. Canceling or pausing while audio or microphone
permission is pending prevents that unfinished startup from re-enabling capture.

## Commands

Wake IRIS first, then use any of these. The same commands work in the text box.
Commands also accept a polite prefix such as “Iris, please…” and a trailing “please.”

| Command | Result |
| --- | --- |
| “Start a new chat” | Clears the current conversation; saved memories and tasks remain. |
| “Show my memories” | Opens saved memories. |
| “Show my tasks” | Opens the task list. |
| “Show my goals” / “Show my notes” | Opens saved goals or the notebook. |
| “Show activity” | Shows automatic changes and Undo. |
| “Undo the last change” | Reverses the latest eligible automatic change. |
| “Pause automatic organization” / “Resume automatic organization” | Pauses/resumes automatic capture and reminder delivery. |
| “What time is it?” | Reads the current device time. |
| “Search the web for…” | Researches a public question through OpenRouter and shows source links. |
| “Weather update” or “Use my location” | Requests location and refreshes local weather. The browser may require an Allow click. |
| “Market update” | Reads the latest available completed daily closes. |
| “Mute” / “Unmute” | Turns voice replies off or on; standby remains enabled. |
| “That’s all” / “Go to standby” | Ends automatic follow-up listening; double clap can wake IRIS again. |
| “Pause microphone” or “Stop listening” | Stops microphone monitoring until resumed by clicking. |
| “Show council review” | Opens the most recent council results, if available. |
| “Voice commands” or “Help” | Opens the command guide. |
| “Close the panel” | Closes the information panel. |
| “Approve” / “Cancel” | Answers a currently pending action confirmation. Without one, no action is approved. |

## Automatic reasoning

Automatic organization is a separate optional feature. It picks up commitments,
goals and notes from conversation and schedules deadline reminders. Its background
work does not delay voice playback. See [automatic organization](AUTOMATIC-ORGANIZATION.md).

IRIS uses a conservative local routing heuristic; choosing a route does not add a separate model request. Ordinary conversation, simple actions, and urgent requests use **FAST**. Affirmative analysis, troubleshooting, planning, and detailed explanations use **DEEP**. A decision with alternatives and several distinct constraints can select **COUNCIL** automatically. Explicit requests such as “Ask the council…” also work.

Automatic Council selection requires a sufficiently detailed choice with at least three different constraint categories, such as cost, privacy, and performance. Routine mentions of “council” or “architecture,” quoted examples, and negated reasoning requests do not by themselves escalate. “Do not use the council” keeps a complex choice on the single-model path. Automatic selection keeps tool requests out of Council because Council currently provides advice rather than executing tools.

The default two-seat Council makes five model calls: two proposals, two peer reviews, and one synthesis. It can therefore take longer and use more API credit than a single-model answer. FAST and DEEP use the configured models and different response budgets; they are not guarantees of a particular model's reasoning capability. The heuristic can miss unusual wording, so the current route is shown above the conversation.

## Clock, weather, and markets

The large clock uses the computer's current time and timezone, including seconds and date. It does not depend on weather location.

Weather uses browser geolocation after permission. Click **Use my location** on the first visit; subsequent page loads can use an already-granted location permission. Coordinates are rounded to two decimal places in the browser and again on the server before being sent to Open-Meteo. This is roughly a kilometre of latitude, with longitude distance varying by latitude. IRIS retains weather and coordinates only in runtime memory, not in its persistent database or settings. Browser permission storage and the location service itself are controlled by the browser. Weather shows Celsius, feels-like temperature, wind, and the observation time. See [Open-Meteo](https://open-meteo.com/) for the data source.

The fixed market watchlist uses ETFs as broad market proxies:

| Symbol | Coverage |
| --- | --- |
| SPY | S&P 500 |
| QQQ | Nasdaq-100 |
| DIA | Dow Jones Industrial Average |
| IWM | Russell 2000 |

Prices are in **USD** and represent the latest available completed daily close, with the change from the previous daily close. Each row includes its date. These are not live quotes or the index values themselves. Data comes from a public Yahoo Finance endpoint, an unofficial integration whose availability is not guaranteed. The source links open [Yahoo Finance](https://finance.yahoo.com/).

Widgets attempt a refresh every fifteen minutes while the page is running. Source failures show unavailable or clearly marked cached readings rather than invented values. Browser location accuracy and public data freshness can vary.

## Optional phone access

The separate phone connection now supports owner-only SMS conversations, PIN-protected incoming call conversations, and explicitly confirmed outgoing notifications. It uses Twilio and needs a suitable number, provider credentials and a public HTTPS tunnel to its own port, **8767**. Use `setup-phone.bat` and `start-phone.bat`; follow the [phone setup guide](PHONE.md) for Canadian number requirements.

Phone service is disabled until configured. The desktop server on port **8766** is not the public phone endpoint. Phone conversations currently have isolated history and no access to desktop actions or personal records; calls use a standard Twilio voice. The laptop and tunnel must stay awake. Reliable contact while it sleeps and streaming Fish Audio calls are later extensions.

## Verification limits

Automated tests exercise request routing, standby state changes, command recognition, and widget data handling. Synthetic audio and mocked browser devices do not establish real microphone or clap accuracy. Actual double claps, browser location permission, background-tab behavior, and NVIDIA speech acceleration still need checking on the HP OMEN 16. Keep the visible state indicators in view during the first hardware trial.
