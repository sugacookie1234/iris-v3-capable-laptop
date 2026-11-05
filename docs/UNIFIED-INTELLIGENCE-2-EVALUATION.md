# Semantic interpretation evaluation — 2026-11-05

## What the evidence measures

Development fixtures: `tests/test_interpretation.py` has 21 test methods covering
strict parsing, malicious/unknown capabilities, forged authority, context expiry and
revision mismatch, numerical grounding, compound/UI shared state, original reference
resolution, social response routing, permissions, private history isolation,
no-retry failures and default-off legacy behavior. Tests use fake model responses;
they measure host behavior given a proposal, NOT live intent classification accuracy.

`tests/test_interpretation_provider.py` has two additional tests. One exercises the
real provider admission wrapper with a temporary SQLite ledger and a fake failing
transport: one failed attempt consumes capacity and a restarted ledger denies the
next attempt before transport. The other verifies turn-lock release on cancellation.
These measure request admission, not token usage, financial billing or provider uptime.

CAP-34 includes the 21 interpretation tests. Provider-wrapper tests run separately
and in full discovery because CAP-34 intentionally blocks actual provider.generate.
The paired CAP-34 arms remain regression/experience-guidance ablations, not a
legacy-versus-semantic model-quality comparison. Both run the same contract corpus.

## Separate holdout

`tests/fixtures/interpretation_holdout.json` reserves ten synthetic prompts covering
social conversation, speculative grades, unseen paraphrases, ambiguity, read-only
requests and injection. They are not inserted into runtime prompts or development
test responses. They have NOT been evaluated against a real model. No accuracy,
precision/recall, live latency percentile or hallucination-rate claim is made.
Some deliberately exceed the first slice's conservative eligibility; report host
abstention separately from interpretation quality instead of treating it as success.

For an owner-approved later benchmark, record model/version/configuration, target
capability and argument correctness, abstentions, unsupported claims, reference
resolution, host denial and calls separately. Freeze the holdout before that run;
do not tune prompts on its results. Use only synthetic context and an explicit call
budget. No paid or assumed-unlimited free endpoint may be used without approval.

## Validation record

- Focused existing + new contracts: 41 passed.
- Interpretation plus provider wrapper: 23 passed.
- Desktop JavaScript: all 12 checks passed, including standby, safe visual sinks,
  stale revisions and renderer readiness. These are simulated checks, not hardware.
- Full Python: 1041 run, 1037 passed, four skipped, zero failures/errors (118.233s).
- Expanded CAP-34: 133/133 each arm, zero regressions, PASS.

Holdout SHA256: `0A12CD2FD985095C7C371498DD9F77DF915F9BC2291C67AC453CBD5A72BA2A3C`.

Native stress remains FAILED from stabilization; not rerun or repaired here.
The HP OMEN, actual microphone and real model quality remain unverified in this sprint.

## M3 context evaluation

Twenty new deterministic test methods in `tests/test_working_context.py` exercise
bounded topic retention, provenance, expiry/clear/restart, live scenario revisions,
assignment continuity, topic transitions, multiple possible referents, forged IDs,
UI-to-conversation state, private/retrieved-content exclusion, implicit-vault and
organizer filtering, tool-result isolation, cancellation and unavailable-context
fallback. FAST/DEEP/Council use the same filtered view without routing changes or
an extra ordinary-turn inference. Conditional rate edits still require explicit
rate units and an exact owner-provided numeric value; unrelated quantities are refused.

Focused context + M1/M2 + routing/authority suite initially passed 62 tests. Final
targeted context, interpretation and provider suite after rate-unit and deterministic
lifecycle hardening: 43 passed. These overlap. Lifecycle coverage verifies open,
close, reopen, pause, resume and cancel without invoking the model.
The full suite and expanded CAP-34 results are recorded in VALIDATION.md.
CAP-34 now includes the working_context category; its two arms remain contract
regressions, not a model intelligence comparison. No paid/live provider was called.

Five reserved multi-turn cases in `tests/fixtures/working_context_holdout.json` have
NOT been scored or inserted into prompts. SHA256:
`64752F121CC264CED84B1CEEAD204D59337F6455F0F7750EC1B9B2B0B784D874`.
The M1/M2 holdout retains its recorded hash unchanged. Real-model coherence, novel
paraphrases, topic-change detection and latency distributions remain unverified;
the test suite does not substantiate a general conversational-intelligence claim.

Final M3 acceptance: 1061 Python tests run / 1057 passed / four skipped; 12 desktop
JS checks passed; CAP-34 153/153 each arm, zero regressions. See VALIDATION.md for
exact log paths and which earlier runs were superseded by the final hardening fixes.

## M4 bounded planning evaluation

`tests/test_controlled_plan.py` exercises strict proposals, registered schemas,
three-step limits, dependency cycles, unknown fields/capabilities, authority forgery,
prepared argument snapshots, exact confirmation, permissions, stale context/expiry,
replay and concurrent consumption, cancellation, failed dependencies, malformed
success data, timeout, audit failure, restart invalidation and private-output isolation.
The two-/three-step demonstrations run actual workspace_list/workspace_read handlers
against temporary synthetic files, with mocked owner approval and model proposals.
These are genuine handler executions but not a real-model planning benchmark.

Checkpoint A: 14 focused tests passed. Checkpoint B: 74 focused tests passed across
controlled/generalist plans, ToolExecutor, desktop, working context and provider
admission. Sets overlap. Full acceptance counts appear in VALIDATION.md.
Five new reserved cases in `tests/fixtures/controlled_plan_holdout.json` are unscored,
not runtime examples; previous holdouts remain frozen. No live model/provider call,
owner file access, paid request or hardware acceptance occurred.

Final M4 results: 1082 Python tests run, 1078 passed, four skipped; 12 desktop JS
checks passed; CAP-34 174/174 each arm, zero regressions. Twenty-one planning test
methods were added. The reserved planning holdout hash is recorded in VALIDATION.md.
