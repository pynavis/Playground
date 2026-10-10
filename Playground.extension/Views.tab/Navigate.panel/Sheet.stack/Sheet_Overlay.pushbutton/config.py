"""Places a DXF sheet: file, layers, elevation and position, by offset and rotation or by two points."""
from namo import sheetoverlay, vp_common
from pynavis import toast

document = vp_common.active_doc()
if not vp_common.has_models(document):
    toast.info('No model open', 'Open or append a model first.')
else:
    outcome = sheetoverlay.setup(document, sheetoverlay.saved(document))
    if outcome is not None:
        toast.show(outcome[0], outcome[1], outcome[2])
