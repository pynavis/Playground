# -*- coding: utf-8 -*-
"""Regression tests for the Select and Find refit: one test per bug the refit fixed."""
import sys

import _compat

from namo import find_library, find_query, find_repair, find_sets, hk_pickorder, quickfind
from namo import sel_history as sh
from namo import sel_pickorder as po
from namo import selecttools as st
from namo import setexchange as sx


# ---- Selection History: Back after clearing the selection ------------------------------


def _state(path):
    return sh.make_state([{'m': 'Arch.nwc', 'i': 0, 'p': path}], 1, '10:00:00', 'Walls')


def test_back_after_clearing_returns_to_the_last_selection():
    history = sh.new_history()
    for path in ('1', '2', '3'):
        sh.record(history, _state(path), now=0)
    # On the newest selection: Back goes one earlier, as before.
    assert sh.target(history, -1, at_cursor=True) == 1
    # The selection was cleared (not recorded): Back brings the newest one back.
    assert sh.target(history, -1, at_cursor=False) == 2
    # Forward is not affected, and the ends still stop.
    assert sh.target(history, 1, at_cursor=False) is None
    history['cursor'] = 0
    assert sh.target(history, -1, at_cursor=False) == 0
    assert sh.target(history, -1, at_cursor=True) is None
    assert sh.target(history, -1) is None                  # default: on the cursor


# ---- Pick Order: the hook's off path, the banner text ------------------------------------


def test_pick_order_hook_reads_its_flag_without_importing_the_tool():
    name = hk_pickorder.HOLDER_MODULE
    from namo import session
    assert name == session.PREFIX + po.HOLDER
    saved = sys.modules.pop(name, None)
    try:
        assert hk_pickorder.is_on() is False               # no holder yet: off
        session.holder(po.HOLDER).on = True
        assert hk_pickorder.is_on() is True
        session.holder(po.HOLDER).on = False
        assert hk_pickorder.is_on() is False
        hk_pickorder.handle('selection-changed', {})       # off: returns at once, no API
        hk_pickorder.handle('doc-opened', {})
    finally:
        sys.modules.pop(name, None)
        if saved is not None:
            sys.modules[name] = saved


def test_pick_order_status_text():
    message, detail = po.status_text(0)
    assert message == 'Pick order on: click items in order'
    assert 'Stop Picking' in detail
    message, detail = po.status_text(1, 'Basic Wall')
    assert message == 'Pick order on: 1 item picked'
    assert detail.startswith('Last: Basic Wall.')
    message, detail = po.status_text(1234)
    assert message == 'Pick order on: 1,234 items picked'
    assert not detail.startswith('Last')


# ---- Filter Selection: numbers picked from the list ----------------------------------------


def test_filter_matches_a_picked_number_by_how_it_reads():
    lengths = [12.3333333333, 12.3333331, 4.0, 12.5]
    tally = find_query.tally_values(lengths)
    shown = find_query.value_text(lengths[0])
    assert shown == '12.333333'
    cond = st.picked_condition('Element', 'Length', 'equals', shown, '', tally)
    assert cond['shown'] == shown
    readings = [(True, v) for v in lengths] + [(False, None)]
    assert st.filter_indices(readings, cond, keep=True) == [0, 1]
    assert st.filter_indices(readings, cond, keep=False) == [2, 3, 4]
    other = st.picked_condition('Element', 'Length', 'not_equals', shown, '', tally)
    assert st.filter_indices(readings, other, keep=True) == [2, 3]     # missing never passes


def test_filter_typed_and_text_values_still_use_the_rules():
    tally = find_query.tally_values(['Ducts', 'Pipes'])
    cond = st.picked_condition('Element', 'Category', 'equals', 'Ducts', '', tally)
    assert 'shown' not in cond
    readings = [(True, 'ducts'), (True, 'Pipes')]
    assert st.filter_indices(readings, cond) == [0]                    # text ignores case
    typed = st.picked_condition('Element', 'Length', 'gt', st.OTHER, '5', [])
    assert typed['value'] == '5' and 'shown' not in typed
    assert st.filter_indices([(True, 4.0), (True, 12.5)], typed) == [1]
    # a number picked for a non-equality test goes through the rules as before
    more = st.picked_condition('Element', 'Length', 'ge', '12.5', '', find_query.tally_values([12.5]))
    assert 'shown' not in more


# ---- find_query: unsearchable values, branch sampling -------------------------------------


def test_values_navisworks_cannot_search_are_not_offered():
    assert find_query.kind_of('NamedConstant:LcRevitMaterial(Steel)') is None
    assert find_query.kind_of('Point3D:1,2,3') is None
    assert find_query.kind_of('None') == 'text'                        # a real Revit value
    assert find_query.kind_of('Named constant') == 'text'
    assert find_query.kind_of('Type: A') == 'text'


def test_branches_open_the_tree_until_there_are_enough():
    tree = {'file': ['L1', 'L2'], 'L1': ['walls', 'ducts'], 'L2': ['pipes'],
            'walls': ['w1', 'w2'], 'ducts': ['d1'], 'pipes': ['p1', 'p2', 'p3']}
    kids = lambda node: tree.get(node, [])
    assert find_query.branches(['file'], kids, want=1) == ['file']
    assert find_query.branches(['file'], kids, want=2) == ['L1', 'L2']
    assert find_query.branches(['file'], kids, want=3) == ['walls', 'ducts', 'pipes']
    # leaves stay; opening stops when nothing has children or the depth runs out
    assert find_query.branches(['file'], kids, want=99) == ['w1', 'w2', 'd1', 'p1', 'p2', 'p3']
    assert find_query.branches(['file'], kids, want=99, max_depth=1) == ['L1', 'L2']
    assert find_query.branches([], kids) == []


# ---- Quick Find: type ids ---------------------------------------------------------------------


def test_quick_find_leaves_type_ids_out_where_the_model_marks_elements():
    rows = [(0, '0/1', ['Fixture', '900001']),      # the element
            (0, '0/1/1', ['Part', '555']),          # a nested part carrying the TYPE id
            (1, '0/1', ['Beam', '777'])]            # a model that marks no element at all
    out = quickfind.drop_type_ids(rows, [True, False, False], 1)
    assert [r[2][1] for r in out] == ['900001', '', '777']
    assert rows[1][2][1] == '555'                   # the input rows are not edited
    assert quickfind.drop_type_ids(rows, [True, False, False], None) == rows


# ---- Set Exchange: path hits are checked, small id searches ---------------------------------


def test_contradicts():
    ref = {'element_id': '312045', 'unique_id': 'abc-1', 'name': 'Basic Wall'}
    assert not sx.contradicts(ref, {'unique_id': 'ABC-1', 'name': 'Other'})   # first shared id decides
    assert sx.contradicts(ref, {'unique_id': 'abc-2', 'element_id': '312045'})
    assert sx.contradicts(ref, {'element_id': '999'})
    assert not sx.contradicts(ref, {'element_id': '312045', 'name': 'Renamed'})
    assert sx.contradicts({'name': 'Slab'}, {'name': 'Roof'})                 # no ids: the name
    assert not sx.contradicts({'name': 'Slab'}, {'name': ''})
    assert not sx.contradicts({}, {})
    assert sx.check_fields(ref) == ('unique_id',)
    assert sx.check_fields({'element_id': '5'}) == ('element_id',)
    assert sx.check_fields({'name': 'x'}) == ()


def test_id_search_plan_and_query():
    pending = [{'model': 'Arch.nwc', 'element_id': '1'}, {'model': 'Gone.nwc', 'element_id': '2'},
               {'model': 'ARCH.NWC', 'unique_id': 'u'}, {'model': 'arch.nwc', 'element_id': '3'}]
    assert sx.id_search_plan(pending, ['Arch.nwc', 'MEP.nwc']) == [0, 3]
    assert sx.id_search_plan(pending, ['Arch.nwc'], limit=1) == []            # too many: walk
    assert sx.id_search_plan(pending, ['MEP.nwc']) == []
    query = sx.element_id_query(312045)
    conds = query['or'][0]['and']
    assert conds[0] == {'category': 'Element ID', 'prop': 'Value', 'op': 'equals', 'value': '312045'}
    assert conds[1] == {'category': 'LcRevitData_Element', 'op': 'has_category', 'by_display': False}
    assert len(sx.element_id_query('7', elements_only=False)['or'][0]['and']) == 1
    from pynavis import sets
    assert sets._validate_import({'sets': [{'name': 'x', 'query': query}]}) == []


# ---- Sets: condition options survive, one bad set does not block a library ---------------


def test_with_options():
    cond = {'category': 'Element', 'prop': 'Category', 'op': 'equals', 'value': 'Ducts'}
    assert find_sets.with_options(cond) == cond
    assert find_sets.with_options(cond, ignore_case=True)['ignore_case'] is True
    assert 'ignore_case' not in cond                                           # a copy
    number = {'category': 'Element', 'prop': 'Width', 'op': 'equals', 'value': 12}
    assert 'ignore_case' not in find_sets.with_options(number, ignore_case=True)
    negated = find_sets.with_options(cond, negated=True, text='Category = Ducts')
    assert negated == {'op': 'raw', 'text': 'Category = Ducts (negated)'}
    assert find_sets.with_options(cond, or_group=True)['op'] == 'raw'
    raw = {'op': 'raw', 'text': 'x'}
    assert find_sets.with_options(raw, ignore_case=True) is raw


def test_split_importable_keeps_the_good_sets():
    good = {'name': 'Ducts', 'folder': None,
            'query': {'or': [{'and': [{'category': 'Element', 'prop': 'Category', 'op': 'equals',
                                       'value': 'Ducts'}]}]}}
    bad = {'name': 'Odd', 'folder': None, 'query': {'or': [{'and': [{'op': 'raw', 'text': 'x'}]}]}}
    spec, problems = find_library.split_importable({'sets': [good, bad]})
    assert spec == {'sets': [good]}
    assert len(problems) == 1 and 'Odd' in problems[0]
    spec, problems = find_library.split_importable({'sets': [good]})
    assert spec == {'sets': [good]} and problems == []
    assert find_library.split_importable({'sets': []}) == ({'sets': []}, [])


# ---- Repair Search In: a whole-model scope is always working -----------------------------


def test_whole_model_scope_is_ok_whatever_it_resolves_to():
    assert find_repair.classify({'whole': True, 'is_clear': False, 'sources': [], 'resolved': 0}) == 'ok'
    assert find_repair.classify({'whole': False, 'is_clear': True, 'sources': [], 'resolved': 0}) == 'empty'
