# -*- coding: utf-8 -*-
"""Property Explorer window built under IronPython + WPF with a sample index: the
three linked tables load, follow selection and filter; never shown."""
import time

import _compat

_compat.require_ironpython()

from namo import data_explorer, items, propindex  # noqa: E402


class Me(object):
    def __init__(self):
        self.saved = {}

    def get_config(self, defaults):
        out = dict(defaults)
        out.update(self.saved)
        return out

    def save_config(self, values):
        self.saved.update(values)


def _entry():
    index = propindex.PropIndex()
    for n in range(300):
        rows = [('Element', 'Category', 'text', 'DisplayString', ['Walls', 'Ducts', 'Pipes'][n % 3]),
                ('Element', 'Mark', 'text', 'DisplayString', 'M%d' % (n % 40)),
                ('Element', 'Length', 'length', 'DoubleLength', '%d mm' % (1000 + n % 7)),
                ('Item', 'Name', 'text', 'DisplayString', 'Item %d' % n)]
        if n % 2:
            rows.append(('Playground', 'Status', 'text', 'DisplayString', 'Open'))
        index.add(rows)
    item_list = items.ItemList(['item%d' % n for n in range(300)])
    return {'index': index, 'items': item_list, 'scope': 'model', 'level': 'objects', 'budget': 1000,
            'time': time.time(), 'sampled': False}


def test_explorer_loads_linked_lists():
    entry = _entry()
    win = data_explorer.build_window(entry, Me())
    state = win.Tag
    assert state.categories.total() == 3
    assert state.category == 'Element'
    assert state.prop == 'Category'
    assert state.values.total() == 3
    assert state.values.rows[0]['cells'][1] == 100
    assert 'scanned at' in state.status.Text
    state.properties.select_values(['Mark'])
    assert state.prop == 'Mark' and state.values.total() == 40
    state.values.set_filter('M1')
    assert 0 < state.values.visible_count() < 40
    state.values.select_values(['M1'])
    assert 'picked' in state.footer_note.Text
    state.categories.select_values(['Playground'])
    assert state.category == 'Playground' and state.prop == 'Status'
    values = [r['value'] for r in state.values.rows]
    assert values == ['Open', propindex.MISSING]


def test_explorer_reload_in_place():
    win = data_explorer.build_window(_entry(), Me())
    state = win.Tag
    other = _entry()
    other['scope'] = 'selection'
    state.load(other)
    assert state.entry is other and 'current selection' in state.status.Text


def test_pure_helpers():
    entry = _entry()
    rows = data_explorer.value_rows(entry['index'], 'Element', 'Category')
    assert rows[0]['cells'][2] == '33.3%'
    assert data_explorer.first_choice(['a', 'b'], 'b') == 'b'
    assert data_explorer.first_choice(['a'], 'z') == 'a'
    assert data_explorer.first_choice([], 'z') is None
    assert data_explorer.set_name('Element', 'Category', 'Ducts') == 'Category = Ducts'
    assert data_explorer.set_name('Element', 'Mark', 'x' * 80).endswith('...')
