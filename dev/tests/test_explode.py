# -*- coding: utf-8 -*-
"""namo.explode: options, offsets per mode, nesting, tolerance, records, the collapse
plan, and explode/collapse through the fake Navisworks layer."""
import datetime
import sys
import types

import _compat

from namo import explode

import test_colorize
import test_items as nav


def test_normalize_options_and_fields():
    assert explode.normalize_options(None) == {'factor': 1.5, 'mode': 'radial', 'units': 'items'}
    opts = explode.normalize_options({'factor': '50', 'mode': 'diagonal', 'units': 'models'})
    assert opts == {'factor': explode.MAX_FACTOR, 'mode': 'radial', 'units': 'models'}
    assert explode.normalize_options({'factor': 0.2})['factor'] == explode.MIN_FACTOR
    fields = explode.option_fields({'mode': 'vertical'}, models_count=2)
    assert fields[1]['default'] == 'vertical'
    assert fields[2]['options'][1] == ('Their whole models (2 models)', 'models')


def test_offsets_per_mode():
    centers = [(10.0, 0.0, 4.0), (-2.0, 6.0, 0.0), None]
    origin = (0.0, 0.0, 2.0)
    assert explode.offsets(centers, origin, 1.5) == [(5.0, 0.0, 1.0), (-1.0, 3.0, -1.0), (0.0, 0.0, 0.0)]
    assert explode.offsets(centers, origin, 2.0, 'vertical') == [(0.0, 0.0, 2.0), (0.0, 0.0, -2.0), (0.0, 0.0, 0.0)]
    assert explode.offsets(centers, origin, 2.0, 'x')[0] == (10.0, 0.0, 0.0)
    assert explode.offsets(centers, origin, 2.0, 'y')[1] == (0.0, 6.0, 0.0)


def test_union_center_and_vectors():
    assert explode.union_center([((0, 0, 0), (2, 2, 2)), None, ((4, -2, 0), (6, 0, 1))]) == (3.0, 0.0, 1.0)
    assert explode.union_center([]) is None
    assert explode.box_center(((0, 0, 0), (2, 4, 6))) == (1.0, 2.0, 3.0)
    assert explode.add((1, 2, 3), (1, 1, 1)) == (2.0, 3.0, 4.0)
    assert explode.negate((1, -2, 0)) == (-1.0, 2.0, -0.0)
    assert explode.is_zero((0.0, 1e-15, 0.0)) and not explode.is_zero((0.0, 0.001, 0.0))


def test_drop_nested():
    parent = {'b': 'a', 'c': 'b', 'd': None, 'a': None}
    assert explode.drop_nested(['c', 'a', 'd'], parent.get) == ['a', 'd']
    assert explode.drop_nested(['c', 'd'], parent.get) == ['c', 'd']


def test_tolerance_scales_with_coordinates():
    near = explode.tolerance([(0.0, 0.0, 0.0), (1.0, 1.0, 1.0)])
    far = explode.tolerance([(1.0e6, 0.0, 0.0), (1.0e6 + 1, 0.0, 0.0)])
    assert 1e-6 <= near < 1e-5
    assert 0.1 < far < 0.2          # one float32 step at a million units, not a wide guess
    field = explode.tolerance([(1.37e6, 2.0e5, 30.0)])
    assert 0.1 < field < 0.2        # the owner's model: a half foot move must still register
    assert explode.tolerance([]) == 1e-6


def test_records_merge_and_collapse_plan():
    now = datetime.datetime(2026, 10, 5, 10, 0, 0)
    opts = explode.normalize_options({})
    record = explode.make_record([{'m': 'a'}, {'m': 'b'}], [(1.0, 0.0, 0.0), (0.0, 0.0, 0.0)],
                                 [(11.0, 0.0, 0.0), (5.0, 5.0, 5.0)], opts, now)
    assert record['items'][0] == {'entry': {'m': 'a'}, 'offset': [1.0, 0.0, 0.0], 'center': [11.0, 0.0, 0.0]}
    assert explode.valid_record(record) and not explode.valid_record({'items': []})
    assert explode.describe(record) == '2 objects, spread 1.5x'
    more = explode.merge_record(record, [(1.0, 0.0, 0.0), (0.0, 2.0, 0.0)],
                                [(12.0, 0.0, 0.0), (5.0, 7.0, 5.0)], 2.0, now)
    assert more['items'][0]['offset'] == [2.0, 0.0, 0.0] and more['factor'] == 3.0
    assert more['items'][1]['center'] == [5.0, 7.0, 5.0]
    plan, moved = explode.collapse_plan(more['items'], [(12.0, 0.0, 0.0), (5.0, 7.0, 5.0)])
    assert plan == [(0, (-2.0, -0.0, -0.0)), (1, (-0.0, -2.0, -0.0))] and moved == 0
    plan, moved = explode.collapse_plan(more['items'], [(13.0, 0.0, 0.0), None])
    assert plan == [] and moved == 1


def test_drift_rebase_stale_and_tracking():
    rows = [{'offset': [1.0, 0.0, 0.0], 'center': [11.0, 0.0, 0.0]},
            {'offset': [0.0, 2.0, 0.0], 'center': [0.0, 7.0, 0.0]}]
    assert explode.drifted(rows, [(11.0, 0.0, 0.0), (0.0, 5.0, 0.0)]) == [False, True]
    assert explode.drifted(rows, [None, (0.0, 7.0, 0.0)]) == [False, False]
    record = {'items': rows, 'factor': 1.5}
    rebased = explode.rebase(record, [False, True])
    assert rebased['items'][1]['offset'] == [0.0, 0.0, 0.0] and rows[1]['offset'] == [0.0, 2.0, 0.0]
    assert explode.is_stale(rows, [(10.0, 0.0, 0.0), (0.0, 5.0, 0.0)])
    assert not explode.is_stale(rows, [(11.0, 0.0, 0.0), None])
    assert explode.is_stale(rows, [None, None])
    assert not explode.is_stale(rows, [(10.0, 0.0, 0.0), None], tracks=False)
    plan, moved = explode.collapse_plan(rows, [(10.0, 0.0, 0.0), (0.0, 5.0, 0.0)], tracks=False)
    assert len(plan) == 2 and moved == 0
    before = [(0.0, 0.0, 0.0), (5.0, 5.0, 5.0)]
    moves = [(1.0, 0.0, 0.0), (0.0, 0.0, 0.0)]
    assert explode.tracks_moves(before, [(1.0, 0.0, 0.0), (5.0, 5.0, 5.0)], moves) is True
    assert explode.tracks_moves(before, before, moves) is False
    assert explode.tracks_moves(before, before, [(0.0, 0.0, 0.0)] * 2) is None


def test_api_explode_and_collapse_one_step_each():
    doc, n = nav.model_tree()
    moves = []

    class Transform(object):
        def __init__(self, v):
            self.v = v

    def override(coll, transform, update):
        moves.append(([i.DisplayName for i in coll], (transform.v.X, transform.v.Y, transform.v.Z), update))
    doc.Models.OverridePermanentTransform = override
    with test_colorize.fake(doc) as layer:
        layer.Api.Transform3D = nav._Ns(CreateTranslation=lambda v: Transform(v))
        memory = sys.modules.get('pynavis.memory')
        fake_memory = types.ModuleType('pynavis.memory')
        fake_memory.encode_items = lambda its, d=None: [{'name': i.DisplayName} for i in its]
        fake_memory.resolve_entries = lambda entries, d=None: (
            [n[e['name']] for e in entries if e['name'] in n], 0, [])
        sys.modules['pynavis.memory'] = fake_memory
        sys.modules['pynavis'].memory = fake_memory
        try:
            nodes = explode.units_of([n['Wall 1'], n['Wall 1 solid'], n['Duct']], 'items')
            assert [x.DisplayName for x in nodes] == ['Wall 1', 'Duct']
            roots = explode.units_of([n['Wall 1'], n['Wall 2'], n['Duct']], 'models')
            assert [x.DisplayName for x in roots] == ['ARCH.nwc', 'MEP.nwc']
            moved, record = explode.explode(nodes, explode.normalize_options({'factor': 2.0}))
            assert moved == 2 and doc.transactions == ['Exploded view']
            assert moves[0][0] == ['Wall 1'] and moves[0][2] is False
            assert [r['entry']['name'] for r in record['items']] == ['Wall 1', 'Duct']
            # the fake does not move boxes: the centres did not follow, so an inverse
            # move cannot be trusted (an undo would go unseen) and Collapse resets
            assert record['tracks'] is False and explode.collapse_route(record) == 'reset'
            resets = []
            doc.Models.ResetPermanentTransform = lambda coll: resets.append([i.DisplayName for i in coll])
            back, since, missing = explode.collapse(record)
            assert (back, since, missing) == (2, 0, 0)
            assert doc.transactions == ['Exploded view', 'Collapse exploded view']
            assert resets == [['Wall 1', 'Duct']] and len(moves) == 2
            # centres that followed the move: each item goes back by its own offset
            tracked = dict(record, tracks=True)
            assert explode.collapse_route(tracked) == 'inverse'
            back, since, missing = explode.collapse(tracked)
            assert (back, since, missing) == (2, 0, 0) and len(resets) == 1
            assert doc.transactions[-1] == 'Collapse exploded view' and len(doc.transactions) == 3
            assert moves[2][1] == tuple(-x for x in moves[0][1])
        finally:
            if memory is None:
                sys.modules.pop('pynavis.memory', None)
            else:
                sys.modules['pynavis.memory'] = memory


def test_factor_text_keeps_small_spreads_readable():
    assert explode.factor_text(1.5) == '1.5x' and explode.factor_text(10.0) == '10x'
    assert explode.factor_text(1.05) == '1.05x' and explode.factor_text(2.25) == '2.25x'
    assert explode.collapse_route({'tracks': None}) == 'reset'
