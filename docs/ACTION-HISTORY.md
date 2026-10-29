# Local action history and capability awareness

Say or type **“What can you do?”** to inspect this running desktop build. The
answer is generated locally from registered tools and configuration. The read-only
`/api/capabilities` endpoint uses the same authenticated local session as the UI.
It exposes typed arguments, authority level, required/granted host permissions,
locality, reversible effects and configured model roles. Discovery cannot execute
a tool, grant permission, install a skill or probe a provider.

“Configured” is not a connection, credit balance, installed-app or microphone
health check. FAST and DEEP can use the same model. Council seats are roles, not
proof of independent model families. The separate phone bridge's status is unknown
to desktop chat; it does not grant SMS/calling rights here. Skill discovery remains
limited to existing host workflows; automatic installation is not implemented.

**“What have you done today?”** reads receipts using the configured local timezone.
**“Show action history”** shows up to 20 recent receipts from retained history.
Each receipt includes ordered ID, tool name, origin, start/finish times, approval
state, failure category and outcome evidence. Successful handler returns are
*unverified* unless a supported Windows adapter independently checked a visible
app window or system-volume readback. Workspace routines report each component;
Explorer folder selection is still unverified. Timeouts and interrupted attempts
have unknown effects and are never automatically replayed.

Coverage starts with this update: desktop controls, bounded filename search,
daily briefings and registered chat-tool invocations. It is not a historical
reconstruction. Automatic notebook/task/goal changes retain their existing
Activity and Undo interface. Phone, microphone, speech, web requests, ordinary
chat, direct memory commands and other UI operations are not logged by this store.
CAP-30 therefore remains a tested first slice, with full route/model/cost tracing
and cross-channel coverage still pending. No cost estimates are invented.

The ignored `.local/action_history.sqlite3` contains metadata only. There are no
prompts, raw audio, responses, paths, tool arguments, note contents, full error
messages, endpoints or credentials. This SQLite file is not encrypted; normal
Windows account/disk protection applies. It is bounded to 1,000 records and 30
days, pruned on startup/read/write. **“Clear action history”** requests confirmation
and deletes these receipts with SQLite secure deletion enabled. It leaves tasks,
goals, memories, notes and their separate histories untouched. Backup copies are
outside this deletion's scope.

History and capability replies are kept out of later model conversation context
and the automatic organizer. Their short spoken summaries can still use Fish
Audio when voice replies are enabled. Queries themselves make no LLM request.
An audit write failure during execution never changes tool authority or turns an already
performed action into a failure/retry; the history command discloses missed
receipts for that session. A crash before saving a final result leaves an unknown
receipt. Full filesystem failure before any receipt is written can leave no record.

This adds evidence and awareness to the existing executor. It does not add a
general planner, autonomous skill learning or broader access to your computer.
