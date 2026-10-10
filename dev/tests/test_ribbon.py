# -*- coding: utf-8 -*-
"""namo.ribbon pure half: chords, keys, titles, bindings, context words, the Job state
machine. Under IronPython the chord grammar and binding resolution are cross-checked
against pyNavis' own ChordParser and ShortcutMap."""
import _compat

from namo import ribbon

CHORDS = [
    ('Ctrl+Shift+M', 'Ctrl+Shift+M', None),
    ('ctrl + shift + m', 'Ctrl+Shift+M', None),
    ('shift+ctrl+alt+f5', 'Ctrl+Alt+Shift+F5', None),
    ('Alt+pgup', 'Alt+PgUp', None),
    ('Ctrl+Left', 'Ctrl+Left', None),
    ('Ctrl+9', 'Ctrl+9', None),
    ('Ctrl+F24', 'Ctrl+F24', None),
    ('', None, 'empty binding'),
    ('   ', None, 'empty binding'),
    ('Ctrl+M+K', None, "'Ctrl+M+K': more than one key"),
    ('Ctrl+Esc', None, "'Ctrl+Esc': unknown token 'Esc'"),
    ('Ctrl+Shift', None, "'Ctrl+Shift': no key"),
    ('Shift+M', None, "'Shift+M': bindings need Ctrl or Alt (set shortcuts.allowBareKeys to permit bare keys)"),
    ('M', None, "'M': bindings need Ctrl or Alt (set shortcuts.allowBareKeys to permit bare keys)"),
    ('Ctrl+PageUp', None, "'Ctrl+PageUp': unknown token 'PageUp'"),
    ('Win+M', None, "'Win+M': unknown token 'Win'"),
    ('Ctrl++', None, "'Ctrl++': unknown token ''"),
    ('Ctrl+F25', None, "'Ctrl+F25': unknown token 'F25'"),
]


def test_parse_chord_matches_the_runtime_grammar():
    for text, chord, error in CHORDS:
        got = ribbon.parse_chord(text)
        assert got == (chord, error), (text, got)


def test_bare_keys_only_when_allowed():
    assert ribbon.parse_chord('Shift+M', allow_bare=True) == ('Shift+M', None)
    assert ribbon.parse_chord('f2', allow_bare=True) == ('F2', None)
    assert ribbon.chord_or_none('Shift+M') is None
    assert ribbon.chord_or_none('alt+x') == 'Alt+X'


def test_chord_error_sentences():
    assert ribbon.chord_error_sentence(None) is None
    assert ribbon.chord_error_sentence('empty binding') == 'Press a key combination.'
    assert ribbon.chord_error_sentence("'M': bindings need Ctrl or Alt (x)") == 'A shortcut needs Ctrl or Alt.'
    assert 'one key' in ribbon.chord_error_sentence("'Ctrl+A+B': more than one key")
    assert ribbon.chord_error_sentence("'Ctrl+?': unknown token '?'").startswith('Use letters')


def test_keys_normalise_like_bundlekeys():
    assert ribbon.normalize_key('10_Tab.tab/02_Panel.panel/Thing.pushbutton') == \
        'Tab.tab/Panel.panel/Thing.pushbutton'
    assert ribbon.normalize_key('1_Keep.pushbutton') == '1_Keep.pushbutton'
    assert ribbon.normalize_key('NoUnderscore.pushbutton') == 'NoUnderscore.pushbutton'
    assert ribbon.normalize_key('') == ''
    assert ribbon.normalize_key(None) is None
    assert ribbon.same_key('01_A.tab/B.panel/C.pushbutton', 'a.tab/b.panel/c.PUSHBUTTON')
    assert not ribbon.same_key('A.tab/B.panel/C.pushbutton', None)


def test_bundle_key_from_paths():
    import os
    ext = os.path.join('C:' + os.sep, 'x', 'My.extension')
    bundle = os.path.join(ext, '01_My.tab', 'Tools.panel', 'Go.pushbutton')
    assert ribbon.bundle_key(ext, bundle) == 'My.tab/Tools.panel/Go.pushbutton'


def test_titles():
    assert ribbon.flatten_title('Record\\nMacro') == 'Record Macro'
    assert ribbon.flatten_title('Record \\n  Macro') == 'Record Macro'
    assert ribbon.flatten_title('A   B') == 'A B'
    assert ribbon.flatten_title(None) is None
    assert ribbon.title_from_folder('Clash_Report.pushbutton') == 'Clash Report'
    assert ribbon.title_from_folder('02_Recall_Now.pushbutton') == 'Recall Now'
    assert ribbon.title_from_folder('1_Keep.toggle') == '1 Keep'
    assert ribbon.title_from_folder('Team_Tools.stack') == 'Team Tools'
    assert ribbon.command_path('Playground', '', None, 'Automate') == 'Playground > Automate'


def test_resolve_bindings_mirrors_shortcutmap():
    buttons = [
        {'key': 'A.tab/P.panel/One.pushbutton', 'shortcut': 'Ctrl+Shift+1'},
        {'key': 'A.tab/P.panel/Two.pushbutton', 'shortcut': 'ctrl+shift+1'},   # loses
        {'key': 'A.tab/P.panel/Three.pushbutton', 'shortcut': 'Ctrl+Shift+3'},
        {'key': 'A.tab/P.panel/Four.pushbutton', 'shortcut': None},
        {'key': 'a.tab/p.panel/one.pushbutton', 'shortcut': 'Ctrl+9'},          # duplicate key
        {'key': 'A.tab/P.panel/Bad.pushbutton', 'shortcut': 'Shift+B'},
    ]
    overrides = {
        '01_A.tab/P.panel/Three.pushbutton': None,       # disables the default
        'A.tab/P.panel/Four.pushbutton': 'Alt+4',
        'Gone.tab/X.panel/Old.pushbutton': 'Ctrl+O',
    }
    bound, problems = ribbon.resolve_bindings(buttons, overrides)
    assert bound == {'a.tab/p.panel/one.pushbutton': 'Ctrl+Shift+1',
                     'a.tab/p.panel/four.pushbutton': 'Alt+4'}
    assert "shortcut override for unknown tool 'Gone.tab/X.panel/Old.pushbutton' ignored" in problems
    assert any("wants Ctrl+Shift+1 but 'A.tab/P.panel/One.pushbutton' already has it" in p
               for p in problems)
    assert any(p.startswith("'A.tab/P.panel/Bad.pushbutton': 'Shift+B': bindings need")
               for p in problems)


def test_find_conflicts_first_wins():
    pairs = [('a', 'Ctrl+K'), ('b', 'ctrl+k'), ('c', None), ('d', 'Alt+K'), ('e', 'Alt+k')]
    assert ribbon.find_conflicts(pairs) == {'b': 'a', 'e': 'd'}


def test_needs_text():
    assert ribbon.needs_text('') == ''
    assert ribbon.needs_text('selection') == 'a selection'
    assert ribbon.needs_text('doc & selection') == 'an open model and a selection'
    assert ribbon.needs_text('clash-tests | viewpoints') == 'clash tests or saved viewpoints'
    assert ribbon.needs_text('doc & !selection') == 'an open model and nothing selected'
    assert ribbon.needs_text('!!doc') == 'an open model'
    assert ribbon.needs_text('weird') == 'weird'
    assert ribbon.needs_text('& doc') == '& doc'


def test_native_key_and_labels():
    assert ribbon.native_key('ID_TabHome', 'ID_Select', 'Home', 'Select', 'Select') == \
        'native:ID_TabHome/ID_Select'
    assert ribbon.native_key('', '', 'Home', 'Tools', 'Clash Detective') == \
        'native:Home/Tools/Clash Detective'
    assert ribbon.clean_label('Clash\r\nDetective') == 'Clash Detective'
    assert ribbon.clean_label(None) == ''


def test_mru_push():
    assert ribbon.mru_push([], 'a') == ['a']
    assert ribbon.mru_push(['b', 'A', 'c'], 'a') == ['a', 'b', 'c']
    assert ribbon.mru_push(['b', 'c', 'd'], 'e', limit=3) == ['e', 'b', 'c']
    assert ribbon.mru_push(['b', None, 3], 'x') == ['x', 'b']


class FakeClock(object):
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def test_job_waits_for_the_gate_then_dispatches_and_finishes():
    clock = FakeClock()
    gate = {'held': True}
    log = []
    ops = {'done': False}
    finished = []
    job = ribbon.Job('Thing', lambda: gate['held'], lambda: log.append('run') or 'op',
                     lambda op: ops['done'], lambda op: (True, ''), timeout_s=5,
                     clock=clock, on_done=finished.append)
    assert job.tick() and job.state == 'waiting' and log == []
    gate['held'] = False
    assert job.tick() and job.state == 'running' and log == ['run']
    assert job.tick() and job.state == 'running'
    ops['done'] = True
    assert not job.tick()
    assert job.state == 'done' and job.ok and finished == [job]
    assert not job.tick() and finished == [job]       # on_done fires once


def test_job_timeout_failure_and_cancel():
    clock = FakeClock()
    done = []
    job = ribbon.Job('Thing', lambda: True, lambda: 'op', timeout_s=2, clock=clock,
                     on_done=done.append)
    assert job.tick()
    clock.now += 3
    assert not job.tick()
    assert job.state == 'timeout' and job.ok is False and done == [job]

    def boom():
        raise RuntimeError('no such tool')
    job = ribbon.Job('Thing', lambda: False, boom, clock=clock)
    assert not job.tick()
    assert job.state == 'failed' and job.message == 'no such tool'

    job = ribbon.Job('Thing', lambda: False, lambda: 'op', lambda op: True,
                     lambda op: (False, 'it raised'), clock=clock)
    assert not job.tick()
    assert job.state == 'failed' and job.message == 'it raised'

    job = ribbon.Job('Thing', lambda: True, lambda: 'op', clock=clock)
    job.cancel()
    assert job.state == 'cancelled' and not job.tick()


def test_job_without_gate_wait_runs_at_once():
    job = ribbon.Job('Now', lambda: True, lambda: 'op', wait_gate=False)
    assert not job.tick()
    assert job.state == 'done'


def test_runtime_half_is_safe_outside_navisworks():
    # No RuntimeHost here (it needs AdWindows): every call degrades to empty results.
    assert ribbon.native_commands() == []
    assert ribbon.find_native('native:x/y') is None
    assert ribbon.buttons([]) == []
    assert ribbon.find_button('A.tab/B.panel/C.pushbutton', exts=[]) is None
    assert ribbon.gate_held() is False


# ---- cross-checks against the real pyNavis runtime (IronPython only) --------------------


def _runtime_types():
    _compat.require_ironpython()
    import clr
    clr.AddReference('PyNavis.Runtime')


def test_chords_agree_with_the_real_chordparser():
    _runtime_types()
    from PyNavis.Runtime.Input import ChordParser
    for text, chord, error in CHORDS:
        ok, parsed, message = ChordParser.TryParse(text, False)
        assert bool(ok) == (chord is not None), text
        if ok:
            assert str(parsed) == chord, (text, str(parsed))
        else:
            assert message == error, (text, message)
    ok, parsed, message = ChordParser.TryParse('Shift+M', True)
    assert ok and str(parsed) == 'Shift+M'


def test_resolution_agrees_with_the_real_shortcutmap():
    _runtime_types()
    from System.Collections.Generic import Dictionary, List
    from PyNavis.Runtime.Bundles import PushButtonModel
    from PyNavis.Runtime.Input import ShortcutMap
    specs = [('A.tab/P.panel/One.pushbutton', 'Ctrl+Shift+1'),
             ('A.tab/P.panel/Two.pushbutton', 'Ctrl+Shift+1'),
             ('A.tab/P.panel/Three.pushbutton', 'Ctrl+Shift+3'),
             ('A.tab/P.panel/Four.pushbutton', None)]
    models = List[PushButtonModel]()
    for key, chord in specs:
        model = PushButtonModel()
        model.BundleKey = key
        model.Shortcut = chord
        models.Add(model)
    overrides = Dictionary[str, str]()
    overrides['A.tab/P.panel/Three.pushbutton'] = None
    overrides['A.tab/P.panel/Four.pushbutton'] = 'Alt+4'
    real = ShortcutMap.Build(models, overrides, False)
    ours, _problems = ribbon.resolve_bindings(
        [{'key': k, 'shortcut': c} for k, c in specs],
        {'A.tab/P.panel/Three.pushbutton': None, 'A.tab/P.panel/Four.pushbutton': 'Alt+4'})
    for model in models:
        chord = real.BindingFor(model)
        expected = str(chord) if chord is not None else None
        assert ours.get(model.BundleKey.lower()) == expected, model.BundleKey
    assert real.Count == len(ours)


def test_keys_agree_with_bundlekeys():
    _runtime_types()
    from PyNavis.Runtime.Bundles import BundleKeys
    for key in ['10_Tab.tab/02_Panel.panel/Thing.pushbutton', '1_Keep.pushbutton', 'Plain',
                'A.tab/003_B.panel/C_D.pushbutton']:
        assert ribbon.normalize_key(key) == BundleKeys.Normalize(key), key
