# CAP-34 offline contract evaluation

From the repository in Windows PowerShell:

```powershell
.venv\Scripts\python.exe -m iris.generalist.evaluation --output .local/evaluation
```

The runner produces `results.json` and `summary.md`; exit status is 1 on any
failed/error/skipped contract, unmatched case set, failed preview experiment or
regression. All cases are mandatory, with zero permitted regressions and at least
30 required cases. Run from a full source checkout including `tests/`.

The corpus reuses the independently asserted existing planner, router, notes
executor and experience-store tests. It includes dependency order, unknown tools,
permission/origin rejection, injected instructions, malformed reads, source
revision changes, partial coverage, cancellations, expired budgets, incorrect
experiences, stale reviews, restart, forgetting and privacy boundaries. Each test
method is one case; its parameterized subcases are not inflated into extra cases.

Both arms run the same contracts. Baseline disables reviewed guidance at the
desktop preview integration; candidate retains the current implementation. Store
review/retention behavior and fixed execution safety remain enabled in both arms.
A separate paired synthetic preview probe seeds the same reviewed partial result
in disposable databases and checks the actual runtime integration. No real owner
memory is accessed or approved. This ablates guidance, not the permission checker
or the already-established fixed recipe.

Reports include source/corpus fingerprints, per-case results, category failure
counts and regressions. Timing is deliberately excluded from reproducible outputs;
this is a correctness gate, not a latency benchmark. Test error details remain out
of reports; rerun the named failing unittest for its traceback. Network connects
and provider generation in the curated in-process corpus are rejected. Fixed
local tool subprocesses execute only the existing notes adapters; this is not an
OS sandbox for arbitrary third-party test plugins. Do not load untrusted modules.

Initial foundation: 59/59 cases in each arm. The business-expanded corpus has
70 cases per arm, including eleven cost, evidence and persistence scenarios.
Both runs have zero regressions. Reviewed guidance adds
a coverage caution but leaves the executable plan unchanged. **No task-correctness
improvement is demonstrated.** These fixtures do not measure LLM reasoning quality,
live research truth, general-agent performance or holdout generalization. Future
candidate routing requires a frozen holdout before any promotion; this command
never promotes or modifies production behavior.
