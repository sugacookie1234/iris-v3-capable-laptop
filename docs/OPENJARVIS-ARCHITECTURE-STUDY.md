# OpenJarvis architecture study — 2026-11-05

Reference: [open-jarvis/OpenJarvis](https://github.com/open-jarvis/OpenJarvis).
Documentation study only; no dependency installed, source copied, local models
benchmarked or private transcripts exported. This records the research already
performed during the interrupted session rather than restarting it.

The official [architecture overview](https://open-jarvis.github.io/OpenJarvis/architecture/overview/)
separates model configuration, inference engines, agent logic, memory and learning.
Its registry interfaces decouple these components; traces can inform routing.
It also describes engine fallback and optional retrieval context injection.
These are useful comparison points, not evidence of compatibility or safe defaults
for IRIS. Its [design principles](https://open-jarvis.github.io/OpenJarvis/architecture/design-principles/)
emphasize pluggability, registries, offline operation and telemetry.

## IRIS decisions

| Reference concept | Existing IRIS home / decision |
| --- | --- |
| Model/engine separation | Keep ModelPolicy, LLMRegistry and existing provider transports |
| Typed capability selection | Add InterpretationV1 before existing host validation and ToolExecutor |
| Agent orchestration | Extend DesktopRuntime and compound orchestrator; retain Council |
| Layered context | Send only current request and host-owned public scenario in this experiment |
| Traces and evaluation | Extend CAP-34; no new private transcript store |
| Adaptive routing / learning | Deferred until measured evaluation and owner-approved rollout |
| Skill catalogues | Reuse installed registry; no automatic community skill installation |

We deliberately do not adopt automatic provider fallback, self-training, broad
retrieval injection, another executor or another permission system. This is an
IRIS-specific security decision, not a security assessment of OpenJarvis.
Provider accounting stays below inference. Models propose data; host code alone
decides whether the current turn, reference, arguments and permissions permit it.

Next research should be driven by a concrete later milestone rather than importing
the framework wholesale. Documentation is a moving upstream reference, not a pinned
source audit or a benchmark of this HP OMEN.
