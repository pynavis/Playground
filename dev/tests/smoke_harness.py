# -*- coding: utf-8 -*-
"""Proves WPF + PyNavis.Runtime are reachable from the IronPython harness."""
import _compat

_compat.require_ironpython()

import clr  # noqa: E402

clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')
clr.AddReference('WindowsBase')
clr.AddReference('PyNavis.Runtime')

from System.Windows import Window  # noqa: E402
from System.Windows.Controls import StackPanel, TextBlock  # noqa: E402


def test_build_window():
    w = Window()
    panel = StackPanel()
    t = TextBlock()
    t.Text = 'hello'
    panel.Children.Add(t)
    w.Content = panel
    assert w.Content.Children.Count == 1


def test_design_system_tokens():
    from PyNavis.Runtime.Forms import DesignSystem
    tokens = DesignSystem.Tokens.For(False)
    assert tokens is not None


def test_pynavis_imports():
    from pynavis import settings, xl, clashgroup, lengths  # noqa: F401
    assert lengths is not None
