# -*- coding: utf-8 -*-
"""namo.data_explorer pure half: list rows, status, choices and set names (the window
itself is smoke_data_explorer.py)."""
import _compat  # noqa: F401  (puts lib on sys.path)
import time

from namo import data_explorer, items, propindex


def _entry():
    index = propindex.PropIndex()
    for n in range(30):
        index.add([('Element', 'Category', 'text', 'DisplayString', ['Walls', 'Ducts', 'Pipes'][n % 3]),
                   ('Item', 'Name', 'text', 'DisplayString', 'Item %d' % n)])
    return {'index': index, 'items': items.ItemList(range(30)), 'scope': 'visible', 'level': 'geometry',
            'time': time.mktime((2026, 10, 5, 14, 2, 0, 0, 0, -1)), 'sampled': True}


def test_rows():
    entry = _entry()
    assert data_explorer.category_rows(entry['index']) == [{'cells': ['Element', 30], 'value': 'Element'},
                                                           {'cells': ['Item', 30], 'value': 'Item'}]
    assert data_explorer.property_rows(entry['index'], 'Element') == [
        {'cells': ['Category', 30, 3], 'value': 'Category'}]
    rows = data_explorer.value_rows(entry['index'], 'Element', 'Category')
    assert [r['value'] for r in rows] == ['Ducts', 'Pipes', 'Walls']
    assert rows[0]['cells'] == ['Ducts', 10, '33.3%']
    assert data_explorer.export_rows(entry['index'])[0][:4] == ['Element', 'Category', 'Ducts', 10]


def test_status_and_helpers():
    text = data_explorer.status_text(_entry())
    assert text.startswith('30 geometry items among visible items (sampled')
    assert text.endswith('scanned at 14:02')
    assert data_explorer.first_choice(['a', 'b'], 'b') == 'b'
    assert data_explorer.first_choice(['a'], 'z') == 'a'
    assert data_explorer.first_choice([], 'z') is None
    assert data_explorer.set_name('Element', 'Category', 'Ducts') == 'Category = Ducts'
    assert data_explorer.set_name('Element', '', 'x') == 'Element = x'
    assert data_explorer.set_name('Element', 'Mark', 'x' * 80).endswith('...')
