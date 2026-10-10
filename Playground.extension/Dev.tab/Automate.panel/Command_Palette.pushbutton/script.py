# -*- coding: utf-8 -*-
"""Finds any command, saved viewpoint or selection set by name and runs it."""
from pynavis import toast
from pynavis._api import Application

from namo import palette

if globals().get('__runner__'):
    toast.info('The Command Palette needs the Navisworks window', 'It cannot open under pynavis run.')
else:
    palette.open_palette(Application.ActiveDocument)
