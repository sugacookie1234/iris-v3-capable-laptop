"""Real authority/executor checks with fake picklable Windows adapters."""
from pathlib import Path
import tempfile
import unittest

from iris.desktop.action_tools import DesktopActionTools
from iris.tools import Approval, AuthorityLevel, FailureCode, RequestOrigin, ResultStatus, ToolExecutor


class FakeControls:
    def open_app(self, app):
        if app == 'obsidian':
            raise RuntimeError('sensitive underlying installation error')
        return {'app': app, 'state': 'visible', 'verified': True, 'detail': app + ' has a visible window.'}

    def open_folder(self, path):
        return {'path': str(path), 'state': 'requested', 'verified': False, 'detail': 'Folder requested.'}

    def volume(self, percent=None, muted=None):
        return {'percent': 40 if percent is None else percent, 'muted': False if muted is None else muted,
                'verified': True, 'state': 'verified'}


class CapturingExecutor(ToolExecutor):
    """Retain the proposal only so a test can try mutating it during approval."""
    def execute(self, call, **kwargs):
        self.call = call
        return super().execute(call, **kwargs)


class ActionToolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name) / 'work space'
        self.workspace.mkdir()
        self.vault = Path(self.temp.name) / 'vault'
        self.vault.mkdir()

    def tools(self, approve=None, **kwargs):
        return DesktopActionTools(self.workspace, self.vault, approve,
                                  controls_factory=FakeControls, **kwargs)

    def test_specifications_keep_launches_yellow_and_out_of_local_workflows(self):
        specs = {spec.name: spec for spec in self.tools().specifications()}
        for name in ('desktop_open_app', 'desktop_open_folder', 'desktop_start_workspace'):
            self.assertEqual(specs[name].authority, AuthorityLevel.YELLOW)
            self.assertFalse(specs[name].local_only)
            self.assertEqual(specs[name].required_permissions, ('desktop.launch',))
        self.assertEqual(specs['desktop_volume_read'].authority, AuthorityLevel.GREEN)
        self.assertTrue(specs['desktop_volume_read'].local_only)
        self.assertEqual(specs['desktop_volume_set'].authority, AuthorityLevel.YELLOW)
        self.assertTrue(specs['desktop_volume_set'].local_only)

    def test_no_approval_or_rejected_approval_cannot_launch(self):
        tools = self.tools()
        self.assertEqual(tools.run('desktop_open_app', app='chrome').failure.code,
                         FailureCode.APPROVAL_REQUIRED)
        tools = self.tools(lambda plan: Approval(plan.id, False))
        for name, arguments in (
            ('desktop_open_app', {'app': 'chrome'}),
            ('desktop_open_folder', {'folder': 'workspace'}),
            ('desktop_start_workspace', {}),
            ('desktop_volume_set', {'percent': 20}),
        ):
            with self.subTest(name=name):
                self.assertEqual(tools.run(name, **arguments).failure.code, FailureCode.APPROVAL_REJECTED)

    def test_external_and_memory_cannot_run_even_with_approval_callback(self):
        approvals = []
        tools = self.tools(lambda plan: approvals.append(plan) or Approval(plan.id, True))
        for origin in (RequestOrigin.EXTERNAL, RequestOrigin.MEMORY):
            self.assertEqual(tools.run('desktop_open_app', app='chrome', origin=origin).failure.code,
                             FailureCode.AUTHORITY_DENIED)
            self.assertEqual(tools.run('desktop_volume_read', origin=origin).failure.code,
                             FailureCode.AUTHORITY_DENIED)
        self.assertEqual(approvals, [])

    def test_invalid_arguments_are_rejected_before_approval(self):
        def unexpected(plan):
            self.fail('Malformed commands must never request approval')
        tools = self.tools(unexpected)
        for name, arguments in (
            ('desktop_open_app', {'app': 'cmd'}),
            ('desktop_open_app', {'app': 'chrome', 'url': 'https://example.com'}),
            ('desktop_open_folder', {'folder': str(self.workspace)}),
            ('desktop_open_folder', {'folder': '../vault'}),
            ('desktop_start_workspace', {'workspace': 'C:/other'}),
            ('desktop_volume_set', {'percent': -1}),
            ('desktop_volume_set', {'percent': 101}),
            ('desktop_volume_set', {'percent': True}),
            ('desktop_volume_set', {'muted': 'false'}),
            ('desktop_volume_set', {}),
        ):
            with self.subTest(name=name, arguments=arguments):
                self.assertEqual(tools.run(name, **arguments).failure.code, FailureCode.INVALID_ARGUMENTS)
        self.assertEqual(tools.run('unknown_action').failure.code, FailureCode.UNKNOWN_TOOL)

    def test_unconfigured_vault_is_rejected_before_approval(self):
        tools = DesktopActionTools(self.workspace, controls_factory=FakeControls)
        self.assertEqual(tools.run('desktop_open_folder', folder='vault').failure.code,
                         FailureCode.INVALID_ARGUMENTS)

    def test_volume_read_is_green_but_write_requires_plan_approval(self):
        result = self.tools().run('desktop_volume_read')
        self.assertEqual(result.status, ResultStatus.SUCCESS)
        self.assertEqual(result.value['percent'], 40)
        self.assertEqual(self.tools().run('desktop_volume_read', origin=RequestOrigin.MODEL).failure.code,
                         FailureCode.APPROVAL_REQUIRED)
        result = self.tools(lambda plan: Approval(plan.id, True)).run('desktop_volume_set', percent=15, muted=True)
        self.assertEqual(result.status, ResultStatus.SUCCESS)
        self.assertEqual(result.value['percent'], 15)
        self.assertTrue(result.value['muted'])

    def test_approval_snapshot_cannot_be_changed_or_replayed(self):
        previous = []
        tools = None
        def approve(plan):
            self.assertEqual(dict(plan.arguments), {'app': 'chrome'})
            tools._executor.call.arguments['app'] = 'obsidian'
            previous.append(Approval(plan.id, True))
            return previous[-1]
        tools = self.tools(approve, executor_factory=CapturingExecutor)
        result = tools.run('desktop_open_app', app='chrome')
        self.assertEqual(result.status, ResultStatus.SUCCESS)
        self.assertEqual(result.value['app'], 'chrome')
        tools._approve = lambda plan: previous[0]
        self.assertEqual(tools.run('desktop_open_app', app='chrome').failure.code,
                         FailureCode.APPROVAL_REJECTED)

    def test_workspace_is_one_exact_approval_with_partial_outcomes(self):
        approvals = []
        tools = self.tools(lambda plan: approvals.append(plan) or Approval(plan.id, True))
        result = tools.run('desktop_start_workspace')
        self.assertEqual(result.status, ResultStatus.SUCCESS)
        self.assertEqual(len(approvals), 1)
        summary = approvals[0].confirmation_summary
        for component in ('Google Chrome', 'Obsidian', str(self.workspace)):
            self.assertIn(component, summary)
        self.assertIn('future runs', summary)
        actions = result.value['actions']
        self.assertEqual([item['component'] for item in actions], ['Chrome', 'Obsidian', 'Workspace folder'])
        self.assertEqual([item['state'] for item in actions], ['visible', 'failed', 'requested'])
        self.assertEqual(actions[2]['path'], str(self.workspace))
        self.assertNotIn('sensitive', repr(actions))

    def test_folder_approval_identifies_exact_configured_path(self):
        approvals = []
        tools = self.tools(lambda plan: approvals.append(plan) or Approval(plan.id, True))
        result = tools.run('desktop_open_folder', folder='vault')
        self.assertEqual(result.status, ResultStatus.SUCCESS)
        self.assertEqual(result.value['path'], str(self.vault))
        self.assertIn(str(self.vault), approvals[0].confirmation_summary)


if __name__ == '__main__':
    unittest.main()
