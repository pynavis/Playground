# -*- coding: utf-8 -*-
"""Legend Maker: a colour scheme drawn as a print-ready PNG legend.

The layout is pure (layout() takes a measure(text, size, bold) -> (width,
height) function, so it is tested with a fake one on both engines); the
drawing is WPF: one DrawingVisual rendered by RenderTargetBitmap at 2x (192
dpi, crisp on paper and on high-DPI screens) and saved as PNG. The legend is
theme neutral on purpose: white paper, near-black text, hairlines, whatever
theme Navisworks is in, because it ends up in reports and on walls.

    title                       Construction status
    subtitle                    Playground > Status, visible items
    ---------------------------------------------------
    [swatch] value              count      share
    ...
    ---------------------------------------------------
             Total              count

A row whose colour is None ("left unchanged") gets a dashed empty swatch.

save_view() keeps the legend in the model too: a saved viewpoint from
Navisworks' own override snapshot (CaptureRuntimeOverrides, which also holds
the camera), so recalling it brings the colours back; when that refuses, an
ordinary camera viewpoint (namo.camera.save_view). The legend text is its
comment.
"""

import base64
import os

from namo import colorize, colors, naming

STYLE = {
    'pad': 24, 'title_size': 18.0, 'sub_size': 12.0, 'row_size': 13.0, 'row_h': 26,
    'swatch': 16, 'swatch_gap': 10, 'col_gap': 20, 'max_label': 360, 'min_width': 280,
    'head_gap': 14, 'max_rows': 60, 'radius': 3,
}
PAPER = 'FFFFFF'
INK = '1F2328'
MUTED = '61656C'
LINE = 'DADDE1'
ELLIPSIS = u'…'
SCALE = 2.0


# =============================================================================
# Pure half
# =============================================================================


def fit(text, max_width, measure, size, bold=False):
    """text, cut with an ellipsis so it measures no wider than max_width."""
    text = '' if text is None else str(text)
    if measure(text, size, bold)[0] <= max_width:
        return text
    low, high = 0, len(text)
    while low < high:
        middle = (low + high + 1) // 2
        if measure(text[:middle].rstrip() + ELLIPSIS, size, bold)[0] <= max_width:
            low = middle
        else:
            high = middle - 1
    return text[:low].rstrip() + ELLIPSIS


def rows_of(scheme, max_rows=None):
    """[(hex or None, label, count text, share text)] for the legend, plus the
    'and N more' line when max_rows cut it (or None)."""
    entries = list(scheme.get('entries') or [])
    total = scheme.get('total') or sum(int(e.get('count') or 0) for e in entries)
    rows = []
    for entry in entries:
        count = int(entry.get('count') or 0)
        rows.append((colors.parse_hex(entry.get('hex')), str(entry.get('value')),
                     colorize.count_text(count), colorize.share_text(count, total) if count else ''))
    more = None
    if max_rows and len(rows) > max_rows:
        hidden = len(rows) - max_rows + 1
        more = 'and %s more %s' % (colorize.count_text(hidden), 'value' if hidden == 1 else 'values')
        rows = rows[:max_rows - 1]
    return rows, more, total


def layout(scheme, measure, style=None):
    """Everything the renderer draws, in device-independent pixels:
    {'width', 'height', 'texts': [(x, y, text, size, bold, muted, align)],
    'swatches': [(x, y, size, hex or None)], 'lines': [(x0, y, x1)]}.
    measure(text, size, bold) -> (width, height). align 'left' or 'right'
    (x is the right edge then)."""
    s = dict(STYLE)
    s.update(style or {})
    pad = s['pad']
    rows, more, total = rows_of(scheme, s['max_rows'])
    title = str(scheme.get('title') or 'Legend')
    subtitle = str(scheme.get('subtitle') or '')
    size = s['row_size']
    labels = [fit(label, s['max_label'], measure, size) for _h, label, _c, _p in rows]
    label_w = max([measure(t, size, False)[0] for t in labels] + [measure('Total', size, True)[0], 40])
    count_w = max([measure(c, size, False)[0] for _h, _l, c, _p in rows] +
                  [measure(colorize.count_text(total), size, True)[0], 1])
    share_w = max([measure(p, size, False)[0] for _h, _l, _c, p in rows] + [0])
    table_w = s['swatch'] + s['swatch_gap'] + label_w + s['col_gap'] + count_w
    if share_w:
        table_w += s['col_gap'] + share_w
    title_text = fit(title, max(table_w, 480), measure, s['title_size'], True)
    sub_text = fit(subtitle, max(table_w, 480), measure, s['sub_size']) if subtitle else ''
    head_w = max(measure(title_text, s['title_size'], True)[0],
                 measure(sub_text, s['sub_size'], False)[0] if sub_text else 0)
    inner = max(table_w, head_w, s['min_width'] - 2 * pad)
    width = int(round(inner + 2 * pad))
    texts = []
    swatches = []
    lines = []
    y = pad
    title_h = measure(title_text, s['title_size'], True)[1]
    texts.append((pad, y, title_text, s['title_size'], True, False, 'left'))
    y += title_h
    if sub_text:
        texts.append((pad, y + 2, sub_text, s['sub_size'], False, True, 'left'))
        y += 2 + measure(sub_text, s['sub_size'], False)[1]
    y += s['head_gap']
    lines.append((pad, y, width - pad))
    y += 6
    label_x = pad + s['swatch'] + s['swatch_gap']
    count_right = label_x + label_w + s['col_gap'] + count_w
    share_right = count_right + s['col_gap'] + share_w
    row_h = s['row_h']
    text_h = measure('Ag', size, False)[1]
    for (hex_value, _label, count, share), label in zip(rows, labels):
        middle = y + row_h / 2.0
        swatches.append((pad, middle - s['swatch'] / 2.0, s['swatch'], hex_value))
        top = middle - text_h / 2.0
        texts.append((label_x, top, label, size, False, False, 'left'))
        texts.append((count_right, top, count, size, False, False, 'right'))
        if share_w and share:
            texts.append((share_right, top, share, size, False, True, 'right'))
        y += row_h
    if more:
        texts.append((label_x, y + (row_h - text_h) / 2.0, more, size, False, True, 'left'))
        y += row_h
    y += 4
    lines.append((pad, y, width - pad))
    y += 4
    top = y + (row_h - text_h) / 2.0
    texts.append((label_x, top, 'Total', size, True, False, 'left'))
    texts.append((count_right, top, colorize.count_text(total), size, True, False, 'right'))
    y += row_h
    height = int(round(y + pad - 6))
    return {'width': width, 'height': height, 'texts': texts, 'swatches': swatches,
            'lines': lines, 'radius': s['radius']}


def default_name(title, file_stem):
    """'Hospital - Legend - Status.png' (no document name: 'Legend - Status.png')."""
    base = ('%s - Legend - %s' % (file_stem, title)) if file_stem else 'Legend - %s' % title
    return naming.sanitize(base, for_file=True) + '.png'


def view_name(title):
    return naming.sanitize('Legend - %s' % (title or 'colors'))


def image_html(png_bytes, width, caption=None):
    """An <img> for the output window at its logical width (the PNG is 2x)."""
    data = base64.b64encode(png_bytes).decode('ascii')
    cap = ''
    if caption:
        cap = '<div style="color:var(--muted);margin-top:4px">%s</div>' % colorize.escape(caption)
    return ('<figure style="margin:8px 0"><img src="data:image/png;base64,%s" style="width:%dpx;'
            'max-width:100%%;border:1px solid var(--line)"/>%s</figure>' % (data, int(width), cap))


def form_fields(scheme, path, defaults):
    return [
        {'kind': 'text', 'key': 'title', 'label': 'Title', 'default': scheme.get('title') or 'Legend',
         'required': True},
        {'kind': 'file_save', 'key': 'path', 'label': 'Save as', 'default': path,
         'filter': 'PNG image (*.png)|*.png', 'default_name': os.path.basename(path),
         'required': True},
        {'kind': 'check', 'key': 'view', 'label': 'Also save a viewpoint with these colors',
         'default': bool(defaults.get('view', False))},
    ]


# =============================================================================
# WPF half
# =============================================================================


def _wpf():
    import clr
    for name in ('PresentationCore', 'PresentationFramework', 'WindowsBase'):
        clr.AddReference(name)


def _brush(hex_value):
    from System.Windows.Media import Color, SolidColorBrush
    r, g, b = colors.hex_to_rgb(hex_value)
    brush = SolidColorBrush(Color.FromRgb(r, g, b))
    brush.Freeze()
    return brush


class _Text(object):
    """FormattedText factory with one typeface pair and pixels-per-dip."""

    def __init__(self, scale):
        from System.Windows import FontStretches, FontStyles, FontWeights
        from System.Windows.Media import FontFamily, Typeface
        family = FontFamily('Segoe UI')
        self.regular = Typeface(family, FontStyles.Normal, FontWeights.Normal, FontStretches.Normal)
        self.bold = Typeface(family, FontStyles.Normal, FontWeights.SemiBold, FontStretches.Normal)
        self.scale = float(scale)
        self.ink = _brush(INK)
        self.muted = _brush(MUTED)

    def make(self, text, size, bold=False, muted=False):
        from System.Globalization import CultureInfo
        from System.Windows import FlowDirection
        from System.Windows.Media import FormattedText
        return FormattedText(str(text), CultureInfo.CurrentUICulture, FlowDirection.LeftToRight,
                             self.bold if bold else self.regular, float(size),
                             self.muted if muted else self.ink, self.scale)

    def measure(self, text, size, bold=False):
        formatted = self.make(text, size, bold)
        return (formatted.WidthIncludingTrailingWhitespace, formatted.Height)


def render(scheme, scale=SCALE):
    """(png bytes, width, height) of the legend; width/height in logical
    pixels (the bitmap is scale times larger)."""
    _wpf()
    from System.IO import MemoryStream
    from System.Windows import Point, Rect
    from System.Windows.Media import DashStyles, DrawingVisual, PixelFormats, Pen
    from System.Windows.Media.Imaging import BitmapFrame, PngBitmapEncoder, RenderTargetBitmap
    text = _Text(scale)
    plan = layout(scheme, text.measure)
    visual = DrawingVisual()
    context = visual.RenderOpen()
    try:
        context.DrawRectangle(_brush(PAPER), None, Rect(0, 0, plan['width'], plan['height']))
        hairline = Pen(_brush(LINE), 1.0)
        hairline.Freeze()
        for x0, y, x1 in plan['lines']:
            context.DrawLine(hairline, Point(x0, y + 0.5), Point(x1, y + 0.5))
        edge = Pen(_brush('8C9097'), 1.0)
        edge.Freeze()
        dashed = Pen(_brush(MUTED), 1.0)
        dashed.DashStyle = DashStyles.Dash
        dashed.Freeze()
        radius = plan['radius']
        for x, y, size, hex_value in plan['swatches']:
            box = Rect(x + 0.5, y + 0.5, size - 1, size - 1)
            if hex_value:
                context.DrawRoundedRectangle(_brush(hex_value), edge, box, radius, radius)
            else:
                context.DrawRoundedRectangle(None, dashed, box, radius, radius)
        for x, y, value, size, bold, muted, align in plan['texts']:
            formatted = text.make(value, size, bold, muted)
            left = x - formatted.WidthIncludingTrailingWhitespace if align == 'right' else x
            context.DrawText(formatted, Point(left, y))
    finally:
        context.Close()
    bitmap = RenderTargetBitmap(int(round(plan['width'] * scale)), int(round(plan['height'] * scale)),
                                96.0 * scale, 96.0 * scale, PixelFormats.Pbgra32)
    bitmap.Render(visual)
    encoder = PngBitmapEncoder()
    encoder.Frames.Add(BitmapFrame.Create(bitmap))
    stream = MemoryStream()
    try:
        encoder.Save(stream)
        data = bytes(bytearray(stream.ToArray()))
    finally:
        stream.Dispose()
    return data, plan['width'], plan['height']


def save_png(scheme, path, scale=SCALE):
    """Renders and writes the legend (atomically). Returns (path, width,
    height, png bytes). IOError when the file cannot be written."""
    from namo import paths
    data, width, height = render(scheme, scale)
    folder = os.path.dirname(os.path.abspath(path))
    if folder and not os.path.isdir(folder):
        paths.ensure_dir(folder)
    paths.atomic_write_bytes(path, data)
    return path, width, height, data


# =============================================================================
# Navisworks half
# =============================================================================


def save_view(name, comments, doc=None):
    """Saves a viewpoint that brings these colours back (see the module
    docstring). Returns (saved name, True when the colours are in it)."""
    from pynavis._api import Api, Application
    from pynavis.viewpoints import transaction
    from namo import camera
    document = doc if doc is not None else Application.ActiveDocument
    texts = [comments] if isinstance(comments, str) else list(comments or [])
    try:
        snapshot = document.SavedViewpoints.CaptureRuntimeOverrides()
        with_colors = snapshot is not None and snapshot.ContainsAppearanceOverrides
    except Exception:
        snapshot, with_colors = None, False
    if not with_colors:
        saved = camera.save_view(name, comments=texts, doc=document)
        return saved.DisplayName if saved is not None else name, False
    saved_points = document.SavedViewpoints
    root = saved_points.RootItem
    final = camera.unique_name(str(name), [child.DisplayName for child in root.Children])
    snapshot.DisplayName = final
    with transaction('Save legend viewpoint', document):
        before = set(str(child.Guid) for child in root.Children)
        saved_points.AddCopy(snapshot)
        added = None
        for child in root.Children:
            if str(child.Guid) not in before:
                added = child
                break
        if added is not None:
            for text in texts:
                if text:
                    saved_points.AddComment(added, Api.Comment(str(text), Api.CommentStatus.New))
    return final, True
