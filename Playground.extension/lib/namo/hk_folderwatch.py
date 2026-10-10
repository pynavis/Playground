# -*- coding: utf-8 -*-
"""Folder Watch handler: restores watching at startup (only when its 'remember' option
is on and watching was on at the last close), takes a new baseline when a document
opens, and stops the timer when Navisworks closes (keeping 'active' for next time)."""


def handle(name, event):
    from namo import folderwatch
    if name == 'doc-opened':
        if folderwatch.is_on():
            folderwatch.rebase()
        return
    if name == 'app-closing':
        if folderwatch.is_on():
            folderwatch.stop(save=False)
        return
    if name == 'startup':
        if (event or {}).get('runner'):
            return
        config = folderwatch.load_config()
        if not (config['remember'] and config['active']):
            return
        if not folderwatch.is_on():
            folderwatch.start(config)
        folderwatch.sync_toggle(True)
