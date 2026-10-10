# -*- coding: utf-8 -*-
"""The Navisworks camera, saved viewpoints and section planes, as plain data.

CONVENTION (Rotation3D, read this before touching the maths)
-------------------------------------------------------------
Viewpoint.Rotation is a Rotation3D whose A, B, C, D are a unit QUATERNION with the
vector part first and the scalar last: q = (x, y, z, w) = (A, B, C, D). The camera
has its own frame in which it LOOKS ALONG LOCAL -Z, with LOCAL +Y UP and LOCAL +X
to the RIGHT (the OpenGL camera). q rotates that frame into the world:

    direction = q * (0, 0, -1) * q^-1
    up        = q * (0, 1, 0)  * q^-1
    right     = q * (1, 0, 0)  * q^-1

so the identity rotation (0, 0, 0, 1) looks straight down -Z with world +Y up the
screen: a plan view. A front view (looking along +Y, Z up) is a +90 degree turn about
X: (0.7071, 0, 0, 0.7071).

Evidence, strongest first:
  * pyNavis' shipped Section Nudge (extensions/pyNavis.extension/lib/sectionnudge.py,
    frame_for/_rotate) reads the live camera exactly this way and names the box
    faces Front/Left/Top from it; those names are what users see on the panel, so a
    wrong convention would have been visible there.
  * Autodesk's own Navisworks .NET sample for the view direction (Xiaodong Liang,
    "get view direction") multiplies Rotation3D(0, 0, -1, 0) between Rotation and
    its inverse with D as the real part of the product: the same formula.
  * Rotation3D(a, b, c, d) takes its components in the order A, B, C, D (the dump:
    Rotation3D::.ctor(Double a, Double b, Double c, Double d)); pynavis.viewstate
    rebuilds a box rotation with Rotation3D(*[A, B, C, D]).
IN-APP CHECK (dev/notes/foundation-F3.md): capture() in the Front view of the
ViewCube must report direction ~(0, 1, 0) and up ~(0, 0, 1).

To be safe against this convention ever being wrong in the WRITE direction, apply()
only writes a Rotation3D it was given (a round trip of a captured camera, which is
exact whatever the convention); cameras built from maths (look_at, from_bcf) are
aimed with Viewpoint.AlignDirection + AlignUp instead, the calls pynavis.section's
shipped Plan to Selection uses.

HeightField is the VERTICAL field of view in RADIANS for a perspective camera
(pyNavis' Apply Speeds writes it that way, field-verified). For an orthographic
camera it is taken to be the visible height in model units: UNVERIFIED, see notes.

Sections follow pynavis.section and pynavis.viewstate (both shipped): edit the
ClipPlanes of a CreateCopy() of the current viewpoint and write it back with ONE
CurrentViewpoint.CopyFrom (one undo step); planes are aimed with
AlignToPick(Custom, origin, normal) where the normal points INTO the volume kept
(pynavis.section.KEEP_INWARD, the one empirical constant there).

Pure half first (unit tested on both engines); the API half lazy-imports
pynavis._api so `import namo.camera` works anywhere.
"""

import math

KEEP_INWARD = True          # mirrors pynavis.section.KEEP_INWARD
DEFAULT_FOV = 60.0          # degrees, vertical, when a BCF camera carries none

_IDENTITY = (0.0, 0.0, 0.0, 1.0)


# ---- vector helpers -----------------------------------------------------------


def _v(p):
    return (float(p[0]), float(p[1]), float(p[2]))


def _add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _scale(v, k):
    return (v[0] * k, v[1] * k, v[2] * k)


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def _length(v):
    return math.sqrt(_dot(v, v))


def normalize(v):
    """v scaled to length 1, or None for a zero (or non-finite) vector."""
    v = _v(v)
    n = _length(v)
    if not (n > 1e-15) or n == float('inf'):
        return None
    return (v[0] / n, v[1] / n, v[2] / n)


def _clean(v):
    """Rounds away -0.0 and 1e-17 dust so results print and compare nicely."""
    return tuple(0.0 if abs(x) < 1e-12 else x for x in v)


# ---- quaternions --------------------------------------------------------------


def _unit_quat(q):
    a, b, c, d = float(q[0]), float(q[1]), float(q[2]), float(q[3])
    n = math.sqrt(a * a + b * b + c * c + d * d)
    if not (n > 1e-15):
        return _IDENTITY
    return (a / n, b / n, c / n, d / n)


def rotate(q, v):
    """v turned by the unit quaternion q = (A, B, C, D) (vector part, then scalar)."""
    a, b, c, d = _unit_quat(q)
    axis = (a, b, c)
    once = _cross(axis, v)
    twice = _cross(axis, once)
    return (v[0] + 2.0 * (d * once[0] + twice[0]),
            v[1] + 2.0 * (d * once[1] + twice[1]),
            v[2] + 2.0 * (d * once[2] + twice[2]))


def quat_to_axes(a, b, c, d):
    """(direction, up, right) world unit vectors of a camera with Rotation3D
    (A, B, C, D). A zero quaternion reads as the identity (a plan view)."""
    q = (a, b, c, d)
    return (_clean(rotate(q, (0.0, 0.0, -1.0))),
            _clean(rotate(q, (0.0, 1.0, 0.0))),
            _clean(rotate(q, (1.0, 0.0, 0.0))))


def orthonormal_up(direction, up):
    """(direction, up) both unit length and perpendicular. When up is (nearly)
    parallel to direction, such as looking straight up or down with Z up, world +Y
    is used instead, then +X, so a plan view comes out north-up rather than
    undefined. Raises ValueError for a zero direction."""
    f = normalize(direction)
    if f is None:
        raise ValueError('the view direction has no length')
    for candidate in (up, (0.0, 1.0, 0.0), (1.0, 0.0, 0.0)):
        if candidate is None:
            continue
        c = _v(candidate)
        size = _length(c)
        if not (size > 1e-15):
            continue
        residual = _sub(c, _scale(f, _dot(c, f)))
        if _length(residual) > 1e-6 * size:
            return f, normalize(residual)
    raise ValueError('could not find an up vector')


def axes_to_quat(direction, up):
    """The Rotation3D (A, B, C, D) of a camera looking along direction with up as
    near to `up` as the direction allows. Canonical sign: D >= 0."""
    f, u = orthonormal_up(direction, up)
    x = _cross(f, u)                    # right = direction x up
    z = _scale(f, -1.0)                 # local +Z is behind the camera
    m00, m01, m02 = x[0], u[0], z[0]
    m10, m11, m12 = x[1], u[1], z[1]
    m20, m21, m22 = x[2], u[2], z[2]
    trace = m00 + m11 + m22
    if trace > 0.0:
        s = 0.5 / math.sqrt(trace + 1.0)
        w = 0.25 / s
        qx = (m21 - m12) * s
        qy = (m02 - m20) * s
        qz = (m10 - m01) * s
    elif m00 > m11 and m00 > m22:
        s = 2.0 * math.sqrt(1.0 + m00 - m11 - m22)
        w = (m21 - m12) / s
        qx = 0.25 * s
        qy = (m01 + m10) / s
        qz = (m02 + m20) / s
    elif m11 > m22:
        s = 2.0 * math.sqrt(1.0 + m11 - m00 - m22)
        w = (m02 - m20) / s
        qx = (m01 + m10) / s
        qy = 0.25 * s
        qz = (m12 + m21) / s
    else:
        s = 2.0 * math.sqrt(1.0 + m22 - m00 - m11)
        w = (m10 - m01) / s
        qx = (m02 + m20) / s
        qy = (m12 + m21) / s
        qz = 0.25 * s
    q = _unit_quat((qx, qy, qz, w))
    if q[3] < 0.0:
        q = (-q[0], -q[1], -q[2], -q[3])
    return _clean(q)


def look_at_axes(eye, target, up=(0.0, 0.0, 1.0)):
    """(direction, up, right) for a camera at eye looking at target. Raises
    ValueError when eye and target coincide."""
    direction = normalize(_sub(_v(target), _v(eye)))
    if direction is None:
        raise ValueError('the eye and the target are the same point')
    f, u = orthonormal_up(direction, up)
    return (_clean(f), _clean(u), _clean(_cross(f, u)))


def bearing_pitch(direction, north=(0.0, 1.0, 0.0), up=(0.0, 0.0, 1.0)):
    """(bearing, pitch) in degrees: bearing clockwise from north in [0, 360),
    pitch above the horizon in [-90, 90]. Looking straight up or down the bearing
    is 0.0. north/up default to world +Y and +Z (Navisworks' defaults)."""
    d = normalize(direction)
    if d is None:
        return (0.0, 0.0)
    n = normalize(north) or (0.0, 1.0, 0.0)
    z = normalize(up) or (0.0, 0.0, 1.0)
    east = _cross(n, z)
    pitch = math.degrees(math.asin(max(-1.0, min(1.0, _dot(d, z)))))
    x, y = _dot(d, east), _dot(d, n)
    if abs(x) < 1e-12 and abs(y) < 1e-12:
        return (0.0, pitch)
    bearing = math.degrees(math.atan2(x, y)) % 360.0
    if bearing >= 360.0 - 1e-9:
        bearing = 0.0
    return (bearing, pitch)


def compass_name(bearing):
    """'N', 'NE', 'E' ... for a bearing in degrees."""
    names = ('N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW')
    return names[int(((float(bearing) % 360.0) + 22.5) // 45.0) % 8]


# ---- lens -------------------------------------------------------------------


def projection_name(value):
    """'persp' or 'ortho' from a ViewpointProjection, its text, or our own name."""
    text = str(value).lower()
    if text.startswith('ortho'):
        return 'ortho'
    return 'persp'


def fov_degrees(height_field, projection):
    """Vertical field of view in degrees for a perspective camera; None for an
    orthographic one (its HeightField is a height, not an angle)."""
    if projection_name(projection) == 'ortho' or height_field is None:
        return None
    return math.degrees(float(height_field))


def height_field_for(fov_deg):
    """Viewpoint.HeightField (radians) for a vertical field of view in degrees."""
    return math.radians(float(fov_deg))


def vertical_fov(horizontal_deg, aspect):
    """Vertical degrees for a horizontal field of view and width/height ratio."""
    half = math.radians(float(horizontal_deg)) / 2.0
    return math.degrees(2.0 * math.atan(math.tan(half) / float(aspect)))


def horizontal_fov(vertical_deg, aspect):
    """Horizontal degrees for a vertical field of view and width/height ratio."""
    half = math.radians(float(vertical_deg)) / 2.0
    return math.degrees(2.0 * math.atan(math.tan(half) * float(aspect)))


# ---- camera dicts -------------------------------------------------------------


def make_cam(position, direction=None, up=None, rotation=None, projection='persp',
             height_field=None, focal_distance=None, aspect=None, json=None):
    """A camera dict in the shape capture() returns, filling whichever of rotation
    or direction/up is missing from the other. height_field defaults to a 60
    degree lens for perspective."""
    if rotation is None and direction is None:
        raise ValueError('a camera needs a rotation or a direction')
    if direction is not None:
        f, u = orthonormal_up(direction, up if up is not None else (0.0, 0.0, 1.0))
        computed = axes_to_quat(f, u)
        direction, up = _clean(f), _clean(u)
    else:
        computed = None
        direction, up, _right = quat_to_axes(*rotation)
    projection = projection_name(projection)
    if height_field is None and projection == 'persp':
        height_field = height_field_for(DEFAULT_FOV)
    return {
        'position': _v(position),
        'rotation': tuple(float(x) for x in rotation) if rotation is not None else None,
        'rotation_computed': computed,
        'direction': direction,
        'up': up,
        'projection': projection,
        'height_field': None if height_field is None else float(height_field),
        'fov': fov_degrees(height_field, projection),
        'focal_distance': None if focal_distance is None else float(focal_distance),
        'aspect': None if aspect is None else float(aspect),
        'json': json,
    }


def target_of(cam, distance=None):
    """The point the camera looks at: focal distance (or `distance`) along direction."""
    d = distance if distance is not None else cam.get('focal_distance') or 1.0
    return _add(cam['position'], _scale(cam['direction'], float(d)))


def to_bcf(cam, unit_to_m):
    """A BCF camera from a camera dict, lengths converted to metres.

    {'type': 'PerspectiveCamera', 'CameraViewPoint', 'CameraDirection',
     'CameraUpVector', 'FieldOfView' (vertical degrees), 'AspectRatio'} or
    {'type': 'OrthogonalCamera', ..., 'ViewToWorldScale' (visible height, metres)}.
    Tuples of floats; the caller writes the XML.
    """
    k = float(unit_to_m)
    direction, up = cam.get('direction'), cam.get('up')
    if direction is None or up is None:
        direction, up, _right = quat_to_axes(*cam['rotation'])
    out = {
        'CameraViewPoint': _scale(_v(cam['position']), k),
        'CameraDirection': _v(direction),
        'CameraUpVector': _v(up),
        'AspectRatio': cam.get('aspect'),
    }
    if projection_name(cam.get('projection', 'persp')) == 'ortho':
        out['type'] = 'OrthogonalCamera'
        height = cam.get('height_field')
        out['ViewToWorldScale'] = None if height is None else float(height) * k
    else:
        out['type'] = 'PerspectiveCamera'
        fov = fov_degrees(cam.get('height_field'), 'persp')
        out['FieldOfView'] = fov if fov is not None else DEFAULT_FOV
    return out


def _pick(source, *names):
    for name in names:
        if name in source and source[name] is not None:
            return source[name]
    lowered = dict((str(k).lower(), v) for k, v in source.items())
    for name in names:
        value = lowered.get(name.lower())
        if value is not None:
            return value
    return None


def from_bcf(bcf_cam, m_to_unit):
    """A camera dict (model units) from a BCF camera dict as to_bcf writes it.

    Also accepts lower-case keys and the short names position/direction/up/fov/
    scale. Orthogonal when 'type' says so or a ViewToWorldScale is present.
    The up vector is re-orthogonalised (BCF files from other tools are often a
    hair off). rotation is left None and rotation_computed carries the
    quaternion, so apply() aims the camera with AlignDirection/AlignUp.
    """
    k = float(m_to_unit)
    position = _pick(bcf_cam, 'CameraViewPoint', 'position')
    direction = _pick(bcf_cam, 'CameraDirection', 'direction')
    up = _pick(bcf_cam, 'CameraUpVector', 'up')
    if position is None or direction is None:
        raise ValueError('a BCF camera needs CameraViewPoint and CameraDirection')
    kind = str(_pick(bcf_cam, 'type') or '')
    scale = _pick(bcf_cam, 'ViewToWorldScale', 'scale')
    ortho = kind.lower().startswith('ortho') or (scale is not None and not kind)
    if ortho:
        height = float(scale) * k if scale is not None else None
        projection = 'ortho'
    else:
        fov = _pick(bcf_cam, 'FieldOfView', 'fov')
        height = height_field_for(fov if fov is not None else DEFAULT_FOV)
        projection = 'persp'
    aspect = _pick(bcf_cam, 'AspectRatio', 'aspect')
    return make_cam(_scale(_v(position), k), direction=direction,
                    up=up if up is not None else (0.0, 0.0, 1.0),
                    projection=projection, height_field=height, aspect=aspect)


# ---- sections, pure -----------------------------------------------------------


def horizontal_planes(z_top, z_bottom=None, center=(0.0, 0.0)):
    """[(origin, normal)] for a horizontal cut: the top plane at z_top keeping what
    is below, and optionally a bottom plane at z_bottom keeping what is above.
    Normals point into the kept volume (KEEP_INWARD)."""
    cx, cy = float(center[0]), float(center[1])
    sign = 1.0 if KEEP_INWARD else -1.0
    planes = [((cx, cy, float(z_top)), (0.0, 0.0, -1.0 * sign))]
    if z_bottom is not None:
        if float(z_bottom) >= float(z_top):
            raise ValueError('the bottom plane must sit below the top plane')
        planes.append(((cx, cy, float(z_bottom)), (0.0, 0.0, 1.0 * sign)))
    return planes


def range_ok(rng):
    """Whether [[min x,y,z], [max x,y,z]] is a usable, non-inverted box.
    (Navisworks stores a never-set range as an inverted box.)"""
    try:
        low, high = rng[0], rng[1]
        if len(low) != 3 or len(high) != 3:
            return False
        return all(float(low[i]) <= float(high[i]) for i in range(3))
    except Exception:
        return False


def unique_name(name, existing):
    """name, or 'name (2)', 'name (3)' ... whichever is not in existing."""
    taken = set(existing)
    if name not in taken:
        return name
    n = 2
    while '%s (%d)' % (name, n) in taken:
        n += 1
    return '%s (%d)' % (name, n)


def split_path(path):
    """'A/B/C' -> ['A', 'B', 'C']; empty segments dropped; None or '' -> []."""
    if not path:
        return []
    return [part.strip() for part in str(path).replace('\\', '/').split('/') if part.strip()]


def view_path(folder_path, name):
    """The stored path of a saved viewpoint: its folder path, a slash, its name
    ('Coordination/Level 1/Clash 1'; just the name at top level). What tools remember
    and what find_view reads back."""
    return '%s/%s' % (folder_path, name) if folder_path else str(name)


def match_view(target, views):
    """The item a stored path or a bare name means among views, [(folder_path, name,
    item)] in tree order, or None. Three passes, first hit wins:

      1. the stored path is exactly target. First, because viewpoint (and folder)
         names often hold a slash themselves ('Level 1/2', 'North / East'), which a
         split-on-slash lookup can never find;
      2. target split on slashes: the last part is the name, the parts before it the
         folder path (a bare name matches in any folder);
      3. a name that is exactly target, in any folder (a bare name with a slash).
    """
    if not target:
        return None
    target = str(target)
    views = list(views)
    for folder_path, name, item in views:
        if view_path(folder_path, name) == target:
            return item
    wanted = split_path(target)
    if not wanted:
        return None
    for folder_path, name, item in views:
        if name != wanted[-1]:
            continue
        if len(wanted) == 1 or split_path(folder_path) == wanted[:-1]:
            return item
    for _folder_path, name, item in views:
        if name == target:
            return item
    return None


# ==== API half (Navisworks only; lazy imports) ==================================


def _doc(doc):
    if doc is not None:
        return doc
    from pynavis._api import Application
    return Application.ActiveDocument


def _xyz(p):
    return (float(p.X), float(p.Y), float(p.Z))


def _point(Api, p):
    return Api.Point3D(float(p[0]), float(p[1]), float(p[2]))


def _vector(Api, v):
    return Api.Vector3D(float(v[0]), float(v[1]), float(v[2]))


def _unit_vector(Api, v):
    return Api.UnitVector3D(float(v[0]), float(v[1]), float(v[2]))


def from_viewpoint(viewpoint):
    """A camera dict from any Viewpoint (current copy, saved view, clash view)."""
    position = _xyz(viewpoint.Position)
    rotation = viewpoint.Rotation
    quat = (float(rotation.A), float(rotation.B), float(rotation.C), float(rotation.D))
    projection = projection_name(viewpoint.Projection)
    try:
        height = float(viewpoint.HeightField)
    except Exception:
        height = None
    focal = None
    try:
        if viewpoint.HasFocalDistance:
            focal = float(viewpoint.FocalDistance)
    except Exception:
        focal = None
    try:
        aspect = float(viewpoint.AspectRatio)
    except Exception:
        aspect = None
    try:
        json_text = str(viewpoint.GetCamera())
    except Exception:
        json_text = None
    cam = make_cam(position, rotation=quat, projection=projection, height_field=height,
                   focal_distance=focal, aspect=aspect, json=json_text)
    return cam


def capture(doc=None):
    """The current camera as a dict:
    {'position', 'rotation' (A, B, C, D), 'direction', 'up', 'projection' ('persp' |
    'ortho'), 'height_field', 'fov' (degrees or None), 'focal_distance', 'aspect',
    'json' (Viewpoint.GetCamera() text or None), 'rotation_computed' (None)}.
    Reads a CreateCopy(): CurrentViewpoint.Value does not track the live camera."""
    copy = _doc(doc).CurrentViewpoint.CreateCopy()
    try:
        return from_viewpoint(copy)
    finally:
        # A native handle: released now rather than by the finalizer at exit, where
        # leftovers are torn down after the document (a crash on closing, field-measured).
        try:
            copy.Dispose()
        except Exception:
            pass


def _write_camera(Api, viewpoint, cam):
    """Puts a camera dict onto an editable Viewpoint.

    A camera without a height_field keeps the viewpoint's own lens, except across a
    projection change, where the old number means something else (radians versus
    model units): perspective then gets DEFAULT_FOV, orthographic the vertical
    extent the perspective view had at its focal distance."""
    projection = projection_name(cam.get('projection', 'persp'))
    was = projection_name(viewpoint.Projection)
    height = cam.get('height_field')
    if height is None and was != projection:
        if projection == 'persp':
            height = height_field_for(DEFAULT_FOV)
        else:
            try:
                height = float(viewpoint.VerticalExtentAtFocalDistance)
            except Exception:
                height = None
    viewpoint.Projection = (Api.ViewpointProjection.Orthographic if projection == 'ortho'
                            else Api.ViewpointProjection.Perspective)
    rotation = cam.get('rotation')
    if rotation is not None:
        viewpoint.Rotation = Api.Rotation3D(float(rotation[0]), float(rotation[1]),
                                            float(rotation[2]), float(rotation[3]))
    else:
        direction = cam.get('direction')
        if direction is None:
            raise ValueError('the camera has neither a rotation nor a direction')
        f, u = orthonormal_up(direction, cam.get('up') or (0.0, 0.0, 1.0))
        viewpoint.AlignDirection(_vector(Api, f))
        viewpoint.AlignUp(_vector(Api, u))
    # Position LAST: whatever the Align calls pivot about, the eye ends where asked.
    viewpoint.Position = _point(Api, cam['position'])
    if height is not None and float(height) > 0.0:
        viewpoint.HeightField = float(height)
    focal = cam.get('focal_distance')
    if focal is not None and float(focal) > 0.0:
        try:
            viewpoint.FocalDistance = float(focal)
        except Exception:
            pass
    return viewpoint


def write_camera(viewpoint, cam):
    """Writes a camera dict onto an editable Viewpoint IN PLACE and returns it: the
    route for a viewpoint you already hold (the detached copy of a saved viewpoint
    being edited), where to_viewpoint would start from a different base. Lens rules
    as in to_viewpoint; raises ValueError for a camera with neither rotation nor
    direction."""
    from pynavis._api import Api
    return _write_camera(Api, viewpoint, cam)


def to_viewpoint(cam, base=None, doc=None):
    """A detached Viewpoint carrying cam. base (a Viewpoint) supplies everything a
    camera dict does not (lighting, render style, clip planes); default: a copy of
    the current viewpoint."""
    from pynavis._api import Api
    viewpoint = base.CreateCopy() if base is not None else _doc(doc).CurrentViewpoint.CreateCopy()
    return _write_camera(Api, viewpoint, cam)


def apply(cam, doc=None):
    """Moves the view to cam (one CopyFrom of an edited copy: one undo step).
    Clip planes, lighting and render style of the current view are kept."""
    document = _doc(doc)
    viewpoint = to_viewpoint(cam, doc=document)
    document.CurrentViewpoint.CopyFrom(viewpoint)
    return viewpoint


def look_at(eye, target, up=(0.0, 0.0, 1.0), fov_deg=None, doc=None):
    """Stands the camera at eye looking at target, perspective, focal distance on
    the target. fov_deg sets the vertical lens; None keeps the current one."""
    direction, true_up, _right = look_at_axes(eye, target, up)
    cam = make_cam(eye, direction=direction, up=true_up, projection='persp',
                   height_field=height_field_for(fov_deg) if fov_deg is not None else None,
                   focal_distance=_length(_sub(_v(target), _v(eye))))
    if fov_deg is None:
        cam['height_field'] = None          # keep the current lens
        cam['fov'] = None
    return apply(cam, doc)


def _box_of(items_or_bbox):
    """((x0,y0,z0),(x1,y1,z1)) from a bbox tuple, a ModelItem, or items."""
    try:
        low, high = items_or_bbox
        if len(low) == 3 and len(high) == 3 and not hasattr(low, 'DisplayName'):
            return (_v(low), _v(high))
    except Exception:
        pass
    from namo import items as _items
    return _items.bbox(items_or_bbox)


def zoom_to(items_or_bbox, doc=None, margin=0.0):
    """Frames items (or a ((min), (max)) box) along the current view direction:
    Viewpoint.ZoomBox on a copy, then one CopyFrom. margin grows the box by that
    fraction of its size on every side. Returns False when there is nothing with
    extent to frame."""
    from pynavis._api import Api
    box = _box_of(items_or_bbox)
    if box is None:
        return False
    low, high = box
    if margin:
        pad = [(high[i] - low[i]) * float(margin) for i in range(3)]
        low = tuple(low[i] - pad[i] for i in range(3))
        high = tuple(high[i] + pad[i] for i in range(3))
    document = _doc(doc)
    viewpoint = document.CurrentViewpoint.CreateCopy()
    viewpoint.ZoomBox(Api.BoundingBox3D(_point(Api, low), _point(Api, high)))
    document.CurrentViewpoint.CopyFrom(viewpoint)
    return True


# ---- saved viewpoints ---------------------------------------------------------


def _child_folder(Api, parent, name):
    for child in parent.Children:
        if isinstance(child, Api.FolderItem) and child.DisplayName == name:
            return child
    return None


def ensure_folder(path, doc=None):
    """The saved-viewpoints FolderItem at 'A/B/C', creating missing folders (one
    undo step). '' or None is the root folder. Returns the live, tree-resident
    folder (AddCopy copies, so a new one is re-found by name)."""
    from pynavis._api import Api
    from pynavis.viewpoints import transaction
    document = _doc(doc)
    saved = document.SavedViewpoints
    parent = saved.RootItem
    segments = split_path(path)
    if not segments:
        return parent
    with transaction('Create viewpoint folder', document):
        at_root = True
        for segment in segments:
            found = _child_folder(Api, parent, segment)
            if found is None:
                fresh = Api.FolderItem()
                fresh.DisplayName = segment
                if at_root:
                    saved.AddCopy(fresh)
                else:
                    saved.AddCopy(parent, fresh)
                found = _child_folder(Api, parent, segment)
                if found is None:
                    raise RuntimeError('could not create the viewpoint folder %r' % segment)
            parent = found
            at_root = False
    return parent


def folder(path, doc=None):
    """Same as ensure_folder (the contract name)."""
    return ensure_folder(path, doc)


def save_view(name, folder=None, cam=None, comments=None, doc=None):
    """Saves a viewpoint named `name` (deduped among its siblings: 'name (2)') in
    folder ('A/B', created as needed; None = top level) from cam (default: the
    current view, including its clip planes). comments: a string or list of
    strings added as viewpoint comments. One undo step. Returns the live,
    tree-resident SavedViewpoint (re-found by Guid after AddCopy).

    Api.SavedViewpoint(Viewpoint) records the camera and sections only: hidden
    items and appearance overrides are NOT captured by this route.
    """
    from pynavis._api import Api
    from pynavis.viewpoints import transaction
    document = _doc(doc)
    saved = document.SavedViewpoints
    viewpoint = to_viewpoint(cam, doc=document) if cam is not None \
        else document.CurrentViewpoint.CreateCopy()
    at_root = not split_path(folder)
    with transaction('Save viewpoint', document):
        parent = saved.RootItem if at_root else ensure_folder(folder, document)
        final = unique_name(str(name), [child.DisplayName for child in parent.Children])
        item = Api.SavedViewpoint(viewpoint)
        item.DisplayName = final
        before = set(str(child.Guid) for child in parent.Children)
        if at_root:
            saved.AddCopy(item)
        else:
            saved.AddCopy(parent, item)
        added = None
        for child in parent.Children:
            if str(child.Guid) not in before:
                added = child
                break
        if added is None:
            for child in parent.Children:
                if child.DisplayName == final:
                    added = child
        if added is not None and comments:
            texts = [comments] if isinstance(comments, str) else list(comments)
            for text in texts:
                if text:
                    saved.AddComment(added, Api.Comment(str(text), Api.CommentStatus.New))
    return added if added is not None else item


def saved_views(doc=None, include_animations=False):
    """[(folder_path, SavedViewpoint)] depth-first in tree order; folder_path is
    'A/B' ('' at top level). Animations are skipped unless asked for."""
    from pynavis._api import Api
    from pynavis.doc import walk_saved_viewpoints
    out = []
    for folders, item in walk_saved_viewpoints(_doc(doc)):
        if isinstance(item, Api.SavedViewpoint) or include_animations:
            out.append(('/'.join(folders), item))
    return out


def find_view(name_or_path, doc=None):
    """The saved viewpoint at a stored path ('Folder/Name', see view_path) or with a
    bare name, or None. A name that itself contains '/' is found: the exact stored
    path is tried before any splitting (match_view has the order)."""
    if not name_or_path:
        return None
    views = [(folder_path, str(item.DisplayName), item) for folder_path, item in saved_views(doc)]
    return match_view(name_or_path, views)


def recall(saved, doc=None):
    """Makes a saved viewpoint current (applies its camera, sections and any
    hide/override state it carries), like clicking it."""
    _doc(doc).SavedViewpoints.CurrentSavedViewpoint = saved


# ---- section planes -----------------------------------------------------------


def clip_json(doc=None):
    """The active view's clip planes as Navisworks' own JSON text
    (View.GetClippingPlanes). Opaque: store it, hand it back to set_clip_json.
    UNVERIFIED in-app (see notes)."""
    return str(_doc(doc).ActiveView.GetClippingPlanes())


def set_clip_json(text, doc=None):
    """Applies JSON from clip_json (View.TrySetClippingPlanes). Raises ValueError
    when Navisworks refuses the text. UNVERIFIED in-app, including whether it is
    an undo step: prefer set_clip_state for anything the user must undo."""
    if not _doc(doc).ActiveView.TrySetClippingPlanes(str(text)):
        raise ValueError('Navisworks did not accept the section planes')
    return True


def clip_state(doc=None):
    """The current section as a plain dict, the SAME shape pynavis.viewstate copies
    ('Copy State > Section State'): {'enabled', 'mode' 'Planes'|'Box', 'linked',
    'planes': [{'index', 'state', 'enabled', 'origin', 'normal'}], 'active',
    optional 'range' and 'box' {'min', 'max', 'rotation'}}. JSON-safe."""
    from pynavis._api import Api
    planes = _doc(doc).CurrentViewpoint.CreateCopy().ClipPlanes
    payload = {
        'enabled': bool(planes.Enabled),
        'mode': 'Box' if planes.Mode == Api.ClipPlaneSetMode.Box else 'Planes',
        'linked': bool(planes.Linked),
        'planes': [],
    }
    try:
        rng = planes.Range
        recorded = [list(_xyz(rng.Min)), list(_xyz(rng.Max))]
        if range_ok(recorded):
            payload['range'] = recorded
    except Exception:
        pass
    for index in range(planes.Size()):
        plane = planes.Get(index)
        payload['planes'].append({
            'index': index,
            'state': str(plane.State),
            'enabled': bool(plane.Enabled),
            'origin': list(_xyz(plane.Origin)),
            'normal': list(_xyz(plane.Normal)),
        })
    payload['active'] = len([p for p in payload['planes'] if p['enabled']])
    if payload['mode'] == 'Box':
        box = {'min': list(_xyz(planes.Box.Min)), 'max': list(_xyz(planes.Box.Max)),
               'rotation': None}
        try:
            api_box = Api.BoundingBox3D()
            rotation = Api.Rotation3D()
            planes.GetOrientedBox(api_box, rotation)
            box = {'min': list(_xyz(api_box.Min)), 'max': list(_xyz(api_box.Max)),
                   'rotation': [rotation.A, rotation.B, rotation.C, rotation.D]}
        except Exception:
            pass
        payload['box'] = box
    return payload


def set_clip_state(payload, doc=None):
    """Applies a clip_state dict (or a pynavis viewstate section payload): one
    CopyFrom, one undo step. Planes are re-aimed with AlignToPick(Custom, ...)."""
    from pynavis._api import Api
    document = _doc(doc)
    viewpoint = document.CurrentViewpoint.CreateCopy()
    planes = viewpoint.ClipPlanes
    box_mode = payload.get('mode') == 'Box'
    planes.Mode = Api.ClipPlaneSetMode.Box if box_mode else Api.ClipPlaneSetMode.Planes
    planes.Linked = bool(payload.get('linked'))
    rng = payload.get('range')
    if range_ok(rng):
        planes.Range = Api.BoundingBox3D(_point(Api, rng[0]), _point(Api, rng[1]))
    if box_mode:
        box = payload.get('box') or {}
        corners = [box.get('min'), box.get('max')]
        if range_ok(corners):
            api_box = Api.BoundingBox3D(_point(Api, corners[0]), _point(Api, corners[1]))
            rotation = box.get('rotation')
            done = False
            if rotation:
                try:
                    planes.SetOrientedBox(api_box, Api.Rotation3D(*[float(x) for x in rotation]))
                    done = True
                except Exception:
                    done = False
            if not done:
                planes.Box = api_box
    else:
        size = planes.Size()
        for record in payload.get('planes') or []:
            index = record.get('index', -1)
            if not (0 <= index < size):
                continue
            plane = planes.Get(index)
            plane.AlignToPick(Api.ClipPlaneAlignment.Custom, _point(Api, record['origin']),
                              _unit_vector(Api, record['normal']))
            plane.State = getattr(Api.ClipPlaneState, str(record.get('state', 'Default')),
                                  Api.ClipPlaneState.Default)
            plane.Enabled = bool(record.get('enabled'))
    planes.Enabled = bool(payload.get('enabled'))
    document.CurrentViewpoint.CopyFrom(viewpoint)


def _model_box(document):
    try:
        box = document.GetBoundingBox(False)
        if box is None or box.IsEmpty:
            return None
        return (_xyz(box.Min), _xyz(box.Max))
    except Exception:
        return None


def horizontal_section(z_top, z_bottom=None, doc=None):
    """Cuts the model level: plane 1 at z_top keeps what is below it, plane 2 at
    z_bottom (optional) keeps what is above; every other plane is switched off.
    Heights in model units. One undo step. Returns how many planes were set."""
    from pynavis._api import Api
    document = _doc(doc)
    box = _model_box(document)
    center = ((box[0][0] + box[1][0]) / 2.0, (box[0][1] + box[1][1]) / 2.0) if box else (0.0, 0.0)
    wanted = horizontal_planes(z_top, z_bottom, center)

    viewpoint = document.CurrentViewpoint.CreateCopy()
    planes = viewpoint.ClipPlanes
    planes.Mode = Api.ClipPlaneSetMode.Planes
    planes.Linked = False
    if box is not None:
        try:
            planes.Range = Api.BoundingBox3D(_point(Api, box[0]), _point(Api, box[1]))
        except Exception:
            pass
    size = planes.Size()
    written = 0
    for index in range(size):
        plane = planes.Get(index)
        if index < len(wanted):
            origin, normal = wanted[index]
            plane.AlignToPick(Api.ClipPlaneAlignment.Custom, _point(Api, origin),
                              _unit_vector(Api, normal))
            plane.State = Api.ClipPlaneState.Enabled
            plane.Enabled = True
            written += 1
        else:
            plane.Enabled = False
    planes.Enabled = True
    document.CurrentViewpoint.CopyFrom(viewpoint)
    return written


def section_box(box, doc=None):
    """Section Box mode around ((min), (max)) in model units, one undo step."""
    from pynavis._api import Api
    low, high = box
    document = _doc(doc)
    viewpoint = document.CurrentViewpoint.CreateCopy()
    planes = viewpoint.ClipPlanes
    planes.Mode = Api.ClipPlaneSetMode.Box
    planes.Box = Api.BoundingBox3D(_point(Api, low), _point(Api, high))
    planes.Enabled = True
    document.CurrentViewpoint.CopyFrom(viewpoint)


def clear_section(doc=None):
    """Switches sectioning off without moving the camera. Returns False when it
    was already off (nothing written)."""
    document = _doc(doc)
    viewpoint = document.CurrentViewpoint.CreateCopy()
    planes = viewpoint.ClipPlanes
    if not planes.Enabled:
        return False
    planes.Enabled = False
    document.CurrentViewpoint.CopyFrom(viewpoint)
    return True
