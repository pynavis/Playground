# -*- coding: utf-8 -*-
"""namo/__init__.py: the UI assembly references are added once per engine, not per run."""
import _compat  # noqa: F401 (puts lib on sys.path)
import namo


def test_references_are_added_once_per_engine():
    calls = []
    modules = {}
    first = namo._reference_ui_assemblies(calls.append, modules)
    assert first == list(namo._UI_ASSEMBLIES) and calls == list(namo._UI_ASSEMBLIES)
    # pyNavis drops namo from sys.modules and the package body runs again: nothing to do
    assert namo._reference_ui_assemblies(calls.append, modules) == []
    assert len(calls) == len(namo._UI_ASSEMBLIES)
    # a fresh engine has its own sys.modules: it gets the references
    again = []
    assert namo._reference_ui_assemblies(again.append, {}) == list(namo._UI_ASSEMBLIES)
    assert len(again) == len(namo._UI_ASSEMBLIES)


def test_a_reference_that_fails_does_not_stop_the_others():
    def add(name):
        if name == 'System.Xaml':
            raise IOError('not found')
    modules = {}
    added = namo._reference_ui_assemblies(add, modules)
    assert 'System.Xaml' not in added and 'WindowsBase' in added and 'System.Drawing' in added
    assert modules[namo._MARKER].done is True


def test_the_marker_survives_the_lib_sweep_and_is_not_a_session_holder():
    from namo import session
    assert not namo._MARKER.startswith(session.PREFIX)
    marker = {}
    namo._reference_ui_assemblies(lambda name: None, marker)
    assert not hasattr(marker[namo._MARKER], '__file__') or marker[namo._MARKER].__file__ is None
