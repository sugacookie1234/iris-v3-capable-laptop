# Standalone Windows app

Double-click **start-iris.bat**. IRIS opens in its own resizable Windows window;
there is no browser tab, address bar, or console to keep open. It owns its local
server and stops it when you close the window. Minimize the window to keep IRIS
running. Reopening the launcher while IRIS is already running shows a notice.

After launch, click **Start standby** and allow the microphone. Double clap to wake
IRIS, then speak. The app remembers microphone and location permissions in its
private application profile under ignored `.local/webview/`. It still requires an
initial Start standby click after each launch. Closing IRIS, sleeping the laptop,
or pausing its microphone stops standby. It does not start automatically with Windows.

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

To support the local clap sampler while minimized, IRIS passes Microsoft's documented
[`disable-background-timer-throttling` flag](https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/webview-features-flags)
to its own rendering process. It makes no global browser or power-setting changes.
Actual minimized-window clap detection still needs a hardware test with your microphone.

## Updating or moving to the OMEN

Pull/download the repository, run `setup.bat` to install the desktop dependencies,
then launch `start-iris.bat`. Enter provider keys on the OMEN during setup; the current
Windows account's encrypted configuration is not portable. Existing memory/task data
stays under `.local/`; updating the code does not reset it.
