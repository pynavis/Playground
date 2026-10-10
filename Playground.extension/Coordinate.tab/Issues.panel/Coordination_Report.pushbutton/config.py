# -*- coding: utf-8 -*-
"""Options for the Coordination Report: formats, thumbnails, trades, folder and file name."""
from pynavis import script, toast

from namo import config as namo_config
from namo import rep_coordination, ui

values = script.get_config(rep_coordination.default_config())
trades = namo_config.get('trades') or []
fields = [
    {'kind': 'multi', 'key': 'formats', 'label': 'Write',
     'options': [('HTML page', 'html'), ('Excel workbook', 'xlsx')],
     'default': values.get('formats') or ['html', 'xlsx']},
    {'kind': 'check', 'key': 'thumbnails', 'label': 'Snapshot thumbnails in each trade section',
     'default': bool(values.get('thumbnails'))},
    {'kind': 'int', 'key': 'max_thumbnails', 'label': 'Thumbnails, at most', 'min': 0, 'max': 2000,
     'default': values.get('max_thumbnails'), 'enabled_if': ('thumbnails', True)},
    {'kind': 'multi', 'key': 'trades', 'label': 'Trades (none ticked: every trade)',
     'options': trades, 'default': [t for t in values.get('trades') or [] if t in trades]},
    {'kind': 'check', 'key': 'include_void', 'label': 'Include void issues',
     'default': bool(values.get('include_void'))},
    {'kind': 'folder', 'key': 'folder', 'label': 'Folder', 'default': values.get('folder') or '',
     'hint': 'Blank: the model\'s own folder.'},
    {'kind': 'text', 'key': 'name_template', 'label': 'File name',
     'default': values.get('name_template') or '{file} - Coordination report - {date}',
     'hint': 'Tokens: {file} {date} {project} {user}.'},
    {'kind': 'check', 'key': 'open_after', 'label': 'Open the page when it is written',
     'default': bool(values.get('open_after'))},
]


def check(answers):
    if not answers['formats']:
        return {'formats': 'Tick at least one format.'}
    if not answers['name_template'].strip():
        return {'name_template': 'Give the file a name.'}
    return None


answers = ui.form('Coordination report options', fields, ok='Save', width=520, validate=check)
if answers is not None:
    values.update(answers)
    script.save_config(values)
    toast.success('Saved Coordination Report options', rep_coordination.describe(values))
