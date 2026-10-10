# -*- coding: utf-8 -*-
"""namo.duplicates: the exact spatial-hash grouping, classification, refinement, wording,
and the object collection through the fake Navisworks layer."""
import datetime
import random
import time

import _compat
from _compat import approx

from namo import duplicates


def _box(x, y=0.0, z=0.0, size=1.0):
    return ((x, y, z), (x + size, y + size, z + size))


def test_union_find():
    uf = duplicates.UnionFind(5)
    uf.union(0, 1)
    uf.union(3, 4)
    uf.union(1, 4)
    assert uf.find(0) == uf.find(3) and uf.find(2) != uf.find(0)
    assert uf.size[uf.find(0)] == 4


def test_identical_boxes_group_and_keys_must_agree():
    entries = [('a', 'Solid', 12, _box(0), 0), ('b', 'Solid', 12, _box(0), 0),
               ('c', 'Solid', 12, _box(0), 1), ('d', 'Solid', 13, _box(0), 0),
               ('e', 'Wall', 12, _box(0), 0), ('f', 'Solid', 12, _box(5), 0),
               ('g', 'Solid', 12, None, 0)]
    groups = duplicates.group_duplicates(entries, 0.001)
    assert groups == [['a', 'b', 'c']]
    assert duplicates.group_duplicates([], 0.001) == []


def test_tolerance_is_per_coordinate():
    tol = 0.001
    base = ('a', 'Solid', 4, ((0.0, 0.0, 0.0), (1.0, 1.0, 1.0)), 0)
    within = ('b', 'Solid', 4, ((0.0009, 0.0, 0.0), (1.0009, 1.0, 1.0)), 0)
    outside = ('c', 'Solid', 4, ((0.0, 0.0, 0.0), (1.0, 1.0, 1.0011)), 0)
    assert duplicates.group_duplicates([base, within], tol) == [['a', 'b']]
    assert duplicates.group_duplicates([base, outside], tol) == []


def test_pairs_straddling_cell_boundaries_still_group():
    tol = 0.001
    cell = 4 * tol
    # centres either side of a cell boundary on one axis, then on all three at once
    for dx, dy, dz in ((1, 0, 0), (0, 1, 0), (0, 0, 1), (1, 1, 1)):
        k = 7
        half = 0.5
        c1 = [(k * cell - 0.0004) if d else 0.3 for d in (dx, dy, dz)]
        c2 = [(k * cell + 0.0004) if d else 0.3 for d in (dx, dy, dz)]
        b1 = (tuple(c - half for c in c1), tuple(c + half for c in c1))
        b2 = (tuple(c - half for c in c2), tuple(c + half for c in c2))
        groups = duplicates.group_duplicates([('p', 'Pipe', 8, b1, 0), ('q', 'Pipe', 8, b2, 0)], tol)
        assert groups == [['p', 'q']], (dx, dy, dz)
        # either insertion order
        groups = duplicates.group_duplicates([('q', 'Pipe', 8, b2, 0), ('p', 'Pipe', 8, b1, 0)], tol)
        assert groups == [['q', 'p']], (dx, dy, dz)


def test_negative_coordinates_and_chains():
    tol = 0.01
    entries = [('a', 'S', 1, _box(-100.0), 0), ('b', 'S', 1, _box(-100.008), 0),
               ('c', 'S', 1, _box(-100.016), 0), ('d', 'S', 1, _box(-50.0), 0)]
    # a~b and b~c are within tol, a~c is not: matches chain into one group
    assert duplicates.group_duplicates(entries, tol) == [['a', 'b', 'c']]


def test_groups_follow_first_seen_order():
    entries = [('x1', 'S', 1, _box(9), 0), ('y1', 'S', 1, _box(3), 0), ('y2', 'S', 1, _box(3), 0),
               ('x2', 'S', 1, _box(9), 0)]
    assert duplicates.group_duplicates(entries, 0.001) == [['x1', 'x2'], ['y1', 'y2']]


def test_classify_extras_and_refine():
    models = {'a': 0, 'b': 0, 'c': 1}
    assert duplicates.classify(['a', 'b'], models.get) == 'Same model'
    assert duplicates.classify(['a', 'c'], models.get) == 'Across models'
    assert duplicates.extras([['a', 'b', 'c'], ['d', 'e']]) == ['b', 'c', 'e']
    props = {'a': (1.0, (0, 0, 0)), 'b': (1.01, (0, 0, 0.0005)), 'c': (2.0, (0, 0, 0)),
             'd': (None, None), 'e': (5.0, (1, 1, 1)), 'f': (5.0, (9, 9, 9))}
    refined = duplicates.refine([['a', 'b', 'c', 'd'], ['e', 'f']], props, 0.001)
    assert refined == [['a', 'b', 'd']]


def test_summary_wording():
    level, message, detail = duplicates.summary([], 12345, '1 mm')
    assert level == 'info' and message == 'No duplicates found'
    assert detail == 'Checked 12,345 objects at 1 mm.'
    _l, _m, detail = duplicates.summary([], 200000, '1 mm', sampled=True)
    assert 'first 200,000' in detail and 'budget' in detail
    level, message, detail = duplicates.summary([['a', 'b'], ['c', 'd', 'e']], 1000, '1 mm')
    assert level == 'warning' and message == 'Found 3 duplicates in 2 groups'
    _l, message, _d = duplicates.summary([['a', 'b']], 10, '1 mm')
    assert message == 'Found 1 duplicate in 1 group'
    assert duplicates.tolerance_text(0.001) == '1 mm'
    assert duplicates.tolerance_text(0.0005) == '0.5 mm'
    assert duplicates.tolerance_text(0.025) == '2.5 cm'
    assert duplicates.tolerance_text(0.0254, imperial=True) == '1 in'
    assert duplicates.set_name(datetime.datetime(2026, 10, 5, 14, 30)) == 'Duplicates 2026-10-05 1430'


def test_speed_20000_entries():
    rng = random.Random(7)
    entries = []
    for i in range(18000):
        x, y, z = rng.uniform(-500, 500), rng.uniform(-500, 500), rng.uniform(0, 50)
        entries.append((i, rng.choice(['Duct', 'Pipe', 'Wall']), rng.randint(10, 400),
                        ((x, y, z), (x + 1, y + 0.5, z + 0.5)), rng.randint(0, 3)))
    for i in range(2000):
        source = entries[i]
        jitter = 0.0004
        box = tuple(tuple(v + jitter for v in corner) for corner in source[3])
        entries.append((18000 + i, source[1], source[2], box, 4))
    started = time.time()
    groups = duplicates.group_duplicates(entries, 0.001)
    spent = time.time() - started
    assert len(groups) == 2000
    assert all(len(g) == 2 and g[1] - g[0] == 18000 for g in groups)
    assert spent < (30.0 if _compat.IRONPYTHON else 5.0), spent


# ---- API half through the fake layer ------------------------------------------------------

import test_items as nav  # noqa: E402


class Item(nav.ModelItem):
    """A fake ModelItem with the members Duplicate Finder reads."""

    def __init__(self, name, children=(), geometry=False, box=None, prims=0, klass='Solid'):
        nav.ModelItem.__init__(self, name, children, geometry=geometry, box=box, klass=klass)
        self.prims = prims
        self.ClassName = 'Lc' + klass

    @property
    def Geometry(self):
        return nav._Ns(PrimitiveCount=self.prims)


def _element(name, x, prims=12, parts=1):
    leaves = [Item('%s part %d' % (name, p), geometry=True, box=_box(x), prims=prims)
              for p in range(parts)]
    element = Item(name, leaves, klass='Duct')
    for leaf in leaves:
        leaf.object = element
    return element


def _doc():
    a = _element('Duct A', 0.0, parts=2)
    b = _element('Duct B', 0.0, parts=2)
    c = _element('Duct C', 10.0)
    arch_root = Item('ARCH.nwc', [a, b, c])
    copy = _element('Duct A copy', 0.0, parts=2)
    mep_root = Item('MEP.nwc', [copy])
    arch = nav.Model(r'C:\X\ARCH.rvt', arch_root)
    mep = nav.Model(r'C:\X\MEP.rvt', mep_root)
    arch_root.Model, arch_root.HasModel = arch, True
    mep_root.Model, mep_root.HasModel = mep, True
    return nav.Document([arch, mep]), a, b, c, copy, arch_root, mep_root


def test_collect_sums_primitives_per_object_and_groups_across_models():
    doc, a, b, c, copy, arch_root, mep_root = _doc()
    with nav.FakeNav(doc):
        seen = []
        data = duplicates.collect([arch_root, mep_root], doc,
                                  progress=lambda f, label: seen.append(label))
    assert [o.DisplayName for o in data['objects']] == ['Duct A', 'Duct B', 'Duct C', 'Duct A copy']
    assert [e[2] for e in data['entries']] == [24, 24, 12, 24]
    assert [e[1] for e in data['entries']] == ['Duct', 'Duct', 'Duct', 'Duct']
    assert [e[4] for e in data['entries']] == [0, 0, 0, 1]
    assert data['leaves'] == 7 and not data['sampled'] and seen
    groups = duplicates.group_duplicates(data['entries'], 0.001)
    assert groups == [[0, 1, 3]]
    model_of = dict((e[0], e[4]) for e in data['entries'])
    assert duplicates.classify(groups[0], model_of.get) == 'Across models'


def test_collect_overlapping_roots_and_budget():
    doc, a, b, c, copy, arch_root, mep_root = _doc()
    with nav.FakeNav(doc):
        data = duplicates.collect([arch_root, a], doc)
        assert data['leaves'] == 5 and len(data['objects']) == 3
        capped = duplicates.collect([arch_root], doc, budget=2)
        assert capped['sampled'] and len(capped['objects']) == 2


# ---- refit: the tolerance in feet documents and far from the origin ----------------------


def test_default_tolerance_is_never_zero_in_a_feet_document():
    from namo import units
    # 1 mm in feet used to prefill the box as 0' 0", which the form then refused
    feet = duplicates.default_tolerance(0.001, 'Feet')
    assert approx(feet, 1.0 / 16.0 / 12.0)
    shown = units.format_length_input(feet, 'Feet')
    assert shown == "0' 0 1/16" + '"'
    assert approx(units.parse_length(shown, 'Feet'), feet)
    assert approx(duplicates.default_tolerance(0.001, 'Inches'), 1.0 / 16.0)
    assert approx(duplicates.default_tolerance(0.0254, 'Feet'), 1.0 / 12.0)      # 1 in stays 1 in
    assert approx(duplicates.default_tolerance(0.001, 'Millimeters'), 1.0)
    assert approx(duplicates.default_tolerance(0.001, 'Meters'), 0.001)
    # left alone, the saved tolerance does not drift to 1/16 in
    assert duplicates.kept_tolerance_m(feet, feet, 0.001, 'Feet') == 0.001
    assert approx(duplicates.kept_tolerance_m(0.25 / 12.0, feet, 0.001, 'Feet'), 0.00635)


def test_tolerance_text_fractions():
    assert duplicates.tolerance_text(0.0015875, imperial=True) == '1/16 in'
    assert duplicates.tolerance_text(0.0381, imperial=True) == '1 1/2 in'
    assert duplicates.tolerance_text(0.001, imperial=True) == '0.0394 in'


def _far_box(dx):
    far = 1370000.0
    return ((far + dx, far, 100.0), (far + dx + 2.0, far + 1.0, 101.0))


def test_grouping_far_from_the_origin():
    tol = 1.0 / 16.0 / 12.0                     # 1/16 in, in feet
    entries = [('a', 'Duct', 12, _far_box(0.0), 0), ('b', 'Duct', 12, _far_box(0.0), 1),
               ('c', 'Duct', 12, _far_box(tol * 0.9), 0), ('d', 'Duct', 12, _far_box(tol * 3.0), 0),
               ('e', 'Duct', 12, _far_box(0.5), 0)]
    assert duplicates.group_duplicates(entries, tol) == [['a', 'b', 'c']]
    precision = duplicates.box_precision(entries)
    assert precision['reach'] > 1370000.0 and not precision['single']
    assert precision['noise'] < 1e-6
    assert duplicates.effective_tolerance(tol, precision) == (tol, False)
    # a nonsense tolerance (smaller than a double can tell apart out there) still groups
    # the identical boxes and nothing else
    assert duplicates.group_duplicates(entries, 1e-15) == [['a', 'b']]


def _f32(value):
    import struct
    return struct.unpack('f', struct.pack('f', value))[0]


def test_single_precision_boxes_widen_the_tolerance():
    far = 1370000.0
    entries = []
    for i in range(40):
        x, y, z = _f32(far + i * 3.3), _f32(far + i * 1.7), _f32(10.1 + i)
        entries.append((i, 'Pipe', 8, ((x, y, z), (_f32(x + 2.2), _f32(y + 0.7), _f32(z + 0.7))), 0))
    precision = duplicates.box_precision(entries)
    assert precision['single']
    assert 0.2 < precision['noise'] < 0.5       # two float32 steps at 1.37 million ft
    tol, widened = duplicates.effective_tolerance(1.0 / 192.0, precision)
    assert widened and tol == precision['noise']
    # whole-number boxes near the origin prove nothing and are not called single
    tidy = [(i, 'Wall', 4, ((float(i), 0.0, 0.0), (float(i + 1), 1.0, 3.0)), 0) for i in range(40)]
    assert not duplicates.box_precision(tidy)['single']
    assert duplicates.box_precision([])['noise'] > 0.0


def test_weld_tolerance_follows_noise_and_size():
    tri = [((0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (0.0, 10.0, 0.0))]
    assert approx(duplicates.weld_tolerance(tri, 0.0), 1e-6)
    assert approx(duplicates.weld_tolerance(tri, 0.001), 0.004)
    assert duplicates.weld_tolerance([], 0.0) == 0.0
