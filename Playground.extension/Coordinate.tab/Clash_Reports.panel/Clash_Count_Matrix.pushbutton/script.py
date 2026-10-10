# -*- coding: utf-8 -*-
"""Counts open and new clashes trade against trade (or model against model) across the chosen tests."""
from pynavis import script, toast

from namo import clashrep_forms as cf
from namo import clashreport as cr
from namo import rep_clash_matrix as rep
from namo import ui

TITLE = 'Clash Count Matrix'
DEFAULTS = {'tests': [], 'axis': 'trade', 'xlsx': False}


def run():
    values = script.get_config(DEFAULTS)
    if cf.runner_active():
        cf.run_saved('clash_matrix', values)
        return
    doc = cr.active_doc()
    problem = cf.start(doc)
    if problem:
        toast.show(*problem)
        return
    tests = cf.pick_tests(TITLE, 'Tick the tests to count.', values['tests'], doc)
    if tests is None:
        return
    if not tests:
        toast.info('No clash results yet', 'Run your clash tests in Clash Detective first.')
        return
    path = cr.default_path(rep.NAME_TEMPLATE, 'xlsx', doc)
    answers = ui.form(TITLE, cf.matrix_fields(values, path), ok='Count', width=500)
    if answers is None:
        return
    values.update({'tests': cf.test_paths(tests), 'axis': answers['axis'], 'xlsx': answers['xlsx']})
    script.save_config(values)
    config = {'tests': values['tests'], 'axis': answers['axis'], 'xlsx': answers['xlsx'],
              'path': answers['path'] if answers['xlsx'] else ''}
    result = cf.run_report('clash_matrix', config, TITLE, doc)
    if result is None:
        return
    toast.show(result['level'], result['message'], result['detail'])
    cf.reveal(result)


run()
