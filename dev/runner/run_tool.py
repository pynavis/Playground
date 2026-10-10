# -*- coding: utf-8 -*-
"""Runs one Playground tool under `pynavis run` (dev only).

    pynavis run dev\\runner\\run_tool.py <model.nwd> --timeout 120 -- <bundle key> [--select-all | --select-first]

The bundle key is the extension-relative path, e.g.
Model.tab/Select.panel/Select_Similar.pushbutton. --select-all selects every element
with geometry before the tool runs (--select-first only the first one), so a tool that
needs a selection takes its real path instead of the empty-selection one.

__result__ (captured by the runner into results.json) holds the outcome: ok,
needs-dialog (the runner's dialog refusal) or failed (anything else raised), the first
error line and traceback, the selection count, and every shell side effect the sandbox
stubbed out (see _bootstrap.py).
"""
import os
import sys

_here = os.path.dirname(os.path.abspath(__file__))
if _here not in sys.path:
    sys.path.insert(0, _here)

import _bootstrap  # noqa: E402

args = list(__args__)  # noqa: F821 (runner global)
key = args[0] if args else ''
mode = None
if '--select-all' in args:
    mode = 'all'
elif '--select-first' in args:
    mode = 'first'

namo_file = _bootstrap.use_playground_lib()
_bootstrap.enter_sandbox()
selected = 0
pre_error = ''
try:
    if mode:
        try:
            selected = _bootstrap.select_items(mode)
        except Exception as error:
            pre_error = 'select pre-step failed: %s' % error
    outcome = _bootstrap.run_bundle(key, globals())
finally:
    _bootstrap.leave_sandbox()

outcome.update({
    'key': key,
    'select': mode or '',
    'selected': selected,
    'blocked': list(_bootstrap.BLOCKED),
    'namo': namo_file,
})
if pre_error:
    outcome['pre_error'] = pre_error
__result__ = outcome
