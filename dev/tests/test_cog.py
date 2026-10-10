# -*- coding: utf-8 -*-
"""namo.cog: density tables, matching, combining, formatting, the marker and the workbook."""
import os

import _compat
from namo import cog


def test_parse_densities():
    table, errors = cog.parse_densities(cog.DEFAULTS['densities'] + '\n# comment\n\nLead=11,340\nbad\nx = y\n = 5')
    assert table[0] == ('steel', 7850.0) and ('lead', 11340.0) in table
    assert errors == ['Line 11: write it as material = density, like steel = 7850.',
                      'Line 12: "y" is not a number.',
                      'Line 13: needs a material word and a density above zero.']
    assert cog.parse_densities('') == ([], [])


def test_match_density_material_then_category():
    table, _ = cog.parse_densities(cog.DEFAULTS['densities'])
    assert cog.match_density(['Steel, ASTM A992'], 'Structural Framing', table) == ('steel', 7850.0, 'material')
    assert cog.match_density(['Concrete - Cast-in-Place 30 MPa'], 'Floors', table)[1] == 2400.0
    assert cog.match_density([], 'Glass Panels', table) == ('glass', 2500.0, 'category')
    assert cog.match_density(['Paint'], 'Walls', table) is None
    assert cog.match_density(['Aluminum mullion'], None, table)[1] == 2700.0


def test_combine_and_format():
    result = cog.combine([(1000.0, (0.0, 0.0, 0.0)), (3000.0, (4.0, 0.0, 2.0)), (None, (9, 9, 9)),
                          (50.0, None), (0.0, (1, 1, 1))])
    assert result['mass'] == 4000.0 and result['count'] == 2
    assert result['cog'] == (3.0, 0.0, 1.5)
    assert cog.combine([]) == {'mass': 0.0, 'cog': None, 'count': 0}
    assert cog.format_mass(860.4) == '860 kg' and cog.format_mass(12400.0) == '12.4 t'
    assert cog.format_mass(453.59237, imperial=True) == '1,000 lb'
    assert cog.format_mass(None) == ''
    assert cog.format_point((1, 2.5, -3)) == '1.000, 2.500, -3.000'


def test_marker():
    segs = cog.marker_segments((1, 2, 3), 0.5)
    assert segs[0] == ((0.5, 2.0, 3.0), (1.5, 2.0, 3.0), False) and len(segs) == 3
    assert cog.marker_size(None, 0.3048) == 0.25 / 0.3048
    assert _compat.approx(cog.marker_size(((0, 0, 0), (30, 40, 0)), 1.0), 1.5)


def _result(name, mass, volume, centroid, method='mesh', density=None):
    return {'name': name, 'mass_kg': mass, 'volume_m3': volume, 'centroid': centroid,
            'method_label': cog.METHODS[method], 'density': density, 'density_from': 'material'}


def test_rows_and_workbook():
    results = [_result('Beam', 785.0, 0.1, (1.0, 2.0, 3.0), density=7850.0),
               _result('Slab', None, 2.0, (0, 0, 0), 'bbox')]
    rows = cog.result_rows(results, False, 'Meters')
    assert rows[0]['cells'] == ['Beam', '785 kg', 0.1, '7,850 (material)', 1.0, 2.0, 3.0, 'Closed mesh']
    assert rows[1]['cells'][1] == 'No mass' and rows[1]['cells'][7] == 'Bounding box (estimate)'
    path = os.path.join(_compat.tmpdir('cog'), 'cog.xlsx')
    combined = cog.combine([(r['mass_kg'], r['centroid']) for r in results])
    cog.write_xlsx(path, results, combined, False, 'Meters', 'Centre of gravity')
    import zipfile
    with zipfile.ZipFile(path) as package:
        assert 'xl/worksheets/sheet1.xml' in package.namelist()
    if _compat.IRONPYTHON:
        return
    import openpyxl
    sheet = openpyxl.load_workbook(path)['Objects']
    values = [[c.value for c in row] for row in sheet.iter_rows(min_row=1)]
    assert values[1][0] == 'Total 785 kg, centre of gravity 1.000, 2.000, 3.000 m'
    assert values[2][:2] == ['Object', 'Mass (kg)'] and values[3][:2] == ['Beam', 785]


def test_measure_object_falls_back_to_the_box():
    import test_items as nav
    doc, n = nav.model_tree()
    table, _ = cog.parse_densities('wall = 1000')
    with nav.FakeNav(doc):
        result = cog.measure_object(n['Wall 1'], 'Meters', table, fill_factor=0.5)
    assert result['method'] == 'bbox' and result['method_label'] == 'Bounding box (estimate)'
    assert result['centroid'] == (0.5, 2.5, 1.5)
    assert _compat.approx(result['volume_m3'], 1 * 5 * 3 * 0.5)
    assert result['density'] == 1000.0 and result['density_from'] == 'category'
    assert _compat.approx(result['mass_kg'], 7500.0)
    with nav.FakeNav(doc):
        bare = cog.measure_object(n['Duct'], 'Millimeters', [], fill_factor=1.0)
    assert bare['mass_kg'] is None and _compat.approx(bare['volume_m3'], 2 * 0.5 * 0.5 * 1e-9)


def test_combine_far_from_the_origin():
    # Moments are taken about the first centroid, so shared coordinates cost no digits.
    x, y = 1370000.125, -1370000.5
    result = cog.combine([(1000.0, (x, y, 10.0)), (3000.0, (x + 4.0, y, 12.0))])
    assert result['count'] == 2
    assert abs(result['cog'][0] - (x + 3.0)) < 1e-9 and abs(result['cog'][1] - y) < 1e-9
    assert abs(result['cog'][2] - 11.5) < 1e-9
