# Restrained speech delivery

IRIS uses plain, calm spoken wording and avoids acted sighs, laughs, breaths,
throat-clearing and emotion tags. Warmth and understated humor remain in the words.

The speech adapter removes recognized short vocal/performance cues, including
`[sighing]`, `(clears throat)` and `*chuckles softly*`. This affects speech rendering
only; the displayed answer and source notes are unchanged. Ordinary explanations,
parenthetical information, link labels, numeric brackets and code remain information
to speak. Remaining square-bracket syntax is neutralized because Fish supports
free-form directions inside brackets. Cue-only answers produce no audio request.

Desktop, CLI and device-voice fallback use the same cleaned text. If the desktop
cannot obtain a cleaned voice ticket, it does not send the raw acted text to the
device fallback. The selected Fish voice ID and model are preserved.

Fish requests now explicitly use temperature `0.3`, top-p `0.7` and normalization.
The [Fish API reference](https://docs.fish.audio/api-reference/endpoint/openapi-v1/text-to-speech)
documents lower temperature as more consistent and higher temperature as more varied.
The [emotion guide](https://docs.fish.audio/developer-guide/core-features/emotions)
documents sighing and other vocal cues, including free-form bracket descriptions.

These changes suppress text-directed performance and reduce variation. They are
not a waveform breath-removal filter and cannot guarantee that a cloned voice
will never generate a spontaneous breath or sigh. Tests use synthetic text and
mocked audio; no paid synthesis was used to declare audible acceptance. If sounds
remain, assess a short real reply and then the reference voice's own delivery.
