# -*- coding: utf-8 -*-
"""Regression tests from the refit pass over the Dev tools (G11): one per real bug."""
import io
import json
import os

import _compat

from namo import buttonmaker as bm
from namo import extmanager, hooks, hotkeys, macros, paths, teamsync, ui

EXT = os.path.join(_compat.ROOT, 'Playground.extension')


# ---- Button Maker: the form's options are (label, value) -------------------------------


def _field(fields, key):
    return [f for f in fields if f.get('key') == key][0]


def test_button_maker_form_hands_back_template_and_glyph_ids():
    # The options were written (value, label): the form returned 'Selection tool' as the
    # template and the first click ended in "unknown template".
    fields = bm.form_fields({}, [])
    templates = [value for _label, value in ui.options_of(_field(fields, 'template'))]
    assert templates == ['selection', 'report', 'toggle', 'file']
    assert list(bm.TEMPLATE_IDS) == templates
    glyphs = [value for _label, value in ui.options_of(_field(fields, 'icon'))]
    assert set(glyphs) <= set(bm.GLYPHS) and 'letters' in glyphs and 'png' in glyphs
    for label, _value in ui.options_of(_field(fields, 'template')) + ui.options_of(_field(fields, 'icon')):
        assert label[:1].isupper(), label
    # every default and every enabled_if value is one the options can produce
    assert _field(fields, 'template')['default'] in templates
    assert _field(fields, 'icon')['default'] in glyphs
    for field in fields:
        condition = field.get('enabled_if')
        if condition:
            values = [v for _l, v in ui.options_of(_field(fields, condition[0]))]
            assert condition[1] in values, field['key']
    # and what the form hands back makes a script for every template but 'file'
    for template in templates:
        spec = bm.spec_from({'title': 'Count Doors', 'template': template, 'tab': 'MyTools',
                             'panel': 'Tools', 'icon': 'letters'})
        if template != 'file':
            source = bm.script_source(spec['template'], spec['title'], spec['tooltip'])
            compile(source, 'script.py', 'exec')


def test_generated_templates_use_real_plurals():
    for template in ('selection', 'report'):
        assert 'item(s)' not in bm.script_source(template, 'T', 'Tip.')


# ---- macros and the palette: views and sets found by their exact stored path ------------


def test_views_with_a_slash_in_the_name_are_found():
    views = [('', 'Overview', 'a'), ('Levels', 'Level 1/2', 'b'), ('', 'North / East', 'c'),
             ('Levels/Deep', 'Core', 'd')]
    assert macros.match_view(macros.view_path('', 'North / East'), views) == 'c'
    assert macros.match_view(macros.view_path('Levels', 'Level 1/2'), views) == 'b'
    assert macros.match_view('Levels/Deep/Core', views) == 'd'
    assert macros.match_view('Nope', views) is None


def test_a_set_step_never_resolves_to_a_folder():
    rows = [
        {'key': '0', 'parent_key': '', 'name': 'Ducts', 'is_folder': True},
        {'key': '0/0', 'parent_key': '0', 'name': 'Level 1', 'is_folder': False},
        {'key': '1', 'parent_key': '', 'name': 'Ducts', 'is_folder': False},
        {'key': '2', 'parent_key': '', 'name': 'A/B', 'is_folder': False},
    ]
    assert macros.match_set('Ducts', rows)['key'] == '1'            # the set, not the folder
    assert macros.match_set('Ducts/Level 1', rows)['key'] == '0/0'
    assert macros.match_set('Level 1', rows)['key'] == '0/0'        # a bare name looks in folders
    assert macros.match_set(macros.set_path(['A/B']), rows)['key'] == '2'
    assert macros.match_set('Missing', rows) is None
    assert macros.match_set('Ducts', rows[:1]) is None              # only a folder has that name


def test_shift_click_runs_are_not_recorded():
    from namo import session
    key = 'A.tab/B.panel/C.pushbutton'
    real = macros._was_config_run
    session.clear(macros.REC)
    try:
        macros.start_recording()
        macros._was_config_run = lambda: True
        assert macros.record_command(key) is False
        macros._was_config_run = lambda: False
        assert macros.record_command(key) is True
        assert [s['key'] for s in macros.snapshot_steps()] == [key]
    finally:
        macros._was_config_run = real
        session.clear(macros.REC)


# ---- config.json: bindings go through pyNavis' own saver when it is loaded ---------------

CONFIG = (u'{\n  "extensions": [\n    "D:\\\\Dev\\\\ext"\n  ],\n  "runtime2026": "C:\\\\x",\n'
          u'  "shortcuts": {\n    "allowBareKeys": true,\n    "bindings": {\n'
          u'      "A.tab/P.panel/Keep.pushbutton": "Ctrl+Alt+K",\n'
          u'      "A.tab/P.panel/Off.pushbutton": null\n    }\n  },\n'
          u'  "future": {\n    "unknown": [\n      1,\n      2\n    ]\n  }\n}\r\n')


def _write(path, text):
    with io.open(path, 'w', encoding='utf-8', newline='') as handle:
        handle.write(text)


def _read(path):
    with io.open(path, encoding='utf-8', newline='') as handle:
        return handle.read()


def test_bindings_save_keeps_every_other_key():
    folder = _compat.tmpdir('refit_bindings')
    path = os.path.join(folder, 'config.json')
    _write(path, CONFIG)
    hotkeys.save_bindings(path, {'A.tab/P.panel/New.pushbutton': 'Ctrl+Alt+N'}, {})
    data = json.loads(_read(path))
    before = json.loads(CONFIG)
    assert data['shortcuts']['bindings'] == {'A.tab/P.panel/Keep.pushbutton': 'Ctrl+Alt+K',
                                             'A.tab/P.panel/Off.pushbutton': None,
                                             'A.tab/P.panel/New.pushbutton': 'Ctrl+Alt+N'}
    assert data['shortcuts']['allowBareKeys'] is True
    for key in ('extensions', 'runtime2026', 'future'):
        assert data[key] == before[key], key
    assert [n for n in os.listdir(folder) if n != 'config.json'] == []      # no temp file left


def test_runtime_saver_and_python_writer_write_the_same_file():
    _compat.require_ironpython()
    folder = _compat.tmpdir('refit_bindings_same')
    a, b = os.path.join(folder, 'a.json'), os.path.join(folder, 'b.json')
    _write(a, CONFIG)
    _write(b, CONFIG)
    changes = {'A.tab/P.panel/New.pushbutton': 'Ctrl+Alt+N', 'A.tab/P.panel/Keep.pushbutton': None}
    root, _error = hotkeys.read_config(a)
    hotkeys.apply_binding_changes(root, changes, {})
    assert hotkeys._runtime_save_bindings(a, hotkeys.overrides_of(root)) is True
    root_b, _error = hotkeys.read_config(b)
    hotkeys.apply_binding_changes(root_b, changes, {})
    hotkeys.write_config(b, root_b)
    assert _read(a) == _read(b)
    # an unparsable file is refused by the runtime too, never overwritten
    _write(a, u'{ not json')
    raised = _compat.raises(IOError, hotkeys._runtime_save_bindings, a, {})
    assert 'not valid JSON' in str(raised)
    assert _read(a) == u'{ not json'


# ---- Extension Manager and Team Sync wording --------------------------------------------


def test_extension_manager_status_line():
    entries = [{'name': 'A'}, {'name': 'B'}]
    assert extmanager.status_text(entries, []) == '2 extensions in the registry'
    assert extmanager.status_text(entries[:1], ['B has no download.']) == \
        '1 extension in the registry; 1 entry skipped: B has no download.'
    notice = 'No registry is set. Shift+Click Extension Manager to choose one.'
    assert extmanager.status_text([], [], notice) == notice            # not "1 entry skipped"
    assert extmanager.status_text([], [], notice, changed=1) == \
        'No registry is set. Shift+Click Extension Manager to choose one; pyNavis reloads when you close this window'


def test_team_sync_says_when_the_folder_is_offline():
    base = _compat.tmpdir('refit_teamsync')
    previous = paths.redirect(base)
    try:
        found = teamsync.preview(os.path.join(base, 'not-there'))
        assert found.get('unreachable') and 'cannot be reached right now' in found['error']
        found = teamsync.preview(base)
        assert not found.get('unreachable') and 'There is no playground-team folder' in found['error']
    finally:
        paths.redirect(previous)


# ---- hooks: nothing escapes a hook file or the dispatcher ---------------------------------


def test_hook_files_and_startup_never_raise():
    files = [os.path.join(EXT, 'startup.py')]
    folder = os.path.join(EXT, 'hooks')
    files += [os.path.join(folder, name) for name in sorted(os.listdir(folder)) if name.endswith('.py')]
    assert len(files) >= 9
    for path in files:
        with io.open(path, encoding='utf-8') as handle:
            source = handle.read()
        # No __event__ in these globals: the body fails, and the file must swallow it.
        exec(compile(source, path, 'exec'), {'__file__': path})


def test_dispatch_survives_a_raising_and_a_missing_handler():
    from namo import hk_macro
    real_handlers, real_handle = hooks.HANDLERS, hk_macro.handle
    seen = []

    def boom(name, event):
        seen.append(name)
        raise RuntimeError('broken tool')
    try:
        hooks.HANDLERS = [('refit-test', 'hk_macro'), ('refit-test', 'hk_not_written_yet')]
        hk_macro.handle = boom
        hooks.dispatch('refit-test', {'name': 'refit-test'})         # must not raise
        import namo
        namo.hk_macro.handle = boom
        hooks.dispatch('refit-test', None)
        assert seen and set(seen) == set(['refit-test'])
    finally:
        hooks.HANDLERS = real_handlers
        hk_macro.handle = real_handle


# ---- startup: the Team Sync check costs one small file read when it is off ----------------


def test_startup_check_reads_the_flag_without_teamsync():
    from namo import hk_teamsync
    assert hk_teamsync.STATE_FILE == teamsync.STATE_FILE
    base = _compat.tmpdir('refit_startup_flag')
    assert hk_teamsync.auto_pull_on(base) is False                  # no file: off
    path = os.path.join(base, hk_teamsync.STATE_FILE)
    _write(path, u'{"auto_pull": false, "team_folder": "X"}')
    assert hk_teamsync.auto_pull_on(base) is False
    _write(path, u'{"auto_pull": true, "team_folder": "X"}')
    assert hk_teamsync.auto_pull_on(base) is True
    _write(path, u'{ damaged')
    assert hk_teamsync.auto_pull_on(base) is True                   # teamsync decides
    hk_teamsync.handle('doc-opened', {})                            # not its event: nothing
    hk_teamsync.handle('startup', {'runner': True})                 # under pynavis run: nothing
