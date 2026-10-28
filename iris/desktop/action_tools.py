"""Typed desktop actions routed through the existing tool authority/executor.

Only trusted host configuration supplies folders and the fixed workspace scene.
Matching a command is not an approval: every YELLOW execution still requires a
fresh plan-bound Approval through ToolExecutor.
"""
from __future__ import annotations

from functools import partial
import os
from pathlib import Path

from iris.desktop.windows_controls import APPS, WindowsControls
from iris.tools import (
    ArgumentType, AuthorityContext, AuthorityLevel, RequestOrigin,
    ToolArgument, ToolCall, ToolExecutor, ToolRegistry, ToolSpec,
)


def _prepare_app(arguments):
    app = arguments['app']
    if app not in APPS:
        raise ValueError('Choose a supported application: Chrome, Obsidian, Notepad, Calculator or File Explorer.')
    return arguments, 'Open only ' + APPS[app][0] + '; no URL, document or additional command arguments.'


def _prepare_folder(paths, arguments):
    folder = arguments['folder']
    locations = dict(paths)
    if folder not in locations:
        raise ValueError('Choose a configured workspace or vault folder.')
    return arguments, f'Open the configured {folder} folder in File Explorer: {locations[folder]}'


def _prepare_workspace(workspace, arguments):
    return arguments, (
        'Start exactly these three components once, in order:\n'
        '1. Google Chrome (no URL or extra arguments).\n'
        '2. Obsidian (no document or extra arguments).\n'
        f'3. File Explorer for the configured workspace: {workspace}\n'
        'Report each outcome separately; unavailable components are skipped without retries. '
        'This approval does not authorize music, websites, other apps or future runs.'
    )


def _prepare_volume(arguments):
    if not arguments:
        raise ValueError('Choose a volume percentage or mute setting.')
    percent = arguments.get('percent')
    if percent is not None and not 0 <= percent <= 100:
        raise ValueError('Volume must be from 0 to 100 percent.')
    return arguments, 'Change only the default Windows speaker volume/mute setting, then read it back.'


def _open_app(app, *, controls_factory):
    return controls_factory().open_app(app)


def _open_folder(folder, *, paths, controls_factory):
    return controls_factory().open_folder(dict(paths)[folder])


def _start_workspace(*, workspace, controls_factory):
    controls = controls_factory()
    actions = []
    # Fixed operations are deliberately not a general-purpose stored plan.
    for component, kind, target in (
        ('Chrome', 'app', 'chrome'),
        ('Obsidian', 'app', 'obsidian'),
        ('Workspace folder', 'folder', workspace),
    ):
        try:
            result = controls.open_app(target) if kind == 'app' else controls.open_folder(target)
            actions.append({'component': component, **result})
        except (OSError, ValueError, RuntimeError):
            actions.append({'component': component, 'state': 'failed', 'verified': False,
                            'detail': 'Could not open it. Check its installation or configured path.'})
    return {'actions': actions}


def _volume_read(*, controls_factory):
    return controls_factory().volume()


def _volume_set(*, controls_factory, percent=None, muted=None):
    return controls_factory().volume(percent=percent, muted=muted)


def _folder_path(value):
    path = Path(os.path.abspath(os.path.expanduser(os.fspath(value))))
    if str(path).startswith(('\\\\', '//')):
        raise ValueError('Desktop actions require configured local directories.')
    return str(path)


class DesktopActionTools:
    def __init__(self, workspace, vault=None, approve=None, *, executor_factory=ToolExecutor,
                 controls_factory=WindowsControls):
        workspace = _folder_path(workspace)
        paths = (('workspace', workspace),)
        if vault:
            paths += (('vault', _folder_path(vault)),)
        self._approve = approve
        registry = ToolRegistry()
        launch_effects = ('Open a configured application or folder in the current Windows session',)
        registry.register(ToolSpec(
            'desktop_open_app', 'Open one allowlisted Windows application', AuthorityLevel.YELLOW, True,
            launch_effects, ('desktop.launch',), 12,
            (ToolArgument('app', 'Fixed application alias', ArgumentType.STRING),), local_only=False,
        ), partial(_open_app, controls_factory=controls_factory), prepare=_prepare_app)
        registry.register(ToolSpec(
            'desktop_open_folder', 'Open a host-configured workspace or vault folder', AuthorityLevel.YELLOW, True,
            launch_effects, ('desktop.launch',), 12,
            (ToolArgument('folder', 'Configured folder alias: workspace or vault', ArgumentType.STRING),),
            local_only=False,
        ), partial(_open_folder, paths=paths, controls_factory=controls_factory),
            prepare=partial(_prepare_folder, paths))
        registry.register(ToolSpec(
            'desktop_start_workspace', 'Start Chrome, Obsidian and the configured workspace folder once',
            AuthorityLevel.YELLOW, True, launch_effects, ('desktop.launch',), 30, local_only=False,
        ), partial(_start_workspace, workspace=workspace, controls_factory=controls_factory),
            prepare=partial(_prepare_workspace, workspace))
        registry.register(ToolSpec(
            'desktop_volume_read', 'Read the default speaker volume and mute state', AuthorityLevel.GREEN, True,
            (), ('desktop.audio',), 8, local_only=True,
        ), partial(_volume_read, controls_factory=controls_factory))
        registry.register(ToolSpec(
            'desktop_volume_set', 'Set default speaker volume or mute and verify the result', AuthorityLevel.YELLOW, True,
            ('Change system speaker volume or mute state',), ('desktop.audio',), 8,
            (ToolArgument('percent', 'Whole percentage from 0 to 100', ArgumentType.INTEGER, False),
             ToolArgument('muted', 'True to mute, false to unmute', ArgumentType.BOOLEAN, False)), local_only=True,
        ), partial(_volume_set, controls_factory=controls_factory), prepare=_prepare_volume)
        self._executor = executor_factory(registry)

    def specifications(self):
        return self._executor.specifications()

    def run(self, name, *, origin=RequestOrigin.USER, **arguments):
        # This wrapper is constructed by the local desktop host, never from a
        # model proposal, imported skill, remote channel or retrieved content.
        # The central authority still rejects external/memory origins and gates
        # every YELLOW action even when a command was explicitly requested.
        context = AuthorityContext(explicitly_requested=origin == RequestOrigin.USER,
                                   permissions=frozenset({'desktop.launch', 'desktop.audio'}))
        return self._executor.execute(ToolCall(name, arguments, origin), authority=context,
                                      approve=self._approve)
