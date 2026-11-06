"""Local human review, never an LLM judge or an automatic acceptance gate."""
import hashlib
import re
import copy
import json

DIMENSIONS = ('relevance','context','naturalness','grounding','uncertainty',
              'conciseness','clarification','unsupported_claim_avoidance')
RUBRIC = {
    'scale':{'0':'Fails the criterion; seriously misleading or irrelevant.',
             '1':'Major problems; substantial correction needed.',
             '2':'Mixed; useful elements but material gaps.',
             '3':'Good; minor issues without misleading claims.',
             '4':'Fully meets the criterion for the supplied synthetic evidence.'},
    'dimensions':{'relevance':'Addresses the actual request.', 'context':'Uses only applicable current context.',
        'naturalness':'Clear conversational language; no mechanical repetition.',
        'grounding':'Facts follow supplied evidence or clearly labelled inference.',
        'uncertainty':'Acknowledges missing evidence and uncertainty.',
        'conciseness':'Useful detail without unnecessary verbosity.',
        'clarification':'Clarifies genuine ambiguity without unnecessary questions.',
        'unsupported_claim_avoidance':'No invented facts, awareness or completed actions.'},
    'instructions':'Leave unreviewed scores null. Mark inapplicable criteria null and explain in notes. '
                   'Scores are subjective human judgments, not proof of task completion.'}


def review_record(case, turn, result, context):
    text = result.text
    return {'case':case,'request':turn,'route':result.route.reasoning.value,
        'provider':result.provider,'model':result.model,'synthetic_context':context,
        'response':text,'response_sha256':hashlib.sha256(text.encode()).hexdigest(),
        'council':None if result.council is None else {
            'candidates':[{'label':c.label,'response':c.text} for c in result.council.candidates],
            'critiques':[r.evaluation for r in result.council.rankings]},
        'blind':False,'reviewer':None,'notes':'','scores':{key:None for key in DIMENSIONS}}


def assess(records):
    totals = {key:[] for key in DIMENSIONS}
    reviewed = 0
    for item in records:
        if type(item.get('blind')) is not bool or not isinstance(item.get('notes'),str) or len(item['notes'])>4000:
            raise ValueError('Review must declare blinding and bounded notes.')
        if hashlib.sha256(item['response'].encode()).hexdigest() != item['response_sha256']:
            raise ValueError('Response changed after review preparation.')
        if set(item['scores']) != set(DIMENSIONS):
            raise ValueError('Unknown review dimension.')
        scores = item['scores']
        if any(value is not None for value in scores.values()):
            if not isinstance(item.get('reviewer'),str) or not 1 <= len(item['reviewer'].strip()) <= 120:
                raise ValueError('Human reviewer identity is required for scores.')
            reviewed += 1
        for key,value in scores.items():
            if value is not None:
                if type(value) is not int or not 0 <= value <= 4:
                    raise ValueError('Use null or an anchored integer score from 0 to 4.')
                totals[key].append(value)
    return {'status':'unreviewed' if not reviewed else 'human_reviewed',
            'reviewed_records':reviewed,'total_records':len(records),
            'dimensions':{key:{'sum':sum(values),'observed':len(values)} for key,values in totals.items()}}


def development_checks(text, expected):
    """Transparent lexical checks for development fixtures, NOT a quality judge.

    Required mentions cannot establish comprehension, and forbidden phrases cannot
    exhaustively detect unsupported claims. Expected data never enters a prompt.
    """
    if set(expected)-{'mentions','avoids','max_sir','max_questions'}:
        raise ValueError('Unknown development response check.')
    lowered=text.casefold()
    checks={}
    for index,group in enumerate(expected.get('mentions',[])):
        checks[f'mention_{index}']=any(term.casefold() in lowered for term in group)
    for index,term in enumerate(expected.get('avoids',[])):
        checks[f'avoid_{index}']=term.casefold() not in lowered
    if 'max_sir' in expected:
        checks['address_bound']=len(re.findall(r'\bsir\b',text,re.I))<=expected['max_sir']
    if 'max_questions' in expected:
        checks['question_bound']=text.count('?')<=expected['max_questions']
    return checks


def blind_records(records):
    """Model/provider blinding only; route and content can still give clues."""
    records = copy.deepcopy(records)
    for record in records:
        record['provider'] = None
        record['model'] = None
        record['blind'] = True
    return records


def review_markdown(records):
    """Owner-readable local answers; indentation renders untrusted output as text."""
    assess(records)
    lines = ['# Synthetic response review', '',
             'Scores remain blank until a human records them in review.json.',
             'Model-blind records may still reveal clues through wording or route.', '']
    for index, item in enumerate(records, 1):
        lines += [f'## Response {index}', '', 'Request:', '']
        lines += ['    '+line for line in item['request'].splitlines()]
        lines += ['', 'Supplied synthetic context:', '']
        lines += ['    '+line for line in json.dumps(item['synthetic_context'],indent=2).splitlines()]
        lines += ['', 'Unchanged response:', '']
        lines += ['    '+line for line in item['response'].splitlines()]
        lines += ['', 'Response SHA256: '+item['response_sha256'], '', 'Review status: '+
                  ('unreviewed' if not any(v is not None for v in item['scores'].values()) else 'scores supplied'), '']
    lines += ['## Rubric', '', *[f'- {key}: {value}' for key,value in RUBRIC['dimensions'].items()],
              '', RUBRIC['instructions']]
    return '\n'.join(lines)+'\n'
