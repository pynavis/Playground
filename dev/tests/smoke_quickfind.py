# -*- coding: utf-8 -*-
"""Quick Find window under IronPython + WPF: built over a sample index, searched,
highlighted results rendered, every action driven through FindState, never shown."""
import _compat

_compat.require_ironpython()

from namo import quickfind as qf  # noqa: E402

KEYS = ['name', 'class', 'element_id', 'category', 'type', 'level']
ROWS = [
    (0, '0/1/1', ['Basic Wall', 'Solid', '312045', 'Walls', 'Generic - 200mm', 'Level 1']),
    (0, '0/1/2', ['Basic Wall', 'Solid', '312046', 'Walls', 'Generic - 300mm', 'Level 2']),
    (1, '0/4', ['Rectangular Duct', 'Solid', '900001', 'Ducts', 'Mitered Elbows', 'Level 3']),
    (1, '0/6', ['Supply Diffuser', 'Block', '900003', 'Air Terminals', '600x600', 'Level 10']),
]


def make_index():
    return qf.QuickIndex(KEYS, ['Arch.nwc', 'MEP.nwc'], ROWS)


def test_window_builds_empty_and_with_a_query():
    win = qf.build_window(make_index(), cap=50)
    state = win.Tag
    assert state.shown == [] and state.listing.Items.Count == 0
    assert state.status.Text == 'Type to search 4 elements'
    win = qf.build_window(make_index(), cap=50, query='wall')
    state = win.Tag
    assert state.shown == [0, 1] and state.listing.Items.Count == 2
    assert state.listing.SelectedIndex == 0
    assert state.status.Text == '2 matches'


def test_refresh_renders_highlights():
    win = qf.build_window(make_index(), cap=50)
    state = win.Tag
    state.refresh('900001')
    assert state.shown == [2]
    visual = state.listing.Items[0]
    stack = visual.Children[0]
    detail = stack.Children[1]
    texts = [run.Text for run in detail.Inlines]
    assert ''.join(texts) == 'Element ID: 900001'
    assert texts[-1] == '900001'                     # the highlighted run
    state.refresh('zzzz')
    assert state.listing.Items.Count == 0 and state.status.Text == 'No matches'


def test_finish_actions():
    index = make_index()
    win = qf.build_window(index, cap=50, query='level')
    state = win.Tag
    assert state.finish('select', [state.shown[0]])
    assert state.result == {'action': 'select', 'rows': [state.shown[0]], 'query': 'level'}
    win = qf.build_window(index, cap=2, query='level')
    state = win.Tag
    assert state.cap == 10                           # never fewer than 10 results listed
    assert len(index.all_matches()) == 4
    assert state.finish('all', index.all_matches())
    assert state.result['action'] == 'all' and len(state.result['rows']) == 4
    win = qf.build_window(index, cap=50)
    assert not win.Tag.finish('add', [])            # nothing highlighted: stays open


def test_cap_and_sampled_status():
    rows = [(0, str(i), ['Item %d' % i, 'Solid', '', '', '', '']) for i in range(300)]
    index = qf.QuickIndex(KEYS, ['A.nwc'], rows, sampled=True)
    win = qf.build_window(index, cap=20, query='item')
    state = win.Tag
    assert state.listing.Items.Count == 20
    assert state.status.Text == '300 matches, showing the best 20 (index sampled: the first 300 elements)'
