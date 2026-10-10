# -*- coding: utf-8 -*-
"""namo.hud: the HUD lines and collect() through the fake layer."""
import test_items as nav
import test_propindex as pf

from namo import hud, propindex


def test_lines_for_nothing_selected():
    assert hud.stats_lines({'count': 0}) == [('Nothing selected', True)]


def test_lines_full_and_partial():
    stats = {'count': 1204, 'read': 1204, 'objects': 312, 'models': ['MEP.rvt', 'ARCH.rvt'],
             'categories': {'Ducts': 120, 'Pipes': 80, 'Walls': 12, 'Doors': 3},
             'sum': {'label': 'Length', 'total': 124.5, 'unit': 'm', 'present': 300}}
    lines = hud.stats_lines(stats)
    assert lines[0] == ('1,204 items selected (312 objects)', False)
    assert lines[1] == ('ARCH.rvt, MEP.rvt', True)
    assert lines[2] == ('Ducts 120, Pipes 80, Walls 12', True)
    assert lines[3] == ('Length: 124.5 m on 300 of 1,204', False)
    partial = dict(stats, read=5000, count=12000, sum=None)
    lines = hud.stats_lines(partial)
    assert lines[0][0] == '12,000 items selected (312+ objects)'
    assert lines[-1] == ('Details from the first 5,000 items', True)
    one = hud.stats_lines({'count': 1, 'read': 1, 'objects': 1})
    assert one[0][0] == '1 item selected (1 object)'


def test_helpers():
    assert hud.models_text(['C.nwc', 'a.nwc', 'B.nwc', 'D.nwc', 'a.nwc'], 3) == 'a.nwc, B.nwc, C.nwc and 1 more'
    assert hud.models_text(['', None]) == ''
    assert hud.top_counts({'b': 2, 'a': 2, 'c': 5}, 2) == [('c', 5), ('a', 2)]
    assert hud.sum_text('Area', 0, 'm2', 3, 0) == 'Area: not on the selection'
    assert hud.sum_text('Count', 3.0, None, 3, 3) == 'Count: 3'


def test_collect_through_fakes():
    doc, n = pf.tree()
    with pf.Fake(doc, 'Meters'):
        selection = nav.ModelItemCollection([n['Wall 1 solid'], n['Wall 1'], n['Wall 2'], n['Duct solid']])
        doc.CurrentSelection.SelectedItems = selection
        reader = propindex.Reader(doc, report_units='auto')
        stats = hud.collect(doc, reader, ('Element', 'Length'))
        assert stats['count'] == 4 and stats['read'] == 4
        assert stats['objects'] == 3
        assert stats['models'] == ['ARCH.rvt', 'MEP.rvt']
        assert stats['categories'] == {'Walls': 2, 'Ducts': 1}
        assert stats['sum']['present'] == 3 and abs(stats['sum']['total'] - 6.5) < 1e-9
        assert stats['sum']['unit'] == 'm'
        lines = hud.stats_lines(stats)
        assert lines[0][0] == '4 items selected (3 objects)'
        capped = hud.collect(doc, reader, None, budget=2)
        assert capped['read'] == 2 and capped['sum'] is None
        doc.CurrentSelection.SelectedItems = nav.ModelItemCollection()
        assert hud.collect(doc, reader)['count'] == 0
