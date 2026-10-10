# -*- coding: utf-8 -*-
"""Options for Selection History: record selections, record clearing, clear the history."""
from pynavis import toast

from namo import sel_history, ui

current = sel_history.settings(refresh=True)
values = ui.form('Selection History', [
    {'kind': 'check', 'key': 'enabled', 'label': 'Record selections as I make them',
     'default': current['enabled']},
    {'kind': 'check', 'key': 'record_empty', 'label': 'Also record clearing the selection',
     'default': current['record_empty']},
    {'kind': 'separator'},
    {'kind': 'check', 'key': 'clear', 'label': "Clear this model's history now", 'default': False},
], ok='Save', width=440)
if values is not None:
    saved = sel_history.save_settings(values)
    dropped = sel_history.clear() if values['clear'] else None
    detail = 'Recording is %s.' % ('on' if saved['enabled'] else 'off')
    if dropped is not None:
        detail += ' Cleared %d recorded %s.' % (dropped, 'selection' if dropped == 1 else 'selections')
    toast.success('Saved', detail)
