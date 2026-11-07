# M6 verification-claim and calculation-sequence regressions — 2026-11-07

Pilot 004's complete schema masked two task failures: unsupported verification
prose reached the user, and a rejected 8% update left the later comparison at 5%
versus 5%. Per-turn intent/capability scores do not measure either outcome.

The development fixture now includes the two observed verification phrases in its
existing lexical avoids list. A regression replays the unsupported claim through
the fake-provider conversation path, confirms the raw and host text are preserved,
and asserts those phrase checks and fixture expectations fail. An honest response
passes. Human scores remain blank. This is a narrow lexical regression: quotations,
negations or different wording can produce false positives/negatives. It is not a
general truthfulness classifier and does not suppress or repair production replies.
The runtime unsupported-verification problem remains unresolved.

The two compound turns now have explicit expected calculation parameters. Each
must produce an accepted host calculation at the right state: rate 8 with no
comparison after update, then rate 8 compared with 5. A new case-level sequence
result requires every labelled turn to pass, and the fixture gate includes these
per-turn state outcomes. No calculation means failure, not an unobserved success.
Unlabelled cases have no sequence score. Existing semantic field metrics and
contract acceptance are unchanged.

Five new tests cover the observed false claim, honest fixture, successful full
sequence (2219.64 vs 1647.01), rejected update followed by accepted 5%-versus-5%,
and missing calculations plus exclusion of evaluator labels from provider prompts.
Expected outputs remain local evaluation data, never provider instructions.

## Retrospective audit

New development labels were applied separately to saved evidence under a blocked
network boundary. They are post-hoc analysis, not rewritten historical scores or
new model responses. Pilot 001 uses its labelled offline host reconstruction.

| Pilot | 8% update state | 8%-versus-5% comparison state | Sequence |
|---|---|---|---|
| 001 | fail | fail | fail |
| 002 | pass | fail | fail |
| 003 | fail | fail | fail |
| 004 | fail | fail | fail |

Pilot 004 matches the newly added false-verification phrases; absence in earlier
responses is not proof of truthfulness. All twenty original pilot files match
their before-analysis hashes. Raw artifacts, human scores and stopped ledgers were
not edited. No new model, provider, workspace-execution, retry or rollout activity.

## Validation

- Focused: 114 passed, 17.864s.
- Full Python: 1192 run, 1188 passed, four skipped; 156.867s.
- CAP-34: 287/287 baseline and
  287/287 candidate, zero regressions, PASS.
- All 12 desktop JavaScript checks passed; automated, not native acceptance.
- git diff --check passed; all tracked Python bytes match the tested source copy.
- Frozen holdouts, main/origin-main and unrelated tatus -sb unchanged.

Verification uses a fresh tracked-source-only copy with empty .local, isolated
TEMP/TMP and process-only provider variables cleared, no owner settings/credentials.
Artifacts: m6-outcome-verification in the current chat workspace. The separate audit
is m6-followup-review/outcome-regression-audit.json. All model transports in the
targeted regressions are fake and the saved-response audit blocks network.

## Scope and limitations

Only evaluation/reporting, development labels and tests changed. No production
prompt, parser, runtime safeguards or model default changed. No real-model gain is
claimed. The development case fingerprint changes because expected labels changed;
this must be disclosed for future comparisons. Frozen holdouts are untouched.

Fresh non-contacting preflight:
scope 217f48525e614bf96f6dbb82168b5f8afcaddc3027c6ab7baa3992c0aad3e053
prompt configuration 7def8b056cc8246a7a93fab195659639f3099c39f5262ac0a48fc99cc5d237d8

The conservative prompt fingerprint covers evaluator source even though provider
prompt text is unchanged. No fifth pilot is authorized or started. Prior approvals
are consumed. Future live testing requires fresh explicit scope and risk approval.
