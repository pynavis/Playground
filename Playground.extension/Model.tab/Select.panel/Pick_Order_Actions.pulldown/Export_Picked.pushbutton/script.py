# -*- coding: utf-8 -*-
"""Writes the pick list to Excel or CSV with ids, source file and centre point."""
import os

from pynavis import forms, toast

from namo import naming, paths, progress, sel_pickorder, units, xlsx

picks = sel_pickorder.load()


def default_path(document):
    name = naming.render('{file} - Pick order - {date}', naming.standard_values())[0]
    name = naming.sanitize(name.strip(' -') or 'Pick order', for_file=True)
    folder = os.path.dirname(document.FileName or '')
    if not folder or not os.path.isdir(folder):
        folder = os.path.join(os.path.expanduser('~'), 'Documents')
    return os.path.join(folder, name + '.xlsx')


def build(found, report):
    rows = []
    for index, item in enumerate(found):
        rows.append(sel_pickorder.export_row(index + 1, sel_pickorder.record_for(item)))
        if index % 50 == 0:
            report(float(index) / max(1, len(found)), 'Reading %d of %d items' % (index, len(found)))
    return rows


if not picks:
    toast.info('No picked items', 'Turn on Pick Order and click items in order first.')
else:
    from pynavis._api import Application
    document = Application.ActiveDocument
    found, missing = sel_pickorder.resolve()
    if not found:
        toast.warning('None of the picked items are in the model',
                      'They may have been removed or re-exported. Clear Picked starts a new list.')
    else:
        path = forms.save_file('Excel workbook (*.xlsx)|*.xlsx|CSV file (*.csv)|*.csv',
                               default_path(document), 'Export picked items')
        if path is not None:
            rows = progress.run('Exporting picked items', lambda report: build(found, report))
            if rows is not progress.CANCELLED:
                headers = sel_pickorder.export_headers(units.doc_unit_symbol(str(document.Units)))
                try:
                    if path.lower().endswith('.csv'):
                        paths.atomic_write_text(path, sel_pickorder.csv_text(headers, rows), 'utf-8-sig')
                    else:
                        xlsx.write_simple(path, [{'name': 'Pick order', 'headers': headers,
                                                  'rows': rows}], title='Pick order')
                except (IOError, OSError) as error:
                    toast.error('Could not write the file', 'Close it in Excel, then try again. %s' % error)
                else:
                    detail = path
                    if missing:
                        detail = '%s (%d picked items are no longer in the model)' % (path, missing)
                    toast.success('Exported %d picked %s' % (len(rows), 'item' if len(rows) == 1 else 'items'),
                                  detail)
