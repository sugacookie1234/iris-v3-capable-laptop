import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from iris.memory.context import MemoryContextMode
from iris.memory.integration import assemble_reasoning_context
from iris.memory.models import MemoryCategory, MemoryItem
from iris.memory.store import MemoryStore
from iris.obsidian import (
    DEFAULT_INDEX_NAME,
    ObsidianKnowledgeAdapter,
)
from iris.terminal import create_brain, load_config


class ObsidianKnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, relative, text, *, data=False):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if data:
            path.write_bytes(text)
        else:
            path.write_text(text, encoding="utf-8")
        return path

    def adapter(self, **kwargs):
        return ObsidianKnowledgeAdapter(str(self.root), **kwargs)

    def test_index_is_loaded_first_and_selects_markdown_and_wikilinks(self):
        self.write(DEFAULT_INDEX_NAME, "# Projects\n- [[Projects/Alpha]] — architecture work\n")
        self.write("Projects/Alpha.md", "Alpha architecture decision.")
        self.write("Projects/Orphan.md", "architecture but not mapped in the index.")
        context = self.adapter().context_for("Explain the architecture project")
        self.assertTrue(context.index_loaded)
        self.assertEqual(context.sources, ("Projects/Alpha.md",))
        self.assertIn("Alpha architecture decision", context.text)
        self.assertNotIn("Orphan", context.text)

    def test_markdown_links_and_headings_are_used_for_relevance(self):
        self.write(DEFAULT_INDEX_NAME, "# Finance\n[Budget](Finance/Budget.md)\n# Engineering\n[API](Engineering/API.md)\n")
        self.write("Finance/Budget.md", "budget details")
        self.write("Engineering/API.md", "api details")
        context = self.adapter().context_for("What is the API design?")
        self.assertEqual(context.sources, ("Engineering/API.md",))
        self.assertIn("Engineering/API.md", context.text)
        self.assertNotIn("budget details", context.text)

    def test_missing_or_unconfigured_vault_degrades_cleanly(self):
        self.assertIsNone(ObsidianKnowledgeAdapter.configured(None))
        self.assertIsNone(ObsidianKnowledgeAdapter.configured(str(self.root / "missing")))
        self.assertEqual(ObsidianKnowledgeAdapter.configured(str(self.root)).context_for("hello").text, "")

    def test_new_vault_configuration_is_optional_and_attaches_adapter(self):
        self.write(DEFAULT_INDEX_NAME, "[[Project]]")
        self.write("Project.md", "configured knowledge")
        config = load_config({
            "IRIS_PROVIDER_URL": "http://localhost:8000",
            "IRIS_MODEL": "test",
            "IRIS_OBSIDIAN_VAULT": str(self.root),
            "IRIS_OBSIDIAN_INDEX": DEFAULT_INDEX_NAME,
        })
        self.assertEqual(config.obsidian_vault, str(self.root))
        self.assertEqual(config.obsidian_index, DEFAULT_INDEX_NAME)
        brain = create_brain(config)
        self.assertIsNotNone(brain._obsidian_knowledge)

    def test_traversal_and_out_of_vault_links_are_skipped(self):
        self.write(DEFAULT_INDEX_NAME, "[[../outside]]\n[escape](../outside.md)\n[[Good]]")
        self.write("Good.md", "safe note")
        self.write("outside.md", "outside note")
        context = self.adapter().context_for("good outside")
        self.assertEqual(context.sources, ("Good.md",))
        self.assertNotIn("outside note", context.text)

    def test_symlinks_hidden_backups_and_zone_identifier_are_excluded(self):
        self.write(DEFAULT_INDEX_NAME, "[[Good]] [[.hidden]] [[Old]] [[Sidecar]] [[Linked]]")
        self.write("Good.md", "good note")
        self.write(".hidden.md", "hidden note")
        self.write("Old.md.bak", "backup note")
        self.write("Sidecar.md:Zone.Identifier", "sidecar note")
        # NTFS creates an empty base file for an alternate stream. It is a
        # legitimate note; the stream contents must never enter context.
        if (self.root / "Sidecar.md").exists():
            (self.root / "Sidecar.md").unlink()
        outside = self.root / "outside.md"
        outside.write_text("outside note", encoding="utf-8")
        (self.root / "Linked.md").symlink_to(outside)
        context = self.adapter().context_for("good hidden old sidecar linked")
        self.assertEqual(context.sources, ("Good.md",))
        self.assertNotIn("outside note", context.text)

    def test_per_note_and_total_limits_are_enforced(self):
        self.write(DEFAULT_INDEX_NAME, "[[One]] [[Two]]")
        self.write("One.md", "one " * 20)
        self.write("Two.md", "two " * 20)
        context = ObsidianKnowledgeAdapter(
            str(self.root), max_note_bytes=30, max_total_bytes=35, max_chars=500,
        ).context_for("one two")
        self.assertTrue(context.sources)
        self.assertLessEqual(context.total_bytes, 35)
        self.assertLessEqual(len(context.text), 500)

    def test_nested_index_decodes_spaces_and_vault_relative_wikilinks(self):
        self.write('IRIS/index.md', '[Personal profile](Personal/About%20me.md)\n[[IRIS/Design/Master]]')
        self.write('IRIS/Personal/About me.md', 'Profile provenance and details.')
        self.write('IRIS/Design/Master.md', 'Master architecture decisions.')
        adapter = self.adapter(index_path='IRIS/index.md')
        self.assertIn('IRIS/Personal/About me.md', adapter.context_for('Read the personal profile About me').sources)
        self.assertIn('IRIS/Design/Master.md', adapter.context_for('Master architecture').sources)

    def test_large_note_returns_bounded_relevant_excerpt_instead_of_disappearing(self):
        self.write(DEFAULT_INDEX_NAME, '[[Architecture]]')
        content = '# Historical source; not verified current\n\n' + ('Background paragraph.\n\n' * 1000)
        content += '## Durable recovery\nRestart recovery uses verified receipts and checkpoints.'
        self.write('Architecture.md', content)
        context = self.adapter().context_for('Architecture durable recovery checkpoints')
        self.assertEqual(context.sources, ('Architecture.md',))
        self.assertIn('Historical source', context.text)
        self.assertIn('checkpoints', context.text)
        self.assertIn('Excerpt', context.text)
        self.assertLessEqual(len(context.text), 12_000)
        self.assertLessEqual(context.total_bytes, 16 * 1024)

    def test_encoded_traversal_and_credentials_after_excerpt_remain_blocked(self):
        self.write(DEFAULT_INDEX_NAME, '[Escape](%2e%2e/outside.md)\n[[Architecture]]')
        self.write('Architecture.md', 'Architecture\n\n' * 2000 + 'api_key=abcdefghijklmnop123456')
        context = self.adapter().context_for('Architecture escape')
        self.assertEqual(context.sources, ())

    def test_failed_candidate_attempts_are_deduplicated_and_bounded(self):
        index = '[[Blocked]]\n' * 1000 + '\n'.join(f'[[Blocked {i}]]' for i in range(100))
        adapter = self.adapter(max_notes=2)
        def read(root, path, count):
            if path == DEFAULT_INDEX_NAME:
                return {'text': index, 'truncated': False}
            raise PermissionError('unreadable')
        with patch('iris.obsidian._safe_note_text', side_effect=read) as opened:
            self.assertEqual(adapter.context_for('Blocked').sources, ())
        paths = [call.args[1] for call in opened.call_args_list[1:]]
        self.assertEqual(len(paths), len(set(paths)))
        self.assertLessEqual(len(paths), 8)

    def test_note_title_beats_shared_parent_folder_in_ranking(self):
        self.write(DEFAULT_INDEX_NAME, '[Tracker](Design/Tracker.md)\n[Master design](Design/Master_design.md)')
        self.write('Design/Tracker.md', 'Tracker')
        self.write('Design/Master_design.md', 'Architecture design')
        self.assertEqual(self.adapter(max_notes=1).context_for('design').sources, ('Design/Master_design.md',))

    def test_malformed_notes_are_skipped_without_failing_context(self):
        self.write(DEFAULT_INDEX_NAME, "[[Bad]] [[Good]]")
        self.write("Bad.md", b"\xff\xfe", data=True)
        self.write("Good.md", "usable note")
        context = self.adapter().context_for("bad good")
        self.assertEqual(context.sources, ("Good.md",))
        self.assertNotIn("Bad", context.text)

    def test_obsidian_context_stays_separate_from_sqlite_memory(self):
        self.write(DEFAULT_INDEX_NAME, "[[Project]]")
        self.write("Project.md", "vault project note")
        memory_path = self.root / "memory.sqlite3"
        with MemoryStore(memory_path) as store:
            store.insert(MemoryItem(MemoryCategory.PREFERENCE, "user", "project", "sqlite fact", "sqlite fact", "test"))
            context = assemble_reasoning_context(
                store, "project", obsidian=self.adapter(),
            )
            self.assertIn("sqlite fact", context.text)
            self.assertIn("vault project note", context.text)
            self.assertEqual(len(store.current()), 1)
            self.assertEqual(context.mode, MemoryContextMode.NORMAL)


if __name__ == "__main__":
    unittest.main()
