# -*- coding: utf-8 -*-
"""One dispatcher for every Playground event handler.

pyNavis allows one hooks/<event>.py per extension, but several Playground tools listen for
the same event (Selection History and Pick Order both want selection changes). Each
hooks/<event>.py file therefore calls dispatch(), which runs the handler modules
registered below for that event, in order.

Contract for a handler module, lib/namo/hk_<name>.py:

    def handle(name, event):
        '''name is the kebab-case event; event is pyNavis' __event__ dict
        ({'name', 'command', 'viewpoint'}) or, for 'startup', {'name', 'runner'}.'''

Rules every handler follows:
  * Check its own on/off switch FIRST and return at once when off. Hooks run on the
    UI thread with a 500 ms soft budget, on every selection change for some events.
  * Import anything heavy inside the function, not at module level: lib modules are
    re-imported on every hook run (pyNavis drops lib modules from the cache before
    each run so edits apply without Reload).
  * Never raise on purpose. dispatch() catches and logs anyway, so a broken handler
    costs only itself: pyNavis would disable the whole hook file after 3 failures,
    which would silently take every other tool's handler down with it.

A handler listed here whose module does not exist yet is skipped quietly; one whose
module exists but fails to import is logged as an error.
"""
import os
import sys
import time
import traceback

# pyNavis only says "Hook Playground:<event> took N ms" for the whole file. A handler slower
# than this is named in the log, so the tool to fix is known.
SLOW_HANDLER_S = 0.25

# (event, handler module under namo/) in run order. Owners in brackets.
HANDLERS = [
    ('selection-changed', 'hk_selhistory'),     # Selection History   [Select panel]
    ('selection-changed', 'hk_pickorder'),      # Pick Order          [Select panel]
    ('before-command', 'hk_usage'),             # Usage Analytics     [Team panel]
    ('after-command', 'hk_usage'),              # Usage Analytics     [Team panel]
    ('after-command', 'hk_macro'),              # Macro Recorder      [Automate panel]
    ('doc-opened', 'hk_stalecheck'),            # Stale File Alert    [Models panel]
    ('doc-opened', 'hk_folderwatch'),           # Folder Watch        [Models panel]
    ('doc-opened', 'hk_issuepins'),             # Issue Pins          [Issues panel]
    ('doc-closed', 'hk_issuepins'),             # Issue Pins          [Issues panel]
    ('doc-opened', 'hk_photopins'),             # Photo Pins          [Field panel]
    ('doc-closed', 'hk_photopins'),             # Photo Pins          [Field panel]
    ('doc-opened', 'hk_sessionstats'),         # Session Stats       [Quality panel]
    ('doc-saved', 'hk_clashhistory'),           # Clash Trends        [Clash Reports panel]
    ('model-appended', 'hk_sessionstats'),      # Session Stats       [Quality panel]
    ('model-appended', 'hk_transformpresets'),  # Transform Fixer     [Models panel]
    ('app-closing', 'hk_presentation'),         # Presentation Mode   [Look panel]
    ('app-closing', 'hk_camsync'),              # Camera Sync         [Navigate panel]
    ('app-closing', 'hk_folderwatch'),          # Folder Watch        [Models panel]
    ('startup', 'hk_teamsync'),                 # Team Config Sync    [Team panel]
    ('startup', 'hk_folderwatch'),              # Folder Watch        [Models panel]
]

_HERE = os.path.dirname(os.path.abspath(__file__))


def handlers_for(name):
    """Handler module names registered for one event, in run order."""
    return [module for event, module in HANDLERS if event == name]


def _logger():
    try:
        from pynavis import script
        return script.get_logger()
    except Exception:
        return None


def _report(message, level='error'):
    log = _logger()
    if log is not None:
        try:
            getattr(log, level)(message)
            return
        except Exception:
            pass
    try:
        sys.stderr.write(message + '\n')
    except Exception:
        pass


def as_dict(event):
    """A plain Python dict from pyNavis' __event__. pyNavis passes a .NET
    Dictionary<string, object>, which has no .get() under IronPython 3.4 (field trap
    found in review: Record Macro never recorded because of it)."""
    if event is None:
        return {}
    if isinstance(event, dict):
        return event
    out = {}
    try:
        for key in event.Keys:
            out[str(key)] = event[key]
        return out
    except Exception:
        pass
    try:
        return dict(event)
    except Exception:
        return {}


def dispatch(name, event):
    """Runs every handler registered for `name`, each given a plain dict. Never raises."""
    event = as_dict(event)
    for module_name in handlers_for(name):
        if not os.path.exists(os.path.join(_HERE, module_name + '.py')):
            continue
        try:
            module = __import__('namo.' + module_name, fromlist=['handle'])
        except Exception:
            _report('Playground: handler %s could not be imported for %s:\n%s'
                    % (module_name, name, traceback.format_exc()))
            continue
        handle = getattr(module, 'handle', None)
        if handle is None:
            _report('Playground: handler %s has no handle(name, event)' % module_name)
            continue
        started = time.time()
        try:
            handle(name, event)
        except Exception:
            _report('Playground: handler %s failed on %s:\n%s'
                    % (module_name, name, traceback.format_exc()))
        took = time.time() - started
        if took > SLOW_HANDLER_S:
            _report('Playground: handler %s took %d ms on %s' % (module_name, int(took * 1000), name),
                    'warning')
