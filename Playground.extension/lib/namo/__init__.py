# -*- coding: utf-8 -*-
"""Playground: the shared library behind the Playground extension for pyNavis.

Every Playground tool keeps its logic here, split the pyNavis way: a pure half (plain dicts,
lists and strings, unit-tested under CPython and IronPython 3.4 outside Navisworks) and
a thin API half that talks to Navisworks. See README.md beside this file for the module
index and each module's contract.

IronPython 3.4 is the engine: no f-strings (house style), no type hints, and never
trust dict ordering (IronPython 3.4 dicts are NOT insertion ordered; sort, or use lists
of pairs).

Importing this package references the .NET UI assemblies once per session. pyNavis' engine
references none of them by default, so `from System.Windows.Threading import ...` raises
"No module named Threading" when it is the first WPF use of a session (field trap found
in review: the headless harness hid it because an earlier test had added the reference).
Every namo module is imported as `namo.<module>`, so this runs before any of them.

pyNavis drops lib modules from sys.modules before every run, so this file's body runs on
every click AND every hook run. Seven clr.AddReference calls measured about 27 ms, which a
selection-changed hook pays on every click in the view. References last for the life of
the engine, so a marker module in sys.modules (no __file__: the per-run sweep keeps it,
the same trick as namo.session.holder) records that they were added. A fresh engine has
its own sys.modules, so it has no marker and gets the references.
"""

import sys
import types

__version__ = '0.1.0'

_UI_ASSEMBLIES = ('WindowsBase', 'PresentationCore', 'PresentationFramework', 'System.Xaml',
                  'System.Drawing', 'System.Windows.Forms', 'WindowsFormsIntegration')
_MARKER = '_playground_references'      # not 'playground_<key>': namo.session.keys() must not list it


def _reference_ui_assemblies(add=None, modules=None):
    """Adds the UI assembly references unless this engine already has them. Returns
    the names added (empty when the marker says it was done, or outside IronPython).
    add and modules are test seams for clr.AddReference and sys.modules."""
    modules = sys.modules if modules is None else modules
    marker = modules.get(_MARKER)
    if marker is not None and getattr(marker, 'done', False):
        return []
    if add is None:
        try:
            import clr
        except ImportError:             # plain CPython (tests): nothing to reference
            return []
        add = clr.AddReference
    added = []
    for name in _UI_ASSEMBLIES:
        try:
            add(name)
            added.append(name)
        except Exception:
            pass
    marker = types.ModuleType(_MARKER)
    marker.done = True
    marker.added = tuple(added)
    modules[_MARKER] = marker
    return added


_reference_ui_assemblies()
