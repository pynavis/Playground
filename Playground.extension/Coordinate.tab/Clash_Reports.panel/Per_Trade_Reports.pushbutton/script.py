# -*- coding: utf-8 -*-
"""Writes one clash workbook (and an optional dashboard) per responsible trade into a folder, with an index."""
import os

from pynavis import script, toast

from namo import clashrep_forms as cf
from namo import clashreport as cr
from namo import rep_per_trade as rep
from namo import ui

TITLE = 'Per-Trade Reports'
DEFAULTS = {'tests': [], 'statuses': list(cr.OPEN), 'html': False, 'images': False, 'folder': '',
            'subfolder': True}


def run():
    values = script.get_config(DEFAULTS)
    if cf.runner_active():
        cf.run_saved('per_trade', values)
        return
    doc = cr.active_doc()
    problem = cf.start(doc)
    if problem:
        toast.show(*problem)
        return
    tests = cf.pick_tests(TITLE, 'Tick the tests to split by trade.', values['tests'], doc)
    if tests is None:
        return
    if not tests:
        toast.info('No clash results yet', 'Run your clash tests in Clash Detective first.')
        return
    priority, _people = rep.assigner_settings()
    folder = values['folder'] if values['folder'] and os.path.isdir(values['folder']) else cr.doc_folder(doc)
    answers = ui.form(TITLE, cf.per_trade_fields(values, folder, priority), ok='Write', validate=cf.need_status,
                      width=560)
    if answers is None:
        return
    cap = cr.IMAGE_CAP
    if answers['images']:
        cap = cf.ask_images(TITLE, tests, answers['statuses'])
        if cap is None:
            return
    values.update({'tests': cf.test_paths(tests), 'statuses': answers['statuses'], 'html': answers['html'],
                   'images': answers['images'], 'folder': answers['folder'], 'subfolder': answers['subfolder']})
    script.save_config(values)
    config = {'tests': values['tests'], 'statuses': answers['statuses'], 'html': answers['html'],
              'images': bool(answers['images']) and cap != -1, 'image_cap': max(0, cap),
              'folder': answers['folder'], 'subfolder': answers['subfolder']}
    result = cf.run_report('per_trade', config, TITLE, doc)
    if result is None:
        return
    toast.show(result['level'], result['message'], result['detail'])
    if result.get('folder') and result['level'] in ('success', 'warning'):
        try:
            ui.open_path(result['folder'])
        except Exception:
            toast.warning('Could not open the folder', result['folder'])


run()
