# -*- coding: utf-8 -*-
"""Removes the chosen kinds of data from the document after showing exactly how much will go."""
from pynavis import doc as navis_doc
from pynavis import forms, toast

from namo import preflight, progress, ui, wipe


def run():
    doc = navis_doc.get_doc()
    name = preflight.document_name(doc)
    found = progress.run('Model Wipe', lambda report: wipe.counts(doc, progress=report),
                         'Counting what is in the document')
    if found is progress.CANCELLED:
        return
    counts, approx = found
    values = ui.form('Model Wipe', wipe.form_fields(counts, approx, name), ok='Continue', width=520)
    if values is None:
        return
    chosen = values['chosen']
    if not chosen:
        toast.info('Nothing chosen', 'Tick what to remove, then Continue.')
        return
    if not forms.confirm(wipe.confirm_text(chosen, counts, approx, name), title='Model Wipe'):
        return
    result = wipe.execute(doc, chosen)
    level, message, detail = wipe.summary(result, counts, approx)
    if result['done']:
        # Say what was and was not written: only the open document changed.
        note = '%s on disk is unchanged until you save.' % name
        detail = ('%s %s' % (detail, note)) if detail else note
    toast.show(level, message, detail)


run()
