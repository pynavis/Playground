# -*- coding: utf-8 -*-
"""namo.find_batch: names and folders from templates, the extra condition, the plan."""
import _compat

from namo import find_batch as fb
from namo import find_query as fq


TALLY = fq.tally_values(['Level 1', 'Level 2', 'Level 2', 'Level 10', None, 3])


def test_render_and_folder():
    assert fb.render('{value}', 'Element', 'Level', 'Level 2') == 'Level 2'
    assert fb.render('{property}: {value}', 'Element', 'Level', 'L2') == 'Level: L2'
    assert fb.render('{value} ({count})', 'E', 'L', 'x', 1204) == 'x (1,204)'
    assert fb.render_folder('By {property}', 'Element', 'Level') == 'By Level'
    assert fb.render_folder('Sets/By {property}', 'Element', 'In/Out') == 'Sets/By In\\/Out'
    assert fb.render_folder('', 'E', 'L') == ''


def test_extra_conditions():
    assert fb.extra_conditions('') == []
    conds = fb.extra_conditions('Element > Category = Ducts')
    assert conds == [{'category': 'Element', 'prop': 'Category', 'op': 'equals', 'value': 'Ducts',
                      'ignore_case': True}]
    assert fb.extra_conditions('Element > Mark exists')[0]['op'] == 'has_property'
    assert [c['op'] for c in fb.extra_conditions('Element > Width between 1 and 2')] == ['ge', 'le']
    _compat.raises(ValueError, fb.extra_conditions, 'Item > Name matches ^P\\d+')
    _compat.raises(ValueError, fb.extra_conditions, 'nonsense without an operator')


def test_value_choices_leave_out_blank():
    labels = [v for _l, v in fb.value_choices(TALLY)]
    assert fq.NO_VALUE not in labels and 'Level 2' in labels


def test_plan_create_skip_replace():
    existing = {('by level', 'level 1'): 'guid-1'}
    rows = fb.plan('Element', 'Level', ['Level 1', 'Level 2', '3', 'missing'], TALLY, '{value}',
                   'By {property}', [], existing)
    assert [r['name'] for r in rows] == ['Level 1', 'Level 2', '3']
    assert [r['action'] for r in rows] == ['skip', 'create', 'create']
    assert rows[0]['guid'] == 'guid-1' and rows[1]['folder'] == 'By Level'
    assert rows[1]['count'] == 2
    cond = rows[2]['query']['or'][0]['and'][0]
    assert cond['value'] == 3 and isinstance(cond['value'], int)      # typed like the value
    rows = fb.plan('Element', 'Level', ['Level 1'], TALLY, '{value}', 'By {property}', [], existing,
                   replace=True)
    assert rows[0]['action'] == 'replace'


def test_plan_adds_extra_and_dedupes_names():
    extra = fb.extra_conditions('Element > Category = Ducts')
    rows = fb.plan('Element', 'Level', ['Level 1', 'Level 2'], TALLY, '{property}', '', extra, {})
    assert [r['name'] for r in rows] == ['Level', 'Level (2)']
    assert rows[0]['folder'] == ''
    assert len(rows[0]['query']['or'][0]['and']) == 2


def test_plan_case_option():
    rows = fb.plan('Element', 'Level', ['Level 1'], TALLY, '{value}', '', [], {}, ignore_case=False)
    assert 'ignore_case' not in rows[0]['query']['or'][0]['and'][0]


def test_summary():
    assert fb.summary(14, 0, 0, [], 'By Level') == ('success', "Created 14 search sets in 'By Level'", None)
    level, message, detail = fb.summary(1, 2, 3, ['x: bad'], '')
    assert level == 'warning' and message == "Wrote 3 search sets in 'the root'"
    assert detail == '2 replaced; 3 already existed and were skipped; 1 failed: x: bad'
    assert fb.summary(0, 0, 2, [], 'F')[0] == 'info'
    assert fb.summary(0, 0, 0, ['e'], 'F')[0] == 'error'
    assert fb.summary(0, 1, 0, [], 'A\\/B')[1] == "Replaced 1 search set in 'A/B'"
