# Updated closeout — Unified Intelligence foundation

This section supersedes the older checkpoint below. User authorised the first
local-only orchestration slice after critical provider/authority work; separate
native Visual Workspace and unrestricted tool execution remain out of scope.

Commits after 875bbed:
- aafc173: default durable accounting for standalone/model/diagnostic/Fish paths.
- c686f6c: bounded compound-interest orchestration, public-only context and private
  local command-result history isolation; existing authority remains in force.
- 171558d: 50ms bounded drain for rejected phone requests, preventing Windows reset
  without waiting on an attacker-advertised body. Seventeen phone-server tests pass.

Read ORCHESTRATION-SPRINT.md for interfaces and exact five-turn replay. First expanded
CAP-34 passes 100/100 per arm, zero regressions; all eleven desktop JS checks pass.
Configured-secret scan of all files changed since 875bbed: zero matches. This is not
repository-history scanning. Full corrected regression: 994 run, 990 passed, four skipped (101.607s); see VALIDATION.md.

Remaining: live SQLite plaintext; incomplete file/settings/phone backup inclusion;
transitive locking/current advisories; native pairing/session-expiry acceptance;
secondary-window ownership; cross-machine recovery. None is represented as closed.
Host Python can deliberately inject a different provider policy; this is not an OS
sandbox. Default ASR uses the standard config ledger even with a custom desktop
folder. Request counters do not prove billing or cancel an already received request.

Privacy fix: the final local answer now determines history inclusion. Private tool
results never become cloud context merely because they were dispatched after the
awareness handler. Public educational context stores only a canonical topic and
verified local output, not arbitrary user asides. Historical transmission was not
investigated; no owner data or pending reviews were edited.

Exact continuation: perform native acceptance of the five-turn replay, then extend
bounded shared context with typed verified-result references and explicit privacy
rules. Pending approvals remain in the old authoritative runtime, not in skills.
Do not implement a privileged visual bridge or broaden tool execution implicitly.
For security maintenance, prioritise native/session acceptance and backup recovery
coverage; see ENCRYPTED-BACKUP.md and PROVIDER-USAGE.md. No paid test is authorised.

Reproduce:
```
.venv\Scripts\python.exe -m unittest discover -s tests
.venv\Scripts\python.exe -m unittest tests.test_orchestration tests.test_orchestration_authority tests.test_provider_adapter tests.test_phone_server
.venv\Scripts\python.exe -m iris.generalist.evaluation --output .local/orchestration-evaluation
Get-ChildItem tests/desktop_*_check.cjs | ForEach-Object { node $_.FullName; if ($LASTEXITCODE) { exit $LASTEXITCODE } }
```
Rollback only source commits with IRIS stopped; retain all owner databases and the
usage ledger. No database migration is required for the session-only skill. No app
restart, real microphone test, paid call or live owner backup/restore was performed.
Main remains b4e5c9636d02657cb3cd89d368583ee6c8ebd006.

## Earlier checkpoint (historical)

# Security continuation checkpoint — 2026-11-03

Development branch: sprint/evaluation-business-os. Implementation checkpoint:
41c0c91. Final documentation commit follows this file. Main remains
b4e5c9636d02657cb3cd89d368583ee6c8ebd006. No merge. No live owner-data migration,
backup/restoration, credential change, paid provider request or bridge activation.
No native process restart or hardware acceptance was performed.

## Completed coherent milestones
- e8f3d29: retained unfinished visual changes; exact frontend schema, hostile DOM
  fixtures and CI check. CAP-37 remains an in-chat static chart, not a new window.
- 56e18a9: CAP-29 durable desktop provider ledger, atomic reservations, hour/day/
  session/concurrency ceilings, failure accounting and owner crash recovery;
  eight-seat/eight-worker Council hard cap. No monetary/token billing claims.
- e547493: CAP-29 explicit passphrase-encrypted database backups, job payload
  portability conversion and new-folder-only restoration. No live DB encryption.
- 5e8020e: phone framing hardening, existing-action SHA pins, clock/ledger eval cases.
- 41c0c91: phone launcher shares checkout provider ledger; adapter assertions stay
  in ordinary regression while offline evaluation keeps blanket provider blocking.
Earlier completed speech/HTTP work: 3f9afd6 and 385f5be, preserved unchanged.

## Verification
- Full unittest discovery: 982 run, 978 passed, four skipped, 99.923 seconds.
  Log: .local/security-final-20261103.log.
- Subsequent phone policy injection/test split: 23 focused tests passed.
- All eleven desktop JS checks passed, including new visual-security check.
- CAP-34 final: 92/92 per arm, zero regressions; .local/security-evaluation-final.
- Encrypted backup: five synthetic tests passed (including temporary DPAPI jobs).
- Phone server/security/service/store/assistant: 85 tests passed.
- pip check: no broken requirements. This is not an advisory audit.
- Configured-secret scan on then-current changes: zero matches. Not history scanning.
- Initial expanded eval failed two tests because its provider guard intercepted
  adapter entry tests. Moved unchanged assertions to test_provider_adapter.py;
  no guard or assertion was weakened. Earlier full provider run: 975/971/4.

Automated fake DOM is not real browser-engine or physical display acceptance.
No microphone, device matching, clap hardware, carrier or paid-provider verification.
The chosen Fish voice was not changed. Cross-machine restoration is unverified.

## Remaining risk register / exact next work
1. HIGH coverage gap: standalone terminal/readiness/Fish and direct provider library
   construction can lack durable policy. Desktop and phone launchers are covered.
   Trace all entry points, inject a shared policy without giving tests live paths,
   test partial Council exhaustion and actual failure/cancellation boundaries.
   Limits are per category, not configurable per vendor; no usage-token ceiling.
2. HIGH data exposure: live SQLite is plaintext. Backup excludes vault/managed note
   files, portable settings, phone.sqlite3 and provider_usage.sqlite3. Add typed,
   owner-selected files/settings and phone payload migration only after reviewing
   their codecs. Preserve pending states; never bulk-copy credentials.
3. MEDIUM recovery exposure: abrupt termination may leave plaintext restore staging;
   stop assertion is not process detection. Test real cross-account recovery and
   interrupted process termination, file ACLs and path rebinding. Do not auto-switch
   live data. See ENCRYPTED-BACKUP.md and PROVIDER-USAGE.md for operator recovery.
4. MEDIUM session residuals: native/Chrome launch/restart acceptance, session expiry
   and recovery, and secondary-window ownership remain pending. No secondary window
   was implemented. Pairing single-use/concurrent tests remain intact.
5. MEDIUM supply chain: action pins fixed; transitive/hash locking, current advisory
   audit and masked Git-history secret review remain incomplete. No certification.
6. Existing authority/prompt-injection regression tests passed as part of full suite,
   but this continuation did not comprehensively re-audit every tool approval path
   or source trust boundary. Extend malicious note/web/business fixtures and stale
   approval replay tests before broader orchestration. Never grant model authority.
7. Phone review is source/synthetic only. Signature alone is not freshness;
   replay relies on store IDs/retention. Carrier budgets use existing phone controls,
   not the new model ledger. Keep the bridge off until explicitly configured.
8. Natural arbitrary prose currency/date/path formatting and real speech acceptance
   remain separate from the completed structured clock fix.

Do not begin Unified Intelligence/Visual Workspace feature work yet.

## Rollback and owner operation
Stop IRIS before rolling back source commits; retain every existing database and
.local directory. The provider ledger is additive metadata, not a destructive schema
migration. Retain it across rollback; never clear counts as a repair. Crash recovery
is explicit via python -m iris.usage and an exact reservation ID after owner review.
Backup restoration only creates a new folder. Keep original archives/source data
until manually verified; lost passphrases cannot be recovered. Reconfigure provider
credentials separately on another Windows account. No owner action was automated.

## Reproduction commands
```
.venv\Scripts\python.exe -m unittest discover -s tests
.venv\Scripts\python.exe -m unittest tests.test_provider_usage tests.test_provider_adapter tests.test_backup tests.test_bootstrap tests.test_natural_clock
Get-ChildItem tests/desktop_*_check.cjs | ForEach-Object { node $_.FullName; if ($LASTEXITCODE) { exit $LASTEXITCODE } }
.venv\Scripts\python.exe -m iris.generalist.evaluation --output .local/security-evaluation-final
```
Windows DPAPI synthetic tests need the Windows account protection context. Do not
replace failing encryption with plaintext to make restricted test runs pass.

## Exact implementation files changed since 385f5be
- .github/workflows/tests.yml
- SECURITY.md
- docs/ENCRYPTED-BACKUP.md
- docs/IRIS_DECISIONS.md
- docs/PROVIDER-USAGE.md
- docs/VALIDATION.md
- iris/backup.py
- iris/brain/council.py
- iris/brain/providers/openai_compatible.py
- iris/desktop/runtime.py
- iris/desktop/server.py
- iris/generalist/evaluation.py
- iris/phone/__main__.py
- iris/phone/assistant.py
- iris/phone/server.py
- iris/usage.py
- requirements.txt
- tests/desktop_visuals_check.cjs
- tests/test_backup.py
- tests/test_phone_server.py
- tests/test_provider_adapter.py
- tests/test_provider_usage.py
- web/visuals.js

Native workspace continuation: independent single-use visual bootstrap leaves main pairing intact; visual reads/edits require the existing cookie plus a short-lived revocable window lease. Revisions reject stale/duplicate mutations. Real local WebView2 synthetic smoke passed the functional window path, with separately resolved temporary-profile cleanup. Same-user malware, main-session expiry and target-hardware acceptance remain limitations. See VISUAL-WORKSPACE-SPRINT.md.

## Native workspace continuation checkpoint — 2026-11-04
Implementation commits on sprint/evaluation-business-os:
- 64bff37: authenticated native child and shared interactive scenario.
- d9bbaf7: keyboard activation and same-window lease renewal.
- 430c2c9: personal commitments retain the normal organizer path.
- 5d3994e: natural workspace/starting-amount aliases.
- 82dab9d: dirty-form revision isolation and simulated DOM race regression.

No live data migration, paid calls, voice changes or main-branch merge. The original
main commit remains b4e5c9636d02657cb3cd89d368583ee6c8ebd006. Exact changed-file list
and remaining native acceptance sequence: VISUAL-WORKSPACE-SPRINT.md. Exact results
and unsuccessful attempts: VALIDATION.md. Native smoke uses only temporary synthetic
data; profile cleanup may be deferred while WebView2 retains files. Do not delete
owner profiles to clean up a synthetic test.

Next: complete physical keyboard/audio, OMEN, multi-monitor and long-expiry checks.
Then begin the separately scoped disposable-environment security/red-team sprint.
Review cross-window auth, injection, approvals, data exposure, dependency advisories
and quotas. Do not mark that sprint complete from these unit tests. Unified
Intelligence 2.0 and broader integrations follow it, not this sprint.

Recovery commands from the repository root (no reset or clean):
1. git status --short; git log -6 --oneline
2. .\.venv\Scripts\python.exe -m unittest tests.test_visual_workspace tests.test_bootstrap tests.test_orchestration tests.test_desktop_app
3. node tests/desktop_workspace_check.cjs
4. .\.venv\Scripts\python.exe tests/native_visual_workspace_smoke.py
5. .\.venv\Scripts\python.exe -m unittest discover -s tests
6. .\.venv\Scripts\python.exe -m iris.generalist.evaluation --output .local/visual-workspace-recheck
Run native smoke and the full regression sequentially. The smoke opens synthetic
windows; no owner runtime restart or hardware audio acceptance is implied.

Final verified checkpoint: 1003 Python passes/four skips (1007 run), twelve desktop
JS checks passed, CAP-34 109/109 each arm with zero regressions, and isolated real
native smoke passed with zero provider calls. Implementation HEAD: 82dab9d; the
following documentation-only commit records this checkpoint. Working-tree changes
at this point are only these closeout docs; no unfinished implementation remains.
Transient test failures and limits are preserved in VALIDATION.md. Push this
development branch; do not merge main. Owner hardware acceptance remains pending.


## Security assessment checkpoint — 2026-11-04
See SECURITY-PENTEST-REPORT.md. Baseline 008f453 was clean. Commit 2d8fc7f
repairs confirmed HIGH visual-bootstrap privilege escalation using independent
localhost visual / 127.0.0.1 main origins and credentials on one listener/runtime.
Commit d319da4 pins a hash-verified installer update before setup/CI dependencies.
Live pip 24.3.1 update failed with WinError 5; do not claim it patched or change
permissions automatically. Source/runtime dependencies and owner data are preserved.

Actual bounded raw-HTTP and native WebView2 adversarial probes were conducted only
against temporary synthetic instances. Native visual-to-main fetch is blocked.
A separate same-agent challenge pass is documented; no external independent test.
The intermittent native reopen failure reproduced with renderVisual unavailable,
then passed in later isolated runs. Its root cause remains unresolved. No timeout
or assertion was weakened. Synthetic profile cleanup may be delayed by WebView2.

Continuation: review the exact evidence and final regression below, resolve the
installer permissions through an owner-controlled environment repair, investigate
native asset readiness and complete long-session/OMEN acceptance. Keep private
SQLite/backup-staging/ACL and model-semantic limitations explicit. Unified
Intelligence 2.0 is the next major feature, not part of this assessment. Do not
expand permissions or merge main. Reproduce with tests.test_security_redteam and
tests.test_redteam_authority; native smoke must run separately from the full suite.
