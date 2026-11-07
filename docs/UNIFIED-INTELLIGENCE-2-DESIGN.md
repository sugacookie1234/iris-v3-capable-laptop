# Unified Intelligence 2.0 — first experimental slice

Authority: [handoff](UNIFIED-INTELLIGENCE-2-HANDOFF.md). Implementation remains
default-off: set `IRIS_EXPERIMENTAL_INTERPRETATION=true` in the launch environment
to opt in; remove it or set false to restore legacy routing. No owner configuration
has been changed. This setting is not a new remote control or model-writable policy.

## Contract and execution

`iris/generalist/interpretation.py` parses exact JSON fields: version=1, current
host-generated turn ID, kind, bounded text, capability, arguments and candidate
context reference. Kinds are conversation/question/hypothetical/action/clarification.
Social intent uses conversation; contextual intent carries a reference. Only compound
and workspace_list are supported. Duplicate/unknown fields, forged permissions,
unsupported versions, native tool calls, non-finite or excessive numbers fail closed.

DesktopRuntime's existing turn lock owns interpretation through publication. The
model cannot write state by emitting JSON: the host rechecks current eligibility,
reference ID/revision/expiry, numerical limits and requested parameter/value.
Compound mutations use CompoundSkill; all graph values and success text come from
existing deterministic arithmetic. UI edits and conversation share the same state.
Single parameter changes are supported. Original-rate comparisons use five percent
only when principal/duration/contributions still match the original baseline;
otherwise clarification is required. No investment transaction exists here.

Workspace listing is limited to the configured root. Current affirmative owner
consent and existing workspace.read permission are required. ToolExecutor retains
MODEL provenance and its existing approval, timeout and path checks. No new permission
is granted. Results are displayed locally and never sent for cloud synthesis or added
to model history. Generated prose is not used as a tool or calculation receipt.

## Routing, cost and privacy

Eligible compound, workspace-list and playful-grade turns use one existing FAST
adapter request with no advertised tools. Active bounded example comparisons may
use FAST despite the generic compare->DEEP heuristic. Other DEEP and Council routing
remain unchanged. Ordinary dialogue remains on the existing single-response path;
this is not an extra interpretation call before every conversation.

The current request and public scenario snapshot are the only supplemental inputs;
private history, memory, vault data and tool results are excluded. Existing memory
and Council systems are preserved, not replaced. Public calculated summaries use
the existing canonical history path. Experimental turns do not trigger the organizer.
The standard transport retains durable quota admission; malformed output or provider
failure produces an honest clarification, without a retry or fallback provider.

## Deliberate limits

This is bounded semantic interpretation, not general autonomous reasoning. Host
eligibility and consent still use conservative intent cues; arbitrary paraphrases,
multi-parameter edits, complex number words and unrelated context are not promised.
Only a labelled synthetic guess demonstrates social output; actual model quality,
factual reliability and latency require an approved benchmark. No private transcript
training, learning traces, new scheduler, multi-step planner or local model installed.

Native origins/cookies/leases and approval routes are untouched. In-chat visuals
remain usable; the outstanding WebView2 reliability gate is NOT fixed. General
provenance-aware ContextRef, persistent projects and multi-step plans remain M3+.

## M3 — shared working context (supersedes the M3 deferral above)

### Gaps identified at 92d65a7

DesktopRuntime.history was a bounded but unlabelled list. Ordinary FAST/DEEP received
that list; Council serialized it into its question. The experimental interpreter
received only a compound snapshot, and unrelated deterministic dispatch cleared that
scenario. MemoryStore already records source, confirmation, sensitivity and expiry;
memory retrieval is bounded independently. It is not the right home for temporary
conversation topics. Organizer records and implicit Obsidian snippets were separate
prompt augmentation paths, so filtering chat history alone was insufficient.

### One session envelope, no new database

`iris/memory/working.py` provides host-owned WorkingContextV1. It is a small transient
export view beside the existing display/legacy history, not a persistent memory store.
It holds at most four 600-character references, retaining the first live owner topic
anchor plus recent exchanges. References carry UUID/revision, source (owner-authored,
host-verified, model inference, untrusted retrieved), privacy, permitted export and
monotonic expiry. The envelope has an ID/revision and last owner interaction timestamp.
Default lifetime is fifteen minutes, with individual entry expiry; new turns do not
extend old entries. A restart creates a new empty envelope; nothing is recovered or
replayed automatically. Explicit new-chat reset clears it.

The scenario and verified calculation reference are derived live from the existing
Orchestrator/CompoundSkill. No second financial state or calculation engine is stored.
UI revisions are visible immediately. Project/task ID lists are deliberately empty:
this slice does not choose a business project or import private project records.
The active conversational topic is an owner-source reference, not a model-generated
summary asserted as fact. Broader semantic topic classification is still future work.

### Integration and authority

With the existing experiment flag true, ordinary responses receive this bounded view
through respond_with_memory/IRISBrain instead of legacy history. This same system
context reaches FAST, DEEP and existing Council without changing their selection or
adding a provider call. Outside the experiment, the legacy behavior remains unchanged.
Persistent approved-memory retrieval retains its existing policy; no new permanent
memory is written by WorkingContext. Existing organizer writes still require their
existing owner-authorized policy, independently of this cache.

Active public-scenario follow-ups can now reach semantic interpretation without an
exact command phrase match. Understanding, capability eligibility and authorization
are separate: JSON proposals still pass current owner-intent, numeric grounding,
capability, reference and ToolExecutor checks. Conditional questions can request a
single grounded numeric change. Negated/quoted/retrieved instructions cannot change
the scenario. Conversation references resolve only against the exported snapshot;
unknown IDs, multiple candidates and expired/revised state cause clarification.
The entire snapshot is revalidated after inference and immediately before application,
under the existing turn lock. Failed/cancelled inference saves no new exchange.

Explicit discourse transitions (such as a new subject or “anyway”) clear the old
topic/scenario before response generation. Other ordinary follow-ups retain context.
This conservative host boundary is not a general learned topic detector. Ambiguous
project references remain questions rather than guessed selections.

### Export policy and limitations

Owner chat sent to configured reasoning may be reused in this bounded session view;
assistant text is explicitly labelled model inference, never verified evidence.
Private or untrusted retrieved content, credential-pattern matches and local-only
entries are excluded. Source/export labels are selected by Python ingress, never
accepted from model JSON. Raw private tool results are not retained in working or
legacy history in experimental mode. Implicit Obsidian augmentation, organizer-record
augmentation and organizer history replay are disabled only in this experiment;
explicit existing read/tool routes remain available under their existing permissions.
Current owner messages and already-approved persistent memory still follow their
existing provider-sharing policy. Pattern screening cannot discover every secret in
free-form owner chat; it is not a confidentiality guarantee or a prompt-injection sandbox.

If context export fails, normal conversation continues without unchecked history.
No additional network calls, durable trace store, background learning, project
selection, permission expansion or model change was added. Native reliability remains
unresolved and in-chat visual fallback remains available. Actual model coherence,
unseen paraphrases, implicit topic shifts and hardware behavior remain unverified.

## M4 — bounded workspace planning and execution

Use the existing default-off experiment flag, then enter an explicit request such as
`/plan workspace List the workspace, then read README.md and notes.md`.
One configured FAST request proposes JSON. Ordinary chat, DEEP and Council are not
rerouted; Council never authorizes execution. This explicit prefix is an initial
ingress boundary, not a claim of general autonomous request understanding.

ProposedPlanV1 contains only version=1, host turn reference, unverified objective,
nodes and candidate context_refs. TaskPlan/validate_plan enforce at most three
steps, a 90-second total registered-tool timeout budget and bounded scalar arguments.
Only actually registered workspace_list/workspace_read are exposed. Both are local,
reversible GREEN tools without declared effects, requiring existing workspace.read.
No output interpolation or dynamic search-to-file selection is supported. Unknown
files must be listed or explicitly named; their existence is not asserted in preview.

ToolExecutor dry-run applies trusted argument preparers without running handlers.
The host validates the prepared representation again and binds a new plan ID,
revision, five-minute expiry, runtime session, owner request digest and full permitted
working-context snapshot into a canonical SHA-256 digest. The preview shows prepared
paths/arguments, order/dependencies, permission and separate approval requirements,
outputs and limitations. No filesystem observations or tools execute during preview.

The owner must submit the displayed `/confirm-plan <id> <revision> <digest>` through
authenticated main chat. IDs/digests alone are not permission; an unrelated origin,
model output or “looks good” statement cannot execute. The current runtime consumes
the pending confirmation once. Before every sequential step and again after approval,
it checks context, expiry, unchanged specifications and current permissions.
Each step uses the existing exact-operation approval dialog, even though the plan
is already confirmed. Prepared arguments must still exactly match the approved
snapshot when ToolExecutor invokes the registered handler. No blanket approval exists.

`/cancel-plan <id>` sets a host-owned cancellation event even while a chat execution
waits for approval. Existing executor cancellation stops its worker; pending approval
waits now support this optional cancellation signal. Normal legacy approvals retain
their existing behavior. Terminal workflows cannot replay. Reset or process restart
invalidates all plan authority; there is no auto-resume or replacement tool selection.

ExecutionReceipt records are generated locally: plan/revision, step, capability,
canonical argument digest, MODEL provenance, approval status, timestamps, outcome,
verification, failure/cancellation/uncertainty and an ActionHistory invocation ID.
The existing observer records attempts and interrupted reads, without a database
migration. A missing initial audit record blocks execution. Detailed workflow receipts
are session-only; existing content-free invocation history survives restart. Durable
effectful recovery and persisted cross-step journals are a later milestone.

Verification means a bounded returned directory/text snapshot matches the expected
path/schema and has retained invocation evidence. It does not prove project correctness,
file relevance, complete inspection when truncated, or any arbitrary model objective.
Malformed results or unavailable verification stop later steps and report unverified
or uncertain outcomes. A failed run can retain earlier completed-step receipts; its
summary reports completed and unexecuted counts rather than inventing total success.
Uncertainty concerns read completion/evidence, not a claim that this read-only slice
modified files. Existing ActionHistory's generic result remains conservatively unverified;
M4's more specific returned-data verification is recorded in its session receipt.

Raw tool outputs remain local and are not passed to another step as instructions,
sent for model synthesis, saved as personal memories or included in working/chat history.
Only deterministic local summaries are returned. No native window is required.
This is a synthetic-tested engineering slice, not live planning accuracy or hardware
acceptance. The existing native reliability gate remains unresolved.


## M4.5 measurement boundary (partial checkpoint)

The intelligence runner is distinct from CAP-34's guidance ablation. It directly
invokes existing FAST interpretation/planning interfaces, then production validators
and registered read-only handlers in a disposable synthetic workspace. It does not
replace DesktopRuntime or authorize owner operations. Every fake adapter attempt
uses a temporary ProviderUsage ledger; concurrency/call/deadline/cancellation
admission is tested. Reports omit raw prompts, outputs and private file contents.
Only receipt metadata and field-match results are retained.

There is intentionally no live adapter at this checkpoint. `--mode real` refuses
before evaluation/account loading. This prevents accidental provider consumption
while live authorization, exact-target binding, unknown-cost consent, durable run
budgets and hard in-flight timeouts are unfinished. Ordinary respond(), DEEP and
Council quality measurement are also unfinished. No experimental defaults changed.


## M4.5 bounded live readiness

Supersedes the earlier transport-disabled checkpoint. benchmark_admission.py binds
exact consent to persistent run accounting and uses bounded worker processes around
the existing transport. Normal provider limits additionally apply with a stable
session across workers. No verified price is available; unknown-cost acknowledgment
is mandatory and no currency ceiling is advertised. Cancellation is local, never
proof of remote billing cancellation. interpretation/planning remain host-validated;
live previews do not execute confirmed workspace plans. Offline execution uses only
disposable fixtures. Ordinary FAST/DEEP/Council measurements call the existing brain
with no executor and share the explicitly selected target rather than changing owner
policy. benchmark_review.py emits local unscored human-review records and validates
anchored scores/response hashes. See EVALUATION.md for exact scope and pilot controls.

## M5 bounded project continuity and recovery

The new projects.sqlite3 is a lazy, explicit-owner-command store; no existing data
is migrated. It contains up to ten DPAPI-protected project envelopes, each with
80-character title, 400-character optional objective, five task ID/revision links
and ten most-recent workflow summaries (three steps each). The payload is private,
export=none. Only random project IDs and SQLite structure are plaintext. Envelope
writes verify decryption/schema before an atomic SQLite commit. Wrong-account,
corrupt/unknown schema and symlink/junction redirection fail closed. Protection does
not defend against same-Windows-user malware, disk rollback or account compromise.

TaskStore remains authoritative; this slice links tasks only, not goals or guessed
folders. Links copy no content and are rechecked at selection and before/after each
approval. Missing/deleted/changed links prevent execution. Project identity is an
explicit full ID, never inferred by a model. Selection is session-only: after restart
an owner lists/selects a retained record. The bounded WorkingContext local project
reference has host provenance, revision and normal TTL, private/no-export metadata;
it never enters provider snapshots, plans' model context, or persistent chat history.

PlanRun now has an optional fail-closed ProjectJournal observer. It journals before
invocation/approval/verification and after each returned-data receipt. It stores only
workflow/step IDs, digests, dependencies, lifecycle, verification and ActionHistory
IDs. No raw arguments, file contents, objective text from the model, approval token,
confirmation digest/session or tool output is persisted. ActionHistory remains the
source of invocation timestamps and historical approval evidence. Its existing
30-day/1000-record retention can make older project evidence unverifiable.

Recovery is inspection, not execution: historical running/approval/verifying steps
without a durable verified receipt remain interrupted/unknown. Pending steps remain
unexecuted. Completed claims require both the protected receipt metadata and a
matching returned/approved MODEL ActionHistory entry. This proves historical bounded
returned-data verification, never current file state or project correctness. No
PlanRun is deserialized, no authority restored and no old plan auto-replayed. A fresh
/plan workspace request uses the existing default-off interpreter, exact confirmation,
per-operation approvals and read-only allowlist. Journal failure stops later steps;
shutdown cancellation still stops when evidence cannot be saved.

Authenticated chat commands (experimental feature remains off by default):
- /project create <title> | <optional objective>
- /project list
- /project select <full-id>
- /project link-task <task-uuid> <current-task-revision>
- /project show <full-id> or /project resume <full-id> (inspection only)
- /project clear (deselect only)
- /project delete <full-id> <current-project-revision>
- /plan workspace <new request> (fresh M4 preview, never automatic resume)

Deletion affects only project continuity, not tasks/goals/history/backups. Ten recent
workflow summaries replace older ones; project records persist until explicit delete.
There is no automatic import, monitor, scheduler, cloud export or global rollout.
The existing portable backup allowlist intentionally remains unchanged: projects are
NOT included. Account-bound store copies require original Windows recovery material;
portable project backup/export is a future explicit implementation gate. Unreadable
records are retained and fail closed, not silently repaired or overwritten. Native
WebView2 reliability remains unresolved; the chat interface is sufficient.

## M5.1 portable project backup boundary

Supersedes M5's project-backup exclusion. The existing iris.backup archive v1 now
accepts projects.sqlite3 in addition to the six prior stores. No new backup service,
key format or migration is introduced. Exact M5 SQL schema/version and envelope
validation are shared by live continuity and portability; duplicate JSON fields,
unknown fields, oversized/duplicate references and malformed records fail closed.

Export reads only an offline source snapshot. Validated source-DPAPI envelopes are
rebuilt as portable JSON in a fresh RAM-only database, inside the existing Scrypt /
Fernet authenticated archive. Restore validates then re-protects each envelope for
the destination Windows account, verifies it, and builds a fresh protected database
before disk staging. Rebuilding prevents portable plaintext surviving in SQLite free
pages. Any project failure aborts publication of the entire backup/restore. The
source is untouched and a restored directory never overwrites an existing one.

Old archives lacking projects remain supported. Old binaries reject the new store
before restoration rather than partially interpreting it. The 64-MiB aggregate
limit, private getpass input and existing notes-job conversion are unchanged.
Source/destination/archive ancestor symlinks and junctions are refused; same-user
filesystem races and RAM/pagefile/crash-dump access are not a guaranteed boundary.

Restored metadata is historical evidence only: no session selection, PlanRun,
permissions or confirmation is reconstructed. M5's current task revisions and
ActionHistory corroboration still apply. Missing evidence remains unknown. New
execution requires a new preview and all current confirmations/approvals. The
/project recovery command reads no store and gives non-destructive recovery options,
even with the experiment disabled. No cleanup, migration or provider call occurs.
See ENCRYPTED-BACKUP.md for unchanged CLI commands, compatibility and recovery limits.

## M6 evaluation boundaries

M6 reuses the existing benchmark runner, not a new reasoning/execution system.
Development-set m6 contains a separate synthetic corpus. Raw model plan fields are
scored before host acceptance; dependency accuracy is reported separately. Rendered
response review is local, preserves exact output hashes and leaves human scores blank.
Model blinding removes provider/model metadata only; wording/route can reveal clues.

Private project identity stays host-local. That corpus case creates a protected
synthetic record and local WorkingContext reference but exports neither title nor ID.
It cannot be admitted to a live benchmark. Controlled same-task route overrides and
actual synthetic tool execution are also offline-only; production routing, Council,
ToolExecutor and permissions remain unchanged. Live planning remains non-executing.

M6 consent binds the selected-case fingerprint plus a fingerprint of canonical
identity/prompt-producing source; this is not a byte hash of dynamic context IDs.
CLI preflight checks that binding without provider contact. The existing durable
adapter budget and normal provider ledger remain authoritative; no new transport,
retry, fallback, model selection or automatic activation is introduced.
# M6 observability clarification — 2026-11-06

The evaluation result has distinct layers: raw proposal/parse, host acceptance,
host-visible response and source, deterministic calculation payload, actual tool
attempts, execution receipts and unscored human review. Host acceptance does not
assert intent correctness; a safe clarification remains a model-selection failure.
Plan dependency equivalence is an ordered capability graph, independent of node
labels. Exact arguments, registered contract validity and labelled request constraints
are separate measurements; none confers execution approval. See M6-POST-PILOT.md.
