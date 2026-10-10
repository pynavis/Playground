# -*- coding: utf-8 -*-
"""Opens the Script Editor on the bundles of your own extensions."""
from pynavis import toast

from namo import editor

if globals().get('__runner__'):
    toast.info('The Script Editor needs the Navisworks window', 'It cannot open under pynavis run.')
else:
    editor.show()
