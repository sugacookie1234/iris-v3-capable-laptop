from dataclasses import FrozenInstanceError, replace
import unittest
from unittest.mock import patch

from iris.generalist.plan import PlanLimits, notes_briefing_preview, validate_plan
from iris.tools.models import ArgumentType, AuthorityLevel, RequestOrigin, ToolArgument, ToolSpec


SEARCH = ToolSpec('obsidian_search', 'Search notes', AuthorityLevel.GREEN, True, (), ('obsidian.read',), 30,
                  (ToolArgument('query', 'Query', ArgumentType.STRING),), True)
READ = replace(SEARCH, name='obsidian_read', arguments=(ToolArgument('path', 'Path', ArgumentType.STRING),))


def proposal(*nodes):
    return {'objective': 'Inspect selected notes', 'nodes': list(nodes)}


def node(identifier='search', tool='obsidian_search', **extra):
    return {'id': identifier, 'tool': tool, 'arguments': {'query': 'synthetic topic'}, **extra}


class PlanTests(unittest.TestCase):
    def validate(self, data, specs=(SEARCH, READ), **options):
        return validate_plan(data, specs, permissions=('obsidian.read',), **options)

    def test_order_is_topological_and_snapshot_is_deeply_immutable(self):
        search = node()
        read = node('read', 'obsidian_read', arguments={'path': 'Projects/Synthetic.md'}, depends_on=['search'])
        plan = self.validate(proposal(read, search))
        self.assertEqual(plan.order, ('search', 'read'))
        self.assertEqual(plan.total_tool_timeout_seconds, 60)
        search['arguments']['query'] = 'changed after validation'
        read['depends_on'].append('invented')
        self.assertEqual(plan.nodes[1].arguments, (('query', 'synthetic topic'),))
        self.assertEqual(plan.nodes[0].depends_on, ('search',))
        with self.assertRaises(FrozenInstanceError):
            plan.nodes[0].tool = 'shell'

    def test_unknown_tools_dependencies_duplicates_and_cycles_fail(self):
        invalid = [proposal(node(tool='shell')), proposal(node(depends_on=['missing'])),
                   proposal(node(), node()), proposal(node(depends_on=['search'])),
                   proposal(node('one', depends_on=['two']), node('two', depends_on=['one']))]
        for data in invalid:
            with self.subTest(data=data), self.assertRaises(ValueError):
                self.validate(data)

    def test_only_host_permitted_local_read_only_tools_are_accepted(self):
        for spec in (replace(SEARCH, local_only=False), replace(SEARCH, reversible=False),
                     replace(SEARCH, side_effects=('writes notes',)), replace(SEARCH, authority=AuthorityLevel.YELLOW)):
            with self.subTest(spec=spec), self.assertRaises(ValueError):
                self.validate(proposal(node()), (spec,))
        with self.assertRaises(ValueError):
            validate_plan(proposal(node()), (SEARCH,))
        for origin in (RequestOrigin.MEMORY, RequestOrigin.EXTERNAL, 'user'):
            with self.subTest(origin=origin), self.assertRaises(ValueError):
                self.validate(proposal(node()), origin=origin)

    def test_arguments_cannot_carry_unknown_fields_nested_values_or_output_references(self):
        for arguments in ({}, {'query': {}}, {'query': ['text']}, {'query': True},
                          {'query': 'text', 'shell': 'command'}, {'query': {'from_node': 'search'}}):
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                self.validate(proposal(node(arguments=arguments)))
        with self.assertRaises(ValueError):
            self.validate(proposal(node(permissions=['obsidian.read'])))

    def test_scalar_validation_excludes_bool_as_number_and_nonfinite_values(self):
        numeric = replace(SEARCH, arguments=(ToolArgument('query', 'Number', ArgumentType.NUMBER),))
        for value in (True, float('nan'), float('inf')):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.validate(proposal(node(arguments={'query': value})), (numeric,))
        self.assertEqual(self.validate(proposal(node(arguments={'query': 3})), (numeric,)).nodes[0].arguments,
                         (('query', 3),))

    def test_node_text_and_timeout_budgets_are_enforced(self):
        for data, limits in ((proposal(*[node(f'n{i}') for i in range(9)]), PlanLimits()),
                             (proposal(node(arguments={'query': 'x' * 2001})), PlanLimits()),
                             (proposal(node()), PlanLimits(max_seconds=29)),
                             (proposal(node()), PlanLimits(max_nodes=True)),
                             (proposal(node()), PlanLimits(max_seconds=float('nan'))),
                             (proposal(node()), PlanLimits(max_nodes=9))):
            with self.subTest(limits=limits), self.assertRaises(ValueError):
                self.validate(data, limits=limits)
        with self.assertRaises(ValueError):
            self.validate(proposal(*[node(f'n{i}') for i in range(5)]))

    def test_preview_declares_missing_steps_and_never_executes(self):
        with patch('iris.tools.executor.ToolExecutor.execute', side_effect=AssertionError('Must not execute')):
            preview = notes_briefing_preview('synthetic topic', (SEARCH, READ), permissions=('obsidian.read',))
        self.assertEqual([step['state'] for step in preview['stages']], ['ready', 'needs_selection', 'unavailable'])
        self.assertFalse(preview['executable'])
        self.assertFalse(preview['executed'])
        self.assertEqual(preview['model_calls'], 0)
        self.assertIsNone(preview['stages'][2]['tool'])
        absent = notes_briefing_preview('topic', ())
        self.assertEqual([step['state'] for step in absent['stages']], ['blocked', 'blocked', 'unavailable'])


if __name__ == '__main__':
    unittest.main()
