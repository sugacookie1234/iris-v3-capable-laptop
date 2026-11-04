# Evaluation + Business OS handoff

## Visual sprint continuation checkpoint

CAP-37 first slice adds version-1 bounded line-chart data, deterministic monthly
compound interest (end-month contributions), and text-safe SVG/table rendering
inside ordinary chat. Ask “Explain compound interest”. Default scenario: 1,000
units, 5% nominal annual rate, ten years. No fees/taxes or return forecast.
Not yet implemented: adjustable controls, animation, bar/comparison/timeline
renderers, point focus/hover and full renderer DOM tests. CAP-38 decision cards
have not been implemented. Continue with chart controls and renderer tests, then
decision state/authority isolation, before business integrations and lifecycle.
The native process has not been restarted for this slice; do not claim live UI
acceptance. Existing owner data and pending review decisions were not touched.

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

Security priority checkpoint: see SECURITY.md. HTTP framing, duplicate headers/JSON, loopback binding and bounded workers hardened. Native/browser session bootstrap remains open; do not treat loopback cookies as protection from same-user malware. Continue with bootstrap design and endpoint quotas before broader autonomy.

Conversation sprint checkpoint: see CONVERSATION-SPRINT.md for implemented natural app aliases, safe educational follow-up context, backend clock answers, conservative speech formatting and irrelevant-note suppression. Separate native Visual Workspace, automatic research budgets and broader context correction remain unfinished. Do not touch microphone-device matching during this sprint.

Security continuation: see SECURITY-CONTINUATION.md. Prioritise provider-level durable budgets, portable authenticated-encryption backups, native pairing acceptance and supply-chain/phone review before full Visual Workspace. Current request limits do not cap Council fan-out or survive restart.

Current security checkpoint: SECURITY-CONTINUATION.md (implementation through 41c0c91). Continue standalone provider budget injection and backup inclusion/recovery acceptance before the next feature sprint. Desktop/phone launcher budgets and encrypted database recovery are now implemented; earlier entries describing them as entirely absent are superseded.

Unified foundation continuation: user authorised and implemented the local compound-interest orchestration slice after default provider enforcement. See ORCHESTRATION-SPRINT.md and the updated SECURITY-CONTINUATION.md. Next: native acceptance and carefully scoped verified-result context; retain existing approvals and private-data boundaries. Separate native Visual Workspace remains deferred.

Native workspace checkpoint (supersedes the deferred status above): CAP-37 now has
an authenticated secondary native window, shared revisioned parameters, conversational
controls and UI-to-host updates. See VISUAL-WORKSPACE-SPRINT.md for actual local
WebView2 smoke evidence. Remaining acceptance: physical keyboard, microphone/audio
continuity, target OMEN, multi-monitor and prolonged session expiry/reopen. Broader
business, private-data and decision integrations remain outside this sprint. Do not
infer that the historical organizer warning was reproduced or resolved.

Owner's 1:44 PM continuation order: finish Native Visual Workspace acceptance and
closeout, then dedicated security penetration-testing/red-team assessment in a
disposable environment, then Unified Intelligence 2.0. No later milestone is part of
this native-workspace sprint. Ordinary automated tests are not red-team completion.


Security assessment completed bounded HTTP/browser/source/advisory passes; see
SECURITY-PENTEST-REPORT.md. High visual credential-scope finding repaired. Follow-up
release gates: owner-controlled pip update (Windows access denied), intermittent
native asset loading, long-session and OMEN acceptance, transitive hash locking,
whole-source indirect injection coverage and plaintext-data lifecycle. No external
security certification. Next major feature remains Unified Intelligence 2.0 after
these release risks are reviewed; no broader controls/connectors were enabled.
