# -*- coding: utf-8 -*-
"""Measures every appended model: file sizes, items, geometry, primitives, fragments, extent and load time."""
from namo import mdl_output, mdl_stats, modelmgmt, progress, reports, rep_session_stats

from pynavis import app, output, toast


def run():
    doc = app.get_doc()
    if not modelmgmt.has_models(doc):
        toast.info('No models to measure', 'Append models first.')
        return
    config = modelmgmt.report_config(doc, 'Session stats', rep_session_stats.default_config())
    result = progress.run('Session Stats', lambda report: reports.run(
        'session_stats', config, doc=doc, interactive=True, progress=report), 'Counting')
    if result is progress.CANCELLED or result.get('cancelled'):
        return
    rows = result.get('rows') or []
    if rows:
        total = result['totals']
        html = [mdl_output.heading('Session stats', 2),
                mdl_output.kpis([('Models', total['models'], None), ('Items', total['items'], None),
                                 ('Geometry items', total['geometry'], None),
                                 ('Primitives', total['primitives'], None),
                                 ('Loaded files', modelmgmt.format_size(total['cache_bytes']), None)]),
                mdl_output.table(mdl_stats.HEADERS, mdl_stats.table_rows(rows), numeric=[5, 6, 7, 8])]
        if total['sampled']:
            html.append(mdl_output.note('Primitives and fragments of the largest models are estimated from '
                                        'a sample of their geometry items (see Note).'))
        output.print_html(''.join(html))
        ordered = sorted(rows, key=lambda r: -r['primitives'])[:20]
        output.chart_bar([r['name'] for r in ordered], [r['primitives'] for r in ordered],
                         'Primitives per model' + (' (largest 20)' if len(rows) > 20 else ''))
        for path in result.get('paths') or []:
            output.print_html(mdl_output.path_line('Workbook:', path))
    toast.show(result['level'], result['message'], result['detail'] or None)


run()
