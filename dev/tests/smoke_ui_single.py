# -*- coding: utf-8 -*-
"""ui.Table.select_values on a single-select table (lead regression test: it used to
throw "Can only change SelectedItems collection in multiple selection modes")."""
import _compat

_compat.require_ironpython()

from namo import ui  # noqa: E402


def test_select_values_single_mode():
    rows = [{'value': i, 'cells': ['Row %d' % i]} for i in range(5)]
    table = ui.Table(['Name'], rows, multiselect=False)
    table.select_values([3])
    assert table.grid.SelectedItem is not None
    table.select_values([])
    assert table.grid.SelectedItem is None


def test_select_values_multi_mode():
    rows = [{'value': i, 'cells': ['Row %d' % i]} for i in range(5)]
    table = ui.Table(['Name'], rows, multiselect=True)
    table.select_values([1, 2])
    assert table.grid.SelectedItems.Count == 2
