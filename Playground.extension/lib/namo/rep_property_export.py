# -*- coding: utf-8 -*-
"""Property Export: chosen properties of the selected objects (or their geometry items)
as a styled Excel workbook or a CSV file, with identity columns in front."""

import csv
import io

from namo import data_common, propindex, reports

TITLE = 'Property Export'
IDENTITY = [('name', 'Name'), ('file', 'Source file'), ('element_id', 'Element ID'),
            ('unique_id', 'UniqueId'), ('ifc_guid', 'IFC GlobalId'), ('path', 'Tree path')]
IDENTITY_KEYS = [key for key, _label in IDENTITY]
IDENTITY_LABELS = dict(IDENTITY)
DEFAULT_IDENTITY = ['name', 'file', 'element_id', 'ifc_guid']


def default_config():
    return reports.base_config(properties=[], identity=list(DEFAULT_IDENTITY), scope='selection',
                               level='objects', format='xlsx', path='', budget=propindex.DEFAULT_BUDGET,
                               name_template='{file} - Properties - {date}')


def describe(config):
    count = len(config.get('properties') or [])
    return '%d %s, %s, %s' % (count, 'property' if count == 1 else 'properties',
                              propindex.SCOPE_NAMES.get(config.get('scope'), 'selection').lower(),
                              (config.get('format') or 'xlsx').upper())


def column_headers(identity, properties, units_by_column):
    """Header texts: identity labels, then 'Category > Property' with ' (unit)' for
    quantity columns."""
    headers = [IDENTITY_LABELS[key] for key in IDENTITY_KEYS if key in identity]
    for index, (category, prop) in enumerate(properties):
        text = propindex.pair_text(category, prop)
        unit = units_by_column.get(index)
        if unit:
            text += ' (%s)' % unit
        headers.append(text)
    return headers


def cell_for(kind, value, ctx):
    """An export cell: numbers stay numbers (quantities in report units), dates ISO,
    yes/no for booleans, text as shown."""
    if value is None:
        return None
    if kind == 'bool':
        return 'Yes' if value else 'No'
    if kind in propindex.QUANTITY_KINDS or kind in ('int', 'float'):
        return propindex.plain_value(kind, value, ctx)
    if kind in ('date', 'point'):
        return propindex.plain_value(kind, value, ctx)
    text = str(value)
    return text if text.strip() else None


def collect(item_list, identity, properties, reader, tick=None):
    """(rows, units_by_column): one row per item, identity cells then property cells."""
    from namo import inspect, items
    data = list(item_list)
    ticker = items.Ticker(tick, total=len(data), every=100)
    rows = []
    units_by_column = {}
    wanted = [key for key in IDENTITY_KEYS if key in identity]
    for item in data:
        row = []
        if wanted:
            record = inspect.id_record(item)
            row.extend(record.get(key) or '' for key in wanted)
        for index, (category, prop) in enumerate(properties):
            exists, kind, value = reader.one(item, category, prop)
            if not exists:
                row.append(None)
                continue
            if kind in propindex.QUANTITY_KINDS and index not in units_by_column:
                unit = propindex.quantity_value(kind, 1.0, reader.ctx)[1]
                units_by_column[index] = 'deg' if unit == 'deg' else unit
            row.append(cell_for(kind, value, reader.ctx))
        rows.append(row)
        ticker.step()
    ticker.finish()
    return rows, units_by_column


def write_xlsx(path, headers, rows, about):
    from namo import naming, xlsx
    wb = xlsx.Workbook(title=TITLE, author=naming.standard_values().get('user'))
    ws = wb.sheet('Properties')
    ws.columns([(h, None, None) for h in headers])
    for row in rows:
        ws.row(row)
    ws.autofilter()
    info = wb.sheet('About')
    info.columns([('Item', 24, 'bold'), ('Value', 80, None)], freeze=False)
    for label, value in about:
        info.row([label, value])
    return wb.save(path)


def write_csv(path, headers, rows):
    from namo import paths
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator='\r\n')
    writer.writerow(headers)
    for row in rows:
        writer.writerow(['' if cell is None else cell for cell in row])
    paths.atomic_write_bytes(path, b'\xef\xbb\xbf' + buffer.getvalue().encode('utf-8'))
    return path


def run(config, doc=None, interactive=True, progress=None):
    document = doc if doc is not None else data_common.active_doc()
    if not data_common.has_models(document):
        return reports.result('info', 'No model is open', 'Open or append a model, then export again.')
    properties = [tuple(pair) for pair in (config.get('properties') or []) if pair and len(pair) == 2]
    identity = [key for key in (config.get('identity') or []) if key in IDENTITY_LABELS]
    if not properties and not identity:
        return reports.result('warning', 'No columns chosen', 'Choose at least one property to export.')
    scope = config.get('scope') or 'selection'
    level = config.get('level') or 'objects'
    budget = int(config.get('budget') or propindex.DEFAULT_BUDGET)
    item_list = propindex.scope_items(scope, level, document,
                                      tick=data_common.stage(progress, 0.0, 0.0, 'Collecting items: %s'),
                                      budget=budget)
    if not item_list:
        message, detail = data_common.nothing_text(scope)
        return reports.result('info', message, detail)
    reader = propindex.Reader(document)
    rows, units_by_column = collect(item_list, identity, properties, reader,
                                    tick=data_common.stage(progress, 0.05, 0.85, 'Reading %s'))
    headers = column_headers(identity, properties, units_by_column)
    fmt = 'csv' if str(config.get('format') or '').lower() == 'csv' else 'xlsx'
    path = config.get('path') or reports.output_path(config, TITLE, fmt)
    scope_line = propindex.scope_text(scope, level, len(item_list), item_list.sampled)
    data_common.report(progress, 0.92, 'Writing the file')
    try:
        if fmt == 'csv':
            write_csv(path, headers, rows)
        else:
            from namo import naming
            values = naming.standard_values(document)
            about = [('Document', values.get('title') or ''), ('Exported', values['datetime'].strftime('%Y-%m-%d %H:%M')),
                     ('By', values.get('user') or ''), ('Rows', scope_line),
                     ('Properties', ', '.join(propindex.pair_text(c, p) for c, p in properties)),
                     ('Units', 'Quantities in %s, %s, %s' % (reader.ctx['length'], reader.ctx['area'],
                                                              reader.ctx['volume']))]
            write_xlsx(path, headers, rows, about)
    except (IOError, OSError) as error:
        return reports.result('error', 'Could not write the file', '%s %s' % (data_common.LOCKED, error))
    message = 'Exported %s %s' % ('{:,}'.format(len(rows)), 'row' if len(rows) == 1 else 'rows')
    out = reports.result('warning' if item_list.sampled else 'success', message, path, [path])
    out['sampled'] = bool(item_list.sampled)
    return out
