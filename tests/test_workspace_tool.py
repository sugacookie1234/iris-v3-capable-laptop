import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from iris.brain.llm import LLMResponse, LLMToolCall
from iris.terminal import create_brain, load_config
from iris.tools import (
    AuthorityContext, AuthorityLevel, FailureCode, RequestOrigin, ResultStatus, ToolCall,
    ToolExecutor, workspace_registry,
)
from iris.tools.workspace import MAX_LIST_ENTRIES, MAX_READ_BYTES, MAX_READ_CHARS, is_workspace_request, list_files, read_text


class WorkspaceToolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "workspace"
        self.root.mkdir()
        (self.root / "README.md").write_text("safe text", encoding="utf-8")
        (self.root / "folder").mkdir()
        (self.root / "folder" / "nested.txt").write_text("nested", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_registered_tools_are_green_read_only_and_bounded(self):
        specs = workspace_registry(str(self.root)).specifications()
        self.assertEqual({spec.name for spec in specs}, {"workspace_list", "workspace_read"})
        self.assertTrue(all(spec.authority == AuthorityLevel.GREEN for spec in specs))
        self.assertTrue(all(spec.reversible and not spec.side_effects for spec in specs))
        self.assertTrue(all(spec.required_permissions == ("workspace.read",) for spec in specs))
        self.assertTrue(all(spec.timeout > 0 for spec in specs))

    def test_authority_requires_an_affirmative_current_workspace_request(self):
        self.assertTrue(is_workspace_request("Please read the README file"))
        self.assertTrue(is_workspace_request("list files in the workspace"))
        self.assertFalse(is_workspace_request("do not read the file"))
        self.assertFalse(is_workspace_request("I read a file yesterday"))

    def test_lists_files_and_reads_text_with_limits(self):
        listed = list_files(str(self.root))
        self.assertEqual([item["name"] for item in listed["entries"]], ["README.md", "folder"])
        self.assertEqual(read_text(str(self.root), "folder/nested.txt")["text"], "nested")
        result = read_text(str(self.root), "README.md", max_chars=4)
        self.assertEqual(result["text"], "safe")
        self.assertTrue(result["truncated"])
        for index in range(MAX_LIST_ENTRIES + 1):
            (self.root / f"file{index:03}.txt").touch()
        self.assertTrue(list_files(str(self.root))["truncated"])

    def test_blocks_traversal_absolute_paths_and_symlink_escapes(self):
        outside = Path(self.tmp.name) / "outside.txt"
        outside.write_text("secret outside", encoding="utf-8")
        for path in ("../outside.txt", str(outside), "folder/../../outside.txt"):
            with self.subTest(path=path), self.assertRaises((ValueError, PermissionError)):
                read_text(str(self.root), path)
        (self.root / "escape.txt").symlink_to(outside)
        (self.root / "escape_dir").symlink_to(outside.parent, target_is_directory=True)
        with self.assertRaises(OSError):
            read_text(str(self.root), "escape.txt")
        with self.assertRaises(OSError):
            list_files(str(self.root), "escape_dir")

    def test_hides_dotfiles_and_credential_names_and_refuses_direct_reads(self):
        for name in (".env", ".ssh", "credentials", "secrets", "api_key.json", "client_secret.json", "id_rsa", "private.pem"):
            (self.root / name).write_text("secret", encoding="utf-8")
        visible = {item["name"] for item in list_files(str(self.root))["entries"]}
        self.assertNotIn(".env", visible)
        self.assertNotIn(".ssh", visible)
        self.assertNotIn("credentials", visible)
        self.assertNotIn("secrets", visible)
        self.assertNotIn("api_key.json", visible)
        self.assertNotIn("client_secret.json", visible)
        self.assertNotIn("id_rsa", visible)
        for name in (".env", ".ssh/id", "credentials", "api_key.json", "private.pem"):
            with self.subTest(name=name), self.assertRaises(PermissionError):
                read_text(str(self.root), name)

    def test_rejects_binary_unknown_large_and_directory_reads(self):
        (self.root / "binary.txt").write_bytes(b"\x00binary")
        (self.root / "invalid.txt").write_bytes(b"\xff")
        (self.root / "large.txt").write_bytes(b"a" * (MAX_READ_BYTES + 1))
        for name in ("binary.txt", "invalid.txt", "large.txt", "folder", "README.bin"):
            with self.subTest(name=name), self.assertRaises((ValueError, UnicodeError, IsADirectoryError)):
                read_text(str(self.root), name)
        with self.assertRaises(ValueError):
            read_text(str(self.root), "README.md", MAX_READ_BYTES + 1)

    def test_rejects_credential_like_values_inside_otherwise_readable_files(self):
        (self.root / "settings.json").write_text('{"api_key": "do-not-expose"}', encoding="utf-8")
        with self.assertRaises(PermissionError):
            read_text(str(self.root), "settings.json")

    def test_executor_executes_registered_read_tool_with_metadata(self):
        executor = ToolExecutor(workspace_registry(str(self.root)))
        result = executor.execute(ToolCall("workspace_read", {"path": "README.md"}, RequestOrigin.MODEL),
                                  authority=AuthorityContext(True, frozenset({"workspace.read"})))
        self.assertEqual(result.status, ResultStatus.SUCCESS, result.failure)
        self.assertEqual(result.value["text"], "safe text")
        self.assertEqual(result.plan.spec.authority, AuthorityLevel.GREEN)

    @patch("iris.terminal.OpenAICompatibleProvider.generate")
    def test_brain_parses_a_proposal_and_executes_only_registered_tool(self, generate):
        generate.side_effect = [LLMResponse(
            "", "terminal", "test-model",
            tool_calls=(LLMToolCall("call_read", "workspace_read", {"path": "README.md"}),),
        ), LLMResponse("The README contains safe text.", "terminal", "test-model")]
        config = load_config({"IRIS_PROVIDER_URL": "http://localhost:8000", "IRIS_MODEL": "test-model",
                             "IRIS_WORKSPACE_ROOT": str(self.root)})
        brain = create_brain(config)
        result = brain.respond("read the README file")
        self.assertEqual(result.tool_result.status, ResultStatus.SUCCESS)
        self.assertEqual(result.tool_result.value["text"], "safe text")
        self.assertEqual(result.provider, "terminal")
        prompt = generate.call_args.args[0].messages[0].content
        self.assertIn("native tool call", prompt)
        self.assertNotIn("shell", prompt.lower().split("# read-only tool policy")[-1].split("registered tools")[0])

    @patch("iris.terminal.OpenAICompatibleProvider.generate")
    def test_exact_terminal_requests_execute_registered_workspace_tools(self, generate):
        generate.side_effect = [
            LLMResponse("", "terminal", "test-model", tool_calls=(
                LLMToolCall("call_list", "workspace_list", {}),)),
            LLMResponse("Files: README.md and folder.", "terminal", "test-model"),
            LLMResponse("The README says: safe text.", "terminal", "test-model"),
        ]
        config = load_config({"IRIS_PROVIDER_URL": "http://localhost:8000", "IRIS_MODEL": "test-model",
                             "IRIS_WORKSPACE_ROOT": str(self.root)})
        output = io.StringIO()
        from iris.terminal import chat
        with patch("builtins.input", side_effect=["List the files in this workspace", "Read README.md", "/exit"]), patch("sys.stdout", output):
            chat(create_brain(config))
        rendered = output.getvalue()
        self.assertIn("Files: README.md", rendered)
        self.assertIn("README says: safe text", rendered)
        self.assertNotIn("unavailable", rendered.lower())
        self.assertEqual(generate.call_count, 3)
        first_request = generate.call_args_list[0].args[0]
        first_followup = generate.call_args_list[1].args[0]
        second_followup = generate.call_args_list[2].args[0]
        self.assertEqual({tool.name for tool in first_request.tools}, {"workspace_list", "workspace_read"})
        self.assertFalse(first_followup.tools)
        self.assertFalse(second_followup.tools)
        self.assertEqual(first_followup.messages[-1].role.value, "tool")
        self.assertIn("README.md", second_followup.messages[-1].content)
        self.assertIn("safe text", second_followup.messages[-1].content)
        self.assertEqual(second_followup.messages[-2].tool_calls[0].name, "workspace_read")

    @patch("iris.terminal.OpenAICompatibleProvider.generate")
    def test_read_readme_returns_real_tool_content_for_summary(self, generate):
        repo_root = Path(__file__).resolve().parents[1]
        expected = (repo_root / "README.md").read_text(encoding="utf-8")
        generate.return_value = (
            LLMResponse("The README describes IRIS setup, configuration, and tests.",
                        "terminal", "test-model")
        )
        config = load_config({"IRIS_PROVIDER_URL": "http://localhost:8000", "IRIS_MODEL": "test-model",
                             "IRIS_WORKSPACE_ROOT": str(repo_root)})
        result = create_brain(config).respond("Read README.md")
        self.assertEqual(result.tool_result.status, ResultStatus.SUCCESS)
        self.assertEqual(result.tool_result.plan.spec.name, "workspace_read")
        self.assertEqual(result.tool_result.plan.origin, RequestOrigin.USER)
        self.assertEqual(result.tool_result.value, {
            "path": "README.md", "text": expected[:MAX_READ_CHARS], "truncated": len(expected) > MAX_READ_CHARS,
        })
        self.assertEqual(result.text, "The README describes IRIS setup, configuration, and tests.")
        self.assertEqual(generate.call_count, 1)
        request = generate.call_args.args[0]
        self.assertFalse(request.tools)
        result_message = request.messages[-1]
        self.assertEqual(result_message.role.value, "tool")
        self.assertEqual(json.loads(result_message.content)["result"]["text"], expected[:MAX_READ_CHARS])

    @patch("iris.terminal.OpenAICompatibleProvider.generate")
    def test_brain_never_executes_unregistered_or_malformed_proposals(self, generate):
        generate.return_value = LLMResponse("", "terminal", "test-model", tool_calls=(
            LLMToolCall("call_shell", "shell", {"cmd": "id"}),))
        config = load_config({"IRIS_PROVIDER_URL": "http://localhost:8000", "IRIS_MODEL": "test-model",
                             "IRIS_WORKSPACE_ROOT": str(self.root)})
        result = create_brain(config).respond("read a file")
        self.assertEqual(result.tool_result.failure.code, FailureCode.UNKNOWN_TOOL)
        self.assertIsNone(result.tool_result.plan)
        generate.return_value = LLMResponse(
            "", "terminal", "test-model", tool_calls=(
                LLMToolCall("call_bad", "workspace_read", {"path": 12}),),
        )
        result = create_brain(config).respond("read a file")
        self.assertEqual(result.tool_result.failure.code, FailureCode.INVALID_ARGUMENTS)

    @patch("iris.terminal.OpenAICompatibleProvider.generate")
    def test_negative_user_request_cannot_authorize_model_proposal(self, generate):
        generate.return_value = LLMResponse(
            "", "terminal", "test-model", tool_calls=(
                LLMToolCall("call_denied", "workspace_read", {"path": "README.md"}),),
        )
        config = load_config({"IRIS_PROVIDER_URL": "http://localhost:8000", "IRIS_MODEL": "test-model",
                             "IRIS_WORKSPACE_ROOT": str(self.root)})
        result = create_brain(config).respond("do not read the README file")
        self.assertEqual(result.tool_result.failure.code, FailureCode.AUTHORITY_DENIED)

    @patch("iris.terminal.OpenAICompatibleProvider.generate")
    def test_tool_request_without_configured_root_is_actionable(self, generate):
        config = load_config({"IRIS_PROVIDER_URL": "http://localhost:8000", "IRIS_MODEL": "test-model"})
        output = io.StringIO()
        from unittest.mock import patch as mock_patch
        with mock_patch("builtins.input", side_effect=["read the README file", "/exit"]), mock_patch("sys.stdout", output):
            from iris.terminal import chat
            chat(create_brain(config))
        self.assertIn("IRIS_WORKSPACE_ROOT", output.getvalue())
        generate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
