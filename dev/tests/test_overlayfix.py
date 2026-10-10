# -*- coding: utf-8 -*-
"""namo.overlayfix: which way up the view counts pixel rows."""
import _compat  # noqa: F401

from namo import overlayfix


def test_rows_from_top_or_bottom():
    assert overlayfix.rows_from_top(430, 380) is True       # above the axis = smaller row
    assert overlayfix.rows_from_top(430, 480) is False      # field case: rows from the bottom
    assert overlayfix.rows_from_top(430, 430.4) is None
    assert overlayfix.rows_from_top(None, 3) is None


def test_probe_points_sit_on_and_above_the_line_of_sight():
    centre, above = overlayfix.probe_points((1370221.9, 258278.8, 836.0), (0, 1, 0), (0, 0, 1), 30.0)
    assert centre == (1370221.9, 258308.8, 836.0)
    assert _compat.approx(above[2] - centre[2], 3.0) and above[:2] == centre[:2]


def test_every_tool_redraws_through_the_calibrated_route():
    import io
    import os
    root = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                        'Playground.extension')
    bad = []
    for folder, _dirs, files in os.walk(root):
        for name in files:
            if not name.endswith('.py') or name == 'overlayfix.py':
                continue
            path = os.path.join(folder, name)
            with io.open(path, encoding='utf-8') as handle:
                if 'overlay.redraw()' in handle.read():
                    bad.append(os.path.relpath(path, root))
    assert bad == []
