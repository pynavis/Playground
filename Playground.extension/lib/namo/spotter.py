# -*- coding: utf-8 -*-
"""Coordinate Spotter: numbered coordinate markers dropped by clicking, a table of
them, and Clear Spots.

Each click (namo.picking.point: the host's own Measure tool, so the pointer snaps
exactly as a measurement does, with the object found under the picked point) adds a
point P1, P2 ... drawn with pynavis.overlay as a small 3D cross with
its label 'P3  X 12' 4"  Y 30' 0"  Z 9' 6"' under its own tag ('playground-spot-3'), so
every label stays readable. Numbering carries on across runs until Clear Spots; the
points live on a session holder. An optional local origin (per document, Shift+Click)
makes every coordinate relative to it.

Pure half: labels, table rows (display text and plain numbers), CSV/TSV text, the
'x, y, z' parser for a typed origin, marker geometry. API half: picking, drawing,
clearing, the origin store, exports.
"""
import csv
import io
import math
import re

TAG_PREFIX = 'playground-spot-'
HOLDER = 'spotter'
STORE = 'coordinate-spotter'
MARKER_M = 0.25             # arm of the cross, the size Go to Coordinates draws
MARKER_MAX_M = 1.0          # never bigger, however far apart the models sit
MAX_SWEEP = 999

_LABEL = re.compile(r'[XxYyZz]\s*[:=]\s*')
_SEPARATORS = re.compile(r'[,;\t\r\n]+')


# ---- pure ---------------------------------------------------------------------------


def relative(point, origin):
    if not origin:
        return tuple(float(v) for v in point)
    return tuple(float(p) - float(o) for p, o in zip(point, origin))


def tag(n):
    return '%s%d' % (TAG_PREFIX, int(n))


def label(n, point, doc_units, origin=None):
    """'P3  X 12.000 m  Y 3.500 m  Z 0.000 m' (relative to origin when given)."""
    from namo import vp_common
    return 'P%d  %s' % (int(n), vp_common.point_text(relative(point, origin), doc_units))


def prompt_text(n, last=None, doc_units='Meters', origin=None):
    """The banner line while the pick for point n runs: the instruction, then the
    last reading so it stays in view between clicks."""
    text = 'Click point %d' % int(n)
    if last is not None:
        text += '. Last: %s' % label(last['n'], last['point'], doc_units, origin)
    elif origin:
        text += ', measured from the local origin'
    return text


def headers(doc_units, origin=None):
    from namo import vp_common
    symbol = vp_common.unit_symbol(doc_units)
    word = 'from origin ' if origin else ''
    return ['Point', 'X %s(%s)' % (word, symbol), 'Y %s(%s)' % (word, symbol), 'Z %s(%s)' % (word, symbol),
            'X (m)', 'Y (m)', 'Z (m)', 'Object', 'Model']


def display_rows(points, doc_units, origin=None):
    """Rows for the output window: lengths as people read them."""
    from namo import vp_common
    out = []
    for p in points:
        rel = relative(p['point'], origin)
        out.append(['P%d' % p['n']] + [vp_common.length_text(v, doc_units) for v in rel]
                   + [vp_common.meters_text(v, doc_units) for v in rel]
                   + [p.get('object') or '', p.get('model') or ''])
    return out


def data_rows(points, doc_units, origin=None, decimals=6):
    """Rows for Excel and CSV: plain numbers (document units, then metres)."""
    from namo import vp_common
    k = vp_common.to_meters_factor(doc_units)
    out = []
    for p in points:
        rel = relative(p['point'], origin)
        out.append(['P%d' % p['n']] + [round(v, decimals) for v in rel] + [round(v * k, decimals) for v in rel]
                   + [p.get('object') or '', p.get('model') or ''])
    return out


def tsv(head, rows):
    """Tab-separated text (Excel pastes it into cells)."""
    def cell(value):
        return str(value).replace('\t', ' ').replace('\r', ' ').replace('\n', ' ')
    return '\r\n'.join('\t'.join(cell(v) for v in row) for row in [head] + list(rows)) + '\r\n'


def csv_text(head, rows):
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator='\r\n')
    writer.writerow([str(h) for h in head])
    for row in rows:
        writer.writerow([('%s' % v) for v in row])
    return buffer.getvalue()


def parse_xyz(text, doc_units):
    """(x, y, z) from typed or pasted text ('12.5, 3, 0', 'X=1 Y=2 Z=3', "10' 6", 4', 0"),
    or None. Exactly three values; lengths may carry units and a sign."""
    from namo import units
    if not text or len(text) > 2000:
        return None
    cleaned = _LABEL.sub(' ', str(text).strip().strip('[](){}<>'))
    tokens = _SEPARATORS.split(cleaned) if _SEPARATORS.search(cleaned) else cleaned.split()
    values = []
    for token in tokens:
        token = token.strip().strip('[](){}<>').strip()
        if not token:
            continue
        number = units.parse_number(token)
        if number is None:
            sign = -1.0 if token[:1] == '-' else 1.0
            body = token[1:] if token[:1] in '+-' else token
            length = units.parse_length(body, doc_units)
            if length is None:
                return None
            number = sign * length
        if number != number or abs(number) == float('inf'):
            return None
        values.append(float(number))
        if len(values) > 3:
            return None
    return tuple(values) if len(values) == 3 else None


def marker_segments(point, size):
    """A 3D cross centred on point: three arms of half-length size."""
    x, y, z = [float(v) for v in point]
    arm = abs(float(size))
    return [((x - arm, y, z), (x + arm, y, z), False),
            ((x, y - arm, z), (x, y + arm, z), False),
            ((x, y, z - arm), (x, y, z + arm), False)]


def marker_size(doc_units, box=None):
    """Arm length in document units: 0.25 m, growing with the model (0.2% of its
    diagonal) up to 1 m. The cap matters: a federation with one stray object at the
    origin and the site a million feet away has a diagonal that says nothing about
    the size of what is being looked at."""
    from namo import vp_common
    k = 1.0 / vp_common.to_meters_factor(doc_units)
    size = MARKER_M * k
    if box:
        diagonal = math.sqrt(sum((b - a) ** 2 for a, b in zip(box[0], box[1])))
        size = min(max(size, diagonal * 0.002), MARKER_MAX_M * k)
    return size


# ==== API half ======================================================================


def state(doc_key=None):
    """The session holder: .points [{'n', 'point', 'object', 'model'}],
    .count (last number used), .doc (key of the document they belong to)."""
    from namo import session
    h = session.holder(HOLDER)
    if not hasattr(h, 'points'):
        h.points = []
        h.count = 0
        h.doc = None
    return h


def clear(sweep=False):
    """Removes every spot marker. Returns how many points there were. sweep also
    clears tags up to MAX_SWEEP (after a lost session holder)."""
    from pynavis import overlay
    h = state()
    highest = max([p['n'] for p in h.points] + [h.count, 0])
    if sweep or not h.points:
        highest = max(highest, MAX_SWEEP)
    for n in range(1, highest + 1):
        try:
            overlay.clear(tag(n))
        except Exception:
            break
    try:
        _overlay_redraw()
    except Exception:
        pass
    count = len(h.points)
    h.points = []
    h.count = 0
    h.doc = None
    return count


def load_origin(document):
    from namo import store, vp_common
    try:
        value = store.Store(STORE, doc_path=vp_common.doc_path(document)).load({}) or {}
        origin = value.get('origin')
        if origin and len(origin) == 3:
            return tuple(float(v) for v in origin)
    except Exception:
        pass
    return None


def save_origin(document, origin):
    from namo import store, vp_common
    store.Store(STORE, doc_path=vp_common.doc_path(document)).save(
        {'origin': list(origin) if origin else None})


def draw(point_record, doc_units, origin, size):
    from pynavis import overlay
    p = point_record['point']
    return overlay.add(tag(point_record['n']), marker_segments(p, size),
                       label=label(point_record['n'], p, doc_units, origin), label_at=p)


def redraw_all(doc_units, origin, size):
    """Redraws every marker (after the origin changed)."""
    from pynavis import overlay
    for record in state().points:
        draw(record, doc_units, origin, size)
    _overlay_redraw()


def record_of(n, hit):
    """A point record from a namo.picking Hit (a measured point knows no snap kind;
    the object is the front-most one at the point, when there is one)."""
    from namo import items
    name = ''
    model = ''
    if hit.item is not None:
        try:
            name = str(items.object_of(hit.item).DisplayName or '')
        except Exception:
            name = ''
        try:
            model = items.model_name(hit.item)
        except Exception:
            model = ''
    return {'n': int(n), 'point': tuple(float(v) for v in hit.point), 'object': name, 'model': model}


def write_xlsx(path, head, rows, title):
    from namo import config, xlsx
    wb = xlsx.Workbook(title='Coordinates', author=config.user_name())
    wb.style('coord', num_format='0.000')
    ws = wb.sheet('Points')
    ws.title(title, span=len(head))
    widths = [8, 14, 14, 14, 12, 12, 12, 36, 28]
    styles = [None] + ['coord'] * 6 + [None, None]
    ws.columns([(h, w, s) for h, w, s in zip(head, widths, styles)])
    for row in rows:
        ws.row(row)
    ws.autofilter()
    return wb.save(path)


def write_csv(path, head, rows):
    from namo import paths
    return paths.atomic_write_text(path, u'﻿' + csv_text(head, rows))


def _overlay_redraw():
    """Redraws the overlay through namo.overlayfix, so labels land on their points."""
    from namo import overlayfix
    return overlayfix.redraw()
