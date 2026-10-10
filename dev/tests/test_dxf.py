# -*- coding: utf-8 -*-
"""namo.dxf: group codes, entities, blocks, coordinate systems, tessellation."""
import math

import _compat
from _compat import approx, raises

from namo import dxf


def _dxf(*sections):
    """A DXF text from (name, [lines]) sections; lines are 'code', 'value' pairs."""
    out = []
    for name, body in sections:
        out += ['0', 'SECTION', '2', name] + list(body) + ['0', 'ENDSEC']
    out += ['0', 'EOF']
    return '\n'.join(out) + '\n'


def _ent(kind, *codes):
    out = ['0', kind]
    for code, value in codes:
        out += [str(code), str(value)]
    return out


def _seg_set(drawing, places=6):
    return sorted((round(a[0], places), round(a[1], places), round(b[0], places), round(b[1], places))
                  for a, b, _l in drawing['segments'])


# ---- pairs and decoding ---------------------------------------------------------------


def test_pairs_tolerates_spaces_crlf_and_junk():
    text = '  0\r\nSECTION\r\n  2\r\nENTITIES\r\njunk\r\n  0\r\nLINE\r\n'
    pairs = dxf.pairs(text)
    assert pairs[0] == (0, 'SECTION')
    assert pairs[1] == (2, 'ENTITIES')
    assert (0, 'LINE') in pairs


def test_decode_utf8_and_cp1252_and_binary():
    assert dxf.decode('abc') == 'abc'
    assert dxf.decode(u'Ø 12'.encode('utf-8')) == u'Ø 12'
    assert dxf.decode(b'caf\xe9') == u'caf\xe9'
    raises(ValueError, dxf.decode, b'AutoCAD Binary DXF\r\n\x1a\x00')


def test_empty_text_is_refused():
    raises(ValueError, dxf.read, '')
    raises(ValueError, dxf.read, 'hello\nworld\n')


# ---- maths ---------------------------------------------------------------------------


def test_ocs_axes_identity_and_mirror():
    ax, ay, az = dxf.ocs_axes((0, 0, 1))
    assert approx(ax, (1, 0, 0)) and approx(ay, (0, 1, 0)) and approx(az, (0, 0, 1))
    m = dxf.ocs_matrix((0, 0, -1))
    assert approx(dxf.apply(m, (2.0, 3.0, 0.0)), (-2.0, 3.0, 0.0))


def test_matrices_compose_in_order():
    m = dxf.matmul(dxf.translation(10, 0), dxf.rotation_z(90))
    assert approx(dxf.apply(m, (1.0, 0.0, 0.0)), (10.0, 1.0, 0.0), 1e-9)


def test_arc_points_counter_clockwise_and_wrap():
    pts = dxf.arc_points(0, 0, 1, 0, 90, 10)
    assert approx(pts[0], (1, 0)) and approx(pts[-1], (0, 1), 1e-9)
    assert len(pts) == 10
    wrap = dxf.arc_points(0, 0, 1, 350, 10, 10)
    assert approx(wrap[0], (math.cos(math.radians(350)), math.sin(math.radians(350))))
    assert approx(wrap[-1], (math.cos(math.radians(10)), math.sin(math.radians(10))), 1e-9)
    circle = dxf.arc_points(0, 0, 2, 0, 360, 10)
    assert len(circle) == 37 and approx(circle[0], circle[-1], 1e-9)


def test_bulge_half_circle_both_ways():
    ccw = dxf.bulge_points((0.0, 0.0), (2.0, 0.0), 1.0, 10)
    assert ccw[0] == (0.0, 0.0) and ccw[-1] == (2.0, 0.0)
    mid = ccw[len(ccw) // 2]
    assert approx(mid, (1.0, -1.0), 1e-9)          # counter-clockwise from (0,0) to (2,0) dips below
    cw = dxf.bulge_points((0.0, 0.0), (2.0, 0.0), -1.0, 10)
    assert approx(cw[len(cw) // 2], (1.0, 1.0), 1e-9)
    for x, y in ccw:
        assert approx(math.hypot(x - 1.0, y), 1.0, 1e-9)


def test_bulge_quarter_and_major_arcs_stay_on_their_circle():
    q = dxf.bulge_points((1.0, 0.0), (0.0, 1.0), math.tan(math.radians(90) / 4.0), 5)
    for x, y in q:
        assert approx(math.hypot(x, y), 1.0, 1e-9)
    big = dxf.bulge_points((1.0, 0.0), (0.0, 1.0), math.tan(math.radians(270) / 4.0), 5)
    assert len(big) > len(q)
    for x, y in big:
        assert approx(math.hypot(x - 0.0, y - 0.0), 1.0, 1e-9) or approx(math.hypot(x - 1.0, y - 1.0), 1.0, 1e-9)
    assert dxf.bulge_points((0, 0), (1, 1), 0.0) == [(0, 0), (1, 1)]


# ---- entities ------------------------------------------------------------------------------


def test_line_and_layers_and_extents():
    text = _dxf(('ENTITIES', _ent('LINE', (8, 'WALLS'), (10, 0), (20, 0), (30, 0), (11, 10), (21, 5), (31, 0))
                 + _ent('LINE', (8, 'GRID'), (10, -2), (20, 1), (11, 3), (21, 1))))
    d = dxf.read(text)
    assert _seg_set(d) == [(-2.0, 1.0, 3.0, 1.0), (0.0, 0.0, 10.0, 5.0)]
    assert d['layers'] == {'WALLS': 1, 'GRID': 1}
    assert d['extents'] == ((-2.0, 0.0), (10.0, 5.0))
    assert d['counts']['LINE'] == 2


def test_lwpolyline_closed_with_bulge():
    body = _ent('LWPOLYLINE', (8, 'A'), (90, 3), (70, 1), (10, 0), (20, 0), (42, 0), (10, 4), (20, 0),
                (42, 1), (10, 4), (20, 4))
    d = dxf.read(_dxf(('ENTITIES', body)))
    segs = d['segments']
    assert segs[0][0] == (0.0, 0.0) and segs[0][1] == (4.0, 0.0)
    # the bulged edge 4,0 -> 4,4 is a half circle around (4, 2) bulging to the right
    arc = [s[1] for s in segs[1:-1]]
    assert all(approx(math.hypot(x - 4.0, y - 2.0), 2.0, 1e-9) for x, y in arc)
    assert max(x for x, _y in arc) > 5.9
    assert segs[-1][1] == (0.0, 0.0)                 # closed back to the start


def test_polyline_vertices_2d_3d_and_mesh_skipped():
    body = (_ent('POLYLINE', (8, 'P'), (66, 1), (70, 0)) + _ent('VERTEX', (10, 0), (20, 0))
            + _ent('VERTEX', (10, 5), (20, 0)) + _ent('VERTEX', (10, 5), (20, 5)) + _ent('SEQEND')
            + _ent('POLYLINE', (8, 'P3'), (70, 8)) + _ent('VERTEX', (10, 1), (20, 1), (30, 9))
            + _ent('VERTEX', (10, 2), (20, 2), (30, 7)) + _ent('SEQEND')
            + _ent('POLYLINE', (70, 64)) + _ent('VERTEX', (10, 0), (20, 0)) + _ent('SEQEND'))
    d = dxf.read(_dxf(('ENTITIES', body)))
    assert _seg_set(d) == [(0.0, 0.0, 5.0, 0.0), (1.0, 1.0, 2.0, 2.0), (5.0, 0.0, 5.0, 5.0)]
    assert d['skipped'].get('POLYLINE mesh') == 1


def test_arc_circle_and_mirrored_arc():
    body = (_ent('CIRCLE', (8, 'C'), (10, 10), (20, 10), (40, 2))
            + _ent('ARC', (8, 'A'), (10, 0), (20, 0), (40, 1), (50, 0), (51, 90))
            + _ent('ARC', (8, 'M'), (10, 5), (20, 0), (40, 1), (50, 0), (51, 90), (210, 0), (220, 0), (230, -1)))
    d = dxf.read(_dxf(('ENTITIES', body)), step_deg=10)
    circle = [s for s in d['segments'] if s[2] == 'C']
    assert len(circle) == 36
    assert all(approx(math.hypot(a[0] - 10, a[1] - 10), 2.0, 1e-9) for a, _b, _l in circle)
    arc = [s for s in d['segments'] if s[2] == 'A']
    assert approx(arc[0][0], (1.0, 0.0)) and approx(arc[-1][1], (0.0, 1.0), 1e-9)
    mirrored = [s for s in d['segments'] if s[2] == 'M']
    # OCS (0,0,-1) mirrors X: centre (5,0) lands at (-5,0), start (6,0) at (-6,0)
    assert approx(mirrored[0][0], (-6.0, 0.0), 1e-9)
    assert approx(mirrored[-1][1], (-5.0, 1.0), 1e-9)


def test_ellipse_and_spline():
    body = (_ent('ELLIPSE', (8, 'E'), (10, 0), (20, 0), (30, 0), (11, 4), (21, 0), (31, 0), (40, 0.5),
                 (41, 0), (42, 6.283185307179586))
            + _ent('SPLINE', (8, 'S'), (70, 0), (11, 0), (21, 0), (11, 1), (21, 1), (11, 2), (21, 0))
            + _ent('SPLINE', (8, 'K'), (10, 0), (20, 0), (10, 3), (20, 3)))
    d = dxf.read(_dxf(('ENTITIES', body)))
    ellipse = [s for s in d['segments'] if s[2] == 'E']
    xs = [a[0] for a, _b, _l in ellipse]
    ys = [a[1] for a, _b, _l in ellipse]
    assert approx(max(xs), 4.0, 1e-9) and approx(max(ys), 2.0, 1e-3)
    assert _seg_set({'segments': [s for s in d['segments'] if s[2] == 'S']}) == [(0.0, 0.0, 1.0, 1.0), (1.0, 1.0, 2.0, 0.0)]
    assert d['counts'].get('SPLINE control polygon') == 1


def test_text_and_mtext_labels():
    body = (_ent('TEXT', (8, 'T'), (10, 1), (20, 2), (40, 0.25), (1, 'Room %%c100'))
            + _ent('TEXT', (8, 'T'), (10, 0), (20, 0), (72, 1), (11, 5), (21, 6), (1, 'Centred'))
            + _ent('MTEXT', (8, 'T'), (10, 3), (20, 4), (40, 0.3), (3, '{\\fArial|b0;Plant '),
                   (1, 'room}\\PNo. 2')))
    d = dxf.read(_dxf(('ENTITIES', body)))
    texts = d['texts']
    assert texts[0]['text'] == u'Room \u00d8100' and texts[0]['x'] == 1.0 and texts[0]['y'] == 2.0
    assert (texts[1]['x'], texts[1]['y']) == (5.0, 6.0)
    assert texts[2]['text'] == 'Plant room No. 2'


def test_insert_scale_rotation_base_and_array():
    blocks = (_ent('BLOCK', (2, 'DOOR'), (10, 1), (20, 0), (30, 0)) + _ent('LINE', (8, '0'), (10, 1), (20, 0),
                                                                           (11, 2), (21, 0))
              + _ent('ENDBLK'))
    entities = (_ent('INSERT', (8, 'D'), (2, 'DOOR'), (10, 10), (20, 10), (41, 2), (42, 2), (50, 90))
                + _ent('INSERT', (8, 'R'), (2, 'DOOR'), (10, 0), (20, 0), (70, 2), (71, 2), (44, 5), (45, 7)))
    d = dxf.read(_dxf(('BLOCKS', blocks), ('ENTITIES', entities)))
    door = [s for s in d['segments'] if s[2] == '0']
    # block line from base (1,0) to (2,0): scaled x2 = (0,0)->(2,0), turned 90: (0,0)->(0,2), moved to (10,10)
    first = door[0]
    assert approx(first[0], (10.0, 10.0), 1e-9) and approx(first[1], (10.0, 12.0), 1e-9)
    starts = sorted((round(s[0][0], 6), round(s[0][1], 6)) for s in door[1:])
    assert starts == [(0.0, 0.0), (0.0, 7.0), (5.0, 0.0), (5.0, 7.0)]
    assert d['counts']['INSERT'] == 2


def test_insert_mirrored_by_negative_scale():
    blocks = _ent('BLOCK', (2, 'B'), (10, 0), (20, 0)) + _ent('LINE', (10, 0), (20, 0), (11, 3), (21, 0)) + _ent('ENDBLK')
    d = dxf.read(_dxf(('BLOCKS', blocks), ('ENTITIES', _ent('INSERT', (2, 'B'), (10, 0), (20, 0), (41, -1)))))
    assert approx(d['segments'][0][1], (-3.0, 0.0), 1e-9)


def test_nested_inserts_stop_at_max_depth_and_missing_blocks_counted():
    blocks = (_ent('BLOCK', (2, 'INNER'), (10, 0), (20, 0)) + _ent('LINE', (10, 0), (20, 0), (11, 1), (21, 0))
              + _ent('ENDBLK')
              + _ent('BLOCK', (2, 'OUTER'), (10, 0), (20, 0)) + _ent('LINE', (10, 0), (20, 0), (11, 0), (21, 1))
              + _ent('INSERT', (2, 'INNER'), (10, 5), (20, 5)) + _ent('ENDBLK'))
    entities = _ent('INSERT', (2, 'OUTER'), (10, 0), (20, 0)) + _ent('INSERT', (2, 'GONE'), (10, 0), (20, 0))
    one = dxf.read(_dxf(('BLOCKS', blocks), ('ENTITIES', entities)))
    assert len(one['segments']) == 1
    assert one['skipped'].get('INSERT nested deeper than 1') == 1
    assert one['skipped'].get('INSERT of a missing block') == 1
    two = dxf.read(_dxf(('BLOCKS', blocks), ('ENTITIES', entities)), max_depth=2)
    assert len(two['segments']) == 2
    assert approx(two['segments'][1][0], (5.0, 5.0))


def test_damaged_entities_are_skipped_with_a_note():
    body = (_ent('LWPOLYLINE', (90, 1), (10, 0), (20, 0)) + _ent('CIRCLE', (10, 0), (20, 0), (40, 0))
            + _ent('HATCH', (8, 'H')) + _ent('LINE', (10, 0), (20, 0), (11, 1), (21, 1)))
    d = dxf.read(_dxf(('ENTITIES', body)))
    assert len(d['segments']) == 1
    assert d['skipped'].get('LWPOLYLINE (damaged)') == 1
    assert d['skipped'].get('CIRCLE (damaged)') == 1
    assert d['skipped'].get('HATCH') == 1
    assert len(d['notes']) == 2


def test_header_units_and_cap():
    header = ['9', '$ACADVER', '1', 'AC1027', '9', '$INSUNITS', '70', '4']
    lines = []
    for i in range(30):
        lines += _ent('LINE', (10, i), (20, 0), (11, i), (21, 1))
    d = dxf.read(_dxf(('HEADER', header), ('ENTITIES', lines)), max_segments=10)
    assert d['units'] == 4 and d['units_name'] == 'Millimeters'
    assert len(d['segments']) == 10 and d['capped']
    assert any('more than 10 line segments' in n for n in d['notes'])
    assert dxf.units_to_meters(4) == 0.001 and dxf.units_to_meters(0) is None
    assert dxf.summary(d) == '10 lines on 1 layer'


def test_a_whole_small_plan():
    """A realistic little file: header, a table section, a block, entities."""
    text = '\n'.join([
        '0', 'SECTION', '2', 'HEADER', '9', '$INSUNITS', '70', '6', '0', 'ENDSEC',
        '0', 'SECTION', '2', 'TABLES', '0', 'TABLE', '2', 'LAYER', '0', 'LAYER', '2', 'WALLS', '0', 'ENDTAB',
        '0', 'ENDSEC',
        '0', 'SECTION', '2', 'BLOCKS', '0', 'BLOCK', '8', '0', '2', 'COL', '10', '0.0', '20', '0.0', '30', '0.0',
        '0', 'LWPOLYLINE', '8', '0', '90', '4', '70', '1', '10', '-0.2', '20', '-0.2', '10', '0.2', '20', '-0.2',
        '10', '0.2', '20', '0.2', '10', '-0.2', '20', '0.2', '0', 'ENDBLK', '0', 'ENDSEC',
        '0', 'SECTION', '2', 'ENTITIES',
        '0', 'LWPOLYLINE', '8', 'WALLS', '90', '4', '70', '1', '10', '0', '20', '0', '10', '20', '20', '0',
        '10', '20', '20', '10', '10', '0', '20', '10',
        '0', 'INSERT', '8', 'COLS', '2', 'COL', '10', '5', '20', '5',
        '0', 'TEXT', '8', 'ROOMS', '10', '8', '20', '4', '40', '0.3', '1', 'Office',
        '0', 'ENDSEC', '0', 'EOF', ''])
    d = dxf.read(text)
    assert d['units_name'] == 'Meters'
    assert d['layers']['WALLS'] == 4 and d['layers']['0'] == 4
    assert d['texts'][0]['text'] == 'Office'
    assert d['extents'] == ((0.0, 0.0), (20.0, 10.0))
    assert dxf.summary(d) == '8 lines on 2 layers, 1 text'


def test_clean_mtext_codes():
    assert dxf.clean_mtext('\\A1;{\\H2.5x;Big}\\Psmall') == 'Big small'
    assert dxf.clean_mtext('A\\~B \\S1/2;') == 'A B 1/2'
    assert dxf.clean_mtext('\\U+00B0C') == u'\u00b0C'
