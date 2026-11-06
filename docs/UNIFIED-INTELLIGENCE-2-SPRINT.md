# Unified Intelligence 2.0 — continuation checkpoint

Recovered baseline: 0f75f6a on sprint/evaluation-business-os. Uncommitted engine/runtime
integration, new interpretation module and tests were preserved and completed in place.
No staged work existed. `tatus -sb` remains untouched/untracked (SHA256
F86ED9018F5473F692F3EAE494C4F62B988CD12FDAD06525AE61BA3C538CE37F).
Stabilization implementation and owner data were not restarted or modified.

M1: strict wire contract and adversarial tests implemented. M2: default-off FAST
integration with compound and root workspace listing implemented. Focused checkpoint:
41 tests passed (interpretation, orchestration, orchestration authority, brain engine).
The incremental implementation checkpoint is 80b898b (pushed). Final validation
below supersedes the original pending-full-regression note. This is not an enabled
rollout or a real-model benchmark.

Corrections during recovery: invalid test arrays were being replaced with empty
objects by the fixture helper; a synthetic filename used a correctly blocked secret
keyword; standby belongs to frontend dispatch, not a backend chat assertion. A
bounded active-example compare now avoids the generic DEEP route. Security checks
were retained. File enumeration needs normal Windows process/file access in tests.

No real provider calls, native hardware acceptance or paid usage occurred. Native
stress remains FAILED from stabilization. Keep default off and in-chat fallback.
## Final offline validation and continuation

- Full suite: 1041 run, 1037 passed, four skipped, zero failures/errors (118.233s).
  Evidence: `.local/unified-intelligence-2-full.log`.
- Desktop JS: 12/12 checks passed.
- CAP-34: 133/133 per arm, zero regressions; local evidence in
  `.local/unified-intelligence-2-evaluation/summary.md`.
- Quota/cancellation + interpretation focused suite: 23 passed.
- Existing authentication/bootstrap/approval tests included in the full suite;
  IRIS-SEC-001 checks retained. No new native smoke or physical acceptance claimed.

Reserved ten-case holdout is separate from development responses and unscored.
See UNIFIED-INTELLIGENCE-2-EVALUATION.md. No broad language-understanding score,
live latency or provider-billing measurement is implied by the contract passes.

Recovery commands: `git status -sb`, `git log -3 --oneline`, then read this file
and UNIFIED-INTELLIGENCE-2-DESIGN.md. For code changes run
`.\.venv\Scripts\python.exe -m unittest tests.test_interpretation tests.test_interpretation_provider`
before broader regression. No need to rerun stabilization for documentation-only work.

Next authorized design dependency: M3 provenance-aware shared context with bounded
export policy/expiry, then host-governed plan preview. Keep the feature default-off
until approved model-quality evaluation. Do not broaden consent cues to force a
holdout pass or automatically activate new permissions. This M1/M2 checkpoint is
complete as a bounded offline-tested vertical slice, not the whole intelligence roadmap.

## Changed-file manifest (relative to repository root)

- `iris/brain/engine.py`: one FAST interpretation adapter call.
- `iris/desktop/runtime.py`: default-off admission and host application.
- `iris/generalist/interpretation.py`: wire schema, references, eligibility and effects.
- `iris/generalist/evaluation.py`: CAP-34 registration.
- `tests/test_interpretation.py`: 21 synthetic contract/integration tests.
- `tests/test_interpretation_provider.py`: two quota/cancellation tests.
- `tests/fixtures/interpretation_holdout.json`: ten unscored reserved prompts.
- `docs/OPENJARVIS-ARCHITECTURE-STUDY.md`: reference mapping and exclusions.
- `docs/UNIFIED-INTELLIGENCE-2-DESIGN.md`: implementation and limits.
- `docs/UNIFIED-INTELLIGENCE-2-EVALUATION.md`: evidence interpretation and holdout.
- `docs/UNIFIED-INTELLIGENCE-2-SPRINT.md`: recovered state and continuation.
- `docs/IRIS_CAPABILITY_TRACKER.md`: existing capability statuses.
- `docs/IRIS_DECISIONS.md`: ADR-037.
- `docs/SPRINT-BACKLOG.md`: dependency-ordered next work.
- `docs/VALIDATION.md`: exact final regression results.
- `SECURITY.md`: experimental authority/privacy boundaries.

## M3 incremental checkpoint — 2026-11-05

Recovered 92d65a7 on the development branch; tracked tree was clean and only the
preserved `tatus -sb` was untracked. No earlier work was replaced. Added bounded
WorkingContextV1 in the existing memory package, engine/memory integration, runtime
lifecycle/export filtering and safe broader public-example interpretation.
Compound state, tools, Council, ledgers and owner databases remain in their existing homes.

Focused validation: **62 tests passed** across working context, interpretation,
provider admission, brain engine, orchestration and orchestration authority.
The new working-context module has 19 synthetic test methods. Five separate held-out
multi-turn cases are reserved and unscored; the original M1/M2 holdout is unchanged.
Full regression/CAP-34 are pending at this incremental checkpoint. Do not interpret
focused tests as real-model or hardware acceptance. Native stress remains FAILED.

Next closeout commands: full unittest discovery, twelve desktop checks, CAP-34 with
the added working_context category; then record exact counts, commit and push.
After M3 closeout, the next handoff dependency is bounded host-owned plan preview
and verified receipts, not autonomous execution or new tool permissions.

## M3 final acceptance and handoff

Completed source checkpoints: 9642383, f47870e and 2ecaf40. Final acceptance:
**1061 Python tests run, 1057 passed, four skipped, zero failures/errors** (144.206s);
**12/12 desktop JS checks passed**; **CAP-34 153/153 per arm, zero regressions**.
Logs: `.local/working-context-acceptance.log` and
`.local/working-context-acceptance-evaluation/summary.md`. Focused final suite: 43 passed.
The nineteen-test initial context checkpoint was expanded to twenty methods to retain
deterministic graph/skill lifecycle behavior. Final full regression supersedes the
earlier 1060-test runs; repeated runs were due to the two substantive final hardening fixes.

M3 is complete as a bounded, offline-tested implementation, still default-off. No
real-model score or hardware acceptance. No live owner configuration/data was changed.
`tatus -sb` remains untouched with its recorded hash. Main remains
`b4e5c9636d02657cb3cd89d368583ee6c8ebd006`. Native WebView2 reliability remains unresolved.

Changed M3 code: `iris/memory/working.py`, `iris/memory/integration.py`,
`iris/brain/engine.py`, `iris/desktop/runtime.py`, `iris/generalist/interpretation.py`,
`iris/generalist/evaluation.py`. Tests: `tests/test_working_context.py` and
`tests/fixtures/working_context_holdout.json`. Documentation: SECURITY.md, this sprint,
design/evaluation documents, capability tracker, validation and sprint backlog.

Continuation: inspect Git status/log and read this final section and the M3 design.
Next dependency is a bounded host-owned plan preview with verified receipts, keeping
existing approvals and permissions. Do not enable general execution, infer a private
project from ambiguous wording, train on conversations or run paid benchmarks.
For changes, begin with `python -m unittest tests.test_working_context
tests.test_interpretation tests.test_interpretation_provider`; rerun full acceptance
only after material changes. No stabilization restart or holdout tuning is needed.

## M4 checkpoint A — preview only

Recovered c3a2c7e with no tracked changes initially; preserved `tatus -sb`.
Added ProposedPlanV1, canonical host snapshots, three-node/90-second limits and
non-executing `/plan workspace <request>` previews behind the existing default-off
flag. Reuses validate_plan, registered workspace_list/workspace_read and ToolExecutor
dry-run preparation. No filesystem inspection occurs during preview. Fixed paths
only; output interpolation and dynamic selection are unsupported. Permissions are
checked and prepared arguments are included in the exact digest and preview.

Fourteen focused planning/preview tests passed after the automatic approval service's
usage reset. The first test attempt was not executed because review quota was exhausted.
The resubmitted older M1/M2 request did not require restarting those completed milestones.

Execution, confirmation, cancellation and receipts are NOT implemented at checkpoint A.
Next: existing approval integration and exact prepared-execution checks, then bounded
read-only execution/verification, followed by full acceptance. No new provider calls,
owner file reads, permanent memory changes or native reliability claim.

## M4 checkpoint B — controlled execution

Checkpoint A is c62d38d (pushed). Execution now binds the explicit in-chat
`/confirm-plan <id> <revision> <digest>` command to the current runtime session,
owner request digest, exact prepared steps, expiry and working-context snapshot.
Every step separately uses the existing approval callback; no standing consent.
ToolExecutor checks its actual prepared snapshot against the confirmed snapshot,
requires an ActionHistory attempt record and retains its existing timeout/cancel
worker behavior. No alternative executor or permission system was introduced.

Real registered workspace_list/workspace_read handlers completed two- and three-step
workflows over temporary synthetic files. Verifiers validate returned bounded data,
not project correctness. Host-generated receipts reference existing invocation
history, exclude raw file data and summarize locally. Terminal runs cannot replay;
reset/restart invalidates pending authority. Per-plan detail is session-only, while
existing ActionHistory retains content-free invocation/interruption evidence.

Focused result: 74 passed across controlled plans, generalist plans, ToolExecutor,
desktop, working context and provider admission. Full regression/JS/CAP-34 are the
next acceptance gate. Do not claim full M4 acceptance yet. No live/paid provider,
owner file inspection or native hardware test was performed.

## M4 final checkpoint C and continuation

M4 is complete as a bounded offline-tested read-only engineering milestone.
Final evidence: **1082 Python tests run / 1078 passed / four skipped**, zero errors
or failures (134.979s); **12 desktop JS checks passed**; **CAP-34 174/174 per arm,
zero regressions**. Full suite was run once after checkpoint B stabilized. Evidence:
`.local/controlled-plan-full.log` and `.local/controlled-plan-evaluation/summary.md`.
The preview and execution checkpoints are c62d38d and fd4a0a3; this closeout commit
adds evaluation registration, frozen held-out planning cases and documentation.

Demo: `/plan workspace List the workspace, then read README.md and notes.md` uses
one fake FAST proposal in tests; preview performs no reads. The exact displayed
confirmation command plus separate existing operation approvals runs real registered
listing/reading handlers against temporary fixtures. Receipts prove validated bounded
returned snapshots and link to invocation history. They do not certify project
correctness, infer relevant files or authorize future actions. No results are sent
for cloud synthesis or promoted to permanent/working memory.

Changed implementation: iris/generalist/controlled_plan.py, iris/brain/engine.py,
iris/desktop/runtime.py, iris/tools/executor.py, iris/tools/models.py and
iris/generalist/evaluation.py. Tests: tests/test_controlled_plan.py and
tests/fixtures/controlled_plan_holdout.json. Updated design, evaluation, sprint,
capability tracker, backlog, validation and SECURITY.md document exact limits.

The experiment remains default-off. No owner files/settings/credentials were changed,
and `tatus -sb` retains its recorded hash. Main remains unchanged. Native startup/
reauthentication reliability and hardware acceptance remain unresolved. All detailed
plan state is session-only; restart invalidates authority. Existing content-free
ActionHistory retains invocation/interruption evidence but is not a durable plan journal.

Exact next milestone: M5 bounded recovery and persistent project continuity. Begin
with current Git status/log and this checkpoint, then inspect existing job/history
recovery before designing any persisted workflow journal. Keep exact operation
approvals, no blind replay of uncertain effects and explicit resource selection.
Do not add effectful tools or enable the interpreter automatically. An owner-approved
synthetic live-model benchmark remains a separate rollout gate. Focused command:
`python -m unittest tests.test_controlled_plan tests.test_generalist_plan tests.test_tools`.


## M4.5 continuation checkpoint — PARTIAL

Recovered clean M4 HEAD 129ddab; preserved the untracked `tatus -sb` unchanged.
Checkpoint A 2b86086 adds the isolated evaluation runner, development corpus and
10 focused tests. Follow-up expands to 26 cases / 27 turns, adds partial failure
and cancellation, and registers measurement tests with CAP-34. No owner data,
credentials, preferences, main or frozen holdouts changed. No inference network
requests were made. Real transport remains disabled even with `--mode real`.

Continue M4.5, not M5: implement and test explicit exact-provider/model/contact
consent, separately acknowledged unknown-cost risk or enforceable monetary ceiling,
persistent run admission, hard deadline/cancellation and no fallback/retry. Then
connect a later live run to the same synthetic fixtures without exporting answers
or expected labels. Add ordinary response/DEEP/Council measurements using existing
routing, human-review artifacts/rubrics, and context-expiry/UI-revision cases.
Do not mistake direct interpreter host rejection for a DesktopRuntime regression;
ordinary social conversation currently follows a different production path.

Acceptance is deliberately partial: no usable live-run command, live benchmark,
provider ranking or rollout recommendation is claimed. Native WebView2 startup/
reauthentication remains unresolved; this sprint does not alter it. M5 remains next
only after M4.5's remaining evaluation-readiness work is complete.


## M4.5 completion checkpoint A — durable admission

Added benchmark_admission.py, reusing ProviderUsage and the existing OpenRouter
transport. Consent binds exact model, synthetic scope fingerprint, call ceiling,
deadline and separate unknown-cost acknowledgment. Run policy and attempts persist;
changed policy, interrupted reservations or stopped runs cannot reset authority.
A bounded subprocess cancels the local provider worker; this cannot guarantee that
remote processing/billing stopped. The normal configured provider ledger is still
applied by the existing transport. Tests use fake workers and isolated ledgers only.
Eight admission tests passed. CLI integration/route/review acceptance is in progress;
no live request or owner credential lookup has been performed in development.


## M4.5 route/review checkpoint

2b32ff6: durable admission and bounded worker foundation.
fc986f0: explicit live preflight, ordinary FAST/DEEP/Council measurements and local
human-review workflow. Follow-up keeps the normal provider ledger session stable
across child adapters, verified with a mocked existing transport. No provider was
contacted. Focused acceptance: 25 tests passed; full evidence follows in VALIDATION.

31 development cases / 33 turns / 37 fake attempts. All fixture expectations met;
no real-model intelligence or human-quality score is accepted. Reserved holdouts
remain unchanged/unscored. Existing interpreter defaults, security origins, tools,
owner data, voice configuration and native fallback are unchanged.

Exact next action after engineering acceptance: owner review of EVALUATION.md's
three-call synthetic pilot, exact model and unknown-cost risk, then a separately
authorized run and human review. Do not run it automatically. M5 follows only after
these limitations/evidence are understood; M5 was not started. Native WebView2
reliability remains unresolved. No hardware acceptance is claimed.


### Final M4.5 acceptance and continuation

25 focused tests passed; 1107 Python tests run / 1103 passed / four skipped;
12 desktop JS checks passed; CAP-34 199/199 each arm, zero regressions. The last
stable-session fix was included in final full acceptance. Offline reports contain
31 cases / 33 turns / 37 fake attempts and four unscored ordinary-response records.
See VALIDATION.md for exact logs and EVALUATION.md for the complete pilot command.

M4.5 is closed as bounded benchmark-readiness infrastructure. Real-model quality is
not accepted. Do not execute the pilot without separate exact-target/scope/cost-risk
approval. No rollout or M5 work occurred. Next evidence gate is the approved tiny
pilot and human review; next development milestone is M5 bounded recovery/project
continuity, preserving the existing authority and privacy boundaries.


## M4.7 checkpoint A — diagnosis and minimal identity refinement

Recovered HEAD 4ad6302, only tatus -sb untracked. Canonical Personality is included
by compile_identity_prompt for every behaviour mode; IRISBrain.respond supplies it
to FAST/DEEP and Council candidate/critique/chair stages. interpret also includes it.
The model-only plan proposal uses the strict plan protocol; user-facing plan/receipt
text is host-generated, not a personality-synthesis path. The three missing addresses
in the historical pilot do not prove a missing prompt or establish a root cause.

The original wording made address use discretionary and did not specifically guide
casual topic transitions or avoid duplicating analytical prose/table content. Small
canonical identity additions clarify usual greetings/acknowledgements with sir,
recent-reply/urgent exceptions, short casual transitions and proportionate analysis.
No output postprocessor, new memory system, routing or tool change was introduced.

29 focused identity/personality/brain tests passed with fake providers and temporary
fixtures. A restricted-path Obsidian test first required the existing Windows test
execution context; no production path-security assertion was weakened. One new mode
fixture was corrected to use the router's existing read-file OPERATIONS trigger.
No inference calls were made. Cross-turn address avoidance remains a prompt preference:
bounded context may be absent, trimmed or cleared. Historical pilot files are intact.


## M4.7 checkpoint B — context and conversation evaluation

9c6eda8 adds an offline-only, separate ten-case conversation development set and
limited lexical oracles with negative examples. Existing WorkingContext now carries
assistant replies in the benchmark as model-inferred text, matching production's
bounded transient context. No second history store or persistent-memory change.
Thirty focused personality/evaluation/route tests passed; sets overlap checkpoint A.
Ten fake calls, ten expected outcomes and 40 lexical checks passed in the dedicated
report. Human scores remain null. Full acceptance evidence belongs in VALIDATION.md.

Production response paths use the same canonical identity, including Council's final
synthesis. Cross-turn style is not deterministic: context can be missing, expired,
trimmed or deliberately reset. The prior live pilot's absent honorific is not proof
of a missing prompt, and these synthetic checks do not establish real-model adherence.
No new live request was made; prior pilot files and frozen holdouts remain untouched.


### M4.7 final handoff

Offline refinement accepted: 1114 Python tests passed / four skipped (1118 run),
12 JS checks passed, CAP-34 213/213 each arm with zero regressions. See VALIDATION.md
for logs, checksums and limitations. d196c3a is the minimal canonical prompt checkpoint;
9c6eda8 adds context-discriminating offline evaluation and benchmark context fidelity.
The final closeout records acceptance only; no further live inference was authorized.

Next: owner review of wording and optional separately scoped live validation; the
next substantial development milestone is M5 Bounded Recovery & Persistent Project
Continuity. Do not activate experiments or infer real-model understanding from these
scripted tests. Preserve existing authorities and the unresolved native release gate.

## M5 checkpoint A — protected continuity foundation

Recovered 472ed5a, only preserved tatus -sb untracked. ActionHistory retains
bounded content-free invocation evidence; NotesJobs supplies account-bound DPAPI
patterns; TaskStore/GoalStore remain authoritative for their own records.
WorkingContext is ephemeral and must not be serialized. The missing abstraction
is a small encrypted project envelope, not another task or memory system.

ProjectContinuity adds at most ten explicit projects, 80-character titles,
400-character descriptions, five task ID/revision links and ten workflow summaries
of up to three steps each. Whole payloads use existing Windows DPAPI, verified
before transactional publication; no plaintext fallback. IDs alone remain plaintext.
Revision conflicts, unsupported schemas, decryption failures and redirected paths
fail closed. No live store is created by development tests. Seven synthetic store
tests pass. Runtime commands and workflow observer integration remain checkpoint B.

Project backups are not yet included in the portable backup allowlist. Copying
this protected store alone requires the original Windows account/machine recovery
material. No migration or silent backup-format change is made. Deletion removes
only continuity; SQLite secure_delete does not erase external copies/backups.

## M5 checkpoint B — integrated recovery (offline)

Protected projects are connected to the existing authenticated chat, TaskStore,
WorkingContext local-only reference and PlanRun/ToolExecutor/ActionHistory. The
synthetic lifecycle exercises actual workspace_list/workspace_read handlers on a
temporary README, exact confirmation and separately simulated operation approvals,
then a new DesktopRuntime: identity/evidence persist, old authority does not. Fresh
preview uses a new plan ID. No raw results are stored/exported. Cancellation, missing
history, task revisions, journal write failure, corruption, restart stage ambiguity,
concurrent revisions and real Windows DPAPI with synthetic payloads are covered.
The optional journal never replaces the existing executor or approvals.

45 focused tests pass (24 new project tests plus 21 existing controlled-plan tests).
Full acceptance is pending. No provider calls or owner-data edits. See DESIGN.md
for commands, retention, privacy, backup exclusion and bounded recovery semantics.

## M5 closeout

Full acceptance passed: 1,138 Python passed/four skipped (1,142 run), 12 JavaScript
checks, CAP-34 237/237 each arm with zero regressions. 24 continuity tests cover the
bounded lifecycle; 45 focused tests include the existing M4 authority cases. All
fixtures are synthetic, no real providers. See VALIDATION.md for exact evidence.

The supported slice is create/select project, explicitly link task identity, preview
and confirm existing read-only workspace steps, persist protected evidence, restart,
inspect verified/unknown/pending progress and request a fresh preview. Old approvals
never resume. Project deletion leaves tasks, goals and ActionHistory intact. Working
context has a private local-only reference; no cloud project understanding is claimed.

Next: explicit portable project backup/recovery remains a narrow readiness gap; the
handoff's next major intelligence milestone is M6, owner-approved measurement/rollout
review. Neither live evaluation nor rollout is authorized by M5 completion. Do not
repeat this sprint or troubleshoot native WebView2 as part of its continuation.

## M5.1 checkpoint A — portable project envelopes

Recovered 2be1504 with only tatus -sb untracked. Extended the existing archive v1
allowlist with projects.sqlite3. Exact project SQL schema/version, integrity, ten-row
limit and shared M5 envelope validation are enforced. Source DPAPI envelopes are
validated and rebuilt as portable JSON in a fresh in-memory SQLite snapshot. Restore
validates portable envelopes, protects them under the destination account, verifies
the roundtrip and builds a fresh protected database before writing any project file.
Rebuilding prevents plaintext remnants in SQLite free pages. No source writes.

Unknown fields/duplicate JSON fields and redirected paths are rejected. Existing
archives remain valid; older binaries reject the unknown projects store rather than
partially restoring it. Cipher/KDF/64-MiB database bound and CLI are unchanged.
40 focused tests passed: ten new portable-project tests plus six existing backup
and 24 continuity tests. Includes two synthetic account keys, real Windows DPAPI,
failed reprotection, schema/corruption, staging/no-clobber and source preservation.
Runtime recovery guidance and end-to-end restored workflow acceptance follow in B.

## M5.1 checkpoint B — recovery acceptance

Portable workflow test now backs up an explicitly selected synthetic project, task
revision and real registered workspace receipts, plus an injected interrupted stage.
A fresh DesktopRuntime after restoration has no selected project or active plan,
rejects the old confirmation and can generate a new fake-provider preview without
execution. Completed evidence is historical; interrupted work stays unknown. Clearing
history removes verified claims; missing/changed task records block execution.
Task/goal/notes-job compatibility, source preservation and deletion isolation pass.

45 focused backup/project tests passed; the two end-to-end recovery tests were rerun
successfully after adding interrupted/missing-task scenarios. /project recovery is
non-destructive guidance only and does not require unlocking a record. No live calls.
Full regression/JS/CAP-34 acceptance follows. Portable account switching is simulated;
actual Windows DPAPI is tested on this account, not across physical Windows accounts.

## M5.1 closeout — checkpoint C

Implementation remains at the verified A/B source checkpoints bb17a12 and 3f55177;
C records acceptance and the pending security/design/backlog notes without speculative
code changes. Full regression completed: 1,153 passed/four skipped (1,157 run), JS12
passed, CAP-34 252/252 each arm with zero regressions. Focused backup/continuity suite
has 45 passing cases. Exact evidence and limitations are in VALIDATION.md.

Portable protected project continuity is accepted offline. Recovery cannot select a
project, restore active plans or reuse approvals. Unknown outcomes stay unknown.
The archive is not a full laptop/vault/configuration backup. Physical Windows-account/
device transfer and abrupt power loss remain acceptance gates; RAM/pagefile and other
plaintext-store staging exposure remain documented. No live provider calls or owner
backup/restore occurred. M6 requires its own authorization and was not started.

## M6 checkpoint A — evaluation preparation, not live acceptance

Recovered 736f6e5 with only preserved tatus -sb untracked. Existing respond,
InterpretationV1, ProposedPlanV1, WorkingContext, ToolExecutor, Council and durable
admission remain the implementation. No default model, rollout or permission change.
Audit: response reviews existed, but plan field scores were calculated only after
host validation and route samples used different tasks. M6 scores raw parsed plan
capabilities/arguments/dependencies before host validation, with false observations
on parse failure. Host acceptance/plan validity remain separate rates. No overall
intelligence score is produced.

A separate 22-case/24-turn development corpus combines natural conversation,
context-dependent Java/SQLite references, ambiguous progress, topic changes,
interpretation and compound follow-ups, planning, adversarial/stale proposals,
identical-task FAST/DEEP/Council comparisons and a protected local project fixture.
Frozen holdouts and historical pilot files are unchanged. Comparisons and private
project context are explicitly offline-only. Existing M5/M5.1 contract suites retain
changed-task, missing-history, interrupted/restarted and approval-replay coverage;
those are host tests, not real-model project-understanding scores.

Seven new M6 tests plus 25 existing benchmark/admission tests passed (32 total).
Fake transport exercises the real CLI path; no real provider was contacted. Public
provider documentation was read without credentials. Source preparation is not
permission to make an inference request or enable the experiment.

## M6 checkpoint B — benchmark readiness

34 focused tests pass, including a fake-transport real-mode M6 CLI with the exact
five-attempt scope, prompt binding, durable admission and local raw-response review.
Direct evaluate() also refuses live execution/private-project/controlled-route cases.
The same-task offline route test counts FAST=1, DEEP=1, Council=5 attempts. Human
review records can be model-blinded without modifying responses or inventing scores.

Final offline development run: 22 cases, 24 turns, 28 fake adapter calls, zero external
calls; fixture expectations PASS, prompt boundary 28/28, lexical checks 45/45. One
real registered two-step synthetic workspace workflow completed offline. Semantic
counts include intentional adverse fixtures and are not intelligence scores. Full
report/review artifacts: .local/m6-offline. Exact proposed pilot, preflight hashes,
provisional thresholds, logging/billing risks and approval requirement are in
UNIFIED-INTELLIGENCE-2-EVALUATION.md. No live inference or rollout occurred.
