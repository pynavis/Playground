# -*- coding: utf-8 -*-
"""Model transforms: read, decompose, move, rotate about Z, presets per model file.

A model's Units and Transform (the dialog behind the Selection Tree's right-click
Units and Transform) is written with DocumentModels.SetModelUnitsAndTransform(model,
units, Transform3D, reflected): one call, inside one transaction, one undo step.

Reading never touches matrix conventions: Model.Transform.Factor() gives
Transform3DComponents (Translation, Rotation, Scale, ScaleOrientation), and writing
sets Translation and Rotation on those components and calls Combine(), so the scale
the model already has is kept exactly. Rotation3D components are read and written in
the order the constructor takes them, Rotation3D(a, b, c, d) = (A, B, C, D), which
namo.camera documents (field evidence from the shipped Section Nudge) as the
quaternion (x, y, z, w): vector part first, scalar last.

A move is applied AFTER the current transform, in world space: rotate by `angle`
degrees about the vertical axis through `origin`, then slide by `move` (both in
DOCUMENT units). For a current transform p -> R p + t that gives

    R' = Rz R            t' = Rz (t - o) + o + d

One thing the API does not say is which units Model.Transform's translation is in:
the model's own units (the dialog's "Units") or the document's. Playground assumes model
units, then measures the model's box after the edit; if the model moved by the
document/model unit ratio instead, it corrects the edit and remembers the other
convention (pynavis.settings 'playground_transforms'), so the next move is right first
time. With equal units the question does not arise.

Presets (namo.templates 'transform_presets', team-shared) store the absolute
components for one model FILE name; marked auto_apply, hk_transformpresets puts them
on every newly appended copy of that file.
"""

import math
import os

SETTINGS_TOOL = 'playground_transforms'
SETTINGS_DEFAULTS = {'translation_units': 'model'}
PRESETS_TOOL = 'transform_presets'
CONVENTIONS = ('model', 'document')
EPS = 1e-9


# ---- pure: quaternions in (x, y, z, w) order --------------------------------------------


def quat_normalize(q):
    x, y, z, w = [float(v) for v in q]
    n = math.sqrt(x * x + y * y + z * z + w * w)
    if n < EPS:
        return (0.0, 0.0, 0.0, 1.0)
    return (x / n, y / n, z / n, w / n)


def quat_mul(q1, q2):
    """q1 * q2: the rotation q2 followed by q1."""
    x1, y1, z1, w1 = q1
    x2, y2, z2, w2 = q2
    return (w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
            w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
            w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
            w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2)


def quat_about_z(degrees):
    """The quaternion for a counter-clockwise turn (seen from above) about +Z."""
    half = math.radians(float(degrees)) / 2.0
    return (0.0, 0.0, math.sin(half), math.cos(half))


def quat_rotate(q, v):
    """v rotated by the unit quaternion q."""
    x, y, z, w = q
    vx, vy, vz = v
    # t = 2 * cross(q.xyz, v); v' = v + w * t + cross(q.xyz, t)
    tx = 2.0 * (y * vz - z * vy)
    ty = 2.0 * (z * vx - x * vz)
    tz = 2.0 * (x * vy - y * vx)
    return (vx + w * tx + (y * tz - z * ty),
            vy + w * ty + (z * tx - x * tz),
            vz + w * tz + (x * ty - y * tx))


def is_identity_quat(q, tol=1e-9):
    x, y, z, w = quat_normalize(q)
    return abs(x) < tol and abs(y) < tol and abs(z) < tol


def z_angle(q, tol=1e-6):
    """(degrees, pure): the turn about Z in -180..180, and whether the rotation is
    about Z only (a tilted model reports pure False and the Z part of its heading)."""
    x, y, z, w = quat_normalize(q)
    pure = abs(x) < tol and abs(y) < tol
    if pure:
        angle = math.degrees(2.0 * math.atan2(z, w))
    else:
        # heading of the rotated +X axis
        ax = quat_rotate((x, y, z, w), (1.0, 0.0, 0.0))
        angle = math.degrees(math.atan2(ax[1], ax[0]))
    while angle > 180.0:
        angle -= 360.0
    while angle <= -180.0:
        angle += 360.0
    if abs(angle) < 1e-9:
        angle = 0.0
    return angle, pure


def rotate_z(v, degrees):
    """(x, y, z) turned counter-clockwise about +Z through the origin."""
    a = math.radians(float(degrees))
    c, s = math.cos(a), math.sin(a)
    return (c * v[0] - s * v[1], s * v[0] + c * v[1], v[2])


def add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def scale_vec(v, k):
    return (v[0] * k, v[1] * k, v[2] * k)


# ---- pure: composing a move ---------------------------------------------------------------


def delta_translation(angle, origin, move):
    """The translation part of the world move q -> Rz (q - o) + o + d, i.e. o - Rz o + d."""
    o = tuple(origin or (0.0, 0.0, 0.0))
    d = tuple(move or (0.0, 0.0, 0.0))
    return add(sub(o, rotate_z(o, angle)), d)


def compose(translation, rotation, angle, origin, move, factor=1.0):
    """(t', q') after applying the world move to a transform whose translation is in
    TRANSFORM units (= document units x factor). angle in degrees, origin and move
    in document units."""
    k = float(factor) if factor else 1.0
    t_doc = scale_vec(tuple(translation), 1.0 / k)
    o = tuple(origin or (0.0, 0.0, 0.0))
    d = tuple(move or (0.0, 0.0, 0.0))
    new_doc = add(add(rotate_z(sub(t_doc, o), angle), o), d)
    q_new = quat_normalize(quat_mul(quat_about_z(angle), quat_normalize(rotation)))
    return scale_vec(new_doc, k), q_new


def unit_factor(doc_units, model_units, convention):
    """Transform-units per document unit: 1 under the 'document' convention, the
    document/model ratio under 'model'. Unknown unit names give 1."""
    if convention != 'model':
        return 1.0
    from namo import units
    try:
        return units.to_meters(1.0, doc_units) / units.to_meters(1.0, model_units)
    except (ValueError, ZeroDivisionError, TypeError):
        return 1.0


def corners(box):
    (x0, y0, z0), (x1, y1, z1) = box
    return [(x, y, z) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]


def aabb(points):
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    zs = [p[2] for p in points]
    return ((min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs)))


def predict_box(box, angle, translation):
    """The axis-aligned box that holds `box` after q -> Rz q + translation (exact for
    turns that are multiples of 90 degrees, an enclosing box otherwise)."""
    if box is None:
        return None
    return aabb([add(rotate_z(c, angle), translation) for c in corners(box)])


def box_diagonal(box):
    if box is None:
        return 0.0
    return math.sqrt(sum((box[1][i] - box[0][i]) ** 2 for i in range(3)))


def _excess(actual, predicted):
    """How far the actual box sticks out of the predicted one (0 when inside)."""
    worst = 0.0
    for i in range(3):
        worst = max(worst, predicted[0][i] - actual[0][i], actual[1][i] - predicted[1][i])
    return worst


def _distance(a, b):
    return max(abs(a[j][i] - b[j][i]) for j in (0, 1) for i in range(3))


def is_right_angle(angle, tol=1e-6):
    rest = abs(float(angle)) % 90.0
    return rest < tol or 90.0 - rest < tol


FLOAT32_STEP = 2.0 ** -23       # one float32 step per unit of coordinate size
FLOAT64_STEP = 2.0 ** -52


def float32_noise(reach):
    """How far a coordinate `reach` units from the origin can be off from float32
    storage alone: the worst case pynavis.faces.tolerance_for uses (4 steps). About
    0.65 ft for a model 1.37 million feet out, a millionth of a unit near the origin."""
    return abs(float(reach)) * 4.0 * FLOAT32_STEP


def point_noise(points):
    """The smallest difference between picked points that means anything: a few
    float64 steps at their distance from the origin (measured points are doubles)."""
    reach = 0.0
    for point in points:
        for value in point:
            reach = max(reach, abs(float(value)))
    return max(reach, 1.0) * 16.0 * FLOAT64_STEP


def tolerance_for(box):
    """Comparison tolerance for boxes of this model: a thousandth of its size, never
    less than float32 noise at its distance from the origin."""
    if box is None:
        return float32_noise(1.0)
    reach = max(abs(v) for corner in box for v in corner)
    return max(box_diagonal(box) * 1e-3, float32_noise(max(reach, 1.0)))


def _miss(actual, predicted, angle):
    """How far a measured box is from a prediction. Exact compare for right-angle
    turns, containment (the turned box can only be smaller than its rotated corners)
    otherwise."""
    if is_right_angle(angle):
        return _distance(actual, predicted)
    return max(0.0, _excess(actual, predicted))


def judge(actual, predictions, angle, tol):
    """Which prediction the measured box matches: predictions [(name, box)]; None
    when none fits within tol. The NEAREST fitting prediction wins (the first one on a
    tie), so a wide tolerance, which a model far from the origin needs, can never make
    the first prediction swallow a move that really followed the second."""
    if actual is None:
        return None
    best_name, best_miss = None, None
    for name, predicted in predictions:
        if predicted is None:
            continue
        miss = _miss(actual, predicted, angle)
        if miss <= tol and (best_miss is None or miss < best_miss):
            best_name, best_miss = name, miss
    return best_name


# ---- pure: lengths people type, descriptions ---------------------------------------------


def parse_signed_length(text, doc_units):
    """A signed length in document units from what people type ('-1\\' 6"', '+25mm',
    '-3.5', '0'), or None. Blank reads as 0."""
    raw = str(text or '').strip()
    if not raw:
        return 0.0
    sign = 1.0
    if raw[0] in '+-':
        sign = -1.0 if raw[0] == '-' else 1.0
        raw = raw[1:].strip()
        if not raw:
            return None
    from namo import units
    value = units.parse_length(raw, doc_units)
    if value is None:
        return None
    return sign * value


def format_length(value, doc_units):
    """A document-units length for display, the way people type it."""
    from namo import units
    text = units.format_length_input(abs(value), doc_units)
    sign = '-' if value < 0 and text not in ('0', '0\' 0"') else ''
    if units.is_imperial(doc_units):
        return sign + text
    return '%s%s %s' % (sign, text, units.doc_unit_symbol(doc_units))


def format_angle(degrees):
    text = ('%.3f' % float(degrees)).rstrip('0').rstrip('.')
    return ('0' if text in ('', '-0') else text) + u'°'


def describe(state, doc_units, factor=1.0):
    """Lines describing a model's transform for people: offset (document units),
    rotation, scale, units, reflection."""
    t = scale_vec(state['translation'], 1.0 / (factor or 1.0))
    angle, pure = z_angle(state['rotation'])
    scale = state.get('scale') or (1.0, 1.0, 1.0)
    lines = []
    if max(abs(v) for v in t) < 1e-9:
        lines.append('Offset: none')
    else:
        lines.append('Offset: X %s, Y %s, Z %s' % tuple(format_length(v, doc_units) for v in t))
    if is_identity_quat(state['rotation']):
        lines.append('Rotation: none')
    elif pure:
        lines.append('Rotation: %s about Z' % format_angle(angle))
    else:
        lines.append('Rotation: tilted (heading %s)' % format_angle(angle))
    if max(abs(s - 1.0) for s in scale) < 1e-9:
        lines.append('Scale: 1')
    elif max(scale) - min(scale) < 1e-9:
        lines.append('Scale: %g' % scale[0])
    else:
        lines.append('Scale: %g, %g, %g' % tuple(scale))
    lines.append('Units: %s%s' % (state.get('units') or 'unknown',
                                  ', reflected' if state.get('reflected') else ''))
    return lines


def is_identity_state(state, tol=1e-9):
    scale = state.get('scale') or (1.0, 1.0, 1.0)
    return (max(abs(v) for v in state['translation']) < tol and is_identity_quat(state['rotation'])
            and max(abs(s - 1.0) for s in scale) < tol and not state.get('reflected'))


def same_state(a, b, tol=1e-6):
    """True when two transform states (translation, rotation, scale, units) agree."""
    if (a.get('units') or '') != (b.get('units') or ''):
        return False
    for key in ('translation', 'scale'):
        va = a.get(key) or (1.0, 1.0, 1.0)
        vb = b.get(key) or (1.0, 1.0, 1.0)
        reach = max([1.0] + [abs(v) for v in va] + [abs(v) for v in vb])
        if max(abs(x - y) for x, y in zip(va, vb)) > tol * reach:
            return False
    qa, qb = quat_normalize(a['rotation']), quat_normalize(b['rotation'])
    dot = abs(sum(x * y for x, y in zip(qa, qb)))
    return dot > 1.0 - tol


# ---- pure: presets --------------------------------------------------------------------------


def preset_key(file_name):
    """Presets are per model FILE: the lowercased base name ('arch-l1.nwc')."""
    return os.path.basename(str(file_name or '').replace('\\', '/').split('/')[-1]).lower()


def preset_from(state, file_name, auto_apply=False):
    """A JSON-safe preset dict from a transform state."""
    return {'file': preset_key(file_name),
            'translation': [float(v) for v in state['translation']],
            'rotation': [float(v) for v in quat_normalize(state['rotation'])],
            'scale': [float(v) for v in (state.get('scale') or (1.0, 1.0, 1.0))],
            'scale_orientation': [float(v) for v in (state.get('scale_orientation') or (0.0, 0.0, 0.0, 1.0))],
            'units': state.get('units') or '',
            'reflected': bool(state.get('reflected')),
            'auto_apply': bool(auto_apply)}


def preset_state(preset):
    """The transform state a preset describes (tuples)."""
    return {'translation': tuple(float(v) for v in preset.get('translation') or (0, 0, 0)),
            'rotation': quat_normalize(preset.get('rotation') or (0, 0, 0, 1)),
            'scale': tuple(float(v) for v in preset.get('scale') or (1, 1, 1)),
            'scale_orientation': quat_normalize(preset.get('scale_orientation') or (0, 0, 0, 1)),
            'units': preset.get('units') or '',
            'reflected': bool(preset.get('reflected'))}


def match_presets(presets, file_names, auto_only=False):
    """[(file_name, preset_name, preset)] for the files that have a preset (by preset
    'file', falling back to the preset NAME as a file name). presets: {name: preset}."""
    by_file = {}
    for name in sorted(presets):
        preset = presets[name]
        key = preset.get('file') or preset_key(name)
        if auto_only and not preset.get('auto_apply'):
            continue
        by_file.setdefault(key, (name, preset))
    out = []
    for file_name in file_names:
        hit = by_file.get(preset_key(file_name))
        if hit is not None:
            out.append((file_name, hit[0], hit[1]))
    return out


def new_models(previous_keys, current_keys):
    """Keys present now that were not before, in current order (multiset-aware via
    the '#n' suffix of modelmgmt keys)."""
    before = set(previous_keys or [])
    return [k for k in current_keys if k not in before]


# ---- settings (shared by the button and the hook) ---------------------------------------


def load_settings():
    try:
        from pynavis import settings
        values = settings.load(SETTINGS_TOOL, SETTINGS_DEFAULTS)
    except Exception:
        values = dict(SETTINGS_DEFAULTS)
    if values.get('translation_units') not in CONVENTIONS:
        values['translation_units'] = 'model'
    return values


def save_settings(values):
    try:
        from pynavis import settings
        settings.save(SETTINGS_TOOL, values)
    except Exception:
        pass


def convention():
    return load_settings()['translation_units']


# ---- API half ---------------------------------------------------------------------------------


def _doc(doc):
    if doc is not None:
        return doc
    from pynavis._api import Application
    return Application.ActiveDocument


def _vec(v):
    return (float(v.X), float(v.Y), float(v.Z))


def _quat(r):
    return (float(r.A), float(r.B), float(r.C), float(r.D))


def read_state(model):
    """The transform state of a Model: {'translation' (transform units), 'rotation'
    (A, B, C, D), 'scale', 'scale_orientation', 'units', 'reflected', 'identity'}."""
    transform = model.Transform
    try:
        identity = bool(transform.IsIdentity())
    except Exception:
        identity = False
    parts = transform.Factor()
    state = {'translation': _vec(parts.Translation), 'rotation': _quat(parts.Rotation),
             'scale': _vec(parts.Scale), 'scale_orientation': _quat(parts.ScaleOrientation),
             'units': str(model.Units), 'reflected': bool(model.IsTransformReflected),
             'identity': identity}
    return state


def model_box(info):
    """World box of a model (document units) or None."""
    from namo import items as _items
    try:
        return _items.bbox(info['root'])
    except Exception:
        return None


def build_transform(model, state):
    """A Transform3D for `state`, built on the model's own Factor() components so the
    parts not being changed stay exactly as they are. Falls back to the
    Transform3D(Rotation3D, Vector3D) constructor when the components refuse writes
    and the model has no scale (raises ValueError when it has one)."""
    from pynavis._api import Api
    t = state['translation']
    q = quat_normalize(state['rotation'])
    translation = Api.Vector3D(float(t[0]), float(t[1]), float(t[2]))
    rotation = Api.Rotation3D(float(q[0]), float(q[1]), float(q[2]), float(q[3]))
    try:
        parts = model.Transform.Factor()
        parts.Translation = translation
        parts.Rotation = rotation
        if state.get('scale') is not None:
            s = state['scale']
            parts.Scale = Api.Vector3D(float(s[0]), float(s[1]), float(s[2]))
        if state.get('scale_orientation') is not None:
            so = quat_normalize(state['scale_orientation'])
            parts.ScaleOrientation = Api.Rotation3D(float(so[0]), float(so[1]), float(so[2]), float(so[3]))
        return parts.Combine()
    except Exception:
        scale = state.get('scale') or (1.0, 1.0, 1.0)
        if max(abs(v - 1.0) for v in scale) > 1e-9:
            raise ValueError('This model is scaled, and Navisworks would not take a new '
                             'transform that keeps the scale.')
        return Api.Transform3D(rotation, translation)


def units_enum(name):
    from pynavis._api import Api
    value = getattr(Api.Units, str(name), None)
    if value is None:
        raise ValueError('Unknown units %r' % (name,))
    return value


def write_state(document, index, state, units_name=None):
    """SetModelUnitsAndTransform for the model at index (no transaction here)."""
    model = document.Models[index]
    transform = build_transform(model, state)
    units = units_enum(units_name or state.get('units') or str(model.Units))
    reflected = bool(state.get('reflected', model.IsTransformReflected))
    document.Models.SetModelUnitsAndTransform(model, units, transform, reflected)


def move_models(keys, angle=0.0, origin='center', point=None, move=(0.0, 0.0, 0.0),
                units_name=None, doc=None, name='Transform models'):
    """Turns (about Z) and moves the models with these keys, one undo step.

    origin: 'center' (each model's own box centre), 'zero' (0, 0, 0) or 'point'
    (`point`, document units). move in document units. units_name changes the models'
    units too (None keeps them). Returns {'moved': [names], 'failed': [(name, why)],
    'checked': [(name, verdict)], 'corrected': bool, 'convention': str} where verdict
    is 'ok', 'corrected' or 'unverified'."""
    from pynavis.viewpoints import transaction
    from namo import modelmgmt
    document = _doc(doc)
    doc_units = str(document.Units)
    wanted = set(keys)
    infos = [i for i in modelmgmt.models_info(document) if i['key'] in wanted]
    current = convention()
    other = 'document' if current == 'model' else 'model'
    plans = []
    for info in infos:
        try:
            state = read_state(info['model'])
        except Exception as error:
            plans.append({'info': info, 'error': str(error) or 'could not read its transform'})
            continue
        box = model_box(info)
        if origin == 'center':
            pivot = tuple((box[0][i] + box[1][i]) / 2.0 for i in range(3)) if box else (0.0, 0.0, 0.0)
        elif origin == 'point' and point is not None:
            pivot = tuple(point)
        else:
            pivot = (0.0, 0.0, 0.0)
        model_units = units_name or state['units']
        factors = {}
        for conv in (current, other):
            factors[conv] = unit_factor(doc_units, state['units'], conv)
        planned = {}
        for conv in (current, other):
            t_new, q_new = compose(state['translation'], state['rotation'], angle, pivot, move,
                                   factors[conv])
            new_state = dict(state)
            new_state['translation'] = t_new
            new_state['rotation'] = q_new
            planned[conv] = new_state
        plans.append({'info': info, 'state': state, 'box': box, 'pivot': pivot,
                      'units': model_units, 'planned': planned, 'factors': factors})

    result = {'moved': [], 'failed': [], 'checked': [], 'corrected': False, 'convention': current}
    good = [p for p in plans if 'error' not in p]
    for plan in plans:
        if 'error' in plan:
            result['failed'].append((plan['info']['name'], plan['error']))
    if not good:
        return result
    with transaction(name, document):
        for plan in good:
            try:
                index = modelmgmt.resolve_index(plan['info']['key'], document)
                if index is None:
                    raise ValueError('it is no longer in the document')
                write_state(document, index, plan['planned'][current], plan['units'])
                plan['written'] = True
            except Exception as error:
                result['failed'].append((plan['info']['name'], str(error) or type(error).__name__))
    written = [p for p in good if p.get('written')]
    result['moved'] = [p['info']['name'] for p in written]

    # Measure: did each model land where the assumed convention says?
    redo = []
    for plan in written:
        info = modelmgmt.info_for(plan['info']['key'], document) or plan['info']
        after = model_box(info)
        if plan['box'] is None or after is None or plan['units'] != plan['state']['units']:
            result['checked'].append((plan['info']['name'], 'unverified'))
            continue
        e = delta_translation(angle, plan['pivot'], move)
        k = plan['factors'][current] / (plan['factors'][other] or 1.0)
        predictions = [('ok', predict_box(plan['box'], angle, e))]
        if abs(k - 1.0) > 1e-9:
            predictions.append(('other', predict_box(plan['box'], angle, scale_vec(e, k))))
        verdict = judge(after, predictions, angle, tolerance_for(plan['box']))
        if verdict == 'other':
            redo.append(plan)
        else:
            result['checked'].append((plan['info']['name'], 'ok' if verdict == 'ok' else 'unverified'))
    if redo:
        with transaction(name, document):
            for plan in redo:
                index = modelmgmt.resolve_index(plan['info']['key'], document)
                if index is None:
                    continue
                write_state(document, index, plan['planned'][other], plan['units'])
                result['checked'].append((plan['info']['name'], 'corrected'))
        values = load_settings()
        values['translation_units'] = other
        save_settings(values)
        result['corrected'] = True
        result['convention'] = other
        try:
            from namo import session
            session.log('info', 'Transform Fixer: model offsets are in %s units here; remembered'
                        % other)
        except Exception:
            pass
    return result


def set_units(keys, units_name, doc=None):
    """Changes the models' units (geometry rescales about the model origin), keeping
    their transforms. One undo step. Returns the names changed."""
    from pynavis.viewpoints import transaction
    from namo import modelmgmt
    document = _doc(doc)
    wanted = set(keys)
    done = []
    with transaction('Change model units', document):
        for info in modelmgmt.models_info(document):
            if info['key'] not in wanted:
                continue
            state = read_state(info['model'])
            write_state(document, info['index'], state, units_name)
            done.append(info['name'])
    return done


def reset_models(keys, doc=None):
    """Puts the models' transforms back to identity (units kept). One undo step."""
    from pynavis._api import Api
    from pynavis.viewpoints import transaction
    from namo import modelmgmt
    document = _doc(doc)
    wanted = set(keys)
    done = []
    with transaction('Reset model transforms', document):
        for info in modelmgmt.models_info(document):
            if info['key'] not in wanted:
                continue
            model = info['model']
            document.Models.SetModelUnitsAndTransform(model, model.Units,
                                                      Api.Transform3D.CreateIdentity(), False)
            done.append(info['name'])
    return done


# ---- presets (API) ------------------------------------------------------------------------------


def preset_store():
    from namo import templates
    return templates.Templates(PRESETS_TOOL)


def all_presets():
    """{name: preset} from the team templates."""
    store = preset_store()
    out = {}
    for name in store.names():
        value = store.get(name)
        if isinstance(value, dict):
            out[name] = value
    return out


def save_preset(info, auto_apply=False, name=None):
    """Saves the model's current transform as the preset for its file. Returns the
    stored name (the file's base name unless one is given)."""
    state = read_state(info['model'])
    file_name = info['source'] or info['file'] or info['name']
    preset = preset_from(state, file_name, auto_apply)
    return preset_store().save(name or os.path.basename(str(file_name).replace('\\', '/').split('/')[-1]),
                               preset)


def apply_presets(pairs, doc=None, name='Apply transform presets'):
    """pairs [(model key, preset)]: writes each preset's absolute transform, one undo
    step. Models already in that state are skipped. Returns (applied names, failed)."""
    from pynavis.viewpoints import transaction
    from namo import modelmgmt
    document = _doc(doc)
    applied, failed = [], []
    todo = []
    for key, preset in pairs:
        info = modelmgmt.info_for(key, document)
        if info is None:
            continue
        target = preset_state(preset)
        try:
            state = read_state(info['model'])
        except Exception as error:
            failed.append((info['name'], str(error)))
            continue
        if not target['units']:
            target['units'] = state['units']
        if same_state(state, target):
            continue
        todo.append((info, target))
    if not todo:
        return applied, failed
    with transaction(name, document):
        for info, target in todo:
            try:
                index = modelmgmt.resolve_index(info['key'], document)
                if index is None:
                    continue
                write_state(document, index, target, target['units'])
                applied.append(info['name'])
            except Exception as error:
                failed.append((info['name'], str(error) or type(error).__name__))
    return applied, failed


def apply_auto_presets(keys, doc=None):
    """Applies auto_apply presets to the models with these keys (just appended).
    Returns (applied names, failed). Never raises."""
    try:
        from namo import modelmgmt
        presets = all_presets()
        if not presets:
            return [], []
        document = _doc(doc)
        wanted = set(keys)
        infos = [i for i in modelmgmt.models_info(document) if i['key'] in wanted]
        pairs = []
        for info in infos:
            hits = match_presets(presets, [info['source'] or info['file'] or info['name']], auto_only=True)
            if not hits:
                hits = match_presets(presets, [info['file']], auto_only=True) if info['file'] else []
            if hits:
                pairs.append((info['key'], hits[0][2]))
        if not pairs:
            return [], []
        return apply_presets(pairs, document, 'Apply transform presets')
    except Exception as error:
        try:
            from namo import session
            session.log('error', 'transform presets failed: %s' % error)
        except Exception:
            pass
        return [], [('presets', str(error))]
