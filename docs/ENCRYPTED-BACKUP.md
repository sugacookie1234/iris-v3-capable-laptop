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
tasks.sqlite3, goals.sqlite3, organizer.sqlite3, action_history.sqlite3 and
jobs.sqlite3. Entire database tables/review decisions are retained. Only these six
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
against same-user malware or pagefile/crash-dump access. Live SQLite remains plaintext.

Creation verifies ciphertext before publishing an encrypted temporary file using
an atomic, no-overwrite hard link (NTFS required; unsupported filesystems fail).
Recovery authenticates before parsing, validates fixed filenames and database
integrity, then stages under the destination parent and renames the completed folder.
It never replaces existing stores. Ordinary failures clean owned staging files.
Abrupt termination/power loss can leave .iris-restore-* plaintext staging files;
secure that recovery destination and remove only verified abandoned staging after
review. Power-loss durability is not claimed. Keep the original archive and source
until you have inspected the restored folder. Switching IRIS to restored data is a
separate owner-controlled operation, deliberately not automated here.
