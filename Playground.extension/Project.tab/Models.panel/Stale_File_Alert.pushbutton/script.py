# -*- coding: utf-8 -*-
"""Compares every model's loaded file with its source file and lists what is out of date or missing."""
from namo import hk_stalecheck, mdl_output, modelmgmt, rep_stale_files

from pynavis import app, output, toast


def run():
    doc = app.get_doc()
    if not modelmgmt.has_models(doc):
        toast.info('No models to check', 'Append models first.')
        return
    config = hk_stalecheck.load_config()
    rows = modelmgmt.stale_rows(doc, tolerance=config['tolerance_seconds'])
    level, message, detail = modelmgmt.stale_summary(rows)
    late = sum(1 for r in rows if r['status'] == modelmgmt.OUT_OF_DATE)
    lost = sum(1 for r in rows if r['status'] in (modelmgmt.CACHE_NOT_FOUND, modelmgmt.CACHE_OFFLINE))
    elsewhere = sum(1 for r in rows if modelmgmt.STATUS_LEVEL.get(r['status']) == 'info')
    table = rep_stale_files.table_rows(rows)
    shown = [[mdl_output.chip(r['level'], r['status']), t[0], t[2], t[4], t[5], t[7]]
             for r, t in zip(rows, table)]
    html = [mdl_output.heading('Stale files', 2),
            mdl_output.kpis([('Models', len(rows), None), ('Out of date', late, 'warn' if late else None),
                             ('Not found', lost, 'fail' if lost else None),
                             ('No source here', elsewhere, None)]),
            mdl_output.table(['Status', 'Model', 'File time', 'Source time', 'Source newer by', 'Detail'],
                             shown, raw=set([0]), numeric=[])]
    if late:
        html.append(mdl_output.note('Refresh (Home > Refresh, or Refresh changed in Source Files) '
                                    'loads the newer source files.'))
    output.print_html(''.join(html))
    toast.show(level, message, detail)


run()
