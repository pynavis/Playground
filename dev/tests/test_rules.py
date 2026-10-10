# -*- coding: utf-8 -*-
"""namo.rules: the condition engine, text rules, descriptions and the native plan."""
import os
import sys

import _compat
from _compat import raises

from namo import rules

# pynavis (stdlib-only modules such as sets/_query) for native_query under CPython.
_PYNAVISLIB = _compat.PYNAVISLIB
if not _compat.IRONPYTHON and os.path.isdir(_PYNAVISLIB) and _PYNAVISLIB not in sys.path:
    sys.path.append(_PYNAVISLIB)


def cond(op, value=None, ignore_case=True, category='Element', prop='Category'):
    return {'category': category, 'property': prop, 'op': op, 'value': value,
            'ignore_case': ignore_case}


def test_ops_table_is_ordered_and_complete():
    names = [op for op, _label, _needs in rules.OPS]
    assert names == ['equals', 'not_equals', 'contains', 'not_contains', 'starts_with',
                     'ends_with', 'wildcard', 'regex', 'gt', 'ge', 'lt', 'le', 'between',
                     'in_list', 'exists', 'missing', 'empty', 'not_empty']
    needs = dict((op, n) for op, _l, n in rules.OPS)
    assert not needs['exists'] and not needs['missing'] and not needs['empty'] and not needs['not_empty']
    assert needs['between'] and needs['in_list'] and needs['regex']
    for op, label, _needs in rules.OPS:
        assert label and label[0].islower() or label[0].isupper()
        assert rules.op_of(label) == op
        assert rules.op_of(op) == op
        assert op in rules.SYMBOLS


def test_to_number():
    assert rules.to_number('12.5') == 12.5
    assert rules.to_number('1,234') == 1234.0
    assert rules.to_number('12.5 m') == 12.5
    assert rules.to_number('3.2 ft') == 3.2
    assert rules.to_number('-4') == -4.0
    assert rules.to_number(7) == 7.0
    assert rules.to_number(2.5) == 2.5
    assert rules.to_number(True) is None
    assert rules.to_number(None) is None
    assert rules.to_number('abc') is None
    assert rules.to_number('') is None


def test_text_equality_ignores_case_and_trims():
    c = cond('equals', 'Ducts')
    assert rules.evaluate(c, True, 'ducts')
    assert rules.evaluate(c, True, '  Ducts ')
    assert not rules.evaluate(c, True, 'Duct')
    assert not rules.evaluate(cond('equals', 'Ducts', ignore_case=False), True, 'ducts')
    assert rules.evaluate(cond('not_equals', 'Ducts'), True, 'Pipes')
    assert not rules.evaluate(cond('not_equals', 'Ducts'), True, 'DUCTS')


def test_numeric_equality_when_both_sides_are_numbers():
    assert rules.evaluate(cond('equals', '3'), True, 3.0)
    assert rules.evaluate(cond('equals', '3'), True, '3.000')
    assert rules.evaluate(cond('equals', 3), True, '3')
    assert not rules.evaluate(cond('equals', '3'), True, '3 m')     # text then: '3 m' != '3'
    assert rules.evaluate(cond('equals', '1,234'), True, 1234)


def test_booleans_read_as_yes_no():
    assert rules.evaluate(cond('equals', 'Yes'), True, True)
    assert rules.evaluate(cond('equals', 'true'), True, True)
    assert rules.evaluate(cond('equals', 'No'), True, False)
    assert not rules.evaluate(cond('equals', 'yes'), True, False)
    assert rules.text_of(True) == 'Yes'
    assert rules.text_of(3.0) == '3'
    assert rules.text_of(2.5) == '2.5'
    assert rules.text_of(None) == ''


def test_text_operators():
    assert rules.evaluate(cond('contains', 'pipe'), True, 'Steel PIPE 50')
    assert not rules.evaluate(cond('contains', 'pipe', ignore_case=False), True, 'Steel PIPE')
    assert rules.evaluate(cond('not_contains', 'duct'), True, 'Pipe')
    assert rules.evaluate(cond('starts_with', 'ste'), True, 'Steel')
    assert rules.evaluate(cond('ends_with', 'EEL'), True, 'Steel')
    assert rules.evaluate(cond('wildcard', 'P-*'), True, 'p-101')
    assert rules.evaluate(cond('wildcard', 'P-??1'), True, 'P-101')
    assert not rules.evaluate(cond('wildcard', 'P-?1'), True, 'P-101')
    assert rules.evaluate(cond('wildcard', 'a.b*'), True, 'A.Bc')
    assert not rules.evaluate(cond('wildcard', 'a.b'), True, 'axb')         # '.' is literal
    assert rules.evaluate(cond('regex', r'^P-\d+$'), True, 'p-12')
    assert not rules.evaluate(cond('regex', r'^P-\d+$', ignore_case=False), True, 'p-12')
    assert not rules.evaluate(cond('regex', '('), True, 'anything')         # bad pattern: False


def test_numeric_comparisons():
    assert rules.evaluate(cond('gt', '3'), True, 3.5)
    assert not rules.evaluate(cond('gt', '3'), True, 3)
    assert rules.evaluate(cond('ge', '3'), True, '3 m')
    assert rules.evaluate(cond('lt', 10), True, '9.99')
    assert rules.evaluate(cond('le', '1,000'), True, 1000)
    assert not rules.evaluate(cond('gt', '3'), True, 'abc')
    assert not rules.evaluate(cond('gt', 'abc'), True, 5)
    assert rules.evaluate(cond('between', [1, 3]), True, 2)
    assert rules.evaluate(cond('between', [3, 1]), True, 3)                # bounds sorted
    assert rules.evaluate(cond('between', '1 and 3'), True, '1')
    assert not rules.evaluate(cond('between', [1, 3]), True, 3.01)
    assert not rules.evaluate(cond('between', 'nonsense'), True, 2)


def test_in_list():
    assert rules.evaluate(cond('in_list', ['Ducts', 'Pipes']), True, 'pipes')
    assert rules.evaluate(cond('in_list', 'Ducts, Pipes'), True, 'Ducts')
    assert rules.evaluate(cond('in_list', 'A, B; C'), True, 'A, B')       # ';' wins as separator
    assert rules.evaluate(cond('in_list', ['1', '2']), True, 2.0)
    assert not rules.evaluate(cond('in_list', []), True, '')
    assert rules.as_list(' a ,b,, ') == ['a', 'b']


def test_presence_operators():
    assert rules.evaluate(cond('exists'), True, '')
    assert not rules.evaluate(cond('exists'), False, None)
    assert rules.evaluate(cond('missing'), False, None)
    assert rules.evaluate(cond('empty'), False, None)
    assert rules.evaluate(cond('empty'), True, '   ')
    assert not rules.evaluate(cond('empty'), True, 'x')
    assert rules.evaluate(cond('not_empty'), True, 0)
    assert not rules.evaluate(cond('not_empty'), False, None)


def test_value_operators_are_false_on_missing_properties():
    for op in ('equals', 'not_equals', 'contains', 'not_contains', 'gt', 'in_list', 'regex'):
        assert not rules.evaluate(cond(op, 'x'), False, None), op


def test_evaluate_accepts_operator_spellings():
    assert rules.evaluate({'property': 'Level', 'op': '>=', 'value': 3}, True, 4)
    assert rules.evaluate({'property': 'Name', 'op': 'Contains', 'value': 'a'}, True, 'ab')


def test_matches_all_any_and_getter_caching():
    calls = []

    def getter(category, prop):
        calls.append((category, prop))
        data = {('Element', 'Category'): (True, 'Ducts'), ('Element', 'Level'): (True, 'L2')}
        if (category, prop) == ('Boom', 'X'):
            raise RuntimeError('broken item')
        return data.get((category, prop), (False, None))

    conds = [cond('equals', 'Ducts'), cond('contains', 'duct'), cond('equals', 'L2', prop='Level')]
    assert rules.matches(conds, getter)
    assert calls.count(('Element', 'Category')) == 1
    assert not rules.matches(conds + [cond('exists', prop='Mark')], getter)
    assert rules.matches([cond('equals', 'X'), cond('equals', 'L2', prop='Level')], getter, mode='any')
    assert not rules.matches([cond('equals', 'X')], getter, mode='any')
    assert rules.matches([], getter)
    assert not rules.matches([], getter, mode='any')
    assert rules.matches([cond('missing', category='Boom', prop='X')], getter)   # raise -> missing
    raises(ValueError, rules.matches, conds, getter, 'some')


def test_describe():
    assert rules.describe(cond('equals', 'Ducts')) == 'Element > Category = Ducts'
    assert rules.describe(cond('contains', 'PIPE', category='Item', prop='Name')) == \
        'Item > Name contains PIPE'
    assert rules.describe({'property': 'Level', 'op': 'ge', 'value': 3}) == 'Level >= 3'
    assert rules.describe(cond('between', [1, 3], prop='Level')) == 'Element > Level between 1 and 3'
    assert rules.describe(cond('in_list', ['Ducts', 'Pipes'])) == 'Element > Category is one of Ducts, Pipes'
    assert rules.describe(cond('in_list', ['A, B', 'C'])) == 'Element > Category is one of A, B; C'
    assert rules.describe(cond('empty', prop='Mark')) == 'Element > Mark is empty'
    assert rules.describe(cond('equals', 'Ducts', ignore_case=False)) == \
        'Element > Category = Ducts (match case)'
    assert rules.describe(cond('equals', '')) == 'Element > Category = ""'
    assert rules.describe(cond('gt', 3, ignore_case=False)) == 'Element > Category > 3'


def test_parse_cell_examples():
    assert rules.parse_cell('Element > Category = Ducts') == cond('equals', 'Ducts')
    c = rules.parse_cell('Item > Name contains PIPE')
    assert (c['category'], c['property'], c['op'], c['value']) == ('Item', 'Name', 'contains', 'PIPE')
    c = rules.parse_cell('Level >= 3')
    assert (c['category'], c['property'], c['op'], c['value']) == ('', 'Level', 'ge', '3')
    c = rules.parse_cell('Level > 3')
    assert (c['property'], c['op'], c['value']) == ('Level', 'gt', '3')
    c = rules.parse_cell('Element > Level > 3')
    assert (c['category'], c['property'], c['op']) == ('Element', 'Level', 'gt')
    c = rules.parse_cell('Element > Mark is empty')
    assert (c['property'], c['op'], c['value']) == ('Mark', 'empty', None)
    c = rules.parse_cell('Element > Category exists')
    assert (c['property'], c['op']) == ('Category', 'exists')
    c = rules.parse_cell('Element > Level between 1 and 3')
    assert c['op'] == 'between' and c['value'] == ['1', '3']
    c = rules.parse_cell('Element > Category is one of Ducts, Pipes')
    assert c['op'] == 'in_list' and c['value'] == ['Ducts', 'Pipes']
    c = rules.parse_cell('Item > Name like P-*')
    assert c['op'] == 'wildcard' and c['value'] == 'P-*'
    c = rules.parse_cell(r'Item > Name matches /^P\d+$/')
    assert c['op'] == 'regex' and c['value'] == r'^P\d+$'
    c = rules.parse_cell('Item > Name does not contain dummy')
    assert c['op'] == 'not_contains' and c['value'] == 'dummy'
    c = rules.parse_cell('Item > Name != X (match case)')
    assert c['op'] == 'not_equals' and c['ignore_case'] is False
    c = rules.parse_cell('Element > Category = Ducts > Pipes')
    assert c['value'] == 'Ducts > Pipes'
    c = rules.parse_cell('Element > Is Mirrored = Yes')
    assert (c['property'], c['op'], c['value']) == ('Is Mirrored', 'equals', 'Yes')
    c = rules.parse_cell('Element > "Phase is" = "a = b"')
    assert (c['property'], c['op'], c['value']) == ('Phase is', 'equals', 'a = b')
    c = rules.parse_cell('Item>Name<>Foo')
    assert (c['category'], c['property'], c['op'], c['value']) == ('Item', 'Name', 'not_equals', 'Foo')


def test_parse_cell_refuses():
    raises(ValueError, rules.parse_cell, '')
    raises(ValueError, rules.parse_cell, 'Element > Category')
    raises(ValueError, rules.parse_cell, '= Ducts')


def test_describe_and_parse_cell_round_trip():
    samples = [
        cond('equals', 'Ducts'), cond('not_equals', 'Ducts'), cond('contains', 'a b'),
        cond('not_contains', 'x'), cond('starts_with', 'S'), cond('ends_with', 'e'),
        cond('wildcard', 'P-*'), cond('regex', r'^\d+$'), cond('gt', '3'), cond('ge', '3'),
        cond('lt', '3'), cond('le', '3'), cond('between', ['1', '3']),
        cond('in_list', ['Ducts', 'Pipes']), cond('exists'), cond('missing'), cond('empty'),
        cond('not_empty'), cond('equals', 'Ducts', ignore_case=False),
        {'category': '', 'property': 'Level', 'op': 'le', 'value': '2', 'ignore_case': True},
    ]
    for c in samples:
        text = rules.describe(c)
        back = rules.parse_cell(text)
        assert rules.normalise(back) == rules.normalise(c), (text, back)


def test_validate():
    assert rules.validate(cond('equals', 'Ducts')) == []
    assert rules.validate(cond('exists')) == []
    assert rules.validate('nope') == ['A rule must be a set of fields.']
    assert rules.validate({'op': 'equals', 'value': 'x'}) == ['Choose a property.']
    assert 'Unknown comparison' in rules.validate(cond('frobnicate', 'x'))[0]
    assert rules.validate(cond('equals', '')) == ['Enter a value for "equals".']
    assert rules.validate(cond('gt', 'abc')) == ['Enter a number for "greater than".']
    assert 'two numbers' in rules.validate(cond('between', 'x'))[0]
    assert 'at least one value' in rules.validate(cond('in_list', []))[0]
    assert 'does not read' in rules.validate(cond('regex', '('))[0]
    for problems in (rules.validate(cond('gt', 'abc')), rules.validate(cond('regex', '('))):
        for line in problems:
            assert line[0].isupper() and chr(0x2014) not in line and chr(0x2013) not in line


def test_native_plan():
    plan = rules.native_plan([cond('equals', 'Ducts'), cond('gt', '3', prop='Width')])
    assert plan == [[('Element', 'Category', 'equals', 'Ducts', True),
                     ('Element', 'Width', 'gt', 3.0, False)]]
    plan = rules.native_plan([cond('starts_with', 'P-'), cond('between', [1, 2], prop='L')])
    assert plan == [[('Element', 'Category', 'wildcard', 'P-*', True),
                     ('Element', 'L', 'ge', 1.0, False), ('Element', 'L', 'le', 2.0, False)]]
    plan = rules.native_plan([cond('in_list', ['Ducts', 'Pipes']), cond('exists', prop='Mark')])
    assert plan == [[('Element', 'Category', 'equals', 'Ducts', True), ('Element', 'Mark', 'exists', None, False)],
                    [('Element', 'Category', 'equals', 'Pipes', True), ('Element', 'Mark', 'exists', None, False)]]
    plan = rules.native_plan([cond('equals', 'A'), cond('missing', prop='B')], mode='any')
    assert plan == [[('Element', 'Category', 'equals', 'A', True)],
                    [('Element', 'B', 'missing', None, False)]]
    # Python-only cases
    assert rules.native_plan([]) is None
    assert rules.native_plan([cond('regex', 'x')]) is None
    assert rules.native_plan([cond('not_contains', 'x')]) is None
    assert rules.native_plan([cond('empty')]) is None
    assert rules.native_plan([cond('starts_with', 'P*')]) is None
    assert rules.native_plan([cond('equals', 'Ducts', category='')]) is None
    assert rules.native_plan([cond('equals', '123')]) is None
    assert rules.native_plan([cond('equals', '123')], numbers_as_text=True) == \
        [[('Element', 'Category', 'equals', '123', True)]]
    assert rules.native_plan([cond('in_list', ['a', 'b', 'c', 'd', 'e'])]) is None   # > 4 walks
    assert 'regex' not in rules.native_ops()


def test_native_query_builds_a_pynavis_builder():
    try:
        from pynavis import sets
    except ImportError:
        raise _compat.SkipTest('pynavis not importable here')
    builder = rules.native_query([cond('in_list', ['Ducts', 'Pipes']), cond('ge', '2', prop='Level')])
    query = builder.build()
    data = query.to_dict()
    assert len(data['or']) == 2
    first = data['or'][0]['and']
    assert first[0] == {'category': 'Element', 'prop': 'Category', 'op': 'equals',
                        'value': 'Ducts', 'ignore_case': True}
    assert first[1] == {'category': 'Element', 'prop': 'Level', 'op': 'ge', 'value': 2.0}
    builder = rules.native_query([cond('exists', prop='Mark'), cond('missing', prop='Note')])
    ops = [c['op'] for c in builder.build().to_dict()['or'][0]['and']]
    assert ops == ['has_property', 'not_has_property']
    assert rules.native_query([cond('regex', 'x')]) is None
