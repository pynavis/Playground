# -*- coding: utf-8 -*-
"""namo.transforms: quaternion maths, composing moves, predicting boxes, the units
convention judge, presets, and the API half driven through a fake whose model box
really moves (so the self-correcting units convention is exercised)."""
import math
import sys
import types

import _compat
from _compat import approx

from namo import transforms as tf


def test_quat_about_z_and_rotate():
    q = tf.quat_about_z(90)
    v = tf.quat_rotate(q, (1.0, 0.0, 0.0))
    assert approx(v, (0.0, 1.0, 0.0), 1e-12)
    assert approx(tf.rotate_z((1.0, 0.0, 5.0), 90), (0.0, 1.0, 5.0), 1e-12)
    # quaternion rotation and the plain Z rotation agree for any angle
    for angle in (-170, -33.3, 0, 12.5, 135):
        a = tf.quat_rotate(tf.quat_about_z(angle), (3.0, -2.0, 1.0))
        b = tf.rotate_z((3.0, -2.0, 1.0), angle)
        assert approx(a, b, 1e-12)


def test_quat_mul_composes_in_order():
    q = tf.quat_mul(tf.quat_about_z(30), tf.quat_about_z(60))
    angle, pure = tf.z_angle(q)
    assert pure and abs(angle - 90.0) < 1e-9
    # x-axis tilt then z turn: not pure
    tilt = (math.sin(math.radians(10)), 0.0, 0.0, math.cos(math.radians(10)))
    angle, pure = tf.z_angle(tf.quat_mul(tf.quat_about_z(45), tilt))
    assert not pure and abs(angle - 45.0) < 1e-6


def test_z_angle_range_and_identity():
    assert tf.z_angle((0, 0, 0, 1)) == (0.0, True)
    angle, pure = tf.z_angle(tf.quat_about_z(270))
    assert pure and abs(angle + 90.0) < 1e-9
    assert tf.is_identity_quat((0, 0, 0, 2.0))
    assert not tf.is_identity_quat(tf.quat_about_z(1))


def test_compose_translation_only():
    t, q = tf.compose((10.0, 0.0, 0.0), (0, 0, 0, 1), 0.0, (0, 0, 0), (1.0, 2.0, 3.0))
    assert approx(t, (11.0, 2.0, 3.0)) and approx(q, (0, 0, 0, 1))


def test_compose_rotation_about_origin_point():
    # a model at offset (10, 0, 0) turned 90 degrees about (10, 0, 0) keeps its offset
    t, q = tf.compose((10.0, 0.0, 0.0), (0, 0, 0, 1), 90.0, (10.0, 0.0, 0.0), (0, 0, 0))
    assert approx(t, (10.0, 0.0, 0.0), 1e-12)
    assert abs(tf.z_angle(q)[0] - 90.0) < 1e-9
    # turned about the world origin it swings to (0, 10, 0)
    t, q = tf.compose((10.0, 0.0, 0.0), (0, 0, 0, 1), 90.0, (0, 0, 0), (0, 0, 0))
    assert approx(t, (0.0, 10.0, 0.0), 1e-12)


def test_compose_with_unit_factor():
    # transform in millimetres, document in metres: factor 1000
    t, q = tf.compose((5000.0, 0.0, 0.0), (0, 0, 0, 1), 0.0, (0, 0, 0), (1.0, 0.0, 0.0), 1000.0)
    assert approx(t, (6000.0, 0.0, 0.0))


def test_unit_factor():
    assert tf.unit_factor('Meters', 'Millimeters', 'model') == 1000.0
    assert tf.unit_factor('Meters', 'Millimeters', 'document') == 1.0
    assert approx(tf.unit_factor('Feet', 'Inches', 'model'), 12.0)
    assert tf.unit_factor('Meters', 'Bananas', 'model') == 1.0


def test_predict_box_and_delta():
    box = ((0.0, 0.0, 0.0), (2.0, 1.0, 1.0))
    e = tf.delta_translation(90.0, (0.0, 0.0, 0.0), (10.0, 0.0, 0.0))
    assert approx(e, (10.0, 0.0, 0.0))
    p = tf.predict_box(box, 90.0, e)
    assert approx(p[0], (9.0, 0.0, 0.0), 1e-12) and approx(p[1], (10.0, 2.0, 1.0), 1e-12)
    e = tf.delta_translation(90.0, (1.0, 0.5, 0.0), (0, 0, 0))
    p = tf.predict_box(box, 90.0, e)
    centre = tuple((p[0][i] + p[1][i]) / 2 for i in range(3))
    assert approx(centre, (1.0, 0.5, 0.5), 1e-12)
    assert tf.predict_box(None, 0, (0, 0, 0)) is None


def test_judge_right_angles_and_containment():
    box = ((0.0, 0.0, 0.0), (4.0, 2.0, 3.0))
    moved = ((1.0, 0.0, 0.0), (5.0, 2.0, 3.0))
    tol = tf.tolerance_for(box)
    preds = [('ok', tf.predict_box(box, 0, (1.0, 0, 0))), ('other', tf.predict_box(box, 0, (1000.0, 0, 0)))]
    assert tf.judge(moved, preds, 0, tol) == 'ok'
    far = ((1000.0, 0.0, 0.0), (1004.0, 2.0, 3.0))
    assert tf.judge(far, preds, 0, tol) == 'other'
    assert tf.judge(((50.0, 0, 0), (54.0, 2, 3)), preds, 0, tol) is None
    # 30 degrees: the actual box sits inside the rotated corners
    preds = [('ok', tf.predict_box(box, 30, (0, 0, 0)))]
    inner = ((0.5, 0.8, 0.0), (2.5, 2.2, 3.0))
    assert tf.judge(inner, preds, 30, tol) == 'ok'
    assert tf.judge(None, preds, 30, tol) is None
    assert tf.is_right_angle(-270) and not tf.is_right_angle(45)


def test_parse_signed_length():
    assert tf.parse_signed_length('', 'Meters') == 0.0
    assert tf.parse_signed_length('-2.5', 'Meters') == -2.5
    assert abs(tf.parse_signed_length('+25mm', 'Meters') - 0.025) < 1e-12
    assert abs(tf.parse_signed_length("-1' 6\"", 'Feet') + 1.5) < 1e-12
    assert tf.parse_signed_length('-', 'Meters') is None
    assert tf.parse_signed_length('banana', 'Meters') is None


def test_describe_and_identity_state():
    state = {'translation': (2000.0, 0.0, -500.0), 'rotation': tf.quat_about_z(15),
             'scale': (1.0, 1.0, 1.0), 'units': 'Millimeters', 'reflected': False}
    lines = tf.describe(state, 'Meters', factor=1000.0)
    assert lines[0] == 'Offset: X 2 m, Y 0 m, Z -0.5 m'
    assert lines[1] == u'Rotation: 15\u00b0 about Z'
    assert lines[2] == 'Scale: 1' and lines[3] == 'Units: Millimeters'
    ident = {'translation': (0, 0, 0), 'rotation': (0, 0, 0, 1), 'scale': (1, 1, 1), 'units': 'Feet'}
    assert tf.describe(ident, 'Feet')[0] == 'Offset: none'
    assert tf.is_identity_state(ident) and not tf.is_identity_state(state)
    feet = tf.describe({'translation': (1.5, 0, 0), 'rotation': (0, 0, 0, 1), 'scale': (2, 2, 2),
                        'units': 'Feet', 'reflected': True}, 'Feet')
    assert feet[0].startswith("Offset: X 1' 6\"") and feet[2] == 'Scale: 2'
    assert feet[3] == 'Units: Feet, reflected'


def test_same_state():
    a = {'translation': (1.0, 2.0, 3.0), 'rotation': tf.quat_about_z(10), 'scale': (1, 1, 1), 'units': 'Meters'}
    b = dict(a)
    b['rotation'] = tuple(-v for v in a['rotation'])        # same rotation, opposite sign
    assert tf.same_state(a, b)
    c = dict(a)
    c['translation'] = (1.0, 2.0, 3.1)
    assert not tf.same_state(a, c)
    d = dict(a)
    d['units'] = 'Feet'
    assert not tf.same_state(a, d)


def test_presets_round_trip_and_matching():
    state = {'translation': (1.0, 2.0, 3.0), 'rotation': tf.quat_about_z(30), 'scale': (1, 1, 1),
             'units': 'Meters', 'reflected': False}
    preset = tf.preset_from(state, r'C:\Models\ARCH-L1.nwc', auto_apply=True)
    assert preset['file'] == 'arch-l1.nwc' and preset['auto_apply'] is True
    back = tf.preset_state(preset)
    assert tf.same_state(state, back)
    presets = {'ARCH-L1.nwc': preset, 'MEP.nwc': dict(preset, file='mep.nwc', auto_apply=False)}
    hits = tf.match_presets(presets, [r'D:\x\arch-l1.NWC', 'mep.nwc', 'other.nwc'])
    assert [(h[0], h[1]) for h in hits] == [(r'D:\x\arch-l1.NWC', 'ARCH-L1.nwc'), ('mep.nwc', 'MEP.nwc')]
    hits = tf.match_presets(presets, ['mep.nwc', 'arch-l1.nwc'], auto_only=True)
    assert [h[1] for h in hits] == ['ARCH-L1.nwc']
    assert tf.new_models(['a#0', 'b#0'], ['a#0', 'b#0', 'b#1', 'c#0']) == ['b#1', 'c#0']


# ---------------------------------------------------------------------------------------------
# API half through a fake: SetModelUnitsAndTransform moves the model's box.
# ---------------------------------------------------------------------------------------------

import test_items as nav  # noqa: E402


class FakeTransform(object):
    def __init__(self, t=(0.0, 0.0, 0.0), q=(0.0, 0.0, 0.0, 1.0), s=(1.0, 1.0, 1.0)):
        self.t, self.q, self.s = tuple(t), tf.quat_normalize(q), tuple(s)

    @staticmethod
    def CreateIdentity():
        return FakeTransform()

    def IsIdentity(self):
        return tf.is_identity_state({'translation': self.t, 'rotation': self.q, 'scale': self.s})

    def Factor(self):
        return FakeParts(self)


class FakeParts(object):
    def __init__(self, transform):
        self.Translation = nav.Vector3D(*transform.t)
        self.Rotation = nav.Rotation3D(*transform.q)
        self.Scale = nav.Vector3D(*transform.s)
        self.ScaleOrientation = nav.Rotation3D(0, 0, 0, 1)

    def Combine(self):
        return FakeTransform(self.Translation.t(), (self.Rotation.A, self.Rotation.B, self.Rotation.C,
                                                    self.Rotation.D), self.Scale.t())


class MovingRoot(nav.ModelItem):
    """A model root whose box is its base box (model units) under the model transform,
    with the translation read in `convention` units ('model' or 'document')."""

    def __init__(self, name, base_box, model_ref, convention, doc_to_m, model_to_m):
        nav.ModelItem.__init__(self, name, geometry=True)
        self.base_box = base_box
        self.model_ref = model_ref
        self.convention = convention
        self.doc_to_m = doc_to_m
        self.model_to_m = model_to_m

    def BoundingBox(self):
        model = self.model_ref[0]
        tr = model.Transform
        s = self.model_to_m / self.doc_to_m              # model units -> document units
        pts = []
        for c in tf.corners(self.base_box):
            p = tf.quat_rotate(tr.q, (c[0] * s, c[1] * s, c[2] * s))
            k = s if self.convention == 'model' else 1.0
            pts.append(tf.add(p, tf.scale_vec(tr.t, k)))
        box = tf.aabb(pts)
        return nav.BoundingBox3D(nav.Point3D(*box[0]), nav.Point3D(*box[1]))


class FakeModel(object):
    def __init__(self, name, units):
        self.FileName = r'C:\M\%s' % name
        self.SourceFileName = r'C:\M\%s' % name.replace('.nwc', '.rvt')
        self.Units = units
        self.Creator = 'Revit'
        self.Guid = 'g-' + name
        self.Transform = FakeTransform()
        self.IsTransformReflected = False
        self.RootItem = None


class FakeModels(nav.DocumentModels):
    def __init__(self, models):
        nav.DocumentModels.__init__(self, models)
        self.writes = []

    def SetModelUnitsAndTransform(self, model, units, transform, reflected):
        self.writes.append((model.FileName, units, transform.t, transform.q, reflected))
        model.Transform = transform
        model.Units = units


def _doc(convention='model', doc_units='Meters', model_units='Millimeters'):
    from namo import units
    model = FakeModel('ARCH.nwc', model_units)
    ref = [model]
    root = MovingRoot('ARCH.nwc', ((0.0, 0.0, 0.0), (4000.0, 2000.0, 3000.0)), ref, convention,
                      units.to_meters(1, doc_units), units.to_meters(1, model_units))
    model.RootItem = root
    doc = nav.Document()
    doc.Units = doc_units
    doc.Models = FakeModels([model])
    return doc, model


class _Settings(object):
    def __init__(self):
        self.store = {}

    def load(self, tool, defaults):
        out = dict(defaults)
        out.update(self.store.get(tool, {}))
        return out

    def save(self, tool, values):
        self.store[tool] = dict(values)


def _with_fake(doc, fn):
    with nav.FakeNav(doc) as fake:
        fake.Api.Units = nav._Ns(Meters='Meters', Millimeters='Millimeters', Feet='Feet')
        fake.Api.Transform3D = FakeTransform
        settings_module = types.ModuleType('pynavis.settings')
        holder = _Settings()
        settings_module.load = holder.load
        settings_module.save = holder.save
        sys.modules['pynavis.settings'] = settings_module
        sys.modules['pynavis'].settings = settings_module
        try:
            return fn(fake, holder)
        finally:
            sys.modules.pop('pynavis.settings', None)


def test_read_state_and_identity():
    doc, model = _doc()

    def run(fake, holder):
        state = tf.read_state(model)
        assert state['units'] == 'Millimeters' and state['identity']
        assert state['translation'] == (0.0, 0.0, 0.0)
    _with_fake(doc, run)


def test_move_models_matching_convention_is_one_step():
    doc, model = _doc(convention='model')

    def run(fake, holder):
        from namo import modelmgmt
        key = modelmgmt.models_info(doc)[0]['key']
        result = tf.move_models([key], angle=0.0, origin='zero', move=(1.0, 0.0, 0.0), doc=doc)
        assert result['moved'] == ['ARCH.rvt'] and not result['corrected']
        assert result['checked'] == [('ARCH.rvt', 'ok')]
        assert doc.transactions == ['Transform models']
        assert approx(model.Transform.t, (1000.0, 0.0, 0.0))     # millimetres
    _with_fake(doc, run)


def test_move_models_corrects_the_other_convention_and_learns():
    doc, model = _doc(convention='document')

    def run(fake, holder):
        from namo import modelmgmt
        key = modelmgmt.models_info(doc)[0]['key']
        result = tf.move_models([key], angle=0.0, origin='zero', move=(1.0, 0.0, 0.0), doc=doc)
        assert result['corrected'] and result['convention'] == 'document'
        assert result['checked'] == [('ARCH.rvt', 'corrected')]
        assert approx(model.Transform.t, (1.0, 0.0, 0.0))
        assert holder.store[tf.SETTINGS_TOOL]['translation_units'] == 'document'
        box = model.RootItem.BoundingBox()
        assert approx((box.Min.X, box.Min.Y), (1.0, 0.0))
        # the next move uses the learned convention first time
        result = tf.move_models([key], angle=0.0, origin='zero', move=(0.0, 2.0, 0.0), doc=doc)
        assert not result['corrected'] and result['checked'] == [('ARCH.rvt', 'ok')]
        assert approx(model.Transform.t, (1.0, 2.0, 0.0))
    _with_fake(doc, run)


def test_move_models_rotation_about_centre():
    doc, model = _doc(convention='model', doc_units='Meters', model_units='Meters')
    model.RootItem.base_box = ((0.0, 0.0, 0.0), (4.0, 2.0, 3.0))
    model.RootItem.model_to_m = 1.0

    def run(fake, holder):
        from namo import modelmgmt
        key = modelmgmt.models_info(doc)[0]['key']
        result = tf.move_models([key], angle=90.0, origin='center', doc=doc)
        assert result['checked'] == [('ARCH.rvt', 'ok')]
        box = model.RootItem.BoundingBox()
        centre = ((box.Min.X + box.Max.X) / 2, (box.Min.Y + box.Max.Y) / 2)
        assert approx(centre, (2.0, 1.0), 1e-9)
        assert abs((box.Max.X - box.Min.X) - 2.0) < 1e-9
    _with_fake(doc, run)


def test_apply_presets_skips_models_already_there():
    doc, model = _doc()

    def run(fake, holder):
        from namo import modelmgmt
        key = modelmgmt.models_info(doc)[0]['key']
        preset = tf.preset_from({'translation': (500.0, 0, 0), 'rotation': (0, 0, 0, 1),
                                 'scale': (1, 1, 1), 'units': 'Millimeters'}, 'ARCH.rvt', True)
        applied, failed = tf.apply_presets([(key, preset)], doc)
        assert applied == ['ARCH.rvt'] and not failed
        assert approx(model.Transform.t, (500.0, 0.0, 0.0))
        applied, failed = tf.apply_presets([(key, preset)], doc)
        assert applied == [] and not failed
        assert doc.transactions == ['Apply transform presets']
    _with_fake(doc, run)


def test_reset_models():
    doc, model = _doc()
    model.Transform = FakeTransform((5.0, 0, 0))

    def run(fake, holder):
        from namo import modelmgmt
        key = modelmgmt.models_info(doc)[0]['key']
        assert tf.reset_models([key], doc) == ['ARCH.rvt']
        assert model.Transform.IsIdentity()
    _with_fake(doc, run)


# ---- refit: models a long way from the origin (shared coordinates, 1.37 million ft) ----


def test_judge_takes_the_nearest_prediction_far_from_the_origin():
    far = 1370000.0
    box = ((far, far, 0.0), (far + 300.0, far + 200.0, 60.0))
    tol = tf.tolerance_for(box)
    assert tol > 0.5                    # float32 noise out there is about 0.65 ft
    # a 1 ft move in a document in feet with the model in metres: the two conventions
    # land 0.7 ft apart, closer together than the tolerance
    wanted, other = (1.0, 0.0, 0.0), (0.3048, 0.0, 0.0)
    preds = [('ok', tf.predict_box(box, 0, wanted)), ('other', tf.predict_box(box, 0, other))]
    assert tf.judge(tf.predict_box(box, 0, wanted), preds, 0, tol) == 'ok'
    assert tf.judge(tf.predict_box(box, 0, other), preds, 0, tol) == 'other'
    assert tf.judge(tf.predict_box(box, 0, (40.0, 0.0, 0.0)), preds, 0, tol) is None


def test_tolerances_scale_with_distance_from_the_origin():
    near = ((0.0, 0.0, 0.0), (1.0, 1.0, 1.0))
    assert tf.tolerance_for(near) < 0.01
    assert approx(tf.float32_noise(1370000.0), 1370000.0 * 4 * 2.0 ** -23)
    assert tf.tolerance_for(None) > 0.0
    # picked points: a real 1/64 in move out there is a move, identical points are not
    a = (1370000.0, 1370000.0, 12.0)
    b = (1370000.0 + 1.0 / 768.0, 1370000.0, 12.0)
    assert max(abs(b[i] - a[i]) for i in range(3)) > tf.point_noise((a, b))
    assert 0.0 <= tf.point_noise((a, a)) < 1e-6
    assert tf.point_noise(((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))) > 0.0
