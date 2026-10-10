# -*- coding: utf-8 -*-
"""Records the current results of the chosen clash tests as a snapshot for Clash Delta and Clash Trends."""
from pynavis import forms, script, toast

from namo import clashrep_forms as cf
from namo import clashrep_history as hist
from namo import clashreport as cr
from namo import progress

TITLE = 'Clash Snapshot'
DEFAULTS = {'tests': []}


def run():
    values = script.get_config(DEFAULTS)
    doc = cr.active_doc()
    problem = cf.start(doc)
    if problem:
        toast.show(*problem)
        return
    if not cr.file_info(doc)[0]:
        toast.info('Save the model first', 'Clash snapshots are kept per model file.')
        return
    if cf.runner_active():
        tests, _missing = cr.resolve_tests(values['tests'], doc)
        label = ''
    else:
        tests = cf.pick_tests(TITLE, 'Tick the tests to record.', values['tests'], doc)
        if tests is None:
            return
        if not tests:
            toast.info('No clash results yet', 'Run your clash tests in Clash Detective first.')
            return
        label = forms.ask_string('Label for this snapshot (optional, for example "Before the 12 Oct meeting"):',
                                 '', TITLE)
        if label is None:
            return
        values['tests'] = cf.test_paths(tests)
        script.save_config(values)
    if not tests:
        toast.info('No clash results yet', 'Run your clash tests in Clash Detective first.')
        return
    try:
        outcome = progress.run('Recording clashes', lambda report: cr.record_snapshot(tests, label, doc, report))
    except RuntimeError as error:
        toast.error('Could not read the clashes', str(error))
        return
    except (IOError, OSError) as error:
        toast.error('Could not save the snapshot', str(error))
        return
    if outcome is progress.CANCELLED:
        return
    entry, where = outcome
    toast.success(*hist.snapshot_message(entry, where))


run()
