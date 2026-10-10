# -*- coding: utf-8 -*-
"""namo.inspect: the What Is It card and summary, Copy IDs rows, Open in Explorer
targets, Properties Plus summaries, and describe()/id_records() through the fake layer."""
import _compat
import test_propindex as pf

from namo import inspect


def _info():
    return {
        'doc_units': 'Feet', 'name': 'Basic Wall <A&B>', 'class_name': 'Wall',
        'class_internal': 'LcRevitWall', 'category': 'Walls', 'family': 'Basic Wall',
        'type': 'Generic 8"', 'model_name': 'ARCH.rvt', 'source_path': r'C:\M\ARCH.rvt',
        'cache_path': r'C:\M\ARCH.nwc', 'path_names': ['ARCH.nwc', 'Level 1', 'Basic Wall <A&B>'],
        'element_id': '101', 'unique_id': 'u-101', 'ifc_guid': '0abc', 'ifc_guid_derived': True,
        'instance_guid': 'aaaa', 'model_index': 0, 'path_id': '0/1',
        'bbox': ((0.0, 0.0, 0.0), (10.0, 2.0, 3.0)), 'picked': (1.0, 1.0, 1.0),
        'geometry': {'items': 2, 'primitives': 24, 'fragments': 2, 'solid': True,
                     'types': 'Triangles', 'sampled': False},
        'color': {'original': '808080', 'active': 'FF0000', 'original_t': 0.0, 'active_t': 0.5},
        'transform': {'item_identity': True, 'override': False},
        'flags': {'hidden_self': False, 'hidden_effective': True, 'required': False, 'frozen': None},
        'tabs': [('Element', [('Category', 'Walls'), ('Mark', '<W1>')]), ('Item', [('Name', 'x')])],
    }


def test_card_html_escapes_and_has_every_section():
    html = inspect.card_html(_info())
    assert 'Basic Wall &lt;A&amp;B&gt;' in html
    assert '<A&B>' not in html
    for heading in ('Identity', 'Location', 'Geometry', 'Appearance and state', 'Properties'):
        assert heading in html, heading
    assert 'derived from UniqueId' in html
    assert 'background:#FF0000' in html and '50% transparent' in html
    assert 'By a parent' in html
    assert '&lt;W1&gt;' in html
    assert '<details><summary>Element <span class="c">(2)</span>' in html
    assert '10.000 ft (3.048 m)' in html
    assert 'Picked point' in html
    assert 'ARCH.nwc &gt; Level 1' in html
    assert u'\u2014' not in html and u'\u2013' not in html


def test_card_html_with_links_and_minimal_info():
    info = {'name': 'Item', 'path_links': ['<a>A</a>', '<a>B</a>'], 'doc_units': 'Meters'}
    html = inspect.card_html(info)
    assert '<a>A</a> &gt; <a>B</a>' in html
    assert 'Geometry' not in html
    assert inspect.card_html({}).startswith('<div class="pynavis-card playground-wii">')


def test_summary_text_lines():
    text = inspect.summary_text(_info())
    lines = text.split('\r\n')
    assert lines[0] == 'Name: Basic Wall <A&B>'
    assert 'Tree path: ARCH.nwc > Level 1 > Basic Wall <A&B>' in lines
    assert 'Size: 10.000 ft x 2.000 ft x 3.000 ft' in lines
    assert 'Element ID: 101' in lines
    assert all(': ' in line for line in lines)


def test_small_formatters():
    assert inspect.guid_text('{AAAA0000-0000-0000-0000-000000000001}') == 'aaaa0000-0000-0000-0000-000000000001'
    assert inspect.guid_text('00000000-0000-0000-0000-000000000000') == ''
    assert inspect.guid_text(None) == ''
    assert inspect.color_hex((1.0, 0.5, 0.0)) == 'FF8000'
    assert inspect.color_hex(None) is None
    assert inspect.length_pair(1.0, 'Meters') == '1.000 m'
    assert inspect.point_text((1, 2, 3), 'Millimeters') == '1.000, 2.000, 3.000 mm'
    assert inspect.percent(0.25) == '25%'
    assert inspect.yes_no(None) == 'Unknown'


def test_id_table_columns_follow_catalogue_order():
    records = [{'name': 'Wall', 'element_id': '1', 'unique_id': 'u', 'file': 'A.rvt', 'path': 'A > Wall'}]
    headers, rows = inspect.id_table(records, ['path', 'name', 'bogus'])
    assert headers == ['Name', 'Tree path']
    assert rows == [['Wall', 'A > Wall']]
    headers, rows = inspect.id_table(records)
    assert headers[0] == 'Name' and len(headers) == len(inspect.ID_COLUMNS)
    assert rows[0][3] == ''


def test_explorer_targets_dedupe_and_presence():
    present = set([r'C:\M\ARCH.rvt'])
    targets = inspect.explorer_targets(r'C:\M\ARCH.nwc', r'C:\M\ARCH.rvt', lambda p: p in present)
    assert targets == [('Source file', r'C:\M\ARCH.rvt', True), ('Cache file', r'C:\M\ARCH.nwc', False)]
    same = inspect.explorer_targets('C:/M/A.nwd', r'c:\m\a.nwd', lambda p: True)
    assert len(same) == 1
    assert inspect.explorer_targets('', None, lambda p: True) == []


def test_pins_and_summaries():
    assert inspect.parse_pin('Element > Category') == ('Element', 'Category')
    assert inspect.parse_pin('Category') is None
    assert inspect.parse_pin(' > x') is None
    assert inspect.clean_pins(['Element > Mark', 'element > mark', 'bad', 'Item > Name']) == [
        'Element > Mark', 'Item > Name']
    same = inspect.summarize(['A', 'A'])
    assert same['state'] == 'same' and same['value'] == 'A'
    varies = inspect.summarize(['A', 'B', 'A', '(missing)'])
    assert varies['state'] == 'varies' and varies['value'] == 'Varies (3 values)'
    assert varies['first'][0] == 'A' and varies['present'] == 3
    assert 'A  (2)' in inspect.varies_tooltip(varies)
    missing = inspect.summarize(['(missing)', '(missing)'])
    assert missing['state'] == 'missing'
    assert inspect.summarize([])['state'] == 'none'
    many = inspect.summarize([str(i) for i in range(8)])
    assert 'and 3 more' in inspect.varies_tooltip(many)


def test_describe_and_id_records_through_fakes():
    doc, n = pf.tree()
    with pf.Fake(doc, 'Meters'):
        info = inspect.describe(n['Wall 1 solid'], doc, picked=(0.5, 0.5, 0.5), links=False)
        assert info['name'] == 'Wall 1 solid'
        assert info['category'] == 'Walls' and info['element_id'] == '101'
        assert info['ifc_guid_derived'] is True and info['ifc_guid']
        assert info['model_name'] == 'ARCH.rvt'
        assert info['path_names'] == ['ARCH.nwc', 'Level 1', 'Wall 1', 'Wall 1 solid']
        assert info['bbox'] == ((0, 0, 0), (1, 5, 3))
        assert info['geometry']['items'] == 1
        assert info['flags']['hidden_effective'] is False
        assert 'Wall 1' in info['object_link']
        html = inspect.card_html(info)
        assert 'Wall 1 solid' in html
        element = inspect.describe(n['Wall 1'], doc, links=False)
        assert element['tabs'][0][0] == 'Element'
        assert element['instance_guid'] == 'aaaa0000-0000-0000-0000-000000000001'
        records = inspect.id_records([n['Wall 1 solid'], n['Wall 1'], n['Duct solid']], doc)
        assert [r['name'] for r in records] == ['Wall 1', 'Duct']
        assert records[0]['element_id'] == '101' and records[0]['file'] == 'ARCH.rvt'
        assert records[1]['path'] == 'MEP.nwc > Duct'


def test_group_tools_follow_the_shipped_routes():
    # Refit: no tool of the Inspect and Data panels uses the custom pick tool (its hover
    # marker and its hit disagree in the field); What Is It picks through namo.picking.
    # The Selection HUD toggle asks the window, not the button, whether it is on.
    import io
    import os
    tab = os.path.join(_compat.ROOT, 'Playground.extension', 'Model.tab')
    lib = os.path.join(_compat.LIB, 'namo')
    paths = []
    for panel in ('Inspect.panel', 'Data.panel'):
        for folder, _dirs, files in os.walk(os.path.join(tab, panel)):
            paths.extend(os.path.join(folder, name) for name in files if name.endswith('.py'))
    for name in ('inspect', 'insp_propsplus', 'hud', 'propindex', 'propwrite', 'validator', 'data_common',
                 'data_explorer', 'data_labels', 'data_write'):
        paths.append(os.path.join(lib, name + '.py'))
    assert len(paths) > 20
    texts = {}
    for path in paths:
        with io.open(path, 'r', encoding='utf-8') as handle:
            texts[path] = handle.read()
    for path, text in texts.items():
        for banned in ('pick.point', 'pick.Unavailable', 'point_then'):
            assert banned not in text, '%s uses %s' % (path, banned)
    what = [t for p, t in texts.items() if p.endswith(os.path.join('What_Is_It.pushbutton', 'script.py'))][0]
    assert 'picking.point(' in what and 'want_item=True' in what
    toggle = [t for p, t in texts.items() if p.endswith(os.path.join('Selection_HUD.toggle', 'script.py'))][0]
    assert 'hud.is_running()' in toggle and 'get_toggle_state' not in toggle
