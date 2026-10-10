# -*- coding: utf-8 -*-
"""Installs, updates and removes pyNavis extensions from the team registry."""
import os
import tempfile

from pynavis import script, toast

from namo import buttonmaker, extmanager, hotkeys, paths, progress, ribbon


def run():
    cfg = script.get_config({'registry': ''})
    location = (cfg['registry'] or '').strip() or extmanager.default_registry(paths.team_root())
    user_root = buttonmaker.user_root()
    entries, problems, notice = [], [], None
    if location == extmanager.PLACEHOLDER:
        notice = 'No registry is set. Shift+Click Extension Manager to choose one.'
    else:
        try:
            outcome = progress.run('Reading the extension registry',
                                   lambda report: extmanager.load_registry(location), 'Reading')
        except IOError as error:
            notice = str(error)
        else:
            if outcome is progress.CANCELLED:
                return                              # cancelled: say nothing
            entries, problems = outcome
    roots = [user_root]
    config_root, _error = hotkeys.read_config(ribbon.user_config_path())
    for root in (config_root or {}).get('extensions') or []:
        if isinstance(root, str) and root.strip() and root.strip().lower() != user_root.lower():
            roots.append(root.strip())
    temp_folder = os.path.join(tempfile.gettempdir(), 'playground-extensions')
    changed = extmanager.run_window(location, entries, problems, user_root, roots,
                                    os.path.join(paths.data_root(), 'trash'), temp_folder, notice)
    if changed:
        ribbon.reload()
        toast.success('Reloaded pyNavis', '%d extension%s changed.' % (changed, '' if changed == 1 else 's'))


if globals().get('__runner__'):
    toast.info('The Extension Manager needs the Navisworks window', 'It cannot open under pynavis run.')
else:
    run()
