# Security and native reliability stabilization — 2026-11-04

Baseline 17cbb9e, clean development branch. No main merge, owner-data migration,
credential changes, voice changes, microphone matching or live provider test.

## Pip repair — verified
Installed pip was 24.3.1. Existing metadata was owned by the restricted execution
account, with FullControl for that account but no delete permission granted to
ordinary Users. The earlier normal-account installer failed removing AUTHORS.txt.
Exclusive read/write open under the owning account passed: no persistent file lock
was demonstrated. File attributes did not establish antivirus interference, and
no antivirus controls were changed. Different execution identities and ACLs explain
the observed access discrepancy; not every possible Windows denial was audited.

An owning-account online attempt stalled and was stopped only after identifying
that task's exact pip command/process. Pip remained importable. Downloaded only the
hash-pinned pip 26.2 wheel with the existing network-capable identity, then installed
offline under the existing file-owning identity:

```
python -m pip download --disable-pip-version-check --no-deps --only-binary=:all: --require-hashes --index-url https://pypi.org/simple -r requirements-tooling.txt --dest .local/tooling-wheel
python -m pip install --no-index --find-links .local/tooling-wheel --disable-pip-version-check --no-deps --only-binary=:all: --require-hashes -r requirements-tooling.txt
```

Use the checkout's .venv/Scripts/python.exe. No ownership/ACL edits, administrator
grant, recursive deletion, environment replacement or dependency upgrades occurred.
Verified `pip 26.2` and `pip check`: no broken requirements. The interrupted uninstall's
`~ip-24.3.1.dist-info` was checked for exact package/version and non-reparse location,
then preserved under `.local/pip-recovery-20261104/stale-pip-24.3.1.dist-info`.
Subsequent pip check had no invalid-distribution warning. Do not put that stale
metadata back alongside the new pip. The active environment was not replaced.

## Deterministic visual startup and recovery
Pairing now exposes a completion promise: ready, redirecting or error. No-token
pages no longer change history unnecessarily. A visual page waits for successful
pairing and actual renderer availability before polling state. A missing renderer
loads the fixed same-origin /visuals.js and verifies execution in onload; failure
offers an explicit retry. No arbitrary URL or generated script can be loaded.
Closing during loading cancels subsequent work. No timeouts were increased.

Frontend readiness reports authenticating, loading-renderer, ready, rendered,
asset-error, expired or no-example. Native created/open still means only a window
exists; neither is evidence of rendering. An always-present same-origin reload link
works even if the application entry script itself failed to execute. It grants no
authentication and cannot recover an expired lease; ask IRIS to reopen for that.

Observed evidence isolates multiple asset-readiness failures, not one proven
WebView2 root cause: historical renderer missing; this sprint captured a pairing
landing without execution, and a loaded renderer with the workspace script not
executed (resource status 200, decoded size zero). Resource timing alone cannot
prove that the server sent an empty body. Cache/engine/transport cause remains
unresolved. The new readiness gate covers missing renderer and pairing races but
is not claimed to solve every native startup failure.

## Bounded native test evidence
The opt-in fixture uses temporary stores/profile, fake brain, blocked Python
provider HTTP, mocked dashboards and disabled native microphone updates. Two
additional open/update/UI/close/reopen cycles and forced visual-lease expiry are
bounded by a 120-second scenario deadline and existing per-check deadlines.
Expiry is accelerated in synthetic server memory, not a 15-minute hardware soak.

Development attempts exposed test defects: submitting immediately after a voice
revision correctly yielded 409; fixture now waits for the visible revision. Server
capture was initially missing and caused IndexError after two cycles; fixed.
A source-encoding error was corrected before native execution. Later actual native
attempts still failed at script startup or reauthentication. One completed two
cycles and verified expiry before reauthentication timed out. Main shutdown passed
in those returned results. Deferred synthetic WebView2 profile cleanup is reported.
Final run/result is recorded in VALIDATION.md; do not hide earlier failures.

## HP OMEN acceptance checklist — not yet performed
- Type a message and tab through controls; edit principal with actual keyboard.
- Speak the five-turn compound-interest sequence; confirm audio and visuals agree.
- Check initial focus, then click/type in either window without focus stealing.
- Minimize/maximize both windows and move them between monitors if available.
- Close the visual, keep talking, reopen, edit, and confirm no duplicate window.
- Leave the visual for over 15 minutes; verify access expires and explicit reopen
  reauthenticates. Main private access must remain independent.
- Return to standby, wake normally, then quit main and confirm child shutdown.
- Record laptop/Windows/WebView2 versions, result and symptom. Do not label physical
  audio/keyboard/multi-monitor tests passed based on synthetic DOM interactions.

## Continuation
See UNIFIED-INTELLIGENCE-2-HANDOFF.md for the implementation plan only. Resolve or
explicitly accept the remaining native reliability gate before making visual UI
essential. Keep IRIS-SEC-001 isolation, approval boundaries and private-context
controls. No Unified Intelligence 2.0 implementation was introduced here.
