# -*- coding: utf-8 -*-
"""Options for Invert: leave hidden items out of the inverted selection, or include them."""
from pynavis import forms, script, toast

from namo import selecttools

cfg = script.get_config(selecttools.INVERT_DEFAULTS)
current = 'Include hidden items' if cfg['include_hidden'] else 'Leave hidden items out'
choice = forms.ask_options('When inverting the selection (now: %s):' % current.lower(),
                           ['Leave hidden items out', 'Include hidden items'], title='Invert')
if choice is not None:
    cfg['include_hidden'] = choice == 'Include hidden items'
    script.save_config(cfg)
    toast.success('Saved', 'Invert now %s.' % ('includes hidden items' if cfg['include_hidden']
                                               else 'leaves hidden items out'))
