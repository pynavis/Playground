# -*- coding: utf-8 -*-
"""namo.insp_propsplus pure half (the window is smoke_insp_propsplus.py)."""
import _compat  # noqa: F401  (puts lib on sys.path)
from namo import inspect, insp_propsplus as plus


def test_rows_and_lines():
    summaries = {'Element > Category': inspect.summarize(['Walls', 'Walls'])}
    rows = plus.pinned_rows(['Element > Category', 'Element > Mark'], summaries)
    assert rows == [{'cells': ['Element > Category', 'Walls'], 'value': 'Element > Category'},
                    {'cells': ['Element > Mark', ''], 'value': 'Element > Mark'}]
    assert plus.status_line(0, 0).startswith('Nothing selected')
    assert plus.status_line(1, 1) == '1 item selected'
    assert plus.status_line(9000, 5000) == '9,000 items selected (values from the first 5,000)'


def test_detail_lines():
    assert plus.detail_line('P', None) == ''
    same = inspect.summarize(['A', 'A', 'A'])
    assert plus.detail_line('E > P', same) == 'E > P: A on all 3'
    varies = inspect.summarize(['A', 'B', 'A'] + [str(i) for i in range(6)])
    line = plus.detail_line('E > P', varies)
    assert line.startswith('Most common: A (2)') and line.endswith('and 3 more')
    assert plus.detail_line('E > P', inspect.summarize(['(missing)'])) == 'E > P is not on the selected items.'


def test_pin_lists():
    assert plus.add_pins(['A > B'], ['a > b', 'C > D']) == ['A > B', 'C > D']
    assert plus.remove_pins(['A > B', 'C > D'], ['a > b']) == ['C > D']
    rows = plus.item_rows([('Element', 'Mark', 'text', 'DisplayString', 'W1')])
    assert rows == [{'cells': ['Element', 'Mark', 'W1'], 'value': ('Element', 'Mark', 'W1', 'DisplayString')}]
    assert plus.DEFAULTS['pins'] == inspect.clean_pins(plus.DEFAULTS['pins'])
