# -*- coding: utf-8 -*-
"""Turns Usage Analytics on or off, picks where it writes, and exports the data to Excel."""
import os

from pynavis import forms, toast

from namo import paths, ribbon, ui, usage, xlsx


def state_toast(saved):
    """One toast for what was saved, honest about a team folder that is not there."""
    title = 'Usage Analytics is %s' % ('on' if saved['enabled'] else 'off')
    if saved['shared'] and not paths.team_available():
        toast.warning(title, 'No team folder is reachable, so records stay on this computer. '
                             'Set the shared folder in Playground Settings.')
    else:
        toast.success(title, 'Records go to %s.' % ('the team folder' if saved['shared'] else 'this computer'))


def export(saved):
    """True when a workbook was written or the failure was reported; False on cancel."""
    rows = usage.read_rows(usage.report_folders(saved))
    if not rows:
        toast.info('Nothing to export yet', 'No usage has been recorded. Turn recording on and run a few tools.')
        return True
    path = forms.save_file(filter='Excel workbooks (*.xlsx)|*.xlsx', default_name='Playground usage.xlsx',
                           title='Export usage')
    if path is None:
        return False
    try:
        xlsx.write_simple(path, usage.xlsx_sheets(usage.aggregate(rows, ribbon.buttons())),
                          title='Playground usage')
    except (IOError, OSError) as error:
        toast.error('Could not write the workbook', 'Close it in Excel, then try again. %s' % error)
    else:
        toast.success('Exported %s run%s' % ('{:,}'.format(len(rows)), '' if len(rows) == 1 else 's'),
                      os.path.basename(path))
    return True


def run():
    settings = usage.load_settings()
    values = ui.form('Usage Analytics', [
        {'kind': 'check', 'key': 'enabled', 'label': 'Record which tools I run', 'default': settings['enabled']},
        {'kind': 'radio', 'key': 'shared', 'label': 'Write the records to',
         'options': [('This computer', False), ('The team folder (one file per person)', True)],
         'default': settings['shared'], 'fallback': None},
        {'kind': 'label', 'text': 'Only the time, user, computer, tool and duration are recorded, never document names.',
         'muted': True},
        {'kind': 'check', 'key': 'export', 'label': 'Export the records to Excel now', 'default': False},
    ], ok='Save')
    if values is None:
        return                                      # cancelled: say nothing
    saved = usage.save_settings({'enabled': values['enabled'], 'shared': values['shared'], 'asked': True})
    # The settings are saved either way; the export, when asked for, reports instead.
    if not (values['export'] and export(saved)):
        state_toast(saved)


if globals().get('__runner__'):
    toast.info('The Usage Analytics settings need the Navisworks window', 'They cannot open under pynavis run.')
else:
    run()
