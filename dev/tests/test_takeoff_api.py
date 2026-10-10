# -*- coding: utf-8 -*-
"""namo.takeoff.collect and run over the shared fake Navisworks layer (test_items):
scopes, group keys, property measures in each model's own units, tile zones."""
import _compat
import test_items as nav
from namo import takeoff


def _model():
    doc, n = nav.model_tree()
    n['Wall 1'].props[('Element', 'Volume')] = 2.0                 # ARCH model is in metres
    n['Wall 2'].props[('Element', 'Volume')] = '1.5 m³'
    n['Duct'].props[('Element', 'Volume')] = 1.0e9                 # MEP model is in millimetres
    n['Duct'].props[('Element', 'Length')] = '2500 mm'
    return doc, n


def test_collect_reads_measures_per_model_units():
    doc, n = _model()
    config = {'scope': 'model', 'measures': ['count', 'volume', 'length'],
              'group_by': [{'special': '@category'}, {'special': '@model'}]}
    with nav.FakeNav(doc):
        data = takeoff.collect(config, doc)
    by_name = dict((r['name'], r) for r in data['records'])
    assert sorted(by_name) == ['Duct', 'Hidden box', 'Wall 1', 'Wall 2']
    assert by_name['Wall 1']['groups'] == ['Walls', 'ARCH.rvt']
    assert by_name['Duct']['groups'] == ['Ducts', 'MEP.rvt']
    assert by_name['Wall 1']['measures']['volume'] == 2.0
    assert _compat.approx(by_name['Wall 2']['measures']['volume'], 1.5)
    assert _compat.approx(by_name['Duct']['measures']['volume'], 1.0)
    assert _compat.approx(by_name['Duct']['measures']['length'], 2.5)
    assert by_name['Hidden box']['measures']['volume'] is None
    assert data['pairs']['volume'] == [('Element', 'Volume')]
    assert data['sampled'] is False and data['geometric'] == 0


def test_run_aggregates_and_visible_scope():
    doc, n = _model()
    config = {'scope': 'visible', 'measures': ['count', 'volume'], 'group_by': [{'special': '@category'}],
              'units': 'm'}
    with nav.FakeNav(doc):
        result = takeoff.run(config, doc)
    names = [r['name'] for r in result['data']['records']]
    assert 'Hidden box' not in names and len(names) == 3
    totals = result['rows'][-1]
    assert totals['kind'] == 'total' and totals['count'] == 3
    assert _compat.approx(totals['values']['volume'], 4.5)
    assert result['group_titles'] == ['Category'] and result['unit_set']['volume'] == 'm3'
    assert result['status'] == '3 objects in 2 groups.'


def test_tiles_zone_assignment():
    doc, n = _model()
    config = {'scope': 'model', 'measures': ['count'], 'group_by': [{'special': '@category'}],
              'zones': {'mode': 'tiles', 'spacing': 5.0}}
    with nav.FakeNav(doc):
        data = takeoff.collect(config, doc)
    zones = dict((r['name'], r['zone']) for r in data['records'])
    assert zones['Wall 1'] == 'X01 Y01' and zones['Wall 2'] == 'X02 Y01'
    assert zones['Hidden box'] == 'X02 Y02'
    with nav.FakeNav(doc):
        _compat.raises(ValueError, takeoff.collect, dict(config, zones={'mode': 'levels'}), doc)
        _compat.raises(ValueError, takeoff.collect, dict(config, zones={'mode': 'tiles', 'spacing': 0}), doc)
