"""Authoritative local time answers; never infer time from conversation history."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

def answer(command, zone, now=None):
    time_queries = {'what time is it', "what's the time right now", 'what is the time right now', 'what time is it in montreal'}
    date_queries = {"what's today's date", "what is today's date", 'what day is it'}
    if command not in time_queries | date_queries:
        return None
    selected = 'America/Toronto' if command.endswith('in montreal') else zone
    try:
        tz = ZoneInfo(selected)
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        return 'Your configured timezone is invalid. Please correct it in setup before relying on local time.'
    instant = now if now is not None else datetime.now(timezone.utc)
    if instant.tzinfo is None:
        raise ValueError('Clock input must be timezone aware.')
    current = instant.astimezone(tz)
    return (current.strftime('It is %H:%M on %A, %B %d, %Y') if command in time_queries
            else current.strftime('Today is %A, %B %d, %Y')) + f' ({selected}).'
