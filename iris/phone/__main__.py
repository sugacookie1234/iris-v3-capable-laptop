"""Separate opt-in phone bridge and explicit owner-only outgoing notifications."""
import argparse
import json
from pathlib import Path

from iris.local_config import effective_environment
from iris.phone.config import PhoneConfig, PhoneDisabled
from iris.phone.store import PhoneStore
from iris.phone.transport import TransportError

ROOT = Path(__file__).resolve().parents[2]


def main(argv=None):
    parser = argparse.ArgumentParser(description='IRIS phone connection; no desktop APIs are exposed.')
    commands = parser.add_subparsers(dest='command')
    commands.add_parser('serve', help='Receive signed phone callbacks until Ctrl+C.')
    commands.add_parser('status', help='Show local configuration and queue counts; never send.')
    sms = commands.add_parser('send-sms', help='Preview and explicitly send one SMS to your configured number.')
    sms.add_argument('--text', required=True)
    call = commands.add_parser('call', help='Preview and explicitly call your number with a spoken notification.')
    call.add_argument('--message', required=True)
    args = parser.parse_args(argv)
    settings = effective_environment()
    try: config = PhoneConfig.from_environment(settings)
    except PhoneDisabled:
        print('Phone service is disabled. Run setup-phone.bat after arranging your number and public HTTPS connection.')
        return 0 if args.command == 'status' else 1
    store = PhoneStore(ROOT / '.local' / 'phone.sqlite3')
    if args.command == 'status':
        print('Phone settings are configured. Live carrier delivery has not been verified by this command.')
        print(json.dumps(store.counts(), sort_keys=True))
        return 0
    from iris.phone.transport import TwilioTransport
    transport = TwilioTransport(config)
    if args.command in ('send-sms', 'call'):
        text = args.text if args.command == 'send-sms' else args.message
        if args.command == 'send-sms' and store.opted_out():
            raise ValueError('SMS is stopped. Send START from your mobile before sending another text.')
        limit = 700 if args.command == 'send-sms' else 400
        if not text.strip() or len(text) > limit: raise ValueError('The phone notification is empty or too long.')
        print('Recipient: ' + config.owner_number)
        print(text)
        confirmation = 'SEND' if args.command == 'send-sms' else 'CALL'
        if input(f'Type {confirmation} to send this exact notification (carrier charges apply): ').strip() != confirmation:
            print('Canceled. Nothing sent.')
            return 0
        if args.command == 'send-sms': transport.send_sms(text)
        else: transport.call(text)
        print('Twilio accepted the request. This does not confirm delivery or that the call was answered.')
        return 0
    from iris.phone.assistant import PhoneAssistant
    from iris.phone.service import PhoneService
    from iris.phone.server import PhoneServer
    from iris.usage import ProviderUsage
    usage = ProviderUsage(ROOT / '.local' / 'provider_usage.sqlite3', settings)
    service = PhoneService(config, store, PhoneAssistant(settings, usage=usage), transport)
    # Bind before recovering jobs: a second launcher must not alter the live queue.
    server = PhoneServer(config, service)
    try:
        service.start()
        print(f'Phone bridge listening on 127.0.0.1:{config.port}. Keep this window and its HTTPS tunnel running.')
        print('No desktop APIs are exposed here. Ctrl+C stops the phone bridge.')
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        service.close()
    return 0


if __name__ == '__main__':
    try: raise SystemExit(main())
    except TransportError:
        print('The phone provider did not confirm acceptance. Check Twilio before retrying to avoid a duplicate.')
        raise SystemExit(1)
    except (ValueError, OSError, ImportError, EOFError) as error:
        # Configuration validation uses fixed errors; never print raw SDK/OS exceptions.
        print('Phone connection did not start or complete. Check setup-phone.bat, dependencies and port availability.')
        raise SystemExit(1)
