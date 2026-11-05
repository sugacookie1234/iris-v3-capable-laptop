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
