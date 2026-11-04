"""Authoritative local time answers; never infer time from conversation history."""
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

def response(command, zone, now=None):
    from iris.desktop.commands import normalize
    from iris.voice.presentation import spoken_clock, spoken_date
    command = normalize(command)
    command = re.sub(r"^(?:tell me |do you know )", "", command)
    if command in {"what time it is", "the time", "the current time", "the time right now", "what time is it right now", "what time is it now", "what is the time", "what\'s the time"}:
        command = "what time is it"
    time_queries = {'what time is it', "what's the time right now", 'what is the time right now', 'what time is it in montreal'}
    date_queries = {"what's today's date", "what is today's date", 'what day is it'}
    if command not in time_queries | date_queries:
        return None
    selected = 'America/Toronto' if command.endswith('in montreal') else zone
    try:
        tz = ZoneInfo(selected)
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        return {'reply': 'Your configured timezone is invalid. Please correct it in setup before relying on local time.'}
    instant = now if now is not None else datetime.now(timezone.utc)
    if instant.tzinfo is None:
        raise ValueError('Clock input must be timezone aware.')
    current = instant.astimezone(tz)
    display_date = current.strftime('%A, %B ') + str(current.day) + current.strftime(', %Y')
    display = (current.strftime('It is %H:%M on ') if command in time_queries else 'Today is ') + display_date + f' ({selected}).'
    speech = spoken_clock(current, command.endswith('in montreal')) if command in time_queries else 'Today is ' + spoken_date(current) + '.'
    return {'reply': display, 'spoken_reply': speech}


def answer(command, zone, now=None):
    result = response(command, zone, now)
    return result['reply'] if result else None
