# -*- coding: utf-8 -*-
"""A small, tolerant ASCII DXF reader for plan overlays (pure: no Navisworks, no .NET).

read(text) returns the drawing flattened to 2D line segments in WORLD XY (the Z of
every entity is dropped, since the overlay places the sheet at one elevation):

  * LINE, LWPOLYLINE (bulges tessellated as arcs), POLYLINE + VERTEX (2D and 3D;
    polyface and mesh polylines skipped), ARC, CIRCLE, ELLIPSE (full or partial),
    SPLINE (through its fit points, else its control polygon: an approximation);
  * INSERT expanded `max_depth` levels (default 1: a block inserted in ENTITIES is
    drawn, a block nested inside that block is counted and skipped), with insertion
    point, X/Y scale (mirrors too), rotation, MINSERT arrays, and the block's base
    point;
  * TEXT and MTEXT as labels (MTEXT formatting codes stripped);
  * entity coordinate systems (group codes 210/220/230) by AutoCAD's arbitrary axis
    algorithm, so mirrored arcs and blocks land where AutoCAD draws them.

Everything else (HATCH, DIMENSION, POINT, SOLID, 3DFACE, IMAGE, VIEWPORT...) is
counted in 'skipped'. The reader never raises on a damaged entity: it skips it and
says so in 'notes'. A binary DXF raises ValueError (save as ASCII DXF).

Group codes are read as (code, value) line pairs; a line that should be a code but
is not a number makes the reader resynchronise on the next line that is.
"""
import math
import re

ARC_STEP_DEG = 10.0
MAX_SEGMENTS = 400000
MAX_TEXTS = 20000

INSUNITS_M = {1: 0.0254, 2: 0.3048, 3: 1609.344, 4: 0.001, 5: 0.01, 6: 1.0, 7: 1000.0,
              8: 2.54e-8, 9: 2.54e-5, 10: 0.9144, 11: 1e-10, 12: 1e-9, 13: 1e-6,
              14: 0.1, 15: 10.0, 16: 100.0, 17: 1e9}
INSUNITS_NAMES = {1: 'Inches', 2: 'Feet', 3: 'Miles', 4: 'Millimeters', 5: 'Centimeters',
                  6: 'Meters', 7: 'Kilometers', 8: 'Microinches', 9: 'Mils', 10: 'Yards',
                  13: 'Micrometers', 14: 'Decimeters'}

DRAWN = ('LINE', 'LWPOLYLINE', 'POLYLINE', 'ARC', 'CIRCLE', 'ELLIPSE', 'SPLINE', 'INSERT',
         'TEXT', 'MTEXT')


# ---- group code pairs ---------------------------------------------------------------


def decode(data):
    """Text from DXF bytes: UTF-8 (R2007+), else Windows-1252 (older files)."""
    if isinstance(data, str):
        return data
    raw = bytes(data)
    if raw.startswith(b'AutoCAD Binary DXF'):
        raise ValueError('This is a binary DXF. Save it as an ASCII DXF and try again.')
    for codec in ('utf-8-sig', 'cp1252', 'latin-1'):
        try:
            return raw.decode(codec)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode('latin-1', 'replace')


def pairs(text):
    """[(code, value)] from DXF text; tolerant of blank lines, spaces and CR/LF."""
    if text.startswith('AutoCAD Binary DXF'):
        raise ValueError('This is a binary DXF. Save it as an ASCII DXF and try again.')
    lines = text.splitlines()
    out = []
    i = 0
    n = len(lines)
    while i < n - 1:
        head = lines[i].strip()
        try:
            code = int(head)
        except ValueError:
            i += 1                      # resynchronise
            continue
        value = lines[i + 1]
        # Text content (1, 3) keeps its spaces: an MTEXT split into chunks of 250
        # characters may break between two words.
        out.append((code, value.rstrip('\r\n') if code in (1, 3) else value.strip()))
        i += 2
    return out


def _float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value, default=0):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


# ---- maths --------------------------------------------------------------------------


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _unit(v):
    size = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
    if size < 1e-15:
        return (0.0, 0.0, 1.0)
    return (v[0] / size, v[1] / size, v[2] / size)


def ocs_axes(normal):
    """(Ax, Ay, Az) of an entity coordinate system (AutoCAD's arbitrary axis
    algorithm). (0, 0, 1) gives the world axes."""
    n = _unit(normal)
    if abs(n[0]) < 1.0 / 64 and abs(n[1]) < 1.0 / 64:
        ax = _unit(_cross((0.0, 1.0, 0.0), n))
    else:
        ax = _unit(_cross((0.0, 0.0, 1.0), n))
    ay = _unit(_cross(n, ax))
    return ax, ay, n


IDENTITY = ((1.0, 0.0, 0.0, 0.0), (0.0, 1.0, 0.0, 0.0), (0.0, 0.0, 1.0, 0.0))


def matmul(a, b):
    """3x4 affine matrices: a after b."""
    out = []
    for r in range(3):
        row = []
        for c in range(4):
            v = a[r][0] * b[0][c] + a[r][1] * b[1][c] + a[r][2] * b[2][c]
            if c == 3:
                v += a[r][3]
            row.append(v)
        out.append(tuple(row))
    return tuple(out)


def apply(m, p):
    x, y, z = p[0], p[1], (p[2] if len(p) > 2 else 0.0)
    return (m[0][0] * x + m[0][1] * y + m[0][2] * z + m[0][3],
            m[1][0] * x + m[1][1] * y + m[1][2] * z + m[1][3],
            m[2][0] * x + m[2][1] * y + m[2][2] * z + m[2][3])


def translation(dx, dy, dz=0.0):
    return ((1.0, 0.0, 0.0, dx), (0.0, 1.0, 0.0, dy), (0.0, 0.0, 1.0, dz))


def scaling(sx, sy, sz=1.0):
    return ((sx, 0.0, 0.0, 0.0), (0.0, sy, 0.0, 0.0), (0.0, 0.0, sz, 0.0))


def rotation_z(degrees):
    a = math.radians(degrees)
    c, s = math.cos(a), math.sin(a)
    return ((c, -s, 0.0, 0.0), (s, c, 0.0, 0.0), (0.0, 0.0, 1.0, 0.0))


def ocs_matrix(normal):
    ax, ay, az = ocs_axes(normal)
    return ((ax[0], ay[0], az[0], 0.0), (ax[1], ay[1], az[1], 0.0), (ax[2], ay[2], az[2], 0.0))


def arc_points(cx, cy, radius, start_deg, end_deg, step_deg=ARC_STEP_DEG):
    """Points along a counter-clockwise arc from start to end (degrees), ends
    included. end <= start wraps once around."""
    sweep = end_deg - start_deg
    while sweep <= 0:
        sweep += 360.0
    if sweep > 360.0:
        sweep = 360.0
    count = max(2, int(math.ceil(sweep / max(0.5, step_deg))))
    out = []
    for i in range(count + 1):
        a = math.radians(start_deg + sweep * i / count)
        out.append((cx + radius * math.cos(a), cy + radius * math.sin(a)))
    return out


def bulge_points(p1, p2, bulge, step_deg=ARC_STEP_DEG):
    """Points from p1 to p2 along the arc a polyline bulge describes (bulge =
    tan(included angle / 4), positive counter-clockwise); [p1, p2] for 0."""
    if abs(bulge) < 1e-12:
        return [p1, p2]
    x1, y1 = p1
    x2, y2 = p2
    chord = math.hypot(x2 - x1, y2 - y1)
    if chord < 1e-15:
        return [p1, p2]
    theta = 4.0 * math.atan(bulge)
    radius = chord / (2.0 * math.sin(abs(theta) / 2.0))
    mx, my = (x1 + x2) / 2.0, (y1 + y2) / 2.0
    sagitta_dist = math.sqrt(max(0.0, radius * radius - (chord / 2.0) ** 2))
    ux, uy = (x2 - x1) / chord, (y2 - y1) / chord
    # centre to the left of p1->p2 for a counter-clockwise arc shorter than half a turn
    side = 1.0 if (bulge > 0) == (abs(theta) < math.pi) else -1.0
    cx, cy = mx - uy * sagitta_dist * side, my + ux * sagitta_dist * side
    a1 = math.atan2(y1 - cy, x1 - cx)
    count = max(2, int(math.ceil(math.degrees(abs(theta)) / max(0.5, step_deg))))
    out = []
    for i in range(count + 1):
        a = a1 + theta * i / count
        out.append((cx + radius * math.cos(a), cy + radius * math.sin(a)))
    out[0] = p1
    out[-1] = p2
    return out


_MTEXT_CODES = [
    (re.compile(r'\\P'), ' '),
    (re.compile(r'\\[~]'), ' '),
    (re.compile(r'\\[fFhHcCtTqQaAwWpP][^;]*;'), ''),
    (re.compile(r'\\S([^;]*)[/#^]([^;]*);'), r'\1/\2'),
    (re.compile(r'\\[LlOoKk]'), ''),
]


def clean_mtext(text):
    """MTEXT content without its formatting codes ('{\\fArial|b0;Room}\\PNo. 2'
    reads 'Room No. 2')."""
    out = text
    out = re.sub(r'\\U\+([0-9A-Fa-f]{4})', lambda m: chr(int(m.group(1), 16)), out)
    for pattern, replacement in _MTEXT_CODES:
        out = pattern.sub(replacement, out)
    out = out.replace('\\\\', '\\').replace('\\{', '{').replace('\\}', '}')
    out = re.sub(r'(?<!\\)[{}]', '', out)
    return ' '.join(out.split())


def clean_text(text):
    """TEXT content without %%c/%%d/%%p control codes (shown as the symbols) and
    %%u/%%o toggles."""
    out = re.sub(r'%%[uUoOkK]', '', text)
    out = out.replace('%%c', chr(216)).replace('%%C', chr(216))
    out = out.replace('%%d', chr(176)).replace('%%D', chr(176))
    out = out.replace('%%p', chr(177)).replace('%%P', chr(177)).replace('%%%', '%')
    return ' '.join(out.split())


# ---- structure ----------------------------------------------------------------------


def _entities(seq):
    """[(type, [(code, value)])] from a run of pairs starting at a code 0."""
    out = []
    current = None
    for code, value in seq:
        if code == 0:
            current = (value.upper(), [])
            out.append(current)
        elif current is not None:
            current[1].append((code, value))
    return out


def sections(all_pairs):
    """{SECTION NAME: [(code, value)]} (pairs between SECTION/ENDSEC)."""
    out = {}
    i = 0
    n = len(all_pairs)
    while i < n:
        code, value = all_pairs[i]
        if code == 0 and value.upper() == 'SECTION' and i + 1 < n and all_pairs[i + 1][0] == 2:
            name = all_pairs[i + 1][1].upper()
            j = i + 2
            body = []
            while j < n and not (all_pairs[j][0] == 0 and all_pairs[j][1].upper() == 'ENDSEC'):
                body.append(all_pairs[j])
                j += 1
            out.setdefault(name, []).extend(body)
            i = j + 1
            continue
        i += 1
    return out


def header_vars(body):
    """{'$NAME': [(code, value)]} from the HEADER section."""
    out = {}
    current = None
    for code, value in body:
        if code == 9:
            current = value.upper()
            out[current] = []
        elif current is not None:
            out[current].append((code, value))
    return out


def group_polylines(entities):
    """Folds POLYLINE + VERTEX... + SEQEND into one ('POLYLINE', codes, vertices)."""
    out = []
    i = 0
    n = len(entities)
    while i < n:
        kind, codes = entities[i]
        if kind == 'POLYLINE':
            vertices = []
            j = i + 1
            while j < n and entities[j][0] == 'VERTEX':
                vertices.append(entities[j][1])
                j += 1
            if j < n and entities[j][0] == 'SEQEND':
                j += 1
            out.append(('POLYLINE', codes, vertices))
            i = j
            continue
        if kind in ('VERTEX', 'SEQEND'):
            i += 1
            continue
        out.append((kind, codes, None))
        i += 1
    return out


def blocks(body):
    """{block name: (base point, [entities])} from the BLOCKS section."""
    out = {}
    ents = _entities(body)
    i = 0
    while i < len(ents):
        kind, codes = ents[i]
        if kind == 'BLOCK':
            name = ''
            base = [0.0, 0.0, 0.0]
            for code, value in codes:
                if code == 2:
                    name = value
                elif code in (10, 20, 30):
                    base[(code // 10) - 1] = _float(value)
            j = i + 1
            inner = []
            while j < len(ents) and ents[j][0] != 'ENDBLK':
                inner.append(ents[j])
                j += 1
            out[name] = (tuple(base), group_polylines(inner))
            i = j + 1
            continue
        i += 1
    return out


# ---- entities to primitives ---------------------------------------------------------


class _Out(object):
    """Collects segments and texts with caps and counts."""

    def __init__(self, max_segments, max_texts):
        self.segments = []
        self.texts = []
        self.layers = {}
        self.counts = {}
        self.skipped = {}
        self.notes = []
        self.max_segments = max_segments
        self.max_texts = max_texts
        self.capped = False
        self.text_capped = False

    def count(self, kind):
        self.counts[kind] = self.counts.get(kind, 0) + 1

    def skip(self, kind):
        self.skipped[kind] = self.skipped.get(kind, 0) + 1

    def polyline(self, points3, layer, m):
        prev = None
        for p in points3:
            q = apply(m, p)
            if prev is not None:
                if len(self.segments) >= self.max_segments:
                    self.capped = True
                    return
                if abs(q[0] - prev[0]) > 1e-12 or abs(q[1] - prev[1]) > 1e-12:
                    self.segments.append(((prev[0], prev[1]), (q[0], q[1]), layer))
                    self.layers[layer] = self.layers.get(layer, 0) + 1
            prev = q

    def text(self, value, point3, height, rotation, layer, m):
        if not value:
            return
        if len(self.texts) >= self.max_texts:
            self.text_capped = True
            return
        q = apply(m, point3)
        self.texts.append({'text': value, 'x': q[0], 'y': q[1], 'height': height,
                           'rotation': rotation, 'layer': layer})


def _codes_dict(codes):
    """First value of each code, plus 'all' lists for repeated codes."""
    first = {}
    for code, value in codes:
        if code not in first:
            first[code] = value
    return first


def _normal(first):
    return (_float(first.get(210), 0.0), _float(first.get(220), 0.0), _float(first.get(230), 1.0))


def _entity(kind, codes, vertices, out, m, blocks_, depth, max_depth, step):
    first = _codes_dict(codes)
    layer = first.get(8, '0') or '0'
    if kind == 'LINE':
        p1 = (_float(first.get(10)), _float(first.get(20)), _float(first.get(30)))
        p2 = (_float(first.get(11)), _float(first.get(21)), _float(first.get(31)))
        out.polyline([p1, p2], layer, m)
    elif kind == 'LWPOLYLINE':
        flags = _int(first.get(70))
        elevation = _float(first.get(38))
        verts = []
        for code, value in codes:
            if code == 10:
                verts.append([_float(value), 0.0, 0.0])
            elif code == 20 and verts:
                verts[-1][1] = _float(value)
            elif code == 42 and verts:
                verts[-1][2] = _float(value)
        if len(verts) < 2:
            raise ValueError('a polyline with fewer than two vertices')
        mm = matmul(m, ocs_matrix(_normal(first)))
        out.polyline(_trace(verts, bool(flags & 1), elevation, step), layer, mm)
    elif kind == 'POLYLINE':
        flags = _int(first.get(70))
        if flags & (16 | 64):
            out.skip('POLYLINE mesh')
            return False
        is3d = bool(flags & 8)
        verts = []
        for vcodes in vertices or []:
            vfirst = _codes_dict(vcodes)
            if _int(vfirst.get(70)) & 128 and 10 not in vfirst:
                continue
            verts.append([_float(vfirst.get(10)), _float(vfirst.get(20)), _float(vfirst.get(42)),
                          _float(vfirst.get(30))])
        if len(verts) < 2:
            raise ValueError('a polyline with fewer than two vertices')
        if is3d:
            pts = [(v[0], v[1], v[3]) for v in verts]
            if flags & 1:
                pts.append(pts[0])
            out.polyline(pts, layer, m)
        else:
            elevation = _float(first.get(30))
            mm = matmul(m, ocs_matrix(_normal(first)))
            out.polyline(_trace([[v[0], v[1], v[2]] for v in verts], bool(flags & 1), elevation, step),
                         layer, mm)
    elif kind in ('ARC', 'CIRCLE'):
        cx, cy, cz = _float(first.get(10)), _float(first.get(20)), _float(first.get(30))
        radius = _float(first.get(40))
        if radius <= 0:
            raise ValueError('a circle without a radius')
        if kind == 'CIRCLE':
            start, end = 0.0, 360.0
        else:
            start, end = _float(first.get(50)), _float(first.get(51))
        pts = [(x, y, cz) for x, y in arc_points(cx, cy, radius, start, end, step)]
        out.polyline(pts, layer, matmul(m, ocs_matrix(_normal(first))))
    elif kind == 'ELLIPSE':
        c = (_float(first.get(10)), _float(first.get(20)), _float(first.get(30)))
        major = (_float(first.get(11)), _float(first.get(21)), _float(first.get(31)))
        ratio = _float(first.get(40), 1.0)
        t0, t1 = _float(first.get(41), 0.0), _float(first.get(42), 2.0 * math.pi)
        n = _unit(_normal(first))
        minor_dir = _unit(_cross(n, major))
        length = math.sqrt(sum(v * v for v in major))
        minor = tuple(v * length * ratio for v in minor_dir)
        sweep = t1 - t0
        while sweep <= 0:
            sweep += 2.0 * math.pi
        count = max(4, int(math.ceil(math.degrees(sweep) / max(0.5, step))))
        pts = []
        for i in range(count + 1):
            t = t0 + sweep * i / count
            pts.append(tuple(c[k] + math.cos(t) * major[k] + math.sin(t) * minor[k] for k in range(3)))
        out.polyline(pts, layer, m)
    elif kind == 'SPLINE':
        fit = []
        control = []
        for code, value in codes:
            if code == 11:
                fit.append([_float(value), 0.0, 0.0])
            elif code == 21 and fit:
                fit[-1][1] = _float(value)
            elif code == 31 and fit:
                fit[-1][2] = _float(value)
            elif code == 10:
                control.append([_float(value), 0.0, 0.0])
            elif code == 20 and control:
                control[-1][1] = _float(value)
            elif code == 30 and control:
                control[-1][2] = _float(value)
        pts = fit if len(fit) >= 2 else control
        if len(pts) < 2:
            raise ValueError('a spline without points')
        if len(fit) < 2:
            out.count('SPLINE control polygon')
        if _int(first.get(70)) & 1:
            pts = pts + [pts[0]]
        out.polyline([tuple(p) for p in pts], layer, m)
    elif kind == 'TEXT':
        value = clean_text(first.get(1, ''))
        h, v = _int(first.get(72)), _int(first.get(73))
        if (h or v) and 11 in first:
            p = (_float(first.get(11)), _float(first.get(21)), _float(first.get(31)))
        else:
            p = (_float(first.get(10)), _float(first.get(20)), _float(first.get(30)))
        out.text(value, p, _float(first.get(40), 1.0), _float(first.get(50)), layer,
                 matmul(m, ocs_matrix(_normal(first))))
    elif kind == 'MTEXT':
        chunks = [value for code, value in codes if code == 3]
        chunks.append(first.get(1, ''))
        value = clean_mtext(''.join(chunks))
        p = (_float(first.get(10)), _float(first.get(20)), _float(first.get(30)))
        out.text(value, p, _float(first.get(40), 1.0), _float(first.get(50)), layer, m)
    elif kind == 'INSERT':
        name = first.get(2, '')
        if depth >= max_depth:
            out.skip('INSERT nested deeper than %d' % max_depth)
            return False
        if name not in blocks_:
            out.skip('INSERT of a missing block')
            return False
        base, inner = blocks_[name]
        ins = (_float(first.get(10)), _float(first.get(20)), _float(first.get(30)))
        sx, sy, sz = _float(first.get(41), 1.0), _float(first.get(42), 1.0), _float(first.get(43), 1.0)
        rot = _float(first.get(50))
        cols, rows = max(1, _int(first.get(70), 1)), max(1, _int(first.get(71), 1))
        dx, dy = _float(first.get(44)), _float(first.get(45))
        if cols * rows > 2500:
            out.notes.append('An array of %d copies of block %s was cut to 2,500.' % (cols * rows, name))
        ocs = ocs_matrix(_normal(first))
        made = 0
        for r in range(rows):
            for c in range(cols):
                if made >= 2500:
                    break
                made += 1
                local = matmul(translation(ins[0], ins[1], ins[2]),
                               matmul(rotation_z(rot),
                                      matmul(translation(c * dx, r * dy, 0.0),
                                             matmul(scaling(sx, sy, sz),
                                                    translation(-base[0], -base[1], -base[2])))))
                mm = matmul(m, matmul(ocs, local))
                for ikind, icodes, iverts in inner:
                    _safe_entity(ikind, icodes, iverts, out, mm, blocks_, depth + 1, max_depth, step)
    else:
        out.skip(kind)
        return False
    return True


def _trace(verts, closed, elevation, step):
    """3D OCS points of a 2D polyline with bulges: verts [[x, y, bulge]]."""
    pts = []
    count = len(verts)
    last = count if closed else count - 1
    for i in range(last):
        a = verts[i]
        b = verts[(i + 1) % count]
        piece = bulge_points((a[0], a[1]), (b[0], b[1]), a[2], step)
        if pts:
            piece = piece[1:]
        pts.extend(piece)
    return [(x, y, elevation) for x, y in pts]


def _safe_entity(kind, codes, vertices, out, m, blocks_, depth, max_depth, step):
    try:
        if _entity(kind, codes, vertices, out, m, blocks_, depth, max_depth, step):
            out.count(kind)
    except Exception as error:
        out.skip('%s (damaged)' % kind)
        if len(out.notes) < 20:
            out.notes.append('A %s was skipped: %s.' % (kind, error))


# ---- the reader -------------------------------------------------------------------------


def read(text, max_depth=1, step_deg=ARC_STEP_DEG, max_segments=MAX_SEGMENTS, max_texts=MAX_TEXTS):
    """The drawing as {'units' ($INSUNITS code, 0 when unset), 'units_name',
    'segments' [((x1, y1), (x2, y2), layer)], 'texts' [{'text', 'x', 'y', 'height',
    'rotation', 'layer'}], 'layers' {name: segments}, 'counts' {entity: drawn},
    'skipped' {kind: n}, 'notes' [sentences], 'extents' ((x0, y0), (x1, y1)) or None,
    'capped' bool}. Raises ValueError for text that holds no DXF."""
    text = decode(text)
    all_pairs = pairs(text)
    if not all_pairs:
        raise ValueError('The file holds no DXF data.')
    parts = sections(all_pairs)
    if not parts and not any(code == 0 for code, _v in all_pairs):
        raise ValueError('The file holds no DXF data.')
    variables = header_vars(parts.get('HEADER', []))
    units = 0
    for code, value in variables.get('$INSUNITS', []):
        if code == 70:
            units = _int(value)
    block_table = blocks(parts.get('BLOCKS', []))
    body = parts.get('ENTITIES')
    if body is None:
        body = all_pairs if not parts else []
    out = _Out(max_segments, max_texts)
    for kind, codes, vertices in group_polylines(_entities(body)):
        if kind in ('ENDSEC', 'EOF', 'SECTION'):
            continue
        _safe_entity(kind, codes, vertices, out, IDENTITY, block_table, 0, max_depth, step_deg)
        if out.capped:
            out.notes.append('The drawing has more than %s line segments; the rest were left out.'
                             % '{:,}'.format(max_segments))
            break
    if out.text_capped:
        out.notes.append('Only the first %s texts were read.' % '{:,}'.format(max_texts))
    xs = [p[0] for s in out.segments for p in s[:2]] + [t['x'] for t in out.texts]
    ys = [p[1] for s in out.segments for p in s[:2]] + [t['y'] for t in out.texts]
    extents = ((min(xs), min(ys)), (max(xs), max(ys))) if xs else None
    return {'units': units, 'units_name': INSUNITS_NAMES.get(units), 'segments': out.segments,
            'texts': out.texts, 'layers': out.layers, 'counts': out.counts, 'skipped': out.skipped,
            'notes': out.notes, 'extents': extents, 'capped': out.capped}


def read_file(path, **kw):
    with open(path, 'rb') as handle:
        data = handle.read()
    return read(decode(data), **kw)


def units_to_meters(code):
    """Metres per drawing unit for an $INSUNITS code, or None (unitless)."""
    return INSUNITS_M.get(int(code or 0))


def summary(drawing):
    """'12,345 lines on 8 layers, 210 texts' for toasts."""
    lines = len(drawing['segments'])
    layers = len(drawing['layers'])
    texts = len(drawing['texts'])
    parts = ['%s line%s' % ('{:,}'.format(lines), '' if lines == 1 else 's')]
    if layers:
        parts[0] += ' on %d layer%s' % (layers, '' if layers == 1 else 's')
    if texts:
        parts.append('%s text%s' % ('{:,}'.format(texts), '' if texts == 1 else 's'))
    return ', '.join(parts)
