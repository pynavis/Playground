# -*- coding: utf-8 -*-
"""Options for Folder Watch: the folders to watch, how often to check, and whether to start with Navisworks."""
import os

from namo import folderwatch, ui

from pynavis import toast


def run():
    values = folderwatch.load_config()
    fields = [
        {'kind': 'textarea', 'key': 'folders', 'label': 'Folders to watch', 'rows': 4,
         'default': '\n'.join(values['folders']),
         'placeholder': 'One folder per line',
         'hint': 'Leave empty to watch the folders the appended models were loaded from.'},
        {'kind': 'int', 'key': 'interval', 'label': 'Check every', 'suffix': 's',
         'default': values['interval'], 'min': folderwatch.MIN_INTERVAL,
         'max': folderwatch.MAX_INTERVAL, 'required': True},
        {'kind': 'check', 'key': 'watch_sources', 'default': values['watch_sources'],
         'label': 'Also watch the native files (RVT, IFC, DWG) the models were made from'},
        {'kind': 'check', 'key': 'remember', 'default': values['remember'],
         'label': 'Start watching with Navisworks when it was on at the last close'},
    ]
    answer = ui.form('Folder Watch', fields, ok='Save')
    if answer is None:
        return
    values['folders'] = [line for line in answer['folders'].splitlines() if line.strip()]
    values['interval'] = answer['interval']
    values['watch_sources'] = answer['watch_sources']
    values['remember'] = answer['remember']
    missing = [f for f in values['folders'] if not os.path.isdir(f.strip().strip('"'))]
    try:
        folderwatch.save_config(values)
    except (IOError, OSError) as error:
        toast.error('Could not save the options', str(error))
        return
    if folderwatch.is_on():
        result = folderwatch.start(values)
        toast.success('Folder Watch options saved', result['detail'])
    elif missing:
        toast.warning('Folder Watch options saved',
                      '%s not found: %s' % ('Folder' if len(missing) == 1 else 'Folders', ', '.join(missing[:3])))
    else:
        toast.success('Folder Watch options saved', 'Used the next time you start watching.')


run()
