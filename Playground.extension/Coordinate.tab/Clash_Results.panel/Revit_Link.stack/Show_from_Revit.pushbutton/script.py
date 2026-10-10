"""Selects and zooms to the elements Revit sent with the Playground Link button for pyRevit."""
import os

from pynavis import toast

from namo import items, progress, revitlink
from namo import clashset_common as common


def run():
    elements, sent, source, problem = revitlink.read_from_revit()
    if problem:
        toast.error('Could not use the link file', problem)
        return
    if not elements:
        toast.info('Nothing has been sent from Revit yet',
                   'In Revit, select elements and click Playground > Send to Navisworks.')
        return
    user = os.environ.get('USERNAME')
    found = progress.run('Finding elements from Revit', lambda report_to: revitlink.find_elements(
        elements, progress=report_to, user=user))
    if found is progress.CANCELLED:
        return
    hits, missing, notes = found
    age = revitlink.age_text(sent)
    origin = 'Sent %s from %s.' % (age, source or 'Revit') if age else ''
    if not hits:
        toast.warning('None of the %s from Revit are in this model' % common.plural(len(elements), 'element'),
                      ' '.join(p for p in (origin, notes[0] if notes else '') if p) or None)
        return
    items.select(hits, zoom=True)
    parts = [origin] if origin else []
    if missing:
        parts.append('Not found: %s.' % revitlink.short_list(missing))
    if notes:
        parts.append(notes[0])
    headline = 'Selected %s from Revit' % common.plural(len(hits), 'element')
    if missing:
        toast.warning(headline, ' '.join(parts))
    else:
        toast.success(headline, ' '.join(parts) or None)


run()
