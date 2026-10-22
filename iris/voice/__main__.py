"""One-shot local voice command mode."""
from __future__ import annotations

import argparse
import sys

from iris.voice.adapters import VoiceBackendError, VoskSpeechRecognizer, PiperSpeechSynthesizer
from iris.voice.session import VoiceSession, VoiceState


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run one explicit local IRIS voice turn.")
    parser.add_argument("--text", help="Use text fallback instead of audio (headless-safe).")
    parser.add_argument("--speak", action="store_true", help="Use optional local speech output.")
    args = parser.parse_args(argv)
    try:
        session = VoiceSession(
            recognizer=None if args.text is not None else VoskSpeechRecognizer(),
            synthesizer=PiperSpeechSynthesizer() if args.speak else None,
            responder=lambda text: text,
        )
        if args.text is not None:
            turn = session.submit_text(args.text)
        else:
            session.press()
            if session.state == VoiceState.ERROR:
                print(f"Voice unavailable: {session.last_error_message or session.last_error}", file=sys.stderr)
                return 2
            turn = session.release()
            if turn is None:
                print(f"Voice error: {session.last_error or 'recognition failed'}", file=sys.stderr)
                return 1
        print(turn.response)
        return 0
    except (VoiceBackendError, RuntimeError, ValueError) as exc:
        print(f"Voice unavailable: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
