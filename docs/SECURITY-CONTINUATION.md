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
