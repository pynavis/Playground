# -*- coding: utf-8 -*-
"""Where Am I: one popup that says where the camera is, in words a coordinator
would use on a call.

gather() reads the document (all cheap reads; the geometry count is time-boxed and
cached for the session); lines() turns that dict into the text (pure, tested). The
grid position uses GridIntersection.FormatCombinedDisplayString when Navisworks
gives one (the status bar wording) and always adds the nearest intersection with its
distance, worked out here.
"""
import math
import time

COUNT_SECONDS = 2.0


# ---- pure ---------------------------------------------------------------------------


def direction_text(direction):
    """'NE, bearing 42 degrees, 12 degrees below the horizon'."""
    from namo import camera
    bearing, pitch = camera.bearing_pitch(direction)
    if abs(pitch) > 89.5:
        return 'straight %s' % ('down' if pitch < 0 else 'up')
    where = 'level' if abs(pitch) < 0.5 else '%s %s the horizon' % (
        _deg(abs(pitch)), 'below' if pitch < 0 else 'above')
    return '%s, bearing %s, %s' % (camera.compass_name(bearing), _deg(int(round(bearing)) % 360), where)


def _deg(value):
    """'42°' (the degree sign is chr(176))."""
    return '%d%s' % (int(round(float(value))), chr(176))


def lens_text(cam, doc_units):
    from namo import vp_common
    if str(cam.get('projection')).startswith('ortho'):
        height = cam.get('height_field')
        if height:
            return 'Orthographic, %s tall view' % vp_common.length_text(height, doc_units)
        return 'Orthographic'
    fov = cam.get('fov')
    if fov:
        return 'Perspective, %s vertical field of view' % _deg(fov)
    return 'Perspective'


def section_text(state):
    if not state or not state.get('enabled'):
        return 'Off'
    if state.get('mode') == 'Box':
        return 'Section box on'
    active = int(state.get('active') or 0)
    if active == 0:
        return 'On, no planes enabled'
    return '%d plane%s on' % (active, '' if active == 1 else 's')


def level_text(levels, z, doc_units):
    """'Level 2, eye 1.600 m above it' (or below the lowest level)."""
    from namo import levels as _levels, vp_common
    if not levels:
        return None
    index = _levels.index_at(levels, z)
    lv = levels[index]
    gap = float(z) - lv['elevation']
    note = ' (approximate elevation)' if lv.get('approximate') else ''
    if gap < 0:
        return '%s, eye %s below it%s' % (lv['name'], vp_common.length_text(-gap, doc_units), note)
    return '%s, eye %s above it%s' % (lv['name'], vp_common.length_text(gap, doc_units), note)


def lines(info):
    """The popup text as a list of 'Label: value' lines."""
    from namo import vp_common
    units = info.get('units') or 'Meters'
    out = ['File: %s' % (info.get('file') or 'Untitled (not saved yet)')]
    saved = info.get('saved')
    if saved is None:
        out.append('Saved viewpoint: none is current')
    elif info.get('on_saved'):
        out.append('Saved viewpoint: %s' % saved)
    else:
        out.append('Saved viewpoint: moved away from %s' % saved)
    cam = info.get('camera')
    if cam:
        out.append('Eye: %s' % vp_common.point_text(cam['position'], units))
        out.append('Looking: %s' % direction_text(cam['direction']))
        out.append('Camera: %s' % lens_text(cam, units))
    level = level_text(info.get('levels'), cam['position'][2], units) if cam else None
    out.append('Level: %s' % (level or info.get('levels_note') or 'no grid levels in this model'))
    grid = info.get('grid')
    if grid:
        text = grid.get('label') or ''
        near = grid.get('nearest')
        if near:
            near_text = 'nearest %s, %s away' % (near, vp_common.length_text(grid.get('distance') or 0.0, units))
            text = '%s (%s)' % (text, near_text) if text else near_text
        out.append('Grid: %s' % text)
    else:
        out.append('Grid: no grid system')
    out.append('Section: %s' % section_text(info.get('section')))
    models = info.get('models') or 0
    count = info.get('geometry')
    if count is None:
        model_line = vp_common.plural(models, 'model') + ' loaded'
    elif info.get('geometry_partial'):
        model_line = '%s loaded, more than %s geometry items (stopped counting)' % (
            vp_common.plural(models, 'model'), vp_common.count_text(count))
    else:
        model_line = '%s loaded, %s' % (vp_common.plural(models, 'model'), vp_common.plural(count, 'geometry item'))
    out.append('Models: %s' % model_line)
    out.append('Units: %s' % units)
    out.append('Selection: %s' % (vp_common.plural(info.get('selected') or 0, 'item') if info.get('selected')
                                  else 'nothing selected'))
    return out


# ==== API half ======================================================================


def _grid(document, point):
    from pynavis._api import Api
    try:
        system = document.Grids.ActiveSystem
    except Exception:
        return None
    if system is None:
        return None
    p = Api.Point3D(float(point[0]), float(point[1]), float(point[2]))
    out = {}
    try:
        hit = system.ClosestIntersection(p)
    except Exception:
        hit = None
    if hit is None:
        return None
    try:
        out['nearest'] = str(hit.DisplayName)
        pos = hit.Position
        out['distance'] = math.hypot(float(pos.X) - point[0], float(pos.Y) - point[1])
    except Exception:
        pass
    try:
        label = str(hit.FormatCombinedDisplayString(p, 1.0) or '').strip()
        if label:
            out['label'] = label
    except Exception:
        pass
    return out


def geometry_count(document, seconds=COUNT_SECONDS):
    """(count, partial) of items with geometry, time-boxed, cached per document and
    model count for the session."""
    from namo import items, session, vp_common
    key = (vp_common.doc_path(document).lower(), document.Models.Count)
    holder = session.holder('whereami')
    cached = getattr(holder, 'count', None)
    if cached is not None and cached[0] == key:
        return cached[1], cached[2]
    started = time.time()
    count = 0
    partial = False
    for root in items.roots(document):
        for item in root.DescendantsAndSelf:
            if item.HasGeometry:
                count += 1
                if count % 5000 == 0 and time.time() - started > seconds:
                    partial = True
                    break
        if partial:
            break
    if not partial:
        holder.count = (key, count, partial)
    return count, partial


def gather(document):
    from pynavis._api import Api
    from namo import camera, levels, vp_common
    units = str(document.Units)
    info = {'units': units, 'file': '', 'models': document.Models.Count}
    path = vp_common.doc_path(document)
    info['file'] = path.replace('\\', '/').split('/')[-1] if path else ''
    cam = camera.capture(document)
    info['camera'] = cam
    try:
        current = document.SavedViewpoints.CurrentSavedViewpoint
    except Exception:
        current = None
    if current is not None and isinstance(current, Api.SavedViewpoint):
        info['saved'] = str(current.DisplayName)
        tol = 0.001 / vp_common.to_meters_factor(units)
        info['on_saved'] = vp_common.same_camera(cam, camera.from_viewpoint(current.Viewpoint), tol, 0.05)
    else:
        info['saved'] = None
    found = levels.cached_or_none(document)
    info['levels'] = found
    if not found:
        info['levels_note'] = 'no grid levels (Level Sectioner can estimate them from the objects)'
    info['grid'] = _grid(document, cam['position'])
    try:
        info['section'] = camera.clip_state(document)
    except Exception:
        info['section'] = None
    try:
        info['selected'] = vp_common.count_of(document.CurrentSelection.SelectedItems)
    except Exception:
        info['selected'] = 0
    try:
        info['geometry'], info['geometry_partial'] = geometry_count(document)
    except Exception:
        info['geometry'] = None
    return info
