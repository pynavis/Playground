"""Picks a background preset, or a custom color or gradient, from a list."""
from namo import look_tools, ui
from pynavis import doc as nwdoc
from pynavis import script, toast

DEFAULTS = {'choice': look_tools.BACKGROUNDS[0]['name'], 'top': 'FFFFFF', 'bottom': 'C9D1DB'}

cfg = script.get_config(DEFAULTS)
values = ui.form('Background', look_tools.background_fields(cfg), ok='Apply')
if values is not None:                      # None means cancelled: say nothing
    spec = look_tools.background_from_form(values)
    if spec is None:
        toast.error('That background cannot be shown', 'Pick a preset, or a valid color like 4E79A7.')
    else:
        cfg.update(values)
        script.save_config(cfg)
        try:
            look_tools.set_background(spec, nwdoc.get_doc())
        except Exception as error:
            toast.error('Could not change the background', str(error))
        else:
            look_tools.remember_background(look_tools.match_background(spec))
            toast.success('Background: %s' % spec['name'])
