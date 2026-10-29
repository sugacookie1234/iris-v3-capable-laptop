"""Speech-only rendering: keep information, discard acted vocal directions."""
import re


# Match short directions, not ordinary sentences discussing these words.
_CUES = frozenset(('sigh sighs sighing laugh laughs laughing laughter chuckle chuckles chuckling '
    'giggle giggles giggling sob sobs sobbing cry cries crying groan groans groaning '
    'gasp gasps gasping pant pants panting yawn yawns yawning snore snores snoring '
    'breath breaths breathing inhale inhales inhaling exhale exhales exhaling '
    'cough coughs coughing whisper whispers whispering shout shouts shouting '
    'scream screams screaming hum hums humming throat clearing clears pause pauses '
    'break laughing audience background crowd happy sad angry excited calm nervous '
    'confident surprised scared worried frustrated empathetic relaxed sarcastic '
    'tired bored cheerful professional broadcast neutral tone voice delivery').split())
_MODIFIERS = frozenset(('a an the with in of and then gives lets out soft softly quiet quietly '
    'deep deeply long short audible audibly weary heavy heavily gentle gently slight '
    'slightly brief little dramatic dramatically slow slowly small very relief '
    'exasperation amused awkwardly warm warmly speaking measured restrained clear').split())
_DIRECTION = re.compile(r'\[([^\[\]\r\n]{1,120})\]|\(([^()\r\n]{1,120})\)|(?<!\*)\*([^*\r\n]{1,120})\*(?!\*)')
_CODE = re.compile(r'(```[\s\S]*?```|`[^`\n]*`)')


def _direction(match):
    body = next(value for value in match.groups() if value is not None)
    words = re.findall(r"[a-z]+", body.casefold())
    is_cue = words and bool(set(words) & _CUES) and set(words) <= (_CUES | _MODIFIERS)
    return ' ' if is_cue else match.group()


def clean_delivery_text(text):
    """No mutation of displayed/stored text; only return a speech rendering.

    Bracket syntax is neutralized because Fish S2 treats even free-form square
    brackets as instructions. Ordinary bracket contents remain spoken; numeric
    and inline-code brackets are named so indexing information is not discarded.
    """
    pieces = []
    for index, part in enumerate(_CODE.split(text)):
        if index % 2:  # Code examples are literal data, never acting directions.
            part = part.strip('`').replace('[', ' open bracket ').replace(']', ' close bracket ')
            part = part.replace('(', ' open parenthesis ').replace(')', ' close parenthesis ')
        else:
            # A Markdown link label is content, including a label such as "sigh".
            part = re.sub(r'\[([^\]\n]+)\]\([^\s)]+\)', r'\1', part)
            part = _DIRECTION.sub(_direction, part)
            part = re.sub(r'\[([0-9, .:+-]+)\]', r' open bracket \1 close bracket ', part)
            part = part.replace('[', ' ').replace(']', ' ')
        pieces.append(part)
    rendered = ''.join(pieces)
    rendered = re.sub(r'[ \t]+', ' ', rendered)
    rendered = re.sub(r' +([,.;:!?])', r'\1', rendered)
    return rendered.strip()
