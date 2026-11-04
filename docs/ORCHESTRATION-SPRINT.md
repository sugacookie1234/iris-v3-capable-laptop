# Unified Intelligence first vertical slice

Branch: sprint/evaluation-business-os; baseline 875bbed. No merge, external account
connection, paid request, microphone change or new computer-control authority.

## Functional conversation
In the ordinary chat, ask:
1. IRIS, explain compound interest.
2. What if the interest rate were eight percent?
3. Compare that with five percent.
4. Why is there such a difference?
5. Go back to the original example.

These five turns use the existing deterministic compound calculation and in-chat
version-1 line renderer. No model call is required. Principal is 1,000 units,
monthly compounding, ten years, no contributions/fees/taxes. Results are educational
constant-rate scenarios, not investment forecasts. Comparison uses two validated
series with identical time/principal assumptions. The explanation reports calculated
balances/difference, not invented figures. Equal rates explicitly produce equal
balances. Original restores 5%. Supported follow-up patterns include change/use/
what-if/compare, numeric percentages and English zero through twenty. Multiple rates,
unsupported number phrases or out-of-range values request clarification without
mutating the scenario. This is bounded language recognition, not general semantic
understanding. Principal, duration and contribution changes are not enabled yet.

## Interfaces and authority
iris/generalist/orchestration.py contains:
- Intent enum and validated Decision: conversation, local information, existing tool,
  active skill, visual explanation, research, clarification.
- Orchestrator.classify: deterministic guidance only. Existing-tool classification
  does NOT execute a tool or create an approval; the original host dispatcher and
  ToolExecutor remain authoritative. Explicit research remains with its old handler.
- Orchestrator.handle: only consumes the compound-interest skill's owner turns.
  Other requests fall through to existing runtime handling. No generated code,
  provider access, filesystem reading or privileged bridge exists in this module.
- ActiveContext: one public topic/workflow/visual reference and CompoundSkill,
  fifteen-minute fixed expiry and a maximum twenty follow-up turns. Cleanup is lazy
  at the next turn, or immediate on reset, cancellation or unrelated owner topic.
- CompoundSkill: start via Orchestrator; update, pause, resume, cancel, complete,
  expire; terminal state is discarded and cannot grant permission or replay work.

DesktopRuntime calls the local orchestrator under its existing turn lock, then falls
back to existing awareness/command/model handlers. No router/Council/memory rewrite.
Pending approvals remain exclusively in the existing runtime; verified private tool
results are deliberately NOT copied into this public skill context. There is not yet
an all-purpose shared private-task context or skill registry. Public example replies
enter bounded chat history with a canonical public query, not arbitrary raw local
user text. Local command responses default to private, even when produced after
awareness dispatch. This fixes the former ordering bug that could append their
results to later cloud context. Automatic note capture is not run for this workflow.

## Security closeout
Unconfigured model adapters now get the standard durable policy, as do standalone
Fish TTS/ASR paths; diagnostic HTTP has a separate category. Defaults cannot silently
skip admission. Test fixtures inject temporary ledgers. ASR quota refusal can use
existing local Whisper fallback without a cloud request. Counters are attempt limits,
not billing, and cannot defend against same-user code replacing the policy.
Existing host approval tests reject forged, stale, declined, model/external/memory
permission attempts and cancellation before worker startup. No new live tool
execution was enabled by orchestration. No existing pending owner approval changed.

## Evidence and limitations
Baseline full suite: 983 run, 979 passed, four skipped (101.987s).
Provider transport focus: 103 passed; combined closeout focus: 112 passed.
Orchestration + authority/existing tools/cancellation focus: 24 passed before the
additional independent closed-form numeric case. Current full-suite/JS/evaluation
results are recorded in VALIDATION.md after completion.

Synthetic replay uses a temporary DesktopRuntime and FakeBrain; five turns cause
zero provider calls. Closed-form Decimal arithmetic independently checks 2,219.64 at
8%. Tests cover expiry, topic changes, rate ambiguity, pause/resume/cancel, typed
routing, private-result isolation and malicious approval data. These do not prove
LLM quality, broad intelligence, hardware acceptance or general autonomy.

Remaining: broader context/reference resolution, typed verified-result references,
private task-context policy, richer deterministic numerical controls and lifecycle
acceptance. Separate native Visual Workspace is NOT built. Backup omissions/live
plaintext databases, current dependency advisory audit, native pairing acceptance,
secondary-window authentication and cross-machine recovery remain in SECURITY.md.

## Exact implementation files changed since 875bbed
- SECURITY.md
- docs/IRIS_CAPABILITY_TRACKER.md
- docs/IRIS_DECISIONS.md
- docs/ORCHESTRATION-SPRINT.md
- docs/PROVIDER-USAGE.md
- docs/VALIDATION.md
- iris/brain/providers/openai_compatible.py
- iris/desktop/recognition.py
- iris/desktop/runtime.py
- iris/desktop/server.py
- iris/generalist/evaluation.py
- iris/generalist/orchestration.py
- iris/phone/server.py
- iris/usage.py
- iris/voice/fish_audio.py
- tests/test_desktop_commands.py
- tests/test_desktop_recognition.py
- tests/test_desktop_web_search.py
- tests/test_fish_audio.py
- tests/test_openai_compatible.py
- tests/test_orchestration.py
- tests/test_orchestration_authority.py
- tests/test_phone_server.py
- tests/test_provider_adapter.py
- tests/test_readiness.py
- tests/test_speech_delivery.py

Final corrected regression: 994 run, 990 passed, four skipped (101.607s), .local/orchestration-verified.log. All eleven desktop checks passed. CAP-34: 100/100 per arm, zero regressions. Seventeen phone-server tests include bounded rejected-body timing. Sprint-range configured-secret scan: zero matches. No hardware acceptance, real provider calls or owner-data migration.

Native workspace extension: CompoundSkill now owns principal, years, contribution and comparison rate; authenticated UI edits and conversation share that same object under the runtime turn lock. See VISUAL-WORKSPACE-SPRINT.md. No private context or tool authority was added.
