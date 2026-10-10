# -*- coding: utf-8 -*-
"""namo.converter pure half: parsing every input style, formatting, history, targets."""
import _compat

from namo import converter as c, paths


def _main(text, a=None, b=None):
    return c.result_text(c.parse(text, a, b))[0]


def test_sentences():
    assert _main('12\' 6" to mm') == '3,810 mm'
    assert _main('250 sqft in m2') == u'23.22576 m²'
    assert _main('3.5 m3 cuyd') == u'4.5778272 yd³'
    assert _main('1200 kg lb') == '2,645.5471 lb'
    assert _main('5 in in mm') == '127 mm'
    assert _main('1,250 mm to m') == '1.25 m'
    assert _main('0.0005 m3 to l') == '0.5 L'
    assert _main('3 cubic yards to m3') == u'2.2936646 m³'
    assert _main('2 ft 3 in to cm') == '68.58 cm'


def test_bare_values_use_the_lists():
    assert _main('100', 'ft', 'mm') == '30,480 mm'
    assert _main('100 m', 'ft', 'mm') == '100,000 mm'             # its own unit wins
    parsed = c.parse('100', None, 'mm')
    assert not parsed['ok'] and parsed['error'] == 'Pick the units to convert between.'


def test_errors():
    parsed = c.parse('10 ft to kg')
    assert not parsed['ok'] and parsed['error'] == 'Cannot convert ft (length) to kg (mass).'
    assert c.parse('hello')['error'] == c.HINT
    assert c.parse('   ') == {'ok': False, 'value': None, 'from': None, 'to': None, 'result': None,
                              'error': None, 'kind': None}
    assert c.result_text(c.parse('hello')) == ('', c.HINT)


def test_secondary_lines_and_copy():
    main, secondary = c.result_text(c.parse('24 in ft'))
    assert main == '2 ft' and secondary == '24 in = 2 ft, or 2\' 0"'
    main, secondary = c.result_text(c.parse('3810 mm to in'))
    assert secondary.endswith('or 12\' 6"')
    assert c.copy_text(c.parse('250 sqft in m2')) == '23.22576 m2'
    assert c.copy_text(c.parse('2000 mm to m')) == '2 m'
    assert c.copy_text(c.parse('nonsense')) == ''


def test_format_number():
    assert c.format_number(1234567.891) == '1,234,567.9'
    assert c.format_number(0.000123456) == '0.000123456'
    assert c.format_number(2.0) == '2'
    assert c.format_number(0) == '0'
    assert c.format_number(None) == ''
    assert c.format_number(-1500.25) == '-1,500.25'


def test_history_and_targets():
    history = c.push_history([], 'a')
    history = c.push_history(history, 'b')
    history = c.push_history(history, 'a')
    assert history == ['a', 'b']
    assert c.push_history([str(i) for i in range(12)], 'x')[:2] == ['x', '0']
    assert len(c.push_history([str(i) for i in range(12)], 'x')) == 10
    assert c.history_entry(' 1  ft to mm', c.parse('1 ft to mm')) == '1 ft to mm = 304.8 mm'
    assert c.doc_target('Feet', 'area') == 'ft2'
    assert c.doc_target('Millimeters', 'volume') == 'mm3'
    assert c.doc_target('Meters', 'length') == 'm'
    assert c.doc_target('Meters', 'mass') is None
    assert c.doc_target(None, 'length') is None
    assert c.with_target('250 sqft in m2', 'ft2') == '250 sqft to ft2'
    assert c.with_target('3.5 m3 cuyd', 'm3') == '3.5 m3 to m3'
    assert c.with_target('12 ft', 'mm') == '12 ft to mm'
    assert c.with_target('', 'mm') == ''
    assert len(c.all_units()) == 31


def test_history_store_is_local():
    folder = _compat.tmpdir('converter_history')
    previous = paths.redirect(folder)
    try:
        assert c.load_history() == []
        c.save_history(['1 ft to mm = 304.8 mm'])
        assert c.load_history() == ['1 ft to mm = 304.8 mm']
    finally:
        paths.redirect(previous)
