# -*- coding: utf-8 -*-
"""Makes a button in your own MyTools extension that plays a macro."""
from pynavis import forms, script, toast

from namo import buttonmaker, hotkeys, macros, ribbon, ui

names = macros.names()
if not names:
    toast.info('There are no macros yet', 'Record one with Record Macro first.')
else:
    macro = forms.select_from_list(names, title='Macro to Button', prompt='Pick the macro the new button plays.')
    if macro is not None:
        root = buttonmaker.user_root()
        last = script.get_config({'tab': buttonmaker.DEFAULT_TAB, 'panel': 'Macros', 'icon': 'play'})
        cfg, _error = hotkeys.read_config(ribbon.user_config_path())
        allow_bare = hotkeys.allow_bare_of(cfg or {})
        taken = buttonmaker.taken_chords(ribbon.buttons())
        fields = buttonmaker.form_fields(dict(last, title=macro), buttonmaker.existing_tabs(root), macro=True)
        values = ui.form('Macro to Button', fields, ok='Make button',
                         intro='The button plays the macro %s. It goes in your own MyTools extension.' % macro,
                         validate=lambda v: buttonmaker.validate_spec(buttonmaker.spec_from(v, macro), root,
                                                                      taken, allow_bare))
        if values is not None:
            spec = buttonmaker.spec_from(values, macro)
            spec['namo_lib'] = buttonmaker.namo_lib_folder()
            try:
                plan = buttonmaker.make(root, spec)
            except (IOError, OSError, ValueError) as error:
                toast.error('Could not make the button', str(error))
            else:
                script.save_config(buttonmaker.remembered(values))
                ribbon.reload()
                detail = '%s > %s, plays %s.' % (plan['tab'], plan['panel'], macro)
                if spec.get('shortcut'):
                    detail += ' Shortcut %s.' % spec['shortcut']
                toast.success('Added %s' % ribbon.flatten_title(spec['title']), detail)
