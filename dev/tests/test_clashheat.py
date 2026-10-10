# -*- coding: utf-8 -*-
"""namo.clashheat: counting, geometric bands, legend, ranking, binning and markers, and
collect/paint/markers/clear through the fakes with a fake overlay."""
import sys
import types

import _compat
import test_clashset_tests as cf

from namo import clashheat as ch
from namo import clashname as cn
from namo import paths, session


def test_count_elements_sides_and_self():
    rows = [{'item_a': 'a', 'item_b': 'b'}, {'item_a': 'a', 'item_b': 'c'},
            {'item_a': 'd', 'item_b': 'd'}, {'item_a': '', 'item_b': 'b'}]
    assert ch.count_elements(rows) == {'a': 2, 'b': 2, 'c': 1, 'd': 1}
    assert ch.count_elements(rows, 'a') == {'a': 2, 'd': 1}
    assert ch.count_elements(rows, 'b') == {'b': 2, 'c': 1, 'd': 1}


def test_band_lows_labels_and_index():
    assert ch.band_lows(100) == [1, 3, 6, 16, 40]
    assert ch.band_labels([1, 3, 6, 16, 40], 100) == ['1 to 2', '3 to 5', '6 to 15', '16 to 39',
                                                      '40 to 100']
    assert ch.band_lows(6) == [1, 2, 3, 4]
    assert ch.band_labels([1, 2, 3, 4], 6) == ['1', '2', '3', '4 to 6']
    assert ch.band_lows(3) == [1, 2, 3]
    assert ch.band_lows(0) == []
    assert ch.band_index(5, [1, 3, 6]) == 1
    assert ch.band_index(100, [1, 3, 6]) == 2
    assert ch.band_index(0, [1, 3, 6]) is None


def test_legend_and_ranked():
    counts = {'a': 1, 'b': 1, 'c': 12, 'd': 3}
    rows = ch.legend(counts)
    assert [r['label'] for r in rows] == ['1', '2', '3', '4 to 6', '7 to 12']
    assert [r['elements'] for r in rows] == [2, 0, 1, 0, 1]
    assert rows[-1]['hex'] == ch.band_colors(5)[-1]
    assert ch.ranked(counts, {'a': 'Zed', 'b': 'Alpha'}, limit=3) == [('c', 12), ('d', 3), ('b', 1)]
    assert ch.legend({}) == []


def test_bin_centres_and_markers():
    points = [(0.5, 0.5, 0.5), (1.5, 0.2, 0.1), (2.5, 0.1, 0.1), (-0.5, 0, 0), None]
    cells = ch.bin_centres(points, 2.0)
    assert cells[0] == {'cell': (0, 0, 0), 'count': 2, 'center': (1.0, 0.35, 0.3)}
    assert [c['cell'] for c in cells[1:]] == [(-1, 0, 0), (1, 0, 0)]
    segments, label = ch.marker_segments((0, 0, 0), 2, 2, 2.0)
    assert segments[0] == ((-1.0, 0, 0), (1.0, 0, 0), False)
    assert label == (0, 0, 1.0)
    small, _label = ch.marker_segments((0, 0, 0), 1, 4, 2.0)
    assert _compat.approx(small[2][1][2], 2.0 * (0.15 + 0.35 * 0.25))
    assert ch.tags_for(2) == ['playground-heat:1', 'playground-heat:2']
    assert ch.summary_text(1, 1, 0) == 'Coloured 1 element in 1 band'
    assert ch.summary_text(412, 5, 9) == 'Coloured 412 elements in 5 bands, 9 markers'


def _fake_overlay():
    module = types.ModuleType('pynavis.overlay')
    module.items = {}
    module.redraws = []
    module.add = lambda tag, segments, label=None, label_at=None, anchor=None: \
        module.items.__setitem__(tag, (segments, label)) or True
    module.clear = lambda tag=None: module.items.pop(tag, None) is not None or True
    module.redraw = lambda: module.redraws.append(1) or True
    return module


def test_collect_paint_markers_and_clear_through_fakes():
    folder = _compat.tmpdir('clashheat')
    previous = paths.redirect(folder)
    saved = sys.modules.get('pynavis.overlay')
    session.clear(ch.HOLDER)
    try:
        doc, test = cf.clash_doc()
        with cf.ClashNav(doc):
            overlay = _fake_overlay()
            sys.modules['pynavis.overlay'] = overlay
            sys.modules['pynavis'].overlay = overlay
            entry = cn.read_test(test, doc)
            counts, elements, names, centres = ch.collect([entry], ['New'])
            assert sorted(counts.values()) == [3, 3]
            assert len(centres) == 3
            coloured = ch.paint(counts, elements, ghost=True, doc=doc)
            assert coloured == 2
            assert doc.transactions[0] == 'Clash heatmap'
            calls = [c[0] for c in doc.Models.calls]
            assert calls == ['color', 'transparency']
            drawn, ok = ch.draw_markers(centres, 2.0)
            assert ok and drawn == 2 and sorted(overlay.items) == ['playground-heat:1', 'playground-heat:2']
            markers, reset = ch.clear(doc)
            assert markers == 2 and overlay.items == {}
            assert reset > 0 and doc.Models.calls[-1][0] == 'reset'
            assert ch.clear(doc) == (0, 0)
            # painted in one model, cleared after another was opened: no reset of stale items
            ch.paint(counts, elements, ghost=False, doc=doc)
            doc.Title = 'Another model.nwf'
            before = len(doc.Models.calls)
            assert ch.clear(doc) == (0, 0)
            assert len(doc.Models.calls) == before
            assert ch.holder().painted == []
    finally:
        paths.redirect(previous)
        session.clear(ch.HOLDER)
        if saved is None:
            sys.modules.pop('pynavis.overlay', None)
        else:
            sys.modules['pynavis.overlay'] = saved


def test_only_the_densest_cells_are_drawn():
    # Regression: every cell became an overlay item; a big test drew thousands of
    # crosses and labels on every frame.
    centres = []
    for i in range(ch.MAX_MARKERS + 40):
        centres.extend([(i * 10.0 + 1.0, 1.0, 1.0)] * (1 + i % 3))
    cells = ch.bin_centres(centres, 2.0)
    assert len(cells) == ch.MAX_MARKERS + 40
    kept = ch.densest(cells)
    assert len(kept) == ch.MAX_MARKERS
    assert min(c['count'] for c in kept) >= max(c['count'] for c in cells[ch.MAX_MARKERS:])
    assert ch.densest(cells, 0) == []
