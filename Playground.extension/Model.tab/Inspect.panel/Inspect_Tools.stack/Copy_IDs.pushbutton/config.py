# -*- coding: utf-8 -*-
"""Chooses which identifier columns Copy IDs puts on the clipboard."""
from pynavis import script, toast

from namo import inspect, ui

DEFAULTS = {'columns': list(inspect.ID_KEYS)}


def run():
    if ui.is_runner():
        toast.info('Settings need the Navisworks window', 'They cannot open under pynavis run.')
        return
    values = script.get_config(DEFAULTS)
    rows = [{'cells': [label], 'value': key} for key, label in inspect.ID_COLUMNS]
    picked = ui.choose('Copy IDs columns', rows, ['Column'], multiselect=True,
                       checked=values.get('columns') or list(inspect.ID_KEYS),
                       prompt='Tick the columns Copy IDs puts on the clipboard, in this order.', ok='Save',
                       width=420, height=420)
    if picked is None:
        return
    values['columns'] = picked
    script.save_config(values)
    toast.success('Copy IDs copies %d %s' % (len(picked), 'column' if len(picked) == 1 else 'columns'),
                  ', '.join(inspect.ID_LABELS[key] for key in picked))


run()
