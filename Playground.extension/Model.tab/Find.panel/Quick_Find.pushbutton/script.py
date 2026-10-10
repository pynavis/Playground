# -*- coding: utf-8 -*-
"""Finds any element by name, Element ID, category, type, mark or level as you type."""
from pynavis import script, toast
from pynavis._api import Application

from namo import items, progress, quickfind, session

cfg = script.get_config(quickfind.DEFAULTS)
document = Application.ActiveDocument


def act(index, result):
    rows = result['rows']
    if result['action'] == 'all' and len(rows) > 2000:
        outcome = progress.run('Selecting %s results' % '{:,}'.format(len(rows)),
                               lambda report: quickfind.resolve(index, rows, document))
        if outcome is progress.CANCELLED:
            return
        found, missing = outcome
    else:
        found, missing = quickfind.resolve(index, rows, document)
    stale = 'Shift+Click Quick Find and rebuild the index if the model changed.'
    if not found:
        toast.warning('That element is no longer in the model' if len(rows) == 1 else
                      'Those elements are no longer in the model', stale)
        return
    shown = index.display(rows[0], result['query'])['name']
    if result['action'] == 'select':
        items.select(found, zoom=True, doc=document)
        toast.success('Selected %s' % shown, index.display(rows[0], result['query'])['detail'] or None)
    elif result['action'] == 'add':
        document.CurrentSelection.AddRange(items.collection(found))
        toast.success('Added %s to the selection' % shown)
    else:
        items.select(found, doc=document)
        message = 'Selected %s %s' % ('{:,}'.format(len(found)), 'result' if len(found) == 1 else 'results')
        detail = "Every element matching '%s'." % result['query']
        if missing:
            toast.warning(message, '%s %d could not be found: %s' % (detail, missing, stale))
        else:
            toast.success(message, detail)


if document is None or document.Models.Count == 0:
    toast.info('Nothing to search', 'Open or append a model first.')
else:
    index = quickfind.cached(document, cfg)
    if index is None:
        built = progress.run('Indexing the model for Quick Find',
                             lambda report: quickfind.build(document, cfg, report),
                             'Finding elements')
        index = None if built is progress.CANCELLED else built
    if index is not None:
        if not len(index):
            toast.info('Nothing to search', 'The model has no elements with geometry.')
        else:
            last = session.get('quickfind', 'last_query', '')
            result = quickfind.dialog(index, cfg['cap'], last)
            if result is not None:
                session.set('quickfind', 'last_query', result['query'])
                act(index, result)
