# -*- coding: utf-8 -*-
"""Saves the current selection as a selection set named from a template, in one click."""
from pynavis import script, toast

from namo import find_sets, items, naming, selecttools

cfg = script.get_config(selecttools.SAVE_DEFAULTS)
selected = items.selected()

if not selected:
    toast.info('Nothing selected', 'Select the items to save first.')
else:
    sample = selected[:200]
    values = selecttools.name_values([items.category(i) for i in sample],
                                     [items.model_name(i) for i in sample], len(selected),
                                     naming.standard_values())
    name, missing = selecttools.set_name(cfg['template'], values)
    folder = (cfg['folder'] or '').strip() or None
    _item, final = find_sets.create_set(name, selected, folder)
    where = 'In folder %s' % folder if folder else 'At the top of the Sets window'
    detail = '%s; %s items.' % (where, '{:,}'.format(len(selected)))
    if missing:
        toast.warning("Saved set '%s'" % final, '%s Unknown tokens kept as written: %s.' % (
            detail, ', '.join('{%s}' % m for m in missing)))
    else:
        toast.success("Saved set '%s'" % final, detail)
