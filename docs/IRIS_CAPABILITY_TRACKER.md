# I.R.I.S. v3 — Capability & Delivery Tracker

> **Tracker version:** 0.1.0-draft · **Baseline date:** 2026-10-28 · **Reference commit:** `9db02a7e9b3ed9dcc4e28dc64270a802cbe4ad28`  
> **Source of requirements:** [Master Design](IRIS_MASTER_DESIGN.md). **Source of validation:** test logs, linked commits/PRs and [`VALIDATION.md`](VALIDATION.md).  
> **Rule:** Repo-reported != automated-test-verified != owner live-verified. Update evidence before advancing a status.

## Status vocabulary

| Status | Meaning |
|---|---|
| `IDEA` | Proposed but not accepted into scope. |
| `DESIGNED` | Requirements drafted, no implementation claim. |
| `REPO-REPORTED` | Documented and/or source present; current test not rerun by this design review. |
| `IN-PROGRESS` | Active implementation branch/PR, not yet accepted. |
| `TESTED` | Identified automated tests passed against a pinned commit; external/hardware acceptance not necessarily done. |
| `LIVE-VERIFIED` | Specified real-provider/actual-device acceptance passed and evidence recorded. |
| `BLOCKED` | Dependency or permission prevents work; record blocker. |
| `DEFERRED` | Deliberately excluded from the current milestone. |

Do not use a single ambiguous “done” marker. `TESTED` and `LIVE-VERIFIED` require date, exact commit and evidence URL. Mixed-feature modules remain in `REPO-REPORTED` until each acceptance condition is satisfied.

## Capability matrix

| ID | Capability | Baseline (2026-10-28) | Next target | Acceptance evidence needed |
|---|---|---|---|---|
| CAP-01 | Conversational identity and modes | REPO-REPORTED | M0 | Confirm introduction/source sync, follow-up handling and non-fabrication tests |
| CAP-02 | Model router: FAST/DEEP | REPO-REPORTED | M0 | Current route/provider tests, latency and fallback errors |
| CAP-03 | LLM Council | REPO-REPORTED | M0/M7 | Distinct model IDs when claimed; partial failures; live budget-aware Council |
| CAP-04 | Persistent approved memory | REPO-REPORTED | M1 | Review/edit/delete/restart/privacy tests |
| CAP-05 | Obsidian/local notes | REPO-REPORTED | M1 | Scoped reads/writes; vault path and rollback acceptance |
| CAP-06 | Windows desktop HUD & tray | REPO-REPORTED | M0/M2 | Actual OMEN UI/tray acceptance; visible truthful states |
| CAP-07 | Double clap + voice conversations | REPO-REPORTED | M2 | ≥100 real-room trial matrix; measured false positives/misses |
| CAP-08 | Fish Audio + Whisper fallback | REPO-REPORTED | M0/M2 | OMEN microphone, playback, local fallback and cost handling |
| CAP-09 | Local tasks, goals, reminders | REPO-REPORTED | M0/M1 | Current automated suite + desktop notification acceptance |
| CAP-10 | Automatic organisation & Activity | REPO-REPORTED | M0/M1 | Semantic extraction quality; correct action reporting; undo |
| CAP-11 | Explicit web research | REPO-REPORTED | M0 | Actual sourced search, quotas and privacy mode check |
| CAP-12 | Optional SMS / inbound phone | REPO-REPORTED | M6 | Provider setup, live delivery/call, owner authentication |
| CAP-13 | Personal event and case awareness | DESIGNED | M1 | Provenance, timestamps, status, retention and restart tests |
| CAP-14 | Interest monitoring | DESIGNED | M5 | Deduped, source-grounded change detection; pause/quiet hours |
| CAP-15 | Welcome Home Scene Engine | DESIGNED | M2 | Real clap → apps → truthful briefing → voice → follow-up |
| CAP-16 | ChatGPT memory import review | DESIGNED | M3 | Local parser, dedupe, sensitive review, rollback, no Git leakage |
| CAP-17 | Calendar connection | DESIGNED | M4 | Real read, stale-data logic, scopes, source consistency |
| CAP-18 | School email monitor and drafts | DESIGNED | M4/M5 | Authenticated thread retrieval, draft only, reply detection |
| CAP-19 | Notion data integration | DESIGNED | M4 | Approved page reads; bounded writes and permission checks |
| CAP-20 | Spotify/local playlist control | DESIGNED | M2/M4 | Real player/device response, unavailable-path fallback |
| CAP-21 | Governed general Windows/browser control | IN-PROGRESS | M4/M7 | Fixed app/folder launch and CoreAudio volume adapter slice is implemented with approval/verification tests; general screen control and actual OMEN launch/volume-change acceptance remain outstanding. See [validation](VALIDATION.md). |
| CAP-22 | Durable multi-step agent jobs | DESIGNED | M7 | Restart/idempotency/retry/approval/partial-action tests |
| CAP-23 | Reusable Skills framework | DESIGNED | M7 | Manifest validation, sandbox and skill injection tests |
| CAP-24 | Coding-agent delegation | DESIGNED | M7 | Isolated worktree, diff/test evidence, no unsanctioned merges |
| CAP-25 | Unified remote context | DESIGNED | M6 | Phone has bounded shared case access; channel restrictions |
| CAP-26 | Proactive digest/notification policy | DESIGNED | M5 | No duplicate or stale alerts; owner quiet hours and pause |
| CAP-27 | Always-on companion worker | DEFERRED | M8 | Service survives laptop sleep; secure sync and real costs |
| CAP-28 | Business operations workflows | DESIGNED | M8 | Complete one approved, verifiable recurring business procedure |
| CAP-29 | Cost/privacy/security dashboard | DESIGNED | M5/M7 | Reconciled usage and actionable controls; data deletion proof |

## Progress rollup

- **Baseline counts:** 12 `REPO-REPORTED`, 16 `DESIGNED`, 1 `DEFERRED` (29 total). These are **not** completion percentages.
- **Last full offline suite:** October 28, 2026: 809 tests run, 805 passed / four skipped after the speech-noise correction; four voice/interface JavaScript checks passed. The preceding action-awareness slice passed all seven JavaScript checks. See `docs/VALIDATION.md`.
- **Current highest-value milestone:** M0 software baseline audited; complete OMEN hardware acceptance. CAP-30/31 first slices implemented; next is the bounded CAP-32 read-only planner demonstration, before broader M1/M2 work.
- **Known gaps:** OMEN mic/voice hardware acceptance, external app connectors, phone's access to desktop memories, general desktop autonomy, persistent cross-app jobs, always-on operation.

## Active milestone board

| Milestone | State | Exit criteria | Links / notes |
|---|---|---|---|
| M0 Baseline/design adoption | SOFTWARE AUDITED; HARDWARE PENDING | Review and approve this spec; test current main; note discrepancies | Owner adopted design on 2026-10-28. Full offline suite passed on 2026-10-28. OMEN mic, voice and app-launch acceptance remain pending. |
| M1 Awareness foundation | NOT STARTED | Event/case/interest schema + provenance and consent UI tests | Depends M0 |
| M2 Welcome Home scene | NOT STARTED | One actual hardware end-to-end scenario succeeds | Depends M1 (partial), wake baseline |
| M3 Memory import | NOT STARTED | Local export import with preview, consent and undo | Depends M1 |
| M4 App connectors | NOT STARTED | One connector at a time, scoped OAuth and live acceptance | Depends M0 |
| M5 Watchtower v1 | NOT STARTED | One real new update, no duplicates, quiet hours | Depends M1 + relevant M4 |
| M6 Unified phone | NOT STARTED | Authenticated remote view of approved context | Depends M1, phone setup |
| M7 Skills and jobs | NOT STARTED | Safe multi-step execution and restart recovery | Depends permissions and tool interfaces |
| M8 Business/always-on | DEFERRED | Security reviewed hosted worker and one business workflow | Depends M5–M7 |

## Risk and blocker register

| Key | Severity | Risk | Mitigation / decision |
|---|---|---|---|
| R-01 | High | Public GitHub repository leaks personal memory, logs or keys | Keep private data out of repo; secret scan, `.gitignore`, fixture-only tests |
| R-02 | High | Prompt injection through email/web/skills | Explicit tool schemas and origin-aware permission enforcement |
| R-03 | High | Duplicate external actions on retry/restart | Idempotency keys, receipts, uncertain status and reconciliation |
| R-04 | High | Desktop/phone auth confusion | Channel scopes, owner verification, fresh RED approvals |
| R-05 | Medium | Voice demos overstate real microphone reliability | Hardware test matrix and measured false positives |
| R-06 | Medium | Monitoring cloud bills, provider quotas, SMS delivery | Daily/monthly caps, backoff, explicit subscriptions and delivery status |
| R-07 | Medium | Codex work is uncommitted or ahead of design baseline | Review latest commits, branch hygiene, change log |
| R-08 | Medium | Local SQLite sensitive records are not encrypted at rest | Dedicated encryption/backup milestone before bulk personal import |

## How to update after every Codex feature

1. Identify affected capability IDs and the approved requirement section.
2. Add commit/PR reference, exact test command/result/date and whether a human hardware/provider check occurred.
3. Advance the status only according to the vocabulary above. A passing unit test does **not** imply `LIVE-VERIFIED`.
4. Record remaining gaps, cost/privacy concerns, and the next specific task.
5. Update `docs/VALIDATION.md` for test evidence and `IRIS_DECISIONS.md` for material design changes.
6. Keep this table up to date on the same branch/PR as the code change.

### Change entry template

```text
Date (YYYY-MM-DD):
Capability IDs:
PR / commit:
Status before -> after:
Code paths changed:
Automated test command + count:
Live/manual test + device/provider:
Privacy/cost/permission impact:
Unresolved limitations:
Next action:
```

## Generalist addendum requirements

The owner also supplied [the Generalist Architecture addendum](IRIS_GENERALIST_ARCHITECTURE.md).
These capabilities are separate from the existing model router and tool registry:

| ID | Capability | Status | Acceptance still needed |
|---|---|---|---|
| CAP-30 | Privacy-safe outcome traces | IN-PROGRESS | Tested desktop/chat-tool receipts, retention, deletion, privacy and interruption recovery. Route/model/cost tracing, background and phone coverage remain pending. |
| CAP-31 | Unified read-only capability registry | IN-PROGRESS | Tested typed tool/model/host-workflow inventory and local capability answers. Configuration is not live health; broader specialist/connector inventory remains pending. |
| CAP-32 | Validated task DAG proposals | DESIGNED | Bounded read-only planning, dependency validation and verified execution |
| CAP-33 | Verified experience memory | DESIGNED | Durable summaries, provenance, consent, retention and restart tests |
| CAP-34 | Offline improvement evaluation | DESIGNED | Baseline/holdout evaluation, injection and regression rejection |
| CAP-35 | Scoped specialist workers | DESIGNED | Typed input/output, bounded delegation and no inherited blanket authority |
| CAP-36 | Supervised routing/skill improvement | DESIGNED | Evidence, owner-reviewed promotion and rollback |

### 2026-10-28 adoption and desktop slice

- Imported the design package and generalist addendum, plus provenance-labelled
  personal context into the configured vault. Personal text is outside Git.
- CAP-15 remains DESIGNED: the explicit fixed workspace routine is a precursor,
  not an automatic homecoming scene or a live-verified clap-to-app sequence.
- CAP-16 remains DESIGNED: storing the supplied profile as a vault note does not
  implement a ChatGPT export parser, confirmed-memory migration or review/undo UI.
- CAP-21 is IN-PROGRESS: fixed adapters and permission handling are present and
  tested with fake apps; only native volume *reading* has been checked live.
  Code: [`b63853c`](https://github.com/sugacookie1234/iris-v3-capable-laptop/commit/b63853c640b64f7adcebf10573e7cdb006b46bff).
  Evidence: 53 focused Python tests and the desktop JavaScript check passed on
  2026-10-28; see [validation](VALIDATION.md). This does not mark the complete
  general Windows-control capability as TESTED or LIVE-VERIFIED.
- No AGI claim, autonomous planner, source-code self-modification, new account
  connector, automatic scene or monitoring subscription has been introduced.

### 2026-10-28 action history and capability awareness

- Code: [`fd040ee`](https://github.com/sugacookie1234/iris-v3-capable-laptop/commit/fd040ee621bf4b60962145afd4534869120e9930).
- CAP-30/31 changed DESIGNED → IN-PROGRESS. Commands and privacy scope are in
  [Action history](ACTION-HISTORY.md); exact checks are in [Validation](VALIDATION.md).
- Receipts store only allowlisted metadata; no arguments, paths, result text,
  secrets or full transcripts. Local replies are excluded from future model prompts.
- Existing authority remains the execution boundary. An observer cannot approve,
  retry or promote generic handler success into independently verified success.
- Receipts retain up to 30 days / 1,000 entries with explicit confirmed erasure.
  Automatic organization keeps its separate Activity/Undo record.
- Capability inspection makes no network call and grants no permissions. The
  exposed schema follows current tool registrations and host configuration.
- No paid provider tests or real app/volume changes were performed for this slice.

### 2026-10-28 voice-noise correction (CAP-07/08)

- Added local CPU speech detection before either cloud upload or local decoding,
  English-mode language validation, and conservative Whisper confidence checks.
- Rejected automatic recordings return quietly to standby, without creating chat
  messages or retrying another recognizer. Manual recording retains no-speech feedback.
- Synthetic noise and the public English speech fixture passed local acceptance;
  microphone false-positive/miss rates still require real-room and OMEN trials.
  Full evidence is in [Validation](VALIDATION.md); capability status is not promoted
  to LIVE-VERIFIED by fixture tests.
