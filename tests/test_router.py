import unittest

from iris.brain.router import (
    ReasoningLevel,
    RouteKind,
    route_message,
)
from iris.identity import BehaviourMode


class RouterTests(unittest.TestCase):
    def test_greeting_is_fast_conversation(self) -> None:
        decision = route_message("hi")

        self.assertEqual(decision.route, RouteKind.CONVERSATION)
        self.assertEqual(decision.mode, BehaviourMode.NORMAL)
        self.assertEqual(decision.reasoning, ReasoningLevel.FAST)
        self.assertFalse(decision.needs_tools)

    def test_calendar_request_routes_to_operations(self) -> None:
        decision = route_message("check my calendar for tomorrow")

        self.assertEqual(decision.route, RouteKind.OPERATIONS)
        self.assertEqual(decision.mode, BehaviourMode.OPERATIONS)
        self.assertTrue(decision.needs_tools)

    def test_personal_advice_routes_to_companion(self) -> None:
        decision = route_message(
            "I'm not sure whether I should keep working on this project"
        )

        self.assertEqual(decision.route, RouteKind.COMPANION)
        self.assertEqual(decision.mode, BehaviourMode.COMPANION)
        self.assertFalse(decision.needs_tools)

    def test_urgent_language_overrides_normal_routing(self) -> None:
        decision = route_message(
            "I'm going to miss class, check my schedule right now"
        )

        self.assertEqual(decision.route, RouteKind.URGENT)
        self.assertEqual(decision.mode, BehaviourMode.URGENT)

    def test_explicit_council_request_uses_council(self) -> None:
        decision = route_message(
            "Run this through the council and tell me whether the plan is good"
        )

        self.assertEqual(decision.reasoning, ReasoningLevel.COUNCIL)

    def test_analysis_request_uses_deep_reasoning(self) -> None:
        decision = route_message(
            "Analyze the architecture and compare the two approaches"
        )

        self.assertEqual(decision.reasoning, ReasoningLevel.DEEP)
        self.assertFalse(decision.needs_tools)

    def test_github_action_requires_tools(self) -> None:
        decision = route_message("check my GitHub repositories")

        self.assertEqual(decision.route, RouteKind.OPERATIONS)
        self.assertTrue(decision.needs_tools)

    def test_empty_input_is_deterministic(self) -> None:
        decision = route_message("   ")

        self.assertEqual(
            decision.reasoning,
            ReasoningLevel.DETERMINISTIC,
        )

    def test_incidental_reasoning_terms_do_not_escalate(self) -> None:
        for text in (
            "What is the council?",
            "What does architecture mean?",
            "Open my council notes",
            "Read my architecture file",
            "What does compare mean?",
            'The example says "ask the council".',
            'The example says "analyze the architecture".',
        ):
            with self.subTest(text=text):
                self.assertEqual(route_message(text).reasoning, ReasoningLevel.FAST)

    def test_negated_reasoning_requests_do_not_escalate(self) -> None:
        for text in (
            "Don't ask the council; just say hello",
            "Please do not analyze the architecture",
            "Don't help me decide between local and cloud speech by comparing cost, privacy, and speed; just say hi",
        ):
            with self.subTest(text=text):
                self.assertEqual(route_message(text).reasoning, ReasoningLevel.FAST)

    def test_natural_council_requests_remain_supported(self) -> None:
        for text in (
            "Could you ask the council about this plan?",
            "Iris, please consult the council about this plan",
            "Give me multiple perspectives on this decision",
            "Debate this approach",
            "Council: help me decide",
        ):
            with self.subTest(text=text):
                self.assertEqual(route_message(text).reasoning, ReasoningLevel.COUNCIL)

    def test_planning_and_detailed_explanations_are_deep(self) -> None:
        for text in (
            "Make a detailed migration plan for my application",
            "Could you explain how speech recognition works under the hood?",
            "Please troubleshoot why the microphone stops after every response",
        ):
            with self.subTest(text=text):
                self.assertEqual(route_message(text).reasoning, ReasoningLevel.DEEP)

    def test_multiple_constraints_can_select_council_automatically(self) -> None:
        text = (
            "Help me decide between local and cloud speech recognition for my assistant, "
            "considering cost, privacy, speed, and ongoing maintenance."
        )
        decision = route_message(text)
        self.assertEqual(decision.reasoning, ReasoningLevel.COUNCIL)
        self.assertFalse(decision.needs_tools)
        self.assertIn("competing constraints", decision.reason)

    def test_simple_decision_does_not_launch_council(self) -> None:
        self.assertEqual(route_message("Should I have tea or coffee?").reasoning, ReasoningLevel.FAST)
        self.assertEqual(route_message("Compare the cost and price of these two laptops").reasoning,
                         ReasoningLevel.DEEP)

    def test_council_opt_out_keeps_complex_decision_on_single_model(self) -> None:
        decision = route_message(
            "Do not use the council. Help me decide between local and cloud speech "
            "recognition for my assistant, considering cost, privacy, speed, and maintenance."
        )
        self.assertEqual(decision.reasoning, ReasoningLevel.DEEP)

    def test_automatic_council_does_not_disable_requested_tools(self) -> None:
        decision = route_message(
            "Help me decide between local and cloud speech recognition for my assistant, "
            "considering cost, privacy, speed, and maintenance; then create a task to test it."
        )
        self.assertEqual(decision.reasoning, ReasoningLevel.DEEP)
        self.assertEqual(decision.route, RouteKind.OPERATIONS)
        self.assertTrue(decision.needs_tools)

    def test_urgency_avoids_automatic_council_latency(self) -> None:
        decision = route_message(
            "Help me decide between local and cloud speech recognition for my assistant "
            "right now, considering cost, privacy, speed, and maintenance."
        )
        self.assertEqual(decision.reasoning, ReasoningLevel.FAST)
        self.assertEqual(decision.route, RouteKind.URGENT)


if __name__ == "__main__":
    unittest.main()
