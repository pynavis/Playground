# -*- coding: utf-8 -*-
"""namo.meshexport: welding and preparation, the glTF/OBJ/STL/DXF writers parsed back,
byte-identical output on both engines, budgets and the read_objects walk on fakes."""
import hashlib
import io
import math
import os
import struct

import _compat

from namo import meshexport as m


def cube(x0, y0, z0, s):
    """12 outward-wound triangles of an axis-aligned cube."""
    p = [(x0 + dx * s, y0 + dy * s, z0 + dz * s) for dx in (0, 1) for dy in (0, 1) for dz in (0, 1)]
    faces = [(0, 2, 6), (0, 6, 4), (1, 5, 7), (1, 7, 3), (0, 4, 5), (0, 5, 1),
             (2, 3, 7), (2, 7, 6), (0, 1, 3), (0, 3, 2), (4, 6, 7), (4, 7, 5)]
    return [tuple(p[i] for i in f) for f in faces]


def records():
    return [
        {'name': 'Duct 1', 'model': 'MEP.nwc', 'category': 'Ducts', 'color': '4E79A7',
         'transparency': 0.0, 'tris': cube(512345.5, 304000.25, 3000.0, 1000.0), 'noise': 0.03,
         'extras': {'category': 'Ducts', 'element_id': '123', 'properties': {'Element': {'Mark': 'D-1'}}}},
        {'name': 'Glass panel', 'model': 'ARCH.nwc', 'category': 'Windows', 'color': 'a0c8e8',
         'transparency': 0.6, 'tris': cube(512000.0, 304500.0, 0.0, 500.0), 'noise': 0.0, 'extras': {}},
        {'name': 'Duct 1', 'model': 'MEP.nwc', 'category': 'Ducts', 'color': None,
         'transparency': 0.0, 'tris': cube(513000.0, 305000.0, 2000.0, 250.0), 'noise': 0.0, 'extras': {}},
    ]


def glb_meshes():
    recs = records()
    shift = m.local_origin(m.union_box(recs), 'Millimeters')
    return m.build_meshes(recs, 'glb', 'Millimeters', shift)[0]


# ---- preparation ------------------------------------------------------------------------


def test_weld_merges_corners_and_drops_collapsed():
    tris = cube(0, 0, 0, 1) + [((0, 0, 0), (0, 0, 0), (1, 1, 1))]
    vertices, faces = m._weld(tris, 1e-6)
    assert len(vertices) == 8 and len(faces) == 12


def test_local_origin_rounds_to_metres_and_floors_z():
    box = ((512000.0, 304000.0, 3000.0), (513345.5, 305000.25, 4000.0))
    assert m.local_origin(box, 'Millimeters') == (513000.0, 305000.0, 3000.0)
    assert m.local_origin(((10.2, 20.6, -0.5), (11.0, 21.0, 3.0)), 'Feet') == (11.0, 21.0, -1.0)
    assert m.local_origin(None, 'Meters') is None


def test_build_meshes_glb_is_metres_y_up_with_centre_translation():
    meshes = glb_meshes()
    assert len(meshes) == 3
    duct = meshes[0]
    assert len(duct['vertices']) == 8 and len(duct['faces']) == 12
    # model x 512345.5..513345.5 mm, origin x 513000 -> centre -0.1545 m
    assert _compat.approx(duct['translation'][0], (512845.5 - 513000.0) / 1000.0)
    # y up: file y is model z (3000..4000 mm, origin z 0) -> 3.5 m
    assert _compat.approx(duct['translation'][1], 3.5)
    # file z is minus model y (304000.25..305000.25, origin y 305000) -> -(-0.49975)
    assert _compat.approx(duct['translation'][2], 0.49975)
    xs = [v[0] for v in duct['vertices']]
    assert _compat.approx(min(xs), -0.5) and _compat.approx(max(xs), 0.5)
    assert meshes[1]['color'] == 'A0C8E8' and _compat.approx(meshes[1]['alpha'], 0.4)
    assert meshes[2]['color'] == m.FALLBACK_COLOR


def test_build_meshes_other_formats_keep_world_and_units():
    recs = records()
    meshes, dropped = m.build_meshes(recs, 'stl', 'Millimeters', None, 'm')
    assert dropped == []
    assert meshes[0]['translation'] == (0.0, 0.0, 0.0)
    xs = [v[0] for v in meshes[0]['vertices']]
    assert _compat.approx(min(xs), 512.3455) and _compat.approx(max(xs), 513.3455)
    zs = [v[2] for v in meshes[0]['vertices']]
    assert _compat.approx(min(zs), 3.0)                    # Z stays up for STL
    obj = m.build_meshes(recs, 'obj', 'Millimeters', None, 'doc', obj_y_up=True)[0]
    assert _compat.approx(max(v[1] for v in obj[0]['vertices']), 4000.0)   # Y is model Z
    flat = m.build_meshes([{'name': 'Line', 'tris': [((0, 0, 0), (0, 0, 0), (1, 0, 0))]}], 'stl', 'Meters')
    assert flat[0] == [] and flat[1] == ['Line']


def test_target_units():
    assert m.target_units('glb', 'mm', 'Millimeters') == (0.001, 'metres')
    assert m.target_units('stl', 'doc', 'Feet') == (1.0, 'feet')
    scale, word = m.target_units('dxf', 'mm', 'Feet')
    assert _compat.approx(scale, 304.8) and word == 'millimetres'
    _compat.raises(ValueError, m.target_units, 'obj', 'furlong', 'Feet')
    _compat.raises(ValueError, m.doc_meters, 'Cubits')


def test_y_up_is_right_handed():
    x, y, z = m.y_up((1.0, 2.0, 3.0))
    assert (x, y, z) == (1.0, 3.0, -2.0)
    # the frame keeps its handedness: (x cross y) still equals z after the change
    ex, ey, ez = m.y_up((1, 0, 0)), m.y_up((0, 1, 0)), m.y_up((0, 0, 1))
    cross = (ex[1] * ey[2] - ex[2] * ey[1], ex[2] * ey[0] - ex[0] * ey[2], ex[0] * ey[1] - ex[1] * ey[0])
    assert cross == ez


# ---- numbers and JSON ----------------------------------------------------------------------


def test_num_text_and_json_are_engine_independent():
    assert m.num_text(0.1) == '0.1'
    assert m.num_text(-0.0) == '0'
    assert m.num_text(1e22) == '1e+22'
    assert m.json_text({'b': [1.5, 0.1, 2, True, None], 'a': 'caf\u00e9'}) == \
        '{"a":"caf\\u00e9","b":[1.5,0.1,2,true,null]}'
    assert m.json_text({'x': float('nan')}) == '{"x":null}'
    assert m.exact32(0.3).text == '0.30000001192092896'
    _compat.raises(ValueError, m.num_text, float('inf'))


def test_srgb_to_linear():
    assert m.srgb_to_linear(0.0) == 0.0
    assert _compat.approx(m.srgb_to_linear(1.0), 1.0)
    assert _compat.approx(m.srgb_to_linear(0.5), 0.21404114, 1e-6)
    assert _compat.approx(m.srgb_to_linear(0.04), 0.04 / 12.92)


def test_json_value():
    import datetime
    assert m.json_value((1.0, 2, 'a')) == [1.0, 2, 'a']
    assert m.json_value(datetime.datetime(2026, 10, 5, 14, 30)) == '2026-10-05T14:30:00'
    assert m.json_value(float('nan')) is None


# ---- glTF ---------------------------------------------------------------------------------


def test_glb_structure_parses_back():
    meshes = glb_meshes()
    data = m.glb_bytes(meshes, title='Hospital', extras={'units': 'metres'})
    assert data[:4] == b'glTF' and len(data) % 4 == 0
    gltf, binary = m.parse_glb(data)
    assert gltf['asset']['version'] == '2.0' and gltf['asset']['extras'] == {'units': 'metres'}
    assert gltf['buffers'][0]['byteLength'] <= len(binary) < gltf['buffers'][0]['byteLength'] + 4
    # chunk lengths: JSON then BIN, both multiples of four
    json_len = struct.unpack('<I', data[12:16])[0]
    assert data[16:20] == b'JSON' and json_len % 4 == 0
    assert data[20 + json_len + 4:20 + json_len + 8] == b'BIN\x00'
    # every buffer view 4-byte aligned and inside the buffer
    for view in gltf['bufferViews']:
        assert view['byteOffset'] % 4 == 0
        assert view['byteOffset'] + view['byteLength'] <= gltf['buffers'][0]['byteLength']
    # root -> model -> object nodes, one mesh per object
    root = gltf['nodes'][0]
    assert root['name'] == 'Hospital' and gltf['scenes'][0]['nodes'] == [0]
    models = [gltf['nodes'][i]['name'] for i in root['children']]
    assert models == ['MEP.nwc', 'ARCH.nwc']
    objects = [n for n in gltf['nodes'] if 'mesh' in n]
    assert len(objects) == 3 == len(gltf['meshes'])
    assert objects[0]['extras']['properties'] == {'Element': {'Mark': 'D-1'}}
    assert 'extras' not in objects[1]


def test_glb_accessors_match_their_data():
    gltf, binary = m.parse_glb(m.glb_bytes(glb_meshes()))
    for mesh in gltf['meshes']:
        prim = mesh['primitives'][0]
        assert prim['mode'] == 4
        pos = gltf['accessors'][prim['attributes']['POSITION']]
        values = m.read_accessor(gltf, binary, prim['attributes']['POSITION'])
        for axis in range(3):
            column = values[axis::3]
            assert pos['min'][axis] == min(column) and pos['max'][axis] == max(column)
        indices = m.read_accessor(gltf, binary, prim['indices'])
        assert len(indices) % 3 == 0 and max(indices) < pos['count']
        assert gltf['accessors'][prim['indices']]['componentType'] == 5123


def test_glb_materials_linear_and_blended():
    gltf, _binary = m.parse_glb(m.glb_bytes(glb_meshes()))
    names = [mat['name'] for mat in gltf['materials']]
    assert names == ['4E79A7', 'A0C8E8 40%', 'BFBFBF']
    blue = gltf['materials'][0]
    assert 'alphaMode' not in blue and blue['doubleSided'] is True
    r, g, b, a = blue['pbrMetallicRoughness']['baseColorFactor']
    assert _compat.approx(r, m.srgb_to_linear(0x4E / 255.0), 1e-5) and a == 1
    glass = gltf['materials'][1]
    assert glass['alphaMode'] == 'BLEND' and glass['pbrMetallicRoughness']['baseColorFactor'][3] == 0.4


def test_glb_uses_uint32_past_65535_vertices():
    tris = []
    for i in range(22000):                          # 66,000 distinct corners
        x = float(i)
        tris.append(((x, 0.0, 0.0), (x + 0.5, 0.0, 0.0), (x, 0.5, 0.0)))
    meshes = m.build_meshes([{'name': 'Big', 'tris': tris}], 'glb', 'Meters')[0]
    assert len(meshes[0]['vertices']) == 66000
    gltf, binary = m.parse_glb(m.glb_bytes(meshes))
    index = gltf['meshes'][0]['primitives'][0]['indices']
    assert gltf['accessors'][index]['componentType'] == 5125
    assert max(m.read_accessor(gltf, binary, index)) == 65999


def test_glb_empty_is_still_valid():
    gltf, binary = m.parse_glb(m.glb_bytes([], title='Empty'))
    assert gltf['nodes'] == [{'children': [], 'name': 'Empty'}] and binary == b''
    assert 'buffers' not in gltf


def test_parse_glb_rejects_damage():
    data = m.glb_bytes(glb_meshes())
    _compat.raises(ValueError, m.parse_glb, data[:-4])
    _compat.raises(ValueError, m.parse_glb, b'XXXX' + data[4:])


def test_glb_cross_check_with_pygltflib():
    if _compat.IRONPYTHON:
        raise _compat.SkipTest('pygltflib is a CPython package')
    try:
        import pygltflib
    except ImportError:
        raise _compat.SkipTest('pygltflib is not installed')
    data = m.glb_bytes(glb_meshes(), title='Hospital')
    doc = pygltflib.GLTF2.load_from_bytes(data)
    assert len(doc.meshes) == 3 and len(doc.materials) == 3
    assert doc.nodes[0].name == 'Hospital'
    blob = doc.binary_blob()
    accessor = doc.accessors[doc.meshes[0].primitives[0].attributes.POSITION]
    view = doc.bufferViews[accessor.bufferView]
    floats = struct.unpack('<%df' % (accessor.count * 3), blob[view.byteOffset:view.byteOffset + view.byteLength])
    assert accessor.min == [min(floats[a::3]) for a in range(3)]


# ---- OBJ ----------------------------------------------------------------------------------


def test_obj_roundtrip_groups_materials_and_indices():
    recs = records()
    meshes = m.build_meshes(recs, 'obj', 'Millimeters', None, 'm', obj_y_up=False)[0]
    text = m.obj_text(meshes, 'Hospital_export.mtl', ['Source: Hospital.nwf'])
    parsed = m.parse_obj(text)
    assert parsed['mtllib'] == 'Hospital_export.mtl'
    assert len(parsed['vertices']) == 24
    names = [g[0] for g in parsed['groups']]
    assert names == ['Duct_1', 'Glass_panel', 'Duct_1_2']
    assert [g[1] for g in parsed['groups']] == ['mat_4E79A7', 'mat_A0C8E8_40', 'mat_BFBFBF']
    second = parsed['groups'][1][2]
    assert min(min(f) for f in second) == 8 and max(max(f) for f in second) == 15
    first_vertex = parsed['vertices'][0]
    assert _compat.approx(first_vertex[0], 512.3455) and _compat.approx(first_vertex[2], 3.0)
    mtl = m.mtl_text(meshes)
    assert mtl.count('newmtl ') == 3 and 'd 0.4' in mtl and 'Kd 0.3059 0.4745 0.6549' in mtl


def test_obj_names_unique():
    taken = set()
    assert m.obj_name('Basic Wall', taken) == 'Basic_Wall'
    assert m.obj_name('basic  wall', taken) == 'basic_wall_2'
    assert m.obj_name('', taken) == 'Object'


# ---- STL ----------------------------------------------------------------------------------


def test_stl_roundtrip_and_normals():
    meshes = m.build_meshes([records()[0]], 'stl', 'Millimeters', (512000.0, 304000.0, 0.0), 'mm')[0]
    data = m.stl_bytes(meshes, header='solid but not really')
    header, triangles = m.parse_stl(data)
    assert not header.lower().startswith(b'solid')
    assert len(triangles) == 12 and len(data) == 84 + 50 * 12
    for normal, a, b, c in triangles:
        assert _compat.approx(math.sqrt(sum(n * n for n in normal)), 1.0, 1e-6)
        expected = m.facet_normal(a, b, c)
        assert _compat.approx(list(normal), list(expected), 1e-6)
    # the cube's bottom face points down
    bottom = [t for t in triangles if all(abs(p[2] - 3000.0) < 1e-3 for p in t[1:])]
    assert bottom and all(_compat.approx(t[0][2], -1.0) for t in bottom)


def test_stl_rejects_wrong_size():
    _compat.raises(ValueError, m.parse_stl, b'x' * 84 + b'\x00')
    assert m.facet_normal((0, 0, 0), (0, 0, 0), (1, 1, 1)) == (0.0, 0.0, 0.0)


# ---- DXF ----------------------------------------------------------------------------------


def test_dxf_roundtrip_layers_and_true_colour():
    meshes = m.build_meshes(records(), 'dxf', 'Millimeters')[0]
    text = m.dxf_text(meshes, 'category', comment='Playground\nHospital')
    parsed = m.parse_dxf(text)
    assert parsed['header']['$ACADVER'] == ['AC1009']
    assert sorted(parsed['layers']) == ['0', 'Ducts', 'Windows']
    assert len(parsed['faces']) == 36
    first = parsed['faces'][0]
    assert first['layer'] == 'Ducts' and first['true'] == 0x4E79A7
    assert first['aci'] == m.nearest_aci('4E79A7')
    assert first['corners'][3] == first['corners'][2]
    assert _compat.approx(float(parsed['header']['$EXTMIN'][0]), 512000.0)
    by_model = m.parse_dxf(m.dxf_text(meshes, 'model'))
    assert sorted(by_model['layers']) == ['0', 'ARCH', 'MEP']
    assert '\r\n' in text and text.endswith('EOF\r\n')


def test_dxf_cross_check_with_ezdxf():
    if _compat.IRONPYTHON:
        raise _compat.SkipTest('ezdxf is a CPython package')
    try:
        import ezdxf
    except ImportError:
        raise _compat.SkipTest('ezdxf is not installed')
    folder = _compat.tmpdir('meshexport_ezdxf')
    path = os.path.join(folder, 'faces.dxf')
    meshes = m.build_meshes(records(), 'dxf', 'Millimeters')[0]
    with io.open(path, 'wb') as handle:
        handle.write(m.dxf_text(meshes, 'category').encode('ascii'))
    doc = ezdxf.readfile(path)
    assert doc.dxfversion == 'AC1009'
    faces = doc.modelspace().query('3DFACE')
    assert len(faces) == 36
    assert faces[0].dxf.layer == 'Ducts' and faces[0].rgb == (0x4E, 0x79, 0xA7)
    assert len(doc.audit().errors) == 0


def test_layer_names_are_r12_safe_and_unique():
    taken = {}
    assert m.layer_name('Mechanical Equipment', taken) == 'Mechanical_Equipment'
    assert m.layer_name('MECHANICAL EQUIPMENT', taken) == 'MECHANICAL_EQUIPMENT_2'
    assert m.layer_name('0', taken) == 'Layer_0'
    assert m.layer_name('\u00e9\u00e9', taken) == 'Unnamed'
    long_name = m.layer_name('x' * 50, taken)
    assert len(long_name) == 31
    assert len(m.layer_name('x' * 50, taken)) == 31 and m.layer_name('x' * 50, taken).endswith('_3')


def test_aci_palette_and_nearest():
    palette = m.aci_palette()
    assert len(palette) == 256
    assert palette[1] == (255, 0, 0) and palette[7] == (255, 255, 255)
    assert m.nearest_aci('FF0000') == 1 and m.nearest_aci('0000FF') == 5
    assert m.nearest_aci('808080') == 8
    assert m.true_color('4E79A7') == 0x4E79A7


def test_aci_palette_matches_ezdxf_within_one_step():
    if _compat.IRONPYTHON:
        raise _compat.SkipTest('ezdxf is a CPython package')
    try:
        from ezdxf import colors
    except ImportError:
        raise _compat.SkipTest('ezdxf is not installed')
    palette = m.aci_palette()
    off = []
    for index in range(1, 250):
        value = colors.DXF_DEFAULT_COLORS[index]
        theirs = ((value >> 16) & 255, (value >> 8) & 255, value & 255)
        if not all(abs(a - b) <= 1 for a, b in zip(theirs, palette[index])):
            off.append(index)
    # ezdxf's table carries a few entries that break the ACI pattern (109 is (19, 88, 23)
    # among its (19, 38, x) neighbours); everything else agrees to within one step.
    assert not [i for i in off if i < 100], off
    assert len(off) <= 25, off


# ---- byte identity across engines -----------------------------------------------------------


def _digest(data):
    if isinstance(data, str):
        data = data.encode('utf-8')
    return hashlib.sha1(data).hexdigest()


GOLDEN = {
    'glb': '25496501b23370357d790ed07f9f3b8373ba7f6d',
    'obj': '90d2847b802db270e2199b146510fe00173f79a7',
    'stl': 'eded7fac409fa8739f97a836e711c7af812009cd',
    'dxf': '5d9107b82f769d36cb497923f65ab9c31751766d',
}


def golden_outputs():
    recs = records()
    shift = m.local_origin(m.union_box(recs), 'Millimeters')
    glb = m.glb_bytes(m.build_meshes(recs, 'glb', 'Millimeters', shift)[0], title='Hospital',
                      extras={'units': 'metres', 'local_origin_model_units': list(shift)})
    obj_meshes = m.build_meshes(recs, 'obj', 'Millimeters', shift, 'm')[0]
    stl = m.stl_bytes(m.build_meshes(recs, 'stl', 'Millimeters', shift, 'mm')[0], header='Playground Hospital')
    dxf = m.dxf_text(m.build_meshes(recs, 'dxf', 'Millimeters')[0], 'category')
    return {'glb': glb, 'obj': m.obj_text(obj_meshes, 'x.mtl') + m.mtl_text(obj_meshes), 'stl': stl, 'dxf': dxf}


def test_outputs_are_byte_identical_on_both_engines():
    outputs = golden_outputs()
    for key in sorted(GOLDEN):
        assert _digest(outputs[key]) == GOLDEN[key], (key, _digest(outputs[key]))


# ---- files, notes, budgets -----------------------------------------------------------------


def test_write_files_and_sidecar():
    from namo import paths
    folder = _compat.tmpdir('meshexport_files')
    recs = records()
    for fmt in ('glb', 'obj', 'stl', 'dxf'):
        meshes = m.build_meshes(recs, fmt, 'Millimeters')[0]
        path = os.path.join(folder, 'Hospital export' + m.EXTENSIONS[fmt])
        written = m.write_files(path, fmt, meshes, title='Hospital', header_lines=['Units: millimetres'])
        assert os.path.isfile(path)
        if fmt == 'obj':
            assert written[1].endswith('Hospital_export.mtl') and os.path.isfile(written[1])
            with io.open(path, encoding='utf-8') as handle:
                assert 'mtllib Hospital_export.mtl' in handle.read()
    note = m.offset_note((513000.0, 305000.0, 0.0), 'Millimeters', 'glb', 'metres', 'Hospital.nwf',
                         axes_y_up=True)
    assert 'X = 513,000 mm  (513 m)' in note and 'Y up' in note
    assert m.sidecar_path(r'C:\a\b.glb') == r'C:\a\b - offset.txt'
    paths.atomic_write_text(os.path.join(folder, 'note.txt'), note)
    _compat.raises(ValueError, m.write_files, os.path.join(folder, 'x.3ds'), '3ds', [])


def test_skip_reasons():
    assert m.skip_reason('312000 primitives is over the 200000 budget') ==         'Too big: 312,000 triangles, over the 200,000 left per object'
    assert m.skip_reason(None) == 'No triangles' and m.skip_reason('no geometry nodes') == 'No geometry'
    assert m.skip_reason('triangle walk failed: boom') == 'Could not read its triangles: boom'
    assert m.skip_reason('no matrix layout fits') == 'No matrix layout fits'


def test_plan_budget_and_summary():
    assert m.plan_budget(500, 200) == 200
    assert m.plan_budget(150, 200) == 150
    assert m.plan_budget(-5, 200) == 0
    meshes = glb_meshes()
    assert m.summary(meshes, [], [], 'glb')[0] == 'success'
    level, message, detail = m.summary(meshes, [('A', 'why', None)], ['B'], 'glb', sampled=True)
    assert level == 'warning' and message == 'Exported 3 objects, 36 triangles'
    assert detail == '2 skipped (listed in the output window); the selection was sampled.'
    assert m.summary([], [('A', 'x', None)], [], 'stl')[0] == 'warning'


# ---- read_objects on fakes ---------------------------------------------------------------------


class FakeItem(object):
    def __init__(self, name, tris):
        self.DisplayName = name
        self.tris = tris


def test_read_objects_budgets_and_skips():
    from namo import items, mesh, paint
    saved = (items.objects, items.model_name, items.category, items.revit_ids, mesh.item_triangles, paint.read_color)
    objects = [FakeItem('A', cube(0, 0, 0, 1)), FakeItem('Empty', []), FakeItem('B', cube(5, 0, 0, 1)),
               FakeItem('C', cube(9, 0, 0, 1))]
    calls = []

    def fake_triangles(item, budget=0):
        calls.append((item.DisplayName, budget))
        if len(item.tris) > budget:
            return {'tris': [], 'note': '%d primitives is over the %d budget' % (len(item.tris), budget),
                    'noise': 0.0}
        if not item.tris:
            return {'tris': [], 'note': None, 'noise': 0.0}
        return {'tris': item.tris, 'note': None, 'noise': 1e-5}

    items.objects = lambda selected, tick=None, budget=None: items.ItemList(selected)
    items.model_name = lambda item: 'M.nwc'
    items.category = lambda item: 'Ducts'
    items.revit_ids = lambda item: {'element_id': '7', 'unique_id': None, 'ifc_guid': None}
    mesh.item_triangles = fake_triangles
    paint.read_color = lambda item: ('FF0000', 0.25)
    try:
        seen = []
        read = m.read_objects(objects, per_object=100, total=20, progress=lambda f, label: seen.append(f))
        welded = m.read_objects(objects[:1], per_object=100, total=100, doc_units='Meters')
    finally:
        (items.objects, items.model_name, items.category, items.revit_ids, mesh.item_triangles,
         paint.read_color) = saved
    assert [r['name'] for r in read['records']] == ['A']
    reasons = dict((name, why) for name, why, _item in read['skipped'])
    assert sorted(reasons) == ['B', 'C', 'Empty']
    assert reasons['Empty'] == 'No triangles'
    assert reasons['B'] == 'Too big: 12 triangles, over the 8 left in the total'
    assert calls[:4] == [('A', 20), ('Empty', 8), ('B', 8), ('C', 8)]
    record = read['records'][0]
    assert record['color'] == 'FF0000' and record['transparency'] == 0.25
    assert record['extras'] == {'category': 'Ducts', 'model': 'M.nwc', 'element_id': '7'}
    assert seen[-1] == 1.0 and read['objects'] == 4 and read['sampled'] is False
    # welded as read: the raw triangles are gone, the mesh and the count stay
    one = welded['records'][0]
    assert 'tris' not in one and one['triangles'] == 12
    assert len(one['mesh'][0]) == 8 and len(one['mesh'][1]) == 12
    assert m.union_box(welded['records']) == ((0.0, 0.0, 0.0), (1.0, 1.0, 1.0))
    meshes = m.build_meshes(welded['records'], 'stl', 'Meters')[0]
    assert len(meshes[0]['faces']) == 12
