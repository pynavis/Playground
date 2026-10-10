# -*- coding: utf-8 -*-
"""Stale File Alert: every appended model's loaded file against its source file, as a
workbook (model, file times, age difference, status)."""
from namo import reports

TITLE = 'Stale File Alert'
HEADERS = ['Model', 'Loaded file', 'File time', 'Source file', 'Source time', 'Source newer by',
           'Status', 'Detail']


def default_config():
    return reports.base_config(tolerance_seconds=2.0)


def describe(config):
    return 'Every model: loaded file against its source file'


def table_rows(rows):
    """Rows for the output window and the workbook (pure)."""
    from namo import modelmgmt
    out = []
    for row in rows:
        delta = row.get('delta')
        newer = modelmgmt.format_age(delta) if delta is not None and delta > 0 else ''
        out.append([row['name'], row.get('file') or '', modelmgmt.format_time(row.get('cache_time')),
                    row.get('source') or '', modelmgmt.format_time(row.get('source_time')), newer,
                    row['status'], row.get('detail') or ''])
    return out


def run(config, doc=None, interactive=True, progress=None):
    from namo import modelmgmt, xlsx
    from pynavis._api import Application
    document = doc if doc is not None else Application.ActiveDocument
    if document is None or not modelmgmt.has_models(document):
        return reports.result('info', 'No models to check', 'Append models first.')
    if progress:
        progress(0.1, 'Reading file times')
    rows = modelmgmt.stale_rows(document, tolerance=float(config.get('tolerance_seconds') or 2.0))
    level, message, detail = modelmgmt.stale_summary(rows)
    path = reports.output_path(config, TITLE, 'xlsx')
    try:
        xlsx.write_simple(path, [{'name': 'Files', 'headers': HEADERS, 'rows': table_rows(rows),
                                  'widths': [28, 44, 17, 44, 17, 16, 18, 60]}], title=TITLE)
    except (IOError, OSError) as error:
        out = reports.result('error', 'Could not write the workbook',
                             '%s. Close it in Excel, then try again.' % error)
        out['rows'] = rows
        return out
    if progress:
        progress(1.0, 'Done')
    out = reports.result({'warning': 'warning', 'success': 'success'}.get(level, 'info'), message,
                         detail or '', paths=[path])
    out['rows'] = rows
    return out
