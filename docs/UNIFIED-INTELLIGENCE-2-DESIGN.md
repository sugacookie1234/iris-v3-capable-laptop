# Unified Intelligence 2.0 — first experimental slice

Authority: [handoff](UNIFIED-INTELLIGENCE-2-HANDOFF.md). Implementation remains
default-off: set `IRIS_EXPERIMENTAL_INTERPRETATION=true` in the launch environment
to opt in; remove it or set false to restore legacy routing. No owner configuration
has been changed. This setting is not a new remote control or model-writable policy.

## Contract and execution

`iris/generalist/interpretation.py` parses exact JSON fields: version=1, current
host-generated turn ID, kind, bounded text, capability, arguments and candidate
context reference. Kinds are conversation/question/hypothetical/action/clarification.
Social intent uses conversation; contextual intent carries a reference. Only compound
and workspace_list are supported. Duplicate/unknown fields, forged permissions,
unsupported versions, native tool calls, non-finite or excessive numbers fail closed.

DesktopRuntime's existing turn lock owns interpretation through publication. The
model cannot write state by emitting JSON: the host rechecks current eligibility,
reference ID/revision/expiry, numerical limits and requested parameter/value.
Compound mutations use CompoundSkill; all graph values and success text come from
existing deterministic arithmetic. UI edits and conversation share the same state.
Single parameter changes are supported. Original-rate comparisons use five percent
only when principal/duration/contributions still match the original baseline;
otherwise clarification is required. No investment transaction exists here.

Workspace listing is limited to the configured root. Current affirmative owner
consent and existing workspace.read permission are required. ToolExecutor retains
MODEL provenance and its existing approval, timeout and path checks. No new permission
is granted. Results are displayed locally and never sent for cloud synthesis or added
to model history. Generated prose is not used as a tool or calculation receipt.

## Routing, cost and privacy

Eligible compound, workspace-list and playful-grade turns use one existing FAST
adapter request with no advertised tools. Active bounded example comparisons may
use FAST despite the generic compare->DEEP heuristic. Other DEEP and Council routing
remain unchanged. Ordinary dialogue remains on the existing single-response path;
this is not an extra interpretation call before every conversation.

The current request and public scenario snapshot are the only supplemental inputs;
private history, memory, vault data and tool results are excluded. Existing memory
and Council systems are preserved, not replaced. Public calculated summaries use
the existing canonical history path. Experimental turns do not trigger the organizer.
The standard transport retains durable quota admission; malformed output or provider
failure produces an honest clarification, without a retry or fallback provider.

## Deliberate limits

This is bounded semantic interpretation, not general autonomous reasoning. Host
eligibility and consent still use conservative intent cues; arbitrary paraphrases,
multi-parameter edits, complex number words and unrelated context are not promised.
Only a labelled synthetic guess demonstrates social output; actual model quality,
factual reliability and latency require an approved benchmark. No private transcript
training, learning traces, new scheduler, multi-step planner or local model installed.

Native origins/cookies/leases and approval routes are untouched. In-chat visuals
remain usable; the outstanding WebView2 reliability gate is NOT fixed. General
provenance-aware ContextRef, persistent projects and multi-step plans remain M3+.
