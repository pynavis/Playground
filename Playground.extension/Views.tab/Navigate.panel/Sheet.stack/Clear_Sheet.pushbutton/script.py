"""Removes the DXF sheet overlay and its labels from the view."""
from namo import sheetoverlay
from pynavis import toast

if sheetoverlay.clear():
    toast.success('Sheet removed', 'Sheet Overlay shows it again.')
else:
    toast.info('No sheet on the view', 'Sheet Overlay draws one.')
