# -*- coding: utf-8 -*-
"""Starts recording the pyNavis commands you run, or stops and saves them as a macro."""
from pynavis import forms, script, toast

from namo import macros, naming

if not macros.is_recording():
    macros.start_recording()
    script.set_toggle_state(True)
    toast.info('Recording a macro',
               'Run pyNavis commands, then click Stop Recording. Navisworks commands record '
               'when you run them from the Command Palette.')
else:
    steps = macros.stop_recording()
    script.set_toggle_state(False)
    if not steps:
        toast.info('Nothing was recorded', 'Click Record Macro, run some commands, then stop.')
    else:
        name = forms.ask_string('Name for this macro (%d step%s):' % (len(steps), '' if len(steps) == 1 else 's'),
                                default=naming.unique('Macro', macros.names()), title='Save macro')
        if name is not None:
            name = name.strip()
            replace = True
            if not name:
                toast.warning('The macro was not saved', 'It needs a name. Save it from Manage Macros.')
                replace = False
            elif macros.load(name) is not None:
                replace = forms.confirm('A macro called %s exists. Replace it?' % name, title='Save macro')
            if name and replace:
                try:
                    stored = macros.save(name, {'steps': steps})
                except (IOError, OSError) as error:
                    toast.error('Could not save the macro', str(error))
                else:
                    macros.forget_unsaved()
                    toast.success('Saved macro %s' % stored,
                                  '%d step%s. Play it from the Macros menu.' % (len(steps), '' if len(steps) == 1 else 's'))
