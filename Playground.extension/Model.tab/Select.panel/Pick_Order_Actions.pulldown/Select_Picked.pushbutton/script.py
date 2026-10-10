# -*- coding: utf-8 -*-
"""Selects the items in the pick list."""
from pynavis import toast

from namo import items, sel_pickorder

picks = sel_pickorder.load()
if not picks:
    toast.info('No picked items', 'Turn on Pick Order and click items in order first.')
else:
    found, missing = sel_pickorder.resolve()
    if not found:
        toast.warning('None of the picked items are in the model',
                      'They may have been removed or re-exported. Clear Picked starts a new list.')
    else:
        items.select(found)
        noun = 'item' if len(found) == 1 else 'items'
        if missing:
            toast.warning('Selected %d picked %s' % (len(found), noun),
                          '%d no longer in the model.' % missing)
        else:
            toast.success('Selected %d picked %s' % (len(found), noun))
