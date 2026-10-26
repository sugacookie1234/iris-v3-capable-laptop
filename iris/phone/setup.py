"""Interactive phone settings saved through IRIS's existing encrypted storage."""
from getpass import getpass

from iris.local_config import read_saved, save_updates
from iris.phone.config import PhoneConfig


def main():
    current = read_saved()
    print('IRIS phone setup. No number will be purchased and no message or call will be sent.')
    print('For Canada, confirm a voice-capable verified toll-free number and personal-use eligibility with Twilio first.')
    print('Use a dedicated HTTPS tunnel to the phone port only. Never expose the desktop port 8766.')
    def ask(label, key, default=''):
        existing = current.get(key, default)
        return input(f'{label} [{existing}]: ').strip() or existing
    updates = {
        'IRIS_PHONE_ENABLED': 'true',
        'IRIS_TWILIO_ACCOUNT_SID': ask('Twilio Account SID', 'IRIS_TWILIO_ACCOUNT_SID'),
        'IRIS_TWILIO_AUTH_TOKEN': getpass('Twilio Auth Token (blank keeps saved): ').strip() or current.get('IRIS_TWILIO_AUTH_TOKEN', ''),
        'IRIS_PHONE_NUMBER': ask('Dedicated IRIS phone number (+countrycode...)', 'IRIS_PHONE_NUMBER'),
        'IRIS_OWNER_PHONE_NUMBER': ask('Your Fizz/mobile number (+countrycode...)', 'IRIS_OWNER_PHONE_NUMBER'),
        'IRIS_PHONE_PUBLIC_URL': ask('Public HTTPS origin for the phone bridge', 'IRIS_PHONE_PUBLIC_URL'),
        'IRIS_PHONE_PORT': ask('Phone bridge local port', 'IRIS_PHONE_PORT', '8767'),
        'IRIS_PHONE_PIN': getpass('Six-digit call access code (blank keeps saved): ').strip() or current.get('IRIS_PHONE_PIN', ''),
    }
    config = PhoneConfig.from_environment(updates)
    print('Inbound texts from your configured number will receive AI replies while the phone bridge is running.')
    print('Incoming calls require your access code. Twilio, chat and search usage can incur charges.')
    if input('Type ENABLE to save these phone settings: ').strip() != 'ENABLE':
        print('No phone settings changed.')
        return 0
    save_updates(updates)
    print('Saved. Configure these POST webhooks in Twilio, then run start-phone.bat:')
    print('Incoming messages: ' + config.public_url + '/phone/sms')
    print('Incoming calls: ' + config.public_url + '/phone/voice')
    print('Call status changes: ' + config.public_url + '/phone/status')
    return 0


if __name__ == '__main__':
    try: raise SystemExit(main())
    except (ValueError, OSError, KeyboardInterrupt, EOFError):
        print('Phone setup did not complete. Check the number format, credentials, HTTPS origin and six-digit code.')
        raise SystemExit(1)
