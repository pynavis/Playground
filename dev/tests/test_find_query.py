# -*- coding: utf-8 -*-
"""namo.find_query: value kinds, typed native conditions, descriptions, tallies."""
import datetime

import _compat

from namo import find_query as fq


def test_kind_of():
    assert fq.kind_of(True) == 'bool'
    assert fq.kind_of(3) == 'int'
    assert fq.kind_of(2.5) == 'float'
    assert fq.kind_of('Ducts') == 'text'
    assert fq.kind_of(None) is None
    assert fq.kind_of(datetime.datetime(2026, 10, 5)) is None
    assert fq.kind_of((1.0, 2.0, 3.0)) is None


def test_value_text():
    assert fq.value_text(None) == fq.NO_VALUE
    assert fq.value_text('  ') == fq.NO_VALUE
    assert fq.value_text(False) == 'No'
    assert fq.value_text(3.0) == '3'
    assert fq.value_text(0.25) == '0.25'
    assert fq.value_text('Level 1') == 'Level 1'


def test_coerce():
    assert fq.coerce('yes', 'bool') is True
    assert fq.coerce('0', 'bool') is False
    _compat.raises(ValueError, fq.coerce, 'maybe', 'bool')
    assert fq.coerce('1,234', 'int') == 1234
    assert isinstance(fq.coerce('12', 'int'), int)
    assert fq.coerce('12.5', 'int') == 12.5           # not whole: stays a float
    assert fq.coerce('2.5', 'float') == 2.5
    _compat.raises(ValueError, fq.coerce, 'abc', 'float')
    assert fq.coerce(' Ducts ', 'text') == ' Ducts '


def test_majority_kind():
    assert fq.majority_kind([1, 2, 3]) == 'int'
    assert fq.majority_kind([1, 2.5]) == 'float'          # int + float read as float
    assert fq.majority_kind(['a', 1, 'b']) == 'text'
    assert fq.majority_kind([None, datetime.date(2026, 1, 1)]) == 'text'
    assert fq.majority_kind([True, False, 'x']) == 'bool'


def test_text_equals_ignores_case_by_default():
    conds = fq.conditions('Element', 'Category', 'equals', 'Ducts')
    assert conds == [{'category': 'Element', 'prop': 'Category', 'op': 'equals', 'value': 'Ducts',
                      'ignore_case': True}]
    conds = fq.conditions('Element', 'Category', 'equals', 'Ducts', ignore_case=False)
    assert 'ignore_case' not in conds[0]


def test_float_equals_becomes_a_window():
    conds = fq.conditions('Element', 'Length', 'equals', 1000.0, kind='float')
    assert [c['op'] for c in conds] == ['ge', 'le']
    assert conds[0]['value'] < 1000.0 < conds[1]['value']
    assert _compat.approx(conds[1]['value'] - conds[0]['value'], 2 * 1000.0 * fq.FLOAT_TOLERANCE)
    zero = fq.conditions('Element', 'Offset', 'equals', 0.0, kind='float')
    assert zero[0]['value'] == -fq.FLOAT_FLOOR and zero[1]['value'] == fq.FLOAT_FLOOR


def test_int_and_bool_keep_their_type():
    conds = fq.conditions('Element ID', 'Value', 'equals', '312045', kind='int')
    assert conds[0]['value'] == 312045 and isinstance(conds[0]['value'], int)
    assert 'ignore_case' not in conds[0]
    conds = fq.conditions('Item', 'Hidden', 'equals', 'No', kind='bool')
    assert conds[0]['value'] is False


def test_numeric_and_value_free_ops():
    conds = fq.conditions('Element', 'Width', 'gt', '1,200', kind='text')
    assert conds == [{'category': 'Element', 'prop': 'Width', 'op': 'gt', 'value': 1200.0}]
    _compat.raises(ValueError, fq.conditions, 'Element', 'Width', 'lt', 'wide')
    assert fq.conditions('Element', 'Mark', 'has_property') == [
        {'category': 'Element', 'prop': 'Mark', 'op': 'has_property'}]
    assert fq.conditions('Element', 'Mark', 'not_has_property', 'ignored')[0]['op'] == 'not_has_property'
    _compat.raises(ValueError, fq.conditions, 'Element', 'Mark', 'equals', None)
    _compat.raises(ValueError, fq.conditions, 'Element', 'Mark', 'regex', 'x')
    contains = fq.conditions('Item', 'Name', 'contains', 'PIPE')
    assert contains[0]['ignore_case'] is True and contains[0]['value'] == 'PIPE'


def test_query_dict_and_describe():
    q = fq.query_dict([[{'category': 'A', 'prop': 'B', 'op': 'equals', 'value': 1}], []])
    assert q == {'or': [{'and': [{'category': 'A', 'prop': 'B', 'op': 'equals', 'value': 1}]}]}
    assert fq.describe('Element', 'Category', 'equals', 'Ducts') == 'Element > Category = Ducts'
    assert fq.describe('Element', 'Mark', 'not_has_property') == 'Element > Mark is missing'
    assert fq.describe('', 'Level', 'ge', 3) == 'Level >= 3'
    assert fq.describe_condition({'op': 'raw', 'text': 'odd'}) == 'odd'
    assert fq.describe_condition({'op': 'has_category', 'category': 'Element'}) == 'has category Element'


def test_stored_values_lose_the_variant_type_prefix():
    """Regression: pynavis.sets.to_dict / export_all read text values with
    VariantData.ToString(), which writes 'DisplayString:Ducts'. Exported and published sets
    must carry 'Ducts', or the imported set finds nothing."""
    assert fq.stored_value('DisplayString:Ducts') == 'Ducts'
    assert fq.stored_value('IdentifierString:a:b') == 'a:b'
    assert fq.stored_value('DoubleArea:12.5') == 12.5
    assert fq.stored_value('Int64:42') == 42 and isinstance(fq.stored_value('Int64:42'), int)
    for unchanged in ('Ducts', 'Level 1: east', 3, 2.5, True, None, 'DateTime:2026-10-05'):
        assert fq.stored_value(unchanged) == unchanged
    conds = [{'category': 'Element', 'prop': 'Category', 'op': 'equals', 'value': 'DisplayString:Ducts'},
             {'category': 'Element', 'prop': 'Mark', 'op': 'has_property'}]
    cleaned = fq.stored_conditions(conds)
    assert cleaned[0]['value'] == 'Ducts' and conds[0]['value'] == 'DisplayString:Ducts'
    assert cleaned[1] == conds[1]
    query = fq.stored_query({'or': [{'and': conds}]})
    assert query['or'][0]['and'][0]['value'] == 'Ducts'
    assert fq.describe_condition(conds[0]) == 'Element > Category = Ducts'


def test_join_descriptions():
    assert fq.join_descriptions(['a', 'b']) == 'a; b'
    assert fq.join_descriptions(['a', 'b', 'c', 'd', 'e'], 2) == 'a; b and 3 more'


def test_tally_values_keeps_raw_and_order():
    rows = fq.tally_values(['Level 10', 'Level 2', 'Level 2', 3, 3.0, None, ''])
    texts = [r[0] for r in rows]
    assert texts == ['3', fq.NO_VALUE, 'Level 2', 'Level 10']      # count, then natural order
    raw = dict((t, r) for t, _c, r in rows)
    assert raw['3'] == 3 and isinstance(raw['3'], int)       # first raw value kept
    assert dict((t, c) for t, c, _r in rows)[fq.NO_VALUE] == 2


def test_spread():
    assert fq.spread(10, 3) == [4, 3, 3]
    assert fq.spread(2, 4) == [1, 1, 0, 0]
    assert fq.spread(5, 0) == []
