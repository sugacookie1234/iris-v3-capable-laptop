# I.R.I.S. v3 — Generalist Agent Architecture Addendum

> **Status:** Research-backed design proposal, **not** a claim of AGI or implementation.  
> **Version:** 0.2.0-draft · **Date:** 2026-10-28  
> **Baseline v3 snapshot:** `9db02a7e9b3ed9dcc4e28dc64270a802cbe4ad28`  
> **Companion files:** `IRIS_MASTER_DESIGN.md`, `IRIS_CAPABILITY_TRACKER.md`, `IRIS_DECISIONS.md`, `IRIS_CODEX_PROTOCOL.md`.  
> **Repository privacy:** The owner plans to keep v3 private. This document contains only architecture and public source links, not private account data.

## 0. What “AGM” means in this design

The owner asked to turn IRIS into an “AGM,” alongside JARVIS-AGI, HuggingGPT, OpenJarvis, and JARVIS-1 research references. **AGM is not defined by those sources.** We use **generalist agentic mind** as a *working internal architecture label*, pending owner terminology confirmation; **not** as a scientific assertion of artificial general intelligence (AGI), consciousness, sentience, human-level competence, or a new foundation model. If the owner meant AGI, acknowledge AGI as the long-term ambition but do not claim it has been achieved.

**Engineering goal:** A persistent, multimodal, self-improving *within measured limits*, single-identity generalist assistant capable of decomposing unfamiliar tasks, selecting specialist models and tools, learning reusable procedures from verified experience, and conducting authorised long-running work. The core product remains a personalised chief of staff with reliable voice/HUD/desktop/phone interfaces.

## 1. Sources, accuracy, and reuse decisions

| Source | Validated idea or documented implementation | Value to IRIS | What NOT to infer | Recommendation |
|---|---|---|---|---|
| [OpenJarvis](https://github.com/open-jarvis/OpenJarvis) / [architecture](https://open-jarvis.github.io/OpenJarvis/architecture/overview/) / [learning](https://open-jarvis.github.io/OpenJarvis/architecture/learning/) | Five primitives (Intelligence, Engine, Agentic Logic, Memory, Learning); model/runtime registries, routed agents, traces, telemetry, learned policies, scheduled/continuous agents, skill library and optimization | Best design reference for a learning loop and modular, hardware-aware model/agent selection | Claims of better on-device benchmarks are not proof of better performance for IRIS on the OMEN; a framework is not AGI | **Adopt patterns selectively**; compare actual code, test coverage and Apache-2.0 licence before copying |
| [HuggingGPT](https://github.com/AI-Chef/HuggingGPT) | Controller language model decomposes requests; selects expert models; executes; synthesises results | Task DAG / model-worker registry; specialist vision, speech and coding delegation | Original example is historically dated; full local setup documents >=24 GB VRAM and very large model storage; not an off-the-shelf lightweight brain | **Architectural reference**, not wholesale installation; MIT licence check for source reuse |
| [JARVIS-1 paper](https://arxiv.org/html/2311.05997) | Minecraft open-world benchmark with multimodal observation, situation-aware replanning, memory of successful plans, goal-conditioned execution, self-instruct exploration | Observe -> plan -> act -> verify -> update; record validated experience; adapt plans when real world changes | 200+ Minecraft tasks and benchmark success do NOT establish office, business, financial or general-human intelligence | **Research pattern only**; benchmark real IRIS workflows separately |
| [JARVIS-AGI](https://github.com/SreejanPersonal/JARVIS-AGI) | Voice assistant assembled from ASR/TTS, multiple text/image providers, audio interruption and clap experiments | Ideas for activation/vision and voice UX; optional isolated comparisons | Name “AGI” and broad README statements do not prove general intelligence or dependable actions; overlaps v3 voice | **Low-priority selective reference**; do not replace v3 Fish/Whisper/clap |

Reference details were reviewed on 2026-10-28. Pin exact external revisions before importing code or dependencies; perform independent licensing, security and maintenance review. The v3 source is canonical, not these upstream repositories.

## 2. Design contract: one mind, many specialist workers

IRIS is **one persona and one accountable orchestrator**. Workers are transient, scoped executors with no independent user identity or permission to add tools or grant themselves rights. The Council offers deliberation, not tool authority. Tool outputs and retrieved content are untrusted, and success is grounded in independent verification.

```text
Desktop / voice / phone / authenticated remote channel
                          |
                   Session Gateway
                          |
                   IRIS Orchestrator
              (intent, context, policy, budget)
                   /      |      \
            Planner    Model Router   Memory/Case Retrieval
               |          |                  |
           Task DAG    FAST/DEEP/COUNCIL    Event & Experience Store
               |
      Policy / Approval Gate  <--- OWNER AUTHORITY ONLY
               |
        Capability Registry
          /       |        \
      Skills    Tools     Specialist Workers
         \       |        /
          Result Verification
               |
      Trace / Outcome / Feedback Store
               |
      Offline Evaluation & Improvement Proposals
               |
        Owner review + gated promotion
```

**Do not** connect model reasoning directly to arbitrary shell, desktop or external-account execution. `iris/tools/authority.py` and `ToolExecutor` remain authoritative; expand only through reviewed and typed adapters.

## 3. The observe–plan–act–verify–learn contract

1. **Observe** — obtain user objective, relevant approved context, current application/source state, constraints, time and budget. Cite provenance; do not infer unobserved facts.
2. **Plan** — break an objective into a dependency-aware Task DAG with clear outputs, costs, preconditions, risk tiers and rollback/compensation options. Planner output is *data*, never executable authority.
3. **Select** — use an explicit capability registry to match each node to deterministic tools, skills, single models or specialist workers. Require a known viable target and input/output schema.
4. **Authorise** — apply GREEN/YELLOW/RED checks to each concrete side effect. RED includes sending external messages, financial acts, account changes, important deletion and publishing. Phone is least-privileged. Guard against replay and approval argument changes.
5. **Act** — execute only allowed nodes; use deterministic tools for exact operations; bound resource consumption, depth, elapsed time and retries. Keep the chat responsive.
6. **Verify** — independently confirm observable outcomes through tool readback, stable IDs, receipts, file diffs, source links or test results; distinguish `attempted`, `submitted`, `verified` and `unknown`.
7. **Replan** — when a precondition fails or context changes, revise the remaining plan; never assume that a prior plan remains valid.
8. **Learn** — store a consent-appropriate *summary of experience* (objective, action, context features, outcomes, failure lessons) without recording secrets/full sensitive payloads by default. Propose skill/routing changes offline; apply only after benchmarks and review.

The only permissible self-improvement in early stages is **memory update, retrieval improvement, evidence-backed routing and reviewed skill description/procedure adjustment**. No autonomous production-code edits, unreviewed skill imports, silent fine-tuning on private records, or automatic privilege expansion.

## 4. Minimal typed contracts (proposed, not current runtime)

```python
@dataclass(frozen=True)
class TaskNode:
    node_id: str
    operation: str           # namespaced registered capability
    inputs: dict[str, object]
    depends_on: tuple[str, ...]
    expected_evidence: str
    authority: str           # GREEN / YELLOW / RED
    timeout_s: int
    max_attempts: int

@dataclass(frozen=True)
class Experience:
    experience_id: str
    objective_tag: str
    planner_version: str
    model_or_agent: str
    tool_names: tuple[str, ...]
    outcome: str             # verified / partial / failed / unknown
    verification_method: str
    source_event_ids: tuple[str, ...]
    privacy_class: str
    time_started: str
    time_finished: str

@dataclass(frozen=True)
class ImprovementProposal:
    proposal_id: str
    kind: str                # routing / skill_overlay / planner_config
    baseline_ref: str
    candidate_ref: str
    evaluation_set: str
    improvement_metrics: dict[str, float]
    regression_metrics: dict[str, float]
    approval_state: str
```

**Schema requirements:** SQLite migrations must be backward compatible; monotonically ordered events and unique idempotency keys for external effects; durable job step state; field length limits; encrypted or restricted private stores; retention/deletion; provenance and consent; no scripts in stored plans. Use existing v3 stores and `RequestOrigin` where possible rather than parallel sources of truth.

## 5. Adaptive cognition without pretending to train an AGI

- **Phase A — Instrumentation:** trace the selected routing mode, model, skill/tool calls, timestamps, cost estimates, errors and verification status. Redact content. Consent-gated debug traces are separate from normal logs.
- **Phase B — Outcome scoring:** combine deterministic success criteria, owner corrections and cost/latency measurements. Do not treat fluent replies, model self-scores or Council votes as proof of success.
- **Phase C — Routing recommendations:** compare FAST/DEEP/COUNCIL and local/cloud choices on fixed, consent-safe evaluation sets. Show recommendation and confidence; keep fallback error semantics truthful.
- **Phase D — Skill discovery:** identify repeated *successful, authorised* tool sequences; generate candidate SKILL.md + manifest under a quarantined staging directory, not an auto-activated skill folder.
- **Phase E — Safe evaluation:** benchmark candidate vs baseline, including negative/security/regression cases. Only an explicit owner-approved change is promoted; keep rollback.
- **Later research:** optionally investigate local embeddings, preference learning or model fine-tuning on opt-in synthetic/redacted traces **only if measured to improve outcomes**, with compute, privacy and rollback budgets.

Never equate storing more conversational text with improved ability, and never let a self-generated “memory” count as verified external evidence.

## 6. Three types of execution to keep separate

| Subsystem | What it does | Owner | Example |
|---|---|---|---|
| **LLM Council** | Independent reasoning / cross-check / synthesis | Existing `iris/brain/council.py` | Compare business strategy options |
| **Workflow / Agent job** | Complete multi-step tasks, verify results, recover on error | `iris/workflows/`, `iris/automation/` plus new job supervisor | Research a supplier, draft a report, log outcomes |
| **Specialist model/tool** | Bounded single function with known contract | New worker/tool registry behind `iris/tools/` | Transcribe speech, extract invoice figures, test code |

Council consensus never bypasses YELLOW/RED action gates. Use a Council selectively, not on each voice request.

## 7. v3 code mapping and minimal architecture extensions

| Existing code | Extend with | Engineering consideration |
|---|---|---|
| `iris/brain/router.py`, `model_policy.py`, `engine.py` | `iris/generalist/capabilities.py`, planner, route scoring | Preserve FAST/DEEP/COUNCIL, bounded latency, explicit model IDs and errors |
| `iris/brain/council.py` | Optional review of difficult plans and contradictory evidence | Do not fictionalise model diversity or use Council as authority |
| `iris/memory/` and local notes | `iris/generalist/experiences.py`, retrieval of verified successful procedures | Record sources, age, corrections, privacy; no uncontrolled chat dump |
| `iris/tools/authority.py`, `executor.py`, `registry.py` | Capabilities with typed read/write effects and per-node approvals | `ToolExecutor` child-process limit is not a security sandbox for malicious code |
| `iris/workflows/engine.py`, `iris/automation/scheduler.py` | Durable Task DAG, step verification, resume/compensation and job supervisor | Crash-safe idempotency, partial effects, cancellation |
| `iris/desktop/runtime.py`, `server.py`, `web/` | Non-blocking job start/status/cancel/approval; trace and costs view | Keep interactive chat independent of long-running work |
| `iris/phone/` | Scope-limited case retrieval and progress reports | Separate authentication/voice session; no blanket desktop rights |
| Existing scenes and Watchtower proposals | Publish events through a durable job/event boundary | No scene/data access without active consent |

Suggested new additions: `iris/generalist/plan.py`, `capabilities.py`, `delegation.py`, `verification.py`, `experiences.py`, `evaluation.py`, `promotion.py` and focused tests. **Names are proposals, not implementation evidence.** Do not add all files at once: one working vertical slice first.

## 8. Measurable capability targets and safety tests

| Requirement | Initial acceptance test | Later milestone |
|---|---|---|
| Generalist task decomposition | A bounded 3-step research→extract→draft task yields a valid DAG with dependency checks and no unknown tools | Unfamiliar tasks with branching/replanning |
| Model selection | Correctly routes a fixed test set, with cost/latency accounting and a no-paid-fallback policy | Outcome-aware routing beats baseline on same holdout |
| Specialist delegation | Registered worker returns schema-valid data; invalid or malicious result is rejected | Concurrent independent workers with isolation |
| Execution verification | No task marked `verified` without independent readback or evidence | Complex uncertain external effects and recovery |
| Experience memory | Restart preserves an approved redacted success/failure trace and its provenance; no sensitive raw content persists by default | Success-pattern retrieval improves outcomes |
| Learning loop | Candidate routing/skill change is benchmarked in sandbox; regression is rejected | Approved positive changes show improvement over multiple runs |
| Personal management | A real authorised reply/monitoring case updates once with correct source and notification | Multiple app sources; quiet proactive resolution |
| Resilience | Provider failures, timeouts, cancellation, duplicated events, restarts, permission denial | Longer-running jobs on separate host |
| Permissions | Prompt injection in retrieved web/email/skill cannot widen tool access; RED requires fresh exact approval | Remote-channel and multi-agent adversarial tests |

**Proposed initial evaluation suite:** at least 30 diverse synthetic tasks across research, education, personal administration, coding, memory and multi-step operations; report task success, invalid-tool rate, verified-result rate, source errors, approval violations, median/p95 time, token/provider cost and interruption rate. Include a baseline with the new planner/learning features OFF. This is a testing proposal, **not** existing benchmark evidence or a guarantee.

## 9. Implementation order for Codex

0. **Audit and benchmark freeze** — check live current branch/working tree, tests, README, permissions, and the design. Keep previous docs and code untouched until scope is agreed.
1. **CAP-30** — instrument privacy-safe traces and observable outcomes on existing real text/tool workflows. Keep sampling/logging bounded. No new external permissions.
2. **CAP-31** — add a read-only `CapabilityRegistry` with typed descriptors for existing allowed skills/tools/models; do not install or execute external code by discovery.
3. **CAP-32** — implement a minimal planner that returns validated Task DAG proposals for bounded read-only tasks, with deterministic execution and verification.
4. **CAP-33** — durable verified experience summaries, linked to existing memory/event system and user review/retention controls.
5. **CAP-34** — an offline evaluation harness for router/skill candidates, including prompt-injection and regression cases.
6. **CAP-35** — a scoped specialist-worker adapter, first with existing models/tool handlers and fully mocked tests, later Codex or other coding agents in isolated worktrees.
7. **CAP-36** — optional supervised learned routing/skill improvement, behind feature flags with owner review, metrics and rollback.
8. Revisit the business manager and Watchtower milestones after this generalist foundation has been tested on real use cases.

**First deliverable** should be only instrumentation + a read-only registry and a demonstrable 3-step task run. Do not pursue self-modifying source code or autonomous skill installation first.

## 10. Worked example: “IRIS, run my business briefing”

1. **Trigger:** owner-defined daily window or explicit user request (no implicit consent to rummage across accounts).
2. **Observe:** fetch only authorised email/calendar/finance/project data and known unresolved cases; disclose sources that are unavailable.
3. **Plan:** DAG of `read inbox` + `read tasks` + `read sales snapshots` → `compare changes` → `draft briefing`.
4. **Delegate:** deterministic adapters for retrieval; specialist model for classification; optional Council for consequential choices. No need for the Council on routine read-only refreshes.
5. **Verify:** source message IDs, task revisions, date ranges and report provenance; check for outdated or duplicate events.
6. **Report:** concise spoken summary and editable detailed view; avoid false statements that actions were taken.
7. **Act:** drafts and suggestions can be prepared; external sends/purchases/transfers remain approval-gated.
8. **Learn:** capture which sources and workflows were effective as anonymised/consent-approved experience; propose improved routing only after evaluation.

This is a realistic path towards a very capable **personal AI manager** without misrepresenting AGI.

## 11. Security, budget and operational limits

- **Untrusted skills are supply-chain software**, not merely prompts. Use integrity hashes/pinned versions, static reviews, strict allowlists and isolated execution where supported.
- Do not treat subprocess/multiprocessing termination as a security boundary against malicious code; use OS isolation where appropriate.
- Browser and email content can contain prompt injection; translate model plans into validated structured actions and follow the original user/tool authority rather than embedded page instructions.
- Default local trace logs **must not** store secrets, tokens, full transcripts, raw microphone recordings, financial records, health data or email content.
- Review hardware tradeoffs on the HP OMEN 16's **actual** VRAM/thermal performance. Full HuggingGPT local deployment is not the recommendation. Use cloud for selective complex tasks and local processing for privacy/latency where measured practical.
- Per-job limits: model calls, tokens, estimated CAD cost, elapsed time, recursion depth, number of tools, parallel agents, retries and notifications. Stop gracefully when limits are reached.
- Pausing the system or revoking a connector must cancel future scheduled actions; verify no stale worker continues without permission.
- GitHub project privacy does not permit uploading personal memory into the repository. Use encrypted local stores and private export workflows.

## 12. Decision and naming summary

**Proposed ADR-016:** Adopt the **generalist agentic mind** vision as the engineering target under the existing IRIS v3 identity. Reserve “AGI” as an aspirational research label rather than a capability claim. Owner terminology to confirm.

**Proposed ADR-017:** Use OpenJarvis's **ideas** (traces, learning policies, skill evaluation, model registries) as the principal research influence. Keep the existing v3 runtime and permission boundary. No wholesale framework migration.

**Proposed ADR-018:** Integrate HuggingGPT-style typed delegation and JARVIS-1-style situation-aware closed-loop planning, but enforce independent outcome verification. No uncontrolled long-lived autonomous agent.

**Proposed ADR-019:** Allow adaptive routing/skill optimisations only through explicit benchmark-and-approval gates; do not enable self-editing production source by default.

**Proposed ADR-020:** Start with a small safe vertical slice, then build towards a personal-manager experience spanning desktop, memory, approved internet research, email, calendar and phone.
