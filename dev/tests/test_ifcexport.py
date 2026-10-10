# -*- coding: utf-8 -*-
"""namo.ifcexport: category to IFC class, overrides, storeys, property sets, GlobalIds,
and the model assembled from read records (fake document) and written by namo.ifc."""
import _compat

from namo import ifc, ifcexport as x, ifcguid, paths


def test_class_for_revit_categories():
    assert x.class_for('Walls') == ('IfcWall', None)
    assert x.class_for('  ducts ') == ('IfcDuctSegment', 'RIGIDSEGMENT')
    assert x.class_for('Structural Framing') == ('IfcBeam', 'BEAM')
    assert x.class_for('Cable Trays') == ('IfcCableCarrierSegment', 'CABLETRAYSEGMENT')
    assert x.class_for('Doors') == ('IfcDoor', 'DOOR')
    assert x.class_for('Generic Models') == ('IfcBuildingElementProxy', None)
    assert x.class_for('Mechanical Equipment') == ('IfcBuildingElementProxy', None)
    assert x.class_for('') == ('IfcBuildingElementProxy', None)


def test_class_for_ifc_sourced_models():
    assert x.class_for('IfcWallStandardCase') == ('IfcWall', None)
    assert x.class_for('IFCSLAB') == ('IfcSlab', None)
    assert x.class_for('IfcColumn') == ('IfcColumn', None)
    assert x.class_for('IfcSpace') == ('IfcBuildingElementProxy', None)


def test_every_mapped_class_is_writable():
    for category in x.CLASS_MAP:
        cls, predefined = x.CLASS_MAP[category]
        assert cls in ifc.ELEMENT_CLASSES, category
        if predefined:
            assert predefined in x.PREDEFINED[cls], category


def test_overrides_parse_and_win():
    mapping, errors = x.parse_overrides('# team rules\nSpecialty Equipment = IfcFurniture\n'
                                        'structural framing = ifcbeam.joist\n\nbad line\n'
                                        'Walls = IfcSpaceship\nWindows = IfcWindow.DOOR\n = IfcWall')
    assert mapping == {'specialty equipment': ('IfcFurniture', None),
                       'structural framing': ('IfcBeam', 'JOIST')}
    assert len(errors) == 4
    assert errors[0] == 'Line 5 needs "Category = IfcClass".'
    assert errors[1].startswith('Line 6: IfcSpaceship is not an IFC class')
    assert errors[2] == 'Line 7: DOOR is not a type of IfcWindow.'
    assert x.class_for('Structural Framing', mapping) == ('IfcBeam', 'JOIST')
    assert x.class_for('Specialty Equipment', mapping) == ('IfcFurniture', None)
    assert x.overrides_text(mapping) == 'specialty equipment = IfcFurniture\nstructural framing = IfcBeam.JOIST'
    _compat.raises(ValueError, x.parse_class, 'IfcBeam.USERDEFINED')


def test_storey_by_elevation():
    levels = [('Level 2', 4000.0), ('Level 1', 0.0), ('Roof', 8000.0)]
    assert x.storey_by_elevation(levels, 10.0) == ('Level 1', 0.0)
    assert x.storey_by_elevation(levels, 3999.0) == ('Level 1', 0.0)
    assert x.storey_by_elevation(levels, 3999.0, tolerance=5.0) == ('Level 2', 4000.0)
    assert x.storey_by_elevation(levels, -500.0) == ('Level 1', 0.0)
    assert x.storey_by_elevation(levels, 9000.0) == ('Roof', 8000.0)
    assert x.storey_by_elevation([], 1.0) is None


def test_plan_storeys_auto_grid_and_one():
    levels = [('Level 1', 0.0), ('Level 2', 4000.0)]
    records = [{'level': 'Level 2', 'bottom': 4100.0}, {'level': None, 'bottom': 50.0},
               {'level': 'Mezzanine', 'bottom': 2000.0}, {'level': None, 'bottom': None},
               {'level': 'level 2', 'bottom': 4500.0}]
    storeys, keys = x.plan_storeys(records, levels, 'auto')
    assert [(s['name'], s['elevation']) for s in storeys] == [('Level 1', 0.0), ('Mezzanine', 2000.0),
                                                              ('Level 2', 4000.0)]
    assert keys == ['level 2', 'level 1', 'mezzanine', None, 'level 2']
    storeys, keys = x.plan_storeys(records, levels, 'grid')
    assert [s['name'] for s in storeys] == ['Level 1', 'Level 2']
    assert keys == ['level 2', 'level 1', 'level 1', None, 'level 2']
    storeys, keys = x.plan_storeys(records, levels, 'one')
    assert storeys == [{'key': 'one', 'name': 'Level 1', 'elevation': 50.0}] and keys == ['one'] * 5
    storeys, keys = x.plan_storeys([{'level': None, 'bottom': 3.0}], [], 'auto')
    assert storeys == [] and keys == [None]


def test_psets_from_rows():
    rows = [{'category': 'Item', 'property': 'Name', 'value': 'Duct'},
            {'category': 'Element', 'property': 'Category', 'value': 'Ducts'},
            {'category': 'Element', 'property': 'Mark', 'value': '  '},
            {'category': 'Revit Type', 'property': 'Width', 'value': 1.5},
            {'category': 'Element', 'property': 'Id', 'value': 7},
            {'category': 'Geometry', 'property': 'Primitives', 'value': 12},
            {'category': 'Element', 'property': 'Comments', 'value': None}]
    assert x.psets_from_rows(rows) == [('Element', [('Category', 'Ducts'), ('Id', 7)]),
                                       ('Revit Type', [('Width', 1.5)])]
    every = x.psets_from_rows(rows, skip=())
    assert [name for name, _props in every] == ['Item', 'Element', 'Revit Type', 'Geometry']


def test_choose_guid_prefers_model_ids_and_never_repeats():
    used = set()
    revit = ifcguid.from_revit_unique_id('60f91daf-3dd7-4283-a86d-24137b73f3da-0001fd0b')
    assert x.choose_guid([revit, None], 'seed', 'k1', used) == revit
    instance = '8ed7f62a-4c4e-4a3b-9a6e-3f2b9f1d6c11'
    assert x.choose_guid([revit, instance], 'seed', 'k2', used) == ifcguid.compress(instance)
    derived = x.choose_guid([revit, instance, 'not a guid'], 'seed', 'k3', used)
    assert ifcguid.is_valid(derived) and derived not in (revit, ifcguid.compress(instance))
    again = x.choose_guid([], 'seed', 'k3', used)
    assert again != derived and len(used) == 4
    assert x.choose_guid(['00000000-0000-0000-0000-000000000000'], 'seed', 'k4', set()) != \
        '0000000000000000000000'


def test_object_type_and_closed():
    assert x.object_type_of({'family': 'Rectangular Duct', 'type': 'Radius Elbows'}, 'Ducts') == \
        'Rectangular Duct: Radius Elbows'
    assert x.object_type_of({'family': None, 'type': 'Basic'}, 'Walls') == 'Basic'
    assert x.object_type_of({}, 'Walls') == 'Walls'
    assert x._closed([(0, 1, 2), (0, 2, 3), (0, 3, 1), (1, 3, 2)])
    assert not x._closed([(0, 1, 2)])


def cube(x0, y0, z0, s):
    p = [(x0 + dx * s, y0 + dy * s, z0 + dz * s) for dx in (0, 1) for dy in (0, 1) for dz in (0, 1)]
    faces = [(0, 2, 6), (0, 6, 4), (1, 5, 7), (1, 7, 3), (0, 4, 5), (0, 5, 1),
             (2, 3, 7), (2, 7, 6), (0, 1, 3), (0, 3, 2), (4, 6, 7), (4, 7, 5)]
    return [tuple(p[i] for i in f) for f in faces]


def test_element_for_makes_local_vertices():
    record = {'name': 'Duct', 'category': 'Ducts', 'tris': cube(100.0, 200.0, 3000.0, 10.0),
              'color': '4E79A7', 'transparency': 0.0, 'ids': {'element_id': '42', 'family': 'Duct', 'type': 'Rect'}}
    element = x.element_for(record, 'IfcDuctSegment', 'RIGIDSEGMENT', ifc.guid('s', 'e'), 'level 1', [])
    assert element['origin'] == (100.0, 200.0, 3000.0)
    assert min(v[0] for v in element['vertices']) == 0.0 and max(v[2] for v in element['vertices']) == 10.0
    assert element['closed'] and element['tag'] == '42' and element['object_type'] == 'Duct: Rect'
    assert x.element_for({'tris': []}, 'IfcWall', None, 'x', None, []) is None


def test_summary():
    assert x.summary(0, 3)[0] == 'warning'
    assert x.summary(12, 0, storeys=3) == ('success', 'Exported 12 objects to IFC', '3 storeys.')
    level, message, detail = x.summary(1, 2, sampled=True, storeys=1)
    assert level == 'warning' and message == 'Exported 1 object to IFC'
    assert detail == '2 skipped (listed in the output window); the selection was sampled.'


# ---- assembling a model from read records (fake document) ---------------------------------


class FakeLevel(object):
    def __init__(self, name, elevation):
        self.DisplayName = name
        self.Elevation = elevation


class FakeSystem(object):
    def __init__(self, levels):
        self.Levels = levels


class FakeGrids(object):
    def __init__(self, system):
        self.ActiveSystem = system


class FakeDoc(object):
    def __init__(self):
        self.Units = 'Millimeters'
        self.Title = 'Hospital.nwf'
        self.FileName = r'C:\Jobs\Hospital.nwf'
        self.Grids = FakeGrids(FakeSystem([FakeLevel('Level 1', 0.0), FakeLevel('Level 2', 4000.0)]))


def read_records():
    return {'records': [
        {'name': 'Wall A', 'model': 'ARCH.nwc', 'category': 'Walls', 'color': 'C8B496', 'transparency': 0.0,
         'tris': cube(0.0, 0.0, 0.0, 3000.0), 'noise': 0.0, 'bottom': 0.0, 'level': 'Level 1',
         'instance_guid': None, 'rows': [{'category': 'Element', 'property': 'Category', 'value': 'Walls'}],
         'ids': {'ifc_guid': ifcguid.compress('11111111-2222-3333-4444-555555555555'), 'element_id': '1'}},
        {'name': 'Duct B', 'model': 'MEP.nwc', 'category': 'Ducts', 'color': None, 'transparency': 0.0,
         'tris': cube(500.0, 500.0, 4200.0, 300.0), 'noise': 0.0, 'bottom': 4200.0, 'level': None,
         'instance_guid': None, 'rows': [], 'ids': {'ifc_guid': ifcguid.compress('11111111-2222-3333-4444-555555555555')}},
        {'name': 'Speck', 'model': 'MEP.nwc', 'category': 'Ducts', 'color': None, 'transparency': 0.0,
         'tris': [((0, 0, 0), (0, 0, 0), (0, 0, 0))], 'noise': 0.0, 'bottom': 0.0, 'level': None,
         'instance_guid': None, 'rows': [], 'ids': {}},
    ], 'skipped': [], 'sampled': False, 'objects': 3}


def test_model_for_and_build():
    previous = paths.redirect(_compat.tmpdir('ifcexport_model'))
    try:
        model, dropped = x.model_for(read_records(), FakeDoc(), {'storeys': 'auto', 'psets': 'data',
                                                                 'project': 'Hospital', 'building': 'Main'},
                                     'Hospital.ifc', 'c:\\jobs\\hospital.nwf',
                                     overrides={'walls': ('IfcCurtainWall', None)})
    finally:
        paths.redirect(previous)
    assert dropped == ['Speck']
    assert model['length_unit'] == 'Millimeters' and model['project']['name'] == 'Hospital'
    assert [s['name'] for s in model['storeys']] == ['Level 1', 'Level 2']
    wall, duct = model['elements']
    assert wall['ifc_class'] == 'IfcCurtainWall' and wall['storey'] == 'level 1'
    assert duct['ifc_class'] == 'IfcDuctSegment' and duct['storey'] == 'level 2'
    assert wall['guid'] != duct['guid']                     # the repeated id was replaced
    assert wall['psets'] == [('Element', [('Category', 'Walls')])]
    parsed = ifc.read(ifc.build(model))
    names = sorted(args[2] for _n, (kind, args) in parsed['entities'].items() if kind == 'IFCBUILDINGSTOREY')
    assert names == ['Level 1', 'Level 2']
