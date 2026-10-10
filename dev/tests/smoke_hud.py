# -*- coding: utf-8 -*-
"""Selection HUD window built under IronPython + WPF: lines render, the window is
borderless, non-activating settings hold, placement maths runs; never shown."""
import _compat

_compat.require_ironpython()

from namo import hud  # noqa: E402


def test_hud_window_builds_and_updates():
    win, update = hud.build_window()
    from System.Windows import WindowStyle
    assert win.WindowStyle == getattr(WindowStyle, 'None')
    assert win.ShowActivated is False and win.ShowInTaskbar is False
    lines = hud.stats_lines({'count': 12, 'read': 12, 'objects': 4, 'models': ['A.rvt'],
                             'categories': {'Walls': 3, 'Doors': 1}})
    update(lines)
    stack = win.Content.Child
    assert stack.Children.Count == len(lines) == 3
    assert stack.Children[0].Text == '12 items selected (4 objects)'
    update([('Nothing selected', True)])
    assert stack.Children.Count == 1
    host = hud._place(win)
    assert len(host) == 4


def test_stop_is_safe_without_a_window():
    hud.stop()
    assert not hud.is_running()
