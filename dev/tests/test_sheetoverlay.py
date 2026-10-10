# -*- coding: utf-8 -*-
"""namo.sheetoverlay pure half: placement maths, filtering, captions, validation."""

import _compat
from _compat import approx, raises

from namo import sheetoverlay


DRAWING = {
    'segments': [((0.0, 0.0), (1000.0, 0.0), 'WALLS'), ((0.0, 0.0), (0.0, 500.0), 'GRID'),
                 ((10.0, 10.0), (20.0, 10.0), 'WALLS')],
    'texts': [{'text': 'Office', 'x': 100.0, 'y': 100.0, 'height': 50.0, 'rotation': 0.0, 'layer': 'ROOMS'},
              {'text': 'A', 'x': 0.0, 'y': 0.0, 'height': 50.0, 'rotation': 0.0, 'layer': 'GRID'}],
    'layers': {'WALLS': 2, 'GRID': 1}, 'units': 4, 'units_name': 'Millimeters',
}


def test_unit_scale():
    assert approx(sheetoverlay.unit_scale('Millimeters', 'Meters'), 0.001)
    assert approx(sheetoverlay.unit_scale('Feet', 'Inches'), 12.0)
    assert sheetoverlay.unit_scale('Meters', 'Meters') == 1.0


def test_to_model_scale_rotation_offset():
    placement = {'scale': 0.001, 'rotation': 90.0, 'dx': 10.0, 'dy': 20.0}
    assert approx(sheetoverlay.to_model((1000.0, 0.0), placement), (10.0, 21.0), 1e-9)
    assert approx(sheetoverlay.to_model((0.0, 0.0), placement), (10.0, 20.0))


def test_from_points_free_and_fixed_scale():
    p1, p2 = (0.0, 0.0), (10000.0, 0.0)            # drawing mm
    q1, q2 = (100.0, 50.0), (100.0, 60.0)          # model m, the grid runs north
    s, rot, dx, dy = sheetoverlay.from_points(p1, p2, q1, q2)
    assert approx(s, 0.001) and approx(rot, 90.0) and approx((dx, dy), (100.0, 50.0))
    placement = {'scale': s, 'rotation': rot, 'dx': dx, 'dy': dy}
    assert approx(sheetoverlay.to_model(p2, placement), q2, 1e-9)
    s2, rot2, dx2, dy2 = sheetoverlay.from_points(p1, p2, q1, (100.0, 70.0), fixed_scale=0.001)
    assert s2 == 0.001 and approx(rot2, 90.0)
    assert approx(sheetoverlay.to_model(p1, {'scale': s2, 'rotation': rot2, 'dx': dx2, 'dy': dy2}), q1)
    raises(ValueError, sheetoverlay.from_points, p1, p1, q1, q2)
    raises(ValueError, sheetoverlay.from_points, p1, p2, q1, q1)


def test_rotation_is_normalised():
    _s, rot, _dx, _dy = sheetoverlay.from_points((0, 0), (1, 0), (0, 0), (0, -1))
    assert approx(rot, -90.0)


def test_parse_xy():
    assert sheetoverlay.parse_xy('12.5, 3') == (12.5, 3.0)
    assert sheetoverlay.parse_xy('X=1 Y=-2') == (1.0, -2.0)
    assert sheetoverlay.parse_xy('(4;5)') == (4.0, 5.0)
    assert sheetoverlay.parse_xy('1, 2, 3') is None
    assert sheetoverlay.parse_xy('a, b') is None
    assert sheetoverlay.parse_xy(None) is None


def test_segments_filter_layers_and_cap():
    placement = {'scale': 0.001, 'rotation': 0.0, 'dx': 0.0, 'dy': 0.0, 'elevation': 4.2, 'layers': ['WALLS']}
    segs, total = sheetoverlay.segments_3d(DRAWING, placement)
    assert total == 2 and len(segs) == 2
    assert segs[0] == ((0.0, 0.0, 4.2), (1.0, 0.0, 4.2), False)
    placement['layers'] = None
    segs, total = sheetoverlay.segments_3d(DRAWING, placement, cap=1)
    assert total == 3 and len(segs) == 1


def test_labels_and_texts_switch():
    placement = {'scale': 0.001, 'rotation': 0.0, 'dx': 1.0, 'dy': 0.0, 'elevation': 0.0, 'layers': None,
                 'texts': True}
    items, total = sheetoverlay.labels(DRAWING, placement)
    assert total == 2 and items[0] == ('Office', (1.1, 0.1, 0.0))
    placement['texts'] = False
    assert sheetoverlay.labels(DRAWING, placement) == ([], 0)
    placement.update({'texts': True, 'layers': ['WALLS']})
    assert sheetoverlay.labels(DRAWING, placement) == ([], 0)


def test_tick_is_flat():
    segs = sheetoverlay.tick((1.0, 2.0, 3.0), 0.5)
    assert len(segs) == 2 and all(a[2] == 3.0 and b[2] == 3.0 for a, b, _d in segs)


def test_describe_outcomes():
    placement = {'file': r'C:\plans\L2.dxf', 'elevation': 4.2}
    level, message, detail = sheetoverlay.describe(DRAWING, placement, 3, 3, 1, 1, 'Meters', 'Level 2')
    assert level == 'success' and message == 'Sheet placed'
    assert detail.startswith('L2.dxf: 3 lines, 1 label at Level 2.')
    level, message, detail = sheetoverlay.describe(DRAWING, placement, 30000, 41000, 0, 0, 'Meters')
    assert level == 'warning' and 'Showing 30,000 of 41,000 lines.' in detail and '4.200 m' in detail


def test_validate_placement_values():
    good = {'mode': 'manual', 'elevation_choice': 'typed', 'elevation': '-3.5', 'dx': '0', 'dy': '-1250'}
    assert sheetoverlay.validate(good, 'Millimeters') is None
    bad = {'mode': 'manual', 'elevation_choice': 'typed', 'elevation': 'abc', 'dx': 'x', 'dy': '1'}
    errors = sheetoverlay.validate(bad, 'Meters')
    assert set(errors) == set(['elevation', 'dx'])
    points = {'mode': 'points', 'elevation_choice': 'level:L1', 'p1': '0, 0', 'p2': '0,0'}
    assert 'p2' in sheetoverlay.validate(points)
    points['p1'] = 'nope'
    assert 'p1' in sheetoverlay.validate(points)
    points.update({'p1': '0, 0', 'p2': '10, 0'})
    assert sheetoverlay.validate(points) is None


def test_placement_fields_are_a_valid_form():
    from namo import ui
    options = [('Level 1 (0.000 m)', 'level:Level 1'), ('Type an elevation', 'typed')]
    fields = sheetoverlay.placement_fields(DRAWING, {}, options, 'Meters')
    import test_vp_common as vpfake
    vpfake.check_defaults(fields)
    specs = ui.normalize_fields(fields)
    keys = [f.get('key') for f in specs]
    assert 'elevation' in keys and 'p1' in keys and 'units_choice' in keys
    unit_field = [f for f in specs if f.get('key') == 'units_choice'][0]
    assert unit_field['default'] == 'file'
    plain = dict(DRAWING, units_name=None)
    unit_field = [f for f in ui.normalize_fields(sheetoverlay.placement_fields(plain, {}, options, 'Feet'))
                  if f.get('key') == 'units_choice'][0]
    assert unit_field['default'] == 'Feet'


def test_drawing_units_choice():
    assert sheetoverlay.drawing_units_of({'units_choice': 'file'}, DRAWING, 'Meters') == 'Millimeters'
    assert sheetoverlay.drawing_units_of({'units_choice': 'Feet'}, DRAWING, 'Meters') == 'Feet'
    assert sheetoverlay.drawing_units_of({'units_choice': 'file'}, {'units_name': None}, 'Inches') == 'Inches'


def test_pick_prompts_name_both_drawing_points():
    first, second = sheetoverlay.pick_prompts(' 0, 0 ', '40, 3')
    assert first == 'Click the model point that matches drawing point 1 (0, 0)'
    assert second == 'Now click the model point that matches drawing point 2 (40, 3)'


def test_two_reference_points_far_from_the_origin():
    # Shared coordinates: the model sits about 1,370,000 ft out. The placement must put
    # both drawing points back on the picked model points to well under a millimetre.
    q1, q2 = (1370000.25, 1370100.5, 12.0), (1370040.25, 1370100.5, 12.0)
    scale, rotation, dx, dy = sheetoverlay.from_points((0.0, 0.0), (12192.0, 0.0), q1, q2)
    placement = {'scale': scale, 'rotation': rotation, 'dx': dx, 'dy': dy}
    a = sheetoverlay.to_model((0.0, 0.0), placement)
    b = sheetoverlay.to_model((12192.0, 0.0), placement)
    assert abs(a[0] - q1[0]) < 1e-6 and abs(a[1] - q1[1]) < 1e-6
    assert abs(b[0] - q2[0]) < 1e-6 and abs(b[1] - q2[1]) < 1e-6
    assert abs(scale - 40.0 / 12192.0) < 1e-12 and abs(rotation) < 1e-9
