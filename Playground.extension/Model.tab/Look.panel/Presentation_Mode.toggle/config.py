"""Chooses what Presentation Mode changes besides minimizing the ribbon."""
from namo import presentation, ui
from pynavis import script, toast

options = presentation.normalize_options(script.get_config(presentation.DEFAULTS))
values = ui.form('Presentation Mode settings', presentation.option_fields(options), ok='Save')
if values is not None:                      # None means cancelled: say nothing
    options = presentation.normalize_options(values)
    script.save_config(options)
    toast.success('Saved', 'Takes effect the next time Presentation Mode starts.'
                  if presentation.is_on() else 'Click Presentation Mode to start presenting.')
