# -*- coding: utf-8 -*-
"""Options for Select by File: zoom to the files after selecting them."""
from pynavis import script, toast

from namo import selecttools, ui

cfg = script.get_config(selecttools.FILE_DEFAULTS)
values = ui.form('Select by File', [
    {'kind': 'check', 'key': 'zoom', 'label': 'Zoom to the files after selecting them',
     'default': cfg['zoom']},
], ok='Save')
if values is not None:
    cfg['zoom'] = values['zoom']
    script.save_config(cfg)
    toast.success('Saved', 'Select by File %s.' % ('zooms to the files' if cfg['zoom']
                                                    else 'leaves the view where it is'))
