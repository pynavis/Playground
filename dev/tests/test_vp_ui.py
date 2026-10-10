# -*- coding: utf-8 -*-
"""namo.vp_ui pure half: moving rows in the hand-order list."""
import _compat

from namo import vp_ui


def test_moved_every_way():
    order = [0, 1, 2, 3]
    assert vp_ui.moved(order, 2, 'up') == [0, 2, 1, 3]
    assert vp_ui.moved(order, 2, 'down') == [0, 1, 3, 2]
    assert vp_ui.moved(order, 2, 'top') == [2, 0, 1, 3]
    assert vp_ui.moved(order, 1, 'bottom') == [0, 2, 3, 1]
    assert vp_ui.moved(order, 0, 'up') == order
    assert vp_ui.moved(order, 3, 'down') == order
    assert vp_ui.moved(order, 9, 'up') == order
    assert order == [0, 1, 2, 3]


def test_rows_for_number_positions():
    rows = vp_ui.rows_for([2, 0], ['a', 'b', 'c'])
    assert rows == [{'value': 2, 'cells': [1, 'c']}, {'value': 0, 'cells': [2, 'a']}]
