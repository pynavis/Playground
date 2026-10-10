# -*- coding: utf-8 -*-
"""Script Editor, Button Maker (form and WPF icons), Unit Converter, Playground Settings,
Team Sync and Extension Manager windows built under IronPython + WPF (never shown)."""
import io
import os

import _compat

_compat.require_ironpython()

from namo import buttonmaker as bm  # noqa: E402
from namo import converter, editor, extmanager, paths, png, team_settings, teamsync, ui  # noqa: E402

import test_editor  # noqa: E402


def _read(path):
    with io.open(path, encoding='utf-8', newline='') as handle:
        return handle.read()


def test_editor_opens_edits_saves_and_marks_errors():
    base = _compat.tmpdir('smoke_editor')
    ext = test_editor.make_extension(base)
    win = editor.build_window([{'name': 'MyTools', 'folder': ext, 'writable': True}])
    parts = win.Tag
    labels = [n['label'] for _d, n in parts.rows]
    assert labels[:2] == ['MyTools', 'MyTools']
    parts.tree_filter('script')
    labels = [n['label'] for _d, n in parts.rows]
    assert labels.count('script.py') == 3
    parts.tree_filter('')
    script = os.path.join(ext, 'MyTools.tab', 'Tools.panel', 'Count_Doors.pushbutton', 'script.py')
    assert parts.open_file(script)
    assert parts.box.Text.startswith('"""Counts doors."""') and not parts.dirty()
    parts.box.Text = parts.box.Text + 'if x\n    pass\n'
    assert parts.dirty() and win.Title.endswith('script.py *')
    assert parts.save()
    assert 'syntax error' in parts.status.Text and parts.error_line == 3
    assert _read(script).endswith('if x\r\n    pass\r\n') or _read(script).endswith('if x\n    pass\n')
    parts.box.Text = '"""Counts doors."""\nx = 1\nthing = 2\nthing.alpha = 3\n'
    assert parts.save() and parts.error_line is None and parts.status.Text == 'Saved script.py'
    parts.find_box.Text = 'thing'
    parts.box.CaretIndex = 0
    parts.find()
    assert parts.box.SelectedText == 'thing'
    parts.go_to_line(3)
    assert editor.line_of(parts.box.Text, parts.box.CaretIndex) == 3
    parts.box.CaretIndex = len(parts.box.Text)
    parts.box.SelectedText = 'thing.al'
    parts.box.CaretIndex = len(parts.box.Text)
    parts.show_completions(True)
    assert list(parts.completions.Items) == ['alpha']
    parts.accept_completion()
    assert parts.box.Text.endswith('thing.alpha')
    helpers = os.path.join(ext, 'lib', 'helpers.py')
    parts.save()                                     # else open_file would ask to save
    assert parts.open_file(helpers) and parts.box.Text.replace('\r', '') == 'X = 1\n'
    assert not parts.dirty()


def test_button_maker_form_validates_and_icons_render():
    root = _compat.tmpdir('smoke_buttonmaker')
    taken = {'Ctrl+Shift+P': 'Command Palette (Dev > Automate)'}
    fields = bm.form_fields({}, bm.existing_tabs(root))
    win = ui.build_form('Button Maker', fields,
                        validate=lambda values: bm.validate_spec(bm.spec_from(values), root, taken))
    state = win.Tag
    state.set_raw('title', 'Count doors')
    state.set_raw('shortcut', 'Ctrl+Shift+P')
    values, errors = state.collect()
    assert errors.get('shortcut') == 'Ctrl+Shift+P is already used by Command Palette (Dev > Automate).'
    state.set_raw('shortcut', 'Ctrl+Alt+D')
    values, errors = state.collect()
    assert errors == {} and values['title'] == 'Count doors'
    plan = bm.make(root, bm.spec_from(values))
    for name, size in (('icon.png', 96), ('icon.dark.png', 96), ('icon.small.png', 32), ('icon.small.dark.png', 32)):
        with open(os.path.join(plan['folder'], name), 'rb') as handle:
            assert png.image_size(handle.read()) == (size, size), name
    toggle = bm.make(root, bm.spec_from(dict(values, title='Switch', template='toggle', shortcut='', icon='bolt')))
    assert sorted(n for n in os.listdir(toggle['folder']) if n.endswith('.png')) == sorted([
        'icon.png', 'icon.dark.png', 'icon.small.png', 'icon.small.dark.png', 'icon.on.png', 'icon.on.dark.png',
        'icon.off.png', 'icon.off.dark.png'])
    picture = bm.make(root, bm.spec_from(dict(values, title='Picture', shortcut='', icon='png',
                                              png=os.path.join(plan['folder'], 'icon.png'))))
    with open(os.path.join(picture['folder'], 'icon.small.png'), 'rb') as handle:
        assert png.image_size(handle.read()) == (32, 32)
    for glyph in ('play', 'check', 'star', 'grid', 'keys'):
        out = os.path.join(root, 'glyph-%s.png' % glyph)
        bm._render(out, 96, bm.LIGHT, True, glyph, 'XX')
        assert os.path.getsize(out) > 200


def test_converter_window_converts_and_copies():
    folder = _compat.tmpdir('smoke_converter')
    previous = paths.redirect(folder)
    try:
        win = ui.window('Unit Converter', width=460)
        win.Content = converter.build(win, 'Feet', ['1 ft to mm = 304.8 mm'])
        parts = win.Tag
        assert parts.history_list.Items.Count == 1
        parts.box.Text = '250 sqft in m2'
        assert parts.result.Text == u'23.22576 m²'
        parts.box.Text = '10 ft to kg'
        assert parts.result.Text == '' and 'Cannot convert' in parts.secondary.Text
        parts.box.Text = '12 m2'
        parts.use_doc_units()
        assert parts.box.Text == '12 m2 to ft2'
        assert parts.result.Text.endswith(u'ft²')
        parts.box.Text = '100'
        parts.use_doc_units()
        assert ui.combo_value(parts.to_combo) == 'ft'
        parts.box.Text = '3 m to mm'
        parts.copy()
        assert parts.history_list.Items[0] == '3 m to mm = 3,000 mm'
        assert converter.load_history()[0] == '3 m to mm = 3,000 mm'
    finally:
        paths.redirect(previous)


def test_settings_form_validates():
    from namo import config
    folder = _compat.tmpdir('smoke_settings')
    previous = paths.redirect(folder)
    try:
        win = ui.build_form('Playground Settings', team_settings.fields(config.load()),
                            validate=lambda values: team_settings.validate(values))
        state = win.Tag
        state.set_raw('trade_rules', 'no equals sign')
        _values, errors = state.collect()
        assert errors.get('trade_rules') == 'Line 1: write it as pattern = Trade.'
        state.set_raw('trade_rules', '\\bmep\\b = Mechanical')
        values, errors = state.collect()
        assert errors == {}
        saved = config.save(team_settings.to_config(values))
        assert saved['trade_rules'] == [['\\bmep\\b', 'Mechanical']]
    finally:
        paths.redirect(previous)


def test_team_sync_window():
    win = teamsync.build_window('\\\\srv\\team', {'count': 2, 'lines': ['Templates: 2 added'], 'stamp': '2026-10-05T10:00:00'},
                                {'auto_pull': True, 'last_pull': ''})
    parts = win.Tag
    assert parts.pull_button.IsEnabled and parts.push_button.IsEnabled and parts.auto.IsChecked
    parts.auto.IsChecked = False
    parts.finish('pull')
    assert parts.action == 'pull' and parts.auto_pull is False
    win = teamsync.build_window('', {'error': 'Set the team folder first.'}, {})
    assert not win.Tag.pull_button.IsEnabled and not win.Tag.push_button.IsEnabled


def test_extension_manager_table():
    rows = extmanager.status_rows([{'name': 'Acme', 'version': '2.0', 'author': 'A', 'description': 'Tools'}],
                                  [{'name': 'Acme', 'version': '1.0', 'folder': 'x'}])
    win = ui.build_table('Extension Manager', ['Extension', 'Available', 'Installed', 'Status', 'Author', 'About'],
                         rows, [{'label': 'Install', 'fn': lambda v: None, 'primary': True}], status='1 extension')
    state = win.Tag
    assert state.table.total() == 1 and state.status_block.Text == '1 extension'
