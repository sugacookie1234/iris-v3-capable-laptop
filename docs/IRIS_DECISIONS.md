# I.R.I.S. v3 — Architectural Decision Log

> **Initial date:** 2026-10-28. Distinguish **accepted by existing implementation**, **user-stated product direction**, **recommended**, and **open**. A recommended design is not automatically approved for implementation.

| ID | Topic | State | Decision or proposal | Rationale / revisit trigger |
|---|---|---|---|---|
| ADR-001 | Canonical codebase | USER-STATED | `sugacookie1234/iris-v3-capable-laptop` supersedes v2 as the working project. | Keep v2 as historical context only. |
| ADR-002 | Deployment target | EXISTING BASELINE | Native Windows desktop app on HP OMEN-class laptop; maintain text mode and local loopback controls. | Matches v3 implementation; hardware acceptance pending. |
| ADR-003 | Core architecture | RECOMMENDED | One IRIS orchestrator with separate memory/awareness, connectors, scenes, monitors and jobs. | Prevent duplicate brains and permission systems. |
| ADR-004 | Identity | USER-STATED DIRECTION | Blend JARVIS intelligence/dry wit, FRIDAY precision, Karen guidance, E.V. warmth into one personalised IRIS identity. | Retain original personality; polished introduction candidate requires source review. |
| ADR-005 | Wake scenes | USER-STATED DIRECTION | Double clap and opt-in cinematic, contextual homecoming; opening browser, playlist and workspace; time-aware briefing. | Requires reliability, cooldown and permission checks. |
| ADR-006 | Monitoring | USER-STATED DIRECTION | Proactively watch approved interests and awaited replies, with relevant/noisy alert suppression. | Watchtower required; consent and dedupe are critical. |
| ADR-007 | Personal memory migration | USER-STATED DIRECTION | Transfer useful ChatGPT context into IRIS; do not assume direct internal memory export or dump everything without review. | Local import and privacy review. |
| ADR-008 | Model policy | EXISTING BASELINE | FAST/DEEP/COUNCIL with a single persona and a governed tool boundary. | Council != permission; same-model seats not diverse models. |
| ADR-009 | Permissions | EXISTING BASELINE + RECOMMENDED | Retain GREEN/YELLOW/RED; exact approval for high-impact and external actions. | Extend to remote channels and worker skills. |
| ADR-010 | Persistent monitoring host | OPEN | Tray-only versus separate always-on host. | Laptop sleeps; evaluate security, hosting cost and true need after Watchtower v1. |
| ADR-011 | Primary calendar and mail | OPEN | Which of Outlook, Google and Notion Calendar owns canonical events and replies? | Needs account inventory and duplicate reconciliation policy. |
| ADR-012 | Music | OPEN | Spotify with appropriate account permissions versus local playlists. | Subscription, playback device and reliability questions. |
| ADR-013 | Privacy/retention | OPEN | Sensitive memory encryption, retention policies and migration location. | Private repo does not authorize personal data in Git; local SQLite personal records remain plaintext in the current default. |
| ADR-014 | Monitoring cadence for design docs | RECOMMENDED | Review after major feature changes and at least weekly in active development; alert on material drift. | Avoid stale status without noisy commit-by-commit interruptions. |
| ADR-015 | Editing policy | RECOMMENDED | Draft design changes on a separate branch/PR before merging into `main`. | Avoid interfering with simultaneous Codex development. |
| ADR-016 | Design adoption | OWNER-ACCEPTED 2026-10-28 | Use the supplied master design and generalist addendum as the development baseline; source snapshots are preserved in Obsidian. | Roadmap acceptance is not evidence that capabilities are implemented. See [design index](IRIS_DESIGN_INDEX.md). |
| ADR-017 | First desktop routine | OWNER-SELECTED 2026-10-28 | Explicit “Start my workspace” uses Chrome, Obsidian and the configured workspace folder. Keep double clap conversation-first. | This is a fixed scene precursor, not general autonomous desktop control. |
| ADR-018 | Desktop action execution | IMPLEMENTATION DECISION 2026-10-28 | Register app/folder/volume adapters behind the existing ToolExecutor. YELLOW changes require a fresh exact plan approval; the three-step workspace has one approval covering exactly that sequence. | Preserves the design authority boundary. Routine failures are per-component, with no implicit retries or false completion claims. |
| ADR-019 | Supplied personal profile | OWNER-REQUESTED 2026-10-28 | Import the original into a provenance-labelled Obsidian note outside the source repo. Keep historical claims and assistant interpretations distinct from current confirmed facts. | No bulk confirmed-memory import, new monitor, provider upload or profile-derived action was performed. |
| ADR-020 | Local action receipts | IMPLEMENTATION DECISION 2026-10-28 | Store bounded metadata for observed desktop/chat tools; keep generic returns unverified and interrupted effects unknown. Retain 30 days / 1,000 rows with confirmed deletion. | No raw content, arguments, paths or full errors. Existing organizer Activity remains separate; full route/cost/phone tracing is pending. |
| ADR-021 | Read-only capability awareness | IMPLEMENTATION DECISION 2026-10-28 | Derive typed inventory from host registrations and configuration; expose local commands and authenticated local API. | Configuration is not live health. Inspection makes no provider requests and confers no execution rights; history/configuration replies stay out of subsequent model prompts. |

- **ADR-022 — Implementation decision, 2026-10-29:** Keep explicit vault inspection
  local and out of model history. Decode safe index links and excerpt large notes
  after screening their full bounded contents; preserve provenance and revision
  checks. Original imports remain snapshots; repository docs track development.
- **ADR-023 — Implementation decision, 2026-10-29:** Begin CAP-32 with pure bounded
  immutable proposal validation and an honest local preview. Do not fabricate
  output schemas, note paths or a draft worker to claim a complete task run.
  Existing ToolExecutor authority remains the boundary for future execution.

- **ADR-024 — Implementation decision, 2026-10-29:** Suppress performed vocal cues
  at the speech boundary and request lower Fish expressiveness, preserving selected
  voice/model and displayed text. Shared cleanup also governs device fallback.
  Auditory acceptance remains separate from request-contract tests.
- **ADR-025 — Implementation decision, 2026-10-29:** Execute a bounded fixed
  notes-briefing recipe locally before introducing a general planner. Use existing
  authority, strict output contracts, source revision/readback and excerpt checks.
  The output is labelled source excerpts, with no model cost or new write authority.

### Decision change template

```text
ID:
Date:
Status: proposed | accepted | superseded | rejected
Context:
Options and tradeoffs:
Choice:
Approver:
Affected capabilities / files:
Implementation or migration consequences:
```

### Open owner confirmations (not blockers for writing design)

- Desired automatic scene trigger distinction; cinematic address and wording.
- Which connectors/accounts are first priority and what personal-data scope is authorised.
- Budgets for LLM, Fish, search, phone and always-on hosting.
- Monitoring/quiet hours and escalation triggers.
- Data retention, encryption and backup expectations.
