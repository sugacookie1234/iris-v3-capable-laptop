# IRIS security policy and operator guide

Report suspected vulnerabilities privately to the repository owner through an
available private GitHub channel. Do not publish credentials, vault excerpts,
databases or exploit details containing personal data. This project has no
independent security certification or guaranteed response SLA.

## Current assessment checkpoint

See docs/SECURITY-PENTEST-REPORT.md for the 2026-11-04 source-assisted local
adversarial assessment. Confirmed HIGH visual bootstrap privilege escalation was
reproduced over HTTP and repaired with separate window origins/cookies. A live OSV
lookup flagged the old pip; stabilization repaired it offline under the file-owning
account. Pip 26.2 and dependency consistency are verified. Native reliability remains
an open gate. Setup applies a hash-pinned tooling update before dependencies.
Earlier chronological entries below are historical, not the current release gate.
No external independent penetration test or security certification is claimed.

## Security checkpoint and risk register

Baseline inspected: 593cddf, development branch, clean working tree. This is a
targeted server/development review, not a completed whole-repository audit.

| Risk / evidence | Severity | Likelihood and impact | Treatment |
|---|---|---|---|
| Former homepage session issuance | High, mitigated | Unauthenticated local GET formerly acquired API access | Fixed in c8533d0: expiring single-use trusted-launch pairing. Same-user malware remains outside this boundary. |
| ThreadingHTTPServer created handlers without an application limit | Medium | Local connection flood consumes threads | Fixed: maximum 32 handlers; excess connections closed, existing socket timeout retained |
| Rejected POST read an unauthenticated client's advertised body before replying | Medium | Slow client occupied handler until timeout | Fixed: brief 50 ms socket-timeout drain and close connection (Windows reply compatibility) |
| JSON POST accepted ambiguous framing/duplicate fields/non-finite constants | Medium | Parser disagreement or invalid values could reach downstream code; no bypass demonstrated | Fixed: single numeric length, no transfer encoding, duplicate JSON keys and NaN/Infinity rejected |
| Constructor accepted arbitrary bind addresses although normal entry points use loopback | High impact, low likelihood | Future caller could expose local APIs | Fixed: constructor permits only localhost/127.0.0.1 |
| Personal/business SQLite stores remain plaintext (`MemoryStore`, business tables) | High | Same-user malware, copied databases or unprotected backups disclose content | OPEN: opt-in encrypted migration with verified backup/recovery; no existing data migrated |
| Dependencies pinned directly but transitive versions/hashes and action SHAs not fully locked | Medium | Supply-chain replacement or vulnerable transitive package | OPEN: reproducible lock and advisory audit; no vulnerability claim about a particular installed version |
| GitHub checkout persisted credentials by default | Medium | Test/dependency code could access checkout credential | Fixed: persist-credentials false; workflow retains contents:read, no added secrets |
| Visual rendering trust boundary | Medium residual | Rendering regression could introduce unsafe presentation | Exact fields, bounded numeric data and text-only DOM sinks tested. Simulated DOM tests are not browser-engine XSS certification. |

## Boundaries and residual exposure

Desktop Host/origin/session checks defend browser-origin boundaries, not hostile
same-user Windows software. Keep the server on loopback; never tunnel it publicly.
The separate phone bridge requires its own signature/owner/PIN checks and must not
inherit desktop authority. Phone implementation has not been re-audited in this
checkpoint. CAP-38 decision cards are not implemented; there is no new approval
mechanism to audit. Existing host-owned ToolExecutor approvals remain authoritative;
external text and memory cannot grant permissions. Council consensus is not consent.

Windows configuration uses account-scoped DPAPI. This does not encrypt all SQLite
records or protect against malware executing as the same user. Encrypted config
and jobs generally cannot be moved to another Windows account by copying files;
re-enter credentials through setup on the new account. No recovery key was added.
Do not delete the old account or its protected data before checking recovery.

Configured reasoning providers receive submitted prompts/context; speech providers
receive voice/text as configured. Local workflow tests do not prove provider
privacy. Never include secrets in prompts or business evidence. Use offline fixtures
for development. No provider requests or credential rotation are authorized by a
security test command.

## Incident response and recovery

Quit IRIS and its phone bridge if compromise is suspected. Preserve a restricted
copy of relevant metadata without posting private databases. Review provider usage
and rotate affected keys through provider dashboards after owner confirmation.
Keys previously pasted into chat should be considered disclosed to that channel;
rotate them if still active. This checkpoint did not scan Git history or establish
whether those keys are still active. Never print keys or rewrite Git history as
an automatic response.

Quit the app before backing up all related databases/configuration. Restrict backup
access and use an encrypted Windows backup destination; ordinary file copying does
not create encryption. This patch has no data migration: rollback its source commit
without changing databases. Deleted live rows may remain in existing backups.

## Verification and continuation

Run `python -m unittest tests.test_desktop_security` for synthetic raw HTTP framing,
duplicate headers/JSON, no-body unauthorized rejection, bind and capacity checks.
Run `python -m unittest discover -s tests` and desktop JS checks for regressions.
No external penetration test or live provider check was performed.

Next priorities: authenticated native/browser bootstrap; per-endpoint rate limits
and expensive-operation quotas; opt-in encrypted business backup/export with
interrupted recovery tests; dependency lock/advisory and secret-history audit;
visual DOM adversarial testing; fresh phone and approval/replay audits. Preserve
all existing owner records and review states. Never promote policies automatically.

## Bootstrap continuation
Homepage no longer issues sessions. Trusted native and Chrome launchers mint 60-second, single-use pairing tokens carried in a URL fragment; local pair.js removes the fragment before redeeming via same-origin POST. The authenticated page also loads pair.js to clear launch fragments on an already-paired window. Ten failed token redemptions per minute block further redemption temporarily. Same-user malware can inspect launch arguments/memory; this is not an OS security boundary. No-browser mode does not currently provide manual pairing. 28 focused tests pass; actual WebView/Chrome/microphone acceptance and full regressions remain pending. Restart is required to load changes. No data migration. Continue with browser pairing recovery, quotas and protected backups.

## Admission control checkpoint — 2026-11-03
Authenticated POST requests share process-local counters across windows. Defaults
(per minute / concurrent / per process session): chat 30/2/500; transcription
30/1/500; job submission/resume 10/2/100; selected database operations 60/4/2000;
all authenticated POST 240/8/20000. Actual streamed TTS calls use 60/2/1000.
Owner configuration keys: IRIS_LIMIT_<GROUP>_PER_MINUTE, _CONCURRENT and
_PER_SESSION, where GROUP is CHAT, TRANSCRIBE, JOBS, DATABASE, HTTP or VOICE.
Positive integers only (1..100000); invalid values fail startup rather than disable
limits. No settings UI was added. Quota rejection returns 429 with no automatic
retry. Admitted failed/cancelled attempts consume count; concurrency releases in
finally. These counters do not represent monetary cost or confirmed provider usage.

Residual HIGH resource risk: Council fan-out and non-desktop provider entry points
lack shared provider-level accounting. GET database reads remain outside this new
quota; socket handlers remain capped at 32. Counters reset on process restart and
are not durable budgets. Existing pairing failed-token limit remains independent.
No new paid provider fallback was enabled. Provider timeout/cancellation semantics
are unchanged; a disconnected client may still finish an upstream request.

Concurrent bootstrap redemption now has an eight-contender test: exactly one wins.
Authenticated HTTP quota tests prove a rejected chat does not execute the runtime.
Native/Chrome restart acceptance and session-expiry improvements remain pending.
Rollback source commits with IRIS stopped; no database migration or owner-data
operation occurred. Do not delete .local. Portable encrypted backups remain absent;
cryptography is not installed in this environment, and no custom cipher was added.


## Durable desktop provider accounting
See docs/PROVIDER-USAGE.md. Desktop-created provider adapters now enforce shared
hour/day/session/concurrency admission, including Council fan-out and research.
The new content-free SQLite ledger survives restart; unfinished reservations fail
closed until explicit owner-reviewed recovery. Council has a hard eight-seat cap.
Standalone phone/terminal/Fish entry points remain an OPEN high-priority coverage
gap. No billing amounts or confirmed usage units are inferred. This supersedes the
earlier statement that desktop Council calls lack provider-level accounting.

## Encrypted backup foundation
Owner-run portable database archives and new-folder restoration now exist; see
 docs/ENCRYPTED-BACKUP.md for exact inclusion/exclusion and recovery steps.
The earlier absent-backup/dependency statements are superseded: cryptography
50.0.2 was installed and pinned. Five synthetic backup tests pass. Live databases
remain plaintext; vault/managed files and portable settings are NOT included.
Same-user malware, plaintext recovery staging after abrupt termination and
cross-machine path rebinding remain limitations. No owner data was migrated.

## Phone and supply-chain review (2026-11-03)
Read phone/security.py, server.py, service.py and assistant.py. Callback signatures
use the configured public URL, not forwarded headers. Account/owner/destination
checks, per-call PIN attempts, token/SID deduplication and isolated conversation-only
assistant remain intact. Tightened callback framing: one Content-Type, ASCII numeric
length and no Transfer-Encoding (even empty). 85 synthetic phone boundary/service/
store/assistant tests pass. No calls, SMS, account access or bridge activation.
Residuals: signature validation is not a timestamp/freshness proof; replay prevention
depends on existing service/store IDs and retention. Phone provider calls still need
the new durable policy. The signature/PIN review is not an external penetration test.

Existing checkout v4, setup-python v5 and setup-node v4 actions now use exact commits
resolved from their official GitHub tag refs; contents:read and persist-credentials:false
remain. Runtime packages remain direct-version pinned, not fully transitive/hash locked.
No comprehensive current-advisory or repository-history secret audit was completed.
No broad dependency upgrades were performed; only the requested backup dependency
was added. Pinning and package consistency checks are not vulnerability certification.

Phone launcher continuation: its model and explicit research provider now receive the same checkout ledger as the desktop. Direct library construction without an injected policy and standalone terminal/Fish entry points remain uncovered. Carrier messaging/call accounting still uses the existing phone-specific controls; the new ledger is not a Twilio billing budget. No bridge was started.


## Critical provider closeout
The prior silent default-policy gap is closed for OpenAI-compatible generation and
diagnostic HTTP, standalone Fish TTS and Fish ASR. Default paths now reserve in the
standard durable ledger; explicit desktop/phone policy injection is preserved.
103 mocked transport tests pass with temporary ledgers. Deliberately modified Python
or injected custom providers remain outside the threat boundary. No budget is actual
billing, and clocks/ledger access retain the documented same-user limitations.


## Local-result history isolation
Confirmed ordering bug in DesktopRuntime.chat: the private/public flag was computed
before DesktopCommands.handle, so a subsequent local command result could enter
ordinary model history. Fixed by classifying the final local answer. Local replies
are private unless explicitly host-marked public; compound examples use canonical
public queries, not raw owner asides. Synthetic regression verifies private markers
never reach FakeBrain/history. No historic cloud transmission was investigated or
claimed. Existing saved conversations were not modified.

## Native Visual Workspace boundary
The secondary native window uses an independent 60-second single-use bootstrap and
a 15-minute in-memory lease, in addition to the existing session cookie and origin
checks. Public IDs and revisions are not authorization. Closing revokes the lease;
explicit reopen renews it. Replay, concurrent redemption, cross-origin updates,
missing credentials and revoked leases have synthetic HTTP regression coverage.
The window renders bounded host-validated chart data using the existing safe SVG
renderer. It has no privileged JavaScript bridge and cannot approve computer actions.
Only public hypothetical scenario data is supported. This is not protection against
malware executing as the same Windows user or trusted-origin code compromise.
Rollback: revert the native-workspace sprint commits on the development branch;
there is no owner-data migration to reverse. Do not remove local databases/profiles.

## Stabilization closeout continuation

Stabilization supersedes the installer blocker: local pip 26.2 verified after a hash-verified offline installation under the existing file-owning account; pip check passes. No ACL or administrator-right changes. See docs/STABILIZATION-CLOSEOUT.md. Native asset/readiness failures remain an explicit release gate; deterministic startup checks and recovery were added without weakening IRIS-SEC-001.

## Experimental semantic interpretation

Default-off M1/M2 adds no tool permissions. Host-owned turn IDs, bounded typed JSON,
context revisions and current owner intent gate compound changes; all calculations
and action receipts remain host-generated. Root listing goes through existing
ToolExecutor permission checks and stays outside cloud history/synthesis. Provider
admission is unchanged and tested with fake transport. Generated text is not an
approval. This is not a prompt-injection guarantee or a general reasoning sandbox.
See docs/UNIFIED-INTELLIGENCE-2-DESIGN.md for narrow eligibility and remaining limits.
Native authentication and the unresolved WebView2 reliability gate are unchanged.
