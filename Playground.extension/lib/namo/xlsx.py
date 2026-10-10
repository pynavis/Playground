# -*- coding: utf-8 -*-
"""Styled Excel (.xlsx) writer: fills, number formats, widths, frozen headers,
autofilter, merged title rows, hyperlinks and embedded images. No Excel needed.

Writes the OOXML package directly (zipfile + string-built XML, every text escaped, only
XML 1.0 characters). Pure: no Navisworks, no .NET; same output on CPython and IronPython.

    wb = xlsx.Workbook(title='Clash report', author='Amol')
    ws = wb.sheet('Clashes')
    ws.title('Level 3 coordination', span=5)
    ws.columns([('Name', 28, None), ('Status', 12, None), ('Distance', 12, 'num2'),
                ('Found', 12, 'date'), ('Image', 24, None)])
    ws.row(['Clash1', 'New', -0.042, datetime.date(2026, 10, 5)],
           styles=[None, xlsx.status_style('New'), None, None])
    ws.write(2, 4, xlsx.Link('https://example.com', 'Open'))
    ws.image(png_bytes, row=2, col=4, width_px=160, fit_cell=True)
    ws.autofilter()
    wb.save(path)

Rows and columns are 0-based everywhere in this API. Styles are referenced by name;
build your own with wb.style(...) or wb.fill_style(hex) (cached, for heatmaps).
"""
import datetime
import hashlib
import io
import os
import re
import zipfile

from namo import png as _png

# ---------------------------------------------------------------------------
# Limits and constants
# ---------------------------------------------------------------------------

MAX_ROWS = 1048576
MAX_COLS = 16384
MAX_TEXT = 32767            # Excel's per-cell character limit
MAX_LINKS = 65530           # Excel's per-sheet hyperlink limit
EMU_PER_PX = 9525           # 914400 EMU per inch / 96 px per inch

_NS_MAIN = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
_NS_R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
_NS_PKG = 'http://schemas.openxmlformats.org/package/2006/relationships'
_REL = _NS_R + '/'
_REL_CORE = 'http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties'
_CT_PREFIX = 'application/vnd.openxmlformats-officedocument.'
_CT = {
    'workbook': _CT_PREFIX + 'spreadsheetml.sheet.main+xml',
    'worksheet': _CT_PREFIX + 'spreadsheetml.worksheet+xml',
    'styles': _CT_PREFIX + 'spreadsheetml.styles+xml',
    'sst': _CT_PREFIX + 'spreadsheetml.sharedStrings+xml',
    'drawing': _CT_PREFIX + 'drawing+xml',
    'app': _CT_PREFIX + 'extended-properties+xml',
    'core': 'application/vnd.openxmlformats-package.core-properties+xml',
    'rels': 'application/vnd.openxmlformats-package.relationships+xml',
}
_IMAGE_TYPES = {'png': ('png', 'image/png'), 'jpeg': ('jpeg', 'image/jpeg'),
                'gif': ('gif', 'image/gif'), 'bmp': ('bmp', 'image/bmp')}
_DECL = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'

# Number formats Excel knows by id. Locale-dependent date ids (14, 22...) are left
# out on purpose: 'yyyy-mm-dd' is written as a custom format so it reads the same everywhere.
_BUILTIN_FORMATS = {
    'General': 0, '0': 1, '0.00': 2, '#,##0': 3, '#,##0.00': 4, '0%': 9, '0.00%': 10,
    '0.00E+00': 11, 'h:mm': 20, 'h:mm:ss': 21, '@': 49,
}
_FIRST_CUSTOM_FORMAT = 164

_BORDER_SIDES = ('left', 'right', 'top', 'bottom')
_BORDER_STYLES = ('thin', 'medium', 'thick', 'dashed', 'dotted', 'hair', 'double')
_H_ALIGN = ('general', 'left', 'center', 'right', 'fill', 'justify', 'centerContinuous',
            'distributed')
_V_ALIGN = ('top', 'center', 'bottom', 'justify', 'distributed')

_UNSET = object()
_STYLE_DEFAULTS = (
    ('bold', False), ('italic', False), ('underline', False), ('size', None),
    ('color', None), ('font', None), ('fill', None), ('border', False),
    ('border_color', 'BFBFBF'), ('border_style', 'thin'), ('align', None),
    ('valign', None), ('wrap', False), ('num_format', None), ('indent', 0),
)
DEFAULT_FONT = 'Calibri'
DEFAULT_SIZE = 11

# Built-in named styles (name -> keyword arguments of Workbook.style).
BUILTIN_STYLES = (
    ('cell', {}),
    ('header', {'bold': True, 'fill': 'F2F2F2', 'border': 'bottom', 'border_color': 'A6A6A6',
                'valign': 'center'}),
    ('title', {'bold': True, 'size': 14, 'valign': 'center'}),
    ('muted', {'color': '6B6B6B'}),
    ('bold', {'bold': True}),
    ('center', {'align': 'center'}),
    ('int', {'num_format': '#,##0'}),
    ('num1', {'num_format': '#,##0.0'}),
    ('num2', {'num_format': '#,##0.00'}),
    ('pct', {'num_format': '0%'}),
    ('pct1', {'num_format': '0.0%'}),
    ('date', {'num_format': 'yyyy-mm-dd'}),
    ('datetime', {'num_format': 'yyyy-mm-dd hh:mm'}),
    ('time', {'num_format': 'hh:mm'}),
    ('good', {'fill': 'E6F4EA', 'color': '0F6C33'}),
    ('warn', {'fill': 'FFF4D6', 'color': '7A5A00'}),
    ('bad', {'fill': 'FDE7E9', 'color': 'A80F1D'}),
    ('info', {'fill': 'E5F0FA', 'color': '0B4F8A'}),
    ('link', {'color': '0563C1', 'underline': True}),
    ('wrap', {'wrap': True, 'valign': 'top'}),
    # Clash statuses in Navisworks' own colours, softened to a readable wash.
    ('status_new', {'fill': 'F9D3D3', 'color': '8E1414'}),
    ('status_active', {'fill': 'FCE1C7', 'color': '8A3B00'}),
    ('status_reviewed', {'fill': 'D6E6F8', 'color': '0B4A85'}),
    ('status_approved', {'fill': 'D4EDDA', 'color': '1B5E20'}),
    ('status_resolved', {'fill': 'FFF1B8', 'color': '6B5300'}),
)
STATUS_STYLES = ('status_new', 'status_active', 'status_reviewed', 'status_approved',
                 'status_resolved')

_XML_BAD = re.compile(u'[\x00-\x08\x0b\x0c\x0e-\x1f\ufffe\uffff]')
_EXCEL_ESCAPE = re.compile(u'_(x[0-9A-Fa-f]{4}_)')
_BAD_SHEET = re.compile(u'[\\[\\]:*?/\\\\\x00-\x1f]')
_HEX = re.compile(u'^[0-9A-Fa-f]+$')
_SCHEME = re.compile(u'^[A-Za-z][A-Za-z0-9+.\\-]*:')
_DRIVE = re.compile(u'^[A-Za-z]:[\\\\/]')
_EPOCH = datetime.datetime(1899, 12, 30)


# ---------------------------------------------------------------------------
# Small public helpers
# ---------------------------------------------------------------------------

class Formula(object):
    """A formula cell: Formula('SUM(B2:B9)') (leading '=' optional).

    value: optional cached result Excel shows before it recalculates (workbooks with
    formulas are flagged to recalculate fully on open, so this is rarely needed).
    """

    def __init__(self, text, value=None):
        text = u'%s' % (text,)
        self.text = text[1:] if text.startswith(u'=') else text
        self.value = value

    def __repr__(self):
        return 'Formula(%r)' % self.text


class Link(object):
    """A hyperlink cell: Link(target, text=None, tip=None).

    target: an http(s)/mailto URL, a file path (absolute 'C:\\...', UNC '\\\\server\\...'
    or relative to the workbook) or '#Sheet!A1' for a place inside the workbook.
    text: what the cell shows (default: the target, without a leading '#'). tip: hover
    text. Quote sheet names with spaces: Link('#' + quote_sheet('My sheet') + '!A1').
    """

    def __init__(self, target, text=None, tip=None):
        self.target = u'%s' % (target,)
        if text is None:
            text = self.target[1:] if self.target.startswith(u'#') else self.target
        self.text = u'%s' % (text,)
        self.tip = tip

    def __repr__(self):
        return 'Link(%r, %r)' % (self.target, self.text)


def col_letter(col):
    """0-based column index -> letters: 0 -> 'A', 25 -> 'Z', 26 -> 'AA'."""
    col = int(col)
    if col < 0:
        raise ValueError('column index must be >= 0, got %d' % col)
    n = col + 1
    letters = ''
    while n > 0:
        n, rem = divmod(n - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def cell_ref(row, col, absolute=False):
    """0-based (row, col) -> 'B3' (or '$B$3' when absolute)."""
    if absolute:
        return '$%s$%d' % (col_letter(col), int(row) + 1)
    return '%s%d' % (col_letter(col), int(row) + 1)


def range_ref(r1, c1, r2, c2, absolute=False):
    """0-based corners -> 'A1:C5' (single cell -> 'A1')."""
    a = cell_ref(min(r1, r2), min(c1, c2), absolute)
    b = cell_ref(max(r1, r2), max(c1, c2), absolute)
    return a if a == b else '%s:%s' % (a, b)


def quote_sheet(name):
    """Sheet name as used inside formulas and links: "'My sheet'" (quotes doubled)."""
    return u"'%s'" % name.replace(u"'", u"''")


def sanitize_sheet_name(name, existing=()):
    """A name Excel accepts: no []:*?/\\, 1..31 chars, no edge apostrophes, not
    'History', unique (case-insensitive) against `existing` by adding ' (2)', ' (3)'..."""
    text = _BAD_SHEET.sub(u' ', u'%s' % ('' if name is None else name))
    text = u' '.join(text.split()).strip(u"'").strip()
    if not text:
        text = u'Sheet'
    if text.lower() == u'history':
        text = u'History sheet'
    text = text[:31].rstrip().rstrip(u"'").rstrip() or u'Sheet'
    taken = set(n.lower() for n in existing)
    base = text
    number = 2
    while text.lower() in taken:
        suffix = u' (%d)' % number
        text = base[:31 - len(suffix)].rstrip().rstrip(u"'").rstrip() + suffix
        number += 1
    return text


def status_style(status):
    """Built-in style name for a Navisworks clash status ('New', 'active'...), or None."""
    if status is None:
        return None
    name = 'status_' + (u'%s' % status).strip().lower()
    return name if name in STATUS_STYLES else None


def px_to_points(px):
    """Pixel height (96 dpi) -> Excel row height in points."""
    return px * 0.75


def px_to_chars(px):
    """Pixel width -> Excel column width in characters (default Calibri 11 font)."""
    return max(0.0, (px - 5) / 7.0)


def chars_to_px(chars):
    """Excel column width in characters -> pixels (default Calibri 11 font)."""
    return int(chars * 7 + 5)


def excel_serial(value):
    """date / datetime / time -> Excel serial number (1900 date system)."""
    if isinstance(value, datetime.datetime):
        if value.tzinfo is not None:
            value = value.replace(tzinfo=None)
        delta = value - _EPOCH
        return delta.days + (delta.seconds + delta.microseconds / 1e6) / 86400.0
    if isinstance(value, datetime.date):
        return (value - _EPOCH.date()).days
    if isinstance(value, datetime.time):
        return (value.hour * 3600 + value.minute * 60 + value.second
                + value.microsecond / 1e6) / 86400.0
    raise TypeError('not a date, datetime or time: %r' % (value,))


# ---------------------------------------------------------------------------
# XML text helpers
# ---------------------------------------------------------------------------

def _xml_text(text):
    text = _XML_BAD.sub(u'', text)
    return text.replace(u'&', u'&amp;').replace(u'<', u'&lt;').replace(u'>', u'&gt;')


def _xml_attr(text):
    return (_xml_text(u'%s' % text).replace(u'"', u'&quot;').replace(u'\n', u'&#10;')
            .replace(u'\r', u'&#13;').replace(u'\t', u'&#9;'))


def _cell_text(text):
    """Shared-string text: newlines normalised, Excel's _xHHHH_ escape protected, capped."""
    text = text.replace(u'\r\n', u'\n').replace(u'\r', u'\n')
    text = _EXCEL_ESCAPE.sub(u'_x005F_\\1', text)
    if len(text) > MAX_TEXT:
        text = text[:MAX_TEXT]
    return _xml_text(text)


def _num(value):
    """Shortest text that round-trips the float, identical on CPython and IronPython."""
    if isinstance(value, bool):
        return '1' if value else '0'
    if isinstance(value, int):
        return '%d' % value
    value = float(value)
    for precision in (15, 16, 17):
        text = '%.*g' % (precision, value)
        if float(text) == value:
            return text
    return text


def _is_finite(value):
    return value == value and value not in (float('inf'), float('-inf'))


def _color(value):
    """'RRGGBB' / '#RRGGBB' / 'AARRGGBB' / (r, g, b) -> 'AARRGGBB'; None stays None."""
    if value is None:
        return None
    if isinstance(value, (tuple, list)):
        if len(value) != 3:
            raise ValueError('colour tuples need three 0..255 values: %r' % (value,))
        return 'FF%02X%02X%02X' % tuple(max(0, min(255, int(v))) for v in value)
    text = (u'%s' % value).strip().lstrip(u'#')
    if not _HEX.match(text) or len(text) not in (6, 8):
        raise ValueError("colours are 'RRGGBB' hex text, got %r" % (value,))
    text = text.upper()
    return text if len(text) == 8 else 'FF' + text


def _luminance(argb):
    r, g, b = [int(argb[i:i + 2], 16) / 255.0 for i in (2, 4, 6)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in (r, g, b)]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _border_sides(value):
    if value is None or value is False or value == '':
        return ()
    if value is True:
        return _BORDER_SIDES
    if isinstance(value, (tuple, list)):
        tokens = [(u'%s' % side).strip().lower() for side in value]
    else:
        tokens = re.split(r'[\s,]+', (u'%s' % value).strip().lower())
    if 'all' in tokens or 'box' in tokens:
        return _BORDER_SIDES
    for token in tokens:
        if token not in _BORDER_SIDES:
            raise ValueError('unknown border side %r (use left, right, top, bottom or all)' % token)
    return tuple(side for side in _BORDER_SIDES if side in tokens)


def _normalise_style(values):
    """Validate and canonicalise one style's settings (a plain dict)."""
    out = {}
    out['bold'] = bool(values['bold'])
    out['italic'] = bool(values['italic'])
    out['underline'] = bool(values['underline'])
    size = values['size']
    out['size'] = None if size is None else float(size)
    out['color'] = _color(values['color'])
    out['font'] = values['font'] or None
    out['fill'] = _color(values['fill'])
    out['border'] = _border_sides(values['border'])
    out['border_color'] = _color(values['border_color'] or 'BFBFBF')
    style = values['border_style'] or 'thin'
    if style not in _BORDER_STYLES:
        raise ValueError('unknown border style %r' % (style,))
    out['border_style'] = style
    align = values['align']
    if align is not None and align not in _H_ALIGN:
        raise ValueError('unknown align %r (left, center, right...)' % (align,))
    out['align'] = align
    valign = values['valign']
    if valign == 'middle':
        valign = 'center'
    if valign is not None and valign not in _V_ALIGN:
        raise ValueError('unknown valign %r (top, center, bottom)' % (valign,))
    out['valign'] = valign
    out['wrap'] = bool(values['wrap'])
    out['num_format'] = values['num_format'] or None
    out['indent'] = int(values['indent'] or 0)
    return out


# ---------------------------------------------------------------------------
# Workbook
# ---------------------------------------------------------------------------

class Workbook(object):
    """An in-memory workbook. Add sheets with sheet(name), then save(path).

    title / author go into the file properties; created (a naive UTC datetime,
    default now) stamps the properties and the zip entries, so a fixed value gives
    byte-identical output for identical input.
    """

    def __init__(self, title=None, author=None, created=None):
        self.title = title
        self.author = author
        self.created = created or datetime.datetime.utcnow().replace(microsecond=0)
        self.sheets = []
        self._styles = {}
        for name, kwargs in BUILTIN_STYLES:
            self.style(name, **kwargs)

    # --- styles --------------------------------------------------------------------

    def style(self, name, bold=_UNSET, italic=_UNSET, size=_UNSET, color=_UNSET, fill=_UNSET,
              border=_UNSET, align=_UNSET, valign=_UNSET, wrap=_UNSET, num_format=_UNSET,
              underline=_UNSET, base=None, font=_UNSET, border_color=_UNSET,
              border_style=_UNSET, indent=_UNSET):
        """Define (or redefine) a named cell style; returns the name.

        Colours are 'RRGGBB' hex. border: False, True/'all', or sides like 'bottom' or
        'top bottom'. align: 'left'|'center'|'right'|...; valign: 'top'|'center'|'bottom'.
        num_format: an Excel format code ('#,##0.0', 'yyyy-mm-dd', '0.0%'...).
        base: start from another style's settings and override only what you pass.
        """
        if base is not None:
            values = dict(self._style_settings(base))
            values['border'] = values['border'] or False
        else:
            values = dict(_STYLE_DEFAULTS)
        passed = (('bold', bold), ('italic', italic), ('size', size), ('color', color),
                  ('fill', fill), ('border', border), ('align', align), ('valign', valign),
                  ('wrap', wrap), ('num_format', num_format), ('underline', underline),
                  ('font', font), ('border_color', border_color),
                  ('border_style', border_style), ('indent', indent))
        for key, value in passed:
            if value is not _UNSET:
                values[key] = value
        self._styles[name] = _normalise_style(values)
        return name

    def _style_settings(self, name):
        if name not in self._styles:
            raise ValueError('unknown xlsx style %r; define it with Workbook.style()' % (name,))
        return self._styles[name]

    def has_style(self, name):
        """True when a style of that name exists."""
        return name in self._styles

    def style_names(self):
        """Every defined style name, sorted."""
        return sorted(self._styles)

    def fill_style(self, hex_fill, base='cell'):
        """A cached style that is `base` with a solid fill (for heatmaps and dynamic fills).

        The text turns white on dark fills so it stays readable. Returns the style name
        ('fill:RRGGBB:base'); calling again with the same colour and base reuses it.
        """
        argb = _color(hex_fill)
        name = 'fill:%s:%s' % (argb[2:], base)
        if name not in self._styles:
            settings = dict(self._style_settings(base))
            settings['fill'] = argb
            if _luminance(argb) < 0.18:
                settings['color'] = 'FFFFFFFF'
            self._styles[name] = settings
        return name

    # --- sheets --------------------------------------------------------------------

    def sheet(self, name):
        """Add a worksheet. The name is sanitised (31 chars, no []:*?/\\) and deduped."""
        clean = sanitize_sheet_name(name, [ws.name for ws in self.sheets])
        ws = Worksheet(self, clean)
        self.sheets.append(ws)
        return ws

    def get_sheet(self, name):
        """The sheet with this (final, sanitised) name, case-insensitive, or None."""
        for ws in self.sheets:
            if ws.name.lower() == (u'%s' % name).lower():
                return ws
        return None

    # --- output --------------------------------------------------------------------

    def to_bytes(self):
        """The whole .xlsx package as bytes."""
        return _Package(self).build()

    def save(self, path):
        """Write the workbook to path atomically (temp file, then replace); returns path.

        Raises IOError/OSError when the folder is missing or the file is open in Excel.
        """
        data = self.to_bytes()
        folder = os.path.dirname(os.path.abspath(path))
        if not os.path.isdir(folder):
            os.makedirs(folder)
        temp = path + '.tmp'
        try:
            handle = open(temp, 'wb')
            try:
                handle.write(data)
            finally:
                handle.close()
            os.replace(temp, path)
        finally:
            if os.path.exists(temp):
                try:
                    os.remove(temp)
                except OSError:
                    pass
        return path


# ---------------------------------------------------------------------------
# Worksheet
# ---------------------------------------------------------------------------

class Worksheet(object):
    """One sheet. Write with title()/columns()/row() (appending at next_row) or
    write(row, col, value) anywhere; all indexes are 0-based."""

    def __init__(self, workbook, name):
        self.workbook = workbook
        self.name = name
        self.next_row = 0
        self._rows = {}            # row -> {col: (value, style name or None)}
        self._widths = {}          # col -> characters
        self._heights = {}         # row -> points
        self._merges = []          # (r1, c1, r2, c2)
        self._images = []
        self._freeze = None        # (rows, cols)
        self._filter = None        # (first_row, last_row, first_col, last_col), None = auto
        self._has_filter = False
        self._header_row = None
        self._header_cols = 0
        self._col_styles = {}
        self._auto_width = set()
        self._tab_color = None

    # --- appending -------------------------------------------------------------------

    def title(self, text, span=6, style='title', height=22):
        """A bold title row at next_row, merged across `span` columns. Returns its row."""
        row = self.next_row
        self.write(row, 0, text, style)
        if span and span > 1:
            self.merge(row, 0, row, span - 1)
        if height:
            self.set_height(row, height)
        self.next_row = row + 1
        return row

    def subtitle(self, text, span=6, style='muted'):
        """A muted line (date, filter, source...) at next_row, merged across `span`."""
        row = self.next_row
        self.write(row, 0, text, style)
        if span and span > 1:
            self.merge(row, 0, row, span - 1)
        self.next_row = row + 1
        return row

    def skip(self, rows=1):
        """Leave `rows` blank rows; returns the new next_row."""
        self.next_row += max(0, int(rows))
        return self.next_row

    def columns(self, specs, freeze=True):
        """Header row at next_row from [(header, width_chars, style_or_None), ...].

        width None sizes the column to its content at save time. The style becomes
        the default for that column's cells below the header. Freezes the panes below
        the header (keeping any frozen columns) and remembers the header row for
        autofilter(). (header,) / (header, width) tuples and plain strings also work.
        Returns the header row index.
        """
        row = self.next_row
        for col, spec in enumerate(specs):
            if isinstance(spec, (tuple, list)):
                header = spec[0]
                width = spec[1] if len(spec) > 1 else None
                style = spec[2] if len(spec) > 2 else None
            else:
                header, width, style = spec, None, None
            self.write(row, col, header, 'header')
            if width is None:
                self._auto_width.add(col)
            else:
                self.set_width(col, width)
            if style is not None:
                self.workbook._style_settings(style)
                self._col_styles[col] = style
            else:
                self._col_styles.pop(col, None)
        self._header_row = row
        self._header_cols = len(specs)
        if freeze:
            cols = self._freeze[1] if self._freeze else 0
            self.freeze(row + 1, cols)
        self.next_row = row + 1
        return row

    def row(self, values, styles=None, height=None):
        """Append one row at next_row. styles: one name for every cell, or a per-cell
        list (None entries fall back to the column style, then the value type).
        Returns the row index."""
        row = self.next_row
        values = list(values)
        if styles is None or isinstance(styles, str):
            per_cell = [styles] * len(values)
        else:
            per_cell = list(styles) + [None] * max(0, len(values) - len(styles))
        for col, value in enumerate(values):
            self.write(row, col, value, per_cell[col])
        if height is not None:
            self.set_height(row, height)
        self.next_row = row + 1
        return row

    # --- cells -----------------------------------------------------------------------

    def write(self, row, col, value, style=None):
        """Set one cell. value: str, int, float, bool, None, date, datetime, time,
        Formula, Link (or anything else, written as its text). style None picks the
        column style (below a columns() header), else a date/time/link default.
        Moves next_row past this row."""
        row = int(row)
        col = int(col)
        if not 0 <= row < MAX_ROWS or not 0 <= col < MAX_COLS:
            raise ValueError('cell (%d, %d) is outside the Excel grid' % (row, col))
        kind = type(value)
        if kind not in _PLAIN_TYPES and value is not None and not isinstance(
                value, (str, int, float, Formula, Link, datetime.date, datetime.time)):
            value = _coerce(value)
            kind = type(value)
        if style is None and self._header_row is not None and row > self._header_row:
            style = self._col_styles.get(col)
        if style is None and kind not in _PLAIN_TYPES:
            style = _type_style(value)
        if style is not None and style not in self.workbook._styles:
            self.workbook._style_settings(style)          # raises the helpful error
        cells = self._rows.get(row)
        if cells is None:
            cells = self._rows[row] = {}
        cells[col] = (value, style)
        if row >= self.next_row:
            self.next_row = row + 1

    def cell(self, row, col):
        """(value, style) stored at a cell, or (None, None)."""
        return self._rows.get(int(row), {}).get(int(col), (None, None))

    # --- layout ----------------------------------------------------------------------

    def set_width(self, col, chars):
        """Column width in characters (Excel's unit; about 7 px each)."""
        self._widths[int(col)] = max(0.0, min(255.0, float(chars)))
        self._auto_width.discard(int(col))

    def set_height(self, row, points):
        """Row height in points (1 pt = 4/3 px)."""
        self._heights[int(row)] = max(0.0, min(409.0, float(points)))

    def merge(self, r1, c1, r2, c2):
        """Merge a block of cells (0-based, inclusive). A single cell is ignored.
        Raises ValueError when it overlaps an existing merge (Excel would repair it)."""
        r1, r2 = sorted((int(r1), int(r2)))
        c1, c2 = sorted((int(c1), int(c2)))
        if r1 == r2 and c1 == c2:
            return
        for m in self._merges:
            if not (r2 < m[0] or r1 > m[2] or c2 < m[1] or c1 > m[3]):
                raise ValueError('merge %s overlaps %s' % (range_ref(r1, c1, r2, c2),
                                                           range_ref(*m)))
        self._merges.append((r1, c1, r2, c2))

    def freeze(self, rows=1, cols=0):
        """Freeze the top `rows` rows and left `cols` columns (0, 0 unfreezes)."""
        rows = max(0, int(rows))
        cols = max(0, int(cols))
        self._freeze = (rows, cols) if (rows or cols) else None

    def autofilter(self, first_row=None, last_row=None, first_col=None, last_col=None):
        """Turn on the filter dropdowns. Defaults: from the columns() header row (else
        row 0) to the last written row, across the header's columns (else all used
        columns). Defaults are resolved at save time, so rows appended later count."""
        self._has_filter = True
        self._filter = (first_row, last_row, first_col, last_col)

    def tab_color(self, hex_color):
        """Colour of the sheet tab ('RRGGBB'), or None for the default."""
        self._tab_color = _color(hex_color)

    def autofit(self, min_chars=6, max_chars=60, cols=None):
        """Size columns to their longest value (all used columns, or the given list).
        Cells merged across several columns (titles) are ignored."""
        widths = self._content_widths()
        targets = cols if cols is not None else sorted(widths)
        for col in targets:
            width = widths.get(col, 0)
            self.set_width(col, max(min_chars, min(max_chars, width + 2)))

    def _content_widths(self):
        spanned = set()          # cells inside merges that cross columns (titles)
        for r1, c1, r2, c2 in self._merges:
            if c2 > c1:
                for r in range(r1, r2 + 1):
                    for c in range(c1, c2 + 1):
                        spanned.add((r, c))
        widths = {}
        for row, cells in self._rows.items():
            for col, (value, style) in cells.items():
                if (row, col) in spanned:
                    continue
                length = _display_len(value)
                if style == 'header':
                    length += 1
                if length > widths.get(col, 0):
                    widths[col] = length
        return widths

    # --- images ----------------------------------------------------------------------

    def image(self, path_or_bytes, row, col, width_px=None, height_px=None, offset_px=(0, 0),
              fit_cell=False, description=None, anchor='one'):
        """Embed a PNG/JPEG (also GIF/BMP) with its top-left corner in cell (row, col).

        Size defaults to the image's own pixel size; give one of width_px/height_px to
        scale and keep the aspect ratio. offset_px nudges it inside the cell.
        fit_cell=True grows that row and column so the picture fits inside the cell.
        anchor 'one' (default, oneCellAnchor): the picture moves with its cell but keeps
        its size, and stays visible when a filter hides its row. anchor 'cell'
        (twoCellAnchor): it moves AND sizes with the cells it covers, so sorting and
        filtering take it along with its row: use it for row thumbnails in a filtered
        table. Returns the (width, height) in pixels.
        """
        if anchor not in ('one', 'cell'):
            raise ValueError("anchor is 'one' or 'cell', not %r" % (anchor,))
        if isinstance(path_or_bytes, (bytes, bytearray)):
            data = bytes(path_or_bytes)
            label = description
        else:
            handle = open(path_or_bytes, 'rb')
            try:
                data = handle.read()
            finally:
                handle.close()
            label = description or os.path.basename(u'%s' % path_or_bytes)
        kind = _png.sniff(data)
        if kind not in _IMAGE_TYPES:
            raise ValueError('Excel can embed PNG, JPEG, GIF or BMP images, not %s' % (kind or 'this file'))
        native = _png.image_size(data)
        if native is None or native[0] <= 0 or native[1] <= 0:
            raise ValueError('cannot read the pixel size of this %s image' % kind)
        w, h = native
        if width_px and height_px:
            w, h = float(width_px), float(height_px)
        elif width_px:
            w, h = float(width_px), float(width_px) * native[1] / float(native[0])
        elif height_px:
            w, h = float(height_px) * native[0] / float(native[1]), float(height_px)
        dx, dy = offset_px or (0, 0)
        entry = {'data': data, 'kind': kind, 'row': int(row), 'col': int(col),
                 'w': int(round(w)), 'h': int(round(h)), 'dx': int(dx), 'dy': int(dy),
                 'descr': label or '', 'anchor': anchor}
        self._images.append(entry)
        if fit_cell:
            need_h = px_to_points(entry['h'] + entry['dy'] + 2)
            if self._heights.get(entry['row'], 15.0) < need_h:
                self.set_height(entry['row'], need_h)
            need_w = px_to_chars(entry['w'] + entry['dx'] + 2)
            if self._widths.get(entry['col'], 8.43) < need_w:
                self.set_width(entry['col'], need_w)
        if int(row) >= self.next_row:
            self.next_row = int(row) + 1
        return entry['w'], entry['h']

    # --- queries ---------------------------------------------------------------------

    @property
    def header_row(self):
        """Row index of the last columns() header, or None."""
        return self._header_row

    def used_range(self):
        """(min_row, min_col, max_row, max_col) of written cells, or None when empty."""
        if not self._rows:
            return None
        rows = [r for r, cells in self._rows.items() if cells]
        if not rows:
            return None
        cols = [c for cells in self._rows.values() for c in cells]
        return min(rows), min(cols), max(rows), max(cols)


_PLAIN_TYPES = frozenset([str, int, float, bool, type(None)])


def _type_style(value):
    if isinstance(value, datetime.datetime):
        return 'datetime'
    if isinstance(value, datetime.date):
        return 'date'
    if isinstance(value, datetime.time):
        return 'time'
    if isinstance(value, Link):
        return 'link'
    return None


def _coerce(value):
    """Values outside the native set: .NET DateTime, Decimal, anything else -> text."""
    if all(hasattr(value, a) for a in ('Year', 'Month', 'Day', 'Hour', 'Minute', 'Second')):
        try:
            return datetime.datetime(int(value.Year), int(value.Month), int(value.Day),
                                     int(value.Hour), int(value.Minute), int(value.Second))
        except (TypeError, ValueError):
            pass
    try:
        import decimal
        if isinstance(value, decimal.Decimal):
            return float(value)
    except ImportError:
        pass
    return u'%s' % (value,)


def _final_widths(ws):
    """Column widths as written: explicit widths plus auto widths resolved from content."""
    widths = dict(ws._widths)
    if ws._auto_width:
        content = ws._content_widths()
        for col in ws._auto_width:
            widths[col] = max(6, min(60, content.get(col, 0) + 2))
    return widths


def _walk(start, distance_px, size_px):
    """From the top/left edge of cell `start`, go distance_px across cells whose sizes
    size_px(index) gives -> (cell index, offset px inside it) for a twoCellAnchor end."""
    index = start
    remaining = float(distance_px)
    while remaining > size_px(index) and index < MAX_ROWS:
        remaining -= size_px(index)
        index += 1
    return index, remaining


def _display_len(value):
    if value is None:
        return 0
    if isinstance(value, Link):
        value = value.text
    if isinstance(value, Formula):
        return 10
    if isinstance(value, bool):
        return 5
    if isinstance(value, datetime.datetime):
        return 16
    if isinstance(value, (datetime.date, datetime.time)):
        return 10
    if isinstance(value, int):
        return len('{:,}'.format(value))
    if isinstance(value, float):
        return min(16, len(_num(round(value, 2))) + 2)
    text = u'%s' % value
    return max(len(line) for line in text.split(u'\n')) if text else 0


# ---------------------------------------------------------------------------
# Package writer
# ---------------------------------------------------------------------------

class _Package(object):
    """Builds every part of the OOXML package for one Workbook."""

    def __init__(self, workbook):
        self.wb = workbook
        self.strings = []
        self.string_index = {}       # escaped text -> index
        self.raw_index = {}          # caller's text -> index (skips re-escaping repeats)
        self.string_refs = 0
        self.media = []              # [(filename, data, kind)]
        self.media_index = {}        # md5 -> filename
        self.style_index = {}
        self.has_formula = False

    # --- shared strings --------------------------------------------------------------

    def sst(self, raw):
        """Shared-string index for the caller's text (escaped once per distinct text)."""
        self.string_refs += 1
        index = self.raw_index.get(raw)
        if index is None:
            text = _cell_text(raw)
            index = self.string_index.get(text)
            if index is None:
                index = len(self.strings)
                self.strings.append(text)
                self.string_index[text] = index
            self.raw_index[raw] = index
        return index

    # --- styles ----------------------------------------------------------------------

    def styles_xml(self):
        numfmts = []
        numfmt_ids = {}
        fonts = []
        font_ids = {}
        fills = []
        fill_ids = {}
        borders = []
        border_ids = {}
        xfs = []
        xf_ids = {}

        def font_id(s):
            key = (s['bold'], s['italic'], s['underline'], s['size'] or DEFAULT_SIZE,
                   s['color'], s['font'] or DEFAULT_FONT)
            if key not in font_ids:
                font_ids[key] = len(fonts)
                fonts.append(key)
            return font_ids[key]

        def fill_id(s):
            key = s['fill']
            if key not in fill_ids:
                fill_ids[key] = len(fills) + 2      # 0 none, 1 gray125 are reserved
                fills.append(key)
            return fill_ids[key]

        def border_id(s):
            if not s['border']:
                return 0
            key = (s['border'], s['border_style'], s['border_color'])
            if key not in border_ids:
                border_ids[key] = len(borders) + 1
                borders.append(key)
            return border_ids[key]

        def numfmt_id(s):
            code = s['num_format']
            if not code or code == 'General':
                return 0
            if code in _BUILTIN_FORMATS:
                return _BUILTIN_FORMATS[code]
            if code not in numfmt_ids:
                numfmt_ids[code] = _FIRST_CUSTOM_FORMAT + len(numfmts)
                numfmts.append(code)
            return numfmt_ids[code]

        default = dict(_normalise_style(dict(_STYLE_DEFAULTS)))
        font_id(default)                      # font 0 is the plain default font
        base_xf = (0, 0, 0, 0, None, None, False, 0)
        xfs.append(base_xf)
        xf_ids[base_xf] = 0
        for name in sorted(self.wb._styles):
            s = self.wb._styles[name]
            fid = font_id(s)
            fl = fill_id(s) if s['fill'] else 0
            key = (numfmt_id(s), fid, fl, border_id(s), s['align'], s['valign'], s['wrap'],
                   s['indent'])
            if key not in xf_ids:
                xf_ids[key] = len(xfs)
                xfs.append(key)
            self.style_index[name] = xf_ids[key]

        parts = [_DECL, '<styleSheet xmlns="%s">' % _NS_MAIN]
        if numfmts:
            parts.append('<numFmts count="%d">' % len(numfmts))
            for code in numfmts:
                parts.append('<numFmt numFmtId="%d" formatCode="%s"/>'
                             % (numfmt_ids[code], _xml_attr(code)))
            parts.append('</numFmts>')
        parts.append('<fonts count="%d">' % len(fonts))
        for bold, italic, underline, size, color, face in fonts:
            parts.append('<font>%s%s%s<sz val="%s"/>%s<name val="%s"/>%s</font>' % (
                '<b/>' if bold else '', '<i/>' if italic else '', '<u/>' if underline else '',
                _num(size), '<color rgb="%s"/>' % color if color else '', _xml_attr(face),
                '<family val="2"/>' if face == DEFAULT_FONT else ''))
        parts.append('</fonts>')
        parts.append('<fills count="%d">' % (len(fills) + 2))
        parts.append('<fill><patternFill patternType="none"/></fill>')
        parts.append('<fill><patternFill patternType="gray125"/></fill>')
        for argb in fills:
            parts.append('<fill><patternFill patternType="solid"><fgColor rgb="%s"/>'
                         '<bgColor indexed="64"/></patternFill></fill>' % argb)
        parts.append('</fills>')
        parts.append('<borders count="%d">' % (len(borders) + 1))
        parts.append('<border><left/><right/><top/><bottom/><diagonal/></border>')
        for sides, style, color in borders:
            edge = []
            for side in _BORDER_SIDES:
                if side in sides:
                    edge.append('<%s style="%s"><color rgb="%s"/></%s>' % (side, style, color, side))
                else:
                    edge.append('<%s/>' % side)
            parts.append('<border>%s<diagonal/></border>' % ''.join(edge))
        parts.append('</borders>')
        parts.append('<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/>'
                     '</cellStyleXfs>')
        parts.append('<cellXfs count="%d">' % len(xfs))
        for num_id, fid, fl, bid, align, valign, wrap, indent in xfs:
            attrs = ' numFmtId="%d" fontId="%d" fillId="%d" borderId="%d" xfId="0"' % (num_id, fid, fl, bid)
            if num_id:
                attrs += ' applyNumberFormat="1"'
            if fid:
                attrs += ' applyFont="1"'
            if fl:
                attrs += ' applyFill="1"'
            if bid:
                attrs += ' applyBorder="1"'
            align_attrs = ''
            if align:
                align_attrs += ' horizontal="%s"' % align
            if valign:
                align_attrs += ' vertical="%s"' % valign
            if wrap:
                align_attrs += ' wrapText="1"'
            if indent:
                align_attrs += ' indent="%d"' % indent
            if align_attrs:
                parts.append('<xf%s applyAlignment="1"><alignment%s/></xf>' % (attrs, align_attrs))
            else:
                parts.append('<xf%s/>' % attrs)
        parts.append('</cellXfs>')
        parts.append('<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>')
        parts.append('<dxfs count="0"/>')
        parts.append('<tableStyles count="0" defaultTableStyle="TableStyleMedium2" '
                     'defaultPivotStyle="PivotStyleLight16"/>')
        parts.append('</styleSheet>')
        return ''.join(parts)

    # --- one worksheet ---------------------------------------------------------------

    def cell_xml(self, ref, value, style):
        s_attr = ' s="%d"' % self.style_index[style] if style else ''
        kind = type(value)
        if kind is str:
            return '<c r="%s"%s t="s"><v>%d</v></c>' % (ref, s_attr, self.sst(value))
        if kind is int:
            return '<c r="%s"%s><v>%d</v></c>' % (ref, s_attr, value)
        if value is None:
            return '<c r="%s"%s/>' % (ref, s_attr) if s_attr else ''
        if isinstance(value, bool):
            return '<c r="%s"%s t="b"><v>%d</v></c>' % (ref, s_attr, 1 if value else 0)
        if isinstance(value, (int, float)):
            if isinstance(value, float) and not _is_finite(value):
                return '<c r="%s"%s t="e"><v>#NUM!</v></c>' % (ref, s_attr)
            return '<c r="%s"%s><v>%s</v></c>' % (ref, s_attr, _num(value))
        if isinstance(value, (datetime.date, datetime.time)):
            return '<c r="%s"%s><v>%s</v></c>' % (ref, s_attr, _num(excel_serial(value)))
        if isinstance(value, Formula):
            self.has_formula = True
            formula = '<f>%s</f>' % _xml_text(value.text)
            cached = value.value
            if cached is None:
                return '<c r="%s"%s>%s</c>' % (ref, s_attr, formula)
            if isinstance(cached, bool):
                return '<c r="%s"%s t="b">%s<v>%d</v></c>' % (ref, s_attr, formula, 1 if cached else 0)
            if isinstance(cached, (int, float)) and _is_finite(cached):
                return '<c r="%s"%s>%s<v>%s</v></c>' % (ref, s_attr, formula, _num(cached))
            return '<c r="%s"%s t="str">%s<v>%s</v></c>' % (ref, s_attr, formula,
                                                             _cell_text(u'%s' % (cached,)))
        if isinstance(value, Link):
            value = value.text
        index = self.sst(value if isinstance(value, str) else u'%s' % (value,))
        return '<c r="%s"%s t="s"><v>%d</v></c>' % (ref, s_attr, index)

    def sheet_xml(self, ws, position, link_rels):
        """Worksheet XML in schema order; fills link_rels with (rId, target) pairs."""
        parts = [_DECL, '<worksheet xmlns="%s" xmlns:r="%s">' % (_NS_MAIN, _NS_R)]
        if ws._tab_color:
            parts.append('<sheetPr><tabColor rgb="%s"/></sheetPr>' % ws._tab_color)
        used = ws.used_range()
        all_rows = set(r for r, cells in ws._rows.items() if cells) | set(ws._heights)
        if used:
            parts.append('<dimension ref="%s"/>' % range_ref(used[0], used[1], used[2], used[3]))
        else:
            parts.append('<dimension ref="A1"/>')
        parts.append(self.view_xml(ws, position == 0))
        parts.append('<sheetFormatPr defaultRowHeight="15"/>')
        widths = _final_widths(ws)
        if widths:
            parts.append('<cols>')
            for col in sorted(widths):
                parts.append('<col min="%d" max="%d" width="%s" customWidth="1"/>'
                             % (col + 1, col + 1, _num(round(widths[col], 2))))
            parts.append('</cols>')
        parts.append('<sheetData>')
        hyperlinks = []
        letters = {}
        for row in sorted(all_rows):
            cells = ws._rows.get(row, {})
            attrs = ''
            if row in ws._heights:
                attrs = ' ht="%s" customHeight="1"' % _num(round(ws._heights[row], 2))
            cell_parts = []
            number = '%d' % (row + 1)
            for col in sorted(cells):
                value, style = cells[col]
                letter = letters.get(col)
                if letter is None:
                    letter = letters[col] = col_letter(col)
                ref = letter + number
                cell_parts.append(self.cell_xml(ref, value, style))
                if isinstance(value, Link):
                    hyperlinks.append((ref, value))
            parts.append('<row r="%d"%s>%s</row>' % (row + 1, attrs, ''.join(cell_parts)))
        parts.append('</sheetData>')
        if ws._has_filter:
            parts.append('<autoFilter ref="%s"/>' % range_ref(*self.filter_range(ws)))
        if ws._merges:
            parts.append('<mergeCells count="%d">' % len(ws._merges))
            for merge in ws._merges:
                parts.append('<mergeCell ref="%s"/>' % range_ref(*merge))
            parts.append('</mergeCells>')
        if hyperlinks:
            parts.append('<hyperlinks>')
            for ref, link in hyperlinks[:MAX_LINKS]:
                target, location = _link_target(link.target)
                attrs = ' ref="%s"' % ref
                if location is not None:
                    attrs += ' location="%s"' % _xml_attr(location)
                else:
                    rid = 'rId%d' % (len(link_rels) + 1)
                    link_rels.append((rid, target))
                    attrs += ' r:id="%s"' % rid
                if link.tip:
                    attrs += ' tooltip="%s"' % _xml_attr(link.tip)
                attrs += ' display="%s"' % _xml_attr(link.text[:MAX_TEXT])
                parts.append('<hyperlink%s/>' % attrs)
            parts.append('</hyperlinks>')
        parts.append('<pageMargins left="0.7" right="0.7" top="0.75" bottom="0.75" '
                     'header="0.3" footer="0.3"/>')
        if ws._images:
            parts.append('<drawing r:id="rId%d"/>' % (len(link_rels) + 1))
        parts.append('</worksheet>')
        return ''.join(parts)

    def view_xml(self, ws, selected):
        tab = ' tabSelected="1"' if selected else ''
        if not ws._freeze:
            return '<sheetViews><sheetView%s workbookViewId="0"/></sheetViews>' % tab
        rows, cols = ws._freeze
        top_left = cell_ref(rows, cols)
        if rows and cols:
            pane = 'bottomRight'
        elif rows:
            pane = 'bottomLeft'
        else:
            pane = 'topRight'
        split = ''
        if cols:
            split += ' xSplit="%d"' % cols
        if rows:
            split += ' ySplit="%d"' % rows
        return ('<sheetViews><sheetView%s workbookViewId="0">'
                '<pane%s topLeftCell="%s" activePane="%s" state="frozen"/>'
                '<selection pane="%s" activeCell="%s" sqref="%s"/>'
                '</sheetView></sheetViews>' % (tab, split, top_left, pane, pane, top_left, top_left))

    def filter_range(self, ws):
        first_row, last_row, first_col, last_col = ws._filter
        used = ws.used_range() or (0, 0, 0, 0)
        if first_row is None:
            first_row = ws._header_row if ws._header_row is not None else used[0]
        if last_row is None:
            last_row = max(first_row, used[2])
        if first_col is None:
            first_col = 0
        if last_col is None:
            last_col = (ws._header_cols - 1) if ws._header_cols else used[3]
        return first_row, first_col, max(first_row, last_row), max(first_col, last_col)

    # --- drawings --------------------------------------------------------------------

    def media_name(self, entry):
        digest = hashlib.md5(entry['data']).hexdigest()
        name = self.media_index.get(digest)
        if name is None:
            ext = _IMAGE_TYPES[entry['kind']][0]
            name = 'image%d.%s' % (len(self.media) + 1, ext)
            self.media.append((name, entry['data'], entry['kind']))
            self.media_index[digest] = name
        return name

    def drawing_xml(self, ws):
        rels = []
        widths = _final_widths(ws)
        parts = [_DECL, '<xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/'
                 'spreadsheetDrawing" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
                 'xmlns:r="%s">' % _NS_R]
        for index, entry in enumerate(ws._images):
            rid = 'rId%d' % (index + 1)
            rels.append((rid, '../media/' + self.media_name(entry)))
            cx = entry['w'] * EMU_PER_PX
            cy = entry['h'] * EMU_PER_PX
            start = ('<xdr:from><xdr:col>%d</xdr:col><xdr:colOff>%d</xdr:colOff>'
                     '<xdr:row>%d</xdr:row><xdr:rowOff>%d</xdr:rowOff></xdr:from>' % (
                         entry['col'], entry['dx'] * EMU_PER_PX, entry['row'], entry['dy'] * EMU_PER_PX))
            pic = ('<xdr:pic><xdr:nvPicPr><xdr:cNvPr id="%d" name="Picture %d" descr="%s"/>'
                   '<xdr:cNvPicPr><a:picLocks noChangeAspect="1"/></xdr:cNvPicPr></xdr:nvPicPr>'
                   '<xdr:blipFill><a:blip r:embed="%s"/><a:stretch><a:fillRect/></a:stretch></xdr:blipFill>'
                   '<xdr:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="%d" cy="%d"/></a:xfrm>'
                   '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></xdr:spPr></xdr:pic>'
                   '<xdr:clientData/>' % (index + 2, index + 1, _xml_attr(entry['descr']), rid, cx, cy))
            if entry['anchor'] == 'cell':
                col, col_off = _walk(entry['col'], entry['dx'] + entry['w'],
                                     lambda c: chars_to_px(widths.get(c, 8.43)))
                row, row_off = _walk(entry['row'], entry['dy'] + entry['h'],
                                     lambda r: ws._heights.get(r, 15.0) / 0.75)
                end = ('<xdr:to><xdr:col>%d</xdr:col><xdr:colOff>%d</xdr:colOff>'
                       '<xdr:row>%d</xdr:row><xdr:rowOff>%d</xdr:rowOff></xdr:to>' % (
                           col, int(round(col_off * EMU_PER_PX)), row, int(round(row_off * EMU_PER_PX))))
                parts.append('<xdr:twoCellAnchor editAs="twoCell">%s%s%s</xdr:twoCellAnchor>'
                             % (start, end, pic))
            else:
                parts.append('<xdr:oneCellAnchor>%s<xdr:ext cx="%d" cy="%d"/>%s</xdr:oneCellAnchor>'
                             % (start, cx, cy, pic))
        parts.append('</xdr:wsDr>')
        return ''.join(parts), rels

    # --- the package -----------------------------------------------------------------

    def build(self):
        wb = self.wb
        sheets = list(wb.sheets) or [Worksheet(wb, u'Sheet1')]
        files = []                   # [(arcname, bytes)] in write order
        styles = self.styles_xml()
        sheet_parts = []
        drawing_parts = []
        defined_names = []
        for position, ws in enumerate(sheets):
            link_rels = []
            xml = self.sheet_xml(ws, position, link_rels)
            rels = [(rid, _REL + 'hyperlink', target, True) for rid, target in link_rels]
            if ws._images:
                drawing_no = len(drawing_parts) + 1
                drawing, drawing_rels = self.drawing_xml(ws)
                drawing_parts.append((drawing_no, drawing, drawing_rels))
                rels.append(('rId%d' % (len(link_rels) + 1), _REL + 'drawing',
                             '../drawings/drawing%d.xml' % drawing_no, False))
            sheet_parts.append((position + 1, xml, rels))
            if ws._has_filter:
                r1, c1, r2, c2 = self.filter_range(ws)
                defined_names.append(
                    '<definedName name="_xlnm._FilterDatabase" localSheetId="%d" hidden="1">'
                    '%s!%s</definedName>' % (position, _xml_text(quote_sheet(ws.name)),
                                             range_ref(r1, c1, r2, c2, absolute=True)))

        # [Content_Types].xml
        ct = [_DECL, '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
              '<Default Extension="rels" ContentType="%s"/>' % _CT['rels'],
              '<Default Extension="xml" ContentType="application/xml"/>']
        for ext in sorted(set(_IMAGE_TYPES[kind][0] for _n, _d, kind in self.media)):
            mime = [m for e, m in _IMAGE_TYPES.values() if e == ext][0]
            ct.append('<Default Extension="%s" ContentType="%s"/>' % (ext, mime))
        ct.append('<Override PartName="/xl/workbook.xml" ContentType="%s"/>' % _CT['workbook'])
        for number, _xml, _rels in sheet_parts:
            ct.append('<Override PartName="/xl/worksheets/sheet%d.xml" ContentType="%s"/>'
                      % (number, _CT['worksheet']))
        for number, _xml, _rels in drawing_parts:
            ct.append('<Override PartName="/xl/drawings/drawing%d.xml" ContentType="%s"/>'
                      % (number, _CT['drawing']))
        ct.append('<Override PartName="/xl/styles.xml" ContentType="%s"/>' % _CT['styles'])
        ct.append('<Override PartName="/xl/sharedStrings.xml" ContentType="%s"/>' % _CT['sst'])
        ct.append('<Override PartName="/docProps/core.xml" ContentType="%s"/>' % _CT['core'])
        ct.append('<Override PartName="/docProps/app.xml" ContentType="%s"/>' % _CT['app'])
        ct.append('</Types>')
        files.append(('[Content_Types].xml', ''.join(ct)))

        files.append(('_rels/.rels', _rels_xml([
            ('rId1', _REL + 'officeDocument', 'xl/workbook.xml', False),
            ('rId2', _REL_CORE, 'docProps/core.xml', False),
            ('rId3', _REL + 'extended-properties', 'docProps/app.xml', False)])))
        files.append(('docProps/core.xml', self.core_xml()))
        files.append(('docProps/app.xml', self.app_xml(sheets)))

        # workbook
        wbx = [_DECL, '<workbook xmlns="%s" xmlns:r="%s">' % (_NS_MAIN, _NS_R),
               '<workbookPr/>',
               '<bookViews><workbookView xWindow="0" yWindow="0" windowWidth="28800" '
               'windowHeight="15000" activeTab="0"/></bookViews>', '<sheets>']
        for position, ws in enumerate(sheets):
            wbx.append('<sheet name="%s" sheetId="%d" r:id="rId%d"/>'
                       % (_xml_attr(ws.name), position + 1, position + 1))
        wbx.append('</sheets>')
        if defined_names:
            wbx.append('<definedNames>%s</definedNames>' % ''.join(defined_names))
        if self.has_formula:
            wbx.append('<calcPr calcId="191029" fullCalcOnLoad="1"/>')
        else:
            wbx.append('<calcPr calcId="191029"/>')
        wbx.append('</workbook>')
        files.append(('xl/workbook.xml', ''.join(wbx)))

        wb_rels = [('rId%d' % n, _REL + 'worksheet', 'worksheets/sheet%d.xml' % n, False)
                   for n, _x, _r in sheet_parts]
        wb_rels.append(('rId%d' % (len(sheet_parts) + 1), _REL + 'styles', 'styles.xml', False))
        wb_rels.append(('rId%d' % (len(sheet_parts) + 2), _REL + 'sharedStrings',
                        'sharedStrings.xml', False))
        files.append(('xl/_rels/workbook.xml.rels', _rels_xml(wb_rels)))
        files.append(('xl/styles.xml', styles))

        sst = [_DECL, '<sst xmlns="%s" count="%d" uniqueCount="%d">'
               % (_NS_MAIN, self.string_refs, len(self.strings))]
        for text in self.strings:
            sst.append('<si><t xml:space="preserve">%s</t></si>' % text)
        sst.append('</sst>')
        files.append(('xl/sharedStrings.xml', ''.join(sst)))

        for number, xml, rels in sheet_parts:
            files.append(('xl/worksheets/sheet%d.xml' % number, xml))
            if rels:
                files.append(('xl/worksheets/_rels/sheet%d.xml.rels' % number, _rels_xml(rels)))
        for number, xml, rels in drawing_parts:
            files.append(('xl/drawings/drawing%d.xml' % number, xml))
            files.append(('xl/drawings/_rels/drawing%d.xml.rels' % number,
                          _rels_xml([(rid, _REL + 'image', target, False) for rid, target in rels])))
        for name, data, _kind in self.media:
            files.append(('xl/media/' + name, data))

        stamp = wb.created
        if stamp.year < 1980:
            stamp = datetime.datetime(1980, 1, 1)
        date_time = (stamp.year, stamp.month, stamp.day, stamp.hour, stamp.minute, stamp.second)
        buffer = io.BytesIO()
        archive = zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED)
        try:
            for arcname, content in files:
                info = zipfile.ZipInfo(arcname, date_time)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o600 << 16
                if not isinstance(content, bytes):
                    content = content.encode('utf-8', 'replace')
                archive.writestr(info, content)
        finally:
            archive.close()
        return buffer.getvalue()

    def core_xml(self):
        wb = self.wb
        stamp = wb.created.strftime('%Y-%m-%dT%H:%M:%SZ')
        parts = [_DECL, '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/'
                 'metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" '
                 'xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" '
                 'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">']
        if wb.title:
            parts.append('<dc:title>%s</dc:title>' % _xml_text(u'%s' % wb.title))
        if wb.author:
            parts.append('<dc:creator>%s</dc:creator>' % _xml_text(u'%s' % wb.author))
            parts.append('<cp:lastModifiedBy>%s</cp:lastModifiedBy>' % _xml_text(u'%s' % wb.author))
        parts.append('<dcterms:created xsi:type="dcterms:W3CDTF">%s</dcterms:created>' % stamp)
        parts.append('<dcterms:modified xsi:type="dcterms:W3CDTF">%s</dcterms:modified>' % stamp)
        parts.append('</cp:coreProperties>')
        return ''.join(parts)

    def app_xml(self, sheets):
        return (_DECL + '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/'
                'extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/'
                'docPropsVTypes"><Application>Playground</Application><DocSecurity>0</DocSecurity>'
                '<ScaleCrop>false</ScaleCrop></Properties>')


def _rels_xml(rels):
    parts = [_DECL, '<Relationships xmlns="%s">' % _NS_PKG]
    for rid, rtype, target, external in rels:
        parts.append('<Relationship Id="%s" Type="%s" Target="%s"%s/>'
                     % (rid, rtype, _xml_attr(target), ' TargetMode="External"' if external else ''))
    parts.append('</Relationships>')
    return ''.join(parts)


def _escape_path(text):
    return text.replace(u'%', u'%25').replace(u' ', u'%20').replace(u'#', u'%23')


def _link_target(target):
    """Link target -> (relationship target, None) or (None, in-workbook location)."""
    text = target.strip()
    if text.startswith(u'#'):
        return None, text[1:]
    if _DRIVE.match(text):
        return u'file:///' + _escape_path(text.replace(u'\\', u'/')), None
    if text.startswith(u'\\\\') or text.startswith(u'//'):
        return u'file:' + _escape_path(text.replace(u'\\', u'/')), None
    if _SCHEME.match(text):
        return text.replace(u' ', u'%20'), None
    return _escape_path(text.replace(u'\\', u'/')), None


# ---------------------------------------------------------------------------
# One-call writer
# ---------------------------------------------------------------------------

def write_simple(path, sheets, title=None, author=None):
    """Write a workbook from plain data; returns path.

    sheets: [{'name': 'Clashes', 'headers': [...], 'rows': [[...], ...],
              'widths': [chars or None, ...] (optional, default auto),
              'styles': [column style or None, ...] (optional),
              'title': 'Optional merged title row' (optional),
              'filter': True (optional, default True)}, ...]
    Each sheet gets a header row, frozen panes below it and (by default) an autofilter.
    """
    wb = Workbook(title=title, author=author)
    for spec in sheets:
        ws = wb.sheet(spec.get('name') or 'Sheet')
        headers = list(spec.get('headers') or [])
        widths = list(spec.get('widths') or [])
        styles = list(spec.get('styles') or [])
        if spec.get('title'):
            ws.title(spec['title'], span=max(1, len(headers)))
        if headers:
            ws.columns([(h, widths[i] if i < len(widths) else None,
                         styles[i] if i < len(styles) else None) for i, h in enumerate(headers)])
        for values in spec.get('rows') or []:
            ws.row(values)
        if headers and spec.get('filter', True):
            ws.autofilter()
        if not headers:
            ws.autofit()
    return wb.save(path)
