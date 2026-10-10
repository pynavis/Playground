# -*- coding: utf-8 -*-
"""Selects and zooms to the elements Navisworks sent with Playground Show in Revit."""
from pyrevit import revit, forms

from Autodesk.Revit import DB
from System.Collections.Generic import List

import playgroundlink as link

TITLE = 'Playground Link'


def run():
    doc = revit.doc
    uidoc = revit.uidoc
    if doc is None or uidoc is None:
        forms.alert('Open the model first, then click Show from Navisworks again.', title=TITLE)
        return
    data, problem = link.read_file(link.TO_REVIT)
    if data is None:
        forms.alert(problem or 'Nothing has been sent from Navisworks yet. In Navisworks, select '
                    'elements and click Playground > Show in Revit.', title=TITLE)
        return
    elements, problem = link.read_message(data, 'to-revit')
    if problem:
        forms.alert(problem, title=TITLE)
        return
    mine = [e for e in elements if link.matches_doc(e['file'], doc)]
    others = [e for e in elements if not link.matches_doc(e['file'], doc)]
    if not mine:
        files = sorted(set(e['file'] for e in others if e['file']))
        forms.alert('The %d element(s) from Navisworks are in %s, not in this model. Open that '
                    'model and click again.' % (len(elements), ', '.join(files) or 'another model'),
                    title=TITLE)
        return
    ids = []
    missing = []
    for element in mine:
        found = link.resolve(doc, element)
        if found is None:
            missing.append(element['element_id'] or element['unique_id'])
        elif found.Id not in ids:
            ids.append(found.Id)
    if not ids:
        forms.alert('None of the %d element(s) from Navisworks are in this model any more.'
                    % len(mine), title=TITLE)
        return
    collection = List[DB.ElementId](ids)
    uidoc.Selection.SetElementIds(collection)
    try:
        uidoc.ShowElements(collection)
    except Exception:
        pass
    details = []
    age = link.age_text(data.get('sent'))
    if age:
        details.append('Sent %s from %s.' % (age, data.get('from') or 'Navisworks'))
    if missing:
        details.append('Not found: %s.' % ', '.join(missing[:8]))
    if others:
        details.append('%d more are in other models.' % len(others))
    link.notify('Selected %d element(s) from Navisworks' % len(ids), ' '.join(details) or None,
                title=TITLE)


run()
