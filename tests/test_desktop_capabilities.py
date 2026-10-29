"""Capability awareness uses host facts, without provider calls or new rights."""
from dataclasses import replace
import json
import http.client
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from iris.desktop.capabilities import build_capabilities, capability_reply
from iris.desktop.runtime import DesktopRuntime
from iris.desktop.server import DesktopServer
from iris.tools import RequestOrigin
from tests.test_desktop import FakeBrain


class CapabilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.brain = FakeBrain()
        self.app = DesktopRuntime(settings={'IRIS_MODEL': 'synthetic-model',
            'IRIS_PROVIDER_URL': 'http://127.0.0.1:9/private-endpoint',
            'IRIS_PROVIDER_API_KEY': 'sk-private-sentinel-not-real',
            'IRIS_WORKSPACE_ROOT': self.temp.name, 'IRIS_AUTO_ORGANIZE_ENABLED': 'false'},
            data_dir=Path(self.temp.name) / 'data', brain=self.brain)
        self.addCleanup(self.app.close)

    def test_inventory_has_typed_specs_but_does_not_launch_or_grant_rights(self):
        inventory = self.app.capabilities()
        tools = {item['name']: item for item in inventory['tools']}
        volume = tools['desktop_volume_set']
        self.assertEqual(volume['authority'], 'YELLOW')
        self.assertIn({'name': 'percent', 'type': 'integer', 'required': False}, volume['arguments'])
        self.assertFalse(tools['desktop_open_app']['local_only'])
        self.assertTrue(all(item['live_verified'] is False for item in inventory['tools'] + inventory['models']))
        self.assertEqual(self.app.action_history.rows(), [])
        self.assertEqual(self.brain.calls, [])
        self.assertEqual(inventory['services']['desktop_apps'], 'installation_not_checked')

    def test_configured_and_unconfigured_connections_are_truthful_and_private(self):
        inventory = self.app.capabilities()
        self.assertEqual(inventory['services']['web_search'], 'not_configured')
        self.assertEqual(inventory['services']['obsidian_folder'], 'not_configured')
        config = replace(self.app.config, obsidian_vault=self.temp.name,
            provider=replace(self.app.config.provider, base_url='https://openrouter.ai/api/v1', api_key='private-sentinel'))
        inventory = build_capabilities(config, {'IRIS_FISH_API_KEY': 'private-fish-key'})
        self.assertEqual(inventory['services']['web_search'], 'configured')
        self.assertEqual(inventory['services']['obsidian_folder'], 'configured')
        self.assertEqual(inventory['services']['fish_voice'], 'configured')
        serialized = json.dumps(inventory)
        for private in (self.temp.name, 'private-sentinel', 'private-fish-key', 'https://openrouter.ai'):
            self.assertNotIn(private, serialized)
        self.assertIn('cannot send SMS', capability_reply(inventory))

    def test_misconfigured_model_ids_cannot_expose_keys_endpoints_or_absolute_paths(self):
        for value in ('sk-not-a-real-secret-value', 'https://host/private', 'C:/private/model'):
            inventory = build_capabilities(replace(self.app.config, model=value,
                fast_target=None, deep_target=None, council_plan=None), {})
            self.assertNotIn(value, json.dumps(inventory))

    def test_actual_host_workflows_are_listed_without_arguments_or_execution(self):
        from iris.workflows import WorkflowRegistry, register_builtin_workflows
        self.brain._workflow_registry = register_builtin_workflows(WorkflowRegistry())
        inventory = self.app.capabilities()
        flows = inventory['skills']['workflows']
        self.assertEqual(flows[0]['name'], 'daily_briefing_workflow')
        self.assertEqual(flows[0]['tools'], ['daily_briefing'])
        self.assertNotIn('arguments', flows[0])
        self.assertFalse(inventory['skills']['automatic_installation'])
        self.assertEqual(self.app.action_history.rows(), [])

    def test_awareness_commands_bypass_model_and_organizer_and_do_not_log_themselves(self):
        with patch.object(self.app.autonomy, 'submit') as organize:
            for command in ('Hey IRIS, what can you do?', 'What have you done today?', 'Show action history'):
                self.assertEqual(self.app.chat(command)['route'], 'LOCAL')
        self.assertEqual(self.brain.calls, [])
        organize.assert_not_called()
        self.assertEqual(self.app.action_history.rows(), [])
        self.assertEqual(self.app.history, [])  # No receipts/config in later provider prompts.

    def test_history_deletion_requires_confirmation_and_leaves_other_stores(self):
        self.app.action_history.begin('desktop_find_files', RequestOrigin.USER)
        with patch.object(self.app, 'approve', return_value=False):
            self.assertIn('kept', self.app.chat('clear action history')['reply'])
        self.assertEqual(len(self.app.action_history.rows()), 1)
        with patch.object(self.app, 'approve', return_value=True):
            self.assertIn('erased', self.app.chat('clear action history')['reply'])
        self.assertEqual(self.app.action_history.rows(), [])
        self.assertEqual(self.brain.calls, [])

    def test_history_failure_is_disclosed_in_report(self):
        self.app.desktop_commands.actions._executor.observer_failed = True
        self.assertIn('incomplete', self.app.chat('what have you done today')['reply'])

    def test_inventory_endpoint_requires_local_session_and_chat_uses_same_inventory(self):
        server = DesktopServer(('127.0.0.1', 0), self.app)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        connection = http.client.HTTPConnection(*server.server_address, timeout=2)
        self.addCleanup(connection.close)
        connection.request('GET', '/api/capabilities')
        response = connection.getresponse()
        self.assertEqual(response.status, 403)
        response.read()
        headers = {'Cookie': 'iris_session=' + server.session, 'X-IRIS-Request': '1',
                   'Content-Type': 'application/json'}
        connection.request('GET', '/api/capabilities', headers=headers)
        response = connection.getresponse()
        self.assertEqual(response.status, 200)
        inventory = json.loads(response.read())
        connection.request('POST', '/api/chat', json.dumps({'text': 'What can you do?'}), headers)
        response = connection.getresponse()
        self.assertEqual(response.status, 200)
        answer = json.loads(response.read())
        self.assertEqual(answer['capabilities'], inventory)
        self.assertEqual(answer['route'], 'LOCAL')
        self.assertEqual(self.brain.calls, [])


if __name__ == '__main__':
    unittest.main()
