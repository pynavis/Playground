# -*- coding: utf-8 -*-
"""Assigns and clears keyboard shortcuts for pyNavis buttons and Navisworks commands."""
from pynavis import toast

from namo import hotkeys, ribbon

if globals().get('__runner__'):
    toast.info('The Hotkey Manager needs the Navisworks window', 'It cannot open under pynavis run.')
else:
    state = hotkeys.load()
    if state['error']:
        toast.error('config.json cannot be read', state['error'])
    elif hotkeys.show(state):
        try:
            count, (added, changed, removed) = hotkeys.save(state)
        except (IOError, OSError, ValueError) as error:
            toast.error('The shortcuts were not saved', str(error))
        else:
            ribbon.reload()
            parts = []
            if count:
                parts.append('%d pyNavis button%s' % (count, '' if count == 1 else 's'))
            natives = added + changed + removed
            if natives:
                parts.append('%d Navisworks command%s' % (natives, '' if natives == 1 else 's'))
            toast.success('Shortcuts saved', 'Changed for %s. pyNavis reloaded.' % ' and '.join(parts))
