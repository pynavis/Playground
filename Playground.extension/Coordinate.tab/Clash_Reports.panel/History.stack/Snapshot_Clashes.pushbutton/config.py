# -*- coding: utf-8 -*-
"""Options for clash snapshots: take one automatically on save, or delete old ones."""
from pynavis import forms, settings, toast

from namo import clashrep_forms as cf
from namo import clashrep_history as hist
from namo import clashreport as cr
from namo import config as namo_config
from namo import hk_clashhistory as auto
from namo import ui

TITLE = 'Clash snapshots'
AUTOMATIC = 'Snapshot automatically when the model is saved'
REVIEW = 'Review and delete snapshots of this model'


def automatic():
    values = auto.load_config()
    names = []
    try:
        from namo import clashdata
        names = clashdata.unique_names([t.DisplayName for t in cr.tests_with_results()])
    except Exception:
        names = []
    fields = cf.snapshot_settings_fields(values, names, namo_config.get('data_mode'))
    answers = ui.form(TITLE, fields, ok='Save', width=540)
    if answers is None:
        return
    values['auto_on_save'] = bool(answers['auto_on_save'])
    if answers.get('min_hours') is not None:
        values['min_hours'] = float(answers['min_hours'])
    if answers.get('max_results') is not None:
        values['max_results'] = int(answers['max_results'])
    if 'tests' in answers:
        values['tests'] = list(answers['tests'] or [])
    try:
        settings.save(auto.TOOL, values)
    except (IOError, OSError) as error:
        toast.error('Could not save the snapshot options', str(error))
        return
    if values['auto_on_save']:
        toast.success('Automatic clash snapshots are on',
                      'At most one every %s hours, when the clash counts changed, up to %s results.'
                      % ('%g' % values['min_hours'], '{:,}'.format(values['max_results'])))
    else:
        toast.success('Automatic clash snapshots are off', 'Use Snapshot to record one by hand.')


def review():
    from namo import clashdata
    doc_path = cr.file_info()[0]
    if not doc_path:
        toast.info('Save the model first', 'Clash snapshots are kept per model file.')
        return
    entries = sorted(clashdata.list_history(doc_path), key=lambda e: (e.get('time') or '', e.get('id') or ''),
                     reverse=True)
    if not entries:
        toast.info('No clash snapshots yet', 'Use Snapshot to record one.')
        return
    rows = []
    for entry in entries:
        when = hist.entry_time(entry)
        totals = hist.entry_totals(entry)
        rows.append({'value': entry['id'], 'cells': [when.strftime('%Y-%m-%d %H:%M') if when else '',
                                                     entry.get('label') or '', totals['tests'], totals['total'],
                                                     totals['open']]})
    picked = ui.choose(TITLE, rows, ['Taken', 'Label', 'Tests', 'Clashes', 'Open'], multiselect=True,
                       prompt='Tick the snapshots to delete. Clash Delta and Clash Trends will no longer see them.',
                       ok='Delete', width=720)
    if picked is None:
        return
    if not picked:
        toast.info('No snapshots ticked', 'Nothing was deleted.')
        return
    if not forms.confirm('Delete %s? This cannot be undone.' % cr.plural(len(picked), 'snapshot'), TITLE):
        return
    deleted = 0
    try:
        for history_id in picked:
            if clashdata.delete_history(doc_path, history_id):
                deleted += 1
    except (IOError, OSError) as error:
        toast.error('Could not delete every snapshot', str(error))
        return
    toast.success('Deleted %s' % cr.plural(deleted, 'snapshot'),
                  '%s left for this model.' % '{:,}'.format(len(entries) - deleted))


if cf.runner_active():
    toast.warning('These options need a window, so they cannot run under pynavis run',
                  'Shift+Click Snapshot on the ribbon instead.')
else:
    choice = forms.ask_options('What do you want to change?', [AUTOMATIC, REVIEW], TITLE)
    if choice == AUTOMATIC:
        automatic()
    elif choice == REVIEW:
        review()
