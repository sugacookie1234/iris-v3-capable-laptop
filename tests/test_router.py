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


if __name__ == "__main__":
    unittest.main()
