"""Sets how transparent Trade Ghost makes everything outside the focus, and whether it turns grey."""
from namo import look_ghost, ui
from pynavis import script, toast

cfg = look_ghost.normalize_config(script.get_config(look_ghost.DEFAULTS))
values = ui.form('Trade Ghost settings', look_ghost.config_fields(cfg), ok='Save')
if values is not None:                      # None means cancelled: say nothing
    cfg.update(values)
    cfg = look_ghost.normalize_config(cfg)
    script.save_config(cfg)
    toast.success('Saved', 'Trade Ghost fades the rest to %d%% transparent%s.'
                  % (cfg['transparency'], ' and grey' if cfg['grey'] else ''))
