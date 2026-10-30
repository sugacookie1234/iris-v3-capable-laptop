# Background notes briefings

Say or type **“Make a briefing from my notes on architecture.”** IRIS queues the
briefing and leaves chat available. Open **Jobs**, or say **“Show jobs.”** The panel
shows searching, reading and checking sources, followed by an honest outcome.

- **Cancel** stops a queued job or requests an active worker to stop. The final
  state appears once stopping completes; no cancelled result is released.
- **View result** opens the source excerpts explicitly. Finishing a job does not
  insert the excerpts into chat, read them aloud or interrupt an approval.
- **Resume** is available for interrupted or failed jobs with attempts remaining.
  It starts the same topic from the beginning against current notes. It does not
  reuse stale partial reads. A changed configured vault requires a new briefing.
- **Delete** removes a terminal job and its stored result, without changing notes.
  Cancel an active job first.

“Cancel briefing” and “Resume briefing” work when exactly one job qualifies. With
several candidates, use Jobs to choose. “Start a new chat” preserves jobs/results.

IRIS must remain open and the laptop awake. Tray standby can continue running
jobs. Closing or crashing IRIS marks unfinished work interrupted on reopening;
it never silently resumes. This is not a Windows service or a remote worker.

## Scope and limits

Only the fixed [local notes recipe](OBSIDIAN-READING.md) is supported. It searches,
reads up to three notes and checks source revisions and exact excerpt spans.
The outcome is an extractive brief, not independent verification of note claims.
Source text cannot introduce tools, permissions, actions or instructions.

There is one worker, up to four queued jobs, at most five tools/120 seconds per
attempt and three attempts per job. Retries are explicit. Repeating the same
active topic joins its existing job. HTTP callers can supply a request identifier
to `/api/jobs/start`; identical retries return the retained job, while reusing the
identifier for a different topic/vault fails. This dedupe ends when the record is
deleted or expires. These read-only jobs do not establish exactly-once external
writes or general-purpose agent recovery.

The recipe uses no model, search-provider or Fish Audio calls. A spoken command
and the ordinary spoken acknowledgement can still use configured speech credits.
Completion notices are quiet screen notifications, not automatic speech.

## Local storage and privacy

`.local/jobs.sqlite3` stores bounded status metadata plus Windows-account-encrypted
topics and results. No partial raw note text is saved. Result contents are returned
only by the authenticated local detail endpoint when explicitly opened. Job commands
and excerpts stay out of future model prompts and the automatic organizer.

Terminal records expire after seven days; at most 100 total records are retained,
pruning oldest terminal jobs first. Explicit Delete is also available. These
controls affect this store, not independent action receipts or existing backups.
An unreadable encrypted topic appears as an unavailable entry; healthy jobs stay
visible and the damaged job can still be cancelled or deleted when stopped.
The store is ignored by Git. Encryption protects these payloads, not every IRIS
database, and does not make them inaccessible to software running as your account.
Copying the repository to the OMEN does not transfer decryptable job history.

## Upgrade and rollback

This slice adds a separate store and leaves existing databases and vault notes
unchanged. Initialization is repeatable and recovers active records to interrupted.
Cancel or close jobs before rollback. Reverting to source baseline `fd9acb1`
restores foreground briefings and ignores the new job database; keep the database
for recovery after upgrading again. Both supported launchers reserve the same
checkout before initializing storage, preventing a second host from recovering
the first host's live jobs. Do not bypass this guard to share a store across hosts.

General task planning, external-effect recovery, scheduled monitors and delegated
coding agents remain separate design work.
