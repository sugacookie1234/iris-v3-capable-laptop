"""Conservative speech formatting; never infer the meaning of arbitrary maths."""
import re

_SMALL = 'zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen'.split()
_TENS = 'zero ten twenty thirty forty fifty sixty seventy eighty ninety'.split()

def number(value):
    if value < 20:
        return _SMALL[value]
    return _TENS[value // 10] + ('-' + _SMALL[value % 10] if value % 10 else '')

def ordinal(day):
    special = {1:'first', 2:'second', 3:'third', 5:'fifth', 8:'eighth', 9:'ninth', 12:'twelfth', 20:'twentieth', 30:'thirtieth'}
    if day in special:
        return special[day]
    if day > 20:
        return number(day // 10 * 10) + '-' + ordinal(day % 10)
    return number(day) + 'th'

def spoken_date(value, include_year=True):
    year = value.year
    year_words = number(year // 100) + ' ' + (number(year % 100) if year % 100 >= 10 else 'oh ' + number(year % 100)) if 2010 <= year <= 2099 else str(year)
    return value.strftime('%A, %B ') + ordinal(value.day) + (', ' + year_words if include_year else '')

def spoken_clock(value, explicit_zone=False):
    hour, minute = value.hour, value.minute
    clock = ('midnight' if hour == 0 else 'noon') if minute == 0 and hour in (0, 12) else (
        number(hour % 12 or 12) + (' oh ' + number(minute) if 0 < minute < 10 else ' ' + number(minute) if minute else '') + (' AM' if hour < 12 else ' PM'))
    names = {'EST':'Eastern Standard Time', 'EDT':'Eastern Daylight Time', 'GMT':'Greenwich Mean Time', 'BST':'British Summer Time', 'JST':'Japan Standard Time', 'UTC':'Coordinated Universal Time'}
    zone = names.get(value.tzname(), 'local time')
    return "It's " + clock + ' on ' + spoken_date(value, False) + (', ' + zone if explicit_zone else '') + '.'

def spoken_text(text):
    text = re.sub(r'```[\s\S]*?```', 'The code is shown on screen.', text)
    text = re.sub(r'\\\[[\s\S]*?\\\]|\\\([\s\S]*?\\\)|\$\$[\s\S]*?\$\$',
                  'The mathematical expression is shown on screen.', text)
    text = re.sub(r'\$([^$\n]*[=^{}\\][^$\n]*)\$',
                  'The mathematical expression is shown on screen.', text)
    text = re.sub(r'\[([^\]\n]+)\]\(https?://[^\s)]+\)', r'\1', text)
    text = re.sub(r'(?m)^\s{0,3}(?:#{1,6}\s+|[-*+]\s+)', '', text)
    text = re.sub(r'\*\*([^*\n]+)\*\*|__([^_\n]+)__', lambda m:m[1] or m[2], text)
    text = re.sub(r'(\d(?:[\d,.]*\d)?)\s*%', r'\1 percent', text)
    return text.strip()
