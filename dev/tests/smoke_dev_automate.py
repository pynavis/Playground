# -*- coding: utf-8 -*-
"""Command Palette, Manage Macros and Hotkey Manager windows built under IronPython + WPF
with sample data (never shown): XAML parses, keys and buttons drive the state."""
import os

import _compat

_compat.require_ironpython()

from namo import hotkeys, macros, palette, paths, session  # noqa: E402

import test_palette  # noqa: E402


def test_palette_window_ranks_moves_and_refuses_blocked():
    entries = test_palette.entries()
    win = palette.build_window(entries, ['set|walls'])
    state = win.Tag
    assert state.listing.Items.Count == len(entries)
    assert state.status.Text == '%d commands, views and sets' % len(entries)
    first = state.ranker.entries[state.shown[0]]
    assert first['title'] == 'Select set: Walls'                   # MRU first
    state.refresh('similar')
    assert state.listing.Items.Count == 1
    assert state.choose(0) == 'Select Similar needs a selection.'
    assert state.result is None
    state.refresh('clash')
    assert state.status.Text == '%d matches' % state.matches
    state.move(1)
    assert state.listing.SelectedIndex == 1
    state.move(0, 0)
    assert state.choose(state.listing.SelectedIndex) is None
    assert state.result['title'] == 'Clash Grouper'
    state.refresh('zzzz')
    assert state.listing.Items.Count == 0 and state.status.Text == 'No matches'
    assert state.choose(0) == 'Nothing to run.'


def test_palette_rows_render_shortcuts_and_muted_text():
    entries = test_palette.entries()
    win = palette.build_window(entries, [], 'command')
    state = win.Tag
    row = state.listing.Items[0]
    assert row.Children.Count == 2                                  # text stack + shortcut
    assert row.Children[1].Text == 'Ctrl+Shift+P'
    title = row.Children[0].Children[0]
    assert ''.join(r.Text for r in title.Inlines) == 'Command Palette'


def test_manage_macros_window_edits_steps():
    folder = _compat.tmpdir('smoke_macros')
    previous = paths.redirect(folder)
    try:
        macros.save('Morning', {'steps': [
            {'kind': 'bundle', 'key': 'A.tab/P.panel/One.pushbutton', 'title': 'One', 'gap': 3},
            {'kind': 'wait', 'seconds': 2},
            {'kind': 'view', 'path': 'Lobby', 'title': 'Lobby'}]})
        macros.save('Evening', {'steps': []})
        session.clear(macros.REC)
        win = macros.build_manager(macros.store(), lambda: test_palette.entries(), select='Morning')
        parts = win.Tag
        assert parts.name == 'Morning' and parts.title.Text == 'Morning'
        assert parts.steps_table.total() == 3
        parts.steps_table.select_values([2])
        parts.move(-1)
        assert [s['kind'] for s in macros.load('Morning')['steps']] == ['bundle', 'view', 'wait']
        parts.steps_table.select_values([0])
        parts.insert({'kind': 'confirm', 'message': 'Go on?'})
        assert [s['kind'] for s in macros.load('Morning')['steps']] == ['bundle', 'confirm', 'view', 'wait']
        parts.steps_table.select_values([3])
        parts.delete_chosen()
        assert len(macros.load('Morning')['steps']) == 3
        parts.stop_check.IsChecked = False
        assert macros.load('Morning')['stop_on_error'] is False
        parts.select_macro('Evening')
        assert parts.name == 'Evening' and parts.steps_table.total() == 0
        assert parts.status.Text == 'Evening: 0 steps'
    finally:
        paths.redirect(previous)


def test_hotkey_manager_window_assigns_and_blocks_conflicts():
    rows = [
        {'key': 'A.tab/P.panel/One.pushbutton', 'kind': 'bundle', 'title': 'One', 'path': 'E > A > P',
         'default': 'Ctrl+Shift+1', 'current': 'Ctrl+Shift+1', 'extension': 'E'},
        {'key': 'A.tab/P.panel/Two.pushbutton', 'kind': 'bundle', 'title': 'Two', 'path': 'E > A > P',
         'default': None, 'current': None, 'extension': 'E'},
        {'key': 'native:T/sel', 'kind': 'native', 'title': 'Select', 'path': 'Navisworks > Home',
         'default': None, 'current': None, 'extension': 'Navisworks'},
    ]
    state = {'model': hotkeys.HotkeyModel(rows), 'config_path': os.path.join(_compat.tmpdir('smoke_hotkeys'), 'c.json'),
             'root': _compat.tmpdir('smoke_hotkeys_root'), 'error': None}
    win = hotkeys.build_window(state)
    parts = win.Tag
    assert parts.table.total() == 3
    assert not parts.save_button.IsEnabled
    parts.table.select_values(['A.tab/P.panel/Two.pushbutton'])
    assert parts.selected == 'A.tab/P.panel/Two.pushbutton'
    parts.chord_changed('Ctrl+Shift+1')
    assert parts.model.row('A.tab/P.panel/Two.pushbutton')['current'] == 'Ctrl+Shift+1'
    assert not parts.save_button.IsEnabled                        # conflict with One
    assert 'fix 1 conflict to save' in parts.status.Text
    parts.chord_changed('Ctrl+Alt+2')
    assert parts.save_button.IsEnabled
    parts.table.select_values(['native:T/sel'])
    parts.chord_changed('Alt+S')
    assert parts.model.changes('native') == {'native:T/sel': 'Alt+S'}
    parts.chord_changed(None)
    assert parts.model.changes('native') == {}
    assert type(parts.recorder).__name__ in ('ChordRecorder', 'Grid', 'Border')


def _pump_until(condition, seconds=5.0):
    """Runs the WPF dispatcher until condition() is true (or the time runs out)."""
    import time
    import clr
    clr.AddReference('WindowsBase')
    from System import TimeSpan
    from System.Windows.Threading import Dispatcher, DispatcherFrame, DispatcherPriority, DispatcherTimer
    frame = DispatcherFrame()
    started = time.time()
    watch = DispatcherTimer(DispatcherPriority.Background)
    watch.Interval = TimeSpan.FromMilliseconds(20)

    def check(sender, args):
        if condition() or time.time() - started > seconds:
            watch.Stop()
            frame.Continue = False
    watch.Tick += check
    watch.Start()
    Dispatcher.PushFrame(frame)
    return condition()


def test_deferred_job_runs_on_a_real_dispatcher_after_the_gate_frees():
    import time
    import clr
    clr.AddReference('WindowsBase')
    from System import Action
    from System.Windows.Threading import Dispatcher, DispatcherPriority
    from namo import ribbon
    gate = {'held': True, 'since': time.time()}
    ran = []
    done = []

    def held():
        if gate['held'] and time.time() - gate['since'] > 0.15:
            gate['held'] = False          # the calling script returned
        return gate['held']

    def dispatch():
        return Dispatcher.CurrentDispatcher.BeginInvoke(DispatcherPriority.Background,
                                                        Action(lambda: ran.append(time.time())))
    job = ribbon.Job('Thing', held, dispatch, ribbon._operation_done, lambda op: (True, ''),
                     on_done=done.append)
    ribbon.schedule(job, 10)
    assert _pump_until(lambda: bool(done))
    assert job.state == 'done' and len(ran) == 1 and ran[0] - gate['since'] >= 0.15


def test_macro_player_runs_on_a_real_dispatcher():
    from namo import macros, ribbon
    finished = []
    order = []

    def start(step):
        order.append(step['title'])
        return (True, '')
    player = macros.Player('Smoke', [{'kind': 'view', 'title': 'A', 'path': 'A'},
                                      {'kind': 'wait', 'seconds': 0.05},
                                      {'kind': 'set', 'title': 'B', 'path': 'B'}],
                           True, start, lambda: False, lambda step: True, on_finish=finished.append)
    ribbon.schedule(player, 10)
    assert _pump_until(lambda: bool(finished))
    assert player.state == 'done' and order == ['A', 'B']
