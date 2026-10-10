# -*- coding: utf-8 -*-
"""namo.picking: a pick needs the Navisworks window, so under `pynavis run` it refuses
with the runner's dialog message instead of switching to the Measure tool and blocking
(pynavis.pick.measure_point has no runner check of its own)."""
import sys
import types

import _compat  # noqa: F401 (puts the library on sys.path)

from namo import picking, ui


class _Calls(object):
    def __init__(self):
        self.calls = []


def _with_fakes(runner, body):
    seen = _Calls()
    pick = types.ModuleType('pynavis.pick')
    banner = types.ModuleType('pynavis.banner')

    def measure_point(prompt, notify=None):
        seen.calls.append(('measure_point', prompt))
        return None

    def measure_points(prompt, second, notify=None, keep=False):
        seen.calls.append(('measure_points', prompt))
        return None

    pick.measure_point = measure_point
    pick.measure_points = measure_points
    banner.clear = lambda: seen.calls.append(('clear',))
    banner.prompt = lambda text: None
    parent = sys.modules.get('pynavis')
    created = parent is None
    if created:
        parent = types.ModuleType('pynavis')
        sys.modules['pynavis'] = parent
    saved = {name: sys.modules.get(name) for name in ('pynavis.pick', 'pynavis.banner')}
    saved_attrs = {name: getattr(parent, name, None) for name in ('pick', 'banner')}
    sys.modules['pynavis.pick'] = pick
    sys.modules['pynavis.banner'] = banner
    parent.pick = pick
    parent.banner = banner
    original = ui.is_runner
    ui.is_runner = lambda: runner
    try:
        return body(seen)
    finally:
        ui.is_runner = original
        for name, module in saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module
        for name, value in saved_attrs.items():
            if value is None:
                try:
                    delattr(parent, name)
                except AttributeError:
                    pass
            else:
                setattr(parent, name, value)
        if created:
            sys.modules.pop('pynavis', None)


def _refuses(call):
    try:
        call()
    except RuntimeError as error:
        return ui.RUNNER_MESSAGE.split('.')[0] in str(error)
    return False


def test_point_refuses_under_the_runner_without_touching_the_measure_tool():
    def body(seen):
        assert _refuses(lambda: picking.point('Click a point'))
        assert _refuses(lambda: picking.points('From', 'To'))
        assert not any(call[0].startswith('measure') for call in seen.calls)
    _with_fakes(True, body)


def test_point_picks_through_the_measure_tool_outside_the_runner():
    def body(seen):
        assert picking.point('Click a point') is None
        assert picking.points('From', 'To') is None
        assert [c[0] for c in seen.calls if c[0].startswith('measure')] == ['measure_point', 'measure_points']
    _with_fakes(False, body)
