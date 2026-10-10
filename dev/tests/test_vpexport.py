# -*- coding: utf-8 -*-
"""namo.vpexport: exchange XML writer and reader (round trip), packages, unit scaling,
and records read from saved viewpoints on the fake."""
import json
import xml.dom.minidom

import _compat
from _compat import approx, raises

import test_items as nav
import test_vp_common as vpfake
from namo import camera, vpexport


def _record(folder, name, position=(1.5, -2.0, 3.25), projection='persp', comments=None, clip=None):
    cam = camera.make_cam(position, rotation=(0.1, 0.2, 0.3, 0.927362), projection=projection,
                          height_field=0.785398 if projection == 'persp' else 25.0, focal_distance=12.5,
                          aspect=1.6)
    cam.update({'near': 0.1, 'far': 900.0, 'linear': 3.0, 'angular': 0.7854, 'world_up': [0.0, 0.0, 1.0],
                'render': 'Shaded', 'lighting': 'FullLights'})
    return {'folder': folder, 'name': name, 'guid': 'g-' + name, 'camera': cam, 'clip': clip,
            'comments': comments or []}


CLIP = {'enabled': True, 'mode': 'Planes', 'linked': False, 'active': 1,
        'range': [[0.0, 0.0, 0.0], [10.0, 10.0, 10.0]],
        'planes': [{'index': 0, 'state': 'Enabled', 'enabled': True, 'alignment': 'Custom',
                    'origin': [0.0, 0.0, 4.0], 'normal': [0.0, 0.0, -1.0]},
                   {'index': 1, 'state': 'Default', 'enabled': False, 'alignment': 'Top',
                    'origin': [0.0, 0.0, 0.0], 'normal': [0.0, 0.0, 1.0], 'distance': 0.0}]}


def test_codes_and_numbers():
    assert vpexport.unit_code('Feet') == 'ft' and vpexport.unit_code('Millimeters') == 'mm'
    assert vpexport.unit_name('ft') == 'Feet' and vpexport.unit_name('Meters') == 'Meters'
    assert vpexport.unit_name('parsecs') == 'Meters'
    assert vpexport.num(1.0) == '1' and vpexport.num(-0.0) == '0' and vpexport.num(0.1234567) == '0.1234567'
    assert vpexport.num(1e-12) == '0' and vpexport.num(123456.5) == '123456.5'
    assert vpexport.num(float('nan')) == '0'
    assert vpexport.esc('a<b & "c"\x01') == 'a&lt;b &amp; &quot;c&quot;'


def test_exchange_layout_is_documented_in_one_place():
    for tag in ('<exchange', '<viewpoints>', '<viewfolder', '<view ', '<viewpoint ', '<camera ', '<pos3f',
                '<quaternion', '<up>', '<clipplaneset', '<comments>'):
        assert tag in vpexport.EXCHANGE_LAYOUT


def test_exchange_xml_is_well_formed_and_nested():
    records = [_record('', 'Top'), _record('A', 'One', comments=[{'body': 'Fix <this>', 'author': 'Ann',
                                                                 'status': 'Active', 'date': '2026-10-05T14:30:00'}]),
               _record('A/B', 'Two', projection='ortho'), _record('A', 'Three')]
    text = vpexport.exchange_xml(records, 'Feet', 'Hospital.nwf', r'C:\Jobs', include_clip=False)
    dom = xml.dom.minidom.parseString(text.encode('utf-8'))
    root = dom.documentElement
    assert root.tagName == 'exchange' and root.getAttribute('units') == 'ft'
    assert root.getAttribute('filename') == 'Hospital.nwf'
    holder = root.getElementsByTagName('viewpoints')[0]
    top = [c for c in holder.childNodes if c.nodeType == c.ELEMENT_NODE]
    assert [c.tagName for c in top] == ['view', 'viewfolder']
    folder_a = top[1]
    kids = [c for c in folder_a.childNodes if c.nodeType == c.ELEMENT_NODE]
    assert [(c.tagName, c.getAttribute('name')) for c in kids] == [('view', 'One'), ('viewfolder', 'B'),
                                                                   ('view', 'Three')]
    camera_node = dom.getElementsByTagName('camera')[2]
    assert camera_node.getAttribute('projection') == 'ortho' and camera_node.getAttribute('height') == '25'
    quat = dom.getElementsByTagName('quaternion')[0]
    assert quat.getAttribute('a') == '0.1' and quat.getAttribute('d') == '0.927362'
    assert 'Fix &lt;this&gt;' in text and '<clipplaneset' not in text
    vp = dom.getElementsByTagName('viewpoint')[0]
    assert vp.getAttribute('render') == 'shaded' and vp.getAttribute('lighting') == 'full'
    assert vp.getAttribute('focal') == '12.5'


def test_exchange_round_trip():
    records = [_record('', 'Top', clip=CLIP),
               _record('A/B', 'Two', projection='ortho', comments=[{'body': 'Line 1', 'author': 'Bo',
                                                                     'status': 'Resolved', 'date': '2026-01-02T03:04:05'}])]
    text = vpexport.exchange_xml(records, 'Millimeters', include_clip=True)
    back, units, notes = vpexport.read_exchange(text)
    assert units == 'Millimeters' and notes == []
    assert [(r['folder'], r['name'], r['guid']) for r in back] == [('', 'Top', 'g-Top'), ('A/B', 'Two', 'g-Two')]
    cam = back[0]['camera']
    assert approx(cam['position'], [1.5, -2.0, 3.25]) and approx(cam['rotation'], [0.1, 0.2, 0.3, 0.927362])
    assert cam['projection'] == 'persp' and approx(cam['height_field'], 0.785398)
    assert approx(cam['focal_distance'], 12.5) and approx(cam['aspect'], 1.6)
    assert cam['near'] == 0.1 and cam['far'] == 900.0 and cam['lighting'] == 'FullLights'
    assert back[1]['camera']['projection'] == 'ortho' and back[1]['camera']['height_field'] == 25.0
    clip = back[0]['clip']
    assert clip['enabled'] and clip['mode'] == 'Planes' and clip['range'][1] == [10.0, 10.0, 10.0]
    assert clip['planes'][0]['enabled'] and approx(clip['planes'][0]['origin'], [0.0, 0.0, 4.0])
    assert approx(clip['planes'][0]['distance'], -4.0) and clip['planes'][1]['alignment'] == 'Top'
    comment = back[1]['comments'][0]
    assert comment == {'body': 'Line 1', 'author': 'Bo', 'status': 'Resolved', 'date': '2026-01-02T03:04:05'}
    again = vpexport.exchange_xml(back, 'Millimeters', include_clip=True)
    assert vpexport.read_exchange(again)[0][1]['comments'] == back[1]['comments']


def test_reader_refuses_what_is_not_a_viewpoint_export():
    raises(ValueError, vpexport.read_exchange, 'not xml at all <')
    raises(ValueError, vpexport.read_exchange, '<?xml version="1.0"?><selectionsets/>')
    raises(ValueError, vpexport.read_exchange, '<exchange units="m"><selectionsets/></exchange>')
    text = ('<exchange units="ft"><viewpoints><view name="Broken"/><animation name="Spin"/>'
            '<view name="Ok"><viewpoint><camera projection="persp" height="1"><position><pos3f x="1" y="2" z="3"/>'
            '</position></camera></viewpoint></view></viewpoints></exchange>')
    records, units, notes = vpexport.read_exchange(text)
    assert [r['name'] for r in records] == ['Ok'] and units == 'Feet' and len(notes) == 2
    assert records[0]['camera']['rotation'] == [0.0, 0.0, 0.0, 1.0]


def test_scaling_cameras_and_sections():
    rec = _record('', 'Ortho', projection='ortho', clip=CLIP)
    rec['camera']['json'] = '{"x": 1}'
    scaled = vpexport.scale_record(rec, 1000.0)
    cam = scaled['camera']
    assert approx(cam['position'], [1500.0, -2000.0, 3250.0]) and cam['height_field'] == 25000.0
    assert cam['focal_distance'] == 12500.0 and cam['near'] == 100.0 and cam['json'] is None
    assert scaled['clip']['planes'][0]['origin'] == [0.0, 0.0, 4000.0]
    assert scaled['clip']['range'][1] == [10000.0, 10000.0, 10000.0]
    assert rec['camera']['position'][0] == 1.5                       # the original is untouched
    persp = vpexport.scale_camera(_record('', 'P')['camera'], 2.0)
    assert approx(persp['height_field'], 0.785398)                    # an angle is not scaled
    assert vpexport.scale_clip(None, 2.0) is None


def test_package_round_trip_through_json():
    records = [_record('A', 'One', clip=CLIP, comments=[{'body': 'b', 'author': '', 'status': 'New', 'date': ''}])]
    data = vpexport.package(records, 'Feet', {'file': 'Hospital.nwf'}, created='2026-10-05T10:00:00')
    data = json.loads(json.dumps(data, sort_keys=True))
    back, units, notes = vpexport.read_package(data)
    assert units == 'Feet' and notes == [] and back[0]['clip'] == CLIP
    assert back[0]['camera']['position'] == [1.5, -2.0, 3.25]
    raises(ValueError, vpexport.read_package, {'format': 'other'})
    raises(ValueError, vpexport.read_package, {'format': vpexport.FORMAT, 'version': 99})
    damaged = dict(data, views=[{'name': 'x'}, data['views'][0]])
    back, _u, notes = vpexport.read_package(damaged)
    assert len(back) == 1 and notes == ['A damaged view entry was skipped.']


def test_read_file_by_extension():
    folder = _compat.tmpdir('vpexport_files')
    from namo import paths
    xml_path = folder + '\\views.xml'
    paths.atomic_write_text(xml_path, vpexport.exchange_xml([_record('', 'V')], 'Meters'))
    records, units, _n = vpexport.read_file(xml_path)
    assert records[0]['name'] == 'V' and units == 'Meters'
    pkg = folder + '\\views.nvp.json'
    paths.write_json(pkg, vpexport.package([_record('F', 'W')], 'Inches'))
    records, units, _n = vpexport.read_file(pkg)
    assert records[0]['folder'] == 'F' and units == 'Inches'
    raises(ValueError, vpexport.read_file, folder + '\\missing.nvp.json')


def test_folder_counts():
    records = [_record('A', 'x'), _record('', 'y'), _record('A', 'z')]
    assert vpexport.folder_counts(records) == [('A', 2), ('', 1)]


def test_records_from_saved_views_on_the_fake():
    doc = vpfake.make_doc()
    vpfake.tree(doc)
    with nav.FakeNav(doc) as fake:
        vpfake.extend(fake.Api)
        from namo import vp_common
        rows = vp_common.view_rows(doc)
        records = vpexport.records_from(rows, doc)
        text = vpexport.exchange_xml(records, 'Meters', include_clip=True)
    assert [r['name'] for r in records] == ['Top', 'One', 'Two', 'Three']
    assert records[0]['comments'][0]['body'] == 'Look here'
    assert records[0]['camera']['position'] == [0.0, 0.0, 10.0]
    assert records[0]['clip']['mode'] == 'Planes'
    assert records[1]['folder_guids']['A/B'] == str(doc.SavedViewpoints.RootItem.Children[1].Children[1].Guid)
    assert 'guid="%s"' % records[1]['folder_guids']['A'] in text
    back, _units, _notes = vpexport.read_exchange(text)
    assert [(r['folder'], r['name']) for r in back] == [('', 'Top'), ('A', 'One'), ('A/B', 'Two'), ('C', 'Three')]


def test_export_fields_defaults_are_option_values():
    from namo import ui
    fields = vpexport.export_fields({'format': 'package', 'comments': False, 'clip_xml': True})
    vpfake.check_defaults(fields)
    specs = ui.normalize_fields(fields)
    values, errors = ui.collect(specs, {'format': 'package', 'comments': False, 'clip_xml': True})
    assert not errors and values['format'] == 'package'
    assert not ui.is_enabled([f for f in specs if f['key'] == 'clip_xml'][0], values)
