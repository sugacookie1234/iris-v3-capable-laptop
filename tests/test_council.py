from __future__ import annotations

import re
import threading
import unittest

from iris.brain.council import (
    CouncilExecutionError,
    CouncilExecutor,
    calculate_aggregate_rankings,
    parse_final_ranking,
)
from iris.brain.llm import (
    LLMRegistry,
    LLMRequest,
    LLMResponse,
    ModelTarget,
)
from iris.brain.model_policy import (
    CouncilPlan,
    CouncilSeat,
)


class CouncilTestProvider:
    def __init__(
        self,
        name: str,
        fail_candidate: bool = False,
        fail_ranking: bool = False,
        malformed_ranking: bool = False,
        fail_chairman: bool = False,
    ) -> None:
        self._name = name
        self.fail_candidate = fail_candidate
        self.fail_ranking = fail_ranking
        self.malformed_ranking = malformed_ranking
        self.fail_chairman = fail_chairman

        self.requests: list[LLMRequest] = []
        self._lock = threading.Lock()

    @property
    def name(self) -> str:
        return self._name

    def healthcheck(self) -> bool:
        return True

    def generate(
        self,
        request: LLMRequest,
    ) -> LLMResponse:
        with self._lock:
            self.requests.append(request)

        system = request.messages[0].content

        if "INDEPENDENT SEAT" in system:
            if self.fail_candidate:
                raise RuntimeError(
                    f"{self.name} candidate failure"
                )

            text = (
                f"Independent recommendation from "
                f"{request.model}."
            )

        elif "PEER EVALUATION" in system:
            if self.fail_ranking:
                raise RuntimeError(
                    f"{self.name} ranking failure"
                )

            if self.malformed_ranking:
                text = (
                    "All responses have strengths, "
                    "but I forgot the required ranking."
                )

            else:
                prompt = request.messages[-1].content

                labels = re.findall(
                    r"Response ([A-Z]):",
                    prompt,
                )

                # Deterministic test preference:
                # reverse the available labels.
                ordered = list(reversed(labels))

                ranking_lines = "\n".join(
                    f"{index}. Response {label}"
                    for index, label in enumerate(
                        ordered,
                        start=1,
                    )
                )

                text = (
                    "Concise peer evaluation.\n\n"
                    "FINAL RANKING:\n"
                    f"{ranking_lines}"
                )

        elif "CHAIRMAN" in system:
            if self.fail_chairman:
                raise RuntimeError(
                    f"{self.name} chairman failure"
                )

            text = "Final council-synthesized answer."

        else:
            raise AssertionError(
                "Unexpected Council prompt."
            )

        return LLMResponse(
            text=text,
            provider=self.name,
            model=request.model,
            input_tokens=100,
            output_tokens=25,
        )


class CouncilTests(unittest.TestCase):
    def make_setup(
        self,
    ) -> tuple[
        CouncilExecutor,
        CouncilPlan,
        dict[str, CouncilTestProvider],
    ]:
        registry = LLMRegistry()

        providers = {
            "a": CouncilTestProvider("a"),
            "b": CouncilTestProvider("b"),
            "c": CouncilTestProvider("c"),
            "chair": CouncilTestProvider("chair"),
        }

        for provider in providers.values():
            registry.register(provider)

        plan = CouncilPlan(
            seats=(
                CouncilSeat(
                    name="strategist",
                    role="Focus on long-term strategy.",
                    target=ModelTarget(
                        "a",
                        "model-a",
                    ),
                ),
                CouncilSeat(
                    name="skeptic",
                    role="Challenge assumptions.",
                    target=ModelTarget(
                        "b",
                        "model-b",
                    ),
                ),
                CouncilSeat(
                    name="operator",
                    role="Focus on execution.",
                    target=ModelTarget(
                        "c",
                        "model-c",
                    ),
                ),
            ),
            chairman=ModelTarget(
                "chair",
                "chairman-model",
            ),
        )

        return (
            CouncilExecutor(registry),
            plan,
            providers,
        )

    def test_full_council_produces_final_answer(
        self,
    ) -> None:
        executor, plan, _ = self.make_setup()

        result = executor.deliberate(
            "Which plan should we choose?",
            plan,
        )

        self.assertEqual(
            result.text,
            "Final council-synthesized answer.",
        )

        self.assertEqual(
            len(result.candidates),
            3,
        )

        self.assertEqual(
            len(result.rankings),
            3,
        )

        self.assertEqual(
            result.chairman_provider,
            "chair",
        )

        self.assertEqual(
            result.failures,
            (),
        )

    def test_candidate_labels_are_stable(
        self,
    ) -> None:
        executor, plan, _ = self.make_setup()

        result = executor.deliberate(
            "Test labels",
            plan,
        )

        self.assertEqual(
            tuple(
                candidate.label
                for candidate in result.candidates
            ),
            ("A", "B", "C"),
        )

        self.assertEqual(
            tuple(
                candidate.seat_name
                for candidate in result.candidates
            ),
            (
                "strategist",
                "skeptic",
                "operator",
            ),
        )

    def test_ranking_parser_reads_final_section(
        self,
    ) -> None:
        parsed = parse_final_ranking(
            """
Evaluation text.

FINAL RANKING:
1. Response C
2. Response A
3. Response B
""",
            ("A", "B", "C"),
        )

        self.assertEqual(
            parsed,
            ("C", "A", "B"),
        )

    def test_ranking_parser_ignores_unknown_and_duplicates(
        self,
    ) -> None:
        parsed = parse_final_ranking(
            """
FINAL RANKING:
1. Response B
2. Response Z
3. Response B
4. Response A
""",
            ("A", "B"),
        )

        self.assertEqual(
            parsed,
            ("B", "A"),
        )

    def test_aggregate_ranking_is_calculated(
        self,
    ) -> None:
        executor, plan, _ = self.make_setup()

        result = executor.deliberate(
            "Aggregate ranking test",
            plan,
        )

        # Every fake reviewer reverses A/B/C -> C/B/A.
        self.assertEqual(
            tuple(
                item.label
                for item in result.aggregate
            ),
            ("C", "B", "A"),
        )

        self.assertEqual(
            result.aggregate[0].average_rank,
            1.0,
        )

        self.assertEqual(
            result.aggregate[0].rankings_count,
            3,
        )

    def test_peer_stage_is_anonymous(
        self,
    ) -> None:
        executor, plan, providers = self.make_setup()

        executor.deliberate(
            "Anonymity test",
            plan,
        )

        for name in ("a", "b", "c"):
            ranking_requests = [
                request
                for request in providers[name].requests
                if "PEER EVALUATION"
                in request.messages[0].content
            ]

            self.assertEqual(
                len(ranking_requests),
                1,
            )

            prompt = ranking_requests[0].messages[-1].content

            self.assertNotIn(
                "strategist",
                prompt.lower(),
            )
            self.assertNotIn(
                "skeptic",
                prompt.lower(),
            )
            self.assertNotIn(
                "operator",
                prompt.lower(),
            )

    def test_one_candidate_failure_is_tolerated(
        self,
    ) -> None:
        executor, plan, providers = self.make_setup()

        providers["c"].fail_candidate = True

        result = executor.deliberate(
            "Degraded candidate test",
            plan,
        )

        self.assertEqual(
            len(result.candidates),
            2,
        )

        self.assertEqual(
            result.text,
            "Final council-synthesized answer.",
        )

        self.assertTrue(
            any(
                failure.startswith(
                    "candidate:operator:"
                )
                for failure in result.failures
            )
        )

    def test_fewer_than_two_candidates_fails(
        self,
    ) -> None:
        executor, plan, providers = self.make_setup()

        providers["b"].fail_candidate = True
        providers["c"].fail_candidate = True

        with self.assertRaises(
            CouncilExecutionError
        ):
            executor.deliberate(
                "Not enough candidates",
                plan,
            )

    def test_one_ranking_failure_is_tolerated(
        self,
    ) -> None:
        executor, plan, providers = self.make_setup()

        providers["b"].fail_ranking = True

        result = executor.deliberate(
            "Ranking failure test",
            plan,
        )

        self.assertEqual(
            len(result.rankings),
            2,
        )

        self.assertEqual(
            result.text,
            "Final council-synthesized answer.",
        )

    def test_no_valid_rankings_fails(
        self,
    ) -> None:
        executor, plan, providers = self.make_setup()

        for name in ("a", "b", "c"):
            providers[name].malformed_ranking = True

        with self.assertRaisesRegex(
            CouncilExecutionError,
            "no valid peer rankings",
        ):
            executor.deliberate(
                "Broken rankings test",
                plan,
            )

    def test_chairman_receives_aggregate_ranking(
        self,
    ) -> None:
        executor, plan, providers = self.make_setup()

        executor.deliberate(
            "Chairman context test",
            plan,
        )

        request = providers["chair"].requests[0]
        prompt = request.messages[-1].content

        self.assertIn(
            "Aggregate ranking:",
            prompt,
        )

        self.assertIn(
            "average rank",
            prompt,
        )

        self.assertNotIn(
            "strategist",
            prompt.lower(),
        )

    def test_chairman_failure_fails_loudly(
        self,
    ) -> None:
        executor, plan, providers = self.make_setup()

        providers["chair"].fail_chairman = True

        with self.assertRaisesRegex(
            CouncilExecutionError,
            "chairman failed",
        ):
            executor.deliberate(
                "Chairman failure test",
                plan,
            )


if __name__ == "__main__":
    unittest.main()
