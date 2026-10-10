"""Clears the last clash heatmap: removes its markers and puts the element colours back."""
from pynavis import toast

from namo import clashheat

markers, reset = clashheat.clear()
if not markers and not reset:
    toast.info('No heatmap to clear', 'Run Clash Heatmap first; this clears what it drew.')
else:
    parts = []
    if reset:
        parts.append('colours reset')
    if markers:
        parts.append('{:,} marker{} removed'.format(markers, '' if markers == 1 else 's'))
    toast.success('Cleared the clash heatmap', ', '.join(parts).capitalize() + '.')
