# -*- coding: utf-8 -*-
"""namo.ui pure half: field specs, parsing, validation, enabled_if, table helpers."""
import _compat

from namo import ui


def test_options_of():
    assert ui.options_of({'options': ['a', ('Bee', 2), ['Sea', None]]}) == [
        ('a', 'a'), ('Bee', 2), ('Sea', None)]
    assert ui.options_of({}) == []


def test_normalize_fields_defaults_and_errors():
    fields = ui.normalize_fields([{'kind': 'text', 'key': 'a'}, {'kind': 'label', 'text': 'x'},
                                  {'kind': 'textarea', 'key': 'b'}])
    assert fields[0]['required'] is False and fields[0]['label'] == ''
    assert fields[2]['rows'] == 4
    _compat.raises(ValueError, ui.normalize_fields, [{'kind': 'nope', 'key': 'a'}])
    _compat.raises(ValueError, ui.normalize_fields, [{'kind': 'text'}])
    _compat.raises(ValueError, ui.normalize_fields, [{'kind': 'text', 'key': 'a'}, {'kind': 'int', 'key': 'a'}])
    _compat.raises(ValueError, ui.normalize_fields, [{'kind': 'choice', 'key': 'c'}])
    _compat.raises(ValueError, ui.normalize_fields,
                   [{'kind': 'text', 'key': 'a', 'enabled_if': ('zzz', True)}])
    _compat.raises(ValueError, ui.normalize_fields, ['not a dict'])
    assert ui.normalize_fields([{'key': 'k'}])[0]['kind'] == 'text'


def test_parse_number_forms():
    assert ui.parse_number('12.5') == (12.5, None)
    assert ui.parse_number(' 1,234.5 ') == (1234.5, None)
    assert ui.parse_number('1 234,5') == (1234.5, None)
    assert ui.parse_number('12,5') == (12.5, None)
    assert ui.parse_number('1,234') == (1234.0, None)
    assert ui.parse_number('-3') == (-3.0, None)
    value, error = ui.parse_number('abc')
    assert value is None and error == 'Enter a number.'
    value, error = ui.parse_number('nan')
    assert value is None
    value, error = ui.parse_number('11', 0, 10)
    assert value is None and error == 'Enter a number between 0 and 10.'
    assert ui.parse_number('5', min_value=1)[1] is None
    assert ui.parse_number('0', min_value=1)[1] == 'Enter a number of at least 1.'
    assert ui.parse_number('0.5', max_value=0.25)[1] == 'Enter a number of at most 0.25.'


def test_parse_int():
    assert ui.parse_int('42') == (42, None)
    assert ui.parse_int('1,000') == (1000, None)
    assert ui.parse_int('4.5')[0] is None
    assert ui.parse_int('12', 1, 10)[1] == 'Enter a whole number between 1 and 10.'


def test_parse_date_and_color():
    assert ui.parse_date('2026-10-05') == ('2026-10-05', None)
    assert ui.parse_date('2026/1/9') == ('2026-01-09', None)
    assert ui.parse_date('2026-02-30')[0] is None
    assert ui.parse_date('05/10/2026')[0] is None
    assert ui.parse_color('#4e79a7') == ('4E79A7', None)
    assert ui.parse_color('blue')[0] is None


def test_validate_value_kinds():
    f = lambda **kw: ui.normalize_fields([kw])[0]
    assert ui.validate_value(f(kind='check', key='c'), 1) == (True, None)
    assert ui.validate_value(f(kind='choice', key='c', options=['a']), None) == (None, None)
    assert ui.validate_value(f(kind='choice', key='c', options=['a'], required=True), None)[1] == 'Choose one.'
    assert ui.validate_value(f(kind='multi', key='m', options=['a'], required=True), [])[1] == 'Tick at least one.'
    assert ui.validate_value(f(kind='text', key='t', required=True), '  ')[1] == 'Enter a value.'
    assert ui.validate_value(f(kind='text', key='t'), '') == ('', None)
    assert ui.validate_value(f(kind='int', key='i'), '') == (None, None)
    assert ui.validate_value(f(kind='textarea', key='t'), 'a\nb') == ('a\nb', None)


def test_validate_length_with_parser():
    field = ui.normalize_fields([{'kind': 'length', 'key': 'l', 'min': 0.0}])[0]
    parser = lambda text, units: {'25mm': 0.025, '-1': None}.get(text)
    assert ui.validate_value(field, '25mm', parser, 'Meters') == (0.025, None)
    value, error = ui.validate_value(field, '-1', parser, 'Meters')
    assert value is None and error.startswith('Enter a length, in meters')
    value, error = ui.validate_value(field, 'x', None, 'Feet')
    assert error == 'Enter a length, like 3", 1\' 6 1/2" or 25mm.'
    field = ui.normalize_fields([{'kind': 'length', 'key': 'l', 'min': 1.0}])[0]
    assert ui.validate_value(field, '0.5', None, 'Meters')[1] == 'Enter a length of at least 1.0.' or \
        ui.validate_value(field, '0.5', None, 'Meters')[1] == 'Enter a length of at least 1.'


def test_validate_paths_use_injected_checks():
    fields = ui.normalize_fields([{'kind': 'file_open', 'key': 'f'}, {'kind': 'folder', 'key': 'd'},
                                  {'kind': 'file_save', 'key': 's'}])
    exists = lambda path, kind: path.startswith('C:/ok')
    assert ui.validate_value(fields[0], 'C:/ok/a.txt', path_exists=exists) == ('C:/ok/a.txt', None)
    assert ui.validate_value(fields[0], 'C:/no/a.txt', path_exists=exists)[1] == 'That file does not exist.'
    assert ui.validate_value(fields[1], 'C:/no', path_exists=exists)[1] == 'That folder does not exist.'
    assert ui.validate_value(fields[2], 'C:/ok/new.xlsx', path_exists=exists) == ('C:/ok/new.xlsx', None)
    assert ui.validate_value(fields[2], 'new.xlsx', path_exists=exists)[1].startswith('Choose a file')


def test_custom_field_validator():
    field = ui.normalize_fields([{'kind': 'text', 'key': 't',
                                  'validate': lambda v: None if v.isupper() else 'Use capitals.'}])[0]
    assert ui.validate_value(field, 'ABC') == ('ABC', None)
    assert ui.validate_value(field, 'abc')[1] == 'Use capitals.'


def test_collect_enabled_if_and_form_validate():
    fields = ui.normalize_fields([
        {'kind': 'check', 'key': 'on'},
        {'kind': 'int', 'key': 'n', 'enabled_if': ('on', True), 'required': True, 'default': 3},
        {'kind': 'choice', 'key': 'mode', 'options': ['a', 'b', 'c']},
        {'kind': 'text', 'key': 'x', 'enabled_if': ('mode', ['b', 'c']), 'required': True},
        {'kind': 'label', 'text': 'note'},
    ])
    values, errors = ui.collect(fields, {'on': False, 'n': '', 'mode': 'a', 'x': ''})
    assert errors == {} and values['n'] == 3
    values, errors = ui.collect(fields, {'on': True, 'n': '', 'mode': 'b', 'x': ''})
    assert sorted(errors) == ['n', 'x']
    values, errors = ui.collect(fields, {'on': True, 'n': '7', 'mode': 'c', 'x': 'ok'},
                                form_validate=lambda v: 'Pick fewer.' if v['n'] > 5 else None)
    assert errors == {'on': 'Pick fewer.'}
    values, errors = ui.collect(fields, {'on': True, 'n': '7', 'mode': 'c', 'x': 'ok'},
                                form_validate=lambda v: {'x': 'Bad x.', 'n': None})
    assert errors == {'x': 'Bad x.'}
    assert 'note' not in values


def test_is_enabled():
    assert ui.is_enabled({}, {})
    assert ui.is_enabled({'enabled_if': ('a', 1)}, {'a': 1})
    assert not ui.is_enabled({'enabled_if': ('a', 1)}, {'a': 2})
    assert ui.is_enabled({'enabled_if': ('a', (1, 2))}, {'a': 2})


def test_default_text():
    f = lambda **kw: ui.normalize_fields([kw])[0]
    assert ui.default_text(f(kind='text', key='a')) == ''
    assert ui.default_text(f(kind='number', key='a', default=2.50)) == '2.5'
    assert ui.default_text(f(kind='color', key='a', default='#abc')) == 'AABBCC'
    assert ui.default_text(f(kind='length', key='a', default=1.5), 'Feet',
                           lambda v, u: "1' 6\"") == "1' 6\""


def test_length_hint():
    assert ui.length_hint('Feet').startswith('like 3"')
    assert ui.length_hint('Millimeters').startswith('in millimeters')


def test_natural_key_sorts_numbers():
    names = ['Level 10', 'level 2', 'Level 1', 'Level 2a', 'B', 'a']
    assert sorted(names, key=ui.natural_key) == ['a', 'B', 'Level 1', 'level 2', 'Level 2a', 'Level 10']
    assert ui.natural_key(None) == ''


def test_format_cell():
    assert ui.format_cell(None) == ''
    assert ui.format_cell(True) == 'Yes'
    assert ui.format_cell(1234567) == '1,234,567'
    assert ui.format_cell(1234.5) == '1,234.50'
    assert ui.format_cell(0.01234) == '0.0123'
    assert ui.format_cell(0.0) == '0.00'
    assert ui.format_cell(float('nan')) == ''
    assert ui.format_cell('x') == 'x'


def test_numeric_columns_and_weights():
    rows = [['a', 1, '2'], ['b', 2.5, ''], ['c', None, 'x']]
    assert ui.numeric_columns(rows, 3) == [False, True, False]
    assert ui.numeric_columns([['1,234', None]], 2) == [True, False]
    weights = ui.column_weights([['a long name here', 1]], 2)
    assert weights[0] > weights[1] and weights[1] == 4.0
    assert ui.column_weights([], 2) == [1.0, 1.0]
    assert ui.cell_number('12.5') == 12.5 and ui.cell_number('L1') is None and ui.cell_number(True) is None


def test_normalize_rows():
    rows = ui.normalize_rows([{'cells': ['a'], 'value': 'A', 'checked': True}, ['b', 2], {'cells': ['c']}])
    assert rows[0] == {'cells': ['a'], 'value': 'A', 'checked': True}
    assert rows[1] == {'cells': ['b', 2], 'value': 1, 'checked': False}
    assert rows[2]['value'] == 2


def test_filtering():
    assert ui.matches('duct l2', 'Duct A Level L2 note')
    assert not ui.matches('duct l3', 'Duct A Level L2')
    assert ui.matches('', 'anything')
    assert ui.search_text(['A', 1234]) == 'a 1,234'
    assert ui.row_filter('') == ''
    assert ui.row_filter("a 50% it's [x]") == (
        "txt LIKE '%a%' AND txt LIKE '%50[%]%' AND txt LIKE '%it''s%' AND txt LIKE '%[[]x[]]%'")
    assert ui.like_escape('a*b') == 'a[*]b'


def test_count_text_and_place():
    assert ui.count_text(3, 1200) == '3 of 1,200 selected'
    assert ui.count_text(3, 1200, 40) == '3 of 1,200 selected, 40 shown'
    assert ui.count_text(3, 10, 10, 'ticked') == '3 of 10 ticked'
    host = (0, 0, 1000, 800)
    assert ui.place_rect(host, (200, 100)) == (400.0, 350.0)
    assert ui.place_rect(host, (200, 100), 'bottom-right') == (776, 676)
    assert ui.place_rect(host, (2000, 100), 'top-left') == (0, 24)


def test_theme_xaml_is_complete():
    names = ['paper', 'surface', 'line', 'line_strong', 'frame', 'ink', 'muted', 'selection',
             'error', 'error_bg', 'error_line', 'success', 'info', 'warning', 'accent', 'on_accent']
    text = ui.theme_xaml(dict((n, '#123456') for n in names))
    assert '%(' not in text and 'namo.grid' in text


def test_normalize_fields_refuses_a_default_that_is_not_an_option_value():
    # Button Maker's first click: options written (value, label), default a value.
    swapped = [{'kind': 'radio', 'key': 't', 'options': [('selection', 'Selection tool')],
                'default': 'selection'}]
    _compat.raises(ValueError, ui.normalize_fields, swapped)
    for kind in ('choice', 'radio'):
        good = ui.normalize_fields([{'kind': kind, 'key': 't', 'default': 'selection',
                                     'options': [('Selection tool', 'selection'), ('File', 'file')]}])
        assert good[0]['default'] == 'selection'
        _compat.raises(ValueError, ui.normalize_fields,
                       [{'kind': kind, 'key': 't', 'options': ['a', 'b'], 'default': 'c'}])
        _compat.raises(ValueError, ui.normalize_fields,
                       [{'kind': kind, 'key': 't', 'options': ['a', 'b'], 'default': ''}])
    # None (or no default) is the first option; plain strings are their own value
    assert ui.normalize_fields([{'kind': 'choice', 'key': 't', 'options': ['a', 'b']}])[0].get('default') is None
    assert ui.normalize_fields([{'kind': 'choice', 'key': 't', 'options': ['a'], 'default': None}])
    assert ui.normalize_fields([{'kind': 'radio', 'key': 't', 'options': ['a', 'b'], 'default': 'b'}])
    # the values the controls compare with ==: False, 0 and numbers are fine
    assert ui.normalize_fields([{'kind': 'radio', 'key': 't', 'default': False,
                                 'options': [('No', False), ('Yes', True)]}])[0]['default'] is False
    assert ui.normalize_fields([{'kind': 'radio', 'key': 't', 'default': 150,
                                 'options': [('Standard', 150), ('High', 220)]}])
    # a multi default may name options that are gone (saved test names): never raises
    assert ui.normalize_fields([{'kind': 'multi', 'key': 'm', 'options': ['a'], 'default': ['a', 'gone']}])


def test_normalize_fields_fallback_for_a_remembered_default():
    spec = {'kind': 'choice', 'key': 'set', 'options': [('Ducts', 'd'), ('Pipes', 'p')],
            'default': 'deleted set', 'fallback': 'p'}
    assert ui.normalize_fields([spec])[0]['default'] == 'p'
    assert spec['default'] == 'deleted set'                      # the caller's dict is not touched
    spec['fallback'] = None
    assert ui.normalize_fields([spec])[0]['default'] is None     # None: the first option
    spec['default'] = 'd'
    assert ui.normalize_fields([spec])[0]['default'] == 'd'      # a live default wins
    spec['default'], spec['fallback'] = 'x', 'also wrong'
    _compat.raises(ValueError, ui.normalize_fields, [spec])


def test_normalize_fields_refuses_an_enabled_if_that_can_never_switch():
    def fields(wanted, options=None, kind='radio'):
        return [{'kind': kind, 'key': 'mode', 'options': options or [('File', 'file'), ('Tool', 'tool')]},
                {'kind': 'text', 'key': 'path', 'enabled_if': ('mode', wanted)}]
    assert ui.normalize_fields(fields('file'))
    assert ui.normalize_fields(fields('file', kind='choice'))
    _compat.raises(ValueError, ui.normalize_fields, fields('File'))          # a label, not a value
    _compat.raises(ValueError, ui.normalize_fields, fields('png', kind='choice'))
    assert ui.normalize_fields(fields(['file', 'not offered today']))        # one live value is enough
    _compat.raises(ValueError, ui.normalize_fields, fields(['x', 'y']))
    check = lambda wanted: [{'kind': 'check', 'key': 'on'},
                            {'kind': 'int', 'key': 'n', 'enabled_if': ('on', wanted)}]
    assert ui.normalize_fields(check(True)) and ui.normalize_fields(check(False))
    _compat.raises(ValueError, ui.normalize_fields, check('yes'))
    # other kinds are compared as typed: no rule
    assert ui.normalize_fields([{'kind': 'text', 'key': 'a'},
                                {'kind': 'text', 'key': 'b', 'enabled_if': ('a', 'go')}])
    # the field may come before the one it watches
    assert ui.normalize_fields([{'kind': 'text', 'key': 'b', 'enabled_if': ('on', True)},
                                {'kind': 'check', 'key': 'on'}])


def _feet_formatter(value, units, denominator=16):
    """pynavis.lengths.format_input for a feet document: feet, inches, sixteenths."""
    ticks = int(round(abs(value) * 12 * denominator))
    feet, rest = divmod(ticks, 12 * denominator)
    inches, num = divmod(rest, denominator)
    text = "%d' %d" % (feet, inches)
    if num:
        text += ' %d/%d' % (num, denominator)
    return text + '"'


def _feet_parser(text, units):
    """Reads what _feet_formatter writes, and decimal inches like 0.0197"."""
    text = text.strip()
    if "'" not in text:
        return float(text.rstrip('"')) / 12.0
    feet, rest = text.split("'")
    total = float(feet) * 12.0
    for part in rest.rstrip('"').split():
        if '/' in part:
            total += float(part.split('/')[0]) / float(part.split('/')[1])
        else:
            total += float(part)
    return total / 12.0


def test_default_text_small_length_never_opens_as_zero():
    f = lambda **kw: ui.normalize_fields([dict(kind='length', key='l', **kw)])[0]
    half_mm = 0.0005 / 0.3048                                  # feet
    assert _feet_formatter(half_mm, 'Feet') == '0\' 0"'          # the trap
    shown = ui.default_text(f(default=half_mm), 'Feet', _feet_formatter, _feet_parser)
    assert shown == '0.0197"'
    assert abs(_feet_parser(shown, 'Feet') - half_mm) < 0.01 * half_mm
    # anything the 1/16 in grid can show is left as pyNavis formats it
    assert ui.default_text(f(default=1.5), 'Feet', _feet_formatter, _feet_parser) == '1\' 6"'
    assert ui.default_text(f(default=0.01), 'Feet', _feet_formatter, _feet_parser) == '0\' 0 2/16"'
    # a real zero stays zero, and no parser means the formatter's text as before
    assert ui.default_text(f(default=0.0), 'Feet', _feet_formatter, _feet_parser) == '0\' 0"'
    assert ui.default_text(f(default=half_mm), 'Feet', _feet_formatter) == '0\' 0"'
    assert ui.default_text(f(default=-half_mm), 'Feet', _feet_formatter, _feet_parser) == '-0.0197"'
    # a parser that cannot read the decimal form keeps the formatter's text
    strict = lambda text, units: 0.0 if text.startswith('0\'') else None
    assert ui.default_text(f(default=half_mm), 'Feet', _feet_formatter, strict) == '0\' 0"'


def test_small_length_text():
    assert ui.small_length_text(0.001 / 0.3048, 'Feet') == '0.0394"'
    assert ui.small_length_text(0.0254, 'Meters') == '1"'
    assert ui.small_length_text(0.0000001, 'Meters') == '0.00000394"'
    assert ui.small_length_text(0.0, 'Feet') is None


class _LoopWindow(object):
    def __init__(self, log):
        self.log = log
        self.closed = False
        self.Tag = None

    def Close(self):
        self.closed = True
        self.log.append('close')


def test_modal_loop_runs_deferred_jobs_only_after_the_window_closed():
    log = []
    rounds = []

    def build(defer):
        win = _LoopWindow(log)
        win.defer = defer
        rounds.append(win)
        return win

    def show(win):
        log.append('show %d' % len(rounds))
        if len(rounds) == 1:                # the user clicks Refresh in the first round
            win.defer(lambda: log.append(('job', win.closed)))
    last = ui.modal_loop(build, show)
    assert log == ['show 1', 'close', ('job', True), 'show 2']
    assert last is rounds[1] and len(rounds) == 2


def test_modal_loop_brings_the_window_back_after_a_failing_job():
    log = []
    rounds = []

    def build(defer):
        win = _LoopWindow(log)
        win.defer = defer
        rounds.append(win)
        return win

    def boom():
        raise IOError('disk full')

    def show(win):
        if len(rounds) == 1:
            win.defer(boom)
            win.defer(lambda: log.append('second job still ran'))
    ui.modal_loop(build, show)
    assert len(rounds) == 2 and 'second job still ran' in log


def test_modal_loop_without_a_deferred_job_shows_once():
    shown = []
    win = ui.modal_loop(lambda defer: _LoopWindow([]), shown.append)
    assert shown == [win]


def test_save_dialog_opens_in_the_folder_the_field_shows():
    there = lambda folder: folder == r'C:\Jobs\Tower'
    # the folder exists: the whole path, so the dialog opens there with the name filled in
    assert ui.save_dialog_name(r'C:\Jobs\Tower\Clashes.xlsx', None, there) == r'C:\Jobs\Tower\Clashes.xlsx'
    assert ui.save_dialog_name(r'  "C:\Jobs\Tower\Clashes.xlsx" ', None, there) == r'C:\Jobs\Tower\Clashes.xlsx'
    # a folder that is gone, or a bare name: just the file name (the dialog picks the folder)
    assert ui.save_dialog_name(r'C:\Gone\Clashes.xlsx', None, there) == 'Clashes.xlsx'
    assert ui.save_dialog_name('Clashes.xlsx', None, there) == 'Clashes.xlsx'
    # an empty field: the field's default name
    assert ui.save_dialog_name('', 'Report.xlsx', there) == 'Report.xlsx'
    assert ui.save_dialog_name(None, None, there) == ''

    def unreachable(folder):
        raise OSError('network path not found')
    assert ui.save_dialog_name(r'\\server\share\a.xlsx', None, unreachable) == 'a.xlsx'


def test_quick_check_never_probes_a_path_or_calls_the_form_validate():
    probes = []

    def exists(path, kind):
        probes.append(path)
        return False

    def own_check(value):
        probes.append('validate ' + value)
        return 'Not a workbook.'
    fields = ui.normalize_fields([
        {'kind': 'file_open', 'key': 'src', 'required': True},
        {'kind': 'folder', 'key': 'dir'},
        {'kind': 'file_save', 'key': 'out', 'validate': own_check},
        {'kind': 'int', 'key': 'n', 'min': 1}])
    raws = {'src': 'S:/share/a.xlsx', 'dir': 'S:/share', 'out': 'S:/share/b.xlsx', 'n': '0'}
    form_calls = []
    values, errors = ui.collect(fields, raws, path_exists=exists, quick=True,
                                form_validate=lambda v: form_calls.append(1) or {'n': 'Too few.'})
    assert probes == [] and form_calls == []                 # nothing touched the disk
    assert sorted(errors) == ['n'] and 'whole number' in errors['n']   # cheap checks still run
    assert values['src'] == 'S:/share/a.xlsx' and values['out'] == 'S:/share/b.xlsx'
    # an empty required path is a cheap check
    assert ui.validate_value(fields[0], '  ', quick=True)[1] == 'Choose a file.'
    # the full check (OK) probes all three and runs the field's own validate
    values, errors = ui.collect(fields, raws, path_exists=exists)
    assert sorted(errors) == ['dir', 'n', 'out', 'src'] and len(probes) == 3


def test_carry_errors_keeps_the_last_full_check_until_the_text_changes():
    fields = ui.normalize_fields([
        {'kind': 'file_open', 'key': 'src'}, {'kind': 'text', 'key': 'name'},
        {'kind': 'check', 'key': 'on'}, {'kind': 'folder', 'key': 'dir', 'enabled_if': ('on', True)}])
    checked_raws = {'src': 'C:/gone.xlsx', 'name': 'A', 'on': True, 'dir': 'C:/nowhere'}
    checked = {'src': 'That file does not exist.', 'dir': 'That folder does not exist.',
               'name': 'Another template has that name.', '__form__': {'name': True}}
    # nothing typed since OK: every error is still shown
    same = ui.carry_errors(fields, dict(checked_raws), {}, checked_raws, checked)
    assert sorted(same) == ['dir', 'name', 'src']
    # the path was edited: its error goes (re-checked on the next OK), and so does the
    # form-level one, which may depend on it; the untouched folder keeps its error
    raws = dict(checked_raws, src='C:/gone2.xlsx')
    assert sorted(ui.carry_errors(fields, raws, {}, checked_raws, checked)) == ['dir']
    # an error the quick pass found wins, and a disabled field shows none
    raws = dict(checked_raws, on=False)
    values = {'src': 'C:/gone.xlsx', 'name': 'A', 'on': False, 'dir': 'C:/nowhere'}
    merged = ui.carry_errors(fields, raws, {'name': 'Enter a value.'}, checked_raws, checked, values)
    assert merged == {'src': 'That file does not exist.', 'name': 'Enter a value.'}
    # before any full check there is nothing to carry
    assert ui.carry_errors(fields, raws, {'name': 'x'}, None, {}) == {'name': 'x'}
