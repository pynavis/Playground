# -*- coding: utf-8 -*-
"""Writes a styled Excel clash report: a summary, then one sheet per test with a row (and thumbnail) per clash."""
from pynavis import script, toast

from namo import clashrep_forms as cf
from namo import clashreport as cr
from namo import rep_clash_excel as rep
from namo import ui

TITLE = 'Clash Excel Report'
DEFAULTS = {'tests': [], 'statuses': list(cr.OPEN), 'images': True, 'open': True}


def run():
    values = script.get_config(DEFAULTS)
    if cf.runner_active():
        cf.run_saved('clash_excel', values)
        return
    doc = cr.active_doc()
    problem = cf.start(doc)
    if problem:
        toast.show(*problem)
        return
    tests = cf.pick_tests(TITLE, 'Tick the tests to report.', values['tests'], doc)
    if tests is None:
        return
    if not tests:
        toast.info('No clash results yet', 'Run your clash tests in Clash Detective first.')
        return
    path = cr.default_path(rep.NAME_TEMPLATE, 'xlsx', doc)
    answers = ui.form(TITLE, cf.excel_fields(values, path), ok='Create', validate=cf.need_status, width=520)
    if answers is None:
        return
    cap = cr.IMAGE_CAP
    if answers['images']:
        cap = cf.ask_images(TITLE, tests, answers['statuses'])
        if cap is None:
            return
    values.update({'tests': cf.test_paths(tests), 'statuses': answers['statuses'], 'images': answers['images'],
                   'open': answers['open']})
    script.save_config(values)
    config = {'tests': values['tests'], 'statuses': answers['statuses'],
              'images': bool(answers['images']) and cap != -1, 'image_cap': max(0, cap), 'path': answers['path']}
    result = cf.run_report('clash_excel', config, TITLE, doc)
    if result is None:
        return
    toast.show(result['level'], result['message'], result['detail'])
    if answers['open'] and result['paths'] and result['level'] in ('success', 'warning'):
        try:
            ui.open_path(result['paths'][0])
        except Exception:
            toast.warning('Could not open the workbook', 'Open it from %s.' % result['paths'][0])
    elif not answers['open']:
        cf.reveal(result)


run()
