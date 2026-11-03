# Reviewed task memory

Open **Jobs → Task memory**, or say **“Show task memory”**. Completed local
notes briefings propose a summary automatically. This first CAP-33 slice covers
only the fixed search/read/draft recipe, not general learning from conversations.

- **Keep** makes a summary available to local notes-plan previews.
- **Dismiss** excludes it; **Mark incorrect** revokes reuse of a kept summary.
- **Forget** removes it. A temporary one-way fingerprint prevents the retained
  source job from immediately recreating it.
- Refresh before reviewing a changed item: stale review versions are rejected.

Ask **“Plan a briefing from my notes on architecture”** to see reviewed guidance.
Only kept, unexpired summaries from the same configured vault contribute. A partial
briefing contributes a coverage caution, not a claim of complete success. Guidance
does not change permissions, execution steps, models or code, and uses no model call.

## Evidence and privacy

Each proposal records job ID, attempt, completion time, source count, outcome and
source-check status. Text is fixed from validated metadata. Topics, source paths,
excerpts, result text and errors are not copied into task memory. Source revision
and excerpt matching does not independently fact-check the note's claims.
Provenance identifies a historical job; it is not a promise that its sources remain
unchanged or that the source job is retained indefinitely.

Pending summaries expire seven days after completion; reviewed summaries expire
30 days after completion. Review does not extend that lifetime. At most 100 are
retained. Deletion markers expire with the source's seven-day eligibility window;
their cap is 1,000. Overflow conservatively excludes older unseen completions.

The additive `experiences` and `experience_source_markers` tables share the local
memory database, but stay outside personal-memory retrieval, exports and provider
context. Capture failures leave completed jobs intact; opening task memory retries
capture from retained evidence. Repeated capture and restart are idempotent.
Rolling back to `a23ff9f` ignores these additive tables; it does not erase them.

## Remaining design work

General success/failure traces, broader pattern retrieval and demonstrated outcome
improvement remain pending. Next is CAP-34's offline evaluation harness with
regression and prompt-injection cases before extending learning or delegation.
