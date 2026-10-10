# -*- coding: utf-8 -*-
"""namo.ifc: STEP encoding, the whole IFC4 file read back (header, numbering, every
reference resolves, attribute counts, GlobalIds, spatial structure, styles, property
sets), byte-identical on both engines, and ifcopenshell's own validator when installed."""
import datetime
import hashlib
import os

import _compat

from namo import ifc, ifcguid

CUBE_V = [(0, 0, 0), (0, 0, 1), (0, 1, 0), (0, 1, 1), (1, 0, 0), (1, 0, 1), (1, 1, 0), (1, 1, 1)]
CUBE_F = [(0, 2, 6), (0, 6, 4), (1, 5, 7), (1, 7, 3), (0, 4, 5), (0, 5, 1), (2, 3, 7), (2, 7, 6),
          (0, 1, 3), (0, 3, 2), (4, 6, 7), (4, 7, 5)]
SMILE = ''.join(chr(c) for c in (0xD83D, 0xDE00)) if _compat.IRONPYTHON else chr(0x1F600)


def model(units='Feet'):
    def cube(scale):
        return [tuple(float(c) * scale for c in v) for v in CUBE_V]
    return {
        'file_name': 'Test \u00e9.ifc', 'timestamp': datetime.datetime(2026, 10, 5, 14, 30), 'epoch': 1791210600,
        'author': "O'Brien", 'organization': 'Acme', 'app_version': '0.1.0', 'seed': 'c:/jobs/x.nwf',
        'project': {'name': 'Hospital'}, 'site': {'name': 'Site'}, 'building': {'name': 'Main building'},
        'length_unit': units,
        'storeys': [{'key': 'l2', 'name': 'Level 2', 'elevation': 12.0},
                    {'key': 'l1', 'name': 'Level 1', 'elevation': 0.0}],
        'elements': [
            {'guid': ifcguid.compress('11111111-2222-3333-4444-555555555555'), 'ifc_class': 'IfcWall',
             'predefined': None, 'name': 'Basic Wall: \u00dcn\u00efcode ' + SMILE, 'object_type': 'Basic Wall',
             'tag': '12345', 'storey': 'l1', 'origin': (10.0, 20.0, 0.0), 'vertices': cube(3.0),
             'faces': CUBE_F, 'closed': True, 'color': 'C8B496', 'transparency': 0.0,
             'psets': [('Element', [('Category', 'Walls'), ('Id', 12345), ('Area', 12.5), ('Structural', True),
                                    ('Long', 'x' * 300), ('Id', 'duplicate name'), ('Empty', '  ')]),
                       ('Nothing', []), ('Pset_WallCommon', [('IsExternal', False)])]},
            {'guid': ifcguid.compress('21111111-2222-3333-4444-555555555555'), 'ifc_class': 'IfcDoor',
             'predefined': 'DOOR', 'name': 'Door', 'object_type': None, 'tag': None, 'storey': 'l2',
             'origin': (1.0, 2.0, 12.5), 'vertices': cube(1.0), 'faces': CUBE_F, 'closed': True,
             'color': '804020', 'transparency': 0.5,
             'psets': [('Element', [('Category', 'Walls'), ('Id', 12345), ('Area', 12.5), ('Structural', True),
                                    ('Long', 'x' * 300)])]},
            {'guid': ifcguid.compress('31111111-2222-3333-4444-555555555555'), 'ifc_class': 'IfcDuctSegment',
             'predefined': 'RIGIDSEGMENT', 'name': "Duct 'A' \\ main", 'object_type': 'Rect', 'tag': '9',
             'storey': None, 'origin': (5.0, 5.0, 9.0), 'vertices': cube(1.0), 'faces': CUBE_F,
             'closed': False, 'color': None, 'transparency': 0.0, 'psets': []},
        ]}


# ---- encoding ---------------------------------------------------------------------------


def test_real_always_has_a_point():
    assert ifc.real(0.0) == '0.'
    assert ifc.real(-0.0) == '0.'
    assert ifc.real(12.0) == '12.'
    assert ifc.real(1.5) == '1.5'
    assert ifc.real(1e-5) == '1.E-5'
    assert ifc.real(-2.5e-6) == '-2.5E-6'
    assert ifc.real(1e22) == '1.E22'
    assert ifc.real(0.3048) == '0.3048'
    _compat.raises(ValueError, ifc.real, float('nan'))


def test_string_encoding_per_iso_10303_21():
    assert ifc.encode_string("O'Brien") == "'O''Brien'"
    assert ifc.encode_string('a\\b') == "'a\\\\b'"
    assert ifc.encode_string('caf\u00e9') == "'caf\\X2\\00E9\\X0\\'"
    assert ifc.encode_string('\u00e9\u00e8x') == "'\\X2\\00E900E8\\X0\\x'"
    assert ifc.encode_string(SMILE) == "'\\X4\\0001F600\\X0\\'"
    assert ifc.encode_string('line\nbreak') == "'line\\X2\\000A\\X0\\break'"
    assert ifc.encode_string(None) == "''"


def test_string_round_trip():
    for text in ("O'Brien", 'a\\b', 'caf\u00e9 \u4e2d\u6587', 'x' + SMILE + 'y', '', 'tab\tend'):
        assert ifc.decode_string(ifc.encode_string(text)) == text


def test_encode_values():
    assert ifc.encode(None) == '$'
    assert ifc.encode(ifc.DERIVED) == '*'
    assert ifc.encode(True) == '.T.' and ifc.encode(False) == '.F.'
    assert ifc.encode(3) == '3'
    assert ifc.encode(ifc.Enum('notdefined')) == '.NOTDEFINED.'
    assert ifc.encode(ifc.Typed('IfcLabel', 'x')) == "IFCLABEL('x')"
    assert ifc.encode([ifc.Ref(1), (1.0, 2.5)]) == '(#1,(1.,2.5))'
    _compat.raises(TypeError, ifc.encode, object())


def test_nominal_values():
    assert ifc.nominal_value(True).type_name == 'IFCBOOLEAN'
    assert ifc.nominal_value(3).type_name == 'IFCINTEGER'
    assert ifc.nominal_value(2 ** 40).type_name == 'IFCLABEL'
    assert ifc.nominal_value(2.5).type_name == 'IFCREAL'
    assert ifc.nominal_value('x' * 256).type_name == 'IFCTEXT'
    assert ifc.nominal_value((1.0, 2.0, 3.0)).value == '1.0, 2.0, 3.0'
    assert ifc.nominal_value(datetime.date(2026, 10, 5)).value == '2026-10-05'
    assert ifc.nominal_value('   ') is None and ifc.nominal_value(float('nan')) is None


def test_clean_psets_drops_empty_and_duplicates():
    out = ifc.clean_psets([('A', [('x', 1), ('X', 2), ('', 3), ('y', None)]), ('a', [('z', 1)]), ('B', [])])
    assert [(name, [p for p, _t in props]) for name, props in out] == [('A', ['x'])]


def test_units():
    assert ifc.length_unit('Millimeters') == ('si', 'MILLI')
    assert ifc.length_unit('Feet') == ('conversion', 'FOOT', 0.3048)
    _compat.raises(ValueError, ifc.length_unit, 'Cubits')
    assert ifc.is_imperial('Inches') and not ifc.is_imperial('Meters')


def test_guid_is_stable_and_valid():
    a = ifc.guid('c:/x.nwf', 'project')
    assert ifcguid.is_valid(a) and a == ifc.guid('c:/x.nwf', 'project')
    assert a != ifc.guid('c:/y.nwf', 'project')


# ---- the file ------------------------------------------------------------------------------


def test_file_header_and_sections():
    text = ifc.build(model())
    lines = text.splitlines()
    assert lines[0] == 'ISO-10303-21;' and lines[-1] == 'END-ISO-10303-21;'
    parsed = ifc.read(text)
    head = parsed['header']
    assert head[0] == "FILE_DESCRIPTION(('ViewDefinition [ReferenceView_V1.2]'),'2;1');"
    assert head[1].startswith("FILE_NAME('Test \\X2\\00E9\\X0\\.ifc','2026-10-05T14:30:00',('O''Brien'),('Acme'),")
    assert head[2] == "FILE_SCHEMA(('IFC4'));"
    assert all(ord(ch) < 128 for ch in text)


def test_entities_numbered_in_order_and_references_resolve():
    parsed = ifc.read(ifc.build(model()))
    entities = parsed['entities']
    numbers = sorted(entities)
    assert numbers == list(range(1, len(numbers) + 1))
    for number in numbers:
        name, args = entities[number]
        assert name in ifc.ATTRIBUTES, name
        assert len(args) == ifc.ATTRIBUTES[name], (name, len(args))
        for ref in ifc.references(args):
            assert ref in entities, (number, ref)
            assert ref < number, 'forward reference from #%d to #%d' % (number, ref)


def _by_type(parsed, name):
    return [(n, args) for n, (kind, args) in sorted(parsed['entities'].items()) if kind == name]


def test_spatial_structure_storeys_and_containment():
    parsed = ifc.read(ifc.build(model()))
    entities = parsed['entities']
    storeys = _by_type(parsed, 'IFCBUILDINGSTOREY')
    assert [args[2] for _n, args in storeys] == ['Level 1', 'No level', 'Level 2']
    assert [args[9] for _n, args in storeys] == [0.0, 0.0, 12.0]
    project = _by_type(parsed, 'IFCPROJECT')[0]
    assert project[1][2] == 'Hospital'
    aggregates = _by_type(parsed, 'IFCRELAGGREGATES')
    assert len(aggregates) == 3
    assert aggregates[2][1][4].number == _by_type(parsed, 'IFCBUILDING')[0][0]
    contained = _by_type(parsed, 'IFCRELCONTAINEDINSPATIALSTRUCTURE')
    homes = {}
    for _n, args in contained:
        for element in args[4]:
            homes[entities[element.number][0]] = entities[args[5].number][1][2]
    assert homes == {'IFCWALL': 'Level 1', 'IFCDOOR': 'Level 2', 'IFCDUCTSEGMENT': 'No level'}


def test_elements_classes_names_and_placement():
    parsed = ifc.read(ifc.build(model()))
    entities = parsed['entities']
    wall = _by_type(parsed, 'IFCWALL')[0][1]
    assert wall[2] == 'Basic Wall: \u00dcn\u00efcode ' + SMILE
    assert wall[4] == 'Basic Wall' and wall[7] == '12345' and wall[8].value == 'NOTDEFINED'
    door = _by_type(parsed, 'IFCDOOR')[0][1]
    assert door[10].value == 'DOOR' and door[8] is None and door[11] is None
    duct = _by_type(parsed, 'IFCDUCTSEGMENT')[0][1]
    assert duct[2] == "Duct 'A' \\ main" and duct[8].value == 'RIGIDSEGMENT'
    # the door sits 0.5 above its storey (origin z 12.5, storey 12)
    placement = entities[door[5].number][1]
    axes = entities[placement[1].number][1]
    point = entities[axes[0].number][1][0]
    assert point == [1.0, 2.0, 0.5]
    relative_to = entities[placement[0].number][1]
    storey_point = entities[entities[relative_to[1].number][1][0].number][1][0]
    assert storey_point == [0.0, 0.0, 12.0]


def test_geometry_is_a_triangulated_face_set():
    parsed = ifc.read(ifc.build(model()))
    entities = parsed['entities']
    sets = _by_type(parsed, 'IFCTRIANGULATEDFACESET')
    assert len(sets) == 3
    number, args = sets[0]
    points = entities[args[0].number][1][0]
    assert len(points) == 8 and points[7] == [3.0, 3.0, 3.0]
    assert args[2] is True and args[1] is None and args[4] is None
    indices = args[3]
    assert len(indices) == 12 and min(min(t) for t in indices) == 1 and max(max(t) for t in indices) == 8
    assert sets[2][1][2] is False
    shapes = _by_type(parsed, 'IFCSHAPEREPRESENTATION')
    assert all(args[1] == 'Body' and args[2] == 'Tessellation' for _n, args in shapes)
    context = entities[shapes[0][1][0].number]
    assert context[0] == 'IFCGEOMETRICREPRESENTATIONSUBCONTEXT' and context[1][0] == 'Body'


def test_styles_shared_per_colour():
    parsed = ifc.read(ifc.build(model()))
    entities = parsed['entities']
    styles = _by_type(parsed, 'IFCSURFACESTYLE')
    assert [args[0] for _n, args in styles] == ['C8B496', '804020 50%', 'BFBFBF']
    shading = [entities[args[2][0].number][1] for _n, args in styles]
    assert shading[1][1] == 0.5 and shading[0][1] is None
    colour = entities[shading[0][0].number][1]
    assert _compat.approx(colour[1], 200 / 255.0, 1e-5)
    assert len(_by_type(parsed, 'IFCSTYLEDITEM')) == 3


def test_property_sets_typed_and_shared():
    parsed = ifc.read(ifc.build(model()))
    entities = parsed['entities']
    psets = _by_type(parsed, 'IFCPROPERTYSET')
    # the door's Element set equals the wall's once cleaned (blank and repeated names
    # dropped), so it is written once and shared
    assert [args[2] for _n, args in psets] == ['Element', 'Pset_WallCommon']
    first = [entities[ref.number][1] for ref in psets[0][1][4]]
    kinds = dict((p[0], p[2].name) for p in first)
    assert kinds == {'Category': 'IFCLABEL', 'Id': 'IFCINTEGER', 'Area': 'IFCREAL', 'Structural': 'IFCBOOLEAN',
                     'Long': 'IFCTEXT'}
    rels = _by_type(parsed, 'IFCRELDEFINESBYPROPERTIES')
    assert len(rels) == 2
    related = [[entities[r.number][0] for r in args[4]] for _n, args in rels]
    assert related == [['IFCWALL', 'IFCDOOR'], ['IFCWALL']]


def test_different_property_sets_are_kept_apart():
    data = model()
    data['elements'][1]['psets'] = [('Element', [('Category', 'Doors')])]
    parsed = ifc.read(ifc.build(data))
    assert [args[2] for _n, args in _by_type(parsed, 'IFCPROPERTYSET')] == ['Element', 'Pset_WallCommon',
                                                                            'Element']
    rels = _by_type(parsed, 'IFCRELDEFINESBYPROPERTIES')
    assert [len(args[4]) for _n, args in rels] == [1, 1, 1]


def test_global_ids_valid_and_unique():
    parsed = ifc.read(ifc.build(model()))
    ids = []
    for _n, (name, args) in parsed['entities'].items():
        if name in ('IFCPROJECT', 'IFCSITE', 'IFCBUILDING', 'IFCBUILDINGSTOREY', 'IFCWALL', 'IFCDOOR',
                    'IFCDUCTSEGMENT', 'IFCRELAGGREGATES', 'IFCRELCONTAINEDINSPATIALSTRUCTURE',
                    'IFCPROPERTYSET', 'IFCRELDEFINESBYPROPERTIES'):
            ids.append(args[0])
    assert all(ifcguid.is_valid(g) for g in ids)
    assert len(ids) == len(set(ids))


def test_units_in_the_file():
    feet = ifc.read(ifc.build(model('Feet')))
    names = [args[2] for _n, args in _by_type(feet, 'IFCCONVERSIONBASEDUNIT')]
    assert names == ['FOOT', 'SQUARE FOOT', 'CUBIC FOOT']
    metric = ifc.read(ifc.build(model('Millimeters')))
    si = [(args[1].value, args[2].value if args[2] else None, args[3].value) for _n, args in _by_type(metric, 'IFCSIUNIT')]
    assert si[0] == ('LENGTHUNIT', 'MILLI', 'METRE')
    assert ('AREAUNIT', None, 'SQUARE_METRE') in si and ('PLANEANGLEUNIT', None, 'RADIAN') in si


def test_bad_elements_raise():
    data = model()
    data['elements'][0]['faces'] = [(0, 1, 99)]
    _compat.raises(ValueError, ifc.build, data)
    data = model()
    data['elements'][1]['guid'] = data['elements'][0]['guid']
    _compat.raises(ValueError, ifc.build, data)
    data = model()
    data['elements'][0]['ifc_class'] = 'IfcSpaceship'
    _compat.raises(ValueError, ifc.build, data)


def test_progress_and_cancel():
    seen = []
    ifc.build(model(), progress=lambda f, label: seen.append((f, label)))
    assert seen[0][0] == 0.0 and seen[-1][0] == 1.0
    error = _compat.raises(RuntimeError, ifc.build, model(), lambda f, label: False)
    assert 'cancelled' in str(error)


def test_reader_rejects_junk():
    _compat.raises(ValueError, ifc.read, 'hello')
    _compat.raises(ValueError, ifc.read, 'ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\n#1=X(;\nEND-ISO-10303-21;')


def test_identical_on_both_engines():
    digest = hashlib.sha1(ifc.build(model()).encode('ascii')).hexdigest()
    assert digest == '86de499ecd1dc15829b3583a46c99d7cb361325f', digest


def test_write_file():
    folder = _compat.tmpdir('ifc_write')
    path = ifc.write(os.path.join(folder, 'x.ifc'), model())
    with open(path, 'rb') as handle:
        assert handle.read().startswith(b'ISO-10303-21;')
    assert ifc.file_stem_ok(path) and not ifc.file_stem_ok('x.ifczip')


def test_ifcopenshell_opens_and_validates():
    if _compat.IRONPYTHON:
        raise _compat.SkipTest('ifcopenshell is a CPython package')
    try:
        import ifcopenshell
        import ifcopenshell.validate
        import ifcopenshell.util.element as element_util
        import ifcopenshell.util.unit as unit_util
    except ImportError:
        raise _compat.SkipTest('ifcopenshell is not installed')
    folder = _compat.tmpdir('ifc_openshell')
    path = ifc.write(os.path.join(folder, 'x.ifc'), model())
    f = ifcopenshell.open(path)
    assert f.schema == 'IFC4'
    logger = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(f, logger, express_rules=True)
    assert logger.statements == [], logger.statements[:5]
    assert _compat.approx(unit_util.calculate_unit_scale(f), 0.3048)
    wall = f.by_type('IfcWall')[0]
    assert wall.Name.endswith(SMILE) and element_util.get_container(wall).Name == 'Level 1'
    assert element_util.get_psets(wall)['Element']['Id'] == 12345
    try:
        import ifcopenshell.geom
    except ImportError:
        return
    settings = ifcopenshell.geom.settings()
    settings.set('use-world-coords', True)
    shape = ifcopenshell.geom.create_shape(settings, f.by_type('IfcDoor')[0])
    verts = shape.geometry.verts
    zs = verts[2::3]
    assert _compat.approx(min(zs), 12.5 * 0.3048, 1e-6) and _compat.approx(max(zs), 13.5 * 0.3048, 1e-6)
