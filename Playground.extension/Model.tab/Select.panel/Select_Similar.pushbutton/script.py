# -*- coding: utf-8 -*-
"""Selects every item that shares the ticked property values with the first selected item."""
from pynavis import script, toast

from namo import items, selecttools, variants

cfg = script.get_config(selecttools.SIMILAR_DEFAULTS)
selected = items.selected()

if not selected:
    toast.info('Nothing selected', 'Select one item, then run Select Similar again.')
else:
    element = items.object_of(selected[0])
    name = element.DisplayName or element.ClassDisplayName or 'the first selected item'
    rows = selecttools.similar_rows(variants.all_of(element))
    if not rows:
        toast.info('Nothing to match', '%s has no property a search can compare.' % name)
    else:
        checked = selecttools.default_checked(rows, cfg.get('checked'))
        choice = selecttools.similar_dialog(rows, checked, cfg.get('scope'),
                                            cfg.get('show_identity'), name)
        if choice is not None:
            script.save_config({'checked': choice['keys'], 'scope': choice['scope'],
                                'show_identity': choice['show_identity']})
            chosen = [r for r in rows if r['key'] in choice['keys']]
            found, dropped = selecttools.run_similar(element, chosen, choice['scope'])
            if found.Count:
                items.select(found)
            kept = [r for r in chosen if r not in dropped]
            level, message, detail = selecttools.similar_summary(found.Count, kept, choice['scope'],
                                                                 dropped)
            toast.show(level, message, detail)
