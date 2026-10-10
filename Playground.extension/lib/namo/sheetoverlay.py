# -*- coding: utf-8 -*-
"""Sheet Overlay: a 2D CAD sheet (DXF, read by namo.dxf) drawn over the model at one
elevation with pynavis.overlay.

Placement (stored per document in the store 'sheet-overlay', so showing the sheet
again is one click):
    {'file', 'elevation' (model units), 'level' (name or None), 'scale' (model units
     per drawing unit), 'rotation' (degrees, counter-clockwise), 'dx', 'dy' (where the
     drawing origin lands, model units), 'mode' ('manual' | 'points'), 'layers'
     (names drawn, None = all), 'texts' (bool), 'units' (the drawing units used)}

    model XY = R(rotation) * (scale * drawing XY) + (dx, dy)

Two reference points: drawing points p1, p2 (typed) and model points q1, q2 (picked
with the Measure tool through namo.picking.points, one two-click run) give the
rotation and offset, and the scale too unless the drawing units are trusted.
Lines go in ONE overlay item (tag 'playground-sheet', capped at 30,000 segments); each
text is its own small item (tag 'playground-sheet-t<n>', capped at 300) with a short tick
at its anchor.
"""
import math
import os

TAG = 'playground-sheet'
TEXT_TAG = 'playground-sheet-t'
STORE = 'sheet-overlay'
HOLDER = 'sheetoverlay'
MAX_SEGMENTS = 30000
MAX_LABELS = 300
UNIT_CHOICES = ['Millimeters', 'Centimeters', 'Meters', 'Inches', 'Feet']


# ---- pure ---------------------------------------------------------------------------


def unit_scale(drawing_units, doc_units):
    """Model units per drawing unit (drawing_units: a document unit name)."""
    from namo import vp_common
    return vp_common.unit_factor(drawing_units, doc_units)


def to_model(point, placement):
    """(X, Y) of a drawing point under a placement."""
    s = float(placement['scale'])
    a = math.radians(float(placement.get('rotation') or 0.0))
    c, si = math.cos(a), math.sin(a)
    x, y = float(point[0]) * s, float(point[1]) * s
    return (c * x - si * y + float(placement.get('dx') or 0.0),
            si * x + c * y + float(placement.get('dy') or 0.0))


def from_points(p1, p2, q1, q2, fixed_scale=None):
    """(scale, rotation degrees, dx, dy) mapping drawing p1 -> model q1 and the
    direction p1->p2 onto q1->q2. Scale from the two distances unless fixed_scale.
    ValueError when either pair is one point."""
    dp = (float(p2[0]) - float(p1[0]), float(p2[1]) - float(p1[1]))
    dq = (float(q2[0]) - float(q1[0]), float(q2[1]) - float(q1[1]))
    lp, lq = math.hypot(*dp), math.hypot(*dq)
    if lp < 1e-12:
        raise ValueError('The two drawing points are the same point.')
    if lq < 1e-12:
        raise ValueError('The two model points are the same point.')
    scale = float(fixed_scale) if fixed_scale else lq / lp
    rotation = math.degrees(math.atan2(dq[1], dq[0]) - math.atan2(dp[1], dp[0]))
    rotation = (rotation + 180.0) % 360.0 - 180.0
    a = math.radians(rotation)
    c, s = math.cos(a), math.sin(a)
    x, y = float(p1[0]) * scale, float(p1[1]) * scale
    dx = float(q1[0]) - (c * x - s * y)
    dy = float(q1[1]) - (s * x + c * y)
    return scale, rotation, dx, dy


def parse_xy(text):
    """(x, y) from '12.5, 3' / '12.5 3' / 'X=12.5 Y=3' (plain drawing numbers), or None."""
    import re
    if text is None:
        return None
    cleaned = re.sub(r'[XxYy]\s*[:=]\s*', ' ', str(text)).strip().strip('()[]')
    parts = [p for p in re.split(r'[,;\s]+', cleaned) if p]
    if len(parts) != 2:
        return None
    try:
        return (float(parts[0]), float(parts[1]))
    except ValueError:
        return None


def segments_3d(drawing, placement, cap=MAX_SEGMENTS):
    """([((X, Y, Z), (X, Y, Z), False)], total eligible) for the drawn layers."""
    layers = placement.get('layers')
    wanted = set(layers) if layers is not None else None
    z = float(placement.get('elevation') or 0.0)
    out = []
    total = 0
    for a, b, layer in drawing['segments']:
        if wanted is not None and layer not in wanted:
            continue
        total += 1
        if len(out) >= cap:
            continue
        pa, pb = to_model(a, placement), to_model(b, placement)
        out.append(((pa[0], pa[1], z), (pb[0], pb[1], z), False))
    return out, total


def labels(drawing, placement, cap=MAX_LABELS):
    """([(text, (X, Y, Z))], total eligible) for texts on drawn layers (when texts on)."""
    if not placement.get('texts', True):
        return [], 0
    layers = placement.get('layers')
    wanted = set(layers) if layers is not None else None
    z = float(placement.get('elevation') or 0.0)
    out = []
    total = 0
    for t in drawing['texts']:
        if wanted is not None and t['layer'] not in wanted:
            continue
        total += 1
        if len(out) < cap:
            x, y = to_model((t['x'], t['y']), placement)
            out.append((t['text'][:80], (x, y, z)))
    return out, total


def tick(point, size):
    """A short flat cross marking a label's anchor."""
    x, y, z = point
    return [((x - size, y, z), (x + size, y, z), False), ((x, y - size, z), (x, y + size, z), False)]


def describe(drawing, placement, shown, total, label_count, label_total, doc_units, level_name=None):
    """(level, message, detail) after drawing."""
    from namo import vp_common
    where = level_name or vp_common.length_text(placement.get('elevation') or 0.0, doc_units)
    name = os.path.basename(str(placement.get('file') or 'the sheet'))
    parts = ['%s: %s line%s' % (name, vp_common.count_text(shown), '' if shown == 1 else 's')]
    if label_count:
        parts.append(vp_common.plural(label_count, 'label'))
    detail = '%s at %s.' % (', '.join(parts), where)
    notes = []
    if total > shown:
        notes.append('Showing %s of %s lines.' % (vp_common.count_text(shown), vp_common.count_text(total)))
    if label_total > label_count:
        notes.append('Showing %s of %s texts.' % (vp_common.count_text(label_count), vp_common.count_text(label_total)))
    if notes:
        return ('warning', 'Sheet placed, partly', detail + ' ' + ' '.join(notes))
    return ('success', 'Sheet placed', detail + ' Clear Sheet removes it.')


# ==== API half ======================================================================


def _store(document):
    from namo import store, vp_common
    return store.Store(STORE, doc_path=vp_common.doc_path(document))


def saved(document):
    """The stored placement for this document, or None."""
    try:
        value = _store(document).load(None)
        if isinstance(value, dict) and value.get('file') and value.get('scale'):
            return value
    except Exception:
        pass
    return None


def save(document, placement):
    _store(document).save(placement)


def clear():
    """Removes the sheet and its labels. Returns True when something was drawn."""
    from pynavis import overlay
    from namo import session
    holder = session.holder(HOLDER)
    count = int(getattr(holder, 'labels', 0) or 0)
    drawn = bool(getattr(holder, 'drawn', False))
    overlay.clear(TAG)
    for n in range(1, max(count, MAX_LABELS) + 1):
        overlay.clear('%s%d' % (TEXT_TAG, n))
    _overlay_redraw()
    holder.labels = 0
    holder.drawn = False
    return drawn


def draw(drawing, placement, doc_units):
    """Draws the sheet (replacing any earlier one). Returns (shown, total, labels,
    label total, overlay loaded)."""
    from pynavis import overlay
    from namo import session, vp_common
    clear()
    segs, total = segments_3d(drawing, placement)
    loaded = overlay.add(TAG, segs)
    texts, text_total = labels(drawing, placement)
    size = 0.1 / vp_common.to_meters_factor(doc_units)
    for n, (text, point) in enumerate(texts):
        overlay.add('%s%d' % (TEXT_TAG, n + 1), tick(point, size), label=text, label_at=point)
    _overlay_redraw()
    holder = session.holder(HOLDER)
    holder.labels = len(texts)
    holder.drawn = True
    return len(segs), total, len(texts), text_total, loaded


def read_drawing(path):
    """The parsed DXF (namo.dxf.read) inside a progress window; None when cancelled."""
    from namo import dxf, progress

    def work(report):
        report(0.1, 'Reading %s' % os.path.basename(path))
        return dxf.read_file(path)
    outcome = progress.run('Sheet Overlay', work)
    return None if outcome is progress.CANCELLED else outcome


def level_options(document, doc_units, found=None):
    """([(label, value)], levels) for the elevation choice: the levels, then typed."""
    from namo import levels, vp_common
    if found is None:
        found = levels.cached_or_none(document) or []
    options = [('%s (%s)' % (lv['name'], vp_common.length_text(lv['elevation'], doc_units)), 'level:' + lv['name'])
               for lv in found]
    options.append(('Type an elevation', 'typed'))
    return options, found


def placement_fields(drawing, previous, options, doc_units):
    """The ui.form fields of the placement step."""
    from namo import vp_common
    previous = previous or {}
    file_units = drawing.get('units_name')
    unit_options = []
    if file_units:
        unit_options.append(('From the file: %s' % file_units.lower(), 'file'))
    unit_options += [(u, u) for u in UNIT_CHOICES]
    default_units = previous.get('units_choice') or ('file' if file_units else doc_units)
    if default_units not in [v for _l, v in unit_options]:
        default_units = unit_options[0][1]
    default_level = previous.get('elevation_choice')
    if default_level not in [v for _l, v in options]:
        default_level = options[0][1]
    hint = 'In %s; negative values allowed.' % str(doc_units).lower()
    return [
        {'kind': 'choice', 'key': 'elevation_choice', 'label': 'Place the sheet at', 'options': options,
         'default': default_level, 'fallback': None},
        {'kind': 'text', 'key': 'elevation', 'label': 'Elevation', 'hint': hint,
         'default': vp_common.length_input(previous.get('elevation', 0.0), doc_units),
         'enabled_if': ('elevation_choice', 'typed')},
        {'kind': 'choice', 'key': 'units_choice', 'label': 'Drawing units', 'options': unit_options,
         'default': default_units, 'fallback': None},
        {'kind': 'radio', 'key': 'mode', 'label': 'Position by',
         'options': [('Rotation and offset', 'manual'), ('Two reference points', 'points')],
         'default': previous.get('mode') or 'manual', 'fallback': 'manual'},
        {'kind': 'number', 'key': 'rotation', 'label': 'Rotation (degrees, counter-clockwise)',
         'default': previous.get('rotation', 0.0), 'enabled_if': ('mode', 'manual')},
        {'kind': 'text', 'key': 'dx', 'label': 'Drawing origin lands at X', 'hint': hint,
         'default': vp_common.length_input(previous.get('dx', 0.0), doc_units), 'enabled_if': ('mode', 'manual')},
        {'kind': 'text', 'key': 'dy', 'label': 'Drawing origin lands at Y',
         'default': vp_common.length_input(previous.get('dy', 0.0), doc_units), 'enabled_if': ('mode', 'manual')},
        {'kind': 'text', 'key': 'p1', 'label': 'Drawing point 1 (x, y)', 'default': previous.get('p1', ''),
         'enabled_if': ('mode', 'points'), 'hint': 'In drawing units, for example a grid intersection: 0, 0'},
        {'kind': 'text', 'key': 'p2', 'label': 'Drawing point 2 (x, y)', 'default': previous.get('p2', ''),
         'enabled_if': ('mode', 'points')},
        {'kind': 'radio', 'key': 'point_scale', 'label': 'Scale',
         'options': [('From the drawing units', 'units'), ('From the two points', 'points')],
         'default': previous.get('point_scale') or 'units', 'fallback': 'units', 'enabled_if': ('mode', 'points'), 'inline': True},
        {'kind': 'check', 'key': 'texts', 'label': 'Show the texts as labels (up to %d)' % MAX_LABELS,
         'default': previous.get('texts', True)},
    ]


def validator(doc_units):
    """A ui.form validate(values) for the placement step."""
    return lambda values: validate(values, doc_units)


def validate(values, doc_units='Meters'):
    from namo import vp_common
    errors = {}
    if values.get('elevation_choice') == 'typed' and vp_common.signed_length(values.get('elevation'), doc_units) is None:
        errors['elevation'] = 'Type an elevation, like 4.2 or -3.5.'
    if values.get('mode') == 'manual':
        for key in ('dx', 'dy'):
            if vp_common.signed_length(values.get(key), doc_units) is None:
                errors[key] = 'Type a distance, like 0 or -1250.'
    if values.get('mode') == 'points':
        p1, p2 = parse_xy(values.get('p1')), parse_xy(values.get('p2'))
        if p1 is None:
            errors['p1'] = 'Type two numbers, like 12.5, 3.'
        if p2 is None:
            errors['p2'] = 'Type two numbers, like 40, 3.'
        if p1 is not None and p2 is not None and math.hypot(p2[0] - p1[0], p2[1] - p1[1]) < 1e-12:
            errors['p2'] = 'Point 2 must differ from point 1.'
    return errors or None


def drawing_units_of(values, drawing, doc_units):
    choice = values.get('units_choice')
    if choice == 'file':
        return drawing.get('units_name') or doc_units
    return choice or doc_units


def show(document, placement, drawing=None):
    """Draws a placement; (level, message, detail), or None when reading was
    cancelled."""
    from namo import session
    units = str(document.Units)
    if drawing is None:
        try:
            drawing = read_drawing(placement['file'])
        except (IOError, OSError, ValueError) as error:
            return ('error', 'Could not read the DXF', str(error))
        if drawing is None:
            return None
    for note in drawing.get('notes') or []:
        session.log('info', 'Sheet Overlay: %s' % note)
    shown, total, label_count, label_total, loaded = draw(drawing, placement, units)
    if not loaded:
        return ('warning', 'The overlay is not available', 'Restart Navisworks to finish updating pyNavis.')
    if not shown and not label_count:
        return ('info', 'Nothing to draw on the chosen layers', 'Shift+Click Sheet Overlay to choose other layers.')
    result = describe(drawing, placement, shown, total, label_count, label_total, units, placement.get('level'))
    if placement.get('scale_note'):
        result = (result[0], result[1], result[2] + ' ' + placement['scale_note'])
    return result


def pick_prompts(p1_text, p2_text):
    """(first, second) banner prompts for the two reference clicks (pure)."""
    return ('Click the model point that matches drawing point 1 (%s)' % str(p1_text).strip(),
            'Now click the model point that matches drawing point 2 (%s)' % str(p2_text).strip())


def _pick_model_points(p1_text, p2_text, document=None):
    """The two model reference points as ((x, y, z), (x, y, z)), or None when the
    user cancelled. One two-click run of the Measure tool (namo.picking.points, the
    way True Distance asks for its two faces): the pointer snaps as a measurement
    does, the prompts sit on the banner and nothing is left on screen."""
    from namo import picking
    first, second = pick_prompts(p1_text, p2_text)
    return picking.points(first, second, doc=document)


def setup(document, previous=None):
    """The full placement flow: file, layers, placement form, picks, draw, save.
    Returns (level, message, detail) or None when cancelled."""
    from pynavis import forms
    from namo import ui, vp_common
    units = str(document.Units)
    path = forms.open_file(filter='DXF drawings (*.dxf)|*.dxf', title='Sheet Overlay')
    if path is None:
        return None
    try:
        drawing = read_drawing(path)
    except (IOError, OSError) as error:
        return ('error', 'Could not open the DXF', '%s. Close it in your CAD program, then try again.' % error)
    except ValueError as error:
        return ('error', 'Could not read the DXF', str(error))
    if drawing is None:
        return None
    if not drawing['segments'] and not drawing['texts']:
        return ('info', 'Nothing to draw in this DXF', 'Lines, polylines, arcs, circles, ellipses, splines, '
                                                      'blocks and texts are read; hatches and dimensions are not.')
    previous = dict(previous or {})
    same_file = os.path.normcase(str(previous.get('file') or '')) == os.path.normcase(path)
    layer_names = sorted(drawing['layers'], key=lambda n: n.lower())
    texts_by_layer = {}
    for t in drawing['texts']:
        texts_by_layer[t['layer']] = texts_by_layer.get(t['layer'], 0) + 1
    for name in sorted(texts_by_layer, key=lambda n: n.lower()):
        if name not in layer_names:
            layer_names.append(name)
    chosen_layers = None
    if len(layer_names) > 1:
        rows = [{'value': name, 'cells': [name, drawing['layers'].get(name, 0), texts_by_layer.get(name, 0)]}
                for name in layer_names]
        remembered = previous.get('layers') if same_file and previous.get('layers') else layer_names
        picked = ui.choose('Sheet Overlay: layers', rows, ['Layer', 'Lines', 'Texts'], checked=remembered,
                           ok='Next', prompt='%s. Untick layers you do not need, such as hatching '
                                             'or dimensions.' % dxf_summary(drawing))
        if picked is None:
            return None
        chosen_layers = picked if len(picked) < len(layer_names) else None
    from namo import levels, progress
    known = levels.cached_or_none(document)
    if known is None:
        known = progress.run('Sheet Overlay', lambda report: levels.find(document, report), 'Looking for levels')
        if known is progress.CANCELLED:
            return None
    options, found = level_options(document, units, known)
    values = ui.form('Sheet Overlay', placement_fields(drawing, previous, options, units),
                     intro=os.path.basename(path), ok='Place', width=500, validate=validator(units))
    if values is None:
        return None
    placement = {'file': path, 'layers': chosen_layers, 'texts': bool(values['texts']), 'mode': values['mode'],
                 'units_choice': values['units_choice'], 'elevation_choice': values['elevation_choice'],
                 'p1': values.get('p1') or '', 'p2': values.get('p2') or '',
                 'point_scale': values.get('point_scale') or 'units', 'level': None}
    if values['elevation_choice'] == 'typed':
        placement['elevation'] = vp_common.signed_length(values['elevation'], units)
    else:
        name = values['elevation_choice'][len('level:'):]
        for lv in found:
            if lv['name'] == name:
                placement['elevation'] = lv['elevation']
                placement['level'] = lv['name']
        if placement.get('elevation') is None:
            placement['elevation'] = 0.0
    drawing_units = drawing_units_of(values, drawing, units)
    placement['units'] = drawing_units
    scale = unit_scale(drawing_units, units)
    if values['mode'] == 'manual':
        placement.update({'scale': scale, 'rotation': float(values.get('rotation') or 0.0),
                          'dx': vp_common.signed_length(values['dx'], units) or 0.0,
                          'dy': vp_common.signed_length(values['dy'], units) or 0.0})
    else:
        p1, p2 = parse_xy(values['p1']), parse_xy(values['p2'])
        picked = _pick_model_points(values['p1'], values['p2'], document)
        if picked is None:
            return None                         # Esc, right-click or another tool: say nothing
        q1, q2 = picked
        fixed = scale if placement['point_scale'] == 'units' else None
        try:
            s, rotation, dx, dy = from_points(p1, p2, q1, q2, fixed)
        except ValueError as error:
            return ('error', 'Could not place the sheet', str(error))
        placement.update({'scale': s, 'rotation': rotation, 'dx': dx, 'dy': dy})
        if fixed is None and scale:
            placement['scale_note'] = 'The points give %.4f times the %s scale.' % (s / scale, drawing_units.lower())
    try:
        save(document, placement)
    except (IOError, OSError) as error:
        from namo import session
        session.log('warning', 'Sheet Overlay placement not saved: %s' % error)
    return show(document, placement, drawing)


def dxf_summary(drawing):
    from namo import dxf
    return dxf.summary(drawing)


def _overlay_redraw():
    """Redraws the overlay through namo.overlayfix, so labels land on their points."""
    from namo import overlayfix
    return overlayfix.redraw()
