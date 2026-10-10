# -*- coding: utf-8 -*-
"""Units: document lengths, conversions, and quantities as people and Revit write them.

    units.to_meters(12.5, 'Feet')                  # 3.81 (doc.Units names: str(doc.Units))
    units.convert(250, 'sqft', 'm2')               # 23.2257...
    units.parse_quantity('3.5 m³')            # (3.5, 'm3', 'volume')
    units.parse_quantity('12\' - 6 1/2"')          # (12.541666..., 'ft', 'length')
    units.parse_conversion('12\' 6" to mm')        # (12.5, 'ft', 'mm')
    units.format(1250.0, 'mm', 0)                  # '1,250 mm'
    units.parse_length('1\' 6"', 'Feet')           # 1.5, the pynavis.lengths rules, pure

Canonical unit symbols (what every function returns): length m, mm, cm, km, um, in, ft,
yd, mi, mil, uin; area m2, mm2, cm2, km2, ha, in2, ft2, yd2, ac; volume m3, mm3, cm3,
l, ml, in3, ft3, yd3, gal (US), gal_uk; mass kg, g, t (tonne), lb, oz, ton (US short
ton). resolve(text) maps any alias (m², sq m, sqm, SF, sq ft, ft², CF, cuyd,
CY, L, litres, gal(US), lbs, tonnes...) to its symbol; spaces, dots, '^' and case are
ignored and superscripts read as digits.

parse_length/format_length_input are a pure port of PyNavis.Runtime.Units.Lengths (what
pynavis.lengths wraps; that module needs the runtime, this one does not), checked
against the same examples as the C# tests.

Pure stdlib, CPython and IronPython 3.4.
"""
import math
import re

KINDS = ('length', 'area', 'volume', 'mass')
BASE = {'length': 'm', 'area': 'm2', 'volume': 'm3', 'mass': 'kg'}

# symbol: (kind, SI factor: metres, square metres, cubic metres, kilograms)
UNITS = {
    'm': ('length', 1.0), 'mm': ('length', 0.001), 'cm': ('length', 0.01),
    'km': ('length', 1000.0), 'um': ('length', 1e-6), 'in': ('length', 0.0254),
    'ft': ('length', 0.3048), 'yd': ('length', 0.9144), 'mi': ('length', 1609.344),
    'mil': ('length', 2.54e-5), 'uin': ('length', 2.54e-8),
    'm2': ('area', 1.0), 'mm2': ('area', 1e-6), 'cm2': ('area', 1e-4), 'km2': ('area', 1e6),
    'ha': ('area', 1e4), 'in2': ('area', 0.00064516), 'ft2': ('area', 0.09290304),
    'yd2': ('area', 0.83612736), 'ac': ('area', 4046.8564224),
    'm3': ('volume', 1.0), 'mm3': ('volume', 1e-9), 'cm3': ('volume', 1e-6),
    'l': ('volume', 0.001), 'ml': ('volume', 1e-6), 'in3': ('volume', 1.6387064e-5),
    'ft3': ('volume', 0.028316846592), 'yd3': ('volume', 0.764554857984),
    'gal': ('volume', 0.003785411784), 'gal_uk': ('volume', 0.00454609),
    'kg': ('mass', 1.0), 'g': ('mass', 0.001), 't': ('mass', 1000.0),
    'lb': ('mass', 0.45359237), 'oz': ('mass', 0.028349523125), 'ton': ('mass', 907.18474),
}

# Navisworks document units (str(doc.Units)) in metres.
DOC_UNIT_METERS = {
    'Meters': 1.0, 'Centimeters': 0.01, 'Millimeters': 0.001, 'Feet': 0.3048,
    'Inches': 0.0254, 'Yards': 0.9144, 'Kilometers': 1000.0, 'Micrometers': 1e-6,
    'Microinches': 2.54e-8, 'Mils': 2.54e-5, 'Miles': 1609.344,
}

DOC_UNIT_SYMBOLS = {
    'Meters': 'm', 'Centimeters': 'cm', 'Millimeters': 'mm', 'Feet': 'ft', 'Inches': 'in',
    'Yards': 'yd', 'Kilometers': 'km', 'Micrometers': 'um', 'Microinches': 'uin',
    'Mils': 'mil', 'Miles': 'mi',
}

_SUP2 = chr(0x00B2)
_SUP3 = chr(0x00B3)
_MICRO = (chr(0x00B5), chr(0x03BC))

# Pretty symbols for format(); ascii=True prints the canonical symbol instead.
DISPLAY = {
    'm2': 'm' + _SUP2, 'mm2': 'mm' + _SUP2, 'cm2': 'cm' + _SUP2, 'km2': 'km' + _SUP2,
    'in2': 'in' + _SUP2, 'ft2': 'ft' + _SUP2, 'yd2': 'yd' + _SUP2,
    'm3': 'm' + _SUP3, 'mm3': 'mm' + _SUP3, 'cm3': 'cm' + _SUP3, 'in3': 'in' + _SUP3,
    'ft3': 'ft' + _SUP3, 'yd3': 'yd' + _SUP3, 'um': chr(0x00B5) + 'm', 'l': 'L', 'ml': 'mL',
    'gal_uk': 'gal (UK)',
}

_ALIAS_LIST = [
    ('m', ['m', 'meter', 'meters', 'metre', 'metres', 'mtr', 'mtrs']),
    ('mm', ['mm', 'millimeter', 'millimeters', 'millimetre', 'millimetres']),
    ('cm', ['cm', 'centimeter', 'centimeters', 'centimetre', 'centimetres']),
    ('km', ['km', 'kilometer', 'kilometers', 'kilometre', 'kilometres']),
    ('um', ['um', 'micrometer', 'micrometers', 'micrometre', 'micrometres', 'micron', 'microns']),
    ('in', ['in', 'inch', 'inches', '"', "''"]),
    ('ft', ['ft', 'foot', 'feet', "'"]),
    ('yd', ['yd', 'yds', 'yard', 'yards']),
    ('mi', ['mi', 'mile', 'miles']),
    ('mil', ['mil', 'mils', 'thou']),
    ('uin', ['uin', 'microinch', 'microinches']),
    ('m2', ['m2', 'sqm', 'sqmeter', 'sqmeters', 'sqmetre', 'sqmetres', 'squaremeter',
            'squaremeters', 'squaremetre', 'squaremetres', 'msq']),
    ('mm2', ['mm2', 'sqmm', 'squaremillimeter', 'squaremillimeters', 'squaremillimetre',
             'squaremillimetres']),
    ('cm2', ['cm2', 'sqcm', 'squarecentimeter', 'squarecentimeters', 'squarecentimetre',
             'squarecentimetres']),
    ('km2', ['km2', 'sqkm', 'squarekilometer', 'squarekilometers', 'squarekilometre',
             'squarekilometres']),
    ('ha', ['ha', 'hectare', 'hectares']),
    ('in2', ['in2', 'sqin', 'squareinch', 'squareinches']),
    ('ft2', ['ft2', 'sf', 'sqft', 'sqfeet', 'sqfoot', 'squarefoot', 'squarefeet', 'sft']),
    ('yd2', ['yd2', 'sqyd', 'sqyds', 'squareyard', 'squareyards', 'sy']),
    ('ac', ['ac', 'acre', 'acres']),
    ('m3', ['m3', 'cum', 'cumeter', 'cumeters', 'cubicmeter', 'cubicmeters', 'cubicmetre',
            'cubicmetres']),
    ('mm3', ['mm3', 'cumm', 'cubicmillimeter', 'cubicmillimeters', 'cubicmillimetre',
             'cubicmillimetres']),
    ('cm3', ['cm3', 'cc', 'cucm', 'cubiccentimeter', 'cubiccentimeters', 'cubiccentimetre',
             'cubiccentimetres']),
    ('l', ['l', 'liter', 'liters', 'litre', 'litres', 'ltr', 'ltrs']),
    ('ml', ['ml', 'milliliter', 'milliliters', 'millilitre', 'millilitres']),
    ('in3', ['in3', 'cuin', 'cubicinch', 'cubicinches']),
    ('ft3', ['ft3', 'cf', 'cuft', 'cubicfoot', 'cubicfeet', 'cft']),
    ('yd3', ['yd3', 'cuyd', 'cuyds', 'cy', 'cubicyard', 'cubicyards']),
    ('gal', ['gal', 'gals', 'gallon', 'gallons', 'gal(us)', 'usgal', 'usgallon', 'usgallons',
             'gallon(us)', 'gallons(us)']),
    ('gal_uk', ['gal_uk', 'gal(uk)', 'galuk', 'impgal', 'ukgal', 'gal(imp)', 'imperialgallon',
                'imperialgallons', 'gallon(uk)', 'gallons(uk)']),
    ('kg', ['kg', 'kgs', 'kilo', 'kilos', 'kilogram', 'kilograms', 'kilogramme', 'kilogrammes']),
    ('g', ['g', 'gr', 'gram', 'grams', 'gramme', 'grammes']),
    ('t', ['t', 'tonne', 'tonnes', 'metricton', 'metrictons', 'mt']),
    ('lb', ['lb', 'lbs', 'pound', 'pounds', 'lbm']),
    ('oz', ['oz', 'ounce', 'ounces']),
    ('ton', ['ton', 'tons', 'shortton', 'shorttons', 'uston', 'ustons']),
]


def unit_key(text):
    """The lookup form of a unit text: lowercase, superscripts as digits, micro signs as
    'u', and spaces, dots and '^' removed ('Sq. Ft' -> 'sqft', 'm²' -> 'm2')."""
    text = str(text or '').strip().lower()
    text = text.replace(_SUP2, '2').replace(_SUP3, '3')
    for micro in _MICRO:
        text = text.replace(micro, 'u')
    for ch in (' ', '.', '^', chr(0x00A0), '\t'):
        text = text.replace(ch, '')
    return text


ALIASES = {}
for _symbol, _names in _ALIAS_LIST:
    for _name in _names:
        ALIASES[unit_key(_name)] = _symbol
for _doc_name, _symbol in DOC_UNIT_SYMBOLS.items():
    ALIASES[unit_key(_doc_name)] = _symbol


def resolve(unit):
    """Canonical symbol for a unit text or Navisworks unit name, or None when unknown."""
    if unit is None:
        return None
    return ALIASES.get(unit_key(unit))


def kind_of(unit):
    """'length' | 'area' | 'volume' | 'mass' for a unit text, or None when unknown."""
    symbol = resolve(unit)
    return UNITS[symbol][0] if symbol else None


def _tidy(value):
    """Rounds float noise away (12 significant digits): 24 in is 2.0 ft, not 2.0000000000000004."""
    if value == 0 or math.isinf(value) or math.isnan(value):
        return value
    return float('%.12g' % value)


def convert(value, from_unit, to_unit):
    """value in from_unit expressed in to_unit (any aliases). Raises ValueError for an
    unknown unit or across kinds (an area cannot become a length). Result rounded to 12
    significant digits."""
    a, b = resolve(from_unit), resolve(to_unit)
    if a is None:
        raise ValueError('Unknown unit %r' % (from_unit,))
    if b is None:
        raise ValueError('Unknown unit %r' % (to_unit,))
    kind_a, factor_a = UNITS[a]
    kind_b, factor_b = UNITS[b]
    if kind_a != kind_b:
        raise ValueError('Cannot convert %s (%s) to %s (%s)' % (a, kind_a, b, kind_b))
    if a == b:
        return float(value)
    return _tidy(float(value) * factor_a / factor_b)


def _doc_factor(doc_units):
    if doc_units in DOC_UNIT_METERS:
        return DOC_UNIT_METERS[doc_units]
    symbol = resolve(doc_units)
    if symbol and UNITS[symbol][0] == 'length':
        return UNITS[symbol][1]
    raise ValueError('Unknown length unit %r' % (doc_units,))


def to_meters(value, doc_units):
    """A length in document units (str(doc.Units), or any length alias) in metres."""
    return float(value) * _doc_factor(str(doc_units))


def from_meters(value_m, doc_units):
    """A length in metres in document units."""
    return float(value_m) / _doc_factor(str(doc_units))


def doc_unit_symbol(doc_units):
    """'Feet' -> 'ft', 'Millimeters' -> 'mm' ...; an alias resolves too; unknown -> 'm'."""
    if doc_units in DOC_UNIT_SYMBOLS:
        return DOC_UNIT_SYMBOLS[doc_units]
    symbol = resolve(doc_units)
    return symbol if symbol and UNITS[symbol][0] == 'length' else 'm'


def report_units_for(report_units, doc_units):
    """The units a report shows, from config 'report_units' ('auto' | 'mm' | 'm' | 'ft' |
    'in') and the document units: {'length', 'area', 'volume'}. Metric reports use m2 and
    m3 for areas and volumes, imperial ones ft2 and ft3."""
    choice = (report_units or 'auto').lower()
    length = doc_unit_symbol(doc_units) if choice == 'auto' else (resolve(choice) or 'm')
    if length in ('ft', 'in', 'yd', 'mi', 'mil', 'uin'):
        return {'length': length if length in ('ft', 'in') else 'ft', 'area': 'ft2', 'volume': 'ft3'}
    if length not in ('m', 'mm', 'cm'):
        length = 'm'
    return {'length': length, 'area': 'm2', 'volume': 'm3'}


# ---- numbers as people type them --------------------------------------------------

_SPACES = (' ', chr(0x00A0), chr(0x2009), chr(0x202F))
_DIGITS = '0123456789'


def _clean_number(token):
    """Float from a token of digits with ',', '.' and space separators, or None.

    Thousands: '1,234', '1 234', '1.234.567'; decimals: '12.5', '12,5' (a comma followed
    by other than exactly 3 digits, or after a leading 0, is a decimal comma); both: the
    rightmost of '.' and ',' is the decimal mark.
    """
    t = token
    for space in _SPACES:
        if space in t:
            groups = t.split(space)
            if any(len(g) != 3 or not g.isdigit() for g in groups[1:]) or not groups[0]:
                return None
            t = ''.join(groups)
    if not t or t in ('.', ','):
        return None
    dot, comma = t.rfind('.'), t.rfind(',')
    if dot >= 0 and comma >= 0:
        decimal, thousands = ('.', ',') if dot > comma else (',', '.')
        whole, frac = t.rsplit(decimal, 1)
        if not _thousands_ok(whole, thousands):
            return None
        t = whole.replace(thousands, '') + '.' + frac
    elif comma >= 0:
        parts = t.split(',')
        if len(parts) == 2 and (len(parts[1]) != 3 or parts[0] in ('', '0', '-0')):
            t = parts[0] + '.' + parts[1]
        elif _thousands_ok(t, ','):
            t = t.replace(',', '')
        else:
            return None
    elif t.count('.') > 1:
        if not _thousands_ok(t, '.'):
            return None
        t = t.replace('.', '')
    try:
        return float(t)
    except ValueError:
        return None


def _thousands_ok(text, sep):
    groups = text.split(sep)
    if len(groups) == 1:
        return True
    if not groups[0] or len(groups[0]) > 3 or not groups[0].isdigit():
        return False
    return all(len(g) == 3 and g.isdigit() for g in groups[1:])


def split_number(text):
    """(value, rest) for the number at the start of text ('12.5 m' -> (12.5, ' m'),
    '1 250 mm' -> (1250.0, ' mm'), '-3e2x' -> (-300.0, 'x')), or (None, text)."""
    if text is None:
        return None, ''
    s = str(text).lstrip()
    sign = 1.0
    i = 0
    if s[:1] in ('+', '-', chr(0x2212)):
        sign = -1.0 if s[0] != '+' else 1.0
        i = 1
    j = i
    n = len(s)
    while j < n:
        ch = s[j]
        if ch in _DIGITS or ch in '.,':
            j += 1
        elif ch in _SPACES and j > i and s[j - 1] in _DIGITS and j + 1 < n and s[j + 1] in _DIGITS:
            j += 1
        else:
            break
    token = s[i:j].rstrip(',')
    if not token or not any(c in _DIGITS for c in token):
        return None, s
    value = _clean_number(token)
    if value is None:
        # '12 6': the space was not a thousands separator; keep the part before it.
        for space in _SPACES:
            if space in token:
                token = token.split(space)[0]
        value = _clean_number(token)
        if value is None:
            return None, s
    rest = s[i + len(token):]
    expo = re.match(r'[eE]([+-]?\d+)', rest)
    if expo:
        value = value * (10.0 ** int(expo.group(1)))
        rest = rest[expo.end():]
    return sign * value, rest


def parse_number(text):
    """The whole text as a number ('1,234.5', '12,5', '1 250', '-3', '1e3'), else None."""
    value, rest = split_number(text)
    if value is None or rest.strip():
        return None
    return value


# ---- feet and inches: a pure port of PyNavis.Runtime.Units.Lengths ------------------

_NUMBER = r'(?:\d+(?:\.\d*)?|\.\d+)'
_FRACTION = r'\d+\s*/\s*\d+'
_MIXED = '(?:' + _NUMBER + r'\s+' + _FRACTION + '|' + _FRACTION + '|' + _NUMBER + ')'
_FEET_MARK = "(?:'|feet|foot|ft)"
_INCH_MARK = '(?:"|inches|inch|in)'


def _whole(pattern):
    return re.compile('^' + pattern + '$')


_RE_FEET_INCHES = _whole('(?P<ft>' + _MIXED + r')\s*' + _FEET_MARK +
                         r'(?:\s*-?\s*(?P<in>' + _MIXED + r')\s*(?:' + _INCH_MARK +
                         r')?\s*(?P<tail>' + _FRACTION + ')?)?')
_RE_INCHES_ONLY = _whole('(?P<in>' + _MIXED + r')\s*' + _INCH_MARK + r'\s*(?P<tail>' + _FRACTION + ')?')
_RE_METRIC = _whole('(?P<v>' + _NUMBER + r')\s*(?P<u>mm|cm|m)')
_RE_SPACED = _whole('(?P<ft>' + _NUMBER + r')\s+(?P<in>' + _NUMBER + r'(?:\s+' + _FRACTION + ')?)')
_RE_HYPHEN = _whole('(?P<ft>' + _NUMBER + r')\s*-\s*(?P<in>' + _MIXED + ')')
_RE_BARE_FRACTION = _whole('(?P<f>' + _FRACTION + ')')
_RE_BARE = _whole('(?P<v>' + _MIXED + ')')

_INCHES_PER_UNIT = {'feet': 12.0, 'inches': 1.0, 'yards': 36.0, 'miles': 63360.0}
_METRIC_WORDS = {'mm': 'Millimeters', 'cm': 'Centimeters', 'm': 'Meters'}
_LENGTH_METERS = dict((k.lower(), v) for k, v in DOC_UNIT_METERS.items())


def _normalize_marks(text):
    t = str(text).strip().lower()
    for ch in (chr(0x2019), chr(0x2032), chr(0x2018)):
        t = t.replace(ch, "'")
    for ch in (chr(0x201D), chr(0x201C), chr(0x2033)):
        t = t.replace(ch, '"')
    return t.replace("''", '"')


def _mixed_value(text):
    """6.5, 1/2 or 6 1/2 as a number; ZeroDivisionError on x/0."""
    text = text.strip()
    slash = text.rfind('/')
    if slash < 0:
        return float(text)
    den = float(text[slash + 1:].strip())
    if den == 0:
        raise ZeroDivisionError
    head = text[:slash].split()
    whole = float(head[0]) if len(head) == 2 else 0.0
    return whole + float(head[-1]) / den


def is_imperial(units):
    """True for document units that read as feet and inches (Feet, Inches, Yards, Miles)."""
    return units is not None and str(units).lower() in _INCHES_PER_UNIT


def _length_convert(value, from_units, to_units):
    """Lengths.Convert: imperial pairs go by inches (exact), anything else by metres;
    unknown names count as metres (as in the C#)."""
    a, b = str(from_units).lower(), str(to_units).lower()
    if a in _INCHES_PER_UNIT and b in _INCHES_PER_UNIT:
        return value * _INCHES_PER_UNIT[a] / _INCHES_PER_UNIT[b]
    return value * _LENGTH_METERS.get(a, 1.0) / _LENGTH_METERS.get(b, 1.0)


def _group(match, name):
    return match.groupdict().get(name)


def _feet_inches_value(match):
    """Total inches of a FEET_INCHES / INCHES_ONLY / SPACED / HYPHEN match."""
    ft, inch, tail = _group(match, 'ft'), _group(match, 'in'), _group(match, 'tail')
    feet = _mixed_value(ft) if ft else 0.0
    inches = (_mixed_value(inch) if inch else 0.0) + (_mixed_value(tail) if tail else 0.0)
    return feet * 12.0 + inches


def parse_length(text, doc_units):
    """A typed length in document units, or None (the pynavis.lengths.parse rules, pure).

    In a feet-and-inches document: 1' 6", 1'-6 1/2", 6 1/2", 3/4", 1.5', the space form
    1 6 and hyphen form 1-6 (feet then inches), and a bare fraction as inches. Anywhere: a
    bare number is in the document's unit, and 25mm, 0.1m, 6", 1' 6" convert. Negative
    lengths are refused (None).
    """
    if text is None:
        return None
    t = _normalize_marks(text)
    if not t:
        return None
    try:
        m = _RE_FEET_INCHES.match(t) or _RE_INCHES_ONLY.match(t)
        if m:
            return _length_convert(_feet_inches_value(m), 'Inches', doc_units)
        m = _RE_METRIC.match(t)
        if m:
            return _length_convert(float(m.group('v')), _METRIC_WORDS[m.group('u')], doc_units)
        if is_imperial(doc_units):
            m = _RE_SPACED.match(t) or _RE_HYPHEN.match(t)
            if m:
                return _length_convert(_feet_inches_value(m), 'Inches', doc_units)
            m = _RE_BARE_FRACTION.match(t)
            if m:
                return _length_convert(_mixed_value(m.group('f')), 'Inches', doc_units)
        m = _RE_BARE.match(t)
        if m:
            return _mixed_value(m.group('v'))
    except (ZeroDivisionError, ValueError, OverflowError):
        return None
    return None


def _gcd(a, b):
    while b:
        a, b = b, a % b
    return a


def format_length_input(value, doc_units, denominator=16):
    """A length as a user would type it back (pynavis.lengths.format_input, pure):
    1' 6 1/2" in a feet-and-inches document (nearest 1/denominator inch), a plain decimal
    (up to 6 places, no trailing zeros) otherwise."""
    per_unit = _INCHES_PER_UNIT.get(str(doc_units).lower())
    if per_unit is None:
        text = ('%.6f' % float(value)).rstrip('0').rstrip('.')
        return '0' if text in ('', '-0') else text
    denominator = max(1, int(denominator))
    sign = '-' if value < 0 else ''
    ticks = int(math.floor(abs(float(value)) * per_unit * denominator + 0.5))
    feet = ticks // (12 * denominator)
    rest = ticks % (12 * denominator)
    inches = rest // denominator
    num = rest % denominator
    text = "%s%d' %d" % (sign, feet, inches)
    if num:
        g = _gcd(num, denominator)
        text += ' %d/%d' % (num // g, denominator // g)
    return text + '"'


def format_feet_inches(feet, denominator=16):
    """A length in feet as Revit shows it: 12' 6 1/2" (nearest 1/denominator inch)."""
    return format_length_input(feet, 'Feet', denominator)


# ---- quantities --------------------------------------------------------------------


def parse_quantity(text):
    """(value, unit, kind) from text, or None when it does not read.

    Reads '12.5 m', '1 250 mm', '1,250 mm', '12,5 m' (decimal comma when unambiguous),
    '3.5 m³', '12.5 m2', '250 sqft', '250 SF', '12 CY', '5.2 kg', Revit
    DisplayStrings, and feet-and-inches: "12' - 6 1/2\"", '12\'6"', '6 1/2"', '2 ft 3 in'
    (feet forms give unit 'ft', inch-only forms 'in'). A bare number gives
    (value, None, None). Negative values are allowed.
    """
    if text is None:
        return None
    t = _normalize_marks(text)
    if not t:
        return None
    # A number and one unit first: '250 ft2' must not read as 250 ft 2 in.
    value, rest = split_number(t)
    if value is not None:
        rest = rest.strip()
        if not rest:
            return (value, None, None)
        found = resolve(rest)
        if found is not None:
            return (value, found, UNITS[found][0])
    sign = 1.0
    body = t
    if body[:1] in ('-', chr(0x2212)):
        sign, body = -1.0, body[1:].strip()
    elif body[:1] == '+':
        body = body[1:].strip()
    try:
        m = _RE_FEET_INCHES.match(body)
        if m:
            return (sign * _feet_inches_value(m) / 12.0, 'ft', 'length')
        m = _RE_INCHES_ONLY.match(body)
        if m:
            return (sign * _feet_inches_value(m), 'in', 'length')
    except (ZeroDivisionError, ValueError, OverflowError):
        return None
    return None


_SEPARATORS = re.compile(r'(?<=\s)(?:to|into|in|as)(?=\s)|->|=>|=', re.IGNORECASE)


def parse_conversion(text):
    """(value, from_unit, to_unit) from "12' 6\" to mm", '250 sqft in m2', '3 m3 -> cuyd',
    '5 ft as m' or '10 kg = ? lb'; None when it does not read. The LAST separator that
    leaves a quantity with a unit on the left and a unit on the right wins, so
    '5 in in mm' works. Kinds are not checked here (convert() raises across kinds)."""
    if not text:
        return None
    text = str(text).strip()
    matches = list(_SEPARATORS.finditer(text))
    for match in reversed(matches):
        left, right = text[:match.start()], text[match.end():]
        target = resolve(right.strip().lstrip('?').strip().rstrip('?').strip())
        if target is None:
            continue
        quantity = parse_quantity(left)
        if quantity is None or quantity[1] is None:
            continue
        return (quantity[0], quantity[1], target)
    return None


def convert_text(text):
    """(value, to_unit) for a conversion sentence (see parse_conversion). Raises ValueError
    with a readable message when it does not read or the kinds differ."""
    parsed = parse_conversion(text)
    if parsed is None:
        raise ValueError('Type a conversion like 12\' 6" to mm or 250 sqft in m2.')
    value, a, b = parsed
    return convert(value, a, b), b


def symbol(unit, ascii=False):
    """The display symbol of a unit ('m2' -> 'm²'), or the canonical one with ascii=True.
    Unknown units come back unchanged."""
    canonical = resolve(unit) or unit
    if ascii:
        return canonical
    return DISPLAY.get(canonical, canonical)


def format(value, unit, decimals=2, ascii=False):  # noqa: A001 (contract name)
    """'1,250.00 mm': thousands separators, fixed decimals, then the unit symbol
    (pretty superscripts unless ascii=True). unit None or '' gives just the number."""
    if value is None:
        return ''
    decimals = max(0, int(decimals))
    text = ('{:,.%df}' % decimals).format(float(value))
    if text.startswith('-') and float(text.replace(',', '').lstrip('-') or 0) == 0:
        text = text[1:]
    if not unit:
        return text
    return '%s %s' % (text, symbol(unit, ascii))
