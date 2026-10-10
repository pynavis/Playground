# -*- coding: utf-8 -*-
"""Levels of the model, and sectioning the view at one of them.

Where levels come from, best first:
  1. the active grid system (Document.Grids.ActiveSystem.Levels: name + exact
     elevation, the levels Navisworks' own Grids and Levels show);
  2. IFC storeys in the model tree (nodes whose class name says storey) with
     elevations estimated from the bottoms of the objects under them;
  3. a Revit level property on the objects (Element > Level, Base Constraint,
     Reference Level, Schedule Level), grouped by value, elevations estimated the
     same way.
Estimated elevations are marked approximate everywhere they are shown: they are the
most common object bottom on that level (walls, columns, doors and furniture start
at their level; a slab's underside sits a slab below it, so the mode wins).

Sectioning writes ONE detached viewpoint back with one CurrentViewpoint.CopyFrom
(one undo step): plane 1 at level + cut height keeps what is below, plane 2 (the
optional slab view) at level - depth keeps what is above, other planes off; with
'plan' the camera also turns to a top-down orthographic view framed on the model
(Viewpoint.ZoomBox along the new direction).

Settings shared by Level Sectioner, Level Up and Level Down live in
pynavis.settings under TOOL (lengths stored in METRES so they survive unit
changes). The current level per document is kept in a session holder and in the
document store 'level-sectioner'.
"""
import math

TOOL = 'playground_levels'
DEFAULTS = {'cut_height_m': 1.2, 'slab': False, 'slab_depth_m': 0.5, 'plan': False}

LEVEL_PROPERTIES = [
    ('Element', 'Level'),
    ('Element', 'Base Constraint'),
    ('Element', 'Reference Level'),
    ('Element', 'Schedule Level'),
    ('Constraints', 'Level'),
    ('Constraints', 'Base Constraint'),
]
STOREY_WORDS = ('storey', 'story')

SCAN_BUDGET = 12000         # objects read by the property scan, spread over the tree
TREE_NODE_BUDGET = 4000     # nodes looked at when searching the tree for storeys
TREE_DEPTH = 6
BIN_METERS = 0.05           # elevation histogram bin


# ---- pure ---------------------------------------------------------------------------


def settings_values(stored):
    """DEFAULTS overlaid with stored values, types made safe."""
    out = dict(DEFAULTS)
    for key in DEFAULTS:
        if stored and key in stored and stored[key] is not None:
            out[key] = stored[key]
    try:
        out['cut_height_m'] = float(out['cut_height_m'])
    except (TypeError, ValueError):
        out['cut_height_m'] = DEFAULTS['cut_height_m']
    try:
        out['slab_depth_m'] = abs(float(out['slab_depth_m']))
    except (TypeError, ValueError):
        out['slab_depth_m'] = DEFAULTS['slab_depth_m']
    out['slab'] = bool(out['slab'])
    out['plan'] = bool(out['plan'])
    return out


def settings_fields(cfg, doc_units):
    """The ui.form fields of Level Sectioner's Shift+Click settings (lengths shown in
    document units; cfg holds metres). The cut height is required: a blank one would
    reach the caller as None."""
    from namo import vp_common
    k = 1.0 / vp_common.to_meters_factor(doc_units)
    return [
        {'kind': 'length', 'key': 'cut', 'label': 'Cut height above the level', 'min': 0.0,
         'default': cfg['cut_height_m'] * k, 'required': True},
        {'kind': 'check', 'key': 'slab', 'label': 'Hide the floors below (slab view)', 'default': cfg['slab']},
        {'kind': 'length', 'key': 'depth', 'label': 'Keep this much below the level', 'min': 0.0,
         'default': cfg['slab_depth_m'] * k, 'enabled_if': ('slab', True)},
        {'kind': 'check', 'key': 'plan', 'label': 'Turn to a plan view framed on the model', 'default': cfg['plan']},
    ]


def level(name, elevation, source='grid', approximate=False, count=0):
    return {'name': str(name), 'elevation': float(elevation), 'source': source,
            'approximate': bool(approximate), 'count': int(count)}


def normalize(levels):
    """Levels sorted by elevation (then name, naturally); a name met twice keeps
    its first elevation; levels with no usable elevation dropped."""
    from namo import naming
    seen = set()
    out = []
    for lv in levels:
        try:
            z = float(lv['elevation'])
        except (TypeError, ValueError, KeyError):
            continue
        if z != z or z in (float('inf'), float('-inf')):
            continue
        key = str(lv['name']).strip().lower()
        if key in seen:
            continue
        seen.add(key)
        fresh = dict(lv)
        fresh['elevation'] = z
        out.append(fresh)
    out.sort(key=lambda lv: (lv['elevation'], naming.natural_key(lv['name'])))
    return out


def estimate_elevation(bottoms, bin_size):
    """The most common bottom height among `bottoms` (a histogram of `bin_size`
    bins; ties go to the LOWER bin), refined to the median of the values in that
    bin and its two neighbours. None for no values."""
    values = sorted(float(b) for b in bottoms if b is not None)
    if not values:
        return None
    size = float(bin_size) if bin_size and bin_size > 0 else 1.0
    counts = {}
    for v in values:
        b = int(math.floor(v / size))
        counts[b] = counts.get(b, 0) + 1
    best = min(counts, key=lambda b: (-counts[b], b))
    near = [v for v in values if best - 1 <= int(math.floor(v / size)) <= best + 1]
    near.sort()
    mid = len(near) // 2
    if len(near) % 2:
        return near[mid]
    return (near[mid - 1] + near[mid]) / 2.0


def index_at(levels, z, tolerance=1e-6):
    """Index of the level the height z stands on: the highest level at or below
    z (+ tolerance); 0 when z is below every level; None for no levels."""
    if not levels:
        return None
    found = 0
    for i, lv in enumerate(levels):
        if lv['elevation'] <= float(z) + tolerance:
            found = i
    return found


def index_of(levels, name):
    """Index of the level named name (exact, then case-insensitive), or None."""
    for i, lv in enumerate(levels):
        if lv['name'] == name:
            return i
    lowered = str(name or '').strip().lower()
    for i, lv in enumerate(levels):
        if lv['name'].strip().lower() == lowered:
            return i
    return None


def step_index(levels, current, direction):
    """(new index, moved) one level up (direction +1) or down (-1); moved False at
    the top or bottom. current None starts at the bottom (up) or top (down)."""
    if not levels:
        return None, False
    if current is None:
        return (0 if direction > 0 else len(levels) - 1), True
    target = current + (1 if direction > 0 else -1)
    if target < 0 or target >= len(levels):
        return current, False
    return target, True


def pick_current(levels, remembered_name, top_z, cut, eye_z):
    """Index of the level the user is on now, or None for no levels.

    A horizontal top plane that is switched on decides: the level under it (top_z
    minus the cut height). That keeps Level Up and Level Down honest after the plane
    was moved by hand or with pyNavis' Section Nudge. The remembered level only wins
    while the plane still sits where that level put it, or when there is no plane at
    all; with neither, the level under the eye."""
    if not levels:
        return None
    named = index_of(levels, remembered_name) if remembered_name is not None else None
    if top_z is not None:
        cut = abs(float(cut))
        slack = max(cut * 0.25, 1e-6 * max(1.0, abs(float(top_z))))
        if named is not None and abs(levels[named]['elevation'] + cut - float(top_z)) <= slack:
            return named
        return index_at(levels, float(top_z) - cut, tolerance=slack)
    if named is not None:
        return named
    if eye_z is not None:
        return index_at(levels, eye_z)
    return None


def cut_planes(elevation, cut_height, slab=False, slab_depth=0.0, center=(0.0, 0.0)):
    """[(origin, normal)] for a level cut (namo.camera.horizontal_planes): top at
    elevation + cut_height, and with slab a bottom plane at elevation - slab_depth."""
    from namo import camera
    top = float(elevation) + float(cut_height)
    bottom = (float(elevation) - abs(float(slab_depth))) if slab else None
    if bottom is not None and bottom >= top:
        bottom = top - abs(float(cut_height) or 1.0)
    return camera.horizontal_planes(top, bottom, center)


def plan_camera(box, elevation, top_z, aspect=None):
    """A top-down orthographic camera dict over the XY of box ((min), (max)),
    standing above top_z: looks straight down, north (+Y) up the screen."""
    from namo import camera
    (x0, y0, z0), (x1, y1, z1) = box
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    span = max(x1 - x0, y1 - y0, 1e-6)
    height = max(float(top_z), float(z1)) + span * 0.5
    ratio = float(aspect) if aspect else 16.0 / 9.0
    visible = max(y1 - y0, (x1 - x0) / ratio) * 1.08
    return camera.make_cam((cx, cy, height), direction=(0.0, 0.0, -1.0), up=(0.0, 1.0, 0.0),
                           projection='ortho', height_field=max(visible, 1e-6),
                           focal_distance=max(height - float(elevation), 1e-6), aspect=aspect)


def describe(lv, doc_units):
    """'Level 2 at 4.200 m' (+ ' (approximate)')."""
    from namo import vp_common
    text = '%s at %s' % (lv['name'], vp_common.length_text(lv['elevation'], doc_units))
    if lv.get('approximate'):
        text += ' (approximate)'
    return text


def source_note(levels):
    """One sentence on where the levels came from (for toasts)."""
    if not levels:
        return ''
    source = levels[0].get('source')
    if source == 'grid':
        return 'Levels from the active grid system.'
    if source == 'storey':
        return 'Levels from the IFC storeys; elevations estimated from the objects on them.'
    return 'Levels from the Level property of the objects; elevations estimated.'


def band_boxes(roots, children_of, box_of, levels, top_extra, budget=4000):
    """XY extents of what stands on each level, by tree descent.

    Bands: level i spans [elevation_i, elevation_{i+1}) (the last one + top_extra).
    A node whose box fits inside one band (with a little slack) counts for that band
    whole; a node that crosses bands is split into its children; a leaf, or any node
    once `budget` nodes were looked at, counts for every band it overlaps.
    Returns ([box or None per level], sampled bool). Boxes are ((x0,y0,z0),(x1,y1,z1))
    with the band's own Z range."""
    if not levels:
        return [], False
    edges = [lv['elevation'] for lv in levels]
    tops = edges[1:] + [edges[-1] + abs(float(top_extra))]
    gaps = [t - b for b, t in zip(edges, tops) if t > b]
    slack = min(gaps) * 0.15 if gaps else 0.0
    xy = [None] * len(levels)

    def add(i, box):
        (x0, y0, _z0), (x1, y1, _z1) = box
        if xy[i] is None:
            xy[i] = [x0, y0, x1, y1]
        else:
            r = xy[i]
            r[0], r[1], r[2], r[3] = min(r[0], x0), min(r[1], y0), max(r[2], x1), max(r[3], y1)

    def bands_of(box):
        # The box shrunk by the slack at both ends: a wall group whose slab pokes a
        # little below its level still belongs to that one level.
        z0, z1 = box[0][2], box[1][2]
        low, high = z0 + slack, z1 - slack
        if low > high:
            low = high = (z0 + z1) / 2.0
        hit = [i for i, (b, t) in enumerate(zip(edges, tops)) if high >= b and low < t]
        if not hit:
            hit = [0] if high < edges[0] else [len(levels) - 1]
        return hit

    seen = [0]
    sampled = [False]
    stack = list(reversed(list(roots)))
    while stack:
        node = stack.pop()
        box = box_of(node)
        if box is None:
            continue
        seen[0] += 1
        hit = bands_of(box)
        fits = len(hit) == 1
        kids = list(children_of(node)) if not fits else []
        if fits or not kids:
            for i in hit:
                add(i, box)
            continue
        if seen[0] >= budget:
            sampled[0] = True
            for i in hit:
                add(i, box)
            continue
        stack.extend(reversed(kids))
    out = []
    for i, r in enumerate(xy):
        if r is None:
            out.append(None)
        else:
            out.append(((r[0], r[1], edges[i]), (r[2], r[3], tops[i])))
    return out, sampled[0]


# ==== API half ======================================================================


def _doc(doc):
    if doc is not None:
        return doc
    from pynavis._api import Application
    return Application.ActiveDocument


def _box(node):
    try:
        box = node.BoundingBox()
        if box is None or box.IsEmpty:
            return None
        return ((box.Min.X, box.Min.Y, box.Min.Z), (box.Max.X, box.Max.Y, box.Max.Z))
    except Exception:
        return None


def model_box(doc=None):
    document = _doc(doc)
    try:
        box = document.GetBoundingBox(False)
        if box is None or box.IsEmpty:
            return None
        return ((box.Min.X, box.Min.Y, box.Min.Z), (box.Max.X, box.Max.Y, box.Max.Z))
    except Exception:
        return None


def grid_levels(doc=None):
    """Levels of the active grid system (else the first system), exact."""
    document = _doc(doc)
    try:
        grids = document.Grids
        system = grids.ActiveSystem
        if system is None and grids.Systems.Count > 0:
            system = grids.Systems[0]
    except Exception:
        return []
    if system is None:
        return []
    out = []
    try:
        for lv in system.Levels:
            out.append(level(lv.DisplayName, lv.Elevation, 'grid', False))
    except Exception:
        return []
    return normalize(out)


def _class_text(node):
    parts = []
    for attr in ('ClassDisplayName', 'ClassName'):
        try:
            parts.append(str(getattr(node, attr) or ''))
        except Exception:
            pass
    return ' '.join(parts).lower()


def _bottoms_under(node, limit):
    """Bottom Z of up to `limit` objects under node."""
    from namo import items
    bottoms = []
    seen = set()
    try:
        walk = node.DescendantsAndSelf
    except Exception:
        return bottoms
    for item in walk:
        if not item.HasGeometry:
            continue
        element = items.object_of(item)
        if element in seen:
            continue
        seen.add(element)
        box = _box(element)
        if box is not None:
            bottoms.append(box[0][2])
        if len(bottoms) >= limit:
            break
    return bottoms


def storey_levels(doc=None, report=None):
    """IFC storeys found in the top of the tree, elevations estimated."""
    from namo import items, vp_common
    document = _doc(doc)
    bin_size = BIN_METERS / vp_common.to_meters_factor(str(document.Units))
    found = []
    queue = [(root, 0) for root in items.roots(document)]
    looked = 0
    while queue and looked < TREE_NODE_BUDGET:
        node, depth = queue.pop(0)
        looked += 1
        if any(word in _class_text(node) for word in STOREY_WORDS):
            found.append(node)
            continue
        if depth < TREE_DEPTH:
            try:
                queue.extend((child, depth + 1) for child in node.Children)
            except Exception:
                pass
    out = []
    per = max(40, SCAN_BUDGET // max(1, len(found)))
    for index, node in enumerate(found):
        if vp_common.report_step(report, float(index) / max(1, len(found)),
                                 'Reading storey %d of %d' % (index + 1, len(found))):
            raise items.Cancelled()
        bottoms = _bottoms_under(node, per)
        z = estimate_elevation(bottoms, bin_size)
        if z is None:
            box = _box(node)
            z = box[0][2] if box else None
        if z is not None:
            out.append(level(node.DisplayName or 'Storey', z, 'storey', True, len(bottoms)))
    return normalize(out)


def _level_value(element):
    from namo import items
    for category, prop in LEVEL_PROPERTIES:
        value = items.prop(element, category, prop, fallback_to_object=False)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def property_levels(doc=None, report=None):
    """Levels from the Level property of objects sampled across the tree (each
    model's top branches get an equal share, so a level-ordered tree is not read
    from the bottom floor only). Returns (levels, sampled)."""
    from namo import items, vp_common
    document = _doc(doc)
    bin_size = BIN_METERS / vp_common.to_meters_factor(str(document.Units))
    branches = []
    for root in items.roots(document):
        try:
            kids = list(root.Children)
        except Exception:
            kids = []
        branches.extend(kids or [root])
    if not branches:
        return [], False
    share = max(30, SCAN_BUDGET // len(branches))
    groups = {}
    sampled = False
    for index, branch in enumerate(branches):
        if vp_common.report_step(report, float(index) / len(branches),
                                 'Reading levels: branch %d of %d' % (index + 1, len(branches))):
            raise items.Cancelled()
        taken = 0
        seen = set()
        try:
            walk = branch.DescendantsAndSelf
        except Exception:
            continue
        for item in walk:
            if not item.HasGeometry:
                continue
            element = items.object_of(item)
            if element in seen:
                continue
            seen.add(element)
            taken += 1
            if taken > share:
                sampled = True
                break
            name = _level_value(element)
            if name is None:
                continue
            box = _box(element)
            if box is None:
                continue
            groups.setdefault(name, []).append(box[0][2])
    out = []
    for name in sorted(groups):
        z = estimate_elevation(groups[name], bin_size)
        if z is not None:
            out.append(level(name, z, 'property', True, len(groups[name])))
    return normalize(out), sampled


def _cache():
    from namo import session
    return session.holder('levels')


def _cache_key(document):
    from namo import vp_common
    try:
        count = document.Models.Count
    except Exception:
        count = 0
    return (vp_common.doc_path(document).lower(), count, str(document.Units))


def find(doc=None, report=None, use_cache=True):
    """Levels of the document, best source first (see the module docstring).
    Estimated levels are cached for the session per document and model count.
    Raises items.Cancelled when report says stop."""
    document = _doc(doc)
    grid = grid_levels(document)
    if grid:
        return grid
    holder = _cache()
    key = _cache_key(document)
    cached = getattr(holder, 'levels', None)
    if use_cache and cached is not None and cached[0] == key:
        return [dict(lv) for lv in cached[1]]
    found = storey_levels(document, report)
    if not found:
        found, _sampled = property_levels(document, report)
    holder.levels = (key, [dict(lv) for lv in found])
    return found


def cached_or_none(doc=None):
    """Levels without any scan: grid levels, else the session cache, else None."""
    document = _doc(doc)
    grid = grid_levels(document)
    if grid:
        return grid
    cached = getattr(_cache(), 'levels', None)
    if cached is not None and cached[0] == _cache_key(document):
        return [dict(lv) for lv in cached[1]]
    return None


def load_settings():
    try:
        from pynavis import settings
        return settings_values(settings.load(TOOL, DEFAULTS))
    except Exception:
        return settings_values(None)


def save_settings(values):
    from pynavis import settings
    settings.save(TOOL, settings_values(values))


def remembered(doc=None):
    """The level name last sectioned in this document, or None."""
    document = _doc(doc)
    from namo import vp_common
    key = vp_common.doc_path(document).lower()
    names = getattr(_cache(), 'current', None) or {}
    if key in names:
        return names[key]
    try:
        from namo import store
        value = store.Store('level-sectioner', doc_path=vp_common.doc_path(document)).load({})
        return (value or {}).get('level')
    except Exception:
        return None


def remember(lv, doc=None):
    document = _doc(doc)
    from namo import session, vp_common
    key = vp_common.doc_path(document).lower()
    holder = _cache()
    names = getattr(holder, 'current', None)
    if names is None:
        names = {}
        holder.current = names
    names[key] = lv['name']
    try:
        from namo import store
        store.Store('level-sectioner', doc_path=vp_common.doc_path(document)).save(
            {'level': lv['name'], 'elevation': lv['elevation']})
    except Exception as error:
        session.log('warning', 'level not remembered: %s' % error)


def current_index(levels, doc=None, settings=None):
    """Where the user is now (see pick_current): the level under the current
    section's top plane, the remembered level, else the level under the eye."""
    from namo import camera, vp_common
    document = _doc(doc)
    cfg = settings or load_settings()
    cut = cfg['cut_height_m'] / vp_common.to_meters_factor(str(document.Units))
    top_z = None
    try:
        state = camera.clip_state(document)
        if state.get('enabled') and state.get('mode') == 'Planes':
            tops = [p['origin'][2] for p in state['planes']
                    if p.get('enabled') and abs(p['normal'][2]) > 0.99 and p['normal'][2] < 0]
            if tops:
                top_z = max(tops)
    except Exception:
        top_z = None
    eye_z = None
    if top_z is None:
        try:
            eye_z = camera.capture(document)['position'][2]
        except Exception:
            eye_z = None
    return pick_current(levels, remembered(document), top_z, cut, eye_z)


def level_viewpoint(document, lv, settings, base=None, plan=None, box=None):
    """A detached Viewpoint cut at level lv (one CreateCopy of `base` or the
    current view). plan True also aims a top-down orthographic camera framed on
    box (default the model box)."""
    from namo import camera, vp_common
    units = str(document.Units)
    k = 1.0 / vp_common.to_meters_factor(units)
    whole = model_box(document)
    center = ((whole[0][0] + whole[1][0]) / 2.0, (whole[0][1] + whole[1][1]) / 2.0) if whole else (0.0, 0.0)
    viewpoint = (base or document.CurrentViewpoint).CreateCopy()
    planes = cut_planes(lv['elevation'], settings['cut_height_m'] * k, settings['slab'],
                        settings['slab_depth_m'] * k, center)
    vp_common.set_planes(viewpoint, planes, whole)
    use_plan = settings['plan'] if plan is None else plan
    if use_plan:
        frame = box or whole
        if frame is not None:
            top = lv['elevation'] + settings['cut_height_m'] * k
            aspect = None
            try:
                aspect = float(viewpoint.AspectRatio) or None
            except Exception:
                aspect = None
            cam = plan_camera(frame, lv['elevation'], max(top, frame[1][2]), aspect)
            viewpoint = camera.to_viewpoint(cam, base=viewpoint)
            try:
                from pynavis._api import Api
                (x0, y0, _z0), (x1, y1, _z1) = frame
                viewpoint.ZoomBox(Api.BoundingBox3D(Api.Point3D(x0, y0, lv['elevation']),
                                                    Api.Point3D(x1, y1, top)))
            except Exception:
                pass
    return viewpoint


def apply(lv, doc=None, settings=None, plan=None):
    """Sections the view at level lv (one undo step) and remembers it."""
    document = _doc(doc)
    cfg = settings or load_settings()
    viewpoint = level_viewpoint(document, lv, cfg, plan=plan)
    document.CurrentViewpoint.CopyFrom(viewpoint)
    remember(lv, document)
    return viewpoint


def step(direction, doc=None, report=None):
    """Level Up (+1) / Level Down (-1). Returns (level, message, detail)."""
    from namo import vp_common
    document = _doc(doc)
    levels = find(document, report)
    if not levels:
        return ('info', 'No levels found',
                'Add a grid system with levels (Grids and Levels), or open a model whose '
                'objects carry a Level property.')
    cfg = load_settings()
    current = current_index(levels, document, cfg)
    target, moved = step_index(levels, current, direction)
    units = str(document.Units)
    if not moved:
        edge = 'top' if direction > 0 else 'bottom'
        return ('info', 'Already at the %s level' % edge,
                '%s is the %s level.' % (levels[target]['name'], 'highest' if direction > 0 else 'lowest'))
    lv = levels[target]
    apply(lv, document, cfg, plan=False)
    k = 1.0 / vp_common.to_meters_factor(units)
    cut = lv['elevation'] + cfg['cut_height_m'] * k
    detail = 'Cut at %s%s.' % (vp_common.length_text(cut, units),
                               ' (approximate level)' if lv.get('approximate') else '')
    return ('info', lv['name'], detail)
