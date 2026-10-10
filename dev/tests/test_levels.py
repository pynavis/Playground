# -*- coding: utf-8 -*-
"""namo.levels: level lists, elevation estimates, stepping, cut planes, framing, and
the API half (grid levels, IFC storeys, Level properties, sectioning) on the fake."""
import _compat
from _compat import approx

import test_items as nav
import test_vp_common as vpfake
from namo import levels, paths, session


def lv(name, z, source='grid', approximate=False):
    return levels.level(name, z, source, approximate)


LEVELS = [lv('Level 1', 0.0), lv('Level 2', 4.0), lv('Level 3', 8.0), lv('Roof', 12.5)]


# ---- pure -------------------------------------------------------------------------------


def test_settings_values_are_made_safe():
    out = levels.settings_values({'cut_height_m': '1.5', 'slab_depth_m': -0.4, 'slab': 1, 'plan': None, 'x': 1})
    assert out == {'cut_height_m': 1.5, 'slab': True, 'slab_depth_m': 0.4, 'plan': False}
    assert levels.settings_values({'cut_height_m': 'abc'})['cut_height_m'] == 1.2
    assert levels.settings_values(None) == levels.DEFAULTS


def test_settings_fields_require_a_cut_height():
    """Regression: a blank cut height reached config.py as None (TypeError on * m)."""
    from namo import ui
    fields = ui.normalize_fields(levels.settings_fields(levels.settings_values(None), 'Millimeters'))
    raws = {'cut': '', 'slab': True, 'depth': '500', 'plan': False}
    _values, errors = ui.collect(fields, raws, units='Millimeters')
    assert 'cut' in errors
    raws['cut'] = '1200'
    values, errors = ui.collect(fields, raws, units='Millimeters')
    assert not errors and approx(values['cut'], 1200.0) and approx(values['depth'], 500.0)
    assert approx([f['default'] for f in fields if f['key'] == 'cut'][0], 1200.0)


def test_normalize_sorts_dedupes_and_drops_bad():
    raw = [lv('Level 10', 30.0), lv('Level 2', 4.0), lv('level 2', 9.0),
           {'name': 'Bad', 'elevation': float('nan')}, {'name': 'None'}]
    out = levels.normalize(raw)
    assert [x['name'] for x in out] == ['Level 2', 'Level 10']


def test_estimate_elevation_takes_the_common_bottom():
    bottoms = [3.98, 4.0, 4.0, 4.01, 4.0, 3.7, 3.7, 12.0, -1.0]
    assert approx(levels.estimate_elevation(bottoms, 0.05), 4.0)
    assert levels.estimate_elevation([], 0.05) is None
    assert levels.estimate_elevation([None, 2.0], 0.05) == 2.0
    # a tie between two bins goes to the lower one
    assert levels.estimate_elevation([1.0, 1.0, 5.0, 5.0], 0.05) == 1.0


def test_index_at_and_of():
    assert levels.index_at(LEVELS, 5.0) == 1
    assert levels.index_at(LEVELS, -3.0) == 0
    assert levels.index_at(LEVELS, 100.0) == 3
    assert levels.index_at(LEVELS, 3.99) == 0
    assert levels.index_at(LEVELS, 3.9999999) == 1          # float noise counts as on the level
    assert levels.index_at([], 1.0) is None
    assert levels.index_of(LEVELS, 'Roof') == 3
    assert levels.index_of(LEVELS, ' level 2 ') == 1
    assert levels.index_of(LEVELS, 'Basement') is None


def test_step_index():
    assert levels.step_index(LEVELS, 1, 1) == (2, True)
    assert levels.step_index(LEVELS, 3, 1) == (3, False)
    assert levels.step_index(LEVELS, 0, -1) == (0, False)
    assert levels.step_index(LEVELS, None, 1) == (0, True)
    assert levels.step_index(LEVELS, None, -1) == (3, True)
    assert levels.step_index([], 0, 1) == (None, False)


def test_cut_planes():
    top = levels.cut_planes(4.0, 1.2)
    assert top == [((0.0, 0.0, 5.2), (0.0, 0.0, -1.0))]
    both = levels.cut_planes(4.0, 1.2, slab=True, slab_depth=0.5, center=(3, 4))
    assert both == [((3.0, 4.0, 5.2), (0.0, 0.0, -1.0)), ((3.0, 4.0, 3.5), (0.0, 0.0, 1.0))]


def test_plan_camera_looks_down_north_up():
    cam = levels.plan_camera(((0, 0, 0), (40, 20, 9)), 4.0, 5.2, aspect=2.0)
    assert cam['projection'] == 'ortho'
    assert approx(cam['direction'], (0.0, 0.0, -1.0)) and approx(cam['up'], (0.0, 1.0, 0.0))
    assert approx(cam['position'][:2], (20.0, 10.0)) and cam['position'][2] > 9.0
    assert approx(cam['height_field'], 21.6)


def test_describe_and_source_note():
    assert levels.describe(lv('L2', 4.2), 'Meters') == 'L2 at 4.200 m'
    assert levels.describe(lv('L2', 4.2, 'property', True), 'Meters') == 'L2 at 4.200 m (approximate)'
    assert 'grid' in levels.source_note(LEVELS)
    assert 'IFC' in levels.source_note([lv('S', 0, 'storey', True)])
    assert 'Level property' in levels.source_note([lv('S', 0, 'property', True)])
    assert levels.source_note([]) == ''


class Box(object):
    def __init__(self, name, box, children=()):
        self.name, self.box, self.kids = name, box, list(children)


def test_band_boxes_split_crossing_nodes_only():
    l1 = Box('L1', ((0, 0, -0.3), (30, 10, 3.9)))
    l2 = Box('L2', ((5, 2, 3.7), (15, 8, 7.9)))
    tall = Box('Stair', ((40, 0, 0), (45, 5, 8)))
    root = Box('root', ((0, 0, -0.3), (45, 10, 7.9)), [l1, l2, tall])
    boxes, sampled = levels.band_boxes([root], lambda n: n.kids, lambda n: n.box,
                                       [lv('L1', 0.0), lv('L2', 4.0)], top_extra=4.0)
    assert not sampled
    assert boxes[0] == ((0, 0, 0.0), (45, 10, 4.0))
    assert boxes[1] == ((5, 0, 4.0), (45, 8, 8.0))


def test_band_boxes_budget_and_empty_levels():
    nodes = [Box('n%d' % i, ((i, 0, 0), (i + 1, 1, 10))) for i in range(10)]
    root = Box('root', ((0, 0, 0), (10, 1, 10)), nodes)
    boxes, sampled = levels.band_boxes([root], lambda n: n.kids, lambda n: n.box,
                                       [lv('A', 0.0), lv('B', 5.0), lv('C', 50.0)], 4.0, budget=1)
    assert sampled
    assert boxes[2] is None
    assert levels.band_boxes([root], lambda n: n.kids, lambda n: n.box, [], 4.0) == ([], False)


# ---- API half on the fake --------------------------------------------------------------------


class _Ns(object):
    def __init__(self, **kw):
        self.__dict__.update(kw)


def _grid_doc():
    doc = vpfake.make_doc()
    grid_levels = [_Ns(DisplayName='Level 2', Elevation=4.0), _Ns(DisplayName='Level 1', Elevation=0.0)]
    system = _Ns(Levels=grid_levels)
    doc.Grids = _Ns(ActiveSystem=system, Systems=[system])
    return doc


def _level_model():
    """Objects on Level 1 (bottom 0.0, one slab at -0.3) and Level 2 (bottom 4.0)."""
    def obj(name, level, z0, z1):
        geo = nav.ModelItem(name + ' solid', geometry=True, box=((0, 0, z0), (1, 1, z1)))
        element = nav.ModelItem(name, [geo], props={('Element', 'Level'): level})
        geo.object = element
        return element
    first = nav.ModelItem('Level 1', [obj('Wall A', 'Level 1', 0.0, 3.0), obj('Wall B', 'Level 1', 0.0, 3.0),
                                      obj('Slab', 'Level 1', -0.3, 0.0)])
    second = nav.ModelItem('Level 2', [obj('Wall C', 'Level 2', 4.0, 7.0), obj('Door', 'Level 2', 4.0, 6.1)])
    root = nav.ModelItem('ARCH.nwc', [first, second])
    model = nav.Model(r'C:\M\ARCH.rvt', root)
    root.Model, root.HasModel = model, True
    return vpfake.make_doc([model])


def test_grid_levels_sorted():
    doc = _grid_doc()
    with nav.FakeNav(doc):
        found = levels.grid_levels(doc)
    assert [x['name'] for x in found] == ['Level 1', 'Level 2'] and not found[0]['approximate']


def test_property_levels_estimate_from_object_bottoms():
    session.clear('levels')
    doc = _level_model()
    with nav.FakeNav(doc):
        found, sampled = levels.property_levels(doc)
        assert levels.grid_levels(doc) == []
        assert levels.storey_levels(doc) == []
        again = levels.find(doc)
        cached = levels.cached_or_none(doc)
    assert not sampled
    assert [(x['name'], x['elevation'], x['approximate']) for x in found] == [('Level 1', 0.0, True),
                                                                             ('Level 2', 4.0, True)]
    assert again == found and cached == found
    session.clear('levels')


def test_storey_levels_from_ifc_tree():
    session.clear('levels')
    geo = nav.ModelItem('Slab', geometry=True, box=((0, 0, 3.0), (5, 5, 3.2)))
    storey = nav.ModelItem('Level 02', [geo], klass='IfcBuildingStorey')
    building = nav.ModelItem('Building', [storey], klass='IfcBuilding')
    root = nav.ModelItem('model.ifc', [building])
    model = nav.Model(r'C:\M\model.ifc', root)
    root.Model, root.HasModel = model, True
    doc = vpfake.make_doc([model])
    with nav.FakeNav(doc):
        found = levels.find(doc, use_cache=False)
    assert [(x['name'], x['source']) for x in found] == [('Level 02', 'storey')]
    assert approx(found[0]['elevation'], 3.0)
    session.clear('levels')


def test_apply_step_and_remember():
    folder = _compat.tmpdir('levels_store')
    previous = paths.redirect(folder)
    session.clear('levels')
    try:
        doc = _grid_doc()
        with nav.FakeNav(doc) as fake:
            vpfake.extend(fake.Api)
            found = levels.find(doc)
            cfg = levels.settings_values({'cut_height_m': 1.0, 'slab': True, 'slab_depth_m': 0.5, 'plan': True})
            levels.apply(found[0], doc, cfg)
            written = doc.CurrentViewpoint.writes[-1]
            planes = written.ClipPlanes.planes
            assert planes[0].Origin.t()[2] == 1.0 and planes[1].Origin.t()[2] == -0.5
            assert written.ClipPlanes.Enabled and written.zoomed is not None
            assert levels.remembered(doc) == 'Level 1'
            assert levels.current_index(found, doc, cfg) == 0
            level, message, detail = levels.step(1, doc)
            assert (level, message) == ('info', 'Level 2') and 'Cut at 5.200 m' in detail
            level, message, _d = levels.step(1, doc)
            assert message == 'Already at the top level'
            level, message, _d = levels.step(-1, doc)
            assert message == 'Level 1'
            assert len(doc.CurrentViewpoint.writes) == 3
    finally:
        session.clear('levels')
        paths.redirect(previous)


def test_current_index_from_the_section_when_nothing_is_remembered():
    folder = _compat.tmpdir('levels_current')
    previous = paths.redirect(folder)
    session.clear('levels')
    try:
        doc = _grid_doc()
        with nav.FakeNav(doc) as fake:
            api = vpfake.extend(fake.Api)
            vp = doc.CurrentViewpoint.vp
            vp.ClipPlanes.Enabled = True
            vp.ClipPlanes.Mode = api.ClipPlaneSetMode.Planes
            vp.ClipPlanes.planes[0].Origin = nav.Point3D(0, 0, 5.2)
            vp.ClipPlanes.planes[0].Normal = nav.UnitVector3D(0, 0, -1)
            vp.ClipPlanes.planes[0].Enabled = True
            found = levels.find(doc)
            assert levels.current_index(found, doc) == 1
            vp.ClipPlanes.Enabled = False
            vp.Position = nav.Point3D(0, 0, 1.6)
            assert levels.current_index(found, doc) == 0
    finally:
        session.clear('levels')
        paths.redirect(previous)


def test_no_levels_message():
    doc = vpfake.make_doc()
    session.clear('levels')
    with nav.FakeNav(doc):
        level, message, _detail = levels.step(1, doc)
    assert (level, message) == ('info', 'No levels found')
    session.clear('levels')


def test_pick_current_follows_the_plane_once_it_was_moved():
    # Regression: the remembered level always won, so after the cut was moved with
    # Section Nudge (or by hand) Level Up stepped from where the plane used to be.
    found = [levels.level('L1', 0.0), levels.level('L2', 4.0), levels.level('L3', 8.0)]
    cut = 1.2
    assert levels.pick_current(found, 'L2', 5.2, cut, None) == 1           # still where L2 put it
    assert levels.pick_current(found, 'L2', 9.2, cut, None) == 2           # nudged up to L3
    assert levels.pick_current(found, 'L2', 9.25, cut, None) == 2          # a little off: still L3
    assert levels.pick_current(found, 'L3', 1.0, cut, None) == 0           # dragged down low
    assert levels.pick_current(found, None, 5.2, cut, None) == 1
    assert levels.pick_current(found, 'L2', None, cut, 100.0) == 1         # no plane: remembered
    assert levels.pick_current(found, 'gone', None, cut, 4.5) == 1         # else under the eye
    assert levels.pick_current(found, None, None, cut, None) is None
    assert levels.pick_current([], 'L2', 5.2, cut, 1.0) is None
    assert levels.pick_current(found, None, 4.0, 0.0, None) == 1           # a cut of zero
