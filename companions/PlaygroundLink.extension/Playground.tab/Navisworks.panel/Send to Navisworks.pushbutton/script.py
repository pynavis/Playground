# -*- coding: utf-8 -*-
"""Sends the selected Revit elements to Navisworks, where Playground Show from Revit selects them."""
from pyrevit import revit, forms

from Autodesk.Revit import DB

import playgroundlink as link

TITLE = 'Playground Link'


def run():
    doc = revit.doc
    uidoc = revit.uidoc
    if doc is None or uidoc is None:
        forms.alert('Open the model first.', title=TITLE)
        return
    ids = list(uidoc.Selection.GetElementIds())
    if not ids:
        forms.alert('Select elements first, then click Send to Navisworks.', title=TITLE)
        return
    elements = []
    linked = 0
    for element_id in ids:
        element = doc.GetElement(element_id)
        if element is None:
            continue
        if isinstance(element, DB.RevitLinkInstance):
            linked += 1
            continue
        elements.append(link.describe(element, doc))
    if not elements:
        forms.alert('Only linked models are selected. Open the linked model itself to send its '
                    'elements.', title=TITLE)
        return
    data = link.message('to-navisworks', doc.Title, elements)
    try:
        link.write_file(link.TO_NAVISWORKS, data)
    except Exception as error:
        forms.alert('Could not write the link file: %s' % error, title=TITLE)
        return
    detail = 'In Navisworks, click Playground > Show from Revit.'
    if linked:
        detail = '%d linked model(s) were left out. %s' % (linked, detail)
    link.notify('Sent %d element(s) to Navisworks' % len(elements), detail, title=TITLE)


run()
