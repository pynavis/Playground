# -*- coding: utf-8 -*-
"""Runs one Playground schedule's report templates under `pynavis run`, with no dialogs.

Scheduled Reports registers a Windows task that calls

    pynavis.exe run "<this file>" "<model>" --timeout <s> --results "<log>" --
        --schedule "<name>" --templates "<report>:<template>;..." [--mail "<profile>"]
        [--folder "<folder>"] [--copy-to "<folder>"] [--no-attach]

The runner adds only this file's folder to the module path, so the extension's lib
folder is added here. Everything else is namo.schedule.run_from_runner: run the
templates (interactive=False), copy and mail the results, write the run log. The
summary becomes __result__ (results.json); a failed report ends the run with exit
code 1 so Task Scheduler shows it.
"""
import io
import os
import sys


def _add_lib():
    folder = os.path.dirname(os.path.abspath(__file__))
    while folder and not folder.lower().endswith('.extension'):
        parent = os.path.dirname(folder)
        if parent == folder:
            return
        folder = parent
    lib = os.path.join(folder, 'lib')
    if os.path.isdir(lib) and lib not in sys.path:
        sys.path.append(lib)


if not globals().get('__runner__', False):
    from pynavis import toast
    toast.info('Scheduled Reports runs this file', 'It runs from a scheduled task. Use Scheduled Reports to set one up.')
else:
    _add_lib()
    from namo import schedule
    __result__ = schedule.run_from_runner(list(__args__), __model__)
    _log = __result__.get('log') or ''
    if _log and os.path.isfile(_log):
        with io.open(_log, encoding='utf-8') as _handle:
            print(_handle.read())
    if __result__.get('failed') or __result__.get('problems'):
        sys.exit(1)
