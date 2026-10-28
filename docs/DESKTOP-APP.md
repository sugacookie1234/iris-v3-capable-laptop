# Standalone Windows app

Double-click **start-iris.bat**. IRIS opens in its own resizable Windows window;
there is no browser tab, address bar, or console to keep open. It owns its local
server. Closing the window keeps IRIS running in the Windows notification area.
Double-click its tray icon, or right-click it and choose **Open IRIS**, to return.
Choose **Quit IRIS** in that menu to stop the app, microphone and local server.
If Windows cannot create the tray icon, closing the window exits normally instead.
Reopening the launcher while IRIS is already running directs you to the tray.

On the first launch, click **Start standby** and allow the microphone. Double clap
to wake IRIS, then speak. The app remembers microphone and location permissions in
its application profile under ignored `.local/webview/`. Later launches restore
standby automatically when microphone permission is still granted. An explicit
**Pause mic** is remembered and must be resumed by clicking; a denied or unknown
permission leaves Start standby visible. Chrome mode still starts with a click.
Quitting IRIS, sleeping the laptop, or pausing its microphone stops standby.
Closing just its window keeps standby and reminders available while the laptop is awake.

To start at sign-in, right-click the IRIS tray icon and enable **Start with Windows**.
This is off by default and affects only your Windows account. Uncheck it to remove
this checkout's login entry. Keep the repository and its `.venv` at the same path;
if you move it, disable this option first and enable it again from the new location.
Login startup opens IRIS normally so microphone permission or other setup needs remain visible.

The window uses [pywebview](https://pywebview.flowrl.com/) and Microsoft's
[WebView2 Runtime](https://developer.microsoft.com/en-us/microsoft-edge/webview2/).
WebView2 is an embedded rendering component, not an Edge browser window. Windows 11
normally includes it; if the app reports a missing runtime, install the Evergreen
Runtime from that Microsoft page and run `setup.bat` again. Python 3.11–3.13 is supported.

The default launcher uses `pythonw.exe` so it does not leave a console behind.
Startup errors show a Windows dialog. `.local/desktop.log` records startup/shutdown
events and error categories without configuration values or chat text.

## Optional Chrome mode

Run **start-iris-browser.bat** to use Google Chrome. Keep that launcher's console
open while using IRIS, and close it to stop the server. Chrome must be installed;
IRIS does not silently select Edge or the system's default browser. Weather and
market source links from the desktop app also open in Chrome. This preference is
limited to IRIS and does not change your Windows default browser.

## Local app, online providers

The app, conversation session, memories, tasks, clap detector and Whisper fallback
run on your computer. The configured chat provider and Fish Audio still need the
internet and available API credit. The desktop window does not make those services
offline. Local-only recognition can be selected in setup.

The server binds only to loopback and retains its session/origin checks. The embedded
window only permits navigation on its owned loopback origin. It exposes no custom
Python API to the page, disallows file-URL access and downloads, and keeps TLS checks
enabled. Ordinary external source links open separately in Chrome.

To support standby heartbeats while minimized and previously permitted audio on
launch, IRIS passes Microsoft's documented
[`disable-background-timer-throttling` and `autoplay-policy` flags](https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/webview-features-flags)
to its own rendering process. Microphone access still requires permission. It makes
no global browser or power-setting changes.
Actual minimized/hidden-window clap detection still needs a hardware test with your microphone.

Clap capture now runs in Python with sounddevice using the user's tested 44.1 kHz,
40 ms detector. The embedded view receives only a wake counter and microphone name;
no standby audio is saved or uploaded. A three-second ownership lease releases the
listener if the interface stops sending heartbeats. **Pause mic** and app shutdown
also stop it. Request recording uses the same microphone, with explicit matching
errors if Windows and the embedded recorder cannot identify one unique input.

## Updating or moving to the OMEN

Pull/download the repository, run `setup.bat` to install the desktop dependencies,
then launch `start-iris.bat`. Enter provider keys on the OMEN during setup; the current
Windows account's encrypted configuration is not portable. Existing memory/task data
stays under `.local/`; updating the code does not reset it.
