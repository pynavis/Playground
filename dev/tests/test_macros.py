# -*- coding: utf-8 -*-
"""namo.macros: steps, labels, editing helpers, the recorder's session state and the
Player state machine (driven with fake jobs and a fake clock)."""
import _compat

from namo import macros, paths, session


def test_should_record_skips_the_macro_tools_and_the_palette():
    assert macros.should_record('Model.tab/Select.panel/Select_Similar.pushbutton')
    assert not macros.should_record('Dev.tab/Automate.panel/Macro_Record.toggle')
    assert not macros.should_record('dev.tab/automate.panel/command_palette.pushbutton')
    assert not macros.should_record('Dev.tab/Automate.panel/Macros.pulldown/Play_Macro.pushbutton')
    assert not macros.should_record('')


def test_normalize_drops_what_cannot_play():
    config = {'steps': [
        {'kind': 'bundle', 'key': 'A.tab/B.panel/C.pushbutton', 'title': 'C', 'gap': '2.5'},
        {'kind': 'bundle'},
        {'kind': 'teleport', 'key': 'x'},
        {'kind': 'wait', 'seconds': 5000},
        {'kind': 'wait', 'seconds': 'soon'},
        {'kind': 'confirm'},
        {'kind': 'view', 'path': 'Level 1/Lobby'},
        {'kind': 'set', 'path': ''},
        'junk',
    ], 'stop_on_error': False}
    macro = macros.normalize_macro(config)
    assert macro['stop_on_error'] is False and macro['version'] == 1
    assert [s['kind'] for s in macro['steps']] == ['bundle', 'wait', 'wait', 'confirm', 'view']
    assert macro['steps'][0] == {'kind': 'bundle', 'key': 'A.tab/B.panel/C.pushbutton', 'extension': '',
                                 'title': 'C', 'gap': 2.5}
    assert macro['steps'][1]['seconds'] == macros.MAX_WAIT
    assert macro['steps'][2]['seconds'] == 1.0
    assert macro['steps'][3]['message'] == 'Continue the macro?'
    assert macros.normalize_macro(None) == {'version': 1, 'steps': [], 'stop_on_error': True}


def test_labels_and_descriptions():
    label = macros.step_label
    assert label({'kind': 'bundle', 'key': 'A.tab/B.panel/Clash_Report.pushbutton', 'title': ''}) == 'Clash Report'
    assert label({'kind': 'native', 'key': 'native:x', 'title': 'Select'}) == 'Navisworks: Select'
    assert label({'kind': 'view', 'path': 'A/Lobby', 'title': 'Lobby'}) == 'Go to view: Lobby'
    assert label({'kind': 'set', 'path': 'Ducts', 'title': ''}) == 'Select set: Ducts'
    assert label({'kind': 'wait', 'seconds': 2}) == 'Wait 2 s'
    assert label({'kind': 'wait', 'seconds': 2.5}) == 'Wait 2.5 s'
    assert label({'kind': 'confirm', 'message': 'Go on?'}) == 'Ask to continue: Go on?'
    assert macros.describe({'steps': [{'kind': 'wait', 'seconds': 1}]}) == '1 step'
    assert macros.describe({'steps': [], 'stop_on_error': False}) == '0 steps, keeps going after an error'


def test_editing_helpers():
    steps = ['a', 'b', 'c', 'd']
    assert macros.move_steps(steps, [1, 2], -1) == (['b', 'c', 'a', 'd'], [0, 1])
    assert macros.move_steps(steps, [2, 3], 1) == (steps, [2, 3])          # already at the end
    assert macros.move_steps(steps, [0, 2], 1) == (['b', 'a', 'd', 'c'], [1, 3])
    assert macros.move_steps(steps, [], 1) == (steps, [])
    assert macros.delete_steps(steps, [0, 3]) == ['b', 'c']
    wait = {'kind': 'wait', 'seconds': 3}
    out, position = macros.insert_step([{'kind': 'wait', 'seconds': 1}], 0, wait)
    assert position == 1 and out[1]['seconds'] == 3
    out, position = macros.insert_step([], None, wait)
    assert position == 0 and len(out) == 1
    out, position = macros.insert_step([], None, {'kind': 'nope'})
    assert out == [] and position is None
    assert macros.gap_of(12.34, 10.0) == 2.3 and macros.gap_of(5, None) == 0.0 and macros.gap_of(1, 3) == 0.0


def test_recording_state_lives_in_the_session():
    session.clear(macros.REC)
    assert not macros.is_recording()
    assert not macros.record_command('A.tab/B.panel/C.pushbutton')          # off: ignored
    macros.start_recording()
    assert macros.is_recording()
    assert macros.record_command('A.tab/B.panel/C.pushbutton')
    assert not macros.record_command('Dev.tab/Automate.panel/Macro_Record.toggle')
    assert macros.record_entry({'kind': 'native', 'key': 'native:T/a', 'title': 'Orbit', 'path': 'Viewpoint > Navigate'})
    assert macros.record_entry({'kind': 'view', 'target': 'Level 1/Lobby', 'name': 'Lobby', 'title': 'Go to view: Lobby'})
    assert not macros.record_entry({'kind': 'bundle', 'key': 'x'})           # hk_macro records those
    steps = macros.snapshot_steps()
    assert [s['kind'] for s in steps] == ['bundle', 'native', 'view']
    assert steps[0]['key'] == 'A.tab/B.panel/C.pushbutton' and steps[2]['path'] == 'Level 1/Lobby'
    recorded = macros.stop_recording()
    assert len(recorded) == 3 and not macros.is_recording()
    assert len(macros.unsaved_steps()) == 3
    macros.forget_unsaved()
    assert macros.unsaved_steps() == []
    session.clear(macros.REC)


def test_step_from_entry():
    assert macros.step_from_entry({'kind': 'set', 'target': 'MEP/Ducts', 'name': 'Ducts', 'title': 'Select set: Ducts'}) == \
        {'kind': 'set', 'path': 'MEP/Ducts', 'title': 'Ducts'}
    assert macros.step_from_entry({'kind': 'url', 'url': 'https://x', 'title': 'Docs'})['url'] == 'https://x'
    assert macros.step_from_entry({'kind': 'bundle'}) is None


class FakeJob(object):
    def __init__(self, ticks=1, ok=True, message=''):
        self.left = ticks
        self.ok_value = ok
        self.message = message
        self.ok = None
        self.cancelled = False

    @property
    def active(self):
        return self.left > 0 and not self.cancelled

    def tick(self):
        if self.left > 0:
            self.left -= 1
            if self.left == 0:
                self.ok = self.ok_value
        return self.active

    def cancel(self):
        self.cancelled = True
        self.ok = False


class Clock(object):
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def _player(steps, results, stop_on_error=True, gate=None, answers=None, clock=None):
    started = []
    finished = []
    gate = gate if gate is not None else {'held': False}
    answers = list(answers or [])

    def start(step):
        started.append(step.get('title') or step['kind'])
        return results.pop(0)
    player = macros.Player('Test', steps, stop_on_error, start, lambda: gate['held'],
                           lambda step: answers.pop(0), clock=clock or Clock(), on_finish=finished.append)
    return player, started, finished


def _run(player, limit=100):
    for _ in range(limit):
        if not player.tick():
            return
    raise AssertionError('player never finished')


def test_player_runs_steps_in_order_and_waits_for_the_gate():
    clock = Clock()
    gate = {'held': True}
    steps = [{'kind': 'bundle', 'title': 'One'}, {'kind': 'wait', 'seconds': 2},
             {'kind': 'view', 'title': 'Lobby'}, {'kind': 'bundle', 'title': 'Two'}]
    player, started, finished = _player(steps, [FakeJob(2), (True, ''), FakeJob(1)], gate=gate, clock=clock)
    assert player.tick() and started == []          # gate held: nothing starts
    gate['held'] = False
    assert player.tick() and started == ['One']
    assert player.tick() and player.tick()          # job ticks twice
    assert player.tick() and player.wait_until == 2.0
    assert player.tick() and started == ['One']     # still waiting
    clock.now = 2.5
    _run(player)
    assert started == ['One', 'Lobby', 'Two']
    assert player.state == 'done' and finished == [player] and player.failures == []


def test_player_stops_or_continues_on_errors():
    steps = [{'kind': 'bundle', 'title': 'One'}, {'kind': 'bundle', 'title': 'Two'},
             {'kind': 'set', 'title': 'Ducts'}]
    player, started, finished = _player(steps, [FakeJob(1, ok=False, message='boom'), FakeJob(1)])
    _run(player)
    assert player.state == 'failed' and started == ['One']
    assert player.failures == [(1, 'One', 'boom')]
    player, started, _ = _player(steps, [FakeJob(1, ok=False, message='boom'), None,
                                         (False, 'no such set')], stop_on_error=False)
    _run(player)
    assert player.state == 'done' and started == ['One', 'Two', 'Ducts']
    assert [f[0] for f in player.failures] == [1, 2, 3]
    assert player.failures[1][2] == 'Two is not available here.'
    assert player.failures[2][2] == 'no such set'


def test_player_confirm_and_stop():
    steps = [{'kind': 'confirm', 'message': 'Go?'}, {'kind': 'bundle', 'title': 'One'},
             {'kind': 'confirm', 'message': 'Again?'}, {'kind': 'bundle', 'title': 'Two'}]
    player, started, finished = _player(steps, [FakeJob(1), FakeJob(1)], answers=[True, False])
    _run(player)
    assert started == ['One'] and player.state == 'cancelled' and finished == [player]
    job = FakeJob(10)
    player, started, finished = _player([{'kind': 'bundle', 'title': 'Long'}], [job])
    player.tick()
    player.stop()
    assert player.state == 'stopped' and job.cancelled and not player.tick()
    assert finished == [player]


def test_player_reports_a_raising_start():
    def boom(step):
        raise RuntimeError('broken step')
    player = macros.Player('X', [{'kind': 'bundle', 'title': 'A'}], True, boom, lambda: False,
                           lambda step: True)
    _run(player)
    assert player.state == 'failed' and player.failures[0][2] == 'broken step'


def test_storage_roundtrip_in_a_temp_root():
    folder = _compat.tmpdir('macros_store')
    previous = paths.redirect(folder)
    try:
        assert macros.names() == []
        stored = macros.save('Morning', {'steps': [{'kind': 'wait', 'seconds': 1}, {'kind': 'bad'}]})
        assert stored == 'Morning' and macros.names() == ['Morning']
        assert macros.load('morning') == {'version': 1, 'steps': [{'kind': 'wait', 'title': '', 'gap': 0.0,
                                                                   'seconds': 1.0}],
                                          'stop_on_error': True}
        rows = macros.macro_rows(macros.store())
        assert rows[0]['value'] == 'Morning' and rows[0]['cells'][1] == 1
        assert macros.step_rows(macros.load('Morning')['steps'])[0]['cells'] == [1, 'Wait 1 s', '']
        assert macros.load('nope') is None
    finally:
        paths.redirect(previous)


def test_command_choices():
    entries = [{'kind': 'bundle', 'key': 'A/B.pushbutton', 'title': 'B', 'extension': 'E', 'path': 'T > P'},
               {'kind': 'native', 'key': 'native:x', 'title': 'Orbit', 'path': 'Viewpoint'},
               {'kind': 'view', 'target': 'Lobby', 'name': 'Lobby', 'title': 'Go to view: Lobby', 'path': ''}]
    rows = macros.command_choices(entries)
    assert [r['cells'][0] for r in rows] == ['B', 'Navisworks: Orbit', 'Go to view: Lobby']
    assert rows[0]['value'] == {'kind': 'bundle', 'key': 'A/B.pushbutton', 'extension': 'E', 'title': 'B'}


def _event(values):
    """pyNavis' __event__: a .NET Dictionary[str, object] under IronPython (no .get()),
    a stand-in with only 'in' and [] under CPython."""
    if _compat.IRONPYTHON:
        from System import Object, String
        from System.Collections.Generic import Dictionary
        event = Dictionary[String, Object]()
        for key in values:
            event[key] = values[key]
        return event

    class NetDictionary(object):
        def __init__(self, items):
            self._items = dict(items)

        def __contains__(self, key):
            return key in self._items

        def __getitem__(self, key):
            return self._items[key]
    return NetDictionary(values)


def test_hk_macro_records_from_the_net_event_dictionary():
    from namo import hk_macro
    key = 'A.tab/B.panel/C.pushbutton'
    event = _event({'name': 'after-command', 'command': key, 'viewpoint': None})
    assert hk_macro.command_of(event) == key
    assert hk_macro.command_of(_event({'name': 'doc-opened', 'command': None})) is None
    assert hk_macro.command_of(_event({'name': 'doc-opened'})) is None
    assert hk_macro.command_of(None) is None
    session.clear(macros.REC)
    try:
        hk_macro.handle('after-command', event)                     # not recording: ignored
        assert macros.snapshot_steps() == []
        macros.start_recording()
        hk_macro.handle('before-command', event)                    # only after-command records
        hk_macro.handle('after-command', event)
        assert [s['key'] for s in macros.snapshot_steps()] == [key]
    finally:
        session.clear(macros.REC)
