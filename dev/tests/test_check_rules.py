# -*- coding: utf-8 -*-
"""dev/check.py house rules: the banned pynavis pick tool (CPython only: check.py is a
dev script and never runs under IronPython)."""
import ast
import os
import sys

import _compat


def _problems(source):
    _compat.require_cpython('check.py runs under CPython')
    dev = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if dev not in sys.path:
        sys.path.insert(0, dev)
    import check
    before = len(check.problems)
    path = os.path.join(check.EXT, 'lib', 'namo', 'sample.py')
    check.PyRules(path, False).visit(ast.parse(source))
    found = check.problems[before:]
    del check.problems[before:]
    return found


def test_pick_point_calls_are_refused():
    assert len(_problems('from pynavis import pick\nhit = pick.point("Click")\n')) == 1
    assert len(_problems('import pynavis\npynavis.pick.point_then(done)\n')) == 1
    assert len(_problems('from pynavis.pick import point\n')) == 1
    found = _problems('from pynavis import pick\n\ndef go():\n    return pick.point_then(lambda p: p)\n')
    assert len(found) == 1 and 'line 4' in found[0] and 'namo.picking' in found[0]


def test_mentions_and_the_safe_routes_are_not():
    doc = '"""pynavis.pick.point (the custom tool) is not used: pick.point( and pick.point_then( are banned."""\n'
    assert _problems(doc) == []
    assert _problems('# pick.point(prompt) was here\nx = 1\n') == []
    assert _problems('from namo import picking\nhit = picking.point("Click", want_item=True)\n') == []
    assert _problems('from pynavis import pick\np = pick.measure_point()\nq = pick.measure_points(2)\n') == []
    assert _problems('grid.point(1, 2)\nself.point_then = 3\n') == []
