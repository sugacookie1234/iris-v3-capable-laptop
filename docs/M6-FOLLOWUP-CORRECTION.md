# M6 follow-up offline correction

The second five-attempt pilot completed on 8387357 with partial improvement, not
quality acceptance: intent 1/2, capability 2/3 and exact arguments 1/3. The 8% update
reached host arithmetic; the original comparison still produced clarification.
Both conversations and the workspace preview remain non-executing. Raw model
numbers are not host calculation evidence. AI reviewer opinions remain separate
from original blank human review fields.

## Findings and changes

Current scenario parameters were serialized correctly. However, the structured
snapshot omitted the original educational baseline and monthly-compounding rule.
The original 5% rate was already specified in prompt prose and retained in host
compare/reset semantics: this was not complete loss of original state. The model
still chose null capability and described the current 8% as original. The fix adds
explicit original_parameters and calculation_convention to the public snapshot,
separate from current parameters. These describe existing fixed-default semantics,
not a new arbitrary history store or owner preference.

Comparison guidance now specifies compare_original with the current reference,
rejects differing principal/timing assumptions, and asks for operation-only prose
without invented numerical results. Host arithmetic, schema validation, authority
and clarification fallback are unchanged; no proposal is fabricated by the host.

Conversation references already reached the provider. The follow-up used the Java
referent on its second turn but still missed it on the first, and used internal
provenance terminology. Guidance now asks for a brief named referent, plain-language
testing evidence, and concise replies. Privacy filtering and provenance remain
unchanged. This is a prompt intervention, not demonstrated real-model improvement.

## Verification

- Focused: 68 passed, 3.187s, including three new regressions for actual two-turn
  provider context, detached baseline/expiry, and mismatched-principal refusal.
- Full Python: 1180 tests run in 132.220s; 1175 passed, four skipped,
  one environment error (missing disposable .local directory). After the contract
  runner created that directory, the single failed fake-transport test passed in
  0.157s. Thus all 1176 non-skipped tests passed across the full run plus targeted
  rerun, not a claim of a single clean full-suite run.
- All 12 desktop JavaScript checks passed; automated checks, not hardware acceptance.
- CAP-34: 275/275 in both arms, zero regressions, gate PASS. This compares
  offline contracts, not old versus new model intelligence.
- git diff --check passed. Both five-file pilot manifests, frozen holdouts and
  unrelated tatus -sb hashes match. main and origin/main remain unchanged.

Verification artifacts: C:/Users/Admin/.codex/.chatgpt-projects/g-p-6a648a58888481919a020c5609385722/m6-followup-verification
The disposable copy includes tracked source only and no owner configuration. All
tracked Python bytes were captured in source-python-sha256.json. Its local Git
commit is a disposable test snapshot, not a project commit. Tests used the existing
virtual environment, isolated TEMP/TMP and cleared process-only IRIS/OpenRouter/Fish
variables under the Windows user context. No owner credentials were loaded.

Initial restricted focused run: 68 tests, two failures and one error from workspace
access checks. First isolated run: 14 errors because Git metadata was absent.
Adding a local disposable Git snapshot resolved that requirement; no assertions
were weakened. Initial isolated errors remain in focused.log before the successful
run. Restricted failures are documented here from tool output.

## Remaining gates

No new provider calls, retries, substitutions, rollout, settings or owner-data
changes. Experiments remain default-off. Both original ledgers remain stopped.
There is no new real-model quality score. Any subsequent live run needs new scope
approval; the consumed five-attempt authorization cannot be reused.

Fresh offline-only preflight (not authorization):
scope 89d6f2374bccffc174edd28b08baf8d3de5279238d91369edca59704b7e2a91c
prompt 6a4cfd3dd85dcd57439a70f06c93ee9b1bb405eb2826686d17186f74abccecdf

Native/hardware acceptance and general intelligence remain unverified.
