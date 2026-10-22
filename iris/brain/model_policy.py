from __future__ import annotations

from dataclasses import dataclass

from iris.brain.llm import ModelTarget
from iris.brain.router import ReasoningLevel


@dataclass(frozen=True)
class SingleModelPlan:
    """
    One provider/model target for FAST or DEEP reasoning.
    """

    target: ModelTarget


@dataclass(frozen=True)
class CouncilSeat:
    """
    One independent reasoning seat inside the I.R.I.S. LLM Council.

    `role` describes the perspective this seat should take.
    The Council engine will later turn that role into instructions.
    """

    name: str
    role: str
    target: ModelTarget

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Council seat name cannot be empty.")

        if not self.role.strip():
            raise ValueError("Council seat role cannot be empty.")


@dataclass(frozen=True)
class CouncilPlan:
    """
    Multi-model deliberation plan.

    Seats reason independently.
    The chairman later synthesizes the final I.R.I.S. answer.
    """

    seats: tuple[CouncilSeat, ...]
    chairman: ModelTarget

    def __post_init__(self) -> None:
        if len(self.seats) < 2:
            raise ValueError(
                "LLM Council requires at least two independent seats."
            )

        names = [seat.name.strip().lower() for seat in self.seats]

        if len(names) != len(set(names)):
            raise ValueError("Council seat names must be unique.")


ModelExecutionPlan = SingleModelPlan | CouncilPlan | None


@dataclass(frozen=True)
class ModelPolicy:
    """
    Maps I.R.I.S. reasoning depth to model execution.

    The brain asks for a reasoning level.
    This policy decides which model architecture fulfills it.

    No provider names are hardcoded into the router.
    """

    fast: ModelTarget
    deep: ModelTarget
    council: CouncilPlan

    def plan_for(
        self,
        reasoning: ReasoningLevel,
    ) -> ModelExecutionPlan:
        if reasoning == ReasoningLevel.DETERMINISTIC:
            return None

        if reasoning == ReasoningLevel.FAST:
            return SingleModelPlan(self.fast)

        if reasoning == ReasoningLevel.DEEP:
            return SingleModelPlan(self.deep)

        if reasoning == ReasoningLevel.COUNCIL:
            return self.council

        raise ValueError(
            f"Unsupported reasoning level: {reasoning}"
        )
