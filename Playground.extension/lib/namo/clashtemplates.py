# -*- coding: utf-8 -*-
"""Clash Templates: clash test definitions saved by name and applied in other projects.

A template is a namo.templates entry of tool 'clash_tests' (team-shared when a shared
folder is set):

    {'version': 1, 'source': 'Hospital.nwf', 'units': 'Millimeters',
     'tests': [definition, ...]}          # namo.clashset_tests definitions

Selections are stored as set PATHS (with the set's search conditions when it is a
search set, so a missing search set can be recreated), whole models by file name, and
hand-picked items as model-relative entries (they resolve only in the same model).
Tolerances are metres.

Applying resolves every source against the open model first (plan_apply, pure over a
resolver callback): ready, recreate (a missing search set that can be rebuilt from its
stored conditions), missing (named), or exists (a test with that name is there). The
API half then recreates search sets and writes the tests in ONE undo step through
namo.clashset_tests.
"""

from namo import clashset_tests as defs

TOOL_ID = 'clash_tests'
VERSION = 1

STATUS_LABELS = {'ready': 'Ready', 'recreate': 'Ready (recreates sets)', 'missing': 'Missing items',
                 'exists': 'Exists', 'invalid': 'Cannot build'}


# ---- pure ---------------------------------------------------------------------------------


def template_config(definitions, source='', doc_units=''):
    """The stored config for a list of definitions."""
    return {'version': VERSION, 'source': str(source or ''), 'units': str(doc_units or ''),
            'tests': [defs.normalise_definition(d) for d in definitions]}


def definitions_of(config):
    """The normalised definitions in a stored config ([] for junk)."""
    if not isinstance(config, dict):
        return []
    return [defs.normalise_definition(d) for d in config.get('tests') or [] if isinstance(d, dict)]


def portability_notes(definitions):
    """Sentences about tests that will not travel to another model."""
    notes = []
    for d in definitions:
        for key in ('a', 'b'):
            if not defs.side_is_portable(d[key]):
                notes.append('%s: selection %s holds hand-picked items, which only apply in this model.'
                             % (d['name'], key.upper()))
    return notes


def describe(config):
    """'6 tests from Hospital.nwf'."""
    tests = definitions_of(config)
    text = '{:,} test{}'.format(len(tests), '' if len(tests) == 1 else 's')
    source = (config or {}).get('source') if isinstance(config, dict) else ''
    return '%s from %s' % (text, source) if source else text


def plan_apply(config, resolve_source, test_exists):
    """What applying a template would do, without touching the document.

    resolve_source(source) -> ('ok' | 'recreate' | 'missing', sentence or None);
    test_exists(name) -> bool. Returns rows [{'definition', 'status', 'problems',
    'recreate': [source], 'exists'}] in template order; status is 'invalid', 'missing',
    'exists' (buildable, but a test of that name is there), 'recreate' or 'ready'."""
    rows = []
    for definition in definitions_of(config):
        problems = list(defs.validate_definition(definition))
        recreate = []
        for key in ('a', 'b'):
            for source in definition[key]['sources']:
                state, sentence = resolve_source(source)
                if state == 'missing':
                    problems.append(sentence or 'Selection %s: %s is missing.'
                                    % (key.upper(), defs.describe_source(source)))
                elif state == 'recreate':
                    if source not in recreate:
                        recreate.append(source)
        exists = bool(definition['name']) and bool(test_exists(definition['name']))
        if definition['type'] not in defs.TYPE_KEYS:
            status = 'invalid'
        elif problems:
            status = 'missing'
        elif exists:
            status = 'exists'
        elif recreate:
            status = 'recreate'
        else:
            status = 'ready'
        rows.append({'definition': definition, 'status': status, 'problems': problems,
                     'recreate': recreate, 'exists': exists})
    return rows


def buildable(row):
    return row['status'] in ('ready', 'recreate', 'exists')


def plan_cells(row, doc_units):
    """Table cells for a plan row: Test, Type, Tolerance, A, B, Status."""
    d = row['definition']
    status = STATUS_LABELS.get(row['status'], row['status'])
    if row['problems']:
        status = '%s: %s' % (status, row['problems'][0])
    return [d['name'], defs.TYPE_LABELS.get(d['type'], 'Custom'),
            defs.tolerance_text(d['tolerance_m'], doc_units) if d['tolerance_m'] else '0',
            defs.describe_side(d['a']), defs.describe_side(d['b']), status]


def recreate_target(source):
    """(folder path or None, set name) where a missing search set is rebuilt."""
    names = defs.split_set_path(source.get('path'))
    if not names:
        return None, ''
    folder = defs.join_set_path(names[:-1]) or None
    return folder, names[-1]


def can_recreate(source):
    """True for a set source whose stored search can rebuild it (one condition group)."""
    query = source.get('search') if source.get('kind') == 'set' else None
    return (not source.get('folder') and defs.query_is_portable(query)
            and len(defs.query_groups(query)) == 1)


# ==== API half (Navisworks only; lazy imports) ============================================


def _doc(doc):
    if doc is not None:
        return doc
    from pynavis._api import Application
    return Application.ActiveDocument


def store():
    from namo import templates
    return templates.Templates(TOOL_ID)


def read_tests(tests, doc=None, with_failures=False):
    """Definitions of live tests, in the order given. with_failures=True returns
    (definitions, [names of tests whose settings could not be read]) instead of raising
    on the first test Navisworks will not describe."""
    document = _doc(doc)
    if not with_failures:
        return [defs.read_definition(test, document) for test in tests]
    definitions = []
    unread = []
    for test in tests:
        try:
            definitions.append(defs.read_definition(test, document))
        except Exception:
            try:
                unread.append(str(test.DisplayName))
            except Exception:
                unread.append('a test')
    return definitions, unread


def resolver(doc=None):
    """resolve_source(source) for plan_apply against the open model."""
    from namo import items as _items
    document = _doc(doc)
    cache = {}

    def resolve_source(source):
        kind = source.get('kind')
        key = (kind, source.get('path') or source.get('name') or '')
        if kind in ('set', 'model') and key in cache:
            return cache[key]
        if kind == 'set':
            if defs.find_set(source['path'], document) is not None:
                answer = ('ok', None)
            elif can_recreate(source):
                answer = ('recreate', None)
            else:
                answer = ('missing', 'Selection set "%s" is not in this model.' % source['path'])
        elif kind == 'model':
            answer = ('ok', None) if defs.find_model_roots(source['name'], document) else \
                ('missing', 'Model "%s" is not loaded.' % source['name'])
        elif kind == 'items':
            if source.get('entries'):
                _found, lost = _items.resolve(source['entries'], document)
                answer = ('ok', None) if not lost else \
                    ('missing', '{:,} picked items are not in this model.'.format(lost))
            else:
                answer = ('missing', 'Hand-picked items cannot be found in another model.')
        elif kind == 'search':
            answer = ('missing', 'A search that was never saved as a selection set cannot be applied.')
        else:
            answer = ('missing', 'An unknown selection.')
        cache[key] = answer
        return answer

    return resolve_source


def plan(config, doc=None):
    document = _doc(doc)
    return plan_apply(config, resolver(document),
                      lambda name: defs.find_test(name, document) is not None)


def _recreate(source, document):
    from pynavis import sets
    from namo import find_query
    folder, name = recreate_target(source)
    # Templates saved before clashset_tests cleaned them hold 'DisplayString:Ducts' values.
    return sets.create(name, find_query.stored_query(source['search']), folder=folder, doc=document)


def apply(rows, existing='skip', doc=None, progress=None):
    """Writes the chosen plan rows in ONE undo step: recreates missing search sets,
    then creates or updates each test. Returns ([{'name', 'outcome', 'detail', 'test'}],
    recreated set count). progress(fraction, label) only reports."""
    from pynavis.viewpoints import transaction
    document = _doc(doc)
    out = []
    total = len(rows) or 1
    recreated = {}
    with transaction('Apply clash template', document):
        for index, row in enumerate(rows):
            definition = row['definition']
            if progress is not None:
                progress(float(index) / total, 'Building %s' % definition['name'])
            result = {'name': definition['name'], 'outcome': 'failed', 'detail': '', 'test': None}
            out.append(result)
            try:
                for source in row.get('recreate') or []:
                    key = source.get('path')
                    if key not in recreated and defs.find_set(key, document) is None:
                        recreated[key] = _recreate(source, document)
                resolved_a = defs.resolve_side(definition['a'], document)
                resolved_b = defs.resolve_side(definition['b'], document)
                problems = resolved_a['missing'] + resolved_b['missing']
                if problems:
                    result['detail'] = problems[0]
                    continue
                outcome, live = defs.write_test(definition, resolved_a, resolved_b, existing, document)
                result['outcome'] = outcome
                result['test'] = live
                notes = resolved_a['notes'] + resolved_b['notes']
                if outcome == 'skipped':
                    result['detail'] = 'A test with this name already exists.'
                elif notes:
                    result['detail'] = notes[0]
            except Exception as error:
                result['detail'] = str(error)
    if progress is not None:
        progress(1.0, 'Done')
    return out, len(recreated)
