# M6.1 — Contextual Reasoning and Tool Reliability

The objective is one reliably completed five-turn conversation. This first slice
defines offline acceptance checks; it does not demonstrate real-model intelligence.
Completed M6 work through aa37607 was pushed and remotely verified on the sprint
branch before starting this slice. Main remains unchanged.

## Scope and acceptance

1. Compound state: start the educational example, update to 8%, compare with the
   original 5%, show the difference, then reset. All five exact parameter states
   must match. The comparison ends at 2219.64 versus 1647.01 after ten years,
   using the existing monthly-compounding capability.
2. Deterministic capability selection: invented prose earns no calculation credit.
   Wrong operations, stale references and an incomplete five-turn run fail the
   whole sequence, even if the final reset recovers. Host safety is distinct from
   model correctness. There are zero workspace tool attempts.
3. Conversational context: a separate five-turn scripted regression retains the
   Java inventory file-saving owner anchor and reported code change. An explicit
   verification question receives the existing host boundary; no test receipt is
   invented. Raw model review and unreviewed human ratings remain separate.

The new corpus is offline-only. Seven new regressions use the existing evaluator,
context store, deterministic calculation and verification boundary. No runtime
feature, prompt, model default or rollout changes are included. Scripted replies
prove plumbing and rejection checks, not comprehension or general truthfulness.

## Validation

Validation results are recorded in VALIDATION.md. All twenty saved pilot artifacts,
three frozen holdouts, main and the unrelated `tatus -sb` match earlier hashes.
No new provider contact occurred. Previous live admissions remain consumed.

## Next sprint work

Broaden offline phrasing and ambiguity cases for this same conversation before
changing prompts. Diagnose operation selection and context use separately from
host handling. Do not loosen schema validation or turn generated text into receipts.
A future live benchmark needs a separately reviewed non-offline case selection,
fresh scope and prompt fingerprints, a new output directory, five attempts and
180 seconds, plus explicit approval of provider contact and residual billing and
privacy uncertainty. This document grants no live approval. No retries,
substitutions, Council, workspace execution or feature expansion are proposed.


## M6.1 phrasing and ambiguity coverage — 2026-11-12

Three new parameterized regressions exercise twelve five-turn variants: three
equivalent request sequences, six ambiguous/negated/quoted or underspecified rate
requests, and three model values differing from the owner's requested 8%.
Successful sequences require all five states. Rejected updates leave the rate at
5%; a later reset cannot erase the sequence failure. No workspace tools execute.
The scripted model supplies operations; these tests do not measure whether a real
model selects them correctly. No production code, prompt or fixture changes.

Validation: 130 focused tests passed in 15.247 seconds, including all ten M6.1
tests; desktop JavaScript 12/12 passed; diff whitespace check clean. The full
suite and CAP-34 results above belong to the preceding checkpoint and were not
rerun for this test-only addition. All twenty pilot artifacts, three holdouts and
the unrelated file retain their earlier hashes. No provider contact occurred.

Next: assess clarification quality and explicit recovery after ambiguity, keeping
host rejection distinct from task completion. Any live benchmark still requires
fresh scope/prompt fingerprints and separate provider/privacy/billing approval.
