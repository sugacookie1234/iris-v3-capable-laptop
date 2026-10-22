# Council upstream comparison

Reviewed 2026-09-11 against upstream commit
`92e1fccb1bdcf1bab7221aa9ed90f9dc72529131` (HEAD at review time) in
[Andrej Karpathy's llm-council](https://github.com/karpathy/llm-council):
[backend/council.py](https://github.com/karpathy/llm-council/blob/92e1fccb1bdcf1bab7221aa9ed90f9dc72529131/backend/council.py)
and [backend/openrouter.py](https://github.com/karpathy/llm-council/blob/92e1fccb1bdcf1bab7221aa9ed90f9dc72529131/backend/openrouter.py).
The source links are pinned to that commit.

## Finding and attribution

IRIS already implements the upstream workflow: concurrent answers, anonymous peer
ranking, and chairman synthesis. Both calculate average observed rank positions.
This is behavioral overlap, not proof of copied source. Local commit
`bbaecca5062e45da66e06f9aa1254a2bd95e5dcf` introduced the IRIS council; its message
and source contain no upstream attribution or provenance statement. Treat Karpathy's
project as the reference for this review without asserting an undocumented lineage.

## Concrete differences

| Area | Upstream | IRIS |
| --- | --- | --- |
| Execution | asyncio/httpx, global model list | Bounded thread pool, provider registry, configurable named seats/roles/chairman |
| Prompts | Same initial question per model | Specialized perspectives plus runtime identity throughout |
| Rankings | Can parse labels without a final-ranking marker | Requires marker, case-insensitive, filters unknown/duplicate labels |
| Aggregation | By model, two decimal places | By candidate label, three decimals, deterministic tie order; repeated model targets remain distinct seats |
| Chairman | Sees model names; aggregate returned as metadata | Sees anonymous evaluations and aggregate scores; identity guides final voice |
| Failures | Client prints errors and returns None; synthesis can return error text; only zero candidates stops early | Requires two successful candidates and a valid review; records partial failures; raises CouncilExecutionError for fatal failures |
| Transport | OpenRouter-specific bearer auth; returns content/reasoning_details | Configurable OpenAI-compatible URL, optional auth, healthcheck, typed text/token metadata, explicit exceptions |
| Extra features | Conversation-title helper | No title request needed for terminal chat |

IRIS preserves all candidate/reviewer targets, rankings, aggregates, chairman
provider/model, and partial failures in CouncilResult. Council total token usage
is still unimplemented. The terminal supplies session-only history through the
brain; routing itself remains based on the current message.

## Reuse decision and terms

No upstream source was copied in this change. Replacing either IRIS module would
repeat existing work and require restoring its abstractions and failure semantics.
Keep the existing pipeline and use upstream as a behavioral reference. An async
transport might be useful for a future async application, but would add dependencies
and interface work to this synchronous terminal. Provider reasoning details and
title generation do not solve a current requirement. Do not adopt permissive ranking
fallbacks or error strings as successful council results.

The inspected upstream root has no LICENSE file (the raw LICENSE URL returned
404), and neither inspected module declares a license. The
[README](https://github.com/karpathy/llm-council/blob/92e1fccb1bdcf1bab7221aa9ed90f9dc72529131/README.md) invites
modification but does not state a formal license or redistribution conditions.
No specific reuse license is asserted here. Before importing source in future,
verify an explicit grant and preserve its required notices and attribution.

## Validation

The existing council tests exercise stages, anonymity, stable labels, aggregation,
partial failures, insufficient candidates, invalid reviews, and chairman failure.
A new brain regression test asserts that CouncilExecutionError propagates unchanged
and neither single-model provider is invoked as a fallback. Full suite command:

```bash
.venv/bin/python -B -m unittest discover -s tests -v
```

All provider responses in these tests are mocked/faked; no live model verification
is implied. The existing terminal work and unrelated files remain preserved.
