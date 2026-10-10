# -*- coding: utf-8 -*-
"""Pulls shared Playground settings from the team folder, or pushes this computer's to it."""
from pynavis import forms, toast

from namo import ribbon, teamsync, ui


def pick(initial):
    return forms.pick_folder(title='Team folder (the one that holds or will hold playground-team)',
                             initial=initial or None)


if globals().get('__runner__'):
    toast.info('Team Sync needs the Navisworks window', 'It cannot open under pynavis run.')
else:
    state = teamsync.load_state()
    folder = teamsync.team_folder(state)
    if not folder:
        folder = pick('')
        if folder is not None:
            state['team_folder'] = folder
            teamsync.save_state(state)
    while folder:
        found = teamsync.preview(folder)
        win = teamsync.build_window(folder, found, state)
        ui.show_modal(win)
        action = win.Tag.action
        if win.Tag.auto_pull != state.get('auto_pull'):
            state['auto_pull'] = win.Tag.auto_pull
            teamsync.save_state(state)
            if action is None:
                toast.info('Pull at startup is %s' % ('on' if state['auto_pull'] else 'off'))
        if action == 'folder':
            chosen = pick(folder)
            if chosen is not None:
                folder = chosen
                state['team_folder'] = chosen
                teamsync.save_state(state)
            continue
        if action == 'pull':
            try:
                result = teamsync.pull(folder)
            except (IOError, OSError) as error:
                toast.error('Could not pull the team settings', str(error))
            else:
                level, message, detail = teamsync.result_toast(result)
                if result.get('needs_reload'):
                    ribbon.reload()
                    detail = detail.replace('Reload pyNavis to apply them.', 'pyNavis reloaded to apply them.')
                toast.show(level, message, detail)
        elif action == 'push':
            if forms.confirm('Write this computer\'s templates, presets, libraries, rules, project settings, '
                             'shortcuts and extension folders to %s? Team files it replaces are backed up '
                             'in playground-team\\.backup.' % folder, title='Team Sync'):
                try:
                    result = teamsync.push(folder)
                except (IOError, OSError) as error:
                    toast.error('Could not push to the team folder', str(error))
                else:
                    toast.success('Pushed to the team folder',
                                  '%d file%s updated, version %s.' % (result['files'], '' if result['files'] == 1 else 's',
                                                                     result['stamp'].replace('T', ' ')))
        break
