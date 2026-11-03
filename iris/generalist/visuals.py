"""Deterministic educational visual data; no executable presentation content."""
import math


def compound(principal=1000, rate=5, years=10, contribution=0):
    values = (principal, rate, years, contribution)
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in values):
        raise ValueError('Use finite numeric inputs.')
    if not (0 <= principal <= 10000000 and 0 <= rate <= 100 and
            type(years) is int and 1 <= years <= 50 and 0 <= contribution <= 100000):
        raise ValueError('Inputs exceed educational limits.')
    balance = principal
    points = [[0, principal, principal]]
    for month in range(1, years * 12 + 1):
        balance = balance * (1 + rate / 1200) + contribution
        if month % 12 == 0:
            points.append([month // 12, round(balance, 2), principal + month * contribution])
    return {'version': 1, 'kind': 'line', 'title': 'Compound growth: hypothetical constant rate',
            'labels': ['Balance', 'Principal plus contributions'], 'points': points,
            'summary': 'Monthly compounding; contributions at month end. No taxes, fees or return forecast.'}


def validate(spec):
    if type(spec) is not dict or set(spec) != {'version', 'kind', 'title', 'labels', 'points', 'summary'}:
        raise ValueError('Invalid visual fields.')
    if type(spec['version']) is not int or spec['version'] != 1 or spec['kind'] != 'line':
        raise ValueError('Unsupported visual version or kind.')
    if any(type(spec[k]) is not str or len(spec[k]) > 300 for k in ('title', 'summary')):
        raise ValueError('Invalid visual text.')
    labels, points = spec['labels'], spec['points']
    if type(labels) is not list or not 1 <= len(labels) <= 4 or any(type(x) is not str or len(x) > 80 for x in labels):
        raise ValueError('Invalid series labels.')
    if type(points) is not list or not 1 <= len(points) <= 100:
        raise ValueError('Invalid point count.')
    for point in points:
        if type(point) is not list or len(point) != len(labels) + 1 or any(type(x) not in (int, float) or not math.isfinite(x) or abs(x) > 1e30 for x in point):
            raise ValueError('Invalid point.')
    return spec
