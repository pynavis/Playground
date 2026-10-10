# -*- coding: utf-8 -*-
"""namo.hotkeys: config.json edits (against temp copies only), the editor model and the
generated native-command bundles. Under IronPython, pyNavis' own PyNavisConfig.Load and
BundleParser read the files back."""
import collections
import io
import json
import os

import _compat

from namo import buttonmaker, hotkeys

ORIGINAL = (u'{\n  "extensions": [\n    "D:\\\\Dev\\\\ext"\n  ],\n  "runtime2026": "C:\\\\x",\n'
            u'  "theme": "dark",\n  "shortcuts": {\n    "allowBareKeys": false,\n'
            u'    "bindings": {\n      "pyNavis.tab/Selection.panel/Remember.pushbutton": "Ctrl+Alt+M",\n'
            u'      "01_A.tab/P.panel/Old.pushbutton": "Ctrl+Alt+O",\n'
            u'      "A.tab/P.panel/Off.pushbutton": null\n    }\n  },\n'
            u'  "panes": {\n    "assignments": {\n      "X.tab/Y.panel/Z.dockpane": 2\n    }\n  },\n'
            u'  "note": "caf\u00e9"\n}\r\n')


def _write(path, text):
    with io.open(path, 'w', encoding='utf-8', newline='') as handle:
        handle.write(text)


def _read(path):
    with io.open(path, encoding='utf-8', newline='') as handle:
        return handle.read()


def test_read_and_dump_keep_order_and_layout():
    folder = _compat.tmpdir('hotkeys_roundtrip')
    path = os.path.join(folder, 'config.json')
    _write(path, ORIGINAL)
    root, error = hotkeys.read_config(path)
    assert error is None
    assert list(root.keys()) == ['extensions', 'runtime2026', 'theme', 'shortcuts', 'panes', 'note']
    assert hotkeys.dumps_config(root) == ORIGINAL       # byte for byte, JsonPretty's layout
    assert hotkeys.allow_bare_of(root) is False
    overrides = hotkeys.overrides_of(root)
    assert overrides['A.tab/P.panel/Off.pushbutton'] is None
    assert hotkeys.override_for(overrides, 'A.tab/P.panel/OLD.pushbutton') == (True, 'Ctrl+Alt+O')
    assert hotkeys.override_for(overrides, 'Nope') == (False, None)


def test_missing_empty_and_broken_files():
    folder = _compat.tmpdir('hotkeys_broken')
    missing = os.path.join(folder, 'missing.json')
    assert hotkeys.read_config(missing) == (collections.OrderedDict(), None)
    empty = os.path.join(folder, 'empty.json')
    _write(empty, '   \n')
    assert hotkeys.read_config(empty)[1] is None
    broken = os.path.join(folder, 'broken.json')
    _write(broken, '{"a": 1,}')
    root, error = hotkeys.read_config(broken)
    assert root is None and 'is not valid JSON' in error
    raised = _compat.raises(IOError, hotkeys.save_bindings, broken, {'K': 'Ctrl+K'}, {})
    assert 'not valid JSON' in str(raised)
    assert _read(broken) == '{"a": 1,}'                  # never overwritten
    hotkeys.save_bindings(missing, {'A.tab/P.panel/New.pushbutton': 'Ctrl+Alt+N'}, {})
    assert json.loads(_read(missing)) == {'shortcuts': {'bindings': {'A.tab/P.panel/New.pushbutton': 'Ctrl+Alt+N'}}}


def test_apply_changes_touches_only_its_keys():
    folder = _compat.tmpdir('hotkeys_apply')
    path = os.path.join(folder, 'config.json')
    _write(path, ORIGINAL)
    defaults = {'A.tab/P.panel/Old.pushbutton': 'Ctrl+Shift+O',
                'A.tab/P.panel/Def.pushbutton': 'Ctrl+Shift+D',
                'A.tab/P.panel/Off.pushbutton': 'Ctrl+Shift+F',
                'A.tab/P.panel/Plain.pushbutton': None}
    changes = {'A.tab/P.panel/Old.pushbutton': 'Ctrl+Alt+Q',     # replaces the 01_ spelling
               'A.tab/P.panel/Def.pushbutton': None,             # disables its default
               'A.tab/P.panel/Off.pushbutton': 'Ctrl+Shift+F',   # back to default: removed
               'A.tab/P.panel/Plain.pushbutton': None}           # no default: nothing written
    hotkeys.save_bindings(path, changes, defaults)
    root, _error = hotkeys.read_config(path)
    assert list(root.keys()) == ['extensions', 'runtime2026', 'theme', 'shortcuts', 'panes', 'note']
    bindings = root['shortcuts']['bindings']
    assert list(bindings.items()) == [
        ('pyNavis.tab/Selection.panel/Remember.pushbutton', 'Ctrl+Alt+M'),
        ('A.tab/P.panel/Def.pushbutton', None),
        ('A.tab/P.panel/Old.pushbutton', 'Ctrl+Alt+Q')]
    assert root['shortcuts']['allowBareKeys'] is False
    assert root['panes'] == {'assignments': {'X.tab/Y.panel/Z.dockpane': 2}}
    assert root['note'] == u'caf\u00e9'
    # Removing the last binding removes the section; the shortcuts block keeps allowBareKeys.
    hotkeys.save_bindings(path, {'pyNavis.tab/Selection.panel/Remember.pushbutton': None,
                                 'A.tab/P.panel/Def.pushbutton': 'Ctrl+Shift+D',
                                 'A.tab/P.panel/Old.pushbutton': 'Ctrl+Shift+O'},
                          defaults)
    root, _error = hotkeys.read_config(path)
    assert root['shortcuts'] == {'allowBareKeys': False}
    root = collections.OrderedDict([('shortcuts', collections.OrderedDict([('bindings', {'K': 'Ctrl+K'})]))])
    hotkeys.apply_binding_changes(root, {'K': None}, {})
    assert 'shortcuts' not in root


def test_model_set_clear_reset_and_conflicts():
    rows = [
        {'key': 'A/One.pushbutton', 'kind': 'bundle', 'title': 'One', 'path': 'x', 'default': 'Ctrl+Shift+1', 'current': 'Ctrl+Shift+1'},
        {'key': 'A/Two.pushbutton', 'kind': 'bundle', 'title': 'Two', 'path': 'x', 'default': None, 'current': None},
        {'key': 'B/X.pushbutton', 'kind': 'bundle', 'title': 'Old X', 'path': 'x', 'default': 'Ctrl+9', 'current': 'Ctrl+9'},
        {'key': 'B/Y.pushbutton', 'kind': 'bundle', 'title': 'Old Y', 'path': 'x', 'default': 'Ctrl+9', 'current': 'Ctrl+9'},
        {'key': 'native:T/sel', 'kind': 'native', 'title': 'Select', 'path': 'Navisworks', 'default': None, 'current': None},
    ]
    model = hotkeys.HotkeyModel(rows)
    assert model.conflicts() == {'b/y.pushbutton': 'Old X'}
    assert model.blocking_conflicts() == {}              # an old conflict never blocks
    assert not model.can_save()
    assert model.set('A/Two.pushbutton', 'Shift+T') == 'A shortcut needs Ctrl or Alt.'
    assert model.set('Nope', 'Ctrl+T') == 'That command is no longer listed.'
    assert model.set('a/two.PUSHBUTTON', 'ctrl+shift+1') is None
    assert model.row('A/Two.pushbutton')['current'] == 'Ctrl+Shift+1'
    assert model.blocking_conflicts() == {'a/two.pushbutton': 'One'}
    assert not model.can_save()
    assert model.note('A/Two.pushbutton') == 'Taken by One'
    model.clear('A/One.pushbutton')
    assert model.can_save()
    assert model.note('A/One.pushbutton') == 'Changed'
    assert model.set('native:T/sel', 'Alt+S') is None
    assert model.changes('bundle') == {'A/One.pushbutton': None, 'A/Two.pushbutton': 'Ctrl+Shift+1'}
    assert model.changes('native') == {'native:T/sel': 'Alt+S'}
    model.reset('A/One.pushbutton')
    assert model.row('A/One.pushbutton')['current'] == 'Ctrl+Shift+1'
    assert model.defaults()['A/One.pushbutton'] == 'Ctrl+Shift+1'
    assert 'fix 1 conflict to save' in hotkeys.status_text(model)
    cells = hotkeys.table_rows(model, 'bound')
    assert [c['value'] for c in cells] == ['A/One.pushbutton', 'A/Two.pushbutton', 'B/X.pushbutton',
                                           'B/Y.pushbutton', 'native:T/sel']


def test_bundle_rows_follow_shortcutsmodel():
    commands = [
        {'key': 'A.tab/P.panel/One.pushbutton', 'title': 'One', 'default': 'ctrl+shift+1', 'extension': 'E', 'path': 'A > P'},
        {'key': 'A.tab/P.panel/Two.pushbutton', 'title': 'Two', 'default': 'Ctrl+2', 'extension': 'E', 'path': 'A > P'},
        {'key': 'A.tab/P.panel/Three.pushbutton', 'title': 'Three', 'default': 'Ctrl+3', 'extension': 'E', 'path': 'A > P'},
        {'key': 'a.tab/p.panel/one.pushbutton', 'title': 'Dup', 'default': None, 'extension': 'F', 'path': ''},
        {'key': 'M.tab/Hotkeys.panel/Sel.nobutton', 'title': 'Sel', 'default': 'Alt+S', 'extension': 'MyTools', 'path': ''},
    ]
    overrides = {'A.tab/P.panel/Two.pushbutton': None, '01_A.tab/P.panel/Three.pushbutton': 'Shift+bad'}
    rows = hotkeys.bundle_rows(commands, overrides, ['M.tab/Hotkeys.panel/Sel.nobutton'])
    assert [(r['title'], r['default'], r['current']) for r in rows] == [
        ('One', 'Ctrl+Shift+1', 'Ctrl+Shift+1'), ('Two', 'Ctrl+2', None), ('Three', 'Ctrl+3', 'Ctrl+3')]
    assert rows[0]['path'] == 'E > A > P'
    natives = hotkeys.native_rows([{'key': 'native:T/a', 'title': 'Orbit', 'path': 'Viewpoint > Navigate'}],
                                  {'native:t/a': 'Alt+O'})
    assert natives == [{'key': 'native:T/a', 'kind': 'native', 'title': 'Orbit',
                        'path': 'Navisworks > Viewpoint > Navigate', 'default': None,
                        'current': 'Alt+O', 'extension': 'Navisworks'}]


def test_native_bundles_add_rechord_remove():
    root = _compat.tmpdir('hotkeys_native')
    trash_root = os.path.join(root, 'trash')
    lib = buttonmaker.namo_lib_folder()
    rows = {'native:id_tabhome/id_select': {'title': 'Select', 'path': 'Navisworks > Home > Select'},
            'native:id_tabhome/id_select2': {'title': 'Select', 'path': 'Navisworks > Item Tools'}}
    added = hotkeys.apply_native_changes(root, {'native:ID_TabHome/ID_Select': 'Ctrl+Alt+1',
                                                'native:ID_TabHome/ID_Select2': 'Ctrl+Alt+2'},
                                         rows, trash_root, lib, make_icons=False)
    assert added == (2, 0, 0)
    found = hotkeys.scan_native_bundles(root)
    assert sorted(found) == ['native:id_tabhome/id_select', 'native:id_tabhome/id_select2']
    first = found['native:id_tabhome/id_select']
    assert first['chord'] == 'Ctrl+Alt+1' and first['title'] == 'Select'
    assert first['key'] == 'MyTools.tab/Hotkeys.panel/Select.nobutton'
    assert found['native:id_tabhome/id_select2']['key'] == 'MyTools.tab/Hotkeys.panel/Select_2.nobutton'
    panel = hotkeys.hotkeys_panel(root)
    layout = buttonmaker.read_flat_yaml(_read(os.path.join(panel, 'bundle.yaml')))[1]
    assert layout == ['Hotkeys', 'Select', 'Select_2']
    assert os.path.isfile(os.path.join(panel, 'Hotkeys.pushbutton', 'script.py'))
    script = _read(os.path.join(first['folder'], 'script.py'))
    compile(script, 'script.py', 'exec')
    assert "COMMAND = 'native:ID_TabHome/ID_Select'" in script
    changed = hotkeys.apply_native_changes(root, {'native:ID_TabHome/ID_Select': 'Ctrl+Alt+9',
                                                  'native:ID_TabHome/ID_Select2': None},
                                           rows, trash_root, lib, make_icons=False)
    assert changed == (0, 1, 1)
    found = hotkeys.scan_native_bundles(root)
    assert list(found) == ['native:id_tabhome/id_select']
    assert found['native:id_tabhome/id_select']['chord'] == 'Ctrl+Alt+9'
    layout = buttonmaker.read_flat_yaml(_read(os.path.join(panel, 'bundle.yaml')))[1]
    assert layout == ['Hotkeys', 'Select']
    trashed = os.listdir(trash_root)
    assert len(trashed) == 1 and trashed[0].endswith(' Select_2.nobutton')


def test_pynavis_reads_what_we_wrote():
    _compat.require_ironpython()
    import clr
    clr.AddReference('PyNavis.Runtime')
    from PyNavis.Runtime.Bundles import BundleParser
    from PyNavis.Runtime.Config import PyNavisConfig
    folder = _compat.tmpdir('hotkeys_pynavis')
    path = os.path.join(folder, 'config.json')
    _write(path, ORIGINAL)
    hotkeys.save_bindings(path, {'A.tab/P.panel/Old.pushbutton': 'Ctrl+Alt+Q',
                                 'A.tab/P.panel/Def.pushbutton': None},
                          {'A.tab/P.panel/Def.pushbutton': 'Ctrl+Shift+D'})
    cfg = PyNavisConfig.Load(path)
    assert list(cfg.ExtensionPaths) == ['D:\\Dev\\ext'] and cfg.Theme == 'dark'
    assert cfg.ShortcutBindings['A.tab/P.panel/Old.pushbutton'] == 'Ctrl+Alt+Q'
    assert cfg.ShortcutBindings['A.tab/P.panel/Def.pushbutton'] is None
    assert cfg.ShortcutBindings['pyNavis.tab/Selection.panel/Remember.pushbutton'] == 'Ctrl+Alt+M'
    assert cfg.PaneAssignments['X.tab/Y.panel/Z.dockpane'] == 2
    root = _compat.tmpdir('hotkeys_pynavis_bundles')
    hotkeys.apply_native_changes(root, {'native:T/A': 'Ctrl+Alt+A'}, {}, os.path.join(root, 'trash'),
                                 buttonmaker.namo_lib_folder(), make_icons=False)
    ext = list(BundleParser.ParseRoot(root))[0]
    assert list(ext.Problems) == []
    panel = list(list(ext.Tabs)[0].Panels)[0]
    buttons = list(panel.Buttons)
    assert [(b.Title, b.NoUi, b.Shortcut) for b in buttons] == [('Hotkeys', False, None),
                                                                ('native:T/A', True, 'Ctrl+Alt+A')]
