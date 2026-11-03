"""Bounded local feasibility analysis. No network, orders or inferred market facts."""
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_HALF_UP
import hashlib
import json
import re
from uuid import uuid4

from iris.memory.store import MemoryStore
from iris.memory.redaction import reject_secrets

COSTS = ('unit_cost', 'inbound_shipping', 'packaging', 'fulfilment', 'outbound_shipping',
         'transaction_fixed', 'advertising', 'returns_allowance', 'duties')
NUMBERS = (*COSTS, 'price', 'transaction_percent', 'fixed_costs')
DESCRIPTIONS = ('customer', 'problem', 'competitors', 'differentiation', 'supplier', 'fulfilment_plan', 'risks')


def text(value, limit=1000):
    if type(value) is not str or len(value) > limit:
        raise ValueError('Text is missing or too long.')
    reject_secrets(value)
    return value.strip()


def money(value):
    if type(value) not in (str, int) or not re.fullmatch(r'\d{1,9}(?:\.\d{1,4})?', str(value)):
        raise ValueError('Enter a nonnegative decimal amount with up to four decimal places.')
    try:
        return Decimal(value)
    except InvalidOperation:
        raise ValueError('Invalid amount.') from None


def amount(value):
    return str(value.quantize(Decimal('.01'), rounding=ROUND_HALF_UP))


def validate(project):
    if type(project) is not dict or set(project) - {'name', 'currency', 'budget', 'context', 'products', 'goals', 'status'}:
        raise ValueError('Unknown business project fields.')
    if len(json.dumps(project, ensure_ascii=True)) > 60000:
        raise ValueError('Project exceeds the 60000-character workspace limit.')
    name = text(project.get('name'), 120)
    currency = project.get('currency', 'CAD')
    if not name or type(currency) is not str or not re.fullmatch('[A-Z]{3}', currency):
        raise ValueError('Provide a project name and three-letter currency code.')
    products = project.get('products')
    if type(products) is not list or not 1 <= len(products) <= 10:
        raise ValueError('Compare between one and ten products.')
    result = {'name': name, 'currency': currency, 'budget': str(money(project.get('budget'))),
              'context': text(project.get('context', ''), 3000), 'goals': text(project.get('goals', ''), 2000),
              'status': project.get('status', 'research'), 'products': []}
    if result['status'] not in ('research', 'paused', 'archived'):
        raise ValueError('Unknown project status.')
    names = set()
    for raw in products:
        if type(raw) is not dict or set(raw) - {'name', 'quantity', 'evidence', 'tax_status', *NUMBERS, *DESCRIPTIONS}:
            raise ValueError('Unknown product fields or action request.')
        title = text(raw.get('name'), 120)
        if not title or title.casefold() in names:
            raise ValueError('Product names must be nonempty and unique.')
        names.add(title.casefold())
        quantity = raw.get('quantity')
        if type(quantity) is not int or not 1 <= quantity <= 100000:
            raise ValueError('Quantity must be an integer from 1 to 100000.')
        item = {'name': title, 'quantity': quantity, 'tax_status': raw.get('tax_status', 'unresolved')}
        if item['tax_status'] not in ('unresolved', 'excluded_from_scenario'):
            raise ValueError('Taxes must be explicitly unresolved or excluded from this scenario.')
        for key in NUMBERS:
            value = raw.get(key)
            item[key] = None if value is None or value == '' else str(money(value))
        if item['transaction_percent'] is not None and Decimal(item['transaction_percent']) > 100:
            raise ValueError('Transaction percentage cannot exceed 100.')
        item.update({key: text(raw.get(key, ''), 1500) for key in DESCRIPTIONS})
        evidence = raw.get('evidence', [])
        if type(evidence) is not list or len(evidence) > 20:
            raise ValueError('At most twenty evidence entries per product.')
        item['evidence'] = []
        for entry in evidence:
            if type(entry) is not dict or set(entry) != {'claim', 'source', 'status'}:
                raise ValueError('Evidence needs claim, source and status.')
            if entry['status'] not in ('supplied', 'assumption', 'contradicted'):
                raise ValueError('Unknown evidence status.')
            claim, source = text(entry['claim'], 1500), text(entry['source'], 500)
            if not claim or not source:
                raise ValueError('Evidence needs a nonempty claim and provenance.')
            item['evidence'].append({'claim': claim, 'source': source, 'status': entry['status']})
        result['products'].append(item)
    return result


def economics(product, budget):
    missing = [key for key in NUMBERS if product[key] is None]
    if missing:
        return {'status': 'incomplete', 'missing': missing}
    values = {key: Decimal(product[key]) for key in NUMBERS}
    q = Decimal(product['quantity'])
    price = values['price']
    landed = sum(values[key] for key in ('unit_cost', 'inbound_shipping', 'packaging', 'duties'))
    variable = sum(values[key] for key in COSTS) + price * values['transaction_percent'] / 100
    contribution = price - variable
    fixed = values['fixed_costs']
    cash = q * variable + fixed
    return {'status': 'scenario_only', 'revenue': amount(q * price),
        'gross_profit': amount(q * (price - landed)), 'variable_cost_per_unit': amount(variable),
        'contribution_per_unit': amount(contribution), 'contribution_total': amount(q * contribution),
        'contribution_margin_percent': amount(contribution / price * 100) if price else None,
        'operating_profit_before_tax': amount(q * contribution - fixed), 'net_profit': None,
        'break_even_units': int((fixed / contribution).to_integral_value(rounding=ROUND_CEILING)) if contribution > 0 else None,
        'conservative_cash_required': amount(cash), 'budget_gap': amount(max(Decimal(0), cash - budget)),
        'within_budget': cash <= budget, 'positive_contribution': contribution > 0,
        'sensitivity': {'price_minus_10_percent_contribution': amount(contribution - price * Decimal('.1') * (1-values['transaction_percent']/100)),
                        'shipping_plus_25_percent_contribution': amount(contribution - (values['inbound_shipping'] + values['outbound_shipping']) * Decimal('.25'))}}


def evaluate_project(project):
    project = validate(project)
    evaluations = []
    for product in project['products']:
        costs = economics(product, Decimal(project['budget']))
        missing = [key for key in DESCRIPTIONS if not product[key]]
        contradictory = any(entry['status'] == 'contradicted' for entry in product['evidence'])
        if costs['status'] == 'incomplete':
            recommendation = 'Gather missing cost inputs before assessing feasibility.'
        elif not costs['positive_contribution']:
            recommendation = 'Rework this scenario: each sale has zero or negative contribution.'
        elif not costs['within_budget']:
            recommendation = 'Rework quantity or costs: conservative cash needs exceed the budget.'
        else:
            recommendation = 'Candidate for further research only; validate demand and binding supplier/fulfilment terms.'
        if contradictory:
            recommendation += ' Resolve contradictory evidence before relying on these assumptions.'
        evaluations.append({'name': product['name'], 'economics': costs, 'recommendation': recommendation,
            'confidence': 'unverified assumptions', 'missing_research': missing,
            'contradictory_evidence': contradictory, 'supplied_evidence_count': len(product['evidence']),
            'evidence_independently_verified': False, 'tax_status': product['tax_status']})
    return {'version': 1, 'currency': project['currency'], 'evaluations': evaluations,
        'stages': ['define', 'organize_supplied_evidence', 'validate_inputs', 'calculate', 'identify_gaps', 'compare'],
        'limitations': ['No demand forecast: quantity is a scenario, not expected sales.',
            'Amounts share one currency; no exchange-rate conversion.',
            'Net profit is unknown: taxes and unmodelled overhead/regulatory obligations are unresolved.',
            'Cash estimate conservatively prepays all modelled variable costs; supplier payment timing is unknown.',
            'Evidence and cost inputs are user-supplied assumptions, not independently checked quotes.',
            'No external connector, message, purchase, payment or storefront action.'], 'model_calls': 0}


class BusinessWorkspace:
    """Additive tables in the existing local memory DB; never retrieved as facts."""
    def __init__(self, path):
        self.path = path

    @contextmanager
    def database(self):
        with MemoryStore(self.path) as memory:
            db = memory._connection
            db.execute('BEGIN IMMEDIATE')
            try:
                row = db.execute("SELECT value FROM schema_meta WHERE key='business_version'").fetchone()
                if row and row['value'] != '1':
                    raise ValueError('Unsupported business workspace version.')
                db.execute('CREATE TABLE IF NOT EXISTS business_projects (id TEXT PRIMARY KEY, revision INTEGER NOT NULL, payload TEXT NOT NULL, report TEXT NOT NULL)')
                db.execute('CREATE TABLE IF NOT EXISTS business_requests (request_id TEXT PRIMARY KEY, digest TEXT NOT NULL, project_id TEXT NOT NULL, revision INTEGER NOT NULL)')
                db.execute("INSERT OR IGNORE INTO schema_meta VALUES ('business_version','1')")
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise

    @staticmethod
    def public(row):
        return {'id': row['id'], 'revision': row['revision'], 'project': json.loads(row['payload']), 'report': json.loads(row['report'])}

    def list(self):
        with self.database() as db:
            return [self.public(row) for row in db.execute('SELECT * FROM business_projects ORDER BY rowid DESC')]

    def save(self, project, request_id, identifier=None, revision=None):
        project = validate(project)
        if type(request_id) is not str or not re.fullmatch('[a-zA-Z0-9_-]{8,80}', request_id):
            raise ValueError('A unique request identifier is required.')
        if identifier is not None and (type(identifier) is not str or not re.fullmatch('[a-f0-9]{32}', identifier)
                or type(revision) is not int or revision < 1):
            raise ValueError('Invalid project revision.')
        payload = json.dumps(project, sort_keys=True)
        digest = hashlib.sha256(json.dumps([identifier, revision, project], sort_keys=True).encode()).hexdigest()
        report = json.dumps(evaluate_project(project), sort_keys=True)
        with self.database() as db:
            previous = db.execute('SELECT * FROM business_requests WHERE request_id=?', (request_id,)).fetchone()
            if previous:
                if previous['digest'] != digest:
                    raise ValueError('Request identifier was already used for different inputs.')
                row = db.execute('SELECT * FROM business_projects WHERE id=?', (previous['project_id'],)).fetchone()
                if not row or row['revision'] != previous['revision']:
                    raise ValueError('That saved project has changed; reload before editing.')
                return self.public(row)
            if db.execute('SELECT COUNT(*) FROM business_requests').fetchone()[0] >= 10000:
                raise ValueError('Business request retention limit reached; export and review maintenance before further saves.')
            if identifier is None:
                if db.execute('SELECT COUNT(*) FROM business_projects').fetchone()[0] >= 100:
                    raise ValueError('Business workspace limit reached (100 projects).')
                identifier, next_revision = uuid4().hex, 1
                db.execute('INSERT INTO business_projects VALUES (?,?,?,?)', (identifier, 1, payload, report))
            else:
                row = db.execute('SELECT revision FROM business_projects WHERE id=?', (identifier,)).fetchone()
                if not row or row['revision'] != revision:
                    raise ValueError('Project changed; reload before editing.')
                next_revision = revision + 1
                db.execute('UPDATE business_projects SET revision=?,payload=?,report=? WHERE id=?', (next_revision, payload, report, identifier))
            db.execute('INSERT INTO business_requests VALUES (?,?,?,?)', (request_id, digest, identifier, next_revision))
            return self.public(db.execute('SELECT * FROM business_projects WHERE id=?', (identifier,)).fetchone())
