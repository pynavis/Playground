# -*- coding: utf-8 -*-
"""Exports the issue and clash KPI tables (CSV and JSON) for Power BI into a folder."""
import os

from pynavis import forms, script, toast

from namo import issuestore, progress, rep_kpi_export, reports, ui

DEFAULTS = dict(rep_kpi_export.default_config(), fixed_folder='', last_folder='')


def run():
    me = script.bind()
    values = me.get_config(dict(DEFAULTS))
    doc = issuestore.active_doc()
    store = issuestore.for_doc(doc) if doc is not None else None
    if store is None or not store.saved:
        toast.info('Save the model first', 'The export is keyed by the model file; save it, then export.')
        return
    folder = str(values.get('fixed_folder') or '').strip()
    if not folder:
        start = values.get('last_folder') or os.path.dirname(store.doc_path)
        folder = forms.pick_folder('Folder for the KPI tables', start if os.path.isdir(start) else None)
        if folder is None:
            return
        values['last_folder'] = folder
        me.save_config(values)
    config = dict(values)
    config['folder'] = folder
    result = progress.run('KPI export', lambda report: reports.run(
        'kpi_export', config, doc=doc, interactive=True, progress=report))
    if result is progress.CANCELLED or result.get('cancelled'):
        return
    toast.show(result['level'], result['message'], result['detail'])
    if result['level'] in ('success', 'warning') and result['paths']:
        try:
            ui.show_in_explorer(result['paths'][0])
        except Exception:
            pass


run()
