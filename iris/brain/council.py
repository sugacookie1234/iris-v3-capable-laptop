from __future__ import annotations

import re
from collections import defaultdict
from concurrent.futures import (
    Future,
    ThreadPoolExecutor,
    as_completed,
)
from dataclasses import dataclass

from iris.brain.llm import (
    GenerationOptions,
    LLMMessage,
    LLMRegistry,
    LLMResponse,
    MessageRole,
    ModelTarget,
)
from iris.brain.model_policy import (
    CouncilPlan,
    CouncilSeat,
)


class CouncilExecutionError(RuntimeError):
    """Raised when the I.R.I.S. Council cannot complete reliably."""


@dataclass(frozen=True)
class CouncilCandidate:
    label: str
    seat_name: str
    target: ModelTarget
    text: str


@dataclass(frozen=True)
class CouncilRanking:
    reviewer_name: str
    target: ModelTarget
    evaluation: str
    ranking: tuple[str, ...]


@dataclass(frozen=True)
class AggregateRank:
    label: str
    average_rank: float
    rankings_count: int


@dataclass(frozen=True)
class CouncilResult:
    text: str
    candidates: tuple[CouncilCandidate, ...]
    rankings: tuple[CouncilRanking, ...]
    aggregate: tuple[AggregateRank, ...]
    chairman_provider: str
    chairman_model: str
    failures: tuple[str, ...]


def parse_final_ranking(
    text: str,
    valid_labels: tuple[str, ...],
) -> tuple[str, ...]:
    """
    Parse an explicit FINAL RANKING section.

    Expected examples:

        FINAL RANKING:
        1. Response B
        2. Response A
        3. Response C

    Unknown and duplicate labels are discarded.
    """
    marker = re.search(
        r"FINAL\s+RANKING\s*:",
        text,
        flags=re.IGNORECASE,
    )

    if marker is None:
        return ()

    ranking_section = text[marker.end():]

    matches = re.findall(
        r"(?:\d+\.\s*)?Response\s+([A-Z])\b",
        ranking_section,
        flags=re.IGNORECASE,
    )

    allowed = set(valid_labels)
    result: list[str] = []
    seen: set[str] = set()

    for raw_label in matches:
        label = raw_label.upper()

        if label not in allowed:
            continue

        if label in seen:
            continue

        seen.add(label)
        result.append(label)

    return tuple(result)


def calculate_aggregate_rankings(
    rankings: tuple[CouncilRanking, ...],
    labels: tuple[str, ...],
) -> tuple[AggregateRank, ...]:
    """
    Average each candidate's observed ranking position.

    Lower average rank is better.

    A missing candidate in a malformed/incomplete review does not receive
    an invented position; only actual parsed placements are counted.
    """
    positions: dict[str, list[int]] = defaultdict(list)

    for review in rankings:
        for position, label in enumerate(
            review.ranking,
            start=1,
        ):
            if label in labels:
                positions[label].append(position)

    aggregate: list[AggregateRank] = []

    for label in labels:
        observed = positions.get(label, [])

        if not observed:
            continue

        aggregate.append(
            AggregateRank(
                label=label,
                average_rank=round(
                    sum(observed) / len(observed),
                    3,
                ),
                rankings_count=len(observed),
            )
        )

    aggregate.sort(
        key=lambda item: (
            item.average_rank,
            item.label,
        )
    )

    return tuple(aggregate)


class CouncilExecutor:
    """
    I.R.I.S. multi-model deliberation engine.

    Stage 1
    -------
    Specialized seats independently answer the question in parallel.

    Stage 2
    -------
    Candidate answers are anonymized as Response A/B/C...
    Council seats independently critique and rank them in parallel.

    Stage 3
    -------
    Rankings are aggregated and a chairman synthesizes:
      - the original question
      - anonymous candidate answers
      - anonymous peer evaluations
      - aggregate rankings
      - relevant I.R.I.S. context

    Candidate and review failures are tolerated when enough independent
    reasoning survives to constitute a meaningful Council.
    """

    def __init__(
        self,
        llm_registry: LLMRegistry,
        max_workers: int = 8,
    ) -> None:
        if type(max_workers) is not int or not 1 <= max_workers <= 8:
            raise ValueError(
                "Council max_workers must be between 1 and 8."
            )

        self._llm_registry = llm_registry
        self._max_workers = max_workers

    def deliberate(
        self,
        question: str,
        plan: CouncilPlan,
        system_context: str = "",
    ) -> CouncilResult:
        if not 2 <= len(plan.seats) <= 8:
            raise CouncilExecutionError('Council requires between two and eight seats; no requests were sent.')
        question = question.strip()

        if not question:
            raise ValueError(
                "Council question cannot be empty."
            )

        failures: list[str] = []

        candidates = self._run_candidate_stage(
            question=question,
            plan=plan,
            system_context=system_context,
            failures=failures,
        )

        if len(candidates) < 2:
            detail = "; ".join(failures) or "unknown failure"

            raise CouncilExecutionError(
                "I.R.I.S. Council requires at least two "
                "successful independent candidates. "
                f"{detail}"
            )

        rankings = self._run_ranking_stage(
            question=question,
            plan=plan,
            candidates=candidates,
            system_context=system_context,
            failures=failures,
        )

        if not rankings:
            detail = "; ".join(failures) or (
                "no valid peer rankings were returned"
            )

            raise CouncilExecutionError(
                "I.R.I.S. Council produced no valid "
                f"peer rankings. {detail}"
            )

        labels = tuple(
            candidate.label
            for candidate in candidates
        )

        aggregate = calculate_aggregate_rankings(
            rankings,
            labels,
        )

        chairman_response = self._run_chairman_stage(
            question=question,
            plan=plan,
            candidates=candidates,
            rankings=rankings,
            aggregate=aggregate,
            system_context=system_context,
        )

        return CouncilResult(
            text=chairman_response.text,
            candidates=candidates,
            rankings=rankings,
            aggregate=aggregate,
            chairman_provider=chairman_response.provider,
            chairman_model=chairman_response.model,
            failures=tuple(failures),
        )

    def _run_candidate_stage(
        self,
        question: str,
        plan: CouncilPlan,
        system_context: str,
        failures: list[str],
    ) -> tuple[CouncilCandidate, ...]:
        responses: dict[str, LLMResponse] = {}

        worker_count = min(
            self._max_workers,
            len(plan.seats),
        )

        with ThreadPoolExecutor(
            max_workers=worker_count
        ) as executor:
            futures: dict[
                Future[LLMResponse],
                CouncilSeat,
            ] = {
                executor.submit(
                    self._generate_candidate,
                    seat,
                    question,
                    system_context,
                ): seat
                for seat in plan.seats
            }

            for future in as_completed(futures):
                seat = futures[future]

                try:
                    responses[seat.name] = future.result()

                except Exception as exc:
                    failures.append(
                        f"candidate:{seat.name}:"
                        f"{type(exc).__name__}: {exc}"
                    )

        # Generation is concurrent, but labels remain deterministic.
        candidates: list[CouncilCandidate] = []

        for seat in plan.seats:
            response = responses.get(seat.name)

            if response is None:
                continue

            label = chr(
                ord("A") + len(candidates)
            )

            candidates.append(
                CouncilCandidate(
                    label=label,
                    seat_name=seat.name,
                    target=seat.target,
                    text=response.text,
                )
            )

        return tuple(candidates)

    def _generate_candidate(
        self,
        seat: CouncilSeat,
        question: str,
        system_context: str,
    ) -> LLMResponse:
        system_parts = [
            "[I.R.I.S. COUNCIL — INDEPENDENT SEAT]",
            (
                "You are one independent reasoning seat "
                "inside the I.R.I.S. LLM Council."
            ),
            (
                "Your assigned perspective:\n"
                f"{seat.role}"
            ),
            (
                "Answer independently. Challenge weak assumptions. "
                "Give a clear recommendation, key evidence, "
                "important tradeoffs, uncertainty, and risks."
            ),
            (
                "Do not speculate about what other Council seats "
                "may conclude."
            ),
            (
                "Do not provide hidden chain-of-thought. "
                "Provide concise reasoning suitable for review."
            ),
        ]

        if system_context.strip():
            system_parts.extend(
                [
                    "Relevant I.R.I.S. context:",
                    system_context.strip(),
                ]
            )

        return self._llm_registry.generate(
            target=seat.target,
            messages=[
                LLMMessage(
                    role=MessageRole.SYSTEM,
                    content="\n\n".join(system_parts),
                ),
                LLMMessage(
                    role=MessageRole.USER,
                    content=question,
                ),
            ],
            options=GenerationOptions(
                temperature=0.5,
                max_tokens=900,
            ),
        )

    def _run_ranking_stage(
        self,
        question: str,
        plan: CouncilPlan,
        candidates: tuple[CouncilCandidate, ...],
        system_context: str,
        failures: list[str],
    ) -> tuple[CouncilRanking, ...]:
        candidate_block = self._candidate_block(
            candidates
        )

        valid_labels = tuple(
            candidate.label
            for candidate in candidates
        )

        responses: dict[str, LLMResponse] = {}

        worker_count = min(
            self._max_workers,
            len(plan.seats),
        )

        with ThreadPoolExecutor(
            max_workers=worker_count
        ) as executor:
            futures: dict[
                Future[LLMResponse],
                CouncilSeat,
            ] = {
                executor.submit(
                    self._generate_ranking,
                    seat,
                    question,
                    candidate_block,
                    system_context,
                ): seat
                for seat in plan.seats
            }

            for future in as_completed(futures):
                seat = futures[future]

                try:
                    responses[seat.name] = future.result()

                except Exception as exc:
                    failures.append(
                        f"ranking:{seat.name}:"
                        f"{type(exc).__name__}: {exc}"
                    )

        rankings: list[CouncilRanking] = []

        for seat in plan.seats:
            response = responses.get(seat.name)

            if response is None:
                continue

            parsed = parse_final_ranking(
                response.text,
                valid_labels,
            )

            if not parsed:
                failures.append(
                    f"ranking:{seat.name}:"
                    "invalid-or-missing-final-ranking"
                )
                continue

            rankings.append(
                CouncilRanking(
                    reviewer_name=seat.name,
                    target=seat.target,
                    evaluation=response.text,
                    ranking=parsed,
                )
            )

        return tuple(rankings)

    def _generate_ranking(
        self,
        seat: CouncilSeat,
        question: str,
        candidate_block: str,
        system_context: str,
    ) -> LLMResponse:
        system_parts = [
            "[I.R.I.S. COUNCIL — PEER EVALUATION]",
            (
                "You are evaluating anonymous candidate answers "
                "to the user's question."
            ),
            (
                "Your review lens:\n"
                f"{seat.role}"
            ),
            (
                "Evaluate each response independently for "
                "correctness, relevance, reasoning quality, "
                "practicality, risk awareness, and usefulness."
            ),
            (
                "For each candidate, identify important strengths "
                "and weaknesses."
            ),
            (
                "Then rank all available candidates from strongest "
                "to weakest."
            ),
            (
                "Do not try to identify which model or Council seat "
                "produced a response."
            ),
            (
                "Your response MUST end with exactly this structure:\n\n"
                "FINAL RANKING:\n"
                "1. Response X\n"
                "2. Response Y\n"
                "...\n\n"
                "Use only the response labels actually provided."
            ),
            (
                "Do not provide hidden chain-of-thought. "
                "Give a concise evaluation suitable for synthesis."
            ),
        ]

        if system_context.strip():
            system_parts.extend(
                [
                    "Relevant I.R.I.S. context:",
                    system_context.strip(),
                ]
            )

        user_prompt = (
            f"Original question:\n{question}\n\n"
            "Anonymous candidate answers:\n\n"
            f"{candidate_block}"
        )

        return self._llm_registry.generate(
            target=seat.target,
            messages=[
                LLMMessage(
                    role=MessageRole.SYSTEM,
                    content="\n\n".join(system_parts),
                ),
                LLMMessage(
                    role=MessageRole.USER,
                    content=user_prompt,
                ),
            ],
            options=GenerationOptions(
                temperature=0.2,
                max_tokens=700,
            ),
        )

    def _run_chairman_stage(
        self,
        question: str,
        plan: CouncilPlan,
        candidates: tuple[CouncilCandidate, ...],
        rankings: tuple[CouncilRanking, ...],
        aggregate: tuple[AggregateRank, ...],
        system_context: str,
    ) -> LLMResponse:
        system_parts = [
            "[I.R.I.S. COUNCIL — CHAIRMAN]",
            (
                "You are the chairman of the I.R.I.S. "
                "LLM Council."
            ),
            (
                "Synthesize one final answer from the independent "
                "candidate responses and peer evaluations."
            ),
            (
                "Do not blindly majority-vote. Prefer correctness, "
                "evidence, reasoning quality, practical constraints, "
                "and the user's actual objective."
            ),
            (
                "The aggregate ranking is evidence about peer "
                "preference, not ground truth."
            ),
            (
                "Resolve disagreements where possible and clearly "
                "state meaningful uncertainty where they cannot "
                "be resolved."
            ),
            (
                "Return one coherent answer in I.R.I.S. voice."
            ),
            (
                "Do not expose candidate labels, reviewer identities, "
                "model names, or internal Council mechanics unless "
                "the user explicitly asks."
            ),
        ]

        if system_context.strip():
            system_parts.extend(
                [
                    "I.R.I.S. runtime identity and relevant context:",
                    system_context.strip(),
                ]
            )

        user_prompt = (
            f"Original question:\n{question}\n\n"
            "Anonymous candidate answers:\n\n"
            f"{self._candidate_block(candidates)}\n\n"
            "Anonymous peer evaluations:\n\n"
            f"{self._ranking_block(rankings)}\n\n"
            "Aggregate ranking:\n\n"
            f"{self._aggregate_block(aggregate)}"
        )

        try:
            return self._llm_registry.generate(
                target=plan.chairman,
                messages=[
                    LLMMessage(
                        role=MessageRole.SYSTEM,
                        content="\n\n".join(
                            system_parts
                        ),
                    ),
                    LLMMessage(
                        role=MessageRole.USER,
                        content=user_prompt,
                    ),
                ],
                options=GenerationOptions(
                    temperature=0.2,
                    max_tokens=1400,
                ),
            )

        except Exception as exc:
            raise CouncilExecutionError(
                "I.R.I.S. Council chairman failed: "
                f"{type(exc).__name__}: {exc}"
            ) from exc

    @staticmethod
    def _candidate_block(
        candidates: tuple[CouncilCandidate, ...],
    ) -> str:
        return "\n\n".join(
            f"Response {candidate.label}:\n"
            f"{candidate.text}"
            for candidate in candidates
        )

    @staticmethod
    def _ranking_block(
        rankings: tuple[CouncilRanking, ...],
    ) -> str:
        return "\n\n".join(
            (
                f"Review {index}:\n"
                f"{review.evaluation}"
            )
            for index, review in enumerate(
                rankings,
                start=1,
            )
        )

    @staticmethod
    def _aggregate_block(
        aggregate: tuple[AggregateRank, ...],
    ) -> str:
        if not aggregate:
            return "No aggregate ranking available."

        return "\n".join(
            (
                f"{index}. Response {item.label} "
                f"(average rank {item.average_rank:.3f}, "
                f"{item.rankings_count} review(s))"
            )
            for index, item in enumerate(
                aggregate,
                start=1,
            )
        )
