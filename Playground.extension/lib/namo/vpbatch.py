# -*- coding: utf-8 -*-
"""Batch Viewpoints: saved viewpoints generated per level, per grid intersection,
per selection or search set, or per model.

Every viewpoint is built DETACHED (a CreateCopy of the user's current view, so it
keeps their lighting and render style), cut and aimed there, and filed with
vp_common.add_view inside ONE viewpoints.transaction: the whole batch is one undo
step and the user's view is never touched, except by the "hide everything else"
option, which has to show the hidden state to capture it
(SavedViewpoints.CaptureRuntimeOverrides) and is wrapped in images.ViewKeeper so
the camera comes back afterwards.

Grid intersections are not listed by the API (GridLine has a name only), so they
are found by asking GridLevel.ClosestIntersection over a lattice of points across
the model, then completed from the grid lines those answers reveal: every pair of
lines that cross inside the model box is asked once more at its crossing point.

Pure half first (tested on both engines), API half after.
"""
import math

GENERATORS = [
    ('level', 'Per level'),
    ('grid', 'Per grid intersection'),
    ('set', 'Per selection or search set'),
    ('model', 'Per model'),
]

POLICIES = [('Replace it', 'replace'), ('Keep both', 'keep'), ('Skip it', 'skip')]     # (label, value)

AXES = [                                                                             # (label, value)
    ('Along the first grid line', 'line1'),
    ('Along the second grid line', 'line2'),
    ('North (+Y)', 'north'),
    ('East (+X)', 'east'),
    ('South (-Y)', 'south'),
    ('West (-X)', 'west'),
]

DEFAULTS = {
    'generator': 'level',
    'level_view': 'plan', 'cut_height_m': 1.2, 'eye_height_m': 1.6,
    'slab': True, 'slab_depth_m': 0.5, 'level_frame': 'level',
    'grid_view': 'plan', 'grid_size_m': 12.0, 'grid_axis': 'line1', 'grid_spacing_m': 2.0,
    'zoom_margin': 10, 'hide_others': False, 'keep_section': True,
    'folder_level': 'Batch/Levels', 'name_level': '{level}',
    'folder_grid': 'Batch/Grids/{level}', 'name_grid': '{grid}',
    'folder_set': 'Batch/Sets', 'name_set': '{set}',
    'folder_model': 'Batch/Models', 'name_model': '{model}',
    'policy': 'replace', 'comment': True,
}

MAX_LATTICE = 6000
NAME_TOKENS = {
    'level': '{level} {elevation} {n} {date} {file}',
    'grid': '{grid} {line1} {line2} {level} {n} {date}',
    'set': '{set} {set_folder} {n} {date} {file}',
    'model': '{model} {n} {date} {file}',
}


# ---- pure: settings -------------------------------------------------------------------


def settings(stored):
    """DEFAULTS overlaid with stored values (unknown keys dropped, bad values reset)."""
    out = dict(DEFAULTS)
    for key in DEFAULTS:
        if stored and key in stored and stored[key] is not None:
            out[key] = stored[key]
    for key in ('cut_height_m', 'eye_height_m', 'slab_depth_m', 'grid_size_m', 'grid_spacing_m'):
        try:
            out[key] = abs(float(out[key]))
        except (TypeError, ValueError):
            out[key] = DEFAULTS[key]
    try:
        out['zoom_margin'] = max(0, min(200, int(out['zoom_margin'])))
    except (TypeError, ValueError):
        out['zoom_margin'] = DEFAULTS['zoom_margin']
    if out['generator'] not in [g for g, _l in GENERATORS]:
        out['generator'] = 'level'
    if out['policy'] not in [p for _l, p in POLICIES]:
        out['policy'] = 'replace'
    if out['grid_axis'] not in [a for _l, a in AXES]:
        out['grid_axis'] = 'line1'
    for key in ('level_view', 'grid_view'):
        if out[key] not in ('plan', 'eye'):
            out[key] = 'plan'
    if out['level_frame'] not in ('level', 'model'):
        out['level_frame'] = 'level'
    for key in ('slab', 'hide_others', 'keep_section', 'comment'):
        out[key] = bool(out[key])
    return out


def fields_for(generator, cfg, doc_units, level_options=None):
    """The ui.form fields for one generator, filled from cfg (lengths in metres
    turned into document units)."""
    k = 1.0 / _to_m(doc_units)
    fields = []
    if generator == 'level':
        fields += [
            {'kind': 'radio', 'key': 'level_view', 'label': 'View',
             'options': [('Plan: top down, orthographic', 'plan'), ('Eye level: perspective', 'eye')],
             'default': cfg['level_view'], 'fallback': None},
            {'kind': 'length', 'key': 'cut_height', 'label': 'Cut height above the level',
             'default': cfg['cut_height_m'] * k, 'min': 0.0, 'enabled_if': ('level_view', 'plan')},
            {'kind': 'length', 'key': 'eye_height', 'label': 'Eye height above the level',
             'default': cfg['eye_height_m'] * k, 'min': 0.0, 'enabled_if': ('level_view', 'eye')},
            {'kind': 'check', 'key': 'slab', 'label': 'Hide the floors below', 'default': cfg['slab']},
            {'kind': 'length', 'key': 'slab_depth', 'label': 'Keep this much below the level',
             'default': cfg['slab_depth_m'] * k, 'min': 0.0, 'enabled_if': ('slab', True)},
            {'kind': 'radio', 'key': 'level_frame', 'label': 'Frame each view on',
             'options': [('What stands on that level', 'level'), ('The whole model', 'model')],
             'default': cfg['level_frame'], 'fallback': None, 'inline': True},
        ]
    elif generator == 'grid':
        fields += [
            {'kind': 'choice', 'key': 'grid_level', 'label': 'Level',
             'options': level_options or [], 'default': level_options[0][1] if level_options else None},
            {'kind': 'radio', 'key': 'grid_view', 'label': 'View',
             'options': [('Plan zoomed on the intersection', 'plan'), ('Eye level at the intersection', 'eye')],
             'default': cfg['grid_view'], 'fallback': None},
            {'kind': 'length', 'key': 'grid_size', 'label': 'Plan width around the intersection',
             'default': cfg['grid_size_m'] * k, 'min': 0.0, 'enabled_if': ('grid_view', 'plan')},
            {'kind': 'length', 'key': 'cut_height', 'label': 'Cut height above the level',
             'default': cfg['cut_height_m'] * k, 'min': 0.0, 'enabled_if': ('grid_view', 'plan')},
            {'kind': 'length', 'key': 'eye_height', 'label': 'Eye height above the level',
             'default': cfg['eye_height_m'] * k, 'min': 0.0, 'enabled_if': ('grid_view', 'eye')},
            {'kind': 'choice', 'key': 'grid_axis', 'label': 'Look', 'options': AXES,
             'default': cfg['grid_axis'], 'fallback': None, 'enabled_if': ('grid_view', 'eye')},
            {'kind': 'check', 'key': 'slab', 'label': 'Hide the floors below', 'default': cfg['slab']},
            {'kind': 'length', 'key': 'grid_spacing', 'label': 'Search step',
             'default': cfg['grid_spacing_m'] * k, 'min': 0.0,
             'hint': 'Intersections are found by sampling the model this often. Smaller finds '
                     'tighter grids and takes longer.'},
        ]
    else:
        fields += [
            {'kind': 'int', 'key': 'zoom_margin', 'label': 'Margin around each zoom', 'suffix': '%',
             'min': 0, 'max': 200, 'default': cfg['zoom_margin']},
            {'kind': 'check', 'key': 'hide_others', 'label': 'Hide everything else in each view',
             'default': cfg['hide_others'],
             'hint': 'The hidden state is stored in the viewpoint and put back afterwards.'},
            {'kind': 'check', 'key': 'keep_section', 'label': 'Keep the current section planes',
             'default': cfg['keep_section']},
        ]
    fields += [
        {'kind': 'separator'},
        {'kind': 'text', 'key': 'folder', 'label': 'Folder', 'default': cfg['folder_' + generator],
         'hint': 'Use / for subfolders. Tokens: %s' % NAME_TOKENS[generator]},
        {'kind': 'text', 'key': 'name', 'label': 'Viewpoint name', 'default': cfg['name_' + generator],
         'required': True},
        {'kind': 'radio', 'key': 'policy', 'label': 'When a viewpoint with that name exists',
         'options': POLICIES, 'default': cfg['policy'], 'fallback': None, 'inline': True},
        {'kind': 'check', 'key': 'comment', 'label': 'Add a comment saying how each view was made',
         'default': cfg['comment']},
    ]
    return fields


def update_settings(cfg, generator, values, doc_units):
    """cfg with the form's values folded in (lengths back to metres)."""
    out = dict(cfg)
    m = _to_m(doc_units)
    out['generator'] = generator
    for key in ('cut_height', 'eye_height', 'slab_depth', 'grid_size', 'grid_spacing'):
        if key in values and values[key] is not None:
            out[key + '_m'] = float(values[key]) * m
    for key in ('level_view', 'grid_view', 'grid_axis', 'slab', 'level_frame', 'zoom_margin',
                'hide_others', 'keep_section', 'policy', 'comment'):
        if key in values and values[key] is not None:
            out[key] = values[key]
    if 'folder' in values:
        out['folder_' + generator] = values['folder'] or ''
    if values.get('name'):
        out['name_' + generator] = values['name']
    return settings(out)


def _to_m(doc_units):
    from namo import vp_common
    return vp_common.to_meters_factor(doc_units)


# ---- pure: names ---------------------------------------------------------------------


def _folder_safe(value):
    return str(value).replace('/', '-').replace('\\', '-')


def render_jobs(entries, folder_template, name_template, standard=None):
    """[(folder, name)] for entries (each a dict of token values), numbered from 1.
    A '/' inside a token value never splits a folder; an empty name falls back to
    the entry's 'fallback' (or 'View {n}')."""
    from namo import naming
    base = dict(standard or {})
    out = []
    for index, values in enumerate(entries):
        tokens = dict(base)
        tokens.update(values)
        tokens['n'] = index + 1
        folder_tokens = dict((k, _folder_safe(v) if isinstance(v, str) else v) for k, v in tokens.items())
        folder, _missing = naming.render(folder_template or '', folder_tokens)
        parts = [naming.sanitize(p) for p in folder.replace('\\', '/').split('/')]
        folder = '/'.join(p for p in parts if p)
        name, _missing = naming.render(name_template or '', tokens)
        name = naming.sanitize(name)
        if not name:
            name = naming.sanitize(values.get('fallback') or 'View %d' % (index + 1))
        out.append((folder, name))
    return out


def comment_text(kind, values, cfg, doc_units, when=None, user=None):
    """The provenance comment put on each generated view."""
    from namo import vp_common
    k = 1.0 / _to_m(doc_units)
    parts = []
    if kind == 'level':
        elevation = vp_common.length_text(values.get('elevation_value', 0.0), doc_units)
        if cfg['level_view'] == 'plan':
            parts.append('Plan of %s (%s), cut %s above.' % (
                values.get('level'), elevation, vp_common.length_text(cfg['cut_height_m'] * k, doc_units)))
        else:
            parts.append('Eye level view of %s (%s), eye %s above.' % (
                values.get('level'), elevation, vp_common.length_text(cfg['eye_height_m'] * k, doc_units)))
    elif kind == 'grid':
        parts.append('Grid intersection %s on %s.' % (values.get('grid'), values.get('level')))
    elif kind == 'set':
        parts.append('Zoomed to the set %s.' % values.get('set'))
    else:
        parts.append('Zoomed to the model %s.' % values.get('model'))
    if values.get('approximate'):
        parts.append('Level elevation estimated from the objects.')
    stamp = []
    if when:
        stamp.append(str(when))
    if user:
        stamp.append('by %s' % user)
    parts.append('Made by Batch Viewpoints%s.' % ((' ' + ' '.join(stamp)) if stamp else ''))
    return ' '.join(parts)


# ---- pure: grid intersections ------------------------------------------------------


def lattice(box, spacing, max_points=MAX_LATTICE):
    """(points [(x, y)], step used) covering box ((x0, y0, ...), (x1, y1, ...)) every
    `spacing`, the step grown when more than max_points would be needed. Points sit
    in the middle of their cells."""
    (x0, y0) = box[0][0], box[0][1]
    (x1, y1) = box[1][0], box[1][1]
    w, h = max(x1 - x0, 1e-9), max(y1 - y0, 1e-9)
    step = float(spacing) if spacing and spacing > 0 else max(w, h) / 20.0
    while (math.ceil(w / step) * math.ceil(h / step)) > max_points:
        step *= 1.25
    nx, ny = int(math.ceil(w / step)), int(math.ceil(h / step))
    points = []
    for j in range(ny):
        for i in range(nx):
            points.append((x0 + (i + 0.5) * w / nx, y0 + (j + 0.5) * h / ny))
    return points, step


def pair_key(line1, line2):
    """Order-free key of two grid line names."""
    a, b = str(line1), str(line2)
    return (a, b) if a <= b else (b, a)


def lines_from(found):
    """{line name: ((x, y), (dx, dy))} from found intersections
    [{'line1', 'line2', 'position', 'dir1', 'dir2'}]: each line's direction and one
    point on it (directions are made horizontal and unit length; vertical or zero
    directions are skipped)."""
    lines = {}
    for record in found:
        for name_key, dir_key in (('line1', 'dir1'), ('line2', 'dir2')):
            name = record.get(name_key)
            direction = record.get(dir_key)
            if not name or direction is None or name in lines:
                continue
            dx, dy = float(direction[0]), float(direction[1])
            size = math.hypot(dx, dy)
            if size < 1e-9:
                continue
            p = record['position']
            lines[name] = ((float(p[0]), float(p[1])), (dx / size, dy / size))
    return lines


def crossing(line_a, line_b, min_angle_deg=5.0):
    """(x, y) where two lines given as ((x, y), (dx, dy)) cross, or None when they
    are (nearly) parallel."""
    (px, py), (ux, uy) = line_a
    (qx, qy), (vx, vy) = line_b
    det = ux * vy - uy * vx
    if abs(det) < math.sin(math.radians(min_angle_deg)):
        return None
    t = ((qx - px) * vy - (qy - py) * vx) / det
    return (px + t * ux, py + t * uy)


def candidates(lines, box, known_pairs, grow=0.05):
    """[(line1, line2, (x, y))] crossings of every non-parallel pair of lines inside
    box (grown by `grow` of its size), skipping pairs already found. Sorted by name."""
    (x0, y0) = box[0][0], box[0][1]
    (x1, y1) = box[1][0], box[1][1]
    gx, gy = (x1 - x0) * grow, (y1 - y0) * grow
    names = sorted(lines)
    out = []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if pair_key(a, b) in known_pairs:
                continue
            point = crossing(lines[a], lines[b])
            if point is None:
                continue
            if x0 - gx <= point[0] <= x1 + gx and y0 - gy <= point[1] <= y1 + gy:
                out.append((a, b, point))
    return out


def sort_intersections(found):
    """Found intersections in natural order of their names."""
    from namo import naming
    return sorted(found, key=lambda r: (naming.natural_key(r['name']), r['position'][0], r['position'][1]))


def look_direction(axis, dir1=None, dir2=None):
    """Horizontal unit (dx, dy, 0) for an AXES value; the line directions for
    'line1' / 'line2' (north when unknown)."""
    fixed = {'north': (0.0, 1.0), 'east': (1.0, 0.0), 'south': (0.0, -1.0), 'west': (-1.0, 0.0)}
    if axis in fixed:
        x, y = fixed[axis]
        return (x, y, 0.0)
    direction = dir1 if axis == 'line1' else dir2
    if direction is not None:
        x, y = float(direction[0]), float(direction[1])
        size = math.hypot(x, y)
        if size > 1e-9:
            return (x / size, y / size, 0.0)
    return (0.0, 1.0, 0.0)


def eye_camera(eye, direction, fov_deg=60.0, focal=None):
    """A perspective camera dict at eye looking along direction (Z up)."""
    from namo import camera
    return camera.make_cam(eye, direction=direction, up=(0.0, 0.0, 1.0), projection='persp',
                           height_field=camera.height_field_for(fov_deg), focal_distance=focal)


def corner_eye(box, z, inset=0.08):
    """(eye, direction) for an eye-level view across a floor: standing in from the
    south-west corner of box by `inset` of its size, looking at its centre."""
    (x0, y0, _z0), (x1, y1, _z1) = box
    ex, ey = x0 + (x1 - x0) * inset, y0 + (y1 - y0) * inset
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    dx, dy = cx - ex, cy - ey
    size = math.hypot(dx, dy)
    if size < 1e-9:
        return (ex, ey, z), (0.0, 1.0, 0.0), 1.0
    return (ex, ey, z), (dx / size, dy / size, 0.0), size


def grown(box, fraction):
    """box grown by fraction of its size on every side (a flat side by the largest)."""
    (x0, y0, z0), (x1, y1, z1) = box
    span = max(x1 - x0, y1 - y0, z1 - z0, 1e-9)
    pads = [max(x1 - x0, span * 0.05) * fraction, max(y1 - y0, span * 0.05) * fraction,
            max(z1 - z0, span * 0.05) * fraction]
    return ((x0 - pads[0], y0 - pads[1], z0 - pads[2]), (x1 + pads[0], y1 + pads[1], z1 + pads[2]))


# ==== API half ======================================================================


def grid_level_object(document, name):
    """The GridLevel of the active grid system named name, or None."""
    try:
        system = document.Grids.ActiveSystem
        if system is None and document.Grids.Systems.Count > 0:
            system = document.Grids.Systems[0]
        for lv in system.Levels:
            if str(lv.DisplayName) == name:
                return lv
    except Exception:
        return None
    return None


def _intersection_record(hit):
    def vec(v):
        return (float(v.X), float(v.Y), float(v.Z))
    record = {'name': str(hit.DisplayName), 'position': vec(hit.Position), 'line1': '', 'line2': '',
              'dir1': None, 'dir2': None}
    try:
        record['line1'] = str(hit.Line1.DisplayName)
        record['dir1'] = vec(hit.Line1Direction)
    except Exception:
        pass
    try:
        record['line2'] = str(hit.Line2.DisplayName)
        record['dir2'] = vec(hit.Line2Direction)
    except Exception:
        pass
    if not record['line1'] and not record['line2']:
        record['line1'] = record['name']
    return record


def find_intersections(document, grid_level, box, spacing, report=None):
    """Grid intersections on one GridLevel inside box (see the module docstring).
    Returns (sorted records, step used). Raises items.Cancelled on a cancel."""
    from pynavis._api import Api
    from namo import items, vp_common
    z = float(grid_level.Elevation)
    points, step = lattice(box, spacing)
    found = {}
    tol = max(step * 0.02, 1e-6)
    total = len(points)

    def ask(x, y):
        try:
            hit = grid_level.ClosestIntersection(Api.Point3D(float(x), float(y), z))
        except Exception:
            return None
        return _intersection_record(hit) if hit is not None else None

    for index, (x, y) in enumerate(points):
        if index % 100 == 0 and vp_common.report_step(
                report, 0.8 * index / max(1, total),
                'Finding grid intersections: %s of %s points' % (vp_common.count_text(index),
                                                                 vp_common.count_text(total))):
            raise items.Cancelled()
        record = ask(x, y)
        if record is not None:
            found.setdefault(pair_key(record['line1'], record['line2']), record)
    lines = lines_from(found.values())
    extra = candidates(lines, box, set(found))
    for index, (a, b, point) in enumerate(extra):
        if index % 50 == 0 and vp_common.report_step(
                report, 0.8 + 0.2 * index / max(1, len(extra)), 'Checking grid line crossings'):
            raise items.Cancelled()
        record = ask(point[0], point[1])
        if record is None:
            continue
        key = pair_key(record['line1'], record['line2'])
        if key in found:
            continue
        if math.hypot(record['position'][0] - point[0], record['position'][1] - point[1]) <= max(tol, step):
            found[key] = record
    return sort_intersections(list(found.values())), step


def selection_sets(document):
    """[{'name', 'folder', 'item'}] of every selection and search set, tree order."""
    from pynavis._api import Api
    out = []

    def walk(children, folder):
        for child in children:
            try:
                is_folder = isinstance(child, Api.FolderItem)
            except Exception:
                is_folder = False
            if is_folder:
                walk(child.Children, (folder + '/' + child.DisplayName) if folder else child.DisplayName)
            else:
                out.append({'name': str(child.DisplayName), 'folder': folder, 'item': child})
    try:
        walk(document.SelectionSets.RootItem.Children, '')
    except Exception:
        return []
    return out


def set_items(document, entry):
    from pynavis import sets
    try:
        return list(sets.items_of(entry['item'], document))
    except Exception:
        return []


def storey_height(level_list, doc_units):
    """The typical gap between levels (median), else 4 m in document units."""
    gaps = sorted(b['elevation'] - a['elevation'] for a, b in zip(level_list, level_list[1:])
                  if b['elevation'] > a['elevation'])
    if gaps:
        return gaps[len(gaps) // 2]
    return 4.0 / _to_m(doc_units)


def _next_top(level_list, lv, doc_units):
    """Where an eye-level view's top plane goes: just under the next level up."""
    k = 1.0 / _to_m(doc_units)
    above = [x['elevation'] for x in level_list if x['elevation'] > lv['elevation']]
    if above:
        return min(above) - 0.05 * k
    return lv['elevation'] + storey_height(level_list, doc_units) - 0.05 * k


def _standard(document):
    from namo import naming
    try:
        return naming.standard_values(document)
    except Exception:
        return {}


def level_jobs(document, level_list, chosen, cfg, report=None):
    """Jobs for the chosen levels (see run). Frames come from levels.band_boxes
    (sampled flag returned) or the model box. Returns (jobs, sampled)."""
    from namo import camera, items, levels, vp_common
    units = str(document.Units)
    k = 1.0 / _to_m(units)
    whole = levels.model_box(document)
    sampled = False
    frames = [whole] * len(level_list)
    if cfg['level_frame'] == 'level' and whole is not None:
        vp_common.report_step(report, 0.0, 'Measuring what stands on each level')
        frames, sampled = levels.band_boxes(items.roots(document), lambda n: n.Children, levels._box,
                                            level_list, storey_height(level_list, units))
        frames = [f if f is not None else whole for f in frames]
    base = document.CurrentViewpoint.CreateCopy()
    standard = _standard(document)
    wanted = set(x['name'] for x in chosen)
    position = dict((lv['name'], i) for i, lv in enumerate(level_list))
    picked = [lv for lv in level_list if lv['name'] in wanted]
    entries = []
    for lv in picked:
        entries.append({'level': lv['name'], 'elevation': vp_common.length_text(lv['elevation'], units),
                        'fallback': lv['name']})
    names = render_jobs(entries, cfg['folder_level'], cfg['name_level'], standard)
    jobs = []
    lvcfg = {'cut_height_m': cfg['cut_height_m'], 'slab': cfg['slab'],
             'slab_depth_m': cfg['slab_depth_m'], 'plan': True}
    for lv, (folder, name) in zip(picked, names):
        frame = frames[position[lv['name']]]

        def build(lv=lv, frame=frame):
            if cfg['level_view'] == 'plan':
                return levels.level_viewpoint(document, lv, lvcfg, base=base, plan=True, box=frame)
            viewpoint = base.CreateCopy()
            top = _next_top(level_list, lv, units) - lv['elevation']
            center = ((whole[0][0] + whole[1][0]) / 2.0, (whole[0][1] + whole[1][1]) / 2.0) if whole else (0, 0)
            vp_common.set_planes(viewpoint, levels.cut_planes(lv['elevation'], top, cfg['slab'],
                                                               cfg['slab_depth_m'] * k, center), whole)
            box = frame or ((0.0, 0.0, 0.0), (1.0, 1.0, 1.0))
            eye, direction, distance = corner_eye(box, lv['elevation'] + cfg['eye_height_m'] * k)
            return camera.to_viewpoint(eye_camera(eye, direction, 60.0, distance), base=viewpoint)
        values = {'level': lv['name'], 'elevation_value': lv['elevation'], 'approximate': lv.get('approximate')}
        jobs.append({'folder': folder, 'name': name, 'build': build, 'keep': None,
                     'comment': comment_text('level', values, cfg, units, standard.get('date'),
                                             standard.get('user')) if cfg['comment'] else None})
    return jobs, sampled


def grid_jobs(document, level_list, lv, found, cfg):
    """Jobs for chosen intersections on level lv."""
    from pynavis._api import Api
    from namo import camera, levels, vp_common
    units = str(document.Units)
    k = 1.0 / _to_m(units)
    whole = levels.model_box(document)
    base = document.CurrentViewpoint.CreateCopy()
    standard = _standard(document)
    entries = [{'grid': r['name'], 'line1': r['line1'], 'line2': r['line2'], 'level': lv['name'],
                'fallback': r['name']} for r in found]
    names = render_jobs(entries, cfg['folder_grid'], cfg['name_grid'], standard)
    center = ((whole[0][0] + whole[1][0]) / 2.0, (whole[0][1] + whole[1][1]) / 2.0) if whole else (0, 0)
    jobs = []
    for record, (folder, name) in zip(found, names):
        def build(record=record):
            viewpoint = base.CreateCopy()
            x, y = record['position'][0], record['position'][1]
            z = lv['elevation']
            if cfg['grid_view'] == 'plan':
                cut = cfg['cut_height_m'] * k
                vp_common.set_planes(viewpoint, levels.cut_planes(z, cut, cfg['slab'],
                                                                   cfg['slab_depth_m'] * k, center), whole)
                half = max(cfg['grid_size_m'] * k / 2.0, 1e-6)
                box = ((x - half, y - half, z), (x + half, y + half, z + cut))
                aspect = None
                try:
                    aspect = float(viewpoint.AspectRatio) or None
                except Exception:
                    pass
                viewpoint = camera.to_viewpoint(levels.plan_camera(box, z, z + cut, aspect), base=viewpoint)
                try:
                    viewpoint.ZoomBox(Api.BoundingBox3D(Api.Point3D(*box[0]), Api.Point3D(*box[1])))
                except Exception:
                    pass
                return viewpoint
            top = _next_top(level_list, lv, units) - z
            vp_common.set_planes(viewpoint, levels.cut_planes(z, top, cfg['slab'],
                                                               cfg['slab_depth_m'] * k, center), whole)
            direction = look_direction(cfg['grid_axis'], record.get('dir1'), record.get('dir2'))
            eye = (x, y, z + cfg['eye_height_m'] * k)
            return camera.to_viewpoint(eye_camera(eye, direction, 60.0, 10.0 * k), base=viewpoint)
        values = {'grid': record['name'], 'level': lv['name']}
        jobs.append({'folder': folder, 'name': name, 'build': build, 'keep': None,
                     'comment': comment_text('grid', values, cfg, units, standard.get('date'),
                                             standard.get('user')) if cfg['comment'] else None})
    return jobs


def zoom_jobs(document, targets, kind, cfg):
    """Jobs for sets (kind 'set') or models (kind 'model'). targets:
    [{'name', 'folder' (sets), 'items' [ModelItem]}]; empty targets are skipped
    by the caller."""
    from pynavis._api import Api
    from namo import items
    units = str(document.Units)
    base = document.CurrentViewpoint.CreateCopy()
    standard = _standard(document)
    if kind == 'set':
        entries = [{'set': t['name'], 'set_folder': t.get('folder') or '', 'fallback': t['name']} for t in targets]
        names = render_jobs(entries, cfg['folder_set'], cfg['name_set'], standard)
    else:
        entries = [{'model': t['name'], 'fallback': t['name']} for t in targets]
        names = render_jobs(entries, cfg['folder_model'], cfg['name_model'], standard)
    jobs = []
    for target, (folder, name) in zip(targets, names):
        def build(target=target):
            viewpoint = base.CreateCopy()
            if not cfg['keep_section']:
                viewpoint.ClipPlanes.Enabled = False
            box = items.bbox(items.collection(target['items']))
            if box is not None:
                low, high = grown(box, cfg['zoom_margin'] / 100.0)
                viewpoint.ZoomBox(Api.BoundingBox3D(Api.Point3D(*low), Api.Point3D(*high)))
            return viewpoint
        values = {kind: target['name']}
        jobs.append({'folder': folder, 'name': name, 'build': build,
                     'keep': target['items'] if cfg['hide_others'] else None,
                     'comment': comment_text(kind, values, cfg, units, standard.get('date'),
                                             standard.get('user')) if cfg['comment'] else None})
    return jobs


def _hide_and_capture(document, viewpoint, keep):
    """Shows viewpoint with everything but keep hidden, captures it with the hidden
    state (CaptureRuntimeOverrides) and puts the hidden flags back. Returns
    (SavedViewpoint, visibility stored)."""
    from namo import items
    others = [i for i in items.complement(keep, document) if not i.IsHidden]
    coll = items.collection(others)
    document.CurrentViewpoint.CopyFrom(viewpoint)
    if coll.Count:
        document.Models.SetHidden(coll, True)
    try:
        snapshot = document.SavedViewpoints.CaptureRuntimeOverrides()
        try:
            stored = bool(snapshot.ContainsVisibilityOverrides)
        except Exception:
            stored = False
    finally:
        if coll.Count:
            document.Models.SetHidden(coll, False)
    return snapshot, stored


def run(document, jobs, cfg, report=None):
    """Files every job {'folder', 'name', 'build' (-> detached Viewpoint), 'keep'
    (items to keep visible, or None), 'comment'} in one transaction. Returns
    {'created', 'replaced', 'skipped', 'failed' [(name, error)], 'stopped', 'total',
    'hidden_lost', 'folders'}."""
    from pynavis.viewpoints import transaction
    from namo import images, session, vp_common
    out = {'created': 0, 'replaced': 0, 'skipped': 0, 'failed': [], 'stopped': False,
           'total': len(jobs), 'hidden_lost': 0, 'folders': []}
    hides = any(job.get('keep') is not None for job in jobs)
    with transaction('Batch viewpoints', document):
        # restore_saved=False: nothing here recalls a saved view, and re-applying the
        # one that was current would reset what the user hid by hand since.
        keeper = images.ViewKeeper(document, restore_saved=False) if hides else None
        if keeper is not None:
            keeper.__enter__()
        try:
            for index, job in enumerate(jobs):
                if vp_common.report_step(report, float(index) / max(1, len(jobs)),
                                         'Saving %s (%d of %d)' % (job['name'], index + 1, len(jobs))):
                    out['stopped'] = True
                    break
                try:
                    viewpoint = job['build']()
                    comments = [job['comment']] if job.get('comment') else None
                    if job.get('keep') is not None:
                        snapshot, stored = _hide_and_capture(document, viewpoint, job['keep'])
                        if not stored:
                            out['hidden_lost'] += 1
                        _live, outcome = vp_common.add_view(document, job['folder'], job['name'],
                                                            saved_item=snapshot, comments=comments,
                                                            policy=cfg['policy'])
                    else:
                        _live, outcome = vp_common.add_view(document, job['folder'], job['name'],
                                                            viewpoint=viewpoint, comments=comments,
                                                            policy=cfg['policy'])
                    out[outcome] += 1
                    if job['folder'] not in out['folders']:
                        out['folders'].append(job['folder'])
                except Exception as error:
                    if vp_common.is_cancel(error):
                        out['stopped'] = True
                        break
                    session.log('warning', 'Batch Viewpoints: %s failed: %s' % (job['name'], error))
                    out['failed'].append((job['name'], str(error)))
        finally:
            if keeper is not None:
                keeper.__exit__(None, None, None)
    return out


def summary(result):
    """(level, message, detail) for the toast."""
    from namo import vp_common
    saved = result['created'] + result['replaced']
    folders = [vp_common.folder_label(f) for f in result['folders']]
    where = ''
    if len(folders) == 1:
        where = 'In %s. ' % folders[0]
    elif folders:
        where = 'In %s. ' % vp_common.plural(len(folders), 'folder')
    notes = []
    if result['replaced']:
        notes.append('%s replaced' % vp_common.count_text(result['replaced']))
    if result['skipped']:
        notes.append('%s skipped (name taken)' % vp_common.count_text(result['skipped']))
    noted = (' (%s)' % ', '.join(notes)) if notes else ''
    if result['stopped']:
        return ('warning', 'Stopped after %s of %s' % (vp_common.count_text(saved), vp_common.plural(result['total'], 'viewpoint')),
                where + 'Ctrl+Z removes the ones that were saved.')
    if result['failed'] and not saved:
        return ('error', 'Could not save the viewpoints', '%s: %s' % result['failed'][0])
    if result['failed']:
        return ('warning', 'Saved %s, %s failed%s' % (vp_common.plural(saved, 'viewpoint'),
                                                      vp_common.count_text(len(result['failed'])), noted),
                '%s: %s' % result['failed'][0])
    if result['hidden_lost']:
        return ('warning', 'Saved %s%s' % (vp_common.plural(saved, 'viewpoint'), noted),
                'Navisworks did not store the hidden items in %s. Turn on Save Hide/Required '
                'Attributes in Options, Interface, Viewpoint Defaults, then run it again.'
                % vp_common.plural(result['hidden_lost'], 'view'))
    if not saved:
        return ('info', 'No viewpoints saved', where + 'Every name was already taken and Skip was chosen.')
    return ('success', 'Saved %s%s' % (vp_common.plural(saved, 'viewpoint'), noted),
            where + 'One Ctrl+Z removes them all.')
