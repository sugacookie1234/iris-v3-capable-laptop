# Conversation repair checkpoint

Based on c8533d0 on sprint/evaluation-business-os; no merge or owner-data changes.

Implemented:
- Bounded natural app aliases, including “Can you open the calculator app for me?”
  and “Could you bring up Notepad?”. Exact allowlist and existing approval/executor
  remain authoritative. Negation, quotes and compound requests do not match these
  aliases. This is not a general semantic router.
- Natural Business project creation opens the existing workspace's new form;
  “Show me my business projects” displays saved projects. No new note system.
- Public compound-interest explanation enters ordinary bounded chat history so
  model follow-ups receive the current explanation. Private local answers/results
  remain excluded. General topic correction and private follow-up resolution remain
  unfinished; no broad private-record upload was enabled.
- Time/date requests use an aware machine clock and configured IANA timezone;
  Montreal uses America/Toronto. Frontend time commands use the same backend path.
  DST boundaries and invalid configuration are tested. No model time guesses.
- Speech-only formatting handles supported LaTeX blocks, fenced code, Markdown
  headings/emphasis, link labels and percentages. Unsupported mathematics is
  referred to the screen, not interpreted. Display text stays intact. Existing
  inline literal-code and performed-cue protection remain intact. Currency,
  dates, times and paths are not fully verbalized; values are preserved.
- Organizer refuses note_capture for wake/greeting fragments and leading
  educational questions. Existing owner notes, Undo and Activity are preserved.

Focused commands:
```
.venv\Scripts\python.exe -m unittest tests.test_conversation_repairs tests.test_speech_presentation
.venv\Scripts\python.exe -m unittest tests.test_speech_delivery tests.test_speech_presentation tests.test_desktop_organizer tests.test_conversation_repairs
Get-ChildItem tests/desktop_*_check.cjs | ForEach-Object { node $_.FullName; if ($LASTEXITCODE) { exit $LASTEXITCODE } }
```
Eight focused repair/presentation tests and 71 combined speech/organizer tests
passed. All ten desktop checks passed. Initial full run: 958 tests, one failure,
four skips; failure exposed inline-code cue loss and was fixed without weakening
the assertion. Final full run recorded in VALIDATION.md once complete.

## Exact continuation

1. Review current regression log and run CAP-34 with the new fixtures added after
   confirming its network guards permit any selected desktop test fixtures.
2. Extend safe semantic context for explicit topic correction; keep private records
   excluded by default. Add complete observed-conversation replay coverage.
3. Add opt-in budgeted automatic current-information research; it is NOT enabled.
   Montreal weather is not newly implemented. Never fabricate current facts.
4. Build the separate authenticated Visual Workspace with native lifecycle tests,
   deterministic controls/rate comparison and graceful fallback. Current visuals
   remain in chat; no separate window or decision cards exist yet.
5. Expand speech presentation for dates/currencies/paths and note classification.

No microphone matching, clap, audio-device discovery or chosen voice changes.
No paid service or live provider tests. No real native-window/hardware acceptance.
Security quota/protected-backup backlog remains outstanding. App restart/acceptance
must use trusted launcher pairing, not an unauthenticated homepage-cookie shortcut.

Final checkpoint: speech milestone cdb5449. Full suite 959 run / 955 passed / four skipped, 101.842s. All ten desktop checks passed. CAP-34 includes the new fixtures and passed 82/82 per arm with zero regressions. Punctuated/repeated greetings received an additional 11-test focused pass after the full suite loaded. Working app has not been restarted; physical native/Chrome acceptance remains outstanding. Next commands: run the documented offline evaluation and native trusted-launch smoke checks before expanding to the separate Visual Workspace. No new automatic web research or paid fallback is enabled.
