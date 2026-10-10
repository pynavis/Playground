"""Sets the cut height, the slab view and the plan camera shared by Level Sectioner, Level Up and Level Down."""
from namo import levels, ui, vp_common
from pynavis import toast

document = vp_common.active_doc()
units = str(document.Units) if document is not None else 'Meters'
cfg = levels.load_settings()
values = ui.form('Level Sectioner settings', levels.settings_fields(cfg, units), ok='Save', units=units)
if values is not None:                      # None means cancelled: say nothing
    m = vp_common.to_meters_factor(units)
    cfg.update({'cut_height_m': values['cut'] * m, 'slab': values['slab'], 'plan': values['plan']})
    if values.get('depth') is not None:
        cfg['slab_depth_m'] = values['depth'] * m
    try:
        levels.save_settings(cfg)
    except (IOError, OSError) as error:
        toast.error('Could not save the settings', str(error))
    else:
        toast.success('Saved', 'Cut %s above the level. Level Up and Level Down use it too.'
                      % vp_common.length_text(values['cut'], units))
