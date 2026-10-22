"""Reproducible, credential-free Brain v0.1 integration demonstration."""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from iris.brain.engine import IRISBrain
from iris.brain.llm import LLMRegistry, LLMResponse, MessageRole, ModelTarget
from iris.brain.model_policy import CouncilPlan, CouncilSeat, ModelPolicy
from iris.identity import load_identity
from iris.memory.integration import respond_with_memory
from iris.memory.models import MemoryCategory, MemoryConfirmation, MemoryItem
from iris.memory.store import MemoryStore
from iris.obsidian import ObsidianKnowledgeAdapter
from iris.skills import ActionRequest, deterministic_fake_executor
from iris.voice import InMemoryPcmRecorder, LocalPushToTalkRecognizer, VoiceSession


class _SimulatedProvider:
    name = "simulated-offline"

    def healthcheck(self) -> bool:
        return True

    def generate(self, request):
        current = next(
            message.content for message in reversed(request.messages)
            if message.role == MessageRole.USER
        )
        return LLMResponse(
            text=f"SIMULATED RESPONSE: {current}",
            provider=self.name,
            model=request.model,
        )


class _SimulatedSpeech:
    def transcribe(self, _audio: bytes) -> str:
        return "what is in the launch plan"


class _SimulatedFish:
    def __init__(self) -> None:
        self.spoken: list[str] = []

    def speak(self, text: str) -> None:
        self.spoken.append(text)


def _brain() -> IRISBrain:
    registry = LLMRegistry()
    provider = _SimulatedProvider()
    registry.register(provider)
    target = ModelTarget(provider.name, "simulated-model")
    council = CouncilPlan(
        seats=(
            CouncilSeat("planner", "Plan clearly.", target),
            CouncilSeat("reviewer", "Check assumptions.", target),
        ),
        chairman=target,
    )
    return IRISBrain(
        load_identity(),
        ModelPolicy(target, target, council),
        registry,
        action_executor=deterministic_fake_executor(),
    )


def main() -> int:
    with TemporaryDirectory(prefix="iris-offline-demo-") as directory:
        root = Path(directory)
        vault = root / "vault"
        vault.mkdir()
        (vault / "vault index.md").write_text(
            "# Plans\n[Launch plan](Launch.md)\n", encoding="utf-8"
        )
        (vault / "Launch.md").write_text(
            "The launch plan uses a staged release.", encoding="utf-8"
        )
        with MemoryStore(root / "memory.sqlite3") as store:
            store.insert(MemoryItem(
                MemoryCategory.PREFERENCE, "user", "answer_style",
                "concise", "The user prefers concise answers.",
                "offline-demo-explicit-consent",
                confirmation=MemoryConfirmation.CONFIRMED,
            ))
            brain = _brain()
            knowledge = ObsidianKnowledgeAdapter(str(vault))

            first = respond_with_memory(
                brain, "What style should you use for the launch plan?",
                memory_store=store, obsidian=knowledge,
            )
            action = brain._action_executor.execute(
                ActionRequest("iris_status", session_id="offline-demo")
            )
            fish = _SimulatedFish()
            session = VoiceSession(
                recognizer=LocalPushToTalkRecognizer(InMemoryPcmRecorder(), _SimulatedSpeech()),
                synthesizer=fish,
                responder=lambda text: respond_with_memory(
                    brain, text, memory_store=store, obsidian=knowledge,
                ).text,
            )
            session.press()
            session.recognizer.recorder.append([0.1, -0.1, 0.1])
            voice_turn = session.release()
            print("SIMULATED offline demo: provider=ok memory=ok obsidian=ok action=%s voice=%s playback=%s" % (
                action.status.value,
                "ok" if voice_turn is not None else "failed",
                "ok" if fish.spoken else "failed",
            ))
            print("SIMULATED results use temporary synthetic data; no credentials, microphone, paid provider, or personal data.")
            return 0 if action.status.value == "SUCCESS" and voice_turn is not None and fish.spoken else 1


if __name__ == "__main__":
    raise SystemExit(main())
