# -*- coding: utf-8 -*-
"""Options for Save as Set: the name template and the folder the sets go in."""
from pynavis import script, toast

from namo import selecttools, ui

cfg = script.get_config(selecttools.SAVE_DEFAULTS)
values = ui.form('Save as Set', [
    {'kind': 'text', 'key': 'template', 'label': 'Set name', 'default': cfg['template'],
     'required': True,
     'hint': 'Tokens: {category} (most common), {count}, {date}, {time}, {user}, {file}, {model}. '
             'Dates take a format: {date:%d %b %Y}.'},
    {'kind': 'text', 'key': 'folder', 'label': 'Folder', 'default': cfg['folder'],
     'hint': 'Created when missing; use / for subfolders. Leave blank for the top level.'},
], ok='Save', width=520)
if values is not None:
    cfg['template'] = values['template'].strip() or selecttools.SAVE_DEFAULTS['template']
    cfg['folder'] = values['folder'].strip()
    script.save_config(cfg)
    toast.success('Saved', 'Sets will be named %s.' % cfg['template'])
