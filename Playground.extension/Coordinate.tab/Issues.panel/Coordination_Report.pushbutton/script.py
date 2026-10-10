# -*- coding: utf-8 -*-
"""Writes the coordination report (HTML and Excel) from the issue register and opens it."""
import os

from pynavis import script, toast

from namo import issuestore, progress, rep_coordination, reports, ui


def run():
    me = script.bind()
    config = me.get_config(rep_coordination.default_config())
    doc = issuestore.active_doc()
    store = issuestore.for_doc(doc) if doc is not None else None
    if not str(config.get('folder') or '').strip() and store is not None and store.saved:
        config['folder'] = os.path.dirname(store.doc_path)
    result = progress.run('Coordination report', lambda report: reports.run(
        'coordination', config, doc=doc, interactive=True, progress=report))
    if result is progress.CANCELLED or result.get('cancelled'):
        return
    toast.show(result['level'], result['message'], result['detail'])
    if result['level'] == 'success' and config.get('open_after') and result['paths']:
        try:
            ui.open_path(result['paths'][0])
        except Exception as error:
            toast.warning('The report was written but could not be opened', str(error))


run()
