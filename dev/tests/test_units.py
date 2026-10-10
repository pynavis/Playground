# -*- coding: utf-8 -*-
"""namo.units: conversions, aliases, quantities, Revit strings, and the pure port of
PyNavis.Runtime.Units.Lengths (same examples as src/PyNavis.Tests/LengthsTests.cs)."""
import _compat
from _compat import approx, raises

from namo import units

SUP2 = chr(0x00B2)
SUP3 = chr(0x00B3)


def near(a, b, tol=1e-9):
    return a is not None and abs(a - b) <= tol * max(1.0, abs(b))


# ---- document units -----------------------------------------------------------------

def test_doc_unit_meters_exact_table():
    assert units.DOC_UNIT_METERS == {
        'Meters': 1.0, 'Centimeters': 0.01, 'Millimeters': 0.001, 'Feet': 0.3048,
        'Inches': 0.0254, 'Yards': 0.9144, 'Kilometers': 1000.0, 'Micrometers': 1e-6,
        'Microinches': 2.54e-8, 'Mils': 2.54e-5, 'Miles': 1609.344}


def test_to_and_from_meters():
    assert approx(units.to_meters(12.5, 'Feet'), 3.81)
    assert approx(units.to_meters(1250, 'Millimeters'), 1.25)
    assert approx(units.from_meters(3.81, 'Feet'), 12.5)
    assert approx(units.from_meters(1.0, 'Inches'), 1 / 0.0254)
    assert approx(units.to_meters(2, 'mm'), 0.002)          # aliases work too
    raises(ValueError, units.to_meters, 1, 'Furlongs')
    raises(ValueError, units.to_meters, 1, 'm2')            # not a length


def test_doc_unit_symbol_and_report_units():
    assert units.doc_unit_symbol('Feet') == 'ft'
    assert units.doc_unit_symbol('Millimeters') == 'mm'
    assert units.doc_unit_symbol('Nonsense') == 'm'
    assert units.report_units_for('auto', 'Feet') == {'length': 'ft', 'area': 'ft2', 'volume': 'ft3'}
    assert units.report_units_for('auto', 'Millimeters') == {'length': 'mm', 'area': 'm2', 'volume': 'm3'}
    assert units.report_units_for('m', 'Feet') == {'length': 'm', 'area': 'm2', 'volume': 'm3'}
    assert units.report_units_for('in', 'Meters')['area'] == 'ft2'
    assert units.report_units_for('auto', 'Kilometers')['length'] == 'm'


# ---- aliases and conversion ------------------------------------------------------------

def test_aliases_from_the_contract():
    expected = {
        'm2': 'm2', 'm' + SUP2: 'm2', 'sqm': 'm2', 'sq m': 'm2', 'Sq. M': 'm2', 'm^2': 'm2',
        'sf': 'ft2', 'SF': 'ft2', 'sqft': 'ft2', 'sq ft': 'ft2', 'ft2': 'ft2', 'ft' + SUP2: 'ft2',
        'm3': 'm3', 'm' + SUP3: 'm3', 'cuyd': 'yd3', 'yd3': 'yd3', 'CY': 'yd3', 'l': 'l', 'L': 'l',
        'gal(US)': 'gal', 'gal (US)': 'gal', 'gallons': 'gal', 'kg': 'kg', 't': 't', 'tonnes': 't',
        'lb': 'lb', 'lbs': 'lb', 'Millimeters': 'mm', 'Feet': 'ft', 'inch': 'in', '"': 'in',
        "'": 'ft', 'cf': 'ft3', 'cu ft': 'ft3', 'litres': 'l', 'gal(UK)': 'gal_uk',
        chr(0x00B5) + 'm': 'um', chr(0x03BC) + 'm': 'um', 'ha': 'ha', 'acres': 'ac',
    }
    for text, symbol in sorted(expected.items()):
        assert units.resolve(text) == symbol, (text, units.resolve(text), symbol)
    assert units.resolve('parsecs') is None
    assert units.resolve(None) is None
    assert units.kind_of('sqft') == 'area'
    assert units.kind_of('CY') == 'volume'
    assert units.kind_of('lbs') == 'mass'
    assert units.kind_of('nope') is None


def test_every_alias_points_at_a_known_unit():
    for alias in sorted(units.ALIASES):
        assert units.ALIASES[alias] in units.UNITS, alias
    for kind in units.KINDS:
        assert units.BASE[kind] in units.UNITS


def test_convert_lengths_exactly():
    assert units.convert(24, 'in', 'ft') == 2.0            # not 2.0000000000000004
    assert units.convert(1, 'ft', 'mm') == 304.8
    assert units.convert(1250, 'mm', 'm') == 1.25
    assert units.convert(1, 'mi', 'ft') == 5280.0
    assert units.convert(3, 'yd', 'in') == 108.0
    assert units.convert(5, 'm', 'm') == 5.0


def test_convert_areas_volumes_masses():
    assert approx(units.convert(250, 'sqft', 'm2'), 23.2257600, 1e-9)
    assert approx(units.convert(1, 'm2', 'sf'), 10.7639104167, 1e-9)
    assert approx(units.convert(1, 'cuyd', 'm3'), 0.764554857984, 1e-12)
    assert approx(units.convert(1, 'gal', 'l'), 3.785411784, 1e-12)
    assert approx(units.convert(1, 'm3', 'l'), 1000.0)
    assert approx(units.convert(1, 'ft3', 'in3'), 1728.0)
    assert approx(units.convert(1, 't', 'kg'), 1000.0)
    assert approx(units.convert(1, 'lb', 'kg'), 0.45359237)
    assert approx(units.convert(1, 'ton', 'lb'), 2000.0)
    assert approx(units.convert(1, 'ha', 'm2'), 10000.0)


def test_convert_refuses_across_kinds_and_unknown_units():
    error = raises(ValueError, units.convert, 1, 'm2', 'm')
    assert 'area' in str(error) and 'length' in str(error)
    raises(ValueError, units.convert, 1, 'kg', 'l')
    raises(ValueError, units.convert, 1, 'zz', 'm')
    raises(ValueError, units.convert, 1, 'm', 'zz')


# ---- numbers ------------------------------------------------------------------------------

def test_parse_number_separators():
    cases = [('12.5', 12.5), ('1,234', 1234.0), ('1,234.5', 1234.5), ('1.234,5', 1234.5),
             ('12,5', 12.5), ('0,25', 0.25), ('0,250', 0.25), ('1 250', 1250.0),
             ('1,234,567', 1234567.0), ('1.234.567', 1234567.0), ('-3', -3.0), ('+4', 4.0),
             ('.5', 0.5), ('1e3', 1000.0), ('2.5E-2', 0.025), ('7', 7.0),
             ('1' + chr(0x00A0) + '250', 1250.0)]
    for text, value in cases:
        assert units.parse_number(text) == value, (text, units.parse_number(text))
    for text in ('', 'abc', '1,23,4', '12 6', '1..2', '1.2.3', '1e', '--1', None):
        assert units.parse_number(text) is None, text


def test_split_number_keeps_the_rest():
    assert units.split_number('12.5 m') == (12.5, ' m')
    assert units.split_number('1 250 mm') == (1250.0, ' mm')
    assert units.split_number('12 6') == (12.0, ' 6')
    assert units.split_number('3 ft') == (3.0, ' ft')
    assert units.split_number('m 3') == (None, 'm 3')
    value, rest = units.split_number('-3e2x')
    assert value == -300.0 and rest == 'x'


# ---- quantities ---------------------------------------------------------------------------

def test_parse_quantity_contract_examples():
    q = units.parse_quantity('12.5 m')
    assert q == (12.5, 'm', 'length')
    assert units.parse_quantity('1 250 mm') == (1250.0, 'mm', 'length')
    assert units.parse_quantity('1,250 mm') == (1250.0, 'mm', 'length')
    assert units.parse_quantity('3.5 m' + SUP3) == (3.5, 'm3', 'volume')
    assert units.parse_quantity('12.5 m2') == (12.5, 'm2', 'area')
    assert units.parse_quantity('250 sqft') == (250.0, 'ft2', 'area')
    assert units.parse_quantity('250 SF') == (250.0, 'ft2', 'area')
    assert units.parse_quantity('250 ft2') == (250.0, 'ft2', 'area')     # not 250 ft 2 in
    assert units.parse_quantity('12,5 m') == (12.5, 'm', 'length')
    assert units.parse_quantity('12 CY') == (12.0, 'yd3', 'volume')
    assert units.parse_quantity('5.25 kg') == (5.25, 'kg', 'mass')
    assert units.parse_quantity('-3.5 m') == (-3.5, 'm', 'length')
    assert units.parse_quantity('2.5 gal (US)') == (2.5, 'gal', 'volume')


def test_parse_quantity_revit_feet_inches():
    value, unit, kind = units.parse_quantity('12\' - 6 1/2"')
    assert unit == 'ft' and kind == 'length' and near(value, 12 + 6.5 / 12)
    value, unit, _ = units.parse_quantity('12\'-6"')
    assert unit == 'ft' and near(value, 12.5)
    value, unit, _ = units.parse_quantity('0\' - 1 1/2"')
    assert unit == 'ft' and near(value, 1.5 / 12)
    value, unit, _ = units.parse_quantity('6 1/2"')
    assert unit == 'in' and near(value, 6.5)
    value, unit, _ = units.parse_quantity('2 ft 3 in')
    assert unit == 'ft' and near(value, 2.25)
    value, unit, _ = units.parse_quantity('-1\' 6"')
    assert unit == 'ft' and near(value, -1.5)
    value, unit, _ = units.parse_quantity('6"')
    assert unit == 'in' and near(value, 6.0)


def test_parse_quantity_bare_and_bad():
    assert units.parse_quantity('42') == (42.0, None, None)
    assert units.parse_quantity('1,234.5') == (1234.5, None, None)
    for text in ('', '   ', 'abc', '12 parsecs', '12 6', None, 'm 12'):
        assert units.parse_quantity(text) is None, text


def test_parse_conversion_examples():
    value, a, b = units.parse_conversion('12\' 6" to mm')
    assert near(value, 12.5) and a == 'ft' and b == 'mm'
    assert units.parse_conversion('250 sqft in m2') == (250.0, 'ft2', 'm2')
    assert units.parse_conversion('3 m3 -> cuyd') == (3.0, 'm3', 'yd3')
    assert units.parse_conversion('5 ft as m') == (5.0, 'ft', 'm')
    assert units.parse_conversion('10 kg = ? lb') == (10.0, 'kg', 'lb')
    assert units.parse_conversion('5 in in mm') == (5.0, 'in', 'mm')
    assert units.parse_conversion('5 m2 into sqft') == (5.0, 'm2', 'ft2')
    assert units.parse_conversion('12 to mm') is None           # no source unit
    assert units.parse_conversion('12 m to parsecs') is None
    assert units.parse_conversion('') is None


def test_convert_text():
    value, unit = units.convert_text('12\' 6" to mm')
    assert unit == 'mm' and near(value, 3810.0)
    raises(ValueError, units.convert_text, '5 m2 to m')
    raises(ValueError, units.convert_text, 'hello')


def test_format():
    assert units.format(1250.0, 'mm', 0) == '1,250 mm'
    assert units.format(1250.0, 'mm') == '1,250.00 mm'
    assert units.format(3.5, 'm3', 1) == '3.5 m' + SUP3
    assert units.format(3.5, 'm3', 1, ascii=True) == '3.5 m3'
    assert units.format(23.22576, 'sqm') == '23.23 m' + SUP2
    assert units.format(-0.001, 'm') == '0.00 m'
    assert units.format(12.0, None) == '12.00'
    assert units.format(None, 'm') == ''
    assert units.format(1.5, 'l') == '1.50 L'


# ---- the Lengths port (examples from LengthsTests.cs) -------------------------------------

FEET_CASES = [
    ('1\' 6"', 1.5), ('1\'6"', 1.5), ('1\'-6"', 1.5), ('1\' - 6 1/2"', 1 + 6.5 / 12),
    ('6"', 0.5), ('6 1/2"', 6.5 / 12), ('3/4"', 0.75 / 12), ("1'", 1.0), ("1.5'", 1.5),
    ('6.25"', 6.25 / 12), ('  6 " ', 0.5), ('1 6', 1.5), ('1 6 1/2', 1 + 6.5 / 12),
    ('0 0 1/8', 1.0 / 96), ('1-6', 1.5), ('1-6 1/2', 1 + 6.5 / 12), ('2', 2.0),
    ('6 1/2', 6.5), ('1/2', 0.5 / 12), ('0', 0.0),
    ('18in', 1.5), ('1ft 6in', 1.5), ('2 ft 3 in', 2.25), ('1 ft 6 1/4 in', 1 + 6.25 / 12),
    ('2ft 3in 1/8', 2 + 3.125 / 12), ('1 feet 6 inches', 1.5), ('25mm', 25 / 304.8),
    ('2.5 cm', 0.025 / 0.3048), ('0.1m', 0.1 / 0.3048), ("6''", 0.5),
    (chr(0x2019).join(['1', ' 6']) + chr(0x201D), 1.5),     # 1' 6" pasted with curly marks
    (chr(0x2032).join(['1', ' 6']) + chr(0x2033), 1.5),     # primes
]

OTHER_UNIT_CASES = [
    ('150', 150.0, 'Millimeters'), ('150mm', 150.0, 'Millimeters'), ('6"', 152.4, 'Millimeters'),
    ('1\' 6"', 457.2, 'Millimeters'), ('0.1m', 100.0, 'Millimeters'), ('150mm', 0.15, 'Meters'),
    ('0.5', 0.5, 'Meters'), ('6', 6.0, 'Inches'), ("1'", 12.0, 'Inches'),
]

REFUSED = [
    ('', 'Feet'), ('   ', 'Feet'), (None, 'Feet'), ('abc', 'Feet'), ("1'' 2", 'Feet'),
    ('-6"', 'Feet'), ('6" 1\'', 'Feet'), ('1/0', 'Feet'), ("'", 'Feet'), ('6 in 2 ft', 'Feet'),
    ('5 mm 2', 'Feet'), ('1 6', 'Millimeters'), ('1-6', 'Meters'), ('1 x', 'Meters'),
]


def test_parse_length_reads_feet_and_inches_like_revit():
    for text, feet in FEET_CASES:
        got = units.parse_length(text, 'Feet')
        assert near(got, feet), (text, got, feet)


def test_parse_length_in_other_document_units():
    for text, want, doc_units in OTHER_UNIT_CASES:
        got = units.parse_length(text, doc_units)
        assert near(got, want), (text, doc_units, got, want)


def test_parse_length_refuses_what_it_cannot_read():
    for text, doc_units in REFUSED:
        assert units.parse_length(text, doc_units) is None, (text, doc_units)


def test_format_length_input_round_trips():
    cases = [(1.5, 'Feet', '1\' 6"'), (3.25 / 12, 'Feet', '0\' 3 1/4"'), (2.0, 'Feet', '2\' 0"'),
             (0.0, 'Feet', '0\' 0"'), (6.5, 'Inches', '0\' 6 1/2"'), (150.0, 'Millimeters', '150'),
             (150.5, 'Millimeters', '150.5'), (0.15, 'Meters', '0.15')]
    for value, doc_units, text in cases:
        assert units.format_length_input(value, doc_units) == text, (value, doc_units)
        assert near(units.parse_length(text, doc_units), value), text
    assert units.format_feet_inches(12 + 6.5 / 12) == '12\' 6 1/2"'
    assert units.is_imperial('Feet') and units.is_imperial('Inches')
    assert not units.is_imperial('Millimeters')
