# -*- coding: utf-8 -*-
"""namo.ui under IronPython + WPF: every window type built with sample data, wired,
driven through its state objects, never shown."""
import _compat

_compat.require_ironpython()

import os  # noqa: E402

from namo import ui  # noqa: E402


ALL_FIELDS = [
    {'kind': 'label', 'text': 'Pick what to export.'},
    {'kind': 'text', 'key': 'name', 'label': 'Name', 'default': 'Report', 'required': True,
     'placeholder': 'A name'},
    {'kind': 'textarea', 'key': 'notes', 'label': 'Notes', 'rows': 3},
    {'kind': 'int', 'key': 'count', 'label': 'Count', 'default': 5, 'min': 1, 'max': 10},
    {'kind': 'number', 'key': 'scale', 'label': 'Scale', 'default': 1.5, 'suffix': 'x'},
    {'kind': 'length', 'key': 'gap', 'label': 'Gap', 'default': 0.5},
    {'kind': 'choice', 'key': 'fmt', 'label': 'Format', 'options': [('Excel', 'xlsx'), ('CSV', 'csv')],
     'default': 'csv'},
    {'kind': 'radio', 'key': 'scope', 'label': 'Scope', 'options': ['All', 'Selection'], 'inline': True},
    {'kind': 'check', 'key': 'open', 'label': 'Open when done', 'default': True},
    {'kind': 'multi', 'key': 'cats', 'label': 'Categories',
     'options': ['Ducts', 'Pipes', 'Walls', 'Doors', 'Floors', 'Roofs', 'Stairs', 'Columns', 'Beams'],
     'default': ['Pipes']},
    {'kind': 'separator'},
    {'kind': 'file_open', 'key': 'src', 'label': 'Source', 'filter': 'Excel (*.xlsx)|*.xlsx'},
    {'kind': 'file_save', 'key': 'dst', 'label': 'Save as', 'default_name': 'out.xlsx'},
    {'kind': 'folder', 'key': 'dir', 'label': 'Folder', 'enabled_if': ('open', True)},
    {'kind': 'color', 'key': 'tint', 'label': 'Color', 'default': '4E79A7'},
    {'kind': 'date', 'key': 'due', 'label': 'Due'},
]


def test_theme_and_palette():
    resources = ui.theme_resources()
    for key in ('namo.focus', 'namo.grid', 'namo.header', 'namo.row', 'namo.cell',
                'namo.celltext', 'namo.cellnum', 'namo.checkcell'):
        assert resources[key] is not None, key
    colors = ui.palette()
    assert colors['paper'].startswith('#') and len(colors['accent']) == 7
    for dark in (False, True):
        ui.theme_xaml(ui.palette(ui.tokens(dark)))


def test_parts_build():
    win = ui.window('Parts', 400)
    shell, box = ui.text_box('abc', placeholder='Type', suffix='mm')
    assert box.Text == 'abc'
    box.Text = ''
    element, search = ui.search_box('Filter', lambda q: None)
    control = ui.combo(['a', ('Bee', 'b')], selected='b')
    assert ui.combo_value(control) == 'b'
    panel, radios = ui.radio_group(['x', 'y'], selected='y')
    assert ui.radio_value(radios, ui.options_of({'options': ['x', 'y']})) == 'y'
    tick = ui.check('Tick', True)
    assert tick.IsChecked
    for kind in ('primary', 'secondary', 'quiet', 'danger'):
        ui.button(kind.title(), lambda: None, kind)
    _compat.raises(ValueError, ui.button, 'X', None, 'loud')
    bar = ui.footer([ui.button('OK', None, 'primary')], left=ui.hint('left'))
    frame = ui.group('Group', ui.text('inside'))
    from System.Windows.Controls import StackPanel
    stack = StackPanel()
    for child in (shell, element, control, panel, tick, bar, frame, ui.separator(), ui.heading('H')):
        stack.Children.Add(child)
    win.Content = ui.scroll(stack, 300)
    assert win.Content is not None


def test_form_builds_every_kind_and_collects():
    win = ui.build_form('Export', ALL_FIELDS, intro='Choose the options.', units='Meters')
    state = win.Tag
    keys = sorted(state.controls)
    assert keys == sorted(f['key'] for f in ALL_FIELDS if f.get('key'))
    folder = _compat.tmpdir('smoke_ui_form')
    src = os.path.join(folder, 'in.xlsx')
    open(src, 'w').close()
    state.set_raw('src', src)
    state.set_raw('dst', os.path.join(folder, 'out.xlsx'))
    state.set_raw('dir', folder)
    state.set_raw('due', '2026-10-05')
    state.set_raw('gap', '25mm')
    values, errors = state.collect()
    assert errors == {}, errors
    assert values['name'] == 'Report'
    assert values['count'] == 5 and values['scale'] == 1.5
    assert abs(values['gap'] - 0.025) < 1e-9
    assert values['fmt'] == 'csv' and values['scope'] == 'All' and values['open'] is True
    assert values['cats'] == ['Pipes']
    assert values['tint'] == '4E79A7' and values['due'] == '2026-10-05'
    assert values['src'] == src
    # accept() on an unshown window closes it and keeps the result
    assert state.accept()
    assert state.accepted and state.result['name'] == 'Report'


def test_form_inline_errors_and_enabled_if():
    win = ui.build_form('Errors', ALL_FIELDS, units='Feet')
    state = win.Tag
    state.set_raw('name', '   ')
    state.set_raw('count', '40')
    state.set_raw('gap', 'banana')
    state.set_raw('tint', 'nope')
    state.set_raw('due', '05/10/2026')
    state.set_raw('src', r'C:\definitely\missing.xlsx')
    assert not state.accept()
    values, errors = state.collect()
    for key in ('name', 'count', 'gap', 'tint', 'due', 'src'):
        assert key in errors, key
    assert 'between 1 and 10' in errors['count']
    # the folder field follows the check box
    state.set_raw('open', False)
    assert not state.controls['dir'].enabled()
    state.set_raw('open', True)
    assert state.controls['dir'].enabled()
    # feet-and-inches lengths read through pynavis.lengths
    state.set_raw('gap', "1' 6\"")
    values, errors = state.collect()
    assert 'gap' not in errors and abs(values['gap'] - 1.5) < 1e-9


def test_form_small_length_default_does_not_open_as_zero():
    # half a millimetre in a feet document: pynavis.lengths.format_input gives 0' 0"
    from pynavis import lengths
    half_mm = 0.0005 / 0.3048
    assert lengths.parse(lengths.format_input(half_mm, 'Feet'), 'Feet') == 0.0
    win = ui.build_form('Small', [{'kind': 'length', 'key': 'tol', 'default': half_mm}], units='Feet')
    values, errors = win.Tag.collect()
    assert not errors and abs(values['tol'] - half_mm) < 0.01 * half_mm, win.Tag.raws()


def test_form_multi_filter_and_ticks():
    win = ui.build_form('Multi', ALL_FIELDS, units='Meters')
    table = win.Tag.controls['cats'].table
    assert table.total() == 9
    table.set_filter('oo')
    assert sorted(table.rows[i]['cells'][0] for i in table.visible_indices()) == ['Doors', 'Floors', 'Roofs']
    table.set_checked(None, True, visible_only=True)
    table.set_filter('')
    assert table.checked_values() == ['Pipes', 'Doors', 'Floors', 'Roofs']
    win.Tag.set_raw('cats', ['Walls'])
    assert win.Tag.collect()[0]['cats'] == ['Walls']


def test_form_validate_hook():
    fields = [{'kind': 'int', 'key': 'a', 'default': 1}, {'kind': 'int', 'key': 'b', 'default': 1}]
    win = ui.build_form('Hook', fields, validate=lambda v: None if v['a'] < v['b'] else {'b': 'B must be bigger.'})
    assert not win.Tag.accept()
    win.Tag.set_raw('b', '5')
    assert win.Tag.accept()


def _rows(count=50):
    return [{'value': 'v%d' % i, 'cells': ['Item %d' % i, i * 10, 'Level %d' % (i % 12)]}
            for i in range(count)]


def test_choose_multi():
    win = ui.build_choose('Pick', _rows(), ['Name', 'Count', 'Level'], multiselect=True,
                          checked=['v3', 'v7'], prompt='Tick some.')
    state = win.Tag
    assert state.values() == ['v3', 'v7']
    state.table.set_filter('item 1')
    visible = state.table.visible_indices()
    expected = [i for i, row in enumerate(state.table.rows)
                if ui.matches('item 1', ui.search_text(row['cells']))]
    assert sorted(visible) == expected and 0 < len(visible) < 50
    state.table.set_checked(None, True, visible_only=True)
    state.table.set_filter('')
    ticked = set(expected) | set([3, 7])
    assert len(state.table.checked_values()) == len(ticked)
    state.table._toggle([3])
    assert 'v3' not in state.table.checked_values()
    assert state.table.numeric == [False, True, False]
    assert state.accept() and len(state.result) == len(ticked) - 1


def test_choose_single_and_empty():
    win = ui.build_choose('One', _rows(5), ['Name', 'Count', 'Level'], multiselect=False, checked=['v2'])
    state = win.Tag
    assert state.values() == ['v2']
    assert state.accept() and state.result == ['v2']
    empty = ui.build_choose('None', [], ['Name'], multiselect=True)
    assert not empty.Tag.accept()


def _logged_errors(build):
    """Runs build() and returns every error namo.ui logged meanwhile (a callback that
    raises is swallowed by ui.safe and only logged, so a bare build looks fine)."""
    seen = []
    original = ui.log_error
    ui.log_error = lambda message, logger=None: seen.append(message)
    try:
        build()
    finally:
        ui.log_error = original
    return seen


def test_choose_single_checked_runs_no_callback_before_its_def():
    # Level Sectioner in Navisworks: a single-select chooser opened on a row fired the
    # table's change callback before refresh_footer existed (NameError, free variable).
    errors = _logged_errors(lambda: ui.build_choose('One', _rows(5), ['Name', 'Count', 'Level'],
                                                    multiselect=False, checked=['v2']))
    assert not errors, errors
    errors = _logged_errors(lambda: ui.build_choose('Many', _rows(5), ['Name', 'Count', 'Level'],
                                                    multiselect=True, checked=['v1', 'v3']))
    assert not errors, errors


def test_choose_filter_survives_special_characters():
    rows = [{'value': i, 'cells': [text]} for i, text in enumerate(
        ["50% done", "it's", "[draft]", "a*b", "plain"])]
    win = ui.build_choose('Odd', rows, ['Name'])
    table = win.Tag.table
    for query, expected in (('50%', [0]), ("it's", [1]), ('[draft', [2]), ('a*b', [3]), ('lai', [4])):
        table.set_filter(query)
        assert table.visible_indices() == expected, (query, table.visible_indices())


def test_table_window_actions_and_update():
    calls = []
    win = ui.build_table('Results', ['Name', 'Count', 'Level'], _rows(20),
                         actions=[('Select', lambda values: calls.append(values)),
                                  ('Export all', lambda values: calls.append('all'), False)],
                         on_open=lambda value: calls.append(('open', value)), status='20 clashes')
    state = win.Tag
    select_button, export_button = state.buttons
    assert not select_button.IsEnabled and export_button.IsEnabled
    state.table.select_values(['v4', 'v5'])
    assert state.selected() == ['v4', 'v5']
    assert select_button.IsEnabled
    state.update(_rows(3), status='3 clashes')
    assert state.table.total() == 3 and state.status_block.Text == '3 clashes'
    state.table.set_filter('item 2')
    assert state.table.visible_count() == 1
    state.update(_rows(30))
    expected = len([r for r in _rows(30) if ui.matches('item 2', ui.search_text(r['cells']))])
    assert state.table.visible_count() == expected > 1        # the filter is kept
    state.close()


def test_modeless_build_and_non_activating():
    built = []

    def content(win):
        built.append(win)
        return ui.text('Live')
    helper = ui.Modeless('smoke-modeless', 'Live', content, width=300)
    win = helper.build()
    assert built and win.Content is not None
    assert ui.Modeless.get('smoke-modeless') is None
    ui.non_activating(win)
    assert win.ShowActivated is False


def test_plumbing():
    rect = ui.host_rect()
    assert len(rect) == 4 and rect[2] > rect[0]
    cancel = ui.run_later(lambda: None, 50)
    cancel()
    hits = []
    debounce = ui.Debouncer(100, lambda: hits.append(1))
    debounce.trigger()
    debounce.trigger()
    debounce.flush()
    assert hits == [1]
    debounce.cancel()
    assert ui.dpi_scale() > 0
    assert ui.is_runner() is False
    wrapped = ui.safe(lambda: 1 / 0, 'boom')
    assert wrapped() is None


def _layout(win, width=900.0, height=700.0):
    """Measures and arranges a window's content off screen: templates get applied,
    DataGrid rows get generated, bindings resolve."""
    from System.Windows import Rect, Size
    content = win.Content
    content.Measure(Size(width, height))
    content.Arrange(Rect(0.0, 0.0, width, height))
    content.UpdateLayout()
    return content


def _find(root, clr_type):
    from System.Windows.Media import VisualTreeHelper
    found = []
    stack = [root]
    while stack:
        node = stack.pop()
        if isinstance(node, clr_type):
            found.append(node)
        try:
            count = VisualTreeHelper.GetChildrenCount(node)
        except Exception:
            count = 0
        for i in range(count):
            stack.append(VisualTreeHelper.GetChild(node, i))
    return found


def test_layout_pass_applies_every_template():
    from System.Windows.Controls import ComboBox, DataGridRow, CheckBox, RadioButton
    from System.Windows.Controls.Primitives import DataGridColumnHeader
    form_window = ui.build_form('Layout', ALL_FIELDS, units='Meters')
    content = _layout(form_window)
    combos = _find(content, ComboBox)
    assert combos and combos[0].Template.FindName('face', combos[0]) is not None
    assert _find(content, CheckBox) and _find(content, RadioButton)
    rows = _find(content, DataGridRow)
    assert rows, 'the multi field generated no rows'
    assert rows[0].Template.FindName('rail', rows[0]) is not None

    choose_window = ui.build_choose('Layout', _rows(200), ['Name', 'Count', 'Level'])
    content = _layout(choose_window)
    rows = _find(content, DataGridRow)
    assert 0 < len(rows) < 200, 'rows are not virtualised: %d' % len(rows)
    headers = _find(content, DataGridColumnHeader)
    assert len([h for h in headers if h.Column is not None]) == 4      # tick + 3

    table_window = ui.build_table('Layout', ['Name', 'Count', 'Level'], _rows(50),
                                  actions=[('Do', lambda v: None)], status='50 rows')
    content = _layout(table_window)
    assert _find(content, DataGridRow)
    table = table_window.Tag.table
    table.grid.SelectedIndex = 0
    assert table_window.Tag.selected() == ['v0']
    assert table_window.Tag.buttons[0].IsEnabled


def test_dark_theme_builds():
    from PyNavis.Runtime.Forms import DesignSystem
    original = ui.tokens
    ui.tokens = lambda dark=None: DesignSystem.Tokens.For(True)
    try:
        win = ui.build_form('Dark', ALL_FIELDS, units='Meters')
        _layout(win)
        win = ui.build_choose('Dark', _rows(10), ['Name', 'Count', 'Level'])
        _layout(win)
    finally:
        ui.tokens = original


def test_table_retypes_columns_when_filled_later():
    table = ui.Table(['Name', 'Count'], [])
    assert table.numeric == [False, False]
    table.update(_rows(5))
    assert table.numeric == [False, True]
    assert table.data.Columns['k1'].DataType.Name == 'Double'
    table.view.Sort = 'k1 DESC'
    assert int(table.view[0]['idx']) == 4
    table.update([['a', 'text now']])
    assert table.numeric == [False, False]


def _offscreen(win):
    from System.Windows import WindowStartupLocation
    win.WindowStartupLocation = WindowStartupLocation.Manual
    win.Left = -20000.0
    win.Top = -20000.0
    win.ShowActivated = False
    return win


def test_modeless_show_activate_and_close():
    def factory():
        return _offscreen(ui.window('Live', 300, 200))
    helper = ui.Modeless('smoke-live', 'Live', lambda w: ui.text('Hello'), window_factory=factory)
    win = helper.show()
    try:
        assert ui.Modeless.get('smoke-live') is win
        again = ui.Modeless('smoke-live', 'Live', None, window_factory=factory).show()
        assert again is win
    finally:
        ui.Modeless.close('smoke-live')
    assert ui.Modeless.get('smoke-live') is None


def test_modeless_table_window_updates_in_place():
    original = ui.build_table
    ui.build_table = lambda *args, **kw: _offscreen(original(*args, **kw))
    try:
        first = ui.table_window('Live table', ['Name', 'Count', 'Level'], _rows(5), modeless=True,
                                key='smoke-table', status='5 rows')
        second = ui.table_window('Live table', ['Name', 'Count', 'Level'], _rows(9), modeless=True,
                                 key='smoke-table', status='9 rows')
        assert second is first
        assert first.Tag.table.total() == 9 and first.Tag.status_block.Text == '9 rows'
    finally:
        ui.build_table = original
        ui.Modeless.close('smoke-table')
    assert ui.Modeless.get('smoke-table') is None


def test_form_typing_a_path_never_probes_the_disk():
    probes = []
    real_isfile = ui.os.path.isfile

    def counting(path):
        probes.append(path)
        return False
    ui.os.path.isfile = counting
    try:
        form_calls = []
        win = ui.build_form('Paths', [{'kind': 'file_open', 'key': 'src', 'required': True},
                                      {'kind': 'text', 'key': 'name'}],
                            validate=lambda values: form_calls.append(1))
        state = win.Tag
        probes[:] = []
        form_calls[:] = []
        for text in ('S', 'S:', 'S:/', 'S:/share/book.xlsx'):          # typing
            state.set_raw('src', text)
        assert probes == [] and form_calls == []
        assert not state.accept()                                      # OK: the one probe
        assert probes == ['S:/share/book.xlsx']
        values, errors = state.refresh()
        assert errors.get('src') == 'That file does not exist.'        # still shown, not re-probed
        state.set_raw('name', 'x')
        assert state.refresh()[1].get('src') == 'That file does not exist.'
        state.set_raw('src', 'S:/share/book2.xlsx')                    # edited: cleared until the next OK
        assert 'src' not in state.refresh()[1]
        assert probes == ['S:/share/book.xlsx']
    finally:
        ui.os.path.isfile = real_isfile
