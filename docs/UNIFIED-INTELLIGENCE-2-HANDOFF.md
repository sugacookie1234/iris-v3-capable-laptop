# Unified Intelligence 2.0 — implementation handoff, not implementation

Preserve IRISBrain, FAST/DEEP routing, CouncilExecutor, ToolExecutor, existing stores,
provider ledger, orchestrator and native windows. No new agent framework, Council,
privileged browser bridge or general OS execution. Defaults and Fish voice stay
unchanged. Model comparison needs evidence and explicit owner approval before any
default-model change. No model training or live provider benchmarking occurred here.

## Preconditions and release gates
- Retain IRIS-SEC-001's independent origins/cookies and exact Host/Origin checks.
- Keep durable provider admission in every transport, including Council fan-out.
- Complete native asset/lifecycle acceptance before making visuals necessary for
  approving or executing anything. In-chat fallback remains available.
- Indirect context must never supply permissions, approval IDs or trusted facts.
- Plaintext SQLite, incomplete vault/settings backup and same-user malware remain
  privacy risks. They prohibit broad unattended private-data ingestion/export, not
  offline development of a typed intent classifier. Do not silently migrate stores.
- A process-lived main session is not a remote access credential. No public tunnel.

## Smallest first slice
Introduce a typed interpretation result behind a default-off experimental setting.
One existing FAST request should produce either conversational text or a bounded
proposal. Do not add a second interpretation call to every ordinary reply. Reuse
the current deterministic compound skill and one already registered read-only
capability as the first integration. Keep authoritative clock/standby operations
host-owned. Do not add new tool permissions with this rollout.

Acceptance: paraphrases select the same capability; playful conversation remains
conversation; contradictory/ambiguous references request clarification; a model's
JSON cannot directly mutate a visual, execute a tool or grant permission. A failed
interpretation falls back to an honest question or ordinary dialogue, never a paid
fallback, guessed operation or infinite retry.

## Proposed contracts
1. `InterpretationV1`: version, current owner-turn reference, kind (conversation,
   question, hypothetical, action, clarification), bounded response text, optional
   registered capability ID and exact typed arguments, optional context references.
2. `ContextRef`: stable ID, version, kind (topic/project/task/visual/result), source,
   trust classification, privacy/export policy, expiry and verified-result status.
   Model-provided references are candidates; the host resolves them from an
   allowlisted snapshot. IDs do not grant access or imply consent.
3. `ProposedPlanV1`: at most a small configured number of steps (start with three),
   registered capability IDs, validated arguments, dependencies and result needs.
   No executable strings, code, arbitrary URLs, shell syntax or tool installation.
4. `ExecutionReceipt`: host-generated plan/step IDs, validated argument digest,
   approval decision, lifecycle state, result verifier, evidence reference and
   cancellation/partial-effect information. Generated prose is not a receipt.

Reject unknown fields/versions, unregistered capabilities, forged references,
non-finite numbers, oversize text and invalid graphs before state mutation. Schemas
belong in Python; frontend only displays validated results. Display and spoken_reply
remain separate representations of the same verified facts.

## Authority and execution
The model proposes intent; it cannot set AuthorityContext, RequestOrigin.USER,
permission lists, approval decisions or standing consent. Python derives provenance
from the actual ingress and retains existing registered-tool authority rules.
Consequential steps pause for the existing exact-operation approval, bound to plan
ID, argument digest and current workflow revision. Replayed or stale approval fails.
Untrusted notes, retrieval, business evidence and Council opinions cannot approve.

Short workflows use proposed -> validated -> awaiting approval -> running ->
verifying -> completed/failed/cancelled/partial. Persist a bounded journal using
existing job/history infrastructure, not another scheduler. Cancellation must be
checked before each step and approval resume. After a crash, do not replay a step
whose effects are uncertain: show its receipt and request owner review. Idempotency
keys and verifiers are per capability, not blanket promises of exactly-once effects.

## Context and natural conversation
Maintain one bounded context view shared by conversation and visuals: active topic,
project, scenario ID/revision, verified results and unresolved references. Do not
merge all private history into every provider prompt. Retain source labels and
explicitly permitted export scope. Untrusted text is quoted data, never a system
instruction. Ordinary ephemeral choices are not automatically permanent memories.

"Guess how much I got for my assignment" is playful speculation: offer a clearly
labelled guess, without asserting access to grades. A request for the actual grade
requires evidence. Warmth, celebration and restrained humour do not require false
awareness. Keep natural occasional "sir", avoid repetitive acknowledgements, and
disagree respectfully when warranted. No movie dialogue or actor-voice changes.

The COMP 248 transcript was mentioned but not supplied to this handoff. Use a
synthetic guessing-game example initially; do not claim to have imported, reviewed
or trained on that private transcript. Owner approval is needed for any later
private-conversation benchmark/export.

## Existing models and Council
Use configured FAST for normal dialogue and straightforward interpretation; DEEP
for genuinely complex reasoning. Existing Council compares competing approaches
or critiques difficult plans only when justified. It does not vote on permissions.
Set step/call/latency ceilings and cancellation before invoking the existing engine.
Charge each actual adapter attempt to the existing ledger; distinguish reservations,
completed calls, token usage when returned and unknown billing. Do not silently
enable paid models, retries or providers to improve benchmark scores.

## Evaluation plan
First implement offline fake-provider fixtures, including malformed proposals and
hostile second-tool requests. Extend CAP-34 while keeping a frozen holdout separate
from development examples. Compare the actually configured Nemotron target with
owner-approved alternatives using identical prompts/context/tool schemas and
generation settings. Verify availability/pricing at benchmark time; do not invent
current alternatives or equate "free" with unlimited use.

Measure separately:
- Social intent and concise natural conversation (blind rubric, supported guess).
- Intent and capability accuracy, arguments and ambiguous-reference abstention.
- Context retention and private/untrusted-context isolation.
- Plan completion verified by host receipts, cancellation and crash recovery.
- Permission adherence (zero unauthorized effects is a hard gate).
- Unsupported factual/action-success claims, not just fluent explanations.
- End-to-end latency (p50/p95), adapter calls, confirmed usage and estimated costs.

No live paid benchmark without approval. Record failures and sample sizes; an
offline contract pass is not a model intelligence score. Do not tune on holdouts,
promote memory suggestions automatically or change the default based on anecdotes.

## Dependency-ordered milestones
1. Contract, validation and synthetic social/intent holdout; no execution change.
2. Experimental FAST interpretation -> existing compound/read-only capabilities;
   preserve deterministic fallback and all security tests.
3. Provenance-aware shared context and references with expiration/revisions.
4. Three-step host-owned plan preview, then existing approvals and verified receipts.
5. Cancellation/recovery and persistent project continuity using existing stores.
6. Approved live comparison, measured rollout and owner review of default choices.

For each milestone: small vertical slice, adversarial tests, regressions, documented
limits, coherent commit on the development branch. Do not merge main. No computer
control expansion, screen capture, communications, Gmail or spending is part of
this handoff or the stabilization sprint.
