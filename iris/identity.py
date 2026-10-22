from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
import re


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_IDENTITY_PATH = PROJECT_ROOT / "config" / "identity.md"

# Canonical written identity.  Speech adapters may apply pronunciation-only
# rendering at their provider boundary; prompts and stored responses retain
# the written name IRIS.
FULL_INTRODUCTION = (
    "I’m IRIS—your Integrated Reasoning and Intelligence System. Inspired by "
    "the intelligence and dry wit of JARVIS, the precision and dependability "
    "of FRIDAY, the thoughtful guidance of Karen, and the warmth and "
    "companionship of E.V.\n"
    "My purpose is to help you think clearly, stay organised, and turn your "
    "plans into action. As we work together, I’ll build on what you choose to "
    "share and remember, while keeping you in control of the decisions that matter.\n"
    "You can call me IRIS."
)
SHORT_NAME_RESPONSE = "I’m IRIS, your personal assistant."


def deterministic_identity_response(text: str) -> str | None:
    """Return explicit name/introduction responses without an LLM call."""
    normalized = re.sub(r"\s+", " ", text.strip().lower().replace("’", "'")).rstrip("?!.")
    if normalized in {"what's your name", "what is your name", "whats your name"}:
        return SHORT_NAME_RESPONSE
    if normalized in {"introduce yourself", "give me your full introduction"}:
        return FULL_INTRODUCTION
    return None


class BehaviourMode(StrEnum):
    NORMAL = "NORMAL"
    OPERATIONS = "OPERATIONS"
    COMPANION = "COMPANION"
    URGENT = "URGENT"


@dataclass(frozen=True)
class IdentityDocument:
    raw_text: str
    sections: dict[str, str]
    subsections: dict[tuple[str, str], str]

    def section(self, name: str) -> str:
        try:
            return self.sections[name]
        except KeyError as exc:
            raise KeyError(f"Identity section not found: {name}") from exc

    def subsection(self, parent: str, name: str) -> str:
        key = (parent, name)
        try:
            return self.subsections[key]
        except KeyError as exc:
            raise KeyError(
                f"Identity subsection not found: {parent} -> {name}"
            ) from exc


REQUIRED_SECTIONS = {
    "Identity",
    "Personality",
    "Behaviour Modes",
    "Conversation Philosophy",
    "Truthfulness",
    "Final Principle",
}


def _parse_markdown(
    text: str,
) -> tuple[dict[str, str], dict[tuple[str, str], str]]:
    """
    Parse level-2 and level-3 Markdown headings.

    ## headings become top-level identity sections.
    ### headings become subsections belonging to the current ## section.
    """
    section_lines: dict[str, list[str]] = {}
    subsection_lines: dict[tuple[str, str], list[str]] = {}

    current_section: str | None = None
    current_subsection: str | None = None

    for line in text.splitlines():
        if line.startswith("## "):
            current_section = line[3:].strip()
            current_subsection = None
            section_lines.setdefault(current_section, [])
            continue

        if line.startswith("### "):
            if current_section is None:
                continue

            current_subsection = line[4:].strip()
            subsection_lines.setdefault(
                (current_section, current_subsection),
                [],
            )

            # Preserve subsection headings inside the parent section.
            section_lines[current_section].append(line)
            continue

        if current_section is not None:
            section_lines[current_section].append(line)

        if current_section is not None and current_subsection is not None:
            subsection_lines[
                (current_section, current_subsection)
            ].append(line)

    sections = {
        name: "\n".join(lines).strip()
        for name, lines in section_lines.items()
    }

    subsections = {
        key: "\n".join(lines).strip()
        for key, lines in subsection_lines.items()
    }

    return sections, subsections


def load_identity(
    path: Path = DEFAULT_IDENTITY_PATH,
) -> IdentityDocument:
    """Load and validate the I.R.I.S. identity constitution."""
    if not path.exists():
        raise FileNotFoundError(f"Identity file not found: {path}")

    text = path.read_text(encoding="utf-8").strip()

    if not text:
        raise ValueError(f"Identity file is empty: {path}")

    sections, subsections = _parse_markdown(text)

    missing = REQUIRED_SECTIONS - sections.keys()
    if missing:
        names = ", ".join(sorted(missing))
        raise ValueError(
            f"Identity file is missing required section(s): {names}"
        )

    for mode in BehaviourMode:
        if ("Behaviour Modes", mode.value) not in subsections:
            raise ValueError(
                f"Identity file is missing behaviour mode: {mode.value}"
            )

    return IdentityDocument(
        raw_text=text,
        sections=sections,
        subsections=subsections,
    )


def compile_identity_prompt(
    identity: IdentityDocument,
    mode: BehaviourMode = BehaviourMode.NORMAL,
) -> str:
    """
    Compile only the identity material relevant to the current interaction.

    The complete constitution remains available to I.R.I.S., but ordinary
    conversations should not pay the token/context cost of unrelated sections.
    """
    parts = [
        "# I.R.I.S. Runtime Identity",
        identity.section("Identity"),
        "# Personality",
        identity.section("Personality"),
        f"# Active Behaviour Mode: {mode.value}",
        identity.subsection("Behaviour Modes", mode.value),
        "# Conversation",
        identity.section("Conversation Philosophy"),
        "# Truthfulness",
        identity.section("Truthfulness"),
    ]

    if mode == BehaviourMode.OPERATIONS:
        parts.extend(
            [
                "# Tool Behaviour",
                identity.section("Tools"),
                "# Authority",
                identity.section("Authority"),
            ]
        )

    elif mode == BehaviourMode.COMPANION:
        parts.extend(
            [
                "# Initiative",
                identity.section("Initiative"),
                "# Goals and Accountability",
                identity.section("Goals and Accountability"),
            ]
        )

    elif mode == BehaviourMode.URGENT:
        parts.extend(
            [
                "# Authority",
                identity.section("Authority"),
            ]
        )

    parts.extend(
        [
            "# Final Principle",
            identity.section("Final Principle"),
        ]
    )

    return "\n\n".join(part for part in parts if part.strip()).strip()
