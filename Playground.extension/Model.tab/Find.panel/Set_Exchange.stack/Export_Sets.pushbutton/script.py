# -*- coding: utf-8 -*-
"""Writes chosen sets to a Playground XML file: search sets as conditions, static sets as item references."""
import os

from pynavis import forms, toast
from pynavis._api import Application

from namo import find_sets, naming, paths, progress, setexchange, ui

document = Application.ActiveDocument


def default_path():
    name = naming.render('{file} - Sets - {date}', naming.standard_values())[0]
    name = naming.sanitize(name.strip(' -') or 'Sets', for_file=True)
    folder = os.path.dirname(document.FileName or '')
    if not folder or not os.path.isdir(folder):
        folder = os.path.join(os.path.expanduser('~'), 'Documents')
    return os.path.join(folder, name + '.xml')


rows = setexchange.export_rows(document)
if not rows:
    toast.info('No sets to export', 'This model has no selection or search sets.')
else:
    table = [{'value': i, 'cells': [find_sets.plain_folder(r['folder']), r['name'],
                                    'Search' if r.get('has_search') else 'Static']}
             for i, r in enumerate(rows)]
    picked = ui.choose('Export sets', table, ['Folder', 'Set', 'Kind'], multiselect=True,
                       checked=list(range(len(rows))), ok='Next', width=640,
                       prompt='Tick the sets to export. Folders come along with their sets.')
    if picked is not None:
        path = forms.save_file('Playground sets (*.xml)|*.xml', default_path(), 'Export sets')
        if path is not None:
            chosen = [rows[i] for i in picked]
            outcome = progress.run('Exporting sets', lambda report: setexchange.collect(
                chosen, document, report))
            if outcome is not progress.CANCELLED:
                meta, tree = outcome
                try:
                    paths.atomic_write_text(path, setexchange.write_xml(meta, tree))
                except (IOError, OSError) as error:
                    toast.error('Could not write the file', str(error))
                else:
                    search, static, count = setexchange.describe_tree(tree)
                    parts = ['%d search %s' % (search, 'set' if search == 1 else 'sets')]
                    if static:
                        parts.append('%d static %s holding %s items' % (
                            static, 'set' if static == 1 else 'sets', '{:,}'.format(count)))
                    toast.success('Exported %d %s' % (search + static, 'set' if search + static == 1 else 'sets'),
                                  '%s. %s' % (' and '.join(parts), path))
