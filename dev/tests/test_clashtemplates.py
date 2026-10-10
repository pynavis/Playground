# -*- coding: utf-8 -*-
"""namo.clashtemplates: template configs, apply planning over a resolver, recreate
targets, and save/apply through the fake clash layer and a scratch template store."""
import os

import _compat
import test_clashset_tests as cf

from namo import clashset_tests as defs
from namo import clashtemplates as ct
from namo import paths

QUERY = {'or': [{'and': [{'category': 'Element', 'prop': 'Category', 'op': 'equals',
                          'value': 'Ducts'}]}]}


def _definition(name, a_sources, b_sources, test_type='hard', tolerance=0.0):
    return defs.new_definition(name, test_type, tolerance, defs.new_side(a_sources),
                               defs.new_side(b_sources))


def test_template_config_and_describe():
    config = ct.template_config([_definition('T1', [{'kind': 'set', 'path': 'A'}],
                                             [{'kind': 'model', 'name': 'B.nwc'}])],
                                source='Hospital.nwf', doc_units='Millimeters')
    assert config['version'] == 1 and config['units'] == 'Millimeters'
    assert ct.describe(config) == '1 test from Hospital.nwf'
    assert ct.describe({'tests': []}) == '0 tests'
    assert ct.definitions_of('junk') == []
    assert len(ct.definitions_of(config)) == 1


def test_portability_notes():
    d = _definition('T', [{'kind': 'items', 'count': 3}], [{'kind': 'set', 'path': 'X'}])
    assert ct.portability_notes([d]) == [
        'T: selection A holds hand-picked items, which only apply in this model.']


def test_plan_apply_statuses():
    defs_list = [
        _definition('Ready', [{'kind': 'set', 'path': 'A'}], [{'kind': 'set', 'path': 'B'}]),
        _definition('Rebuild', [{'kind': 'set', 'path': 'Gone', 'search': QUERY}],
                    [{'kind': 'set', 'path': 'B'}]),
        _definition('Lost', [{'kind': 'set', 'path': 'Lost'}], [{'kind': 'set', 'path': 'B'}]),
        _definition('There', [{'kind': 'set', 'path': 'A'}], [{'kind': 'set', 'path': 'B'}]),
        _definition('Odd', [{'kind': 'set', 'path': 'A'}], [{'kind': 'set', 'path': 'B'}],
                    test_type='custom'),
    ]
    config = ct.template_config(defs_list)

    def resolve(source):
        path = source.get('path')
        if path in ('A', 'B'):
            return 'ok', None
        if path == 'Gone':
            return 'recreate', None
        return 'missing', 'Selection set "%s" is not in this model.' % path

    rows = ct.plan_apply(config, resolve, lambda name: name == 'There')
    assert [r['status'] for r in rows] == ['ready', 'recreate', 'missing', 'exists', 'invalid']
    assert rows[1]['recreate'][0]['path'] == 'Gone'
    assert rows[2]['problems'] == ['Selection set "Lost" is not in this model.']
    assert [ct.buildable(r) for r in rows] == [True, True, False, True, False]
    cells = ct.plan_cells(rows[2], 'Meters')
    assert cells[0] == 'Lost' and cells[5].startswith('Missing items: Selection set')


def test_recreate_target_and_can_recreate():
    assert ct.recreate_target({'path': 'MEP/Sub/Ducts'}) == ('MEP/Sub', 'Ducts')
    assert ct.recreate_target({'path': 'Ducts'}) == (None, 'Ducts')
    assert ct.can_recreate({'kind': 'set', 'path': 'X', 'search': QUERY})
    assert not ct.can_recreate({'kind': 'set', 'path': 'X', 'search': None})
    assert not ct.can_recreate({'kind': 'set', 'path': 'X', 'folder': True, 'search': QUERY})
    two = {'or': QUERY['or'] + QUERY['or']}
    assert not ct.can_recreate({'kind': 'set', 'path': 'X', 'search': two})


def test_store_round_trip_in_scratch_root():
    folder = _compat.tmpdir('clashtemplates')
    previous = paths.redirect(folder)
    try:
        store = ct.store()
        config = ct.template_config([_definition('T', [{'kind': 'set', 'path': 'A'}],
                                                 [{'kind': 'set', 'path': 'B'}])])
        assert store.save('Hospital standard', config) == 'Hospital standard'
        assert store.names() == ['Hospital standard']
        back = store.get('hospital standard')
        assert ct.definitions_of(back)[0]['name'] == 'T'
        exported = os.path.join(folder, 'out.json')
        assert store.export(exported) == 1
        assert store.delete('Hospital standard')
        assert store.import_file(exported) == 1
    finally:
        paths.redirect(previous)


def test_read_tests_plan_and_apply_through_fakes():
    doc, named = cf.new_doc()
    with cf.ClashNav(doc) as fake:
        ducts = cf.add_set(doc, 'MEP/Ducts', [named['Duct']], query=QUERY)
        walls = cf.add_set(doc, 'Walls', [named['Wall 1']])
        test = cf.ClashTest('Ducts vs Walls')
        sources_a = cf.SelectionSourceCollection()
        sources_a.Add(cf.FakeSource(ducts))
        sources_b = cf.SelectionSourceCollection()
        sources_b.Add(cf.FakeSource(walls))
        test.SelectionA.Selection.CopyFrom(sources_a)
        test.SelectionB.Selection.CopyFrom(sources_b)
        definitions = ct.read_tests([test], doc)
        config = ct.template_config(definitions)
        config['tests'][0]['name'] = 'Copied test'
        # the ducts set goes missing: the stored search rebuilds it
        doc.SelectionSets.RootItem.Children[0].Children.remove(ducts)
        rows = ct.plan(config, doc)
        assert [r['status'] for r in rows] == ['recreate']
        results, recreated = ct.apply(rows, 'skip', doc)
        assert recreated == 1
        assert results[0]['outcome'] == 'created'
        assert ('create', 'Ducts', 'MEP') in fake.sets.calls
        assert doc.transactions == ['Apply clash template']
        assert [t.DisplayName for t in doc.clash_tests] == ['Copied test']
        rows = ct.plan(config, doc)
        assert rows[0]['status'] == 'exists'


def test_read_tests_with_failures_names_the_unreadable_test():
    # Regression: one test Navisworks would not describe stopped Save with a traceback.
    doc, named = cf.new_doc()
    with cf.ClashNav(doc):
        good = cf.ClashTest('Good')
        bad = cf.ClashTest('Bad')
        bad.SelectionA = None
        definitions, unread = ct.read_tests([good, bad], doc, with_failures=True)
        assert [d['name'] for d in definitions] == ['Good']
        assert unread == ['Bad']
        assert [d['name'] for d in ct.read_tests([good], doc)] == ['Good']
