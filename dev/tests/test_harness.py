# -*- coding: utf-8 -*-
"""Proves the harness itself: both engines import _compat and see the extension lib."""
import os

import _compat


def test_lib_on_path():
    assert os.path.isdir(_compat.LIB)


def test_raises_helper():
    error = _compat.raises(ValueError, int, 'x')
    assert isinstance(error, ValueError)


def test_dict_order_is_not_trusted():
    # IronPython 3.4 dicts do NOT keep insertion order. Code must sort or use lists.
    d = {}
    for k in 'zyxabc':
        d[k] = 1
    assert sorted(d) == ['a', 'b', 'c', 'x', 'y', 'z']
