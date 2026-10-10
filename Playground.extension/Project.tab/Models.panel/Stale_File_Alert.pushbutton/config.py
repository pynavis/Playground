# -*- coding: utf-8 -*-
"""Options for Stale File Alert: check whenever a model opens, and how much clock difference to ignore."""
from namo import hk_stalecheck, ui

from pynavis import settings, toast


def run():
    values = hk_stalecheck.load_config()
    fields = [
        {'kind': 'check', 'key': 'check_on_open', 'default': values['check_on_open'],
         'label': 'Check the files whenever a model opens, and warn only when something is out of date'},
        {'kind': 'number', 'key': 'tolerance_seconds', 'label': 'Ignore differences up to',
         'default': values['tolerance_seconds'], 'min': 0.0, 'max': 86400.0, 'suffix': 's',
         'hint': 'File servers round times; 2 s covers that. Raise it when clocks between servers drift.'},
    ]
    answer = ui.form('Stale File Alert', fields, ok='Save')
    if answer is None:
        return
    values.update(answer)
    if values['tolerance_seconds'] is None:
        values['tolerance_seconds'] = 2.0
    try:
        settings.save(hk_stalecheck.TOOL, values)
    except (IOError, OSError) as error:
        toast.error('Could not save the options', str(error))
        return
    toast.success('Stale File Alert options saved',
                  'Checks every model that opens.' if values['check_on_open'] else 'Checks only when you click.')


run()
