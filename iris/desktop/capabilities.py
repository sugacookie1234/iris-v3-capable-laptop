"""Read-only inventory from the running host's registrations and configuration.

Discovery never probes a service, installs a skill or grants a permission.
"""
import re

from iris.desktop.autonomy import enabled
from iris.desktop.web_search import web_available
from iris.memory.redaction import contains_secret


def _public_id(value):
    value = str(value or '')
    return value if (re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_./:-]{0,95}', value)
                     and not re.match(r'^[a-zA-Z]:', value)
                     and '://' not in value and not contains_secret(value)) else 'configured'


def build_capabilities(config, settings, desktop_specs=(), brain_specs=(), permissions=(), workflows=(), *, briefing_specs=()):
    tools = []
    for source, specs, granted in (
        ('desktop', desktop_specs, {'desktop.launch', 'desktop.audio'}),
        ('chat', brain_specs, set(permissions)),
        ('notes_briefing', briefing_specs, {'obsidian.read'}),
    ):
        for spec in specs:
            tools.append({'name': spec.name, 'source': source, 'status': 'registered',
                'authority': str(spec.authority), 'local_only': spec.local_only,
                'reversible': spec.reversible, 'timeout_seconds': spec.timeout,
                'side_effects': list(spec.side_effects),
                'required_permissions': list(spec.required_permissions),
                'permissions_granted': set(spec.required_permissions).issubset(granted),
                'arguments': [{'name': arg.name, 'type': str(arg.type), 'required': arg.required}
                              for arg in spec.arguments],
                'approval': 'existing authority policy applies to each invocation',
                'live_verified': False})
    default = {'provider': _public_id(config.provider.name), 'model': _public_id(config.model)}
    models = []
    for role, target in (('fast', config.fast_target), ('deep', config.deep_target)):
        models.append({'role': role, **({'provider': _public_id(target.provider),
            'model': _public_id(target.model)} if target else default), 'status': 'configured', 'live_verified': False})
    plan = config.council_plan
    targets = [seat.target for seat in plan.seats] + [plan.chairman] if plan else []
    for index, target in enumerate(targets):
        models.append({'role': 'council_chair' if index == len(targets) - 1 else 'council_seat',
            'provider': _public_id(target.provider), 'model': _public_id(target.model),
            'status': 'configured', 'live_verified': False})
    if plan is None:
        models.extend({'role': role, **default, 'status': 'configured', 'live_verified': False}
                      for role in ('council_seat', 'council_seat', 'council_chair'))
    fish = bool(settings.get('IRIS_FISH_API_KEY'))
    provider = settings.get('IRIS_STT_PROVIDER', 'fish').strip().lower()
    services = {
        'web_search': 'configured' if web_available(config) else 'not_configured',
        'fish_voice': 'configured' if fish else 'not_configured',
        'recognition': (('fish_with_local_fallback' if fish else 'local_fallback') if provider == 'fish'
                        else 'local' if provider == 'local' else 'invalid_configuration'),
        'automatic_organization': 'enabled' if enabled(settings) else 'paused',
        'obsidian_folder': 'configured' if config.obsidian_vault or config.obsidian_root else 'not_configured',
        'calendar_file': 'configured' if config.calendar_path else 'not_configured',
        'workspace_folder': 'configured' if config.workspace_root else 'repository_default',
        'desktop_apps': 'installation_not_checked',
        'clap_standby': 'supported_while_app_running_microphone_required',
        'phone_bridge': 'separate_setup_status_unknown',
    }
    return {'version': 1, 'tools': tools, 'models': models, 'services': services,
        'local_commands': ['daily briefing', 'find files named …', 'what have you done today',
                           'show action history', 'clear action history', 'what can you do',
                           'check obsidian', 'search my notes for …', 'read note …', 'read next page',
                           'plan a briefing from my notes on …', 'make a briefing from my notes on …'],
        'skills': {'status': 'host_workflows_only', 'automatic_installation': False,
            'workflows': [{'name': definition.name, 'tools': [step.tool_name for step in definition.steps],
                           'status': 'registered', 'live_verified': False} for definition in workflows]},
        'limitations': ['No general screen clicking or arbitrary shell commands.',
            'Email and Google account connectors are not connected.',
            'Desktop chat cannot send SMS or place calls; the phone bridge has separate setup.',
            'Configured does not mean reachable, installed, funded or live-verified.',
            'Reading this inventory grants no permissions.']}


def capability_reply(inventory):
    services = inventory['services']
    names = {tool['name'] for tool in inventory['tools'] if tool['permissions_granted']}
    lines = ['Here is what this desktop build supports:']
    if 'desktop_open_app' in names:
        lines.append('• Open Chrome, Obsidian, Notepad, Calculator or File Explorer after approval; installation is checked when used.')
    if 'desktop_start_workspace' in names:
        lines.append('• “Start my workspace”: Chrome, Obsidian and your workspace folder, with one approval and separate results.')
    if 'desktop_volume_read' in names:
        lines.append('• Read system volume; changing it requires approval and a readback.')
    lines.append('• Find files by name, give a daily briefing, and show local action history.')
    if services['obsidian_folder'] == 'configured':
        lines.append('• Search and read Obsidian notes locally, including long notes page by page. Ask “Check Obsidian” to check access.')
        lines.append('• “Make a briefing from my notes on …”: find and read up to three notes, recheck their revisions and show source excerpts without a model call. A plan preview is also available.')
    if any(name.startswith('tasks_') for name in names):
        lines.append('• Manage local tasks and goals using the registered tools and existing approvals.')
    lines.append('• Automatic notes and reminders: ' + services['automatic_organization'] +
                 '; Obsidian folder: ' + services['obsidian_folder'].replace('_', ' ') + '.')
    lines.append('• Chat selects reasoning automatically; council is available. Configured model connections have not been live-checked by this inventory.')
    lines.append('• Web search: ' + services['web_search'].replace('_', ' ') +
                 '. Use “search the web for …”; a search can use provider credits.')
    lines.append('• Fish voice: ' + services['fish_voice'].replace('_', ' ') +
                 '; recognition: ' + services['recognition'].replace('_', ' ') + '. Microphone/model readiness is checked when used.')
    lines.append('Double clap can wake a conversation while IRIS is running and the computer is awake, with microphone permission.')
    lines.extend(inventory['limitations'][:3])
    return '\n'.join(lines)
