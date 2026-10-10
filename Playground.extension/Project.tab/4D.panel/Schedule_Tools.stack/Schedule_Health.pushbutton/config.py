# -*- coding: utf-8 -*-
"""Options for Schedule Health: the coverage walk and the Not scheduled set."""
from pynavis import script, toast

from namo import ui

DEFAULTS = {'coverage': True, 'create_set': True}


def run():
    if ui.is_runner():
        return
    values = script.get_config(DEFAULTS)
    fields = [
        {'kind': 'check', 'key': 'coverage', 'label': 'Check coverage: objects in no task and in several tasks',
         'default': bool(values.get('coverage', True)),
         'hint': 'Reads every task\'s items and every object in the model; slower on big models.'},
        {'kind': 'check', 'key': 'create_set', 'label': 'Save objects in no task as the set Playground/Not scheduled',
         'default': bool(values.get('create_set', True)), 'enabled_if': ('coverage', True)},
    ]
    answer = ui.form('Schedule Health options', fields, ok='Save')
    if answer is None:
        return
    values.update({'coverage': bool(answer['coverage']), 'create_set': bool(answer['create_set'])})
    script.save_config(values)
    toast.success('Saved the Schedule Health options',
                  'Coverage on.' if values['coverage'] else 'Coverage off: dates and attachments only.')


run()
