# -*- coding: utf-8 -*-
"""Makes a new pyNavis button in your own MyTools extension."""
import io

from pynavis import script, toast

from namo import buttonmaker, hotkeys, ribbon, ui

root = buttonmaker.user_root()
last = script.get_config({'template': 'selection', 'tab': buttonmaker.DEFAULT_TAB,
                          'panel': buttonmaker.DEFAULT_PANEL, 'icon': 'letters'})
cfg, _error = hotkeys.read_config(ribbon.user_config_path())
allow_bare = hotkeys.allow_bare_of(cfg or {})
taken = buttonmaker.taken_chords(ribbon.buttons())

if globals().get('__runner__'):
    toast.info('Button Maker needs the Navisworks window', 'It cannot open under pynavis run.')
else:
    values = ui.form('Button Maker', buttonmaker.form_fields(last, buttonmaker.existing_tabs(root)),
                     ok='Make button', width=520,
                     intro='The new button goes in %s, which pyNavis loads by itself.'
                           % buttonmaker.extension_folder(root),
                     validate=lambda v: buttonmaker.validate_spec(buttonmaker.spec_from(v), root, taken, allow_bare))
    if values is not None:
        spec = buttonmaker.spec_from(values)
        problem = None
        if spec['template'] == 'file':
            try:
                with io.open(spec['script_file'], encoding='utf-8-sig') as handle:
                    spec['script_text'] = handle.read()
            except (IOError, OSError, UnicodeDecodeError) as error:
                problem = str(error)
        if problem:
            toast.error('Could not read the script', problem)
        else:
            try:
                plan = buttonmaker.make(root, spec)
            except (IOError, OSError, ValueError) as error:
                toast.error('Could not make the button', str(error))
            else:
                script.save_config(buttonmaker.remembered(values))
                ribbon.reload()
                detail = '%s > %s. Edit it with Script Editor.' % (plan['tab'], plan['panel'])
                if spec.get('shortcut'):
                    detail = '%s > %s, shortcut %s. Edit it with Script Editor.' % (plan['tab'], plan['panel'],
                                                                                    spec['shortcut'])
                toast.success('Added %s' % ribbon.flatten_title(spec['title']), detail)
