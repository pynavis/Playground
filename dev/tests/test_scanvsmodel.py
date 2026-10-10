# -*- coding: utf-8 -*-
"""namo.scanvsmodel: scan detection, bands, banding and summaries, the test definition,
and collect/paint through the fake layer."""
import _compat
import test_clashset_tests as cf

from namo import scanvsmodel as svm

nav = cf.nav


def test_looks_like_scan():
    assert svm.looks_like_scan('Level 2 scan.RCP')
    assert svm.looks_like_scan(r'C:\scans\site.e57')
    assert not svm.looks_like_scan('MEP.nwc')
    assert not svm.looks_like_scan(None)


def test_parse_bands_with_trailing_unit_and_mixed():
    assert svm.parse_bands('25, 50, 100 mm', 'Meters') == [0.025, 0.05, 0.1]
    assert svm.parse_bands('100mm; 25mm, 50 mm', 'Millimeters') == [25.0, 50.0, 100.0]
    feet = svm.parse_bands('1", 2", 4"', 'Feet')
    assert _compat.approx(feet, [1.0 / 12, 2.0 / 12, 4.0 / 12])
    assert svm.parse_bands('0.05, 0.025', 'Meters') == [0.025, 0.05]
    assert svm.parse_bands('25, 25 mm', 'Millimeters') == [25.0]


def test_parse_bands_errors():
    _compat.raises(ValueError, svm.parse_bands, '', 'Meters')
    error = _compat.raises(ValueError, svm.parse_bands, '25, wide', 'Meters')
    assert 'not a length' in str(error)
    _compat.raises(ValueError, svm.parse_bands, ', '.join(str(i) for i in range(1, 11)), 'Meters')


def test_default_bands_text_reads_back():
    assert svm.parse_bands(svm.default_bands_text('Millimeters'), 'Millimeters') == [25.0, 50.0, 100.0]
    assert len(svm.parse_bands(svm.default_bands_text('Feet'), 'Feet')) == 3


def test_band_labels_and_colors():
    labels = svm.band_labels([25.0, 50.0, 100.0], 'Millimeters')
    assert labels == ['Intrudes', 'Within 25 mm', '25 to 50 mm', '50 to 100 mm']
    assert svm.band_labels([1.0 / 12, 2.0 / 12], 'Feet')[2] == '0\' 1" to 0\' 2"'
    palette = svm.band_colors(3)
    assert len(palette) == 4 and palette[0] == svm.INTRUDE_COLOR
    assert palette[1] == 'E15759' and palette[3] == 'EDC948'
    assert svm.band_colors(1) == [svm.INTRUDE_COLOR, 'E15759']
    assert svm.band_colors(0) == [svm.INTRUDE_COLOR]


def test_band_of_edges():
    bands = [0.025, 0.05, 0.1]
    assert svm.band_of(-0.001, bands) == 0
    assert svm.band_of(0.0, bands) == 1
    assert svm.band_of(0.025, bands) == 1
    assert svm.band_of(0.0251, bands) == 2
    assert svm.band_of(0.1, bands) == 3
    assert svm.band_of(0.2, bands) is None
    assert svm.band_of(None, bands) is None


def test_summarize_keeps_closest_hit_per_element():
    hits = [('d1', 'Duct 1', 0.04), ('d2', 'Beam', -0.01), ('d1', 'Duct 1', 0.01),
            ('d3', 'Pipe', 0.3), ('d4', 'Alpha', 0.01)]
    summary = svm.summarize(hits, [0.025, 0.05, 0.1])
    assert [e['key'] for e in summary['elements']] == ['d2', 'd4', 'd1', 'd3']
    d1 = [e for e in summary['elements'] if e['key'] == 'd1'][0]
    assert d1['hits'] == 2 and d1['distance'] == 0.01 and d1['band'] == 1
    assert summary['counts'] == [1, 2, 0, 0]
    assert summary['beyond'] == 1


def test_suggestions_and_validation():
    models = [{'name': 'MEP.nwc', 'points': False}, {'name': 'scan.rcp', 'points': False},
              {'name': 'survey', 'points': True}]
    assert svm.scan_suggestions(models) == [1, 2]
    assert svm.validate_choice([], [0]) == 'Choose at least one scan model.'
    assert svm.validate_choice([1], [1, 0]) == 'A model cannot be both a scan and the design.'
    assert svm.validate_choice([1], [0]) is None


def test_definition_is_a_point_clearance_test():
    from namo import clashset_tests as defs
    design = defs.new_side([{'kind': 'model', 'name': 'MEP.nwc'}])
    d = svm.definition('Scan vs Model', ['scan.rcp'], design, [25.0, 50.0, 100.0], 'Millimeters')
    assert d['type'] == 'clearance'
    assert _compat.approx(d['tolerance_m'], 0.1)
    assert d['b']['primitives'] == ['points']
    assert d['b']['sources'] == [{'kind': 'model', 'name': 'scan.rcp'}]
    assert d['a']['primitives'] == ['triangles']


def test_collect_and_paint_through_fakes():
    doc, named = cf.new_doc()
    duct, wall = named['Duct'], named['Wall 1']
    duct.InstanceGuid = 'g-duct'
    wall.InstanceGuid = 'g-wall'
    duct_geo, wall_geo = named['Duct solid'], named['Wall 1 solid']
    results = [nav.ClashResult('C1', duct_geo, None, distance=0.03),
               nav.ClashResult('C2', wall_geo, None, distance=-0.002),
               nav.ClashResult('C3', duct_geo, None, distance=0.01)]
    test = cf.ClashTest('Scan vs Model', results)
    with cf.ClashNav(doc):
        hits, elements = svm.collect(test, doc)
        assert sorted(elements) == ['g-duct', 'g-wall']
        summary = svm.summarize(hits, [0.025, 0.05, 0.1])
        assert summary['counts'] == [1, 1, 0, 0]
        count = svm.paint(summary, elements, ghost=False, doc=doc)
        assert count == 2
        colours = [call for call in doc.Models.calls if call[0] == 'color']
        assert [c[1][0].DisplayName for c in colours] == ['Wall 1', 'Duct']
        assert doc.transactions[0] == 'Scan vs Model colours'


def test_build_and_run_refuses_a_scan_side_without_points():
    # Regression: when the points switch does not take, the test would silently compare
    # surfaces with surfaces and every band would be wrong.
    from namo import clashset_tests as defs
    doc, named = cf.new_doc()
    design = defs.new_side([{'kind': 'model', 'name': 'ARCH.nwc'}])
    d = svm.definition('Scan vs Model', ['MEP.nwc'], design, [0.025, 0.05], 'Meters')
    with cf.ClashNav(doc) as fake:
        live, outcome = svm.build_and_run(d, doc)
        assert outcome == 'created' and svm.points_only(live.SelectionB)
        assert ('run', 'Scan vs Model') in fake.data.calls
        assert not svm.points_only(live.SelectionA)

        class Deaf(cf.FakeClashData):
            def TestsAddCopy(self, test):
                test.SelectionB.PrimitiveTypes = cf.PrimitiveTypes.Triangles
                cf.FakeClashData.TestsAddCopy(self, test)

        doc.clash_tests[:] = []
        doc.clash_data = Deaf(doc)
    with cf.ClashNav(doc):
        error = _compat.raises(ValueError, svm.build_and_run, d, doc)
        assert 'Points' in str(error)
