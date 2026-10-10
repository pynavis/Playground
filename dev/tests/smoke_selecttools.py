# -*- coding: utf-8 -*-
"""Select Similar window under IronPython + WPF: built with sample properties, the
identity filter, scope radios and acceptance driven through its state, never shown."""
import _compat

_compat.require_ironpython()

from namo import selecttools as st  # noqa: E402

PROPS = [
    {'category': 'Item', 'property': 'Name', 'value': 'Basic Wall'},
    {'category': 'Item', 'property': 'GUID', 'value': '6f1c2a10-1111-2222-3333-444455556666'},
    {'category': 'Element', 'property': 'Category', 'value': 'Walls'},
    {'category': 'Element', 'property': 'Family', 'value': 'Basic Wall'},
    {'category': 'Element', 'property': 'Type', 'value': 'Generic - 200mm'},
    {'category': 'Element', 'property': 'Mark', 'value': 'W-12'},
    {'category': 'Element', 'property': 'Width', 'value': 0.2},
]


def test_similar_window_builds_and_filters_identity():
    rows = st.similar_rows(PROPS)
    checked = st.default_checked(rows, [])
    win = st.build_similar_window(rows, checked, 'same_model', False, 'Basic Wall')
    state = win.Tag
    assert state.table.total() == len([r for r in rows if not r['identity']])
    assert state.table.checked_values() == checked
    assert state.scope() == 'same_model'
    state.identity_check.IsChecked = True           # fires the refilter
    assert state.table.total() == len(rows)
    assert state.table.checked_values() == checked  # ticks kept by key
    state.table.set_checked(['Item > GUID'], True)
    state.identity_check.IsChecked = False
    assert 'Item > GUID' not in state.table.checked_values()


def test_similar_window_opens_with_identity_when_remembered():
    rows = st.similar_rows(PROPS)
    win = st.build_similar_window(rows, ['Element > Mark'], 'model', False)
    assert win.Tag.show_identity()
    assert win.Tag.table.checked_values() == ['Element > Mark']


def test_similar_window_accept():
    rows = st.similar_rows(PROPS)
    win = st.build_similar_window(rows, [], 'model', False)
    state = win.Tag
    assert not state.accept()                       # nothing ticked
    state.table.set_checked(['Element > Category', 'Element > Width'], True)
    state.scope_buttons[2].IsChecked = True
    assert state.accept()
    assert state.result == {'keys': ['Element > Category', 'Element > Width'], 'scope': 'selection',
                            'show_identity': False}
