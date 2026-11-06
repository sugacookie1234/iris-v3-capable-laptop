# Owner-initiated encrypted backups

Stop all IRIS processes first. These commands never run automatically and are not
available as model tools. Use a long, unique recovery passphrase and keep it in a
separate password manager. Losing it means losing access to the archive. Do not
put it in command-line arguments, Git, or beside the backup.

Create (destination must not exist):
```
.venv\Scripts\python.exe -m iris.backup create .local D:\Backups\iris.iris --confirm-app-stopped
```
Restore to a NEW folder only:
```
.venv\Scripts\python.exe -m iris.backup restore D:\Backups\iris.iris D:\IRIS-recovery --confirm-app-stopped
```
Both prompt privately for the passphrase. Creation asks twice. The parent folder
must already exist. The stop flag is an explicit owner assertion; the command does
not prove other processes stopped. Do not take multi-store snapshots while IRIS runs.

Included when present: memory.sqlite3 (including Business and Task memory tables),
tasks.sqlite3, goals.sqlite3, organizer.sqlite3, action_history.sqlite3,
jobs.sqlite3 and projects.sqlite3. Entire database tables/review decisions are retained. Only these seven
fixed filenames are accepted. Config/credentials, usage ledgers, session tokens,
external Obsidian files, managed note files and temporary caches are excluded.
This is a database backup foundation, NOT a complete vault/files/settings backup.
Conversations exist only to the extent already persisted in these stores; transient
chat history cannot be recovered. Reconfigure secrets and paths on a new machine.

The snapshot uses SQLite's backup API into memory and integrity_check. Job topic
and result blobs are unprotected inside that in-memory snapshot, then encrypted
inside the archive. Recovery re-protects them under the destination Windows account.
Other record IDs, review states and references are preserved. Existing vault-path
bindings may require explicit reconfiguration after moving machines; no automatic
job replay or memory approval is performed. Cross-machine hardware acceptance is
still required; tests verify synthetic conversion on the current Windows account.

Encryption uses PyCA cryptography 50.0.2 Fernet authenticated encryption with a
Scrypt-derived key (N=131072,r=8,p=1), a fresh 16-byte salt and the owner passphrase.
No key is stored. The format contains a version marker, salt and Fernet token.
Fernet exposes creation time; archive size is also visible. Source:
https://cryptography.io/en/latest/fernet/ . Dependency provenance:
https://pypi.org/project/cryptography/ . Pinning does not certify the dependency.

At most 64 MiB of database bytes are accepted; large archives fail closed. The
process needs memory for multiple copies and the 128 MiB KDF. Plaintext snapshots
exist in process memory; Python cannot guarantee zeroization. This does not defend
against same-user malware or pagefile/crash-dump access. Other live SQLite stores remain plaintext; project envelopes use account-bound DPAPI.

Creation verifies ciphertext before publishing an encrypted temporary file using
an atomic, no-overwrite hard link (NTFS required; unsupported filesystems fail).
Recovery authenticates before parsing, validates fixed filenames and database
integrity, then stages under the destination parent and renames the completed folder.
It never replaces existing stores. Ordinary failures clean owned staging files.
Abrupt termination/power loss can leave .iris-restore-* staging files containing other plaintext stores (project payloads are already reprotected);
secure that recovery destination and remove only verified abandoned staging after
review. Power-loss durability is not claimed. Keep the original archive and source
until you have inspected the restored folder. Switching IRIS to restored data is a
separate owner-controlled operation, deliberately not automated here.


## Project portability (M5.1)

Project support extends archive version 1 without changing its marker, KDF or cipher.
New IRIS restores old archives without projects. Older IRIS rejects archives containing
projects.sqlite3 as an unknown store before restoration; it does not silently omit it.

For projects, exact SQL schema/version, integrity, ten-project bound and M5 envelope
validation run before conversion. Any unreadable record aborts the whole backup.
Source-account DPAPI is removed only in RAM. Validated JSON envelopes are rebuilt
in a clean in-memory database, then included inside the passphrase-encrypted archive.
Restore validates portable records and encrypts them with destination-account DPAPI,
verifies decryption/schema again, and rebuilds a clean database before staging it.
This avoids leftover plaintext in SQLite freelist/overflow pages. No project plaintext
is intentionally written to disk; Python memory, pagefiles and crash dumps remain
outside that guarantee. Project IDs and SQLite structure remain visible in the live
store; the archive encrypts all database content. Paths through symlinks/junctions
are refused. This is not protection against same-user malware racing filesystem paths.

Restoration retains identities, revisions and historical references, never active
project selection, PlanRun objects, confirmation tokens or permissions. Missing
ActionHistory evidence means unverified progress. Missing/changed task revisions
block subsequent execution. A new preview and current approvals are always required.
Workspaces, settings and credentials must be explicitly configured on the new host.

If records cannot be unlocked, keep the original files. `/project recovery` shows
options without opening the store, modifying data or calling a model (also available
when the experimental interpreter is off). Recover using the original Windows account
or a valid portable archive and its passphrase; corruption and lost passphrases cannot
always be repaired. No cleanup/quarantine or automatic migration is performed.

Synthetic tests use independent account codecs and real single-account Windows DPAPI.
Physical cross-account/cross-device acceptance remains open. Validate the restored
copy before retiring the original. The --confirm-app-stopped flag remains a caller
assertion, not a process-wide lock or proof that every IRIS process has stopped.
