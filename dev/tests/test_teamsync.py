# -*- coding: utf-8 -*-
"""namo.teamsync: manifests, the per-area diff, merges, and Pull/Push between two temp
folders (never the real %APPDATA%)."""
import collections
import io
import json
import os

import _compat

from namo import config, hotkeys, paths, teamsync


def _write(path, text):
    folder = os.path.dirname(path)
    if not os.path.isdir(folder):
        os.makedirs(folder)
    with io.open(path, 'w', encoding='utf-8', newline='') as handle:
        handle.write(text)


def _read(path):
    with io.open(path, encoding='utf-8') as handle:
        return handle.read()


def test_area_of_and_diff():
    assert teamsync.area_of('templates/a.json') == 'templates'
    assert teamsync.area_of('shortcuts.json') == 'shortcuts'
    assert teamsync.area_of('version.json') is None
    team = {'templates/a.json': '1', 'templates/b.json': '2', 'presets/x/y.json': '3',
            'config.json': 'c2', 'shortcuts.json': 's1'}
    local = {'templates/a.json': '1', 'templates/b.json': 'old', 'templates/mine.json': 'm',
             'rules/gone.json': 'g'}
    pulled = {'config.json': 'c1', 'shortcuts.json': 's1', 'rules/gone.json': 'g', 'templates/a.json': '1'}
    changes = teamsync.diff(team, local, pulled)
    assert changes['templates'] == {'added': [], 'changed': ['templates/b.json'], 'removed': []}
    assert changes['presets']['added'] == ['presets/x/y.json']
    assert changes['rules']['removed'] == ['rules/gone.json']
    assert changes['config']['changed'] == ['config.json']
    assert changes['shortcuts'] == {'added': [], 'changed': [], 'removed': []}
    assert teamsync.count(changes) == 4
    assert teamsync.summary_lines(changes) == ['Project settings: 1 changed', 'Templates: 1 changed',
                                               'Presets: 1 added', 'Rules: 1 removed']


def test_merges():
    values, changed = teamsync.merge_config({'company': 'A', 'trades': ['X']},
                                            {'company': 'B', 'trades': ['X'], 'user': 'hacker', 'shared_root': 'Z'})
    assert values == {'company': 'B'} and changed == ['company']
    root = collections.OrderedDict([('theme', 'dark'), ('shortcuts', collections.OrderedDict(
        [('bindings', collections.OrderedDict([('01_A.tab/P.panel/X.pushbutton', 'Ctrl+1'),
                                               ('Mine.tab/P.panel/Y.pushbutton', 'Ctrl+2')]))]))])
    assert teamsync.merge_shortcuts(root, {'A.tab/P.panel/X.pushbutton': 'Ctrl+Alt+X',
                                           'B.tab/P.panel/Z.pushbutton': None, 'bad': 5}) == 2
    assert list(root['shortcuts']['bindings'].items()) == [
        ('Mine.tab/P.panel/Y.pushbutton', 'Ctrl+2'), ('A.tab/P.panel/X.pushbutton', 'Ctrl+Alt+X'),
        ('B.tab/P.panel/Z.pushbutton', None)]
    assert teamsync.merge_roots(root, ['\\\\srv\\tools\\', 'D:\\ext']) == 2
    assert teamsync.merge_roots(root, ['\\\\SRV\\tools', 7]) == 0
    assert root['extensions'] == ['\\\\srv\\tools\\', 'D:\\ext']
    assert teamsync.needs_pull('2026-10-05T10:00:00', '') and not teamsync.needs_pull('', 'x')
    assert not teamsync.needs_pull('a', 'a')


def test_push_then_pull_between_two_machines():
    base = _compat.tmpdir('teamsync_flow')
    team_folder = os.path.join(base, 'share')
    os.makedirs(team_folder)
    boss = os.path.join(base, 'boss')
    worker = os.path.join(base, 'worker')
    boss_cfg = os.path.join(boss, 'pyNavis', 'config.json')
    worker_cfg = os.path.join(worker, 'pyNavis', 'config.json')
    _write(boss_cfg, json.dumps({'extensions': ['\\\\srv\\ext'], 'shortcuts': {'bindings': {'A.tab/P.panel/X.pushbutton': 'Ctrl+Alt+X'}}}))
    _write(worker_cfg, json.dumps({'theme': 'light', 'shortcuts': {'bindings': {'Mine.tab/P.panel/Y.pushbutton': 'Ctrl+2'}}}))
    previous = paths.redirect(boss)
    try:
        config.save({'company': 'Acme', 'trades': ['Arch', 'Mech']})
        _write(os.path.join(paths.data_root(), 'templates', 'macros.json'), '{"a": 1}')
        _write(os.path.join(paths.data_root(), 'presets', 'colors', 'one.json'), '{"p": 1}')
        result = teamsync.push(team_folder, config_path=boss_cfg, user='Boss')
        assert result['files'] == 5 and result['backup'] is None
        stamp = result['stamp']
        team = teamsync.team_dir(team_folder)
        assert teamsync.read_stamp(team) == stamp
        assert json.loads(_read(os.path.join(team, 'shortcuts.json'))) == {'A.tab/P.panel/X.pushbutton': 'Ctrl+Alt+X'}
        assert json.loads(_read(os.path.join(team, 'config.json')))['company'] == 'Acme'
        assert teamsync.preview(team_folder)['count'] == 0          # the pusher is in sync
    finally:
        paths.redirect(previous)

    previous = paths.redirect(worker)
    try:
        _write(os.path.join(paths.data_root(), 'templates', 'macros.json'), '{"mine": true}')
        _write(os.path.join(paths.data_root(), 'templates', 'local-only.json'), '{"keep": true}')
        found = teamsync.preview(team_folder)
        assert found['error'] is None
        assert found['lines'] == ['Project settings: 1 added', 'Templates: 1 changed', 'Presets: 1 added',
                                  'Shortcuts: 1 added', 'Extension folders: 1 added']
        result = teamsync.pull(team_folder, config_path=worker_cfg)
        assert result['copied'] == 2 and result['removed'] == 0
        assert result['config'] == ['company', 'trades'] and result['shortcuts'] == 1 and result['roots'] == 1
        assert result['needs_reload'] and result['backup']
        assert _read(os.path.join(result['backup'], 'templates', 'macros.json')) == '{"mine": true}'
        assert _read(os.path.join(paths.data_root(), 'templates', 'macros.json')) == '{"a": 1}'
        assert os.path.exists(os.path.join(paths.data_root(), 'templates', 'local-only.json'))
        assert config.load()['company'] == 'Acme'
        root, _error = hotkeys.read_config(worker_cfg)
        assert root['theme'] == 'light' and root['extensions'] == ['\\\\srv\\ext']
        assert dict(root['shortcuts']['bindings']) == {'Mine.tab/P.panel/Y.pushbutton': 'Ctrl+2',
                                                       'A.tab/P.panel/X.pushbutton': 'Ctrl+Alt+X'}
        assert teamsync.load_state()['stamp'] == stamp
        assert teamsync.preview(team_folder)['count'] == 0
        # The team drops the preset: the next pull removes the copy pulled earlier.
        os.remove(os.path.join(teamsync.team_dir(team_folder), 'presets', 'colors', 'one.json'))
        found = teamsync.preview(team_folder)
        assert found['lines'] == ['Presets: 1 removed']
        result = teamsync.pull(team_folder, config_path=worker_cfg)
        assert result['removed'] == 1
        assert not os.path.exists(os.path.join(paths.data_root(), 'presets', 'colors', 'one.json'))
        level, message, detail = teamsync.result_toast(result)
        assert (level, message, detail) == ('success', 'Team settings updated', '1 removed')
        # Startup check: nothing to do while the stamp is unchanged and auto pull is off.
        assert teamsync.startup_check() is None
        state = teamsync.load_state()
        state['auto_pull'] = True
        state['team_folder'] = team_folder
        teamsync.save_state(state)
        assert teamsync.startup_check() is None                 # stamp unchanged
    finally:
        paths.redirect(previous)


def test_preview_errors():
    base = _compat.tmpdir('teamsync_errors')
    previous = paths.redirect(base)
    try:
        assert teamsync.preview('')['error'] == 'Set the team folder first.'
        assert 'There is no playground-team folder' in teamsync.preview(base)['error']
        raised = _compat.raises(IOError, teamsync.push, os.path.join(base, 'missing'))
        assert 'not reachable' in str(raised)
        level, message, _detail = teamsync.result_toast(IOError('offline'))
        assert level == 'warning' and message == 'Team settings were not updated'
    finally:
        paths.redirect(previous)


def test_startup_probe_reads_only_and_finds_a_new_stamp():
    # hk_teamsync runs startup_probe on a worker thread: it must decide from plain file
    # reads alone (no pull, no writes) and leave the pull to the UI thread.
    base = _compat.tmpdir('teamsync_probe')
    team_folder = os.path.join(base, 'share')
    team = teamsync.team_dir(team_folder)
    _write(os.path.join(team, 'version.json'), '{"stamp": "2026-10-05T09:00:00", "by": "Boss"}')
    _write(os.path.join(team, 'templates', 'macros.json'), '{"a": 1}')
    previous = paths.redirect(base)
    try:
        assert teamsync.startup_probe() is None                     # auto pull is off
        state = teamsync.load_state()
        state['auto_pull'] = True
        state['team_folder'] = team_folder
        teamsync.save_state(state)
        assert teamsync.startup_probe() == team_folder              # never pulled: a new stamp
        assert not os.path.exists(os.path.join(paths.data_root(), 'templates', 'macros.json'))
        state['stamp'] = '2026-10-05T09:00:00'
        teamsync.save_state(state)
        assert teamsync.startup_probe() is None                     # same stamp
        state['team_folder'] = os.path.join(base, 'offline')
        teamsync.save_state(state)
        assert teamsync.startup_probe() is None                     # no playground-team there
        _write(teamsync.state_path(), '{damaged')
        assert teamsync.startup_probe() is None                     # unreadable state: no pull
        assert os.path.exists(teamsync.state_path())                # and left where it was
    finally:
        paths.redirect(previous)
