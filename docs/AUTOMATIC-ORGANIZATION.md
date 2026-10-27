# Automatic organization

With automatic organization enabled, talk to IRIS normally. It picks up clear
commitments, long-term goals, useful notes, deadlines and progress updates from
your messages without requiring “create a task” or a separate approval for each
routine local change. Voice transcripts and typed messages use the same path.

Examples:

| Say | Result |
| --- | --- |
| “I need to submit the report tomorrow at 3 PM.” | Creates a task and schedules its reminder. |
| “I want to learn French.” | Creates a goal without inventing a deadline. |
| “My project uses Python and SQLite.” | Can become a categorized Markdown note. |
| “Move submit the report to Friday at 4 PM.” | Reschedules a matching saved task. |
| “I finished submit the report.” | Completes the matching task. |
| “Show activity.” | Opens the record of automatic changes. |
| “Undo the last change.” | Reverses the most recent eligible automatic change. |
| “Pause automatic organization.” | Pauses new captures and reminder delivery. |

Clear common phrases are processed locally, including firm learning/building
commitments and personal project statements such as “My prototype uses Python.”
Greetings, repeated messages and single questions do not trigger an extra
organization request. Ordinary chat and speech can still use their providers.
Other messages use one bounded
request to the configured FAST model, in the background; this can consume model
credit. No council is used for extraction. A provider failure falls back to the
local phrase parser and is shown in the status line. Unsupported model proposals
show a short reason instead of failing silently. The organizer can miss or
misclassify unusual wording, so Activity is the record of what actually happened.

The current message is the source of permission and evidence. Retrieved files,
assistant replies, quoted examples and reported messages cannot authorize an
automatic action. Unclear or tentative commitments are left alone. An uncertain
deadline produces a question in Activity, which can also be spoken when IRIS is
idle. A follow-up such as “tomorrow at 3 PM” can resolve the latest question.

## Enable it

Run `setup.bat` and set **Automatically organize commitments, goals and notes** to
`true`. Set **Also send due reminders to your own number once Twilio is configured**
to `true` only if you want automatic SMS. Both options default to `false` for a new
installation. Restart IRIS after setup. Activity provides a pause/resume button;
the equivalent voice commands also work. Pausing retains your saved items and
undo history.

Configuration uses `IRIS_AUTO_ORGANIZE_ENABLED` and `IRIS_AUTO_REMINDER_SMS` in
the existing encrypted Windows settings. These settings and provider keys are
local to the Windows account. Configure them again on the OMEN.

## Notes and files

If an Obsidian vault is configured, generated notes are organized below its
`IRIS/` folder with a maintained Markdown index. Without a vault, IRIS uses
`.local/notebook` inside the checkout. The Notes view searches the configured
notebook; the organizer can retrieve relevant notes as context in conversation.

For an existing note, give its exact path relative to the vault, for example
`Update Projects/Plan.md with "The prototype uses Python."`. IRIS adds or updates
its marked section while preserving the surrounding human-written text. To move
a note, name both paths: `Move Inbox/Plan.md to Projects/Plan.md`. A destination
that already exists is never overwritten. Generated notes are categorized
automatically; arbitrary existing files are not bulk-rearranged on startup.

Only bounded UTF-8 Markdown files inside the configured folder are supported.
Hidden files, credentials, repositories, dependency folders, links and junctions
are excluded. Word documents, PDFs, arbitrary system files and email are outside
this feature. Notes and files do not grant new computer-control capabilities.

Every automatic note change has a local preimage and activity entry. Undo checks
that the note still matches the recorded result, so it cannot overwrite a later
manual edit. Task and goal changes retain revision snapshots. Explicit legacy
task/goal commands use their existing revision history; the Activity undo button
applies to organizer-created activity.

## Reminders

The desktop starts a reminder worker with automatic organization. Task reminders
appear **15 minutes before their deadline**, or promptly if created within that
window. A date without a time uses **23:59:59 in the configured timezone**, which
Activity discloses. A goal with a target date gets a **9 AM local check-in** on
that day; a linked task on the same date suppresses a duplicate goal alert.
Undated tasks and goals do not get invented reminder times.

Windows receives a best-effort notification. The app also shows the reminder and
speaks it once it is idle and voice output is enabled. It does not interrupt a
recording, an answer or a pending approval. Windows notification/focus settings
can suppress the system balloon. Mute silences speech; pausing organization
pauses reminder delivery. Dismissing a reminder does not complete its task.

Keep IRIS open and the laptop awake. There is no Windows startup service and no
ability to wake a sleeping computer. On restart, desktop catch-up is limited to
the past day with bounded notification bursts. Completed, removed or rescheduled
items are rechecked before delivery. One event is stored per item/deadline, so
ordinary restarts do not repeatedly announce the same reminder.

Automatic SMS needs the explicit SMS setting plus complete Twilio setup. Restart
the desktop after `setup-phone.bat` so it loads the phone settings. Messages go
only to the saved owner number, respect STOP, and are limited to **two per hour
and ten per day**. Each reminder is shortened to one plain-text SMS segment.
Historical deadlines from before initial SMS activation are not sent. Expired or
rate-limited SMS is skipped; uncertain submissions are not retried. “Accepted”
means provider acceptance, not confirmed delivery. Twilio charges still apply.

The reminder worker sends outgoing SMS directly; keep the separate phone bridge
and HTTPS tunnel running for incoming SMS/call conversations and local opt-out
updates. Twilio itself also enforces its opt-out handling. See [phone setup](PHONE.md).

## Local records and limits

Activity, note backups, reminders, tasks and goals are stored locally in ignored
SQLite databases. These records are not encrypted by the credentials' DPAPI
protection. Relevant notes/context and user messages can reach the configured
cloud model. Automatic organization processes submitted conversations, not room
audio, desktop screenshots or every file on the laptop.

Closing IRIS cancels queued organization work and stops reminder delivery. Check
Activity before closing if its status says it is still organizing. Changes that
have already been saved remain available on the next launch.
