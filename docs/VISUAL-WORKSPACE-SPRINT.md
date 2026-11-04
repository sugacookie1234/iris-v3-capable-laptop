# Native Visual Workspace — 2026-11-04

Baseline 9c0de0d was clean; no interrupted implementation existed. Owner already
verified the five-turn in-chat example and renderer. This sprint extends those
working components; it does not repair a blank-chart defect.

## Implementation
One DesktopRuntime, server and orchestrator own both windows. The new lifecycle
controller coalesces requests and dispatches its native operations through the main
WinForms control's BeginInvoke. Creation calls existing pywebview/WebView2; its
installed Windows backend also marshals secondary creation with Invoke. No HTTP
worker directly creates a native window. No JS API bridge is supplied. Windows are
resizable, ordinarily minimisable/movable, and created with focus=False. Navigation
is restricted to the owned loopback origin. Main-window FormClosed disposes the
secondary. Repeated updates use the same window; a manual close is respected until
an explicit reopen or a new visual workflow. Failed native creation retains in-chat
rendering. Browser mode uses that existing in-chat fallback, not a second server.

The state machine tracks closed/opening/open/closing, current ID/revision and manual
closure. Updating content is represented by backend revisions and frontend polling,
not a second native-window creation. Native creation means a window object exists;
conversation never claims the page finished rendering merely from that object.

## Authentication
The main bootstrap slot is unchanged. A separate 60-second single-use visual launch
token cannot invalidate a pending main launch. Both redeem via existing same-origin
/api/pair and the same HttpOnly session cookie. Visual pairing additionally returns
an unpredictable 15-minute window lease. The page removes the launch fragment,
keeps the lease in sessionStorage, and supplies X-IRIS-Visual. Both session and lease
are required for /api/visual/state and /api/visual/update; the visual ID is not a
credential. Close/shutdown revokes bootstrap and lease. A reopen mints fresh values.
No external page is authorised and no visual endpoint executes a computer tool.
Same-user malware can inspect memory/browser storage; this is not an OS sandbox.
The lease does not renew on polling. An explicit open request or a new visual workflow renews pairing in the same window; old leases are revoked.
Only one native workspace is supported. Secondary auth shares the main session's
lifetime, with the additional shorter lease. Main-session expiry policy is unchanged.

## One calculation owner
CompoundSkill now owns principal, rate, years, monthly contribution and comparison
rate. UI submits exact id/revision/changes; the host validates a replacement before
mutating. The existing monthly recurrence and bounds remain authoritative. Reset
restores 1000/5/10/0/no comparison. Both comparison lines use common assumptions.
DesktopRuntime's existing turn lock serialises voice/UI updates. Stale or duplicate
updates return a conflict. Per-workflow revisions and a runtime-wide sequence prevent
older UI responses overwriting a newer workflow. All state is session memory only.
The 15-minute skill expiry and bounded turns remain; polling does not extend them.

Controls use explicit Update/Reset buttons, not speculative frontend calculations.
The page polls every 1.5 seconds, with no overlapping poll loop; pending edits remain
visible. Cleanup aborts requests on pagehide. Responsive dark layout has labelled
inputs, keyboard focus, SVG axes/legend, backend totals, and an accessible table.
Reduced motion disables transitions/animation. No new frontend dependency/CDN.

Natural commands include show/open/close graph, reopen, rate/comparison, principal,
years and numeric monthly contribution. Unsupported phrasing asks for clarification
or follows the existing router. Spoken results are concise while the full assumptions
remain visible. Standby ends follow-up listening and leaves an open visual available
until closed/expired; it does not pause microphone monitoring or grant permissions.

## Organiser investigation
Recognised educational responses return before automatic extraction. A synthetic
whole replay spies on autonomy.submit and verifies zero calls, with zero provider
calls. The owner's earlier two rejected proposals cannot be attributed to specific
utterances from the available evidence; no private activity history was read and no
validation warning was hidden. Existing organiser evidence/permission checks remain.

## Validation / acceptance
Focused lifecycle/state/paired HTTP tests pass; exact final counts go in VALIDATION.md.
Mocked controller tests cover coalescing, manual close/reopen, failure and shutdown;
real-loopback tests cover independent bootstrap, concurrent redemption, invalid
credentials and lease expiry. Arithmetic includes an independent Decimal closed-form
check with contributions. Browser contract tests cover typed payloads and rejection
of old workflow responses. These are not proof of real native display or microphone
operation. Real local native smoke acceptance is attempted separately when feasible.

Residual acceptance: actual multi-monitor movement, maximise/minimise, audio
continuity, prolonged expiry/reopen and target OMEN hardware. No private memory,
business integration, model scripts, decision approvals or screen capture added.


## Native local smoke evidence
A real WebView2 test on this development Windows host used a temporary runtime,
FakeBrain and isolated browser profile. It verified an actual secondary native window
with rendered SVG, an 8% update in the same window, a principal form submission that
changed host state, close with the main window retained, and reopening with SVG.
Provider call count was zero. It did not test actual microphone/speaker hardware,
OMEN hardware, multiple monitors or human visual polish. Test result artifact:
.local/visual-native-smoke-result.json. The initial process exited with an error only
when tempfile cleanup encountered a retained WebView2 BrowserMetrics file. The exact
synthetic directory was subsequently verified and removed after the process exited.
The opt-in reproducible fixture is tests/native_visual_workspace_smoke.py; it reports
any delayed synthetic-profile cleanup rather than claiming it completed.

UI changes also append only the canonical public example and verified summary to
bounded conversation history, so ordinary explanatory follow-ups see current values.
No raw UI text, window token, private result or local path is promoted. 'Explain the
difference' is accepted in addition to 'Why…'. HTTP revision conflicts refresh current
values before another explicit edit; they do not silently retry the old mutation.

Focus correction: pywebview's Windows focus=False sets WS_EX_NOACTIVATE. After the
non-activating initial Show, the host clears that flag on the owned child and enables
normal activation. Subsequent updates do not Show/Activate the window. A mock verifies
the style mask; actual physical keyboard/mouse acceptance remains separate.

Explicit personal commitments and reminders bypass educational parameter matching.
Synthetic runtime regression verifies that three such turns reach the existing
organizer submission path, leave the old scenario values unchanged and release the
educational context. This does not establish the cause of the owner's earlier
unsupported-action warning; genuine organizer validation failures remain visible.

## Owner acceptance sequence (remaining hardware check)
Start the native app using the existing launcher. Say "Explain compound interest",
then "Use eight percent", "Compare that with five percent", and "Explain the
difference". Confirm one child window updates while main conversation remains usable.
Edit principal to 2000 and press Update; ask for the current example explanation.
Try "Contribute 200 monthly", "Use 20 years", and "Restore the original example".
Close the graph, continue talking, then say "Open the graph again". Check keyboard
navigation, minimise/maximise and movement between monitors. Say "That's all. Stand
by" and verify actual clap-wake standby/audio continuity separately. Close main and
confirm its child exits. No live provider test was performed in this sprint.
