# -*- coding: utf-8 -*-
"""Clash Namer's preview window under IronPython + WPF: built with sample tests, the
preview driven through its state, never shown."""
import _compat

_compat.require_ironpython()

from namo import clashname as cn  # noqa: E402


def _row(i, name, grid='C-4'):
    return {'id': i, 'name': name, 'test': 'Ducts vs Beams', 'grid': grid, 'level': 'L2',
            'model_a': 'MEP.nwc', 'model_b': 'STR.nwc', 'trade_a': 'Mechanical',
            'trade_b': 'Structure', 'status': 'New', 'distance': -0.02, 'group': None,
            'assigned': '', 'item_a_name': 'Duct', 'item_b_name': 'Beam'}


ENTRIES = [{'name': 'Ducts vs Beams', 'rows': [_row(i, 'Clash%d' % (i + 1)) for i in range(40)],
            'specs': [{'gid': 0, 'name': 'Group 1', 'ids': [0, 1, 2]}]},
           {'name': 'Pipes vs Walls', 'rows': [_row(i, 'Clash%d' % (i + 1), 'D-5') for i in range(3)],
            'specs': []}]


def _preview(clash_template, group_template, scope):
    return cn.preview(ENTRIES, clash_template, group_template, scope, 'Millimeters')


def test_window_builds_and_previews():
    win = cn.build_window(_preview, {'clash_template': '{test} {n:000}', 'group_template': '{grid}',
                                     'scope': 'both'})
    state = win.Tag
    assert state.table.total() == cn.PREVIEW_ROWS
    assert state.status.Text == 'Renames 43 clashes and 1 group in 2 tests'
    assert state.apply_button.IsEnabled
    state.clash_box.Text = '{nope}'
    state.refresh()
    assert not state.apply_button.IsEnabled
    assert state.status.Text.startswith('{nope} is not a token')
    state.clash_box.Text = '{test} {n:000}'
    state.scope_buttons[1].IsChecked = True
    rows = state.refresh()
    assert [r[1] for r in rows] == ['Group']
    assert state.values()['scope'] == 'groups'


def test_accept_records_result_without_showing():
    win = cn.build_window(_preview, {})
    state = win.Tag
    assert state.clash_box.Text == cn.DEFAULT_CLASH
    assert state.accept()
    assert state.accepted
    assert state.result == {'clash_template': cn.DEFAULT_CLASH, 'group_template': cn.DEFAULT_GROUP,
                            'scope': 'clashes'}
