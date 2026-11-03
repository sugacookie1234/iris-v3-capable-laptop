# IRIS security policy and operator guide

Report suspected vulnerabilities privately to the repository owner through an
available private GitHub channel. Do not publish credentials, vault excerpts,
databases or exploit details containing personal data. This project has no
independent security certification or guaranteed response SLA.

## Security checkpoint and risk register

Baseline inspected: 593cddf, development branch, clean working tree. This is a
targeted server/development review, not a completed whole-repository audit.

| Risk / evidence | Severity | Likelihood and impact | Treatment |
|---|---|---|---|
| Home page issues the session cookie to a local requester (`Handler.do_GET`) | High | Local malicious process can obtain a session and access APIs | OPEN: design native-host bootstrap and browser pairing; cannot isolate against same-user process compromise merely with a cookie |
| ThreadingHTTPServer created handlers without an application limit | Medium | Local connection flood consumes threads | Fixed: maximum 32 handlers; excess connections closed, existing socket timeout retained |
| Rejected POST read an unauthenticated client's advertised body before replying | Medium | Slow client occupied handler until timeout | Fixed: brief 50 ms socket-timeout drain and close connection (Windows reply compatibility) |
| JSON POST accepted ambiguous framing/duplicate fields/non-finite constants | Medium | Parser disagreement or invalid values could reach downstream code; no bypass demonstrated | Fixed: single numeric length, no transfer encoding, duplicate JSON keys and NaN/Infinity rejected |
| Constructor accepted arbitrary bind addresses although normal entry points use loopback | High impact, low likelihood | Future caller could expose local APIs | Fixed: constructor permits only localhost/127.0.0.1 |
| Personal/business SQLite stores remain plaintext (`MemoryStore`, business tables) | High | Same-user malware, copied databases or unprotected backups disclose content | OPEN: opt-in encrypted migration with verified backup/recovery; no existing data migrated |
| Dependencies pinned directly but transitive versions/hashes and action SHAs not fully locked | Medium | Supply-chain replacement or vulnerable transitive package | OPEN: reproducible lock and advisory audit; no vulnerability claim about a particular installed version |
| GitHub checkout persisted credentials by default | Medium | Test/dependency code could access checkout credential | Fixed: persist-credentials false; workflow retains contents:read, no added secrets |
| Visual renderer lacks dedicated adversarial DOM coverage | Medium | Validation/rendering regression could introduce unsafe presentation | OPEN: bounded line schema/text nodes exist; do not treat them as complete XSS assurance |

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
