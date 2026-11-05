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
