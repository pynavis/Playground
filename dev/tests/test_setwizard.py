# -*- coding: utf-8 -*-
"""namo.setwizard: the wizard model, validation, compiling to search-set queries, names,
the property Sample."""
import _compat

from namo import setwizard as sw


def model_with(groups, scope='model', models=None, name=''):
    m = sw.new_model()
    m['groups'] = groups
    m['scope'] = scope
    m['models'] = models or []
    m['name'] = name
    return m


def cond(category='Element', prop='Category', op='equals', value='Ducts', ignore_case=True):
    return sw.new_condition(category, prop, op, value, ignore_case)


def test_normalise_cleans_remembered_models():
    m = sw.normalise({'scope': 'nonsense', 'groups': [[], [{'category': 'A', 'property': 'B',
                                                             'op': 'bogus', 'value': 3}]],
                      'folder': None, 'select_now': 0})
    assert m['scope'] == 'model' and m['folder'] == sw.DEFAULT_FOLDER and m['select_now'] is False
    assert m['groups'] == [[sw.new_condition('A', 'B', 'equals', '3')]]
    assert sw.normalise(None)['groups'] == [[sw.new_condition()]]


def test_condition_problems():
    assert sw.condition_problem(cond(category='')) == 'Choose a category.'
    assert sw.condition_problem(cond(prop='')) == 'Choose a property.'
    assert sw.condition_problem(cond(op='nope')) == 'Choose an operator.'
    assert sw.condition_problem(cond(value='  ')) == 'Type a value.'
    assert sw.condition_problem(cond(op='gt', value='big')) == 'Greater than needs a number.'
    assert sw.condition_problem(cond(op='has_property', value='')) is None
    assert sw.condition_problem(cond(value='abc'), kind='int') == 'Type a number.'
    assert sw.condition_problem(cond(value='12'), kind='int') is None
    assert sw.condition_problem(cond(value='maybe'), kind='bool') == 'Type Yes or No.'


def test_problems_and_queries():
    m = model_with([[cond(), cond(category='', prop='', value='')], [cond(category='', prop='', value='')]])
    assert sw.problems(m) == []                         # blank rows and sets are ignored
    partial = model_with([[cond(), cond(prop='', value='')]])
    assert sw.problems(partial) == [(0, 1, 'Choose a property.')]
    queries = sw.queries(m)
    assert len(queries) == 1
    assert queries[0]['or'][0]['and'] == [{'category': 'Element', 'prop': 'Category', 'op': 'equals',
                                            'value': 'Ducts', 'ignore_case': True}]
    empty = model_with([[sw.new_condition()]])
    assert sw.problems(empty) == [(0, None, 'Add at least one condition.')]
    _compat.raises(ValueError, sw.queries, empty)
    bad = model_with([[cond(), cond(op='lt', value='x')]], scope='models')
    found = sw.problems(bad)
    assert (0, 1, 'Less than needs a number.') in found
    assert (None, None, 'Choose the models to search in.') in found


def test_or_sets_become_separate_queries_with_kinds():
    kinds = {('Element', 'Level'): 'text', ('Element ID', 'Value'): 'int', ('Element', 'Width'): 'float'}
    m = model_with([[cond(), cond('Element', 'Level', 'equals', 'Level 3', False)],
                    [cond('Element ID', 'Value', 'equals', '312045')],
                    [cond('Element', 'Width', 'equals', '0.2'), cond('Element', 'Mark', 'has_property', '')]])
    queries = sw.queries(m, kinds)
    assert len(queries) == 3
    second = queries[0]['or'][0]['and'][1]
    assert second['value'] == 'Level 3' and 'ignore_case' not in second
    assert queries[1]['or'][0]['and'][0]['value'] == 312045
    third = queries[2]['or'][0]['and']
    assert [c['op'] for c in third] == ['ge', 'le', 'has_property']


def test_queries_are_valid_pynavis_queries():
    try:
        from pynavis import _query
    except ImportError:
        raise _compat.SkipTest('pynavis not importable')
    m = model_with([[cond(), cond('Element', 'Width', 'ge', '1,200'), cond('Element', 'Mark', 'not_has_property', '')]])
    for q in sw.queries(m):
        assert _query.validate(_query.Query.from_dict(q)) == []


def test_set_names_and_default_name():
    assert sw.set_names('Ducts', 1) == ['Ducts']
    assert sw.set_names('  ', 1) == ['Search set']
    assert sw.set_names('Ducts', 2) == ['Ducts (set 1)', 'Ducts (set 2)']
    m = model_with([[cond(), cond('Element', 'Level', 'equals', 'Level 3')]])
    assert sw.default_name(m) == 'Ducts on Level 3'
    assert sw.default_name(model_with([[cond(op='contains')]])) == 'Search set'


def test_count_text_and_describe():
    assert sw.count_text([412], 412, 1.25) == '412 items match (1.2 s)' or \
        sw.count_text([412], 412, 1.25) == '412 items match (1.3 s)'
    assert sw.count_text([1], 1, 0.0) == '1 item matches (0.0 s)'
    assert sw.count_text([12, 400], 410, 2.0) == 'Set 1: 12; set 2: 400; 410 in all (2.0 s)'
    assert sw.describe_group([cond(), cond('Element', 'Mark', 'has_property', '')]) == \
        'Element > Category = Ducts and Element > Mark exists'


def test_query_key_tracks_scope():
    m = model_with([[cond()]])
    q = sw.queries(m)
    a = sw.query_key(q, m)
    m['scope'] = 'selection'
    assert sw.query_key(q, m) != a


def test_sample():
    sample = sw.Sample([
        [('Element', 'Category', 'Ducts'), ('Element', 'Level', 'Level 2'), ('Element', 'Width', 0.4)],
        [('Element', 'Category', 'Ducts'), ('Element', 'Level', 'Level 10'), ('Element', 'Width', 1)],
        [('Element', 'Category', 'Pipes'), ('Item', 'Name', 'P1'), ('Element', 'Category', 'Pipes')],
    ], total=3)
    assert sample.categories() == ['Element', 'Item']
    assert sample.properties('Element') == ['Category', 'Level', 'Width']
    assert sample.observed('Element', 'Category') == [('Ducts', 2), ('Pipes', 2)]
    assert sample.carriers[('Element', 'Category')] == 3
    assert sample.observed('Element', 'Level') == [('Level 2', 1), ('Level 10', 1)]
    assert sample.kind('Element', 'Width') == 'float'
    assert sample.kinds()[('Item', 'Name')] == 'text'
    assert sample.observed('Nope', 'Nothing') == []
