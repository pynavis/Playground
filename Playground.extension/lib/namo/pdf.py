# -*- coding: utf-8 -*-
"""Minimal PDF writer: pages, Helvetica text with real metrics (alignment, wrapping,
fitting), JPEG/PNG images, lines, rectangles and link areas. Pure Python; no Navisworks,
no .NET, same behaviour on CPython and IronPython.

    doc = pdf.Document(size='A4', landscape=True, margin_mm=12, title='Clash report', author='Amol')
    page = doc.page()
    page.text(page.left, page.top, 'Clash report', size=18, bold=True)
    y = page.wrap(page.left, page.top + 10, page.content_width, long_text, size=10)
    page.image(jpeg_path, page.left, y + 4, 120)          # height from the aspect ratio
    page.line(page.left, y + 2, page.right, y + 2, width_mm=0.2, color=(224, 224, 224))
    doc.page_numbers()                                     # 'Page 1 of 3' on every page
    doc.save(path)

Coordinates are millimetres from the TOP-LEFT corner of the page. For text, y is where
the top of the capital letters sits (the baseline is 0.718 x the font size lower), so
text(x, y) and image(x, y) line up and wrap() returns the y where the next line would
start. Colours are (r, g, b) as 0..255 ints, 0..1 floats, or 'RRGGBB' hex.

Fonts: Helvetica and Helvetica-Bold (built into every PDF viewer), WinAnsi encoding.
Characters outside Windows-1252 print as '?'. Widths come from the Adobe AFM metrics
embedded below, so measured widths match what viewers draw (no kerning is applied).

Images: JPEG is embedded as-is (DCTDecode). Non-interlaced 1/2/4/8-bit grey, RGB and
palette PNGs without transparency are embedded as-is too (their IDAT data with a PNG
predictor), which is fast. Other PNGs (alpha, tRNS, 16-bit, interlaced) are decoded with
namo.png (slow in IronPython for big images, see namo.png) and re-compressed, alpha
becoming a soft mask. The same image bytes used on several pages are stored once.
"""
import binascii
import datetime
import hashlib
import os
import zlib

from namo import png as _png

MM = 72.0 / 25.4            # PDF points per millimetre
ASCENT = 0.718              # Helvetica cap height / ascender, as a fraction of the font size
DESCENT = 0.207             # Helvetica descender, as a fraction of the font size

# Portrait sizes in millimetres (Document(landscape=True) swaps them).
SIZES = {
    'A5': (148.0, 210.0), 'A4': (210.0, 297.0), 'A3': (297.0, 420.0), 'A2': (420.0, 594.0),
    'A1': (594.0, 841.0), 'A0': (841.0, 1189.0), 'Letter': (215.9, 279.4),
    'Legal': (215.9, 355.6), 'Tabloid': (279.4, 431.8),
}

# Adobe AFM advance widths (1/1000 em) for WinAnsi codes 0x20..0xFF; 0 = unused code.
_HELVETICA = (
    278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278,  # 0x20
    556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556,  # 0x30
    1015, 667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778,  # 0x40
    667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469, 556,  # 0x50
    333, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556,  # 0x60
    556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584, 0,  # 0x70
    556, 0, 222, 556, 333, 1000, 556, 556, 333, 1000, 667, 333, 1000, 0, 611, 0,  # 0x80
    0, 222, 222, 333, 333, 350, 556, 1000, 333, 1000, 500, 333, 944, 0, 500, 667,  # 0x90
    278, 333, 556, 556, 556, 556, 260, 556, 333, 737, 370, 556, 584, 333, 737, 333,  # 0xA0
    400, 584, 333, 333, 333, 556, 537, 278, 333, 333, 365, 556, 834, 834, 834, 611,  # 0xB0
    667, 667, 667, 667, 667, 667, 1000, 722, 667, 667, 667, 667, 278, 278, 278, 278,  # 0xC0
    722, 722, 778, 778, 778, 778, 778, 584, 778, 722, 722, 722, 722, 667, 667, 611,  # 0xD0
    556, 556, 556, 556, 556, 556, 889, 500, 556, 556, 556, 556, 278, 278, 278, 278,  # 0xE0
    556, 556, 556, 556, 556, 556, 556, 584, 611, 556, 556, 556, 556, 500, 556, 500,  # 0xF0
)
_HELVETICA_BOLD = (
    278, 333, 474, 556, 556, 889, 722, 238, 333, 333, 389, 584, 278, 333, 278, 278,  # 0x20
    556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 333, 333, 584, 584, 584, 611,  # 0x30
    975, 722, 722, 722, 722, 667, 611, 778, 722, 278, 556, 722, 611, 833, 722, 778,  # 0x40
    667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 333, 278, 333, 584, 556,  # 0x50
    333, 556, 611, 556, 611, 556, 333, 611, 611, 278, 278, 556, 278, 889, 611, 611,  # 0x60
    611, 611, 389, 556, 333, 611, 556, 778, 556, 556, 500, 389, 280, 389, 584, 0,  # 0x70
    556, 0, 278, 556, 500, 1000, 556, 556, 333, 1000, 667, 333, 1000, 0, 611, 0,  # 0x80
    0, 278, 278, 500, 500, 350, 556, 1000, 333, 1000, 556, 333, 944, 0, 500, 667,  # 0x90
    278, 333, 556, 556, 556, 556, 280, 556, 333, 737, 370, 556, 584, 333, 737, 333,  # 0xA0
    400, 584, 333, 333, 333, 611, 556, 278, 333, 333, 365, 556, 834, 834, 834, 611,  # 0xB0
    722, 722, 722, 722, 722, 722, 1000, 722, 667, 667, 667, 667, 278, 278, 278, 278,  # 0xC0
    722, 722, 778, 778, 778, 778, 778, 584, 778, 722, 722, 722, 722, 667, 667, 611,  # 0xD0
    556, 556, 556, 556, 556, 556, 889, 556, 556, 556, 556, 556, 278, 278, 278, 278,  # 0xE0
    611, 611, 611, 611, 611, 611, 611, 584, 611, 611, 611, 611, 611, 556, 611, 556,  # 0xF0
)

# Unicode code point -> Windows-1252 byte for the 0x80..0x9F block (the rest of
# 0x20..0xFF maps to itself). Built from integers so no dash characters sit in source.
_WIN_HIGH = dict([
    (0x20AC, 0x80), (0x201A, 0x82), (0x0192, 0x83), (0x201E, 0x84), (0x2026, 0x85),
    (0x2020, 0x86), (0x2021, 0x87), (0x02C6, 0x88), (0x2030, 0x89), (0x0160, 0x8A),
    (0x2039, 0x8B), (0x0152, 0x8C), (0x017D, 0x8E), (0x2018, 0x91), (0x2019, 0x92),
    (0x201C, 0x93), (0x201D, 0x94), (0x2022, 0x95), (0x2013, 0x96), (0x2014, 0x97),
    (0x02DC, 0x98), (0x2122, 0x99), (0x0161, 0x9A), (0x203A, 0x9B), (0x0153, 0x9C),
    (0x017E, 0x9E), (0x0178, 0x9F),
])
_QUESTION = 0x3F
_ELLIPSIS = u'…'


# ---------------------------------------------------------------------------
# Text encoding and metrics
# ---------------------------------------------------------------------------

def _codes(text):
    """Text -> list of WinAnsi codes; anything outside Windows-1252 becomes '?'."""
    out = []
    for ch in u'%s' % (text,):
        c = ord(ch)
        if 0xD800 <= c <= 0xDBFF:
            continue                       # IronPython: first half of a surrogate pair
        if c == 9:
            out.append(32)
        elif 32 <= c < 127 or 0xA0 <= c <= 0xFF:
            out.append(c)
        elif c in _WIN_HIGH:
            out.append(_WIN_HIGH[c])
        else:
            out.append(_QUESTION)
    return out


def _code_width(code, bold):
    table = _HELVETICA_BOLD if bold else _HELVETICA
    width = table[code - 32] if 32 <= code <= 255 else 0
    return width or 556


def text_width(text, size=11, bold=False):
    """Width in mm of a single line of text in Helvetica (bold) at `size` points."""
    units = 0
    for code in _codes(text):
        units += _code_width(code, bold)
    return units * size / 1000.0 / MM


def line_height(size=10, leading=1.3):
    """Distance in mm between baselines for `size` point text at `leading`."""
    return size * leading / MM


def fit_text(text, width_mm, size=11, bold=False):
    """The text, cut and ended with an ellipsis when it is wider than width_mm."""
    text = _one_line(text)
    if text_width(text, size, bold) <= width_mm + 1e-9:
        return text
    budget = width_mm * MM * 1000.0 / size - _code_width(0x85, bold)
    used = 0
    keep = 0
    chars = list(text)
    for index, ch in enumerate(chars):
        w = sum(_code_width(c, bold) for c in _codes(ch))
        if used + w > budget:
            break
        used += w
        keep = index + 1
    return u''.join(chars[:keep]).rstrip() + _ELLIPSIS


def wrap_lines(text, width_mm, size=10, bold=False):
    """Split text into lines that fit width_mm: breaks at spaces, keeps the caller's
    newlines, and splits words longer than a line by characters."""
    lines = []
    paragraphs = (u'%s' % (text,)).replace(u'\r\n', u'\n').replace(u'\r', u'\n').split(u'\n')
    for paragraph in paragraphs:
        words = paragraph.replace(u'\t', u' ').split(u' ')
        current = u''
        for word in words:
            if word == u'':
                continue
            candidate = word if not current else current + u' ' + word
            if text_width(candidate, size, bold) <= width_mm + 1e-9:
                current = candidate
                continue
            if current:
                lines.append(current)
                current = u''
            while text_width(word, size, bold) > width_mm + 1e-9 and len(word) > 1:
                cut = 1
                while cut < len(word) and text_width(word[:cut + 1], size, bold) <= width_mm + 1e-9:
                    cut += 1
                lines.append(word[:cut])
                word = word[cut:]
            current = word
        lines.append(current)
    return lines


def _one_line(text):
    return (u'%s' % (text,)).replace(u'\r\n', u' ').replace(u'\r', u' ').replace(u'\n', u' ')


def _literal(text):
    """PDF literal string (ASCII only: specials and high bytes escaped)."""
    out = []
    for code in _codes(text):
        if code in (0x28, 0x29, 0x5C):
            out.append(u'\\' + chr(code))
        elif 32 <= code < 127:
            out.append(chr(code))
        else:
            out.append(u'\\%03o' % code)
    return u'(' + u''.join(out) + u')'


def _info_string(text):
    """Document info text: a literal for plain ASCII, else UTF-16BE hex with a BOM."""
    text = u'%s' % (text,)
    if all(32 <= ord(ch) < 127 for ch in text):
        return u'(' + text.replace(u'\\', u'\\\\').replace(u'(', u'\\(').replace(u')', u'\\)') + u')'
    units = [u'FEFF']
    for ch in text:
        c = ord(ch)
        if c > 0xFFFF:
            c -= 0x10000
            units.append(u'%04X%04X' % (0xD800 + (c >> 10), 0xDC00 + (c & 0x3FF)))
        else:
            units.append(u'%04X' % c)
    return u'<' + u''.join(units) + u'>'


def _uri(url):
    """Link target -> 7-bit URI (Windows paths become file:/// URLs)."""
    text = (u'%s' % (url,)).strip()
    if len(text) > 2 and text[1] == u':' and text[2] in u'\\/':
        text = u'file:///' + text.replace(u'\\', u'/')
    elif text.startswith(u'\\\\'):
        text = u'file:' + text.replace(u'\\', u'/')
    out = []
    for ch in text:
        if ch == u' ':
            out.append(u'%20')
        elif 32 < ord(ch) < 127:
            out.append(ch)
        else:
            for byte in bytearray(ch.encode('utf-8', 'replace')):
                out.append(u'%%%02X' % byte)
    return u''.join(out)


def _n(value):
    """Number for a content stream: up to 3 decimals, no trailing zeros."""
    text = u'%.3f' % value
    text = text.rstrip(u'0').rstrip(u'.')
    return u'0' if text in (u'-0', u'') else text


def _rgb(color):
    """Colour -> (r, g, b) floats 0..1, or None."""
    if color is None:
        return None
    if isinstance(color, str):
        text = color.strip().lstrip(u'#')
        if len(text) != 6:
            raise ValueError("colours are (r, g, b) or 'RRGGBB', got %r" % (color,))
        return tuple(int(text[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    values = tuple(color)
    if len(values) != 3:
        raise ValueError('colours need three components, got %r' % (color,))
    if any(isinstance(v, float) for v in values) and all(0.0 <= v <= 1.0 for v in values):
        return tuple(float(v) for v in values)
    return tuple(max(0.0, min(1.0, v / 255.0)) for v in values)


def _color_op(color, stroke):
    r, g, b = color
    return u'%s %s %s %s' % (_n(r), _n(g), _n(b), u'RG' if stroke else u'rg')


def page_size(size='A4', landscape=True):
    """(width_mm, height_mm) for a name in SIZES (case-insensitive) or a (w, h) tuple.
    Named sizes are oriented by `landscape`; tuples are used exactly as given."""
    if isinstance(size, (tuple, list)):
        return float(size[0]), float(size[1])
    for name, dims in SIZES.items():
        if name.lower() == (u'%s' % size).lower():
            short, long_ = min(dims), max(dims)
            return (long_, short) if landscape else (short, long_)
    raise ValueError('unknown page size %r (use %s or (w, h) in mm)' % (size, ', '.join(sorted(SIZES))))


# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------

class _Image(object):
    def __init__(self, name, width, height, header, data, smask=None):
        self.name = name
        self.width = width
        self.height = height
        self.header = header        # dictionary entries without /Length
        self.data = data
        self.smask = smask


def _split_channels(pixels, channels):
    """Interleaved 8-bit samples -> (colour bytes, alpha bytes or None)."""
    if channels in (1, 3):
        return bytes(pixels), None
    colour_ch = channels - 1
    count = len(pixels) // channels
    colour = bytearray(count * colour_ch)
    for c in range(colour_ch):
        colour[c::colour_ch] = pixels[c::channels]
    alpha = bytes(pixels[colour_ch::channels])
    if alpha.count(b'\xff') == len(alpha):
        alpha = None
    return bytes(colour), alpha


def _build_image(data, name):
    kind = _png.sniff(data)
    if kind == 'jpeg':
        head = _png.jpeg_info(data)
        spaces = {1: u'/DeviceGray', 3: u'/DeviceRGB', 4: u'/DeviceCMYK'}
        if head['components'] not in spaces or head['bits'] != 8:
            raise ValueError('JPEG with %d components at %d bits cannot go in a PDF'
                             % (head['components'], head['bits']))
        header = (u'/Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace %s '
                  u'/BitsPerComponent 8 /Filter /DCTDecode' % (head['width'], head['height'],
                                                                spaces[head['components']]))
        if head['components'] == 4 and head['adobe']:
            header += u' /Decode [1 0 1 0 1 0 1 0]'
        return _Image(name, head['width'], head['height'], header, data)
    if kind != 'png':
        raise ValueError('PDF pages can embed PNG or JPEG images, not %s' % (kind or 'this file'))
    head = _png.info(data)
    width, height = head['width'], head['height']
    ctype, depth = head['color_type'], head['bit_depth']
    plain = head['interlace'] == 0 and not head['transparency'] and depth <= 8
    if plain and ctype in (0, 2, 3):
        colors = 3 if ctype == 2 else 1
        parms = (u'/DecodeParms << /Predictor 15 /Colors %d /BitsPerComponent %d /Columns %d >>'
                 % (colors, depth, width))
        if ctype == 3:
            plte, _trns = _png.palette_of(data)
            if not plte:
                raise ValueError('palette PNG has no palette')
            hexes = binascii.hexlify(plte).decode('ascii').upper()
            space = u'[/Indexed /DeviceRGB %d <%s>]' % (len(plte) // 3 - 1, hexes)
        else:
            space = u'/DeviceGray' if ctype == 0 else u'/DeviceRGB'
        header = (u'/Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace %s '
                  u'/BitsPerComponent %d /Filter /FlateDecode %s' % (width, height, space, depth, parms))
        return _Image(name, width, height, header, _png.idat_stream(data))
    width, height, mode, pixels = _png.decode(data)
    colour, alpha = _split_channels(pixels, len(mode))
    space = u'/DeviceGray' if mode in ('L', 'LA') else u'/DeviceRGB'
    smask = None
    if alpha is not None:
        smask = _Image(name + u'a', width, height,
                       u'/Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace /DeviceGray '
                       u'/BitsPerComponent 8 /Filter /FlateDecode' % (width, height),
                       zlib.compress(alpha, 6))
    header = (u'/Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace %s '
              u'/BitsPerComponent 8 /Filter /FlateDecode' % (width, height, space))
    return _Image(name, width, height, header, zlib.compress(colour, 6), smask)


def _read(path_or_bytes):
    if isinstance(path_or_bytes, (bytes, bytearray)):
        return bytes(path_or_bytes)
    handle = open(path_or_bytes, 'rb')
    try:
        return handle.read()
    finally:
        handle.close()


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

class Page(object):
    """One page. Draw with text/wrap/image/line/rect/link; coordinates in mm from the
    top-left corner. left/top/right/bottom are the margin box edges."""

    def __init__(self, doc, width_mm, height_mm, margin_mm):
        self.doc = doc
        self.width = width_mm
        self.height = height_mm
        self.margin = margin_mm
        self._ops = []
        self._images = []           # _Image objects drawn on this page (in first-use order)
        self._links = []            # (x0, y0, x1, y1 in points, uri)

    # --- geometry --------------------------------------------------------------------

    @property
    def left(self):
        return self.margin

    @property
    def top(self):
        return self.margin

    @property
    def right(self):
        return self.width - self.margin

    @property
    def bottom(self):
        return self.height - self.margin

    @property
    def content_width(self):
        return self.width - 2 * self.margin

    @property
    def content_height(self):
        return self.height - 2 * self.margin

    def _px(self, x_mm):
        return x_mm * MM

    def _py(self, y_mm):
        return (self.height - y_mm) * MM

    # --- text ------------------------------------------------------------------------

    def text(self, x_mm, y_mm, text, size=11, bold=False, color=(0, 0, 0), align='left',
             max_width=None):
        """One line of text with the top of its capitals at y_mm. align: 'left' (x is
        the start), 'center' or 'right' (x is the end). max_width cuts long text with an
        ellipsis. Newlines become spaces. Returns the drawn width in mm."""
        text = _one_line(text)
        if max_width is not None:
            text = fit_text(text, max_width, size, bold)
        width = text_width(text, size, bold)
        if align == 'center':
            x_mm = x_mm - width / 2.0
        elif align == 'right':
            x_mm = x_mm - width
        elif align != 'left':
            raise ValueError("align is 'left', 'center' or 'right', not %r" % (align,))
        if not text:
            return 0.0
        baseline = y_mm + size * ASCENT / MM
        rgb = _rgb(color) or (0.0, 0.0, 0.0)
        self._ops.append(u'BT /%s %s Tf %s %s 0 0 1 %s %s Tm %s Tj ET' % (
            u'F2' if bold else u'F1', _n(size), _color_op(rgb, False), u'1', _n(self._px(x_mm)),
            _n(self._py(baseline)), _literal(text)))
        return width

    def wrap(self, x_mm, y_mm, w_mm, text, size=10, leading=1.3, bold=False, color=(0, 0, 0),
             align='left', max_lines=None):
        """Draw text wrapped to w_mm starting at y_mm (top of the first line's capitals).
        Returns the y where the next line would start (y + lines * line_height). With
        max_lines, the last kept line ends in an ellipsis when text was cut. Empty or
        blank text draws nothing and returns y_mm."""
        if text is None or not (u'%s' % (text,)).strip():
            return y_mm
        lines = wrap_lines(text, w_mm, size, bold)
        if max_lines is not None and len(lines) > max_lines:
            lines = lines[:max(0, int(max_lines))]
            if lines:
                lines[-1] = fit_text(lines[-1].rstrip() + _ELLIPSIS, w_mm, size, bold)
        pitch = line_height(size, leading)
        anchor = {'left': x_mm, 'center': x_mm + w_mm / 2.0, 'right': x_mm + w_mm}.get(align)
        if anchor is None:
            raise ValueError("align is 'left', 'center' or 'right', not %r" % (align,))
        for index, line in enumerate(lines):
            self.text(anchor, y_mm + index * pitch, line, size, bold, color, align)
        return y_mm + len(lines) * pitch

    # --- shapes ----------------------------------------------------------------------

    def line(self, x1, y1, x2, y2, width_mm=0.2, color=(0, 0, 0), dash=None):
        """A straight line. dash: (on_mm, off_mm) for a dashed line."""
        rgb = _rgb(color) or (0.0, 0.0, 0.0)
        dash_op = u''
        if dash:
            dash_op = u'[%s %s] 0 d ' % (_n(dash[0] * MM), _n(dash[1] * MM))
        self._ops.append(u'q %s %s w %s%s %s m %s %s l S Q' % (
            _color_op(rgb, True), _n(width_mm * MM), dash_op, _n(self._px(x1)), _n(self._py(y1)),
            _n(self._px(x2)), _n(self._py(y2))))

    def rect(self, x, y, w, h, stroke=(0, 0, 0), fill=None, width_mm=0.2):
        """A rectangle with its top-left corner at (x, y). stroke/fill: colour or None."""
        stroke_rgb = _rgb(stroke)
        fill_rgb = _rgb(fill)
        if stroke_rgb is None and fill_rgb is None:
            return
        ops = [u'q']
        if fill_rgb is not None:
            ops.append(_color_op(fill_rgb, False))
        if stroke_rgb is not None:
            ops.append(_color_op(stroke_rgb, True))
            ops.append(u'%s w' % _n(width_mm * MM))
        ops.append(u'%s %s %s %s re' % (_n(self._px(x)), _n(self._py(y + h)), _n(w * MM), _n(h * MM)))
        ops.append(u'B' if (fill_rgb is not None and stroke_rgb is not None) else
                   (u'f' if fill_rgb is not None else u'S'))
        ops.append(u'Q')
        self._ops.append(u' '.join(ops))

    # --- images and links ----------------------------------------------------------------

    def image(self, path_or_bytes, x_mm, y_mm, w_mm=None, h_mm=None, fit=False):
        """Place a JPEG or PNG with its top-left corner at (x, y). Give w_mm (and/or h_mm);
        a missing side follows the aspect ratio. fit=True keeps the aspect ratio inside
        the w x h box and centres it. Returns the drawn (x, y, w, h) in mm."""
        img = self.doc._image(_read(path_or_bytes))
        aspect = img.height / float(img.width)
        if w_mm is None and h_mm is None:
            raise ValueError('give the image a width or a height in mm')
        if w_mm is None:
            w_mm = h_mm / aspect
        elif h_mm is None:
            h_mm = w_mm * aspect
        elif fit:
            scale = min(w_mm / float(img.width), h_mm / float(img.height))
            dw, dh = img.width * scale, img.height * scale
            x_mm += (w_mm - dw) / 2.0
            y_mm += (h_mm - dh) / 2.0
            w_mm, h_mm = dw, dh
        if img not in self._images:
            self._images.append(img)
        self._ops.append(u'q %s 0 0 %s %s %s cm /%s Do Q' % (
            _n(w_mm * MM), _n(h_mm * MM), _n(self._px(x_mm)), _n(self._py(y_mm + h_mm)), img.name))
        return x_mm, y_mm, w_mm, h_mm

    def link(self, x, y, w, h, url):
        """Make an area clickable: opens url (http(s), mailto, or a file path)."""
        self._links.append((self._px(x), self._py(y + h), self._px(x + w), self._py(y), _uri(url)))


# ---------------------------------------------------------------------------
# Document
# ---------------------------------------------------------------------------

class Document(object):
    """A PDF document: add pages with page(), then save(path)."""

    def __init__(self, size='A4', landscape=True, margin_mm=12, title=None, author=None,
                 subject=None, created=None, compress=True):
        """size: a SIZES name or (w, h) mm; created: datetime for the document info
        (default now); compress=False writes readable content streams (debugging)."""
        self.size = size
        self.landscape = landscape
        self.width, self.height = page_size(size, landscape)
        self.margin = float(margin_mm)
        self.title = title
        self.author = author
        self.subject = subject
        self.created = created or datetime.datetime.now().replace(microsecond=0)
        self.compress = compress
        self.pages = []
        self._images = {}
        self._numbering = None

    def page(self, size=None, landscape=None):
        """Append a new page (optionally with its own size/orientation) and return it."""
        if size is None and landscape is None:
            width, height = self.width, self.height
        else:
            width, height = page_size(self.size if size is None else size,
                                      self.landscape if landscape is None else landscape)
        page = Page(self, width, height, self.margin)
        self.pages.append(page)
        return page

    def page_numbers(self, template=u'Page {page} of {pages}', size=8, color=(107, 107, 107),
                     align='right', y_mm=None):
        """Print a page number on every page at save time ('{page}', '{pages}' tokens).
        y_mm defaults to half the bottom margin; align 'right' sits at the right margin."""
        self._numbering = (template, size, color, align, y_mm)

    def _image(self, data):
        key = hashlib.md5(data).hexdigest()
        img = self._images.get(key)
        if img is None:
            img = _build_image(data, u'Im%d' % (len(self._images) + 1))
            self._images[key] = img
        return img

    # --- output ----------------------------------------------------------------------

    def to_bytes(self):
        """The whole PDF file as bytes."""
        pages = list(self.pages) or [Page(self, self.width, self.height, self.margin)]
        numbering_ops = {}
        if self._numbering:
            template, size, color, align, y_mm = self._numbering
            for index, page in enumerate(pages):
                saved = page._ops
                page._ops = []
                y = y_mm if y_mm is not None else page.height - page.margin / 2.0 - size * ASCENT / MM / 2.0
                x = {'right': page.right, 'center': page.width / 2.0}.get(align, page.left)
                page.text(x, y, template.format(page=index + 1, pages=len(pages)), size=size,
                          color=color, align=align)
                numbering_ops[index] = page._ops
                page._ops = saved

        # number every object up front: 1 catalog, 2 pages, 3/4 fonts, 5 info, then
        # images (soft mask first), then per page: content stream, link annotations, page
        images = []
        for page in pages:
            for img in page._images:
                if img not in images:
                    images.append(img)
        number = 5
        image_num = {}
        for img in images:
            if img.smask is not None:
                number += 1
                image_num[id(img.smask)] = number
            number += 1
            image_num[id(img)] = number
        page_nums = []
        for page in pages:
            content = number + 1
            annots = list(range(content + 1, content + 1 + len(page._links)))
            number = content + len(page._links) + 1
            page_nums.append((content, annots, number))

        bodies = {}
        bodies[1] = u'<< /Type /Catalog /Pages 2 0 R /ViewerPreferences << /DisplayDocTitle true >> >>'
        bodies[2] = u'<< /Type /Pages /Kids [%s] /Count %d >>' % (
            u' '.join(u'%d 0 R' % n for _c, _a, n in page_nums), len(pages))
        bodies[3] = u'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>'
        bodies[4] = u'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>'
        info = [u'/Producer (Playground)', u'/Creator (Playground)',
                u'/CreationDate (D:%s)' % self.created.strftime('%Y%m%d%H%M%S'),
                u'/ModDate (D:%s)' % self.created.strftime('%Y%m%d%H%M%S')]
        if self.title:
            info.append(u'/Title %s' % _info_string(self.title))
        if self.author:
            info.append(u'/Author %s' % _info_string(self.author))
        if self.subject:
            info.append(u'/Subject %s' % _info_string(self.subject))
        bodies[5] = u'<< %s >>' % u' '.join(info)
        for img in images:
            if img.smask is not None:
                bodies[image_num[id(img.smask)]] = (img.smask.header, img.smask.data)
                bodies[image_num[id(img)]] = (img.header + u' /SMask %d 0 R' % image_num[id(img.smask)], img.data)
            else:
                bodies[image_num[id(img)]] = (img.header, img.data)
        for index, (page, (content, annots, page_no)) in enumerate(zip(pages, page_nums)):
            ops = page._ops + numbering_ops.get(index, [])
            stream = u'\n'.join(ops).encode('latin-1')
            if self.compress:
                bodies[content] = (u'/Filter /FlateDecode', zlib.compress(stream, 6))
            else:
                bodies[content] = (u'', stream)
            for annot_no, (x0, y0, x1, y1, uri) in zip(annots, page._links):
                bodies[annot_no] = (u'<< /Type /Annot /Subtype /Link /Rect [%s %s %s %s] /Border [0 0 0] '
                                    u'/A << /Type /Action /S /URI /URI %s >> >>' % (
                                        _n(x0), _n(y0), _n(x1), _n(y1), _literal(uri)))
            xobjects = u''
            if page._images:
                xobjects = u' /XObject << %s >>' % u' '.join(
                    u'/%s %d 0 R' % (img.name, image_num[id(img)]) for img in page._images)
            annot_ref = u''
            if annots:
                annot_ref = u' /Annots [%s]' % u' '.join(u'%d 0 R' % n for n in annots)
            bodies[page_no] = (u'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %s %s] '
                               u'/Resources << /Font << /F1 3 0 R /F2 4 0 R >>%s '
                               u'/ProcSet [/PDF /Text /ImageB /ImageC /ImageI] >> /Contents %d 0 R%s >>' % (
                                   _n(page.width * MM), _n(page.height * MM), xobjects, content, annot_ref))

        chunks = [b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n']
        offsets = []
        position = len(chunks[0])
        digest = hashlib.md5()
        for num in range(1, number + 1):
            body = bodies[num]
            if isinstance(body, tuple):
                entries, data = body
                head = u'%d 0 obj\n<< %s /Length %d >>\nstream\n' % (num, entries.strip(), len(data))
                chunk = head.encode('latin-1') + data + b'\nendstream\nendobj\n'
            else:
                chunk = (u'%d 0 obj\n%s\nendobj\n' % (num, body)).encode('latin-1')
            offsets.append(position)
            chunks.append(chunk)
            digest.update(chunk)
            position += len(chunk)
        file_id = digest.hexdigest().upper()
        xref = [u'xref\n0 %d\n' % (number + 1), u'0000000000 65535 f\r\n']
        for offset in offsets:
            xref.append(u'%010d 00000 n\r\n' % offset)
        xref.append(u'trailer\n<< /Size %d /Root 1 0 R /Info 5 0 R /ID [<%s> <%s>] >>\n'
                    u'startxref\n%d\n%%%%EOF\n' % (number + 1, file_id, file_id, position))
        chunks.append(u''.join(xref).encode('latin-1'))
        return b''.join(chunks)

    def save(self, path):
        """Write the PDF atomically (temp file, then replace); returns path.
        Raises IOError/OSError when the file is open in a viewer that locks it."""
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
