# IRIS by SMS and phone

The optional phone bridge gives IRIS a dedicated number. Your Canadian Fizz number
stays on your phone; it is the single allowed contact for IRIS. There is no number
transfer or change to your Fizz service.

This first version supports text conversations and spoken, turn-by-turn incoming
calls. You can also manually ask IRIS to text you or call you with a spoken
notification. Outgoing notification calls do not start a conversation.

Phone replies use Twilio's basic `man` voice with English speech, using the
currently supported [Say voice options](https://www.twilio.com/docs/voice/twiml/say).
The desktop's Fish Audio voice is not
yet connected to calls. Phone conversations can use explicit web research, but
are isolated from desktop chat, saved memories, files, Obsidian and
computer-control tools.

The code alone does not activate a phone number. You must finish the provider
account, number and public HTTPS setup below. Setup does not purchase a number,
send a test text, or place a test call.

## Choose the number before paying

Use a dedicated Twilio account/project and a number with **both Voice and SMS**
capabilities. Confirm that Twilio supports your personal-assistant use case and
Canadian destination before buying the number.

For automated messages to Canada, Twilio recommends a **verified toll-free
number** or short code and warns about carrier filtering. A Canadian local number
being available does not guarantee it is suitable for IRIS's automated texts.
For this project, ask Twilio about a voice-capable toll-free number and personal-use
verification eligibility. See [Canada SMS guidelines](https://www.twilio.com/en-us/guidelines/ca/sms)
and [Twilio's sender guidance](https://www.twilio.com/docs/messaging/guides/best-practices-at-scale).

Twilio's current toll-free onboarding requires a paid account and a compliance
profile. SMS to Canada remains blocked until verification is approved. Supply
truthful use-case and consent details; do not invent a business to complete the form.
See [toll-free verification](https://www.twilio.com/docs/messaging/compliance/toll-free/console-onboarding).

Trial accounts can be useful for Twilio's guided tests, but current trial rules
restrict custom SMS content and require verified contacts. A trial test is not
proof that free-form IRIS conversations are enabled.
See [trial restrictions](https://www.twilio.com/docs/usage/tutorials/how-to-use-your-free-trial-account).

Review the number rental, messaging, carrier, speech-recognition and call charges
shown in your provider account. IRIS's language-model charges remain separate.
Fish Audio credit does not pay for Twilio. Confirm your Fizz plan covers calls and
texts to the chosen number; successful Fizz delivery still needs a real-device test.

## Keep the desktop interface private

The phone bridge listens on **127.0.0.1:8767**. A public HTTPS tunnel forwards only
to that port. The desktop interface on **8766** remains private and must not be
used as the tunnel's destination.

Twilio needs an internet-reachable webhook URL to deliver texts and calls.
Use a stable HTTPS hostname with a valid certificate. A local tunnel such as
ngrok can provide this while IRIS runs on the laptop. The laptop, phone bridge,
tunnel and internet connection must stay running. Sleep, shutdown or an expired
tunnel stops incoming conversations.
See [Twilio's webhook setup](https://www.twilio.com/docs/usage/webhooks/getting-started-twilio-webhooks).

The bridge validates Twilio's signature against the configured public URL and
all form fields, then checks the account and allowed phone numbers. This rejects
ordinary public requests. Changing the tunnel URL also requires updating IRIS's
configuration and the webhook URLs in Twilio. Do not disable signature checks to
solve a URL mismatch.
See [signed webhook validation](https://www.twilio.com/docs/usage/webhooks/webhooks-security).

## Set up the connection

1. Complete ordinary IRIS setup first. Confirm that text chat works with your
   selected model provider.
2. Finish the Twilio account and number setup above. Keep your Account SID and
   Auth Token available locally. Do not paste the token into chat, commit it to
   GitHub, or put it in a webhook URL.
3. Install and sign in to your chosen HTTPS tunnel. For ngrok, follow its
   [official setup guide](https://ngrok.com/docs/start), then forward
   `http://127.0.0.1:8767`. A typical command is `ngrok http 8767`. Copy its HTTPS
   base URL; use a stable hostname when available.
4. Double-click **`setup-phone.bat`** in the repository folder. Enter the Twilio
   account credentials, the dedicated IRIS number and your own Fizz number. Use
   international format: `+1` followed by the ten-digit number, without spaces.
   Enter the public HTTPS base URL and choose a **six-digit phone PIN**.
5. In Twilio's configuration for the IRIS number, set **A message comes in** to
   **Webhook**, **HTTP POST**, with `https://YOUR-HOST/phone/sms`. Set
   **A call comes in** to **Webhook**, **HTTP POST**, with
   `https://YOUR-HOST/phone/voice`. Replace `YOUR-HOST` with the tunnel hostname;
   keep the paths exactly as shown. Also set the number's **Voice status callback**
   to `https://YOUR-HOST/phone/status` using **HTTP POST**, so IRIS learns when an
   incoming call ends. Save the settings. See the
   [number's callback options](https://www.twilio.com/docs/phone-numbers/api/incomingphonenumber-resource).
6. Double-click **`start-phone.bat`**. Keep its window and the tunnel running.
   The normal IRIS desktop window is a separate process; opening it alone does
   not start phone service.
7. From the allowed Fizz number, send a short message to the dedicated number.
   Then call it, enter the six-digit PIN using the phone keypad, and speak after
   the prompt. These are real, potentially billable tests; perform them once the
   provider setup is ready.

The allowlist checks your Fizz number for SMS and calls. The PIN adds a check for
incoming calls because caller ID alone is not strong authentication. Keep the
PIN separate from your voicemail PIN. This first version does not grant phone
access to desktop tools or personal records.

On Windows, setup stores settings in `.local/config.dpapi`, encrypted for the
current Windows account. Run setup again on the OMEN rather than copying that
file. Changing credentials, PIN or tunnel hostname requires restarting the
bridge. To stop phone service, close its window and stop the tunnel.

For advanced configuration, setup uses these keys:

| Key | Meaning |
| --- | --- |
| `IRIS_PHONE_ENABLED` | Explicit opt-in to start the phone bridge. |
| `IRIS_TWILIO_ACCOUNT_SID` | Twilio account that owns the dedicated number. |
| `IRIS_TWILIO_AUTH_TOKEN` | Account Auth Token used for API access and webhook validation. |
| `IRIS_PHONE_NUMBER` | Dedicated IRIS number in `+1...` format. |
| `IRIS_OWNER_PHONE_NUMBER` | Your allowed Fizz number in `+1...` format. |
| `IRIS_PHONE_PUBLIC_URL` | Public HTTPS base URL, without a webhook path. |
| `IRIS_PHONE_PORT` | Local bridge port; default `8767`. |
| `IRIS_PHONE_PIN` | Six digits required to unlock incoming calls. |

## Ask IRIS to contact you

These commands run from a terminal in the repository folder. They always target
the configured owner number and show a preview. Type the requested confirmation
only when you want that exact communication sent.

```powershell
.\.venv\Scripts\python.exe -m iris.phone send-sms --text "IRIS phone test."
.\.venv\Scripts\python.exe -m iris.phone call --message "Hello. This is an IRIS test notification."
```

The text command requires typing `SEND`; the call command requires `CALL`.
Submitting a request does not prove delivery or that you answered. Check your
phone and Twilio's logs. No scheduled or proactive contact is enabled by setup.

## How conversations work

Incoming SMS is acknowledged promptly, and the model generates a reply in the
background. IRIS sends the reply through Twilio's messaging API. A queued or sent
status does not prove it reached the Fizz phone; check the delivery status in
Twilio's messaging logs.
Delivery callbacks can arrive before their returned message ID is saved locally;
Twilio's own message log is the delivery record to check in that case.
See [message statuses](https://www.twilio.com/docs/messaging/api/message-resource).

On a call, Twilio transcribes one spoken turn, IRIS generates a reply, and Twilio
speaks it before listening again. The bridge returns short wait-and-check
instructions while the model works. It does not hold one webhook open waiting for
the whole response: Twilio's call webhooks have a hard 15-second response limit.
See [call webhook timeouts](https://www.twilio.com/docs/usage/webhooks/webhooks-connection-overrides)
and [speech input](https://www.twilio.com/docs/voice/twiml/gather).

Twilio handles the phone network, SMS content, spoken call input and synthesized
reply. The configured model provider receives message text or the speech
transcript and the phone conversation context. IRIS does not request call
recording. This does not remove the providers' own processing or account logs.

Local phone processing uses `.local/phone.sqlite3`, which Git ignores. Cleanup
expires message/reply text after one day and duplicate-suppression message IDs
after seven days. Cleanup requires the bridge to run; a stopped laptop cannot
erase expired data. These local SQLite records are not encrypted by the
configuration's DPAPI protection. Opt-out state persists. After an uncertain SMS
send result, IRIS does not automatically retry and risk sending the same reply
twice; inspect Twilio's log before trying again.

Automatic reminders, calls to other people, desktop actions over the phone,
continuous real-time audio and Fish voice over calls are separate future work.

The bridge limits automatic work to 20 SMS requests and 60 spoken requests per
hour, with at most eight queued/working requests. It accepts up to ten new calls
per hour. Calls allow three distinct PIN attempts, up to twelve spoken turns and
a fifteen-minute local session. Short phone history lives in memory until bridge
restart (and is discarded when a call ends); it is not the desktop conversation.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Text reaches Twilio but IRIS does not answer | Bridge and tunnel running; correct incoming-message webhook; allowed Fizz number; model-provider configuration; Twilio message log. |
| Reply is blocked or undelivered | Number's SMS capability, approved verification, account balance, Canada geographic permissions, opt-out status and Twilio's recorded error. |
| Call fails before IRIS speaks | Voice capability and webhook, Canada voice permissions, trial verified-caller restrictions, laptop awake and tunnel reachable. |
| Signature validation fails | Exact public HTTPS hostname and webhook path agree in Twilio and IRIS; account Auth Token belongs to the same account. |
| Long pause during a call | Model response latency and connectivity; turn-by-turn calls are not a streaming voice session. |
| Texts stop after sending STOP | Twilio may block further SMS until you send its supported opt-in keyword, such as START. Do not retry around an opt-out. |

Twilio normally handles standard opt-out keywords, and Messaging Services can
provide `OptOutType` events. These are control messages, not prompts for the model.
See [Twilio opt-out behavior](https://www.twilio.com/docs/messaging/tutorials/advanced-opt-out).

Provider documentation checked October 25–26, 2026. Console screens, trial terms,
verification requirements and prices can change; use the linked provider pages
when activating the number.
