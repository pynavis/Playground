# -*- coding: utf-8 -*-
"""Options for Quick Find: the fields it searches, how many results it lists, rebuild the index."""
from pynavis import script, toast

from namo import quickfind, ui

cfg = script.get_config(quickfind.DEFAULTS)
values = ui.form('Quick Find', [
    {'kind': 'multi', 'key': 'fields', 'label': 'Fields to search',
     'options': [(f['label'], f['key']) for f in quickfind.FIELDS], 'default': cfg['fields'],
     'hint': 'Name is always searched. Changing the fields rebuilds the index on the next search.'},
    {'kind': 'int', 'key': 'cap', 'label': 'Results listed', 'default': cfg['cap'], 'min': 20,
     'max': 2000, 'required': True},
    {'kind': 'int', 'key': 'budget', 'label': 'Elements indexed at most', 'default': cfg['budget'],
     'min': 10000, 'max': 5000000, 'required': True,
     'hint': 'Larger models are indexed from the start of the tree up to this many elements.'},
    {'kind': 'check', 'key': 'rebuild', 'label': 'Rebuild the index of this model now',
     'default': False},
], ok='Save', width=480)
if values is not None:
    cfg['fields'] = values['fields'] or ['name']
    cfg['cap'] = values['cap']
    cfg['budget'] = values['budget']
    script.save_config(cfg)
    detail = 'Searching %d fields, listing up to %s results.' % (
        len(quickfind.field_specs(cfg['fields'])), '{:,}'.format(cfg['cap']))
    if values['rebuild']:
        quickfind.forget()
        detail += ' The index is rebuilt on the next search.'
    toast.success('Saved', detail)
