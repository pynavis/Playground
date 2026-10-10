"""Sets where Status Painter reads and writes the status, and the color of each status."""
from namo import colorize, look_status, ui
from pynavis import script, toast

cfg = look_status.normalize_config(script.get_config(look_status.DEFAULTS))
values = ui.form('Status Painter settings', look_status.config_fields(cfg), ok='Save', width=480)
if values is not None:                      # None means cancelled: say nothing
    cfg = look_status.config_from_form(values)
    script.save_config(cfg)
    painted = len([s for s in cfg['statuses'] if s[1]])
    toast.success('Saved', '%s painted, read from %s.' % (
        colorize.plural(painted, 'status', 'statuses'),
        colorize.property_label(cfg['category'], cfg['property'])))
