# -*- coding: utf-8 -*-
"""Status Rules' editor window under IronPython + WPF: built with the example rules and
sample clashes, driven through its state (add, move, toggle, delete, accept), never shown."""
import datetime

import _compat

_compat.require_ironpython()

from namo import clashrules as cr  # noqa: E402

TODAY = datetime.datetime(2026, 10, 5)


def _row(i, depth, status='New', model_b='STR.nwc'):
    return {'id': i, 'name': 'Clash%d' % i, 'test': 'T', 'status': status, 'distance': -depth,
            'distance_m': -depth, 'created': '2026-08-01T08:00:00', 'model_a': 'MEP.nwc',
            'model_b': model_b, 'trade_a': 'Mechanical', 'trade_b': 'Structure', 'grid': 'C-4',
            'level': 'L2', 'assigned': '', 'group': None, 'item_a_name': 'Duct',
            'item_b_name': 'Beam', 'item_a': 'a', 'item_b': 'b', 'comments': 0, 'priority': 3,
            'description': ''}


ROWS = {'T': [_row(0, 0.001), _row(1, 0.02, model_b='MEP.nwc'), _row(2, 0.05, 'Reviewed')]}


def _preview(rule_list):
    compiled = [cr.compile_rule(r, 'Meters')[0] for r in rule_list]
    if not compiled:
        return None
    return cr.plan(ROWS, compiled, 'Meters', TODAY)


def test_editor_builds_and_previews_examples():
    win = cr.build_window('Examples', cr.EXAMPLE_RULES, _preview, 'Meters')
    state = win.Tag
    assert state.table.total() == 3
    assert state.status.Text == '3 of 3 clashes match a rule; 3 will change.'
    assert state.apply_button.IsEnabled
    assert [row['cells'][5] for row in state.rows()] == [1, 1, 1]


def test_editor_edits_through_state():
    win = cr.build_window('Team', [], _preview, 'Meters')
    state = win.Tag
    assert not state.apply_button.IsEnabled
    assert state.status.Text == 'Add a rule to see what it would change.'
    state.put(None, {'name': 'First', 'conditions': ['depth < 3mm'], 'status': 'Approved'})
    state.put(None, {'name': 'Second', 'conditions': ['depth > 1mm'], 'status': 'Active'})
    assert state.dirty and state.title_block.Text == 'Rule set: Team (changed)'
    state.table.select_values([1])
    state.move(-1)
    assert [r['name'] for r in state.rules] == ['Second', 'First']
    state.toggle()
    assert state.rules[0]['enabled'] is False
    state.table.select_values([0])
    state.delete()
    assert [r['name'] for r in state.rules] == ['First']
    state.load('Other', cr.EXAMPLE_RULES)
    assert not state.dirty and state.set_name == 'Other'
    assert state.accept()
    assert state.result['set'] == 'Other' and len(state.result['rules']) == 3


def test_rule_form_builds():
    from namo import ui
    win = ui.build_form('Status rule', cr.rule_form_fields(cr.EXAMPLE_RULES[0]),
                        validate=lambda values: cr.validate_form(values, 'Meters'))
    values, errors = win.Tag.collect()
    assert errors == {}
    assert values['conditions'].split('\n') == cr.EXAMPLE_RULES[0]['conditions']
