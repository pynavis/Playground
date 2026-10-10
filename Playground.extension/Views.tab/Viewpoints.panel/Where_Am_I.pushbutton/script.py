"""Shows where the camera is: viewpoint, eye, heading, level, grid, lens, section, models, units and selection."""
from namo import vp_common, vp_whereami
from pynavis import forms, toast

document = vp_common.active_doc()
if not vp_common.has_models(document):
    toast.info('No model open', 'Open or append a model, then ask again.')
else:
    text = '\n'.join(vp_whereami.lines(vp_whereami.gather(document)))
    forms.alert(text, title='Where am I', copy=text)
