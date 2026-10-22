from pathlib import Path
import tempfile
import unittest

from iris.identity import (
    BehaviourMode,
    FULL_INTRODUCTION,
    SHORT_NAME_RESPONSE,
    compile_identity_prompt,
    deterministic_identity_response,
    load_identity,
)


class IdentityTests(unittest.TestCase):
    def test_explicit_identity_requests_are_deterministic_and_canonical(self) -> None:
        self.assertEqual(deterministic_identity_response("What’s your name?"), SHORT_NAME_RESPONSE)
        self.assertEqual(deterministic_identity_response("Give me your full introduction."), FULL_INTRODUCTION)
        self.assertIn("IRIS", FULL_INTRODUCTION)
        self.assertIsNone(deterministic_identity_response("tell me about IRIS_MODEL"))

    def test_default_identity_loads(self) -> None:
        identity = load_identity()

        self.assertIn("Identity", identity.sections)
        self.assertIn("Personality", identity.sections)
        self.assertIn("Behaviour Modes", identity.sections)

    def test_all_behaviour_modes_exist(self) -> None:
        identity = load_identity()

        for mode in BehaviourMode:
            text = identity.subsection("Behaviour Modes", mode.value)
            self.assertTrue(text)

    def test_compiled_prompt_is_smaller_than_full_identity(self) -> None:
        identity = load_identity()

        for mode in BehaviourMode:
            prompt = compile_identity_prompt(identity, mode)

            self.assertTrue(prompt)
            self.assertLess(len(prompt), len(identity.raw_text))

    def test_normal_mode_does_not_load_tool_rules(self) -> None:
        identity = load_identity()
        prompt = compile_identity_prompt(identity, BehaviourMode.NORMAL)

        self.assertNotIn("# Tool Behaviour", prompt)
        self.assertNotIn("# Authority", prompt)

    def test_operations_mode_loads_tool_and_authority_rules(self) -> None:
        identity = load_identity()
        prompt = compile_identity_prompt(identity, BehaviourMode.OPERATIONS)

        self.assertIn("# Tool Behaviour", prompt)
        self.assertIn("# Authority", prompt)

    def test_truthfulness_prompt_requires_plain_correction(self) -> None:
        identity = load_identity()
        prompt = compile_identity_prompt(identity, BehaviourMode.NORMAL)

        self.assertIn("When the user identifies a mistake, acknowledge it plainly", prompt)
        self.assertIn("Do not defend or quietly preserve a claim", prompt)

    def test_companion_mode_loads_goals_and_initiative(self) -> None:
        identity = load_identity()
        prompt = compile_identity_prompt(identity, BehaviourMode.COMPANION)

        self.assertIn("# Initiative", prompt)
        self.assertIn("# Goals and Accountability", prompt)

    def test_missing_required_section_fails_loudly(self) -> None:
        bad_identity = """
# I.R.I.S.

## Identity
Test identity.

## Personality
Test personality.
"""

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "identity.md"
            path.write_text(bad_identity, encoding="utf-8")

            with self.assertRaises(ValueError):
                load_identity(path)


if __name__ == "__main__":
    unittest.main()
