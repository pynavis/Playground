# -*- coding: utf-8 -*-
"""Builds a one-page HTML clash dashboard of the chosen tests and opens it in the default browser."""
from pynavis import script, toast

from namo import clashrep_forms as cf
from namo import clashreport as cr
from namo import rep_clash_html as rep
from namo import ui

TITLE = 'Clash Dashboard'
DEFAULTS = {'tests': [], 'statuses': list(cr.OPEN), 'images': True}


def run():
    values = script.get_config(DEFAULTS)
    if cf.runner_active():
        cf.run_saved('clash_html', values)
        return
    doc = cr.active_doc()
    problem = cf.start(doc)
    if problem:
        toast.show(*problem)
        return
    tests = cf.pick_tests(TITLE, 'Tick the tests for the dashboard.', values['tests'], doc)
    if tests is None:
        return
    if not tests:
        toast.info('No clash results yet', 'Run your clash tests in Clash Detective first.')
        return
    path = cr.default_path(rep.NAME_TEMPLATE, 'html', doc)
    answers = ui.form(TITLE, cf.dashboard_fields(values, path), ok='Create', validate=cf.need_status, width=520)
    if answers is None:
        return
    cap = cr.IMAGE_CAP
    if answers['images']:
        cap = cf.ask_images(TITLE, tests, answers['statuses'])
        if cap is None:
            return
    values.update({'tests': cf.test_paths(tests), 'statuses': answers['statuses'], 'images': answers['images']})
    script.save_config(values)
    config = {'tests': values['tests'], 'statuses': answers['statuses'],
              'images': bool(answers['images']) and cap != -1, 'image_cap': max(0, cap), 'path': answers['path']}
    result = cf.run_report('clash_html', config, TITLE, doc)
    if result is None:
        return
    toast.show(result['level'], result['message'], result['detail'])
    if result['paths'] and result['level'] in ('success', 'warning'):
        try:
            ui.open_path(result['paths'][0])
        except Exception:
            toast.warning('Could not open the dashboard', 'Open it from %s.' % result['paths'][0])


run()
