# -*- coding: utf-8 -*-
"""Plays a saved macro, or stops the one that is playing."""
from pynavis import forms, toast

from namo import macros

player = macros.playing()
if player is not None:
    if forms.confirm('Macro %s is playing (step %d of %d). Stop it?'
                     % (player.name, min(player.index + 1, len(player.steps)), len(player.steps)),
                     title='Play Macro'):
        player.stop()
else:
    names = macros.names()
    if not names:
        toast.info('There are no macros yet', 'Click Record Macro, run some commands, then click Stop Recording.')
    else:
        choices = [('%s  (%s)' % (name, macros.describe(macros.load(name) or {})), name) for name in names]
        name = forms.select_from_list(choices, title='Play Macro',
                                      prompt='Pick the macro to play. Dialogs inside its commands still ask you.')
        if name is not None:
            config = macros.load(name)
            if config is None or not config['steps']:
                toast.info('Macro %s has no steps' % name, 'Add steps in Manage Macros.')
            else:
                toast.info('Playing macro %s' % name, '%s. Click Play Macro again to stop it.' % macros.describe(config))
                macros.play(name, config)
