# M6 complete response-shape prompt — 2026-11-07

Pilot 003 omitted context on its update and text on its comparison. This targeted
prompt intervention replaces partial object examples with one complete seven-field
JSON comparison example. All seven fields are explicitly mandatory on every reply;
text remains nonempty and context must be present even when null. The example uses
labelled ID placeholders; guidance requires supplied IDs and the current revision,
and says to choose the operation from the actual request rather than copy it.

Only prompt text and regression tests changed. Parser, host validation, metrics,
fallbacks, arithmetic, transport and permissions are unchanged. No repair, retry,
model substitution, workspace execution, defaults, owner-data or rollout changes.
This is a hypothesis about response reliability, not evidence of real-model gains.

Verification: 109 focused tests passed in 9.130s across corrective, interpretation,
working-context, conversation, orchestration and evaluation/admission/route suites.
Three new tests cover the complete example with bound references, rejection of
each of the seven missing fields, and the real two-turn fake-provider path with
missing context/text and no retry, calculation or tool execution. All 12 desktop
JavaScript checks passed. git diff --check passed. Full Python and CAP-34 were not
rerun for this prompt-only change; previous results remain historical evidence.

The source-only verification tree excludes owner settings and credentials, uses
isolated TEMP/TMP and process-only cleared provider variables, and matches all
current tracked Python bytes. Logs and hashes: m6-complete-shape-verification in
the current chat workspace. Both older pilots and pilot 003 (15 files), frozen
holdouts, main/origin-main and unrelated tatus -sb match preservation evidence.

Fresh non-contacting preflight:
scope b29c35196fbaf695175fceb09b81803afc4eeb26d64c279a00444394f728f99c
prompt 5216e02ea09235584120cd474b50bde360792f7e50abdcc9f031833e69938fe3

Proposed next run: OpenRouter nvidia/nemotron-3.5-lightning:free; same cases
m6-specific-context, m6-eight, m6-preview (2+2+1 turns), maximum five attempts and
180 seconds, FAST 500 output tokens each. Unused output checked absent:
.local/m6-complete-shape-proposed-pilot-004. No new ledger or provider contact.
No Council, retries, substitutions or workspace execution. Provider logging,
uncertain final billing and remote cancellation remain risks. Availability/policy
and secure credential-dependent preflight must be checked after separate approval
of these exact new fingerprints. Prior consumed authorizations do not apply.
