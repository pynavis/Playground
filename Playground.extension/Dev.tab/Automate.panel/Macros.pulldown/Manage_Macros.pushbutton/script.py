# -*- coding: utf-8 -*-
"""Edits, renames, deletes, exports and imports macros."""
from pynavis import toast
from pynavis._api import Application

from namo import macros, palette

document = Application.ActiveDocument


def commands():
    return palette.gather(document)[0]


if globals().get('__runner__'):
    toast.info('Manage Macros needs the Navisworks window', 'It cannot open under pynavis run.')
else:
    name = macros.manage(commands)
    if name is not None:
        config = macros.load(name)
        if macros.playing() is not None:
            # A second player would replace the first in the session, leaving it running
            # where Play Macro can no longer stop it.
            toast.info('A macro is already playing', 'Click Play Macro to stop it first.')
        elif config is not None and config['steps']:
            toast.info('Playing macro %s' % name, '%s. Click Play Macro again to stop it.' % macros.describe(config))
            macros.play(name, config)
