"""Removes the Coordinate Spotter markers from the view and starts the numbering again."""
from namo import spotter, vp_common
from pynavis import toast

count = spotter.clear()
if count:
    toast.success('Cleared %s' % vp_common.plural(count, 'spot'))
else:
    toast.info('No spots to clear', 'Coordinate Spotter drops them where you click.')
