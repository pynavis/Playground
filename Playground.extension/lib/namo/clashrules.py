# -*- coding: utf-8 -*-
"""Status Rules: ordered rules that set clash statuses (and assignees, and a note).

A rule is plain JSON, kept in rule sets (namo.templates tool 'clash_status_rules', so a
team shares them):

    {'name': 'Touching only', 'enabled': True, 'mode': 'all',      # or 'any'
     'conditions': ['depth < 3 mm', 'status is one of New, Active'],
     'status': 'Approved',          # '' leaves the status alone
     'assign': '',                  # '' leaves it; tokens allowed: {trade_a}, {model_b} ...
     'note': 'Approved by rule: under 3 mm.'}   # '' for none; added as a clash comment

Conditions are text, one per line, in namo.rules' cell syntax:

    depth < 3 mm                 the clash depth or gap, |distance| (lengths take units;
                                 a bare number is in the document units)
    distance between -5mm and 0  the signed distance (negative = penetration)
    age > 30                     days since the clash was found
    status is one of New, Active      test contains Ducts      name like *-L2-*
    grid, level, group, assigned, description, comments, priority
    model a, model b, trade a, trade b, item a, item b (element names)
    trade pair = Mechanical / Structure    model pair = A.nwc / B.nwc  (either order)
    same model = yes      same trade = no
    category a = Ducts    category b is one of Walls, Floors
    A: Element > System Type contains Supply      (a property of element A;
    B: ...   Either: ...   Both: ...               B, either or both)

The first enabled rule whose conditions hold decides a clash (first match wins).
Writing is one undo step for the whole Apply. A few changes are edited in place:
TestsEditResultStatus with the CURRENT USER as the acting assignee (the API names that
parameter current_user; it records who approved or resolved), then AssignedTo and the
comment. pynavis.clashtest.set_status passes the clash's own assignee there instead (a
recorded pyNavis bug), so it is NOT used; and every status edit is checked: an
AssignedTo that changed underneath is put back. Many changes (see apply) rebuild each
test once on a copy, the shipped Clash Grouper's route.

Pure: parsing, compiling, evaluation and planning (unit tested). API half after; the
editor window last.
"""

import re

from namo import naming, rules, units

TOOL_ID = 'clash_status_rules'
EXAMPLES_NAME = 'Examples'
STATUSES = ['New', 'Active', 'Reviewed', 'Approved', 'Resolved']
SIDES = {'a': 'a', 'b': 'b', 'either': 'either', 'both': 'both'}

FIELDS = {
    'depth': 'depth', 'overlap': 'depth', 'penetration': 'depth', 'gap': 'depth',
    'distance': 'distance', 'age': 'age', 'age days': 'age', 'days': 'age',
    'status': 'status', 'test': 'test', 'name': 'name', 'clash name': 'name',
    'description': 'description', 'grid': 'grid', 'level': 'level', 'group': 'group',
    'assigned': 'assigned', 'assigned to': 'assigned', 'assignee': 'assigned',
    'model a': 'model_a', 'model b': 'model_b', 'trade a': 'trade_a', 'trade b': 'trade_b',
    'item a': 'item_a', 'item b': 'item_b', 'element a': 'item_a', 'element b': 'item_b',
    'trade pair': 'trade_pair', 'trades': 'trade_pair', 'model pair': 'model_pair',
    'models': 'model_pair', 'same model': 'same_model', 'same trade': 'same_trade',
    'category a': 'category_a', 'category b': 'category_b', 'comments': 'comments',
    'priority': 'priority',
}
FIELD_NAMES = ['depth', 'distance', 'age', 'status', 'test', 'name', 'description', 'grid',
               'level', 'group', 'assigned', 'model a', 'model b', 'trade a', 'trade b',
               'item a', 'item b', 'trade pair', 'model pair', 'same model', 'same trade',
               'category a', 'category b', 'comments', 'priority']
LENGTH_FIELDS = ('depth', 'distance')
PAIR_FIELDS = ('trade_pair', 'model_pair')
LIVE_FIELDS = ('category_a', 'category_b')
_SIDE_LINE = re.compile(r'^\s*(a|b|either|both)\s*:\s*(.+)$', re.IGNORECASE)

EXAMPLE_RULES = [
    {'name': 'Touching only', 'enabled': True, 'mode': 'all',
     'conditions': ['depth < 3 mm', 'status is one of New, Active'],
     'status': 'Approved', 'assign': '', 'note': 'Approved by rule: overlap under 3 mm.'},
    {'name': 'Inside one model', 'enabled': True, 'mode': 'all',
     'conditions': ['same model = yes', 'status = New'],
     'status': 'Active', 'assign': '{trade_a}',
     'note': 'Clash inside {model_a}: its author resolves it.'},
    {'name': 'Stale reviews', 'enabled': True, 'mode': 'all',
     'conditions': ['status = Reviewed', 'age > 30'],
     'status': 'Active', 'assign': '', 'note': 'Reopened: reviewed more than 30 days ago.'},
]


# ---- pure: rules as data -------------------------------------------------------------------


def status_name(text):
    """The canonical status for text ('approved' -> 'Approved'), '' for blank, None
    when it is not a Clash Detective status."""
    value = str(text or '').strip()
    if not value:
        return ''
    for status in STATUSES:
        if status.lower() == value.lower():
            return status
    return None


def normalise_rule(rule):
    """A clean rule dict with every key (unknown keys dropped)."""
    rule = rule if isinstance(rule, dict) else {}
    conditions = rule.get('conditions') or []
    if isinstance(conditions, str):
        conditions = conditions.split('\n')
    mode = str(rule.get('mode') or 'all').lower()
    return {'name': str(rule.get('name') or '').strip() or 'Rule',
            'enabled': bool(rule.get('enabled', True)),
            'mode': mode if mode in ('all', 'any') else 'all',
            'conditions': [str(c).strip() for c in conditions if str(c).strip()],
            'status': status_name(rule.get('status')) or '',
            'assign': str(rule.get('assign') or '').strip(),
            'note': str(rule.get('note') or '').strip()}


def normalise_rules(values):
    return [normalise_rule(r) for r in (values or []) if isinstance(r, dict)]


def rule_set_config(rule_list):
    return {'version': 1, 'rules': normalise_rules(rule_list)}


def rules_of(config):
    if isinstance(config, dict):
        return normalise_rules(config.get('rules'))
    return []


def field_of(text):
    """The field key for a condition's left side ('Trade pair' -> 'trade_pair'), or None."""
    key = ' '.join(str(text or '').replace('_', ' ').lower().split())
    return FIELDS.get(key)


def _length_value(text, doc_units, signed):
    raw = str(text).strip()
    negative = signed and raw.startswith('-')
    if negative:
        raw = raw[1:].strip()
    value = units.parse_length(raw, doc_units)
    if value is None:
        raise ValueError('"%s" is not a length; write it like 3 mm or 1/8".' % text)
    metres = units.to_meters(value, doc_units)
    return -metres if negative else metres


def canonical_pair(text):
    """'mechanical|structure' for 'Structure / Mechanical' (either order), or ''."""
    parts = [p.strip().lower() for p in re.split(r'\s*/\s*|\s+vs\.?\s+|\s*&\s*|\s*\|\s*',
                                                str(text or '')) if p.strip()]
    if len(parts) == 1:
        parts = parts * 2
    if len(parts) != 2:
        return ''
    return '|'.join(sorted(parts))


def compile_condition(line, doc_units):
    """A condition line as a compiled dict ({'field' or 'side'/'category'/'property',
    'op', 'value', 'ignore_case', 'text'}). Raises ValueError with a sentence."""
    text = str(line or '').strip()
    if not text:
        raise ValueError('The condition is empty.')
    side_match = _SIDE_LINE.match(text)
    try:
        cond = rules.parse_cell(side_match.group(2) if side_match else text)
    except ValueError:
        raise ValueError('"%s" has no comparison; write it like depth < 3 mm, status = New or '
                         'A: Element > Category = Ducts.' % text)
    if side_match:
        problems = rules.validate(cond)
        if problems:
            raise ValueError('%s: %s' % (text, problems[0]))
        if not cond.get('category'):
            raise ValueError('"%s" needs a category, like A: Element > Category = Ducts.' % text)
        cond.update({'side': SIDES[side_match.group(1).lower()], 'field': None, 'text': text})
        return cond

    name = ' > '.join(p for p in (cond.get('category'), cond.get('property')) if p)
    field = field_of(name)
    if field is None:
        raise ValueError('"%s" is not a clash field; use %s, or A: Category > Property.'
                         % (name, ', '.join(FIELD_NAMES[:6]) + '...'))
    cond.update({'field': field, 'side': None, 'text': text})
    op = cond['op']
    value = cond.get('value')
    if field in LENGTH_FIELDS and rules.NEEDS_VALUE.get(op):
        signed = field == 'distance'
        if op == 'between':
            parts = value if isinstance(value, (list, tuple)) else [value]
            if len(parts) != 2:
                raise ValueError('"%s": write between like between 0 and 5 mm.' % text)
            suffix = re.search(r'[a-zA-Z"\']+\s*$', str(parts[1]))
            low = str(parts[0])
            if suffix and units.parse_number(low) is not None:
                low = low + suffix.group(0)
            cond['value'] = [_length_value(low, doc_units, signed),
                             _length_value(parts[1], doc_units, signed)]
        elif op == 'in_list':
            cond['value'] = [_length_value(v, doc_units, signed) for v in rules.as_list(value)]
        elif op in ('gt', 'ge', 'lt', 'le', 'equals', 'not_equals'):
            cond['value'] = _length_value(value, doc_units, signed)
    elif field == 'status' and op in ('equals', 'not_equals', 'in_list'):
        values = rules.as_list(value) if op == 'in_list' else [value]
        for v in values:
            if status_name(v) is None:
                raise ValueError('"%s" is not a status; use %s.' % (v, ', '.join(STATUSES)))
    elif field in PAIR_FIELDS and op in ('equals', 'not_equals', 'in_list'):
        values = rules.as_list(value) if op == 'in_list' else [value]
        pairs = [canonical_pair(v) for v in values]
        if not all(pairs):
            raise ValueError('"%s": write a pair like Mechanical / Structure.' % text)
        cond['value'] = pairs if op == 'in_list' else pairs[0]
    elif field in ('age', 'comments', 'priority') and op in ('gt', 'ge', 'lt', 'le') \
            and rules.to_number(value) is None:
        raise ValueError('"%s" needs a number.' % text)
    problems = rules.validate(cond)
    if problems:
        raise ValueError('%s: %s' % (text, problems[0]))
    return cond


def compile_rule(rule, doc_units):
    """(compiled rule, problems). A rule with problems never matches."""
    r = normalise_rule(rule)
    compiled = []
    problems = []
    for line in r['conditions']:
        try:
            compiled.append(compile_condition(line, doc_units))
        except ValueError as error:
            problems.append(str(error))
    if not r['conditions']:
        problems.append('%s has no conditions.' % r['name'])
    if not (r['status'] or r['assign'] or r['note']):
        problems.append('%s changes nothing: set a status, an assignee or a note.' % r['name'])
    out = dict(r)
    out['compiled'] = compiled
    out['problems'] = problems
    out['needs_live'] = any(c.get('side') or c.get('field') in LIVE_FIELDS for c in compiled)
    return out, problems


def describe_rule(rule):
    """('when' text, 'then' text) for the rules table."""
    r = normalise_rule(rule)
    joiner = ' and ' if r['mode'] == 'all' else ' or '
    when = joiner.join(r['conditions']) or '(no conditions)'
    then = []
    if r['status']:
        then.append('Status %s' % r['status'])
    if r['assign']:
        then.append('Assign %s' % r['assign'])
    if r['note']:
        then.append('Note')
    return when, ', '.join(then) or '(nothing)'


# ---- pure: evaluation -------------------------------------------------------------------------


def age_days(row, today):
    """Whole days from the clash's found date to today, or None."""
    from namo import dates
    created = dates.parse(row.get('created'))
    if created is None or today is None:
        return None
    return dates.days_between(created, today)


def _text(value):
    return '' if value is None else str(value)


def field_value(row, field, today=None):
    """(exists, value) of a clash field on a snapshot row (metres for lengths)."""
    if field == 'depth':
        d = row.get('distance_m')
        return (d is not None, abs(d) if d is not None else None)
    if field == 'distance':
        d = row.get('distance_m')
        return (d is not None, d)
    if field == 'age':
        days = age_days(row, today)
        return (days is not None, days)
    if field in ('item_a', 'item_b'):
        return (True, _text(row.get(field + '_name')))
    if field == 'trade_pair':
        return (True, '|'.join(sorted([_text(row.get('trade_a')).lower(), _text(row.get('trade_b')).lower()])))
    if field == 'model_pair':
        return (True, '|'.join(sorted([_text(row.get('model_a')).lower(), _text(row.get('model_b')).lower()])))
    if field == 'same_model':
        a, b = _text(row.get('model_a')).lower(), _text(row.get('model_b')).lower()
        return (True, bool(a) and a == b)
    if field == 'same_trade':
        a, b = _text(row.get('trade_a')).lower(), _text(row.get('trade_b')).lower()
        return (True, bool(a) and a == b)
    if field in ('comments', 'priority'):
        value = row.get(field)
        return (value is not None, value)
    value = row.get(field)
    return (True, _text(value))


def _pair_display(value):
    return ' / '.join(str(value or '').split('|'))


def condition_holds(cond, row, today=None, reader=None):
    """True when one compiled condition holds for a row. reader(row, side, category,
    property) -> (exists, value) reads element properties ('a' or 'b'); without one,
    live conditions are False."""
    side = cond.get('side')
    if side:
        if reader is None:
            return False
        sides = ['a', 'b'] if side in ('either', 'both') else [side]
        hits = []
        for s in sides:
            try:
                exists, value = reader(row, s, cond['category'], cond['property'])
            except Exception:
                exists, value = False, None
            hits.append(rules.evaluate(cond, exists, value))
        return all(hits) if side == 'both' else any(hits)
    field = cond['field']
    if field in LIVE_FIELDS:
        if reader is None:
            return False
        try:
            exists, value = reader(row, field[-1], '', 'category')
        except Exception:
            exists, value = False, None
        return rules.evaluate(cond, exists, value)
    exists, value = field_value(row, field, today)
    if field in PAIR_FIELDS and cond['op'] not in ('equals', 'not_equals', 'in_list'):
        value = _pair_display(value)
    return rules.evaluate(cond, exists, value)


def rule_matches(compiled_rule, row, today=None, reader=None):
    if compiled_rule['problems'] or not compiled_rule['enabled']:
        return False
    conds = compiled_rule['compiled']
    if not conds:
        return False
    results = (condition_holds(c, row, today, reader) for c in conds)
    if compiled_rule['mode'] == 'any':
        return any(results)
    return all(results)


def first_match(compiled_rules, row, today=None, reader=None):
    """The index of the first enabled rule that matches, or None."""
    for index, rule in enumerate(compiled_rules):
        if rule_matches(rule, row, today, reader):
            return index
    return None


def render_text(template, row, doc_units):
    """An assign or note template rendered over the clash's tokens."""
    if not template:
        return ''
    from namo import clashname
    text, _missing = naming.render(template, clashname.clash_values(row, doc_units))
    return naming.sanitize(text)


def plan(rows_by_test, compiled_rules, doc_units, today=None, reader_for=None):
    """What the rules would do: {'changes': {test: [change]}, 'counts': [{'matched',
    'changed'}] per rule, 'total', 'matched', 'changed'}. A change is {'id', 'rule',
    'status' (new or None), 'assign' (new or None), 'note' (text or '')}; a matched
    clash already in the rule's state (and with no note) is not a change.
    reader_for(test) -> reader for that test's rows (or None)."""
    counts = [{'matched': 0, 'changed': 0} for _r in compiled_rules]
    changes = {}
    total = matched = changed = 0
    for test in sorted(rows_by_test, key=naming.natural_key):
        reader = reader_for(test) if reader_for is not None else None
        out = []
        for row in rows_by_test[test]:
            total += 1
            index = first_match(compiled_rules, row, today, reader)
            if index is None:
                continue
            matched += 1
            counts[index]['matched'] += 1
            rule = compiled_rules[index]
            status = rule['status'] if rule['status'] and rule['status'] != row.get('status') else None
            assign = None
            if rule['assign']:
                name = render_text(rule['assign'], row, doc_units)
                if name and name != (row.get('assigned') or ''):
                    assign = name
            note = render_text(rule['note'], row, doc_units) if rule['note'] else ''
            if status is None and assign is None and not note:
                continue
            counts[index]['changed'] += 1
            changed += 1
            out.append({'id': row['id'], 'rule': index, 'status': status, 'assign': assign,
                        'note': note})
        changes[test] = out
    return {'changes': changes, 'counts': counts, 'total': total, 'matched': matched,
            'changed': changed}


def summary_text(planned):
    """'512 of 1,240 clashes match a rule; 380 will change.'"""
    return '{:,} of {:,} clash{} match a rule; {:,} will change.'.format(
        planned['matched'], planned['total'], '' if planned['total'] == 1 else 'es',
        planned['changed'])


# ==== API half (Navisworks only; lazy imports) ===============================================


def _doc(doc):
    if doc is not None:
        return doc
    from pynavis._api import Application
    return Application.ActiveDocument


def store():
    from namo import templates
    return templates.Templates(TOOL_ID)


def ensure_examples(rule_store=None):
    """Seeds the 'Examples' rule set when there are no rule sets yet. Returns names."""
    rule_store = rule_store or store()
    names = rule_store.names()
    if not names:
        try:
            rule_store.save(EXAMPLES_NAME, rule_set_config(EXAMPLE_RULES))
        except Exception:
            return []
        names = rule_store.names()
    return names


def element_reader(leaves):
    """reader(row, side, category, property) over live results (leaves[row id]), reading
    element properties by display name (namo.items.prop), memoised per element.
    property 'category' with category '' reads namo.items.category."""
    from namo import items as _items
    memo = {}

    def element(result, side):
        composite = result.CompositeItem1 if side == 'a' else result.CompositeItem2
        if composite is not None:
            return composite
        item = result.Item1 if side == 'a' else result.Item2
        return _items.object_of(item) if item is not None else None

    def reader(row, side, category, prop):
        key = (row.get('item_' + side) or '%s:%s' % (side, row['id']), category, prop)
        if key not in memo:
            item = element(leaves[row['id']], side)
            if item is None:
                memo[key] = (False, None)
            elif not category and prop == 'category':
                memo[key] = (True, _items.category(item))
            else:
                value = _items.prop(item, category, prop)
                memo[key] = (value is not None, value)
        return memo[key]

    return reader


def _current_user():
    try:
        from namo import config
        return config.user_name()
    except Exception:
        import os
        return os.environ.get('USERNAME', '')


def count_edits(planned):
    """How many document edits writing the plan one by one would take (a status, an
    assignee and a comment are one edit each). Pure."""
    total = 0
    for name in planned['changes']:
        for change in planned['changes'][name]:
            total += (1 if change['status'] else 0) + (1 if change['assign'] else 0) +                 (1 if change['note'] else 0)
    return total


def apply(entries, planned, doc=None, progress=None, limit=None):
    """Writes the planned changes in ONE undo step (one user action). entries: {test
    name: namo.clashname.read_test entry ('leaves', 'test', 'nodes')}. Returns {'status',
    'assign', 'notes', 'tests', 'restored', 'mode'}. progress(fraction, label) only
    reports.

    Up to `limit` document edits (namo.clashset_edit.EDIT_LIMIT) each clash is edited in
    place (TestsEditResultStatus / AssignedTo / Comments). Above it each test is rebuilt
    once on a detached copy and swapped in, the shipped Clash Grouper's route: per-clash
    edits cost a fixed amount each that grows with the model, and a rule can match tens
    of thousands of clashes."""
    from pynavis._api import Api
    from namo import clashset_edit
    from namo import clashset_tests as defs
    document = _doc(doc)
    ClashApi = defs.clash_api()
    data = defs._clash().get_clash(document).TestsData
    user = _current_user()
    actor = Api.Assignee(user) if user else Api.Assignee()
    mode = clashset_edit.mode_for(count_edits(planned),
                                  clashset_edit.EDIT_LIMIT if limit is None else limit)
    totals = {'status': 0, 'assign': 0, 'notes': 0, 'tests': 0, 'restored': 0, 'mode': mode}
    names = [n for n in sorted(planned['changes'], key=naming.natural_key) if planned['changes'][n]]

    def edit_in_place(result, change):
        if change['status']:
            before = _assignee_name(result.AssignedTo)
            data.TestsEditResultStatus(result, getattr(ClashApi.ClashResultStatus,
                                                       change['status']), actor)
            totals['status'] += 1
            if not change['assign'] and _assignee_name(result.AssignedTo) != before:
                data.TestsEditResultAssignedTo(result, _assignee(Api, before))
                totals['restored'] += 1
        if change['assign']:
            data.TestsEditResultAssignedTo(result, _assignee(Api, change['assign']))
            totals['assign'] += 1
        if change['note']:
            comments = Api.CommentCollection(result.Comments)
            comments.Add(_comment(Api, change['note'], user))
            data.TestsEditResultComments(result, comments)
            totals['notes'] += 1

    def copy_edit(change):
        def edit(copy):
            if change['status']:
                clashset_edit.transition(copy, change['status'],
                                         getattr(ClashApi.ClashResultStatus, change['status']),
                                         actor, keep_assignee=not change['assign'])
                totals['status'] += 1
            if change['assign']:
                copy.AssignedTo = _assignee(Api, change['assign'])
                totals['assign'] += 1
            if change['note']:
                copy.Comments.Add(_comment(Api, change['note'], user))
                totals['notes'] += 1
        return edit

    with clashset_edit.one_step('Status rules', document, mode, len(names)):
        for position, name in enumerate(names):
            if progress is not None:
                progress(float(position) / (len(names) or 1), 'Updating %s' % name)
            entry = entries[name]
            changes = planned['changes'][name]
            if mode == 'edit':
                leaves = entry['leaves']
                for change in changes:
                    edit_in_place(leaves[change['id']], change)
            else:
                new_test = clashset_edit.rebuild(
                    entry, dict((change['id'], copy_edit(change)) for change in changes), {})
                clashset_edit.commit(data, entry['test'], new_test)
            totals['tests'] += 1
    if progress is not None:
        progress(1.0, 'Done')
    return totals


def _assignee_name(assignee):
    from namo import clashset_edit
    return clashset_edit.assignee_name(assignee)


def _assignee(Api, name):
    from namo import clashset_edit
    return clashset_edit.assignee(Api, name)


def _comment(Api, text, author):
    from namo import clashset_edit
    return clashset_edit.comment(Api, text, author)


# ---- the rules editor window ------------------------------------------------------------------


def rule_form_fields(rule):
    """namo.ui.form fields for editing one rule."""
    r = normalise_rule(rule)
    return [
        {'kind': 'text', 'key': 'name', 'label': 'Rule name', 'default': r['name'], 'required': True},
        {'kind': 'textarea', 'key': 'conditions', 'label': 'When (one condition per line)',
         'default': '\n'.join(r['conditions']), 'rows': 5,
         'hint': 'Like: depth < 3 mm, status is one of New, Active, trade pair = Mechanical / '
                 'Structure, age > 30, A: Element > Category = Ducts'},
        {'kind': 'radio', 'key': 'mode', 'label': 'Match', 'inline': True, 'default': r['mode'], 'fallback': None,
         'options': [('Every condition', 'all'), ('Any condition', 'any')]},
        {'kind': 'choice', 'key': 'status', 'label': 'Set the status to', 'default': r['status'], 'fallback': None,
         'options': [('Leave it', '')] + [(s, s) for s in STATUSES]},
        {'kind': 'text', 'key': 'assign', 'label': 'Assign to', 'default': r['assign'],
         'hint': 'Leave blank to keep the assignee. Tokens like {trade_a} work.'},
        {'kind': 'text', 'key': 'note', 'label': 'Add a comment', 'default': r['note'],
         'hint': 'Leave blank for none. Tokens like {distance} work.'},
        {'kind': 'check', 'key': 'enabled', 'label': 'Rule is on', 'default': r['enabled']},
    ]


def validate_form(values, doc_units):
    """{key: sentence} for a rule form (namo.ui.form validate callback)."""
    rule = normalise_rule(values)
    _compiled, problems = compile_rule(rule, doc_units)
    errors = {}
    for problem in problems:
        if 'changes nothing' in problem:
            errors.setdefault('status', problem)
        else:
            errors.setdefault('conditions', problem)
    return errors


class RulesState(object):
    """window.Tag of the rules editor: the rule list, the set name, dirty flag, and
    after Apply `result` = {'set', 'rules'} with `accepted` True."""

    def __init__(self, window, set_name, rule_list, preview, doc_units):
        self.window = window
        self.set_name = set_name
        self.rules = normalise_rules(rule_list)
        self.preview = preview
        self.doc_units = doc_units
        self.dirty = False
        self.result = None
        self.accepted = False
        self.saved = False
        self.table = None
        self.status = None
        self.apply_button = None
        self.title_block = None
        self.counts = None

    def rows(self):
        out = []
        for index, rule in enumerate(self.rules):
            when, then = describe_rule(rule)
            counts = self.counts[index] if self.counts and index < len(self.counts) else None
            _c, problems = compile_rule(rule, self.doc_units)
            matched = '' if counts is None else counts['matched']
            out.append({'value': index, 'cells': [index + 1, 'On' if rule['enabled'] else 'Off',
                                                  rule['name'], when, then,
                                                  'Problem' if problems else matched]})
        return out

    def refresh(self, select=None):
        planned = self.preview(self.rules)
        self.counts = planned['counts'] if planned else None
        self.table.update(self.rows())
        if select is not None:
            self.table.select_values([select])
        if self.title_block is not None:
            self.title_block.Text = 'Rule set: %s%s' % (self.set_name, ' (changed)' if self.dirty else '')
        if planned is None:
            self.status.Text = 'Add a rule to see what it would change.'
            self.apply_button.IsEnabled = False
        else:
            self.status.Text = summary_text(planned)
            self.apply_button.IsEnabled = planned['changed'] > 0
        return planned

    def selected_index(self):
        values = self.table.selected_values()
        return values[0] if values else None

    def replace(self, rules_list, select=None):
        self.rules = normalise_rules(rules_list)
        self.dirty = True
        self.refresh(select)

    def move(self, step):
        index = self.selected_index()
        if index is None:
            return
        target = index + step
        if target < 0 or target >= len(self.rules):
            return
        new = list(self.rules)
        new[index], new[target] = new[target], new[index]
        self.replace(new, target)

    def delete(self):
        index = self.selected_index()
        if index is None:
            return
        new = list(self.rules)
        del new[index]
        self.replace(new, min(index, len(new) - 1) if new else None)

    def toggle(self):
        index = self.selected_index()
        if index is None:
            return
        new = [dict(r) for r in self.rules]
        new[index]['enabled'] = not new[index]['enabled']
        self.replace(new, index)

    def put(self, index, rule):
        """Replaces rule index (None appends)."""
        new = list(self.rules)
        if index is None:
            new.append(normalise_rule(rule))
            index = len(new) - 1
        else:
            new[index] = normalise_rule(rule)
        self.replace(new, index)

    def accept(self):
        self.result = {'set': self.set_name, 'rules': normalise_rules(self.rules)}
        self.accepted = True
        from namo.clashset_common import close_window
        close_window(self.window, True)
        return True


def build_window(set_name, rule_list, preview, doc_units, edit_rule=None, on_save=None,
                 on_switch=None, title='Status Rules'):
    """The unshown rules editor. preview(rules) -> plan() dict or None. edit_rule(rule)
    -> edited rule or None (a modal form); on_save(state) saves the set; on_switch(state)
    lets the user pick or create another set (it calls state.load(name, rules))."""
    from namo import ui
    from namo.clashset_common import close_window, thickness, wpf
    wpf()
    from System.Windows.Controls import Dock, DockPanel, Orientation, StackPanel
    logger = ui.pinned_logger()
    win = ui.window(title, width=1000, height=620, resizable=True, min_width=720, min_height=420)
    state = RulesState(win, set_name, rule_list, preview, doc_units)
    win.Tag = state

    def load(name, new_rules):
        state.set_name = name
        state.rules = normalise_rules(new_rules)
        state.dirty = False
        state.refresh(0 if state.rules else None)
    state.load = load

    top = DockPanel()
    top.Margin = thickness(16, 16, 16, 8)
    state.title_block = ui.text('Rule set: %s' % set_name, 15, bold=True)
    switch = ui.button('Rule sets...', lambda: on_switch(state) if on_switch else None, 'quiet', logger)
    DockPanel.SetDock(switch, Dock.Right)
    top.Children.Add(switch)
    top.Children.Add(state.title_block)

    # Extended selection on purpose: ui.Table.select_values() clears SelectedItems, which
    # WPF refuses in single-select mode (request in dev/notes). The first selected rule acts.
    state.table = ui.Table(['#', 'On', 'Rule', 'When', 'Then', 'Matches'], [], multiselect=True,
                           on_open=lambda value: edit(value), logger=logger)

    def edit(index):
        if edit_rule is None:
            return
        rule = state.rules[index] if index is not None and 0 <= index < len(state.rules) else None
        edited = edit_rule(rule)
        if edited is not None:
            state.put(index if rule is not None else None, edited)

    tools = StackPanel()
    tools.Orientation = Orientation.Horizontal
    tools.Margin = thickness(16, 0, 16, 8)
    for label, action in (('Add rule', lambda: edit(None)),
                          ('Edit', lambda: edit(state.selected_index())),
                          ('Turn on or off', state.toggle),
                          ('Move up', lambda: state.move(-1)),
                          ('Move down', lambda: state.move(1)),
                          ('Delete', state.delete)):
        control = ui.button(label, action, 'quiet', logger)
        control.Margin = thickness(0, 0, 8, 0)
        tools.Children.Add(control)

    hint = ui.hint('The first rule that matches a clash decides it. Double-click a rule to edit it.')
    hint.Margin = thickness(16, 0, 16, 8)

    state.status = ui.hint('')
    state.apply_button = ui.button('Apply', lambda: state.accept(), 'primary', logger)
    save = ui.button('Save rules', lambda: on_save(state) if on_save else None, 'secondary', logger)
    cancel = ui.button('Close', lambda: close_window(win, False), 'secondary', logger)
    cancel.IsCancel = True
    bar = ui.footer([state.apply_button, save, cancel], left=state.status, padding=16)

    table_host = state.table.element
    table_host.Margin = thickness(16, 0, 16, 12)
    layout = DockPanel()
    DockPanel.SetDock(bar, Dock.Bottom)
    layout.Children.Add(bar)
    for element in (top, tools, hint):
        DockPanel.SetDock(element, Dock.Top)
        layout.Children.Add(element)
    layout.Children.Add(table_host)
    win.Content = layout
    win.ContentRendered += ui.safe(lambda s, e: state.table.focus_first(), 'rules focus', logger)
    state.refresh(0 if state.rules else None)
    return win
