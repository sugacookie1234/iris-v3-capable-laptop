# M6 pilot 003: offline schema diagnosis

Pilot 003 completed all five authorized attempts but failed quality expectations.
Its 8% update omitted required `context`; its original-comparison proposal omitted
required `text`. Both were valid JSON but invalid InterpretationV1 objects. No host
calculation resulted. Original replies, scores and ledgers remain unchanged.

Saved-response analysis under the network-blocking offline boundary confirms:

| Pilot / compound turn | Strict parse | Missing field | Raw intent/capability/arguments/context matches |
|---|---|---|---|
| 001 / 1 | pass | none | false / false / false / true |
| 001 / 2 | pass | none | false / false / false / true |
| 002 / 1 | pass | none | true / true / true / true |
| 002 / 2 | pass | none | false / false / false / true |
| 003 / 1 | reject | context | false / false / false / unobserved |
| 003 / 2 | reject | text | true / true / true / true |

These are partial-field observations against the existing fixture, not new
contract scores, task completion or authority. Pilot 003's failed first update
left the scenario at 5%, so the second turn does not establish a successful
8%-versus-5% comparison even though individual fields match the fixture.

The evaluator now records `raw_interpretation_observations` separately from
contract metrics and exposes them in its Markdown summary. Missing fields are
distinct from explicit null. Unknown fields are counted without echoing their
names or values. Duplicate fields, malformed/non-object JSON, oversized input,
excessive nesting and non-finite numbers are left unobserved. Type-sensitive
diagnostic equality distinguishes bool from number; production metric behavior
is unchanged. No incomplete response is repaired, resubmitted or accepted.

Four new regression tests cover missing-text rejection with retained partial
evidence, missing-context versus null, malformed/ambiguous input, and no arbitrary
content echo or boolean coercion. Existing contract acceptance and raw artifacts
remain independent of these diagnostics.

No production prompt, parser, host fallback, provider transport, settings, owner
data or model defaults changed. This corrects measurement visibility; it does not
claim to fix model reliability. The latest sample is insufficient to identify why
the model omitted fields or whether the prior prompt change caused regression.
Do not weaken validation to make this pilot pass.

The conservative prompt-configuration fingerprint includes evaluator source, so
this reporting-only change also invalidates previous authorization fingerprints:

scope `335212c657ba1773cb9698476d6ee352ce0fc5496a41abd29153e2fd074b3d81`

prompt configuration `ba0212c6dcf3b989d30300b3db3ebf6304e0f982c3fcf3820862fb5c4421d42a`

No fourth pilot is authorized or attempted. All three consumed pilots remain
stopped. Native/hardware acceptance and real-model reliability remain unresolved.


## Verification and preservation

- 106 focused tests passed (14.738s), including four new diagnostic regressions.
- Full Python: 1184 run, 1180 passed, four skipped, zero failures/errors (195.043s).
- All 12 desktop JavaScript checks passed (automated, not native acceptance).
- CAP-34 baseline: 279/279 passed.
- CAP-34 candidate: 279/279 passed.
- CAP-34 gate PASS, zero regressions. These are contract checks, not model quality.
- Final source's four diagnostic tests passed again (0.264s).
- All fifteen pilot files match preserved SHA256 manifests, all three admission
  ledgers remain stopped, frozen holdouts and tatus -sb unchanged, main/origin-main
  unchanged. No fourth model run, retry, repair, workspace execution or rollout.

Tests used a fresh tracked-source-only copy with empty .local, isolated TEMP/TMP,
and process-only IRIS/OpenRouter/Fish variables cleared. No saved owner settings
or credentials were copied. Full suite and CAP-34 ran in the Windows user context.
Artifacts are in the current chat workspace under m6-schema-verification; the
network-blocked saved-response analysis is m6-followup-review/schema-replay.json.
The disposable tree has its own Git snapshot, not a project commit.

One unrelated error-message dash was restored after the full-suite source copy
was made (Windows text decoding had changed it). Byte comparison found no other
Python differences; the final four-test diagnostic rerun passed. No executable
behavior or prompt changed in that restoration. The earlier edit attempt was not
executed because automatic approval review encountered a usage limit; a later
review approved the repository edit. No approval bypass was used.
