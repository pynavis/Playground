# -*- coding: utf-8 -*-
"""clashdata.compare pairs same-key clashes by name first (lead regression test)."""
import _compat  # noqa: F401

from namo import clashdata


def _row(name, status):
    return {'name': name, 'status': status, 'key': 'A|B|0,0,0', 'test': 'T'}


def test_same_key_pairs_by_name():
    old = [_row('Clash1', 'Active'), _row('Clash2', 'New')]
    new = [_row('Clash2', 'Approved'), _row('Clash1', 'Active')]
    out = clashdata.compare(old, new)
    changed = out['status_changed']
    assert len(changed) == 1
    before, after = changed[0]
    assert before['name'] == 'Clash2' and after['name'] == 'Clash2'
