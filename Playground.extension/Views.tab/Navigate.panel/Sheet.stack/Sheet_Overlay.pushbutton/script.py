"""Draws a DXF sheet over the model at a level; once placed, one click shows it again."""
import os

from namo import sheetoverlay, vp_common
from pynavis import toast

document = vp_common.active_doc()
if not vp_common.has_models(document):
    toast.info('No model open', 'Open or append a model, then run Sheet Overlay again.')
else:
    placed = sheetoverlay.saved(document)
    if placed is not None and os.path.isfile(str(placed['file'])):
        outcome = sheetoverlay.show(document, placed)
    else:
        outcome = sheetoverlay.setup(document, placed)
    if outcome is not None:
        toast.show(outcome[0], outcome[1], outcome[2])
