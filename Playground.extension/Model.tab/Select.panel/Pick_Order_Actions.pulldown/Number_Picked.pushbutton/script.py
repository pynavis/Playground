# -*- coding: utf-8 -*-
"""Writes Playground > Sequence = 1, 2, 3... onto the picked items in pick order."""
from pynavis import script, toast

from namo import progress, sel_pickorder, ui

cfg = script.get_config(sel_pickorder.NUMBER_DEFAULTS)
picks = sel_pickorder.load()

if not picks:
    toast.info('No picked items', 'Turn on Pick Order and click items in order first.')
else:
    found, missing = sel_pickorder.resolve()
    if not found:
        toast.warning('None of the picked items are in the model',
                      'They may have been removed or re-exported. Clear Picked starts a new list.')
    else:
        values = ui.form('Number Picked', [
            {'kind': 'label', 'text': 'Numbers the %d picked items in pick order on the Playground tab.'
                                      % len(found)},
            {'kind': 'text', 'key': 'property', 'label': 'Property name', 'default': cfg['property'],
             'required': True},
            {'kind': 'int', 'key': 'start', 'label': 'First number', 'default': cfg['start'],
             'required': True},
            {'kind': 'int', 'key': 'step', 'label': 'Step', 'default': cfg['step'], 'min': 1,
             'required': True},
            {'kind': 'text', 'key': 'prefix', 'label': 'Prefix', 'default': cfg['prefix'],
             'hint': 'Optional, for example P- gives P-1, P-2...'},
            {'kind': 'int', 'key': 'digits', 'label': 'Zero padding (digits)', 'default': cfg['digits'],
             'min': 0, 'max': 8,
             'hint': '3 gives 001, 002...; with padding or a prefix the values are text.'},
        ], ok='Number', width=440)
        if values is not None:
            for key in ('property', 'start', 'step', 'prefix', 'digits'):
                cfg[key] = values[key]
            cfg['property'] = cfg['property'].strip()
            cfg['digits'] = cfg['digits'] or 0
            script.save_config(cfg)
            numbers = sel_pickorder.sequence_values(len(found), cfg['start'], cfg['step'],
                                                    cfg['prefix'], cfg['digits'])
            if len(found) > 100:
                outcome = progress.run('Numbering picked items', lambda report: sel_pickorder.number(
                    found, numbers, cfg['property'], report))
            else:
                outcome = sel_pickorder.number(found, numbers, cfg['property'])
            if outcome is not progress.CANCELLED:
                written, errors = outcome
                detail = 'Playground > %s = %s to %s' % (cfg['property'], numbers[0], numbers[-1])
                if missing:
                    detail += '; %d picked items are no longer in the model' % missing
                if errors:
                    toast.warning('Numbered %d of %d items' % (written, len(found)), errors[0])
                else:
                    toast.success('Numbered %d %s' % (written, 'item' if written == 1 else 'items'),
                                  detail)
