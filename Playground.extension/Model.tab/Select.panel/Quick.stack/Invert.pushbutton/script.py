# -*- coding: utf-8 -*-
"""Selects everything the current selection leaves out, leaving hidden items out."""
from pynavis import script, toast

from namo import items, selecttools

cfg = script.get_config(selecttools.INVERT_DEFAULTS)
had_selection = bool(items.selected())
kept, note = selecttools.invert(include_hidden=cfg['include_hidden'])

if not kept:
    if had_selection:
        toast.info('Nothing left to select', 'Everything visible is already selected.')
    else:
        toast.info('Nothing to select', 'The model has no visible items.')
else:
    items.select(kept)
    message = 'Inverted the selection' if had_selection else 'Selected everything visible'
    detail = '%s %s in the selection tree; hidden items %s.' % (
        '{:,}'.format(len(kept)), 'item' if len(kept) == 1 else 'items',
        'included' if cfg['include_hidden'] else 'left out')
    if note:
        toast.warning(message, '%s %s' % (detail, note))
    else:
        toast.success(message, detail)
