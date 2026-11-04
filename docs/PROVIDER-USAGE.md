# Provider request accounting

Desktop startup supplies a single durable ledger to every configured model provider.
Standard, deep and Council generation, organizer calls and explicit public research
reserve capacity in the provider adapter, not merely at the HTTP endpoint.
Desktop Fish TTS and transcription additionally reserve capacity around their
existing operations. Local transcription also conservatively counts an attempt;
this is not a claim that Fish was called or charged.

The new provider_usage.sqlite3 stores only random attempt/session IDs, category,
time and state. It contains no prompts, credentials, provider URLs or outputs.
It is plaintext metadata, not a new secret store. Existing owner stores are unchanged.

Defaults per category: 120 admitted attempts per rolling hour, 500 per rolling day,
500 per process session, four concurrent reservations. Owner settings:
IRIS_PROVIDER_LIMIT_HOUR, IRIS_PROVIDER_LIMIT_DAY, IRIS_PROVIDER_LIMIT_SESSION,
IRIS_PROVIDER_LIMIT_CONCURRENT (integer 1..100000). Categories are model, research,
fish_tts and fish_asr. All model providers share one category, conservatively;
there are not independent per-vendor allowances. SQLite BEGIN IMMEDIATE makes
admission atomic across threads/processes using the same ledger. A storage failure
blocks the call. Failed/cancelled requests still count. No automatic retry is added.
Completed means the local operation returned, not confirmed billing or token usage.
No exact cost, token budget or refund is inferred. Paid fallback policy is unchanged.
Council is capped at eight seats/eight workers (at most 17 generation calls), and
each desktop member is independently admitted. Partial execution can consume quota.

Rolling counts survive restart. Active reservations survive a crash and continue
blocking concurrency until reviewed. Wall-clock rollback is conservative (retains
counts); advancing the Windows clock can shorten a window. Same-user malware can
modify the ledger; this is not an OS security boundary. Completed old entries are
pruned after a day except the current process session. Active entries are retained.

## Explicit crash recovery
Stop all IRIS processes and check provider usage before releasing reservations.
Inspect IDs with `.venv\Scripts\python.exe -m iris.usage .local/provider_usage.sqlite3`.
For a reviewed ID only, repeat with `--abandon ID --confirm-app-stopped`.
This does not refund an attempt or restart work. The stop confirmation is an owner
assertion, not automatic process detection. Never delete the ledger to repair quotas.

## Remaining coverage
Standalone terminal/readiness/phone providers constructed without a usage policy,
and standalone Fish speech are not covered by the desktop ledger yet. This is a
high-priority continuation, not a claim of universal provider enforcement. Existing
phone-specific queue limits still apply. Network cancellation cannot undo a request
already received by a provider. No live provider/billing verification was performed.
Rollback source with the app stopped; keep the metadata ledger for future recovery.

Phone launcher continuation: its model and explicit research provider now receive the same checkout ledger as the desktop. Direct library construction without an injected policy and standalone terminal/Fish entry points remain uncovered. Carrier messaging/call accounting still uses the existing phone-specific controls; the new ledger is not a Twilio billing budget. No bridge was started.


## Closeout: default transport policy
Unconfigured OpenAI-compatible adapters now lazily obtain the standard checkout
ledger instead of bypassing admission. This covers terminal/readiness constructions,
Council/research adapters and direct library use. Health checks reserve a separate
diagnostic category; they are not counted as model billing. Standalone Fish synthesis
and the actual Fish ASR helper also reserve at transport entry. Desktop ASR no longer
reserves around local Whisper, avoiding double counting and counting local work as
cloud requests. Desktop streamed TTS retains its injected runtime policy.
The default path is config_path().parent/provider_usage.sqlite3, with owner settings
from effective_environment. Failure to load policy/storage prevents transport.
Application code can still deliberately supply another policy/path; this is host-owned
Python, not a sandbox against malicious same-user code. Custom data-directory desktop
ASR currently uses the standard config ledger; normal launchers share that location.
Transport fixtures use isolated temporary ledgers. No real provider call was made.
