# Personality refinement checkpoint

Owner request: professional, confident, familiar IRIS with occasional natural
"sir", restrained wit, respectful disagreement and factual reporting. No dialogue
collection was available in the current request; traits were used without quotes.

Canonical config/identity.md now supplies the address, disagreement, initiative,
voice brevity and truthfulness guidance to all compiled behavior modes. No TTS
voice/model or permission was changed. Existing local factual/error templates and
separate display/spoken fields remain intact; no automatic suffix edits source
excerpts, approval text or tool results. Explicit desktop greetings use "Hello,
sir." once per runtime, then "Hello.". Model responses use recent conversation
and prompt guidance to avoid repetitive address; this is not a guaranteed model
output filter. Emergency guidance prioritizes information over ceremony/humour.
The follow-up listening label is descriptive instead of "Anything else?".

Validation: 13 tests in tests.test_personality and tests.test_identity passed.
These validate deterministic behavior and compiled prompt contracts, not live LLM
quality, microphone performance or listening acceptance. No paid model calls.

## Security work preserved for continuation

Uncommitted pairing work from the previous request remains in server.py, app.py,
web/pair.js, tests/test_bootstrap.py and tests/test_desktop.py. Homepage no longer
issues a session; trusted launchers supply a 60-second single-use fragment token,
removed by pair.js before POSTing it with same-origin checks. Invalid redemption
attempts are bounded to ten/minute. This is not yet validated or release-ready.
Tokens can still be exposed to same-user process inspection and briefly to browser
navigation state. Browser --no-browser mode has no manual pairing mechanism yet.
Existing authenticated-cookie reload can leave an unused fragment: review cleanup
before release. Add browser/native startup and microphone acceptance tests.

The required Windows regression command was not executed: automatic approval
review failed due to the account usage limit, explicitly not a safety rejection.
Do not bypass that review. Resume the pending bootstrap/native regression command
when review is available, fix failures, then commit personality and security work
in separate logical units. Main and owner data are unchanged. Quotas and protected
backup/export remain outstanding after pairing completion.
