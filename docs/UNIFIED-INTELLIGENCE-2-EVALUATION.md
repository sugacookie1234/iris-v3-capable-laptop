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


## M4.5 checkpoint A — offline intelligence measurement foundation

`python -m iris.generalist.intelligence_evaluation` uses a separate 24-case,
25-turn synthetic development corpus and the real IRISBrain interpretation/plan
interfaces, validators, WorkingContext, ToolExecutor, ActionHistory and provider
admission ledger. A two-step workflow executes registered listing/reading handlers
against disposable files; confirmations and per-operation approvals are simulated.
No owner settings, workspace, credentials or provider ledger are loaded.

Metrics separate semantic field matches, host acceptance, plan validity, verified
completion and expected security outcomes. Fixture failures are deliberately present;
there is no combined intelligence pass percentage. Raw output and private context
are not written to reports. Missing token usage is unknown, not estimated. Reports
include individual timings, commit/corpus fingerprints and hashes of untouched,
unscored holdouts. Conversational quality/unsupported claims still require human
review. This is a direct contract probe, not full DesktopRuntime chat routing.

Checkpoint A focused validation: 10 tests passed (synthetic only). Real mode fails
closed before loading accounts or contacting providers. Live authorization/bounded
transport and DEEP/Council measurement remain unfinished; M4.5 is PARTIAL. No usable
live-run command is claimed at this checkpoint. Default-off settings are unchanged.


### Expanded offline checkpoint and reproducibility

Run from the repository:

```powershell
.\.venv\Scripts\python.exe -m iris.generalist.intelligence_evaluation --mode offline --max-calls 64 --duration 120 --output .local/intelligence-evaluation
```

26 development scenarios / 27 turns: conversation (3), topic (1), interpretation
(2), ambiguity (3), context (3, including a two-turn shared scenario), tools (1),
adversarial (4), failures (3), planning (6). Frozen holdouts are hash-read only,
never loaded as cases. The corpus fingerprint is recorded in results.json.

Observed fake-output field matches: intent 16/18, capability 21/23, arguments
21/23, context 15/18; correct clarification form 3/3. Host accepted 14/27 proposals;
5/6 plans validated. One of four execution scenarios completed both steps; the
other three intentionally test approval denial, cancellation and a missing second
file. Their expected outcomes all matched. Security expectations passed 12/12;
27/27 prompt checks passed. All 27 adapter attempts were local fakes, zero external
requests and zero actual spending; provider token counts remain unknown.

These mixed positive/negative fixtures are NOT a representative success-rate
estimate. Parse failures lower semantic field-match counts; safe host rejection
never turns a malicious proposal into model correctness. Unsupported claims and
naturalness remain unscored/human-review-required. Plan validity is not objective
completion. Receipt verification only covers returned snapshots, not project quality.
The JSON artifact includes per-turn outcomes, explicit denominators, individual
latencies and attempt states; no percentile claims or actual billing inference.

### Remaining live gate and proposed first pilot (not authorization)

There is no executable live-benchmark command yet. The following safely proves
that the current entry point refuses real mode:

```powershell
.\.venv\Scripts\python.exe -m iris.generalist.intelligence_evaluation --mode real
```

Expected: exit 2, no account lookup or provider request. Do not remove this refusal
until exact target, explicit contact approval, resource/cost bounds and cancellation
have adversarial tests. Proposed first owner-reviewed pilot: one exact current FAST
provider/model confirmed by the owner, three adapter attempts, 120 seconds, monetary
ceiling CAD 0 unless reliable pricing enforcement or separate unknown-cost approval
is available. No claim is made that a model labelled free meets that ceiling.
A final usable command and provider/model identity remain required before execution.

Rollout hard gates: no unauthorized effects/private export, existing authentication
and approval regressions passing, current context validation, malformed proposals
failing safely, durable quotas/cancellation, honest receipts, legacy/default-off
availability and explicit owner activation approval. Suggested quality target for
review, not project policy: at least 90% supported intent/capability/argument matches
on a sufficiently sized unseen synthetic set, with every safety failure investigated.
No rollout is supported by the current fake-provider measurements.


## M4.5 completion — benchmark readiness (supersedes partial transport notes)

The live entry point now uses benchmark_admission.py and the existing
OpenAICompatibleProvider/OpenRouter transport. No new HTTP client, fallback, retries,
model router, owner tool permissions or experimental default is introduced.

**Admission:** explicit real mode, exact OpenRouter model, explicit case IDs and
matching scope SHA256, contact consent, separate unknown-cost consent, 1–100 actual
adapter attempts, a duration of at most 600 seconds, a dedicated `.local` directory,
and an explicitly supplied IRIS_BENCHMARK_API_KEY are required. Other providers and
wildcard models fail locally. Model availability is not asserted without a live run.
The configured owner ProviderUsage restrictions still apply in addition to the run
ledger; all child adapters share a stable benchmark session. Existing owner quota
policy and credentials are never changed. The benchmark key is not written to disk.

SQLite binds immutable consent/deadline and atomically accounts attempts. Restart
cannot reset the budget. Interrupted reservations block automatic recovery; stopped
or completed runs cannot be reopened. A failed provider attempt stops the run.
Council fan-out uses the same gate for every candidate, critique and chair call.
The bounded subprocess is terminated on cancellation/deadline; remote processing or
billing may continue. A killed transport can leave a normal-provider reservation
pending: inspect it using the existing owner-controlled recovery procedure; never
clear it automatically. Local deadline enforcement includes bounded worker cleanup
(up to two seconds), not a promise about remote cancellation or bill finalization.

**Cost:** no monetary ceiling is claimed. This transport does not supply verifiable
billing/pricing. A model ending in `free` is not treated as free. The separate
unknown-cost flag acknowledges residual financial exposure, while call/time limits
remain enforced. Token counts are reported only when observed, with observation
counts. Unknown tokens/cost are not inferred from success. Adapter attempts can
include pre-network failures; actual HTTP call counts remain unknown in live reports.
Generation settings are adapter-request settings; existing transport adjustments
(e.g. model-specific token limits) still apply.

**Scope:** live pilot accepts synthetic ordinary-response, interpretation and plan
preview cases. Deliberate provider-fault/adversarial-output fixtures and confirmed
workspace execution fixtures stay offline. Offline actual-handler execution remains
covered. Response quality uses IRISBrain.respond with production routing and no
executor; no generated tool request can execute through that interface. Structured
proposals use existing validators. Exact owner authorization remains necessary for
any future expansion. All selected reasoning roles use the explicitly chosen model;
this is a bounded single-target comparison harness, not a silent copy/change of the
owner's multi-model defaults. Routes use appropriate different tasks and are not
ranked as if those tasks were interchangeable.

**Coverage:** 31 development cases / 33 turns; 37 fake adapter attempts. FAST ordinary
conversation and an explicit topic transition, DEEP analysis and existing two-seat
Council are exercised. Council makes five calls (two candidates, two critiques, one
chair). Additional stale UI revision and expired-context fixtures fail safely.

Final offline field matches: intent 18/20, capability 23/25, arguments 23/25,
context 17/20, abstention 4/4. Host acceptance 18/33; plan validity 5/6; verified
completion 1/4 deliberately mixed execution cases. Security expectations 13/13;
prompt checks 37/37. Fixture expectations all met, not an intelligence pass rate.
Real-model metrics remain unavailable. CAP-34 remains a separate contract ablation.

### Local human review

Each run writes `review.json` beside the content-free aggregate report. It contains
synthetic requests/context, actual route/model, response hash, Council candidates
and critiques, blank scores, reviewer identity, notes and declared blinding status.
Current records are model-labeled, not blind. Do not commit raw review artifacts.
There is no hidden LLM judge. All generated scores are null/unreviewed.

Eight dimensions use explicit 0–4 anchors: relevance, context, naturalness, grounding,
uncertainty, conciseness, clarification and unsupported-claim avoidance. Leave an
inapplicable dimension null and explain why. Reviewers edit scores/name/notes locally;
never edit the hashed response. Validate and summarize a completed review with:

```powershell
.\.venv\Scripts\python.exe -c "import json; from iris.generalist.benchmark_review import assess; print(json.dumps(assess(json.load(open('.local/benchmark-readiness-offline/review.json', encoding='utf-8'))['records']), indent=2))"
```

This is human judgment with observed denominators, not task verification or proof of
naturalness. Expected labels, case IDs, hidden scoring fields and rubric instructions
are not included in model requests. Only synthetic task inputs and filtered host
context enter prompts. No private owner workspace/database is loaded by the harness.

### Proposed first pilot — requires separate owner authorization

Proposed scope: ordinary-fast + ordinary-deep, **three underlying attempts**, **120
seconds**, OpenRouter, one exact owner-confirmed model. The existing source includes
`nvidia/nemotron-3.5-lightning:free`; this is a candidate identifier, not a verified
current configuration, availability check or zero-cost promise. Owner must approve
that exact target and explicitly accept unknown monetary exposure before execution.
No live pilot was authorized or performed during development.

First inspect scope without credentials or network activity:

```powershell
.\.venv\Scripts\python.exe -m iris.generalist.intelligence_evaluation --case ordinary-fast --case ordinary-deep --preflight
```

Current scope SHA256:
`30d12880e44f4f07f823bc42a10d0543c216aa958c56a2fa876a4b68a5e648f3`.
If it changes, review and reauthorize the changed scope rather than copying a new
hash blindly. Set IRIS_BENCHMARK_API_KEY privately in the launch environment; do not
paste it into a command, repository file or report. After separate authorization,
the complete command is:

```powershell
.\.venv\Scripts\python.exe -m iris.generalist.intelligence_evaluation --mode real --provider openrouter --model nvidia/nemotron-3.5-lightning:free --case ordinary-fast --case ordinary-deep --scope-sha256 30d12880e44f4f07f823bc42a10d0543c216aa958c56a2fa876a4b68a5e648f3 --max-calls 3 --duration 120 --authorize-provider-contact --acknowledge-unknown-cost --output .local/approved-pilot-001 --preflight
```

This exact command still makes no call because it ends in `--preflight`. Only after
owner approval, remove that final flag to execute. Use a new dedicated result folder
for a separately approved run; never delete a ledger to reset admission. Ctrl+C
cancels local processing and records interrupted/billing-unknown evidence. Council
requires its own later scope/budget approval; three calls cannot complete five stages.
Readiness does not authorize activation of experimental intelligence. Existing
security hard gates and owner rollout approval remain mandatory. Native reliability
and hardware acceptance remain unresolved; M5 is not part of this sprint.
