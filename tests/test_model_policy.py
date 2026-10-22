import unittest

from iris.brain.llm import ModelTarget
from iris.brain.model_policy import (
    CouncilPlan,
    CouncilSeat,
    ModelPolicy,
    SingleModelPlan,
)
from iris.brain.router import ReasoningLevel


class ModelPolicyTests(unittest.TestCase):
    def make_policy(self) -> ModelPolicy:
        return ModelPolicy(
            fast=ModelTarget(
                provider="fast-provider",
                model="fast-model",
            ),
            deep=ModelTarget(
                provider="deep-provider",
                model="deep-model",
            ),
            council=CouncilPlan(
                seats=(
                    CouncilSeat(
                        name="strategist",
                        role="Focus on long-term strategy.",
                        target=ModelTarget(
                            provider="provider-a",
                            model="model-a",
                        ),
                    ),
                    CouncilSeat(
                        name="skeptic",
                        role="Challenge assumptions and identify risks.",
                        target=ModelTarget(
                            provider="provider-b",
                            model="model-b",
                        ),
                    ),
                    CouncilSeat(
                        name="operator",
                        role="Evaluate practical execution.",
                        target=ModelTarget(
                            provider="provider-c",
                            model="model-c",
                        ),
                    ),
                ),
                chairman=ModelTarget(
                    provider="chairman-provider",
                    model="chairman-model",
                ),
            ),
        )

    def test_deterministic_uses_no_model(self) -> None:
        policy = self.make_policy()

        self.assertIsNone(
            policy.plan_for(
                ReasoningLevel.DETERMINISTIC
            )
        )

    def test_fast_uses_fast_target(self) -> None:
        policy = self.make_policy()

        plan = policy.plan_for(
            ReasoningLevel.FAST
        )

        self.assertIsInstance(
            plan,
            SingleModelPlan,
        )
        assert isinstance(plan, SingleModelPlan)

        self.assertEqual(
            plan.target,
            ModelTarget(
                "fast-provider",
                "fast-model",
            ),
        )

    def test_deep_uses_deep_target(self) -> None:
        policy = self.make_policy()

        plan = policy.plan_for(
            ReasoningLevel.DEEP
        )

        self.assertIsInstance(
            plan,
            SingleModelPlan,
        )
        assert isinstance(plan, SingleModelPlan)

        self.assertEqual(
            plan.target.model,
            "deep-model",
        )

    def test_council_returns_council_plan(self) -> None:
        policy = self.make_policy()

        plan = policy.plan_for(
            ReasoningLevel.COUNCIL
        )

        self.assertIsInstance(
            plan,
            CouncilPlan,
        )
        assert isinstance(plan, CouncilPlan)

        self.assertEqual(
            len(plan.seats),
            3,
        )
        self.assertEqual(
            plan.chairman.model,
            "chairman-model",
        )

    def test_council_requires_multiple_seats(self) -> None:
        with self.assertRaises(ValueError):
            CouncilPlan(
                seats=(
                    CouncilSeat(
                        name="only-seat",
                        role="Single perspective.",
                        target=ModelTarget(
                            "provider",
                            "model",
                        ),
                    ),
                ),
                chairman=ModelTarget(
                    "provider",
                    "chairman",
                ),
            )

    def test_council_seat_names_must_be_unique(self) -> None:
        with self.assertRaises(ValueError):
            CouncilPlan(
                seats=(
                    CouncilSeat(
                        name="analyst",
                        role="Analyze.",
                        target=ModelTarget(
                            "a",
                            "model-a",
                        ),
                    ),
                    CouncilSeat(
                        name="ANALYST",
                        role="Analyze differently.",
                        target=ModelTarget(
                            "b",
                            "model-b",
                        ),
                    ),
                ),
                chairman=ModelTarget(
                    "c",
                    "chairman",
                ),
            )

    def test_council_role_cannot_be_empty(self) -> None:
        with self.assertRaises(ValueError):
            CouncilSeat(
                name="skeptic",
                role="   ",
                target=ModelTarget(
                    "provider",
                    "model",
                ),
            )


if __name__ == "__main__":
    unittest.main()
