# M6 narrow verification-status boundary — 2026-11-12

Pilot 004's conversational reply asserted successful verification without test
evidence. Unlike compound operations, that conversation path returned raw model
prose. The experimental desktop path now supplies a host response for a small,
explicit set of referential verification-status questions, including "Can I call
it verified now?", "Is the fix verified?" and "Has it been verified?".

The host says it cannot independently confirm verification from conversation alone,
distinguishes reported fixes from test results, and asks for the test and result.
It neither verifies the fix nor claims no test has ever happened. Request matching
is exact after case/punctuation normalization; quotes, negations, general questions,
account-verification requests and mixed action requests are not intercepted.

## Integration and limits

The existing experimental flag remains required. The normal auto conversation path
applies this only when no tool receipt or Council result is being handled; existing
receipt behavior is preserved. The contextual null-capability interpretation path
uses the same helper. No model claim can become positive evidence through this
helper. It is a conservative request-specific boundary, not a general hallucination
detector or a new verification service. Other phrasings and unrelated false claims
remain outside its scope. Default-off behavior is explicitly unchanged and tested.

Runtime history and transient context retain the returned host answer rather than
the unsupported claim. Host warnings retain host provenance; prompt guidance explicitly says they are not test receipts. No new raw-response store is added to production. Evaluation
continues to save the literal model response and run its original phrase/quality
checks before applying the host boundary. The report labels the host response
host_verification_boundary, so safer handling never improves model-quality scores.
There is no retry, additional model call, tool authority or automatic execution.

## Offline replay

The two saved pilot-004 conversational responses were replayed through the evaluator
under a blocked network boundary. Their response strings remain byte-for-byte
identical; the second host reply is now evidence-limited. Both observed verification
phrase checks still fail and fixture_expectations_met remains false. External calls
and tool attempts are zero. This is an offline reconstruction under new code, not
a new model result or an original UI recording. Artifact:
m6-followup-review/verification-boundary-replay.json in the current chat workspace.

## Validation

- 120 focused tests passed (12.240s).
- Full Python: 1198 run, 1194 passed, four skipped, zero failures/errors (192.332s).
- CAP-34: 293/293 per arm, zero regressions, PASS.
- All 12 desktop JavaScript checks passed; no native/hardware acceptance claimed.
- Six new tests cover narrow request scope, contextual application, actual desktop
  handling/history, default-off behavior and unrelated questions. The existing
  false-claim regression still asserts raw text is retained and model checks fail.
- All twenty original pilot files, frozen holdouts, main/origin-main and tatus -sb
  match preservation checks. All tracked Python bytes match tested source.

Verification used a fresh tracked-source-only copy, empty .local, isolated TEMP/TMP
and process-only cleared provider variables under the Windows user context. No
owner settings or credentials were copied. Artifacts: m6-boundary-final-verification in
the current chat workspace. git diff --check passed.

No new provider contact, rollout, model defaults, owner-data or credentials changed.
No real-model improvement is claimed; compound operation-selection errors remain.
Offline preflight only (not authorization):
scope 8869a74c5d2c94ddd0498e1b5fb7ac8d483525d785120e7ba9d90e99d2b99adf
prompt configuration fd21c9ec1864ffacac2fa1370991d37b3f43d5dd86eb8a7bd751ab0181ed59e7
Any new live run still requires separate scope/provider/billing-risk approval.
