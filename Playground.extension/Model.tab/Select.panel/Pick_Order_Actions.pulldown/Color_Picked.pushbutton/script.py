# -*- coding: utf-8 -*-
"""Colors the picked items from light to strong blue along the pick order."""
from pynavis import toast

from namo import sel_pickorder

picks = sel_pickorder.load()
if not picks:
    toast.info('No picked items', 'Turn on Pick Order and click items in order first.')
else:
    found, missing = sel_pickorder.resolve()
    if not found:
        toast.warning('None of the picked items are in the model',
                      'They may have been removed or re-exported. Clear Picked starts a new list.')
    else:
        sel_pickorder.color(found)
        detail = 'Light blue is the first pick, strong blue the last. Ctrl+Z undoes it.'
        if missing:
            detail += ' %d picked items are no longer in the model.' % missing
        toast.success('Colored %d %s in pick order' % (len(found), 'item' if len(found) == 1 else 'items'),
                      detail)
