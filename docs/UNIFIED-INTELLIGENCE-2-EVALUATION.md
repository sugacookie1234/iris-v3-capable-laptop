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
