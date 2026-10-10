# -*- coding: utf-8 -*-
"""Charts open and resolved clashes over the model's clash snapshots, with a burn-down table."""
import os

from pynavis import script, toast

from namo import clashrep_forms as cf
from namo import clashreport as cr
from namo import rep_clash_trends as rep
from namo import ui

TITLE = 'Clash Trends'
DEFAULTS = {'tests': [], 'series': 'total', 'current': True, 'xlsx': False, 'csv': False}


def run():
    from namo import clashdata
    values = script.get_config(DEFAULTS)
    if cf.runner_active():
        cf.run_saved('clash_trends', values)
        return
    doc = cr.active_doc()
    problem = cf.start(doc)
    if problem:
        toast.show(*problem)
        return
    doc_path = cr.file_info(doc)[0]
    if not doc_path:
        toast.info('Save the model first', 'Clash snapshots are kept per model file, so an unsaved model has none.')
        return
    if not clashdata.list_history(doc_path):
        toast.info('No clash snapshots yet',
                   'Take one with Snapshot (or turn on automatic snapshots), then come back after the next run.')
        return
    tests = cf.pick_tests(TITLE, 'Tick the tests to follow.', values['tests'], doc)
    if tests is None:
        return
    if not tests:
        toast.info('No clash results yet', 'Run your clash tests in Clash Detective first.')
        return
    path = cr.default_path(rep.NAME_TEMPLATE, 'xlsx', doc)
    answers = ui.form(TITLE, cf.trends_fields(values, path), ok='Draw', width=560)
    if answers is None:
        return
    export = answers['export']
    values.update({'tests': cf.test_paths(tests), 'series': answers['series'], 'current': answers['current'],
                   'xlsx': export in ('xlsx', 'both'), 'csv': export in ('csv', 'both')})
    script.save_config(values)
    target = answers['path'] if export != 'none' else ''
    if export == 'csv' and target:
        target = os.path.splitext(target)[0] + '.csv'
    config = {'tests': values['tests'], 'series': values['series'], 'current': values['current'],
              'xlsx': values['xlsx'], 'csv': values['csv'], 'path': target}
    result = cf.run_report('clash_trends', config, TITLE, doc)
    if result is None:
        return
    toast.show(result['level'], result['message'], result['detail'])
    cf.reveal(result)


run()
