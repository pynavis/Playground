# -*- coding: utf-8 -*-
"""Turns clash groups and ungrouped clashes into issues, once each, with view, snapshot and elements."""
from pynavis import script, toast

from namo import clashdata, issue_clash, issueapi, issuestore, progress, ui

STATUSES = ['New', 'Active', 'Reviewed', 'Approved', 'Resolved']


def run():
    doc = issuestore.active_doc()
    if doc is None or not issueapi.has_model(doc):
        toast.info('No model open', 'Open the model with the clash tests first.')
        return
    store = issuestore.for_doc(doc)
    if not store.saved:
        toast.info('Save the model first', issuestore.NOT_SAVED)
        return
    names = [clashdata.test_path(t) for t in clashdata.tests(doc)]
    if not names:
        toast.info('No clash tests', 'Set up and run clash tests in Clash Detective first.')
        return
    me = script.bind()
    values = me.get_config(dict(issue_clash.DEFAULTS))
    chosen = [n for n in values.get('tests') or [] if n in names] or names
    fields = [
        {'kind': 'multi', 'key': 'tests', 'label': 'Clash tests', 'options': names, 'default': chosen},
        {'kind': 'multi', 'key': 'statuses', 'label': 'Convert clashes with these statuses',
         'options': STATUSES, 'default': [s for s in values['statuses'] if s in STATUSES]},
        {'kind': 'check', 'key': 'snapshots', 'label': 'Attach the clash image as the snapshot',
         'default': bool(values['snapshots'])},
        {'kind': 'label', 'muted': True,
         'text': 'Each top-level group, and each clash outside a group, becomes one issue. Clashes '
                 'that already have an issue are skipped. Trade, priority and due date follow the '
                 'rules under Shift+Click.'},
    ]

    def check(answers):
        if not answers['tests']:
            return {'tests': 'Tick at least one clash test.'}
        if not answers['statuses']:
            return {'statuses': 'Tick at least one status.'}
        return None

    answers = ui.form('Clash to Issues', fields, ok='Create issues', width=540, validate=check)
    if answers is None:
        return
    values.update(answers)
    me.save_config(values)
    outcome = progress.run('Clash to Issues', lambda report: issue_clash.convert(
        answers['tests'], values, doc, report))
    if outcome is progress.CANCELLED:
        return
    created = len(outcome['created'])
    parts = []
    if outcome['skipped']:
        parts.append('%s already had issues' % '{:,}'.format(outcome['skipped']))
    if outcome['filtered']:
        parts.append('%s had other statuses' % '{:,}'.format(outcome['filtered']))
    if outcome['snapshot_errors']:
        parts.append('%d snapshots failed' % outcome['snapshot_errors'])
    detail = ('; '.join(parts) + '.') if parts else ''
    if created:
        first, last = outcome['created'][0], outcome['created'][-1]
        span = first if created == 1 else '%s to %s' % (first, last)
        toast.success('Created %s issue%s' % ('{:,}'.format(created), '' if created == 1 else 's'),
                      ('%s. %s' % (span, detail)).strip())
    else:
        toast.info('No new issues', detail or 'No clash group or clash matched the chosen statuses.')


run()
