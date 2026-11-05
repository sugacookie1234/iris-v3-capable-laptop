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
