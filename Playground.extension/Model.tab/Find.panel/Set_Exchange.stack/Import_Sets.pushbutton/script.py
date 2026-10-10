# -*- coding: utf-8 -*-
"""Recreates sets and folders from a Playground XML file and reports what each set found."""
from pynavis import forms, output, toast, viewpoints
from pynavis._api import Application

from namo import find_sets, paths, progress, setexchange, ui

document = Application.ActiveDocument


def resolve_all(chosen, report):
    """[found items or None] per chosen set (None for search sets)."""
    out = []
    statics = [n for _f, n in chosen if n['kind'] == 'static']
    done = 0
    for _folder, node in chosen:
        if node['kind'] != 'static':
            out.append(None)
            continue
        done += 1

        def part(fraction, label, _done=done):
            report((_done - 1 + fraction) / float(len(statics)), "%s: %s" % (node['name'], label))
        found, _count = setexchange.resolve_refs(node.get('items') or [], document, part)
        out.append(found)
    return out


def create_all(chosen, found_lists, create_empty):
    """[(set, kind, result text, ok)] after writing every set in one undo step."""
    results = []
    with viewpoints.transaction('Import sets', document):
        for (folder, node), found in zip(chosen, found_lists):
            name = node.get('name') or 'Imported set'
            where = folder or None
            try:
                if node['kind'] == 'search':
                    if setexchange.has_raw(node):
                        results.append((name, 'Search', 'Not imported: a condition Navisworks did not '
                                        'export readably', False))
                        continue
                    final = setexchange.create_search(name, node, where, document)
                    results.append((final, 'Search', 'Created', True))
                else:
                    total = len(node.get('items') or [])
                    if not found and total and not create_empty:
                        results.append((name, 'Static', 'Skipped: none of its %d items found' % total, False))
                        continue
                    final = setexchange.create_static(name, found or [], where, document)
                    text = 'Created with %s of %s items' % ('{:,}'.format(len(found or [])),
                                                            '{:,}'.format(total))
                    results.append((final, 'Static', text, len(found or []) == total))
            except Exception as error:
                results.append((name, node['kind'].capitalize(), 'Not imported: %s' % error, False))
    return results


path = forms.open_file('Playground sets (*.xml)|*.xml|All files (*.*)|*.*', 'Import sets')
if path is not None:
    text = paths.read_text(path)
    try:
        if text is None:
            raise ValueError('The file could not be read.')
        meta, tree = setexchange.read_xml(text)
    except ValueError as error:
        toast.error('Could not read the sets file', str(error))
    else:
        flat = setexchange.flatten(tree)
        if not flat:
            toast.info('No sets in the file', path)
        else:
            picked = ui.choose('Import sets', setexchange.preview_rows(flat), ['Folder', 'Set', 'Kind', 'Holds'],
                               multiselect=True, checked=list(range(len(flat))), ok='Import', width=760,
                               prompt='From %s, exported %s by %s. Tick the sets to import.' % (
                                   meta.get('document') or 'another model',
                                   (meta.get('exported') or '?').replace('T', ' '), meta.get('user') or '?'))
            if picked is not None:
                chosen = [flat[i] for i in picked]
                if any(n['kind'] == 'static' for _f, n in chosen):
                    found_lists = progress.run('Finding the items of static sets',
                                               lambda report: resolve_all(chosen, report))
                else:
                    found_lists = [None] * len(chosen)
                if found_lists is not progress.CANCELLED:
                    empty = [n['name'] for (f, n), found in zip(chosen, found_lists)
                             if n['kind'] == 'static' and not found and n.get('items')]
                    create_empty = False
                    go = True
                    if empty:
                        answer = forms.ask_options(
                            '%d static %s found none of %s items in this model (%s).' % (
                                len(empty), 'set' if len(empty) == 1 else 'sets',
                                'its' if len(empty) == 1 else 'their', ', '.join(empty[:3]) +
                                (' and more' if len(empty) > 3 else '')),
                            ['Skip them', 'Create them empty'], title='Import sets')
                        go = answer is not None
                        create_empty = answer == 'Create them empty'
                    if go:
                        results = create_all(chosen, found_lists, create_empty)
                        written = [r for r in results if not r[2].startswith(('Skipped', 'Not imported'))]
                        partial = [r for r in results if not r[3]]
                        if partial or any(n['kind'] == 'static' for _f, n in chosen):
                            output.print_md('## Imported sets from %s' % path)
                            output.print_table([[r[0], r[1], r[2]] for r in results], ['Set', 'Kind', 'Result'])
                        message = 'Imported %d of %d sets' % (len(written), len(results))
                        detail = 'Every set and item was found.' if not partial else \
                            '%d not complete; see the output window.' % len(partial)
                        if not written:
                            toast.error('No sets were imported', detail)
                        elif partial:
                            toast.warning(message, detail)
                        else:
                            toast.success(message, detail)
