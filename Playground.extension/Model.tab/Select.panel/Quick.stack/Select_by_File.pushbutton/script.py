# -*- coding: utf-8 -*-
"""Selects every item of the appended files you tick."""
from pynavis import script, toast

from namo import items, selecttools, ui

cfg = script.get_config(selecttools.FILE_DEFAULTS)
models = items.models()

if not models:
    toast.info('No models', 'Open or append a model first.')
else:
    counted = selecttools.count_models([m['root'] for m in models])
    counts = dict((m['index'], counted.get(position)) for position, m in enumerate(models))
    rows = selecttools.file_rows(models, counts)
    picked = ui.choose('Select by File', rows, ['File', 'Type', 'Units', 'Items'], multiselect=True,
                       checked=selecttools.checked_files(models, cfg['files']),
                       prompt='Tick the files whose items you want selected.', ok='Select',
                       width=640, height=480)
    if picked is not None:
        chosen = [m for m in models if m['index'] in picked]
        items.select([m['root'] for m in chosen], zoom=cfg['zoom'])
        names = [m['name'] for m in chosen]
        script.save_config({'files': names, 'zoom': cfg['zoom']})
        noun = 'file' if len(names) == 1 else 'files'
        toast.success('Selected %d %s' % (len(names), noun),
                      ', '.join(names) if len(names) <= 4 else '%s and %d more' % (
                          ', '.join(names[:3]), len(names) - 3))
