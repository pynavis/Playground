# -*- coding: utf-8 -*-
"""Empties the pick list of this model."""
from pynavis import forms, toast

from namo import sel_pickorder

count = len(sel_pickorder.load())
if not count:
    toast.info('The pick list is already empty', 'Turn on Pick Order and click items to start one.')
elif count <= sel_pickorder.CONFIRM_CLEAR_OVER or forms.confirm(
        'Clear the pick list of %d items? This cannot be undone.' % count, 'Clear Picked'):
    sel_pickorder.clear()
    toast.success('Cleared %d picked %s' % (count, 'item' if count == 1 else 'items'))
