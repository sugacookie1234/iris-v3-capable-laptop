"""Interactive first-run configuration; keys are never passed as arguments."""
from getpass import getpass
from pathlib import Path
import os
from zoneinfo import ZoneInfo
from iris.local_config import read_saved, save_updates
from iris.brain.providers.configuration import validate_provider_url, validate_model_id
from iris.desktop.speech_config import speech_options


def main():
    current = read_saved()
    print('IRIS v3 — Windows setup\nPress Enter to retain existing values. Keys are hidden while you type.')
    def ask(label, key, default=''):
        existing = current.get(key, default)
        return input(f'{label} [{existing}]: ').strip() or existing
    base = ask('OpenAI-compatible provider URL', 'IRIS_PROVIDER_URL', 'https://openrouter.ai/api/v1')
    validate_provider_url(base)
    model = ask('Fast model ID', 'IRIS_MODEL', 'nvidia/nemotron-3.5-lightning:free')
    validate_model_id(model)
    key = getpass('Provider API key (blank keeps saved key): ').strip() or current.get('IRIS_API_KEY', '')
    fish = getpass('Fish Audio API key (blank keeps saved key; optional): ').strip() or current.get('IRIS_FISH_API_KEY', '')
    voice = ask('Fish voice ID', 'IRIS_FISH_VOICE_ID', '41f0953d7a6b4c078445c7e65d620eeb')
    fish_model = ask('Fish speech model', 'IRIS_FISH_MODEL', 's2.1-pro-free')
    stt_provider = ask('Voice recognition (fish with local fallback, or local)', 'IRIS_STT_PROVIDER', 'fish').lower()
    if stt_provider not in ('fish', 'local'):
        raise ValueError('Voice recognition must be fish or local.')
    stt_model = ask('Local speech model (large-v3-turbo for OMEN; small.en for lighter English)', 'IRIS_STT_MODEL', 'large-v3-turbo')
    stt_device = ask('Local speech device (auto, cpu, cuda)', 'IRIS_STT_DEVICE', 'auto').lower()
    stt_language = ask('Local speech language (en or auto)', 'IRIS_STT_LANGUAGE', 'en').lower()
    speech_options({'IRIS_STT_MODEL': stt_model, 'IRIS_STT_DEVICE': stt_device, 'IRIS_STT_LANGUAGE': stt_language})
    zone = ask('Timezone', 'IRIS_TIMEZONE', 'America/New_York')
    ZoneInfo(zone)
    deep = ask('Deep reasoning model', 'IRIS_DEEP_MODEL', model)
    strategist = ask('Council strategist model', 'IRIS_COUNCIL_STRATEGIST_MODEL', deep)
    skeptic = ask('Council skeptic model (can differ)', 'IRIS_COUNCIL_SKEPTIC_MODEL', deep)
    chairman = ask('Council chairman model', 'IRIS_COUNCIL_CHAIRMAN_MODEL', deep)
    for selected in (deep, strategist, skeptic, chairman):
        validate_model_id(selected)
    print('Council uses five requests: two answers, two reviews, and a final synthesis.')
    vault = ask('Optional Obsidian vault path', 'IRIS_OBSIDIAN_VAULT')
    if vault and not Path(vault).expanduser().is_dir():
        raise ValueError('The Obsidian vault folder does not exist.')
    updates = {'IRIS_PROVIDER_URL': base, 'IRIS_MODEL': model, 'IRIS_API_KEY': key,
               'IRIS_FISH_API_KEY': fish, 'IRIS_FISH_VOICE_ID': voice, 'IRIS_FISH_MODEL': fish_model,
               'IRIS_STT_PROVIDER': stt_provider, 'IRIS_STT_MODEL': stt_model,
               'IRIS_STT_DEVICE': stt_device, 'IRIS_STT_LANGUAGE': stt_language,
               'IRIS_TIMEZONE': zone, 'IRIS_TIMEOUT_SECONDS': '60',
               'IRIS_FAST_MODEL': model, 'IRIS_DEEP_MODEL': deep,
               'IRIS_COUNCIL_STRATEGIST_MODEL': strategist, 'IRIS_COUNCIL_SKEPTIC_MODEL': skeptic,
               'IRIS_COUNCIL_CHAIRMAN_MODEL': chairman,
               'IRIS_OBSIDIAN_VAULT': str(Path(vault).expanduser()) if vault else '',
               'IRIS_OBSIDIAN_ROOT': str(Path(vault).expanduser()) if vault else ''}
    # Explicitly use the selected legacy provider for every role, including after switching providers.
    for role in ('FAST', 'DEEP', 'COUNCIL_STRATEGIST', 'COUNCIL_SKEPTIC', 'COUNCIL_CHAIRMAN'):
        updates['IRIS_' + role + '_PROVIDER'] = 'terminal'
    # load_config names the legacy OpenAI-compatible endpoint 'terminal'.
    from iris.terminal import load_config
    load_config(updates)
    save_updates(updates)
    print('Saved for your Windows account.' if os.name == 'nt' else 'Saved in your private user configuration.')
    print('Run start-iris.bat. Model availability is checked by your first real message.')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError, KeyboardInterrupt, EOFError):
        print('\nSetup did not complete. Check the provider URL, model IDs, speech settings, timezone and optional vault path.')
        raise SystemExit(1)
