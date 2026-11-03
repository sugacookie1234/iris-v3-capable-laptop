# Evaluation + Business OS handoff

Development branch: `sprint/evaluation-business-os`. Do not merge main without
owner approval. Starting revision: `b4e5c96`; evaluation foundation: `8fc9499`.

## Implemented boundaries

- CAP-34 first offline contract gate: same synthetic cases in baseline/candidate,
  guidance ablation, source/corpus fingerprints, machine/readable reports, zero
  tolerated failures/regressions and no promotion. See OFFLINE-EVALUATION.md.
- CAP-28 first local feasibility workspace: supplied evidence, decimal economics,
  durable reviewed input revisions, comparison UI and privacy-safe receipts.
  See BUSINESS-WORKSPACE.md. Autonomous business operation remains unimplemented.
- CAP-33 owner review and stored data preserved. No broad memory promotion.

## Next work in priority order

1. Review this branch and perform native UI acceptance before approving a merge.
2. Business data lifecycle: project/evidence removal, local export and import,
   encrypted backup/recovery, more actionable field-level form validation.
3. Explicit evidence-to-cost provenance, dates/staleness, contradiction review and
   supplier MOQ/payment/fulfilment contracts. Never infer these from prose.
4. Frozen holdout evaluation with real typed candidate adapters. Score tool-choice,
   source errors and permissions as distinct observable events; benchmark latency
   separately from deterministic result files. No LLM quality improvement proven.
5. Authorized read-only research adapter using existing research permissions and
   established background job controls; budgets/cancellation and source snapshots.
6. Scenario model: partial sell-through, MOQ, inventory timing, storage/returns,
   tax/duty inputs and working capital. Keep net-profit claims qualified.
7. OMEN real-room microphone/voice/tray acceptance; Twilio setup remains separate.

Recommended next major sprint: **evidence-backed business research and data
lifecycle**, after review of the current local feasibility foundation. Defer
Shopify writes, spending, supplier commitments, automated messages and generic
agent delegation until exact authority, recovery and evidence contracts exist.

## Known limits

The evaluation corpus is a regression contract suite, not a hidden benchmark or
measurement of general intelligence. Reviewed memory currently changes explanatory
guidance, not plans; no correctness improvement is demonstrated. Business source
verification and external connectors are absent. Business storage is local
plaintext, bounded and indefinite; deletion UI remains outstanding. UI checks are
automated DOM tests, not a human visual/accessibility acceptance review.
