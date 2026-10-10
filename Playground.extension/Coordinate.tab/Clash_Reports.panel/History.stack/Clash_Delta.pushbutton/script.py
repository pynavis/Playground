# -*- coding: utf-8 -*-
"""Compares the chosen clash tests now with a snapshot: new, fixed, still open and changed clashes."""
from pynavis import script, toast

from namo import clashrep_forms as cf
from namo import clashrep_history as hist
from namo import clashreport as cr
from namo import items, rep_clash_delta as rep
from namo import ui

TITLE = 'Clash Delta'
DEFAULTS = {'tests': [], 'xlsx': False, 'select': False}


def run():
    from namo import clashdata
    values = script.get_config(DEFAULTS)
    if cf.runner_active():
        cf.run_saved('clash_delta', values, {'baseline': 'auto'})
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
    entries = clashdata.list_history(doc_path)
    if not entries:
        toast.info('No clash snapshots yet',
                   'Take one with Snapshot (or turn on automatic snapshots), then compare after the next run.')
        return
    tests = cf.pick_tests(TITLE, 'Tick the tests to compare.', values['tests'], doc)
    if tests is None:
        return
    if not tests:
        toast.info('No clash results yet', 'Run your clash tests in Clash Detective first.')
        return
    names = clashdata.unique_names([t.DisplayName for t in tests])
    newest_first = sorted(entries, key=lambda e: (e.get('time') or '', e.get('id') or ''), reverse=True)
    choices = [(hist.entry_text(e, names), e['id']) for e in newest_first]
    default = hist.pick_baseline(entries)
    path = cr.default_path(rep.NAME_TEMPLATE, 'xlsx', doc)
    answers = ui.form(TITLE, cf.delta_fields(values, choices, default['id'], path), ok='Compare', width=640)
    if answers is None:
        return
    values.update({'tests': cf.test_paths(tests), 'xlsx': answers['xlsx'], 'select': answers['select']})
    script.save_config(values)
    config = {'tests': values['tests'], 'baseline': answers['baseline'], 'xlsx': answers['xlsx'],
              'path': answers['path'] if answers['xlsx'] else ''}
    result = cf.run_report('clash_delta', config, TITLE, doc)
    if result is None:
        return
    detail = result['detail']
    if answers['select'] and result['level'] in ('success', 'warning'):
        found = result.get('new_items') or []
        if found:
            count = items.select(found, zoom=True, doc=doc)
            detail = '%s Selected %s of the new clashes.' % (detail, cr.plural(count, 'item'))
        else:
            detail = '%s No new clashes to select.' % detail
    toast.show(result['level'], result['message'], detail)
    cf.reveal(result)


run()
