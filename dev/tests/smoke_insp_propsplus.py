# -*- coding: utf-8 -*-
"""Properties Plus window built under IronPython + WPF and painted from a fake
selection: pinned summaries, the This item list, pin/unpin; never shown."""
import _compat

_compat.require_ironpython()

import test_items as nav  # noqa: E402
import test_propindex as pf  # noqa: E402

from namo import insp_propsplus as plus  # noqa: E402


class Me(object):
    def __init__(self):
        self.saved = {}

    def get_config(self, defaults):
        out = dict(defaults)
        out.update(self.saved)
        return out

    def save_config(self, values):
        self.saved.update(values)


def test_window_paints_selection():
    doc, n = pf.tree()
    with pf.Fake(doc):
        me = Me()
        win = plus.build_window(me, ['Element > Category', 'Element > Mark', 'Element > Nope'])
        state = win.Tag
        assert state.pinned.total() == 3
        doc.CurrentSelection.SelectedItems = nav.ModelItemCollection([n['Wall 1'], n['Wall 2']])
        state.paint(doc)
        assert state.status.Text == '2 items selected'
        values = dict((r['value'], r['cells'][1]) for r in state.pinned.rows)
        assert values['Element > Category'] == 'Walls'
        assert values['Element > Mark'] == 'Varies (2 values)'
        assert values['Element > Nope'] == 'Not on the selection'
        state.pinned.select_values(['Element > Mark'])
        assert state.detail.Text.startswith('Most common:')
        assert state.item_title.Text == 'This item: Wall 1'
        assert state.this_item.total() == 6
        state.this_item.select_values([state.this_item.rows[0]['value']])
        state.pin_from_item()
        assert me.saved['pins'][-1] == 'Element > Category' or 'Element > Category' in me.saved['pins']
        state.pinned.select_values(['Element > Nope'])
        state.unpin()
        assert 'Element > Nope' not in state.pins and 'Element > Nope' not in me.saved['pins']
        state.toggle_item()
        assert str(state.toggle.Content) == 'Show'
        doc.CurrentSelection.SelectedItems = nav.ModelItemCollection()
        state.paint(doc)
        assert state.status.Text.startswith('Nothing selected')
        assert state.this_item.total() == 0


def test_pure_helpers():
    assert plus.status_line(0, 0).startswith('Nothing selected')
    assert plus.status_line(9000, 5000) == '9,000 items selected (values from the first 5,000)'
    assert plus.add_pins(['A > B'], ['a > b', 'C > D']) == ['A > B', 'C > D']
    assert plus.remove_pins(['A > B', 'C > D'], ['a > b']) == ['C > D']
    rows = plus.item_rows([('Element', 'Mark', 'text', 'DisplayString', 'W1')])
    assert rows[0]['value'] == ('Element', 'Mark', 'W1', 'DisplayString')
    same = {'state': 'same', 'value': 'Walls', 'present': 3}
    assert plus.detail_line('Element > Category', same) == 'Element > Category: Walls on all 3'
