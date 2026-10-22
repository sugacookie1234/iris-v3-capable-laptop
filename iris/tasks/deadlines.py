"""Conservative, clock-injectable deadline parsing using only the standard library."""
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
import os
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

WEEKDAYS = ('monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday')
DAY = r'(?:today|tomorrow|tmmr|(?:next\s+)?(?:' + '|'.join(WEEKDAYS) + r')|\d{4}-\d{2}-\d{2})'
CLOCK = r'\d{1,2}(?::\d{2}(?::\d{2}(?:\.\d+)?)?)?\s*(?:AM|PM)?(?:Z|[+-]\d{2}:\d{2})?'
PHRASE = re.compile(r'\b' + DAY + r'(?:(?:\s+at\s+|[Tt]|\s+)(?:' + CLOCK + r'))?(?!\w)', re.I)
UNCERTAIN = re.compile(r'\b(?:not|sometime|soon|later|tonight|morning|afternoon|evening|noon|midnight|next week|next month|maybe|around|before|after|or)\b|\b\d{1,2}/\d{1,2}(?:/\d{2,4})?\b', re.I)


def local_zone(name: str | None = None) -> ZoneInfo:
    name = name or os.environ.get('IRIS_TIMEZONE') or 'America/Toronto'
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError('IRIS_TIMEZONE must name an installed IANA timezone, such as America/Toronto.') from None


@dataclass(frozen=True)
class ParsedDeadline:
    title: str
    due_at: str | None
    explanation: str


def parse_deadline(text: str, *, zone: str | None = None, at: datetime | None = None) -> ParsedDeadline:
    tz = local_zone(zone)
    reference = at or datetime.now(timezone.utc)
    if reference.tzinfo is None:
        raise ValueError('Reference time must include a timezone.')
    local = reference.astimezone(tz)
    matches = list(PHRASE.finditer(text))
    def unresolved(reason):
        return ParsedDeadline(text.strip(), None, f'No deadline set: {reason}. Original title retained.')
    if not matches:
        return unresolved('date/time is ambiguous or unsupported') if UNCERTAIN.search(text) or re.search(r'\bat\s+\d', text, re.I) else ParsedDeadline(text.strip(), None, 'No deadline set: no supported date phrase supplied.')
    if len(matches) != 1 or UNCERTAIN.search(text):
        return unresolved('multiple dates or ambiguous wording')
    match = matches[0]
    # Do not accept a partial match of an invalid/unsupported time or timezone.
    tail = text[match.end():]
    if re.match(r"[:+\-\d]|[’']s\b|\s+\d|\s*(?:AM\b|PM\b|at\b|UTC\b|GMT\b|EST\b|EDT\b|PST\b|PDT\b)", tail, re.I):
        return unresolved('invalid or unsupported time')
    phrase = match.group().strip()
    day_match = re.match(DAY, phrase, re.I)
    day_text = day_match.group().lower()
    clock = phrase[day_match.end():].strip()
    clock = re.sub(r'^(?:at\s+|T)', '', clock, flags=re.I).strip()
    try:
        if day_text[0].isdigit():
            day = datetime.strptime(day_text, '%Y-%m-%d').date()
        elif day_text in ('today', 'tomorrow', 'tmmr'):
            day = local.date() + timedelta(days=day_text != 'today')
        else:
            weekday = WEEKDAYS.index(day_text.removeprefix('next '))
            if day_text.startswith('next '):
                # "next Monday" is Monday of the next calendar week.
                day = local.date() + timedelta(days=7 - local.weekday() + weekday)
            else:
                day = local.date() + timedelta(days=(weekday - local.weekday()) % 7)
        date_only = not clock
        if date_only:
            naive = datetime.combine(day, time(23, 59, 59))
        else:
            ampm = re.fullmatch(r'(\d{1,2})(?::(\d{2}))?\s*(AM|PM)', clock, re.I)
            if ampm:
                hour, minute, period = ampm.groups()
                if not 1 <= int(hour) <= 12:
                    raise ValueError
                parsed_time = time(int(hour) % 12 + (12 if period.lower() == 'pm' else 0), int(minute or 0))
            else:
                if not re.fullmatch(r'\d{1,2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:\d{2})?', clock, re.I):
                    return unresolved('time needs AM/PM or a 24-hour HH:MM value')
                parsed_time = time.fromisoformat(clock.upper())
            naive = datetime.combine(day, parsed_time)
        if naive.tzinfo is not None:
            utc = naive.astimezone(timezone.utc)
        else:
            candidates = {naive.replace(tzinfo=tz, fold=fold).astimezone(timezone.utc)
                          for fold in (0, 1)
                          if naive.replace(tzinfo=tz, fold=fold).astimezone(timezone.utc).astimezone(tz).replace(tzinfo=None) == naive}
            if len(candidates) != 1:
                return unresolved('local time is ambiguous or nonexistent during a daylight-saving transition')
            utc = candidates.pop()
    except ValueError:
        return unresolved('invalid calendar date or time')
    prefix = re.sub(r'\b(?:due|by|on)\s*$', '', text[:match.start()], flags=re.I)
    title = ' '.join((prefix + ' ' + tail).split()).strip(' ,.;')
    if not title:
        return unresolved('a task title is required')
    policy = ' Date-only policy: end of the local day (23:59:59).' if date_only else ''
    week = ' “Next” means the named day in the next Monday–Sunday calendar week.' if day_text.startswith('next ') else ''
    return ParsedDeadline(title, utc.isoformat(), f'Deadline: {utc.astimezone(tz).isoformat()} [{tz.key}].{policy}{week}')


def prepare_creation(arguments: dict, zone: str | None = None) -> tuple[dict, str]:
    args = dict(arguments)
    title = args['title']
    explicit = args.pop('due_at', None)
    # Parse explicit metadata with a placeholder title using exactly the same rules.
    parsed = parse_deadline(title, zone=zone)
    if explicit is not None:
        if PHRASE.search(title):
            parsed = ParsedDeadline(title, None, 'No deadline set: both title and due metadata contain dates. Original title retained.')
        else:
            result = parse_deadline('Task ' + explicit, zone=zone)
            parsed = ParsedDeadline(title, result.due_at if result.title == 'Task' else None,
                                    result.explanation if result.title == 'Task' else 'No deadline set: invalid or ambiguous due metadata.')
    args['title'] = parsed.title
    if parsed.due_at is not None:
        args['due_at'] = parsed.due_at
    return args, parsed.explanation
