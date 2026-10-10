# -*- coding: utf-8 -*-
"""Opens the unit converter: lengths, areas, volumes and masses as you type."""
from pynavis import toast
from pynavis._api import Application

from namo import converter

if globals().get('__runner__'):
    toast.info('The Unit Converter needs the Navisworks window', 'It cannot open under pynavis run.')
else:
    document = Application.ActiveDocument
    doc_units = None
    if document is not None and document.Models.Count:
        doc_units = str(document.Units)
    converter.show(doc_units)
