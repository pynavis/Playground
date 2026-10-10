# -*- coding: utf-8 -*-
"""namo.clashdata pure half: pair keys, run-to-run comparison, history records/stores."""
import datetime

import _compat

from namo import clashdata


def _row(a, b, center, status='New', test='T1', **extra):
    row = {'item_a': a, 'item_b': b, 'center_m': center, 'status': status, 'test': test,
           'name': 'Clash', 'distance_m': -0.01, 'created': None, 'trade_a': 'Mechanical',
           'trade_b': 'Structure', 'grid': 'A-1', 'level': 'L1'}
    row.update(extra)
    return row


def test_pair_key_is_order_free_and_rounded():
    k1 = clashdata.pair_key(_row('A', 'B', (1.01, 2.0, 3.0)))
    k2 = clashdata.pair_key(_row('B', 'A', (0.99, 2.04, 2.96)))
    assert k1 == k2 == 'A|B@10,20,30'


def test_pair_key_without_centre_and_from_center():
    assert clashdata.pair_key({'item_a': 'X', 'item_b': ''}) == '|X@-'
    assert clashdata.pair_key({'item_a': 'a', 'item_b': 'b', 'center': (0.5, 0, 0)}) == 'a|b@5,0,0'


def test_pair_key_keeps_history_key():
    assert clashdata.pair_key({'key': 'k@1,2,3', 'status': 'New'}) == 'k@1,2,3'


def test_split_key():
    assert clashdata.split_key('a|b@1,-2,3') == ('a|b', (1, -2, 3))
    assert clashdata.split_key('a|b@-') == ('a|b', None)
    assert clashdata.split_key('nokey') == ('nokey', None)


def test_compare_buckets():
    old = [_row('A', 'B', (0, 0, 0)),                       # persists
           _row('C', 'D', (5, 5, 5)),                       # disappears -> fixed
           _row('E', 'F', (9, 9, 9)),                       # resolved in new -> fixed
           _row('G', 'H', (1, 1, 1), status='Approved')]    # already closed, gone: nothing
    new = [_row('B', 'A', (0, 0, 0), status='Active'),
           _row('E', 'F', (9, 9, 9), status='Resolved'),
           _row('X', 'Y', (2, 2, 2)),                       # new
           _row('P', 'Q', (3, 3, 3), status='Approved')]    # unmatched but closed
    result = clashdata.compare(old, new)
    assert [r['item_a'] for r in result['new']] == ['X']
    assert [r['item_a'] for r in result['fixed']] == ['C', 'E']
    assert [r['item_a'] for r in result['persisting']] == ['B']
    assert [(o['status'], n['status']) for o, n in result['status_changed']] == [
        ('New', 'Active'), ('New', 'Resolved')]
    assert [r['item_a'] for r in result['closed_new']] == ['P']
    assert result['matched'] == 2


def test_compare_tolerates_boundary_flicker():
    old = [_row('A', 'B', (1.049, 0, 0))]
    new = [_row('A', 'B', (1.051, 0, 0))]
    assert clashdata.pair_key(old[0]) != clashdata.pair_key(new[0])
    result = clashdata.compare(old, new)
    assert result['matched'] == 1 and not result['new'] and not result['fixed']


def test_compare_does_not_match_far_or_other_pairs():
    old = [_row('A', 'B', (0, 0, 0))]
    new = [_row('A', 'B', (0.5, 0, 0)), _row('A', 'C', (0, 0, 0))]
    result = clashdata.compare(old, new)
    assert result['matched'] == 0
    assert len(result['new']) == 2 and len(result['fixed']) == 1


def test_compare_duplicates_pair_one_to_one():
    old = [_row('A', 'B', (0, 0, 0)), _row('A', 'B', (0, 0, 0))]
    new = [_row('A', 'B', (0, 0, 0))]
    result = clashdata.compare(old, new)
    assert result['matched'] == 1 and len(result['fixed']) == 1


def test_compare_empty():
    result = clashdata.compare([], None)
    assert result['new'] == [] and result['fixed'] == [] and result['matched'] == 0


def test_counts_iso_unique():
    c = clashdata.counts([{'status': 'New'}, {'status': 'New'}, {'status': 'Active'}])
    assert c == {'total': 3, 'by_status': {'New': 2, 'Active': 1}}
    assert clashdata.iso(datetime.datetime(2026, 1, 2, 3, 4, 5)) == '2026-01-02T03:04:05'
    assert clashdata.iso(None) is None

    class NetDate(object):
        Year, Month, Day, Hour, Minute, Second = 2025, 12, 31, 23, 59, 58
    assert clashdata.iso(NetDate()) == '2025-12-31T23:59:58'
    assert clashdata.unique_names(['A', 'B', 'A', 'A', 'A (2)']) == ['A', 'B', 'A (2)', 'A (3)', 'A (2) (2)']


def test_history_record_round_trip():
    rows = {'T1': [_row('A', 'B', (0, 0, 0))], 'T2': [_row('C', 'D', (1, 0, 0), status='Active')]}
    record = clashdata.history_record(rows, now=datetime.datetime(2026, 10, 5, 9, 0, 0))
    assert record['id'].startswith('h-20261005-090000-')
    assert record['label'] == '2026-10-05 09:00:00'
    assert record['counts']['T2'] == {'total': 1, 'by_status': {'Active': 1}}
    back = clashdata.record_rows(record)
    assert back['T1'][0]['key'] == 'A|B@0,0,0'
    assert back['T1'][0]['grid'] == 'A-1'
    assert sorted(back['T1'][0]) == sorted(clashdata.HISTORY_FIELDS)
    # history rows compare against fresh snapshot rows
    result = clashdata.compare(back['T1'], [_row('B', 'A', (0, 0, 0), status='Resolved')])
    assert len(result['fixed']) == 1


class _FakeStore(object):
    def __init__(self):
        self.value = None

    def load(self, default=None):
        return default if self.value is None else self.value

    def save(self, value):
        self.value = value

    def update(self, fn, default=None):
        self.value = fn(self.load(default))
        return self.value


class _FakeRecords(object):
    def __init__(self):
        self.records = {}

    def put(self, record):
        self.records[record['id']] = record

    def get(self, record_id):
        return self.records.get(record_id)

    def list(self):
        return [self.records[k] for k in sorted(self.records)]

    def delete(self, record_id):
        self.records.pop(record_id, None)


def test_history_stores():
    index, records = _FakeStore(), _FakeRecords()
    saved = clashdata._STORES
    clashdata._STORES = lambda doc_path: (index, records)
    try:
        first = clashdata.save_history('C:/m.nwf', {'T1': [_row('A', 'B', (0, 0, 0))]}, label='Monday')
        second = clashdata.save_history('C:/m.nwf', {'T1': []})
        listed = clashdata.list_history('C:/m.nwf')
        assert [e['id'] for e in listed] == [first['id'], second['id']]
        assert listed[0]['label'] == 'Monday' and listed[0]['counts']['T1']['total'] == 1
        loaded = clashdata.load_history('C:/m.nwf', first['id'])
        assert loaded['T1'][0]['key'] == 'A|B@0,0,0'
        assert clashdata.load_history('C:/m.nwf', 'missing') is None
        # a lost index is rebuilt from the records
        index.value = None
        assert len(clashdata.list_history('C:/m.nwf')) == 2
        assert clashdata.delete_history('C:/m.nwf', first['id'])
        assert [e['id'] for e in clashdata.list_history('C:/m.nwf')] == [second['id']]
    finally:
        clashdata._STORES = saved


def test_history_against_real_store_layout():
    try:
        from namo import paths, store  # noqa: F401
    except Exception:
        raise _compat.SkipTest('namo.store is not available yet')
    if not hasattr(paths, 'redirect'):
        raise _compat.SkipTest('namo.paths has no redirect() test seam')
    import os
    root = _compat.tmpdir('clash_history_store')
    previous = paths.redirect(root)
    try:
        doc_path = os.path.join(root, 'model.nwf')
        first = clashdata.save_history(doc_path, {'T1': [_row('A', 'B', (0, 0, 0))]}, label='One')
        second = clashdata.save_history(doc_path, {'T1': []}, label='Two')
        listed = clashdata.list_history(doc_path)
        assert [e['label'] for e in listed] == ['One', 'Two']
        assert first['id'] != second['id']
        assert clashdata.load_history(doc_path, first['id'])['T1'][0]['key'] == 'A|B@0,0,0'
    finally:
        paths.redirect(previous)


def test_statuses_constant():
    assert clashdata.STATUSES == ['New', 'Active', 'Reviewed', 'Approved', 'Resolved']


# ---- API half through the fake Navisworks layer (see test_items) -----------------

import test_items as nav  # noqa: E402


def _clash_doc():
    doc, n = nav.model_tree()
    r1 = nav.ClashResult('Clash1', n['Duct solid'], n['Wall 1 solid'], (1.0, 2.0, 3.0))
    r2 = nav.ClashResult('Clash2', n['Duct solid'], n['Wall 2 solid'], (5.0, 2.0, 3.0), status='Active')
    r3 = nav.ClashResult('Clash3', n['Duct solid'], None, None, status='Resolved')
    r4 = nav.ClashResult('Clash4', n['Wall 1 solid'], n['Wall 2 solid'], (3.0, 0.0, 0.0))
    inner = nav.ClashResultGroup('Inner', [r2])
    outer = nav.ClashResultGroup('Duct group', [inner, r3])
    test = nav.ClashTest('MEP vs ARCH', [r1, outer, r4])
    other = nav.ClashTest('Other', [nav.ClashResult('Elsewhere')])
    doc.clash_tests = [test, nav.ClashTest('Empty', []), other]
    doc.clash_data = nav.FakeTestsData()
    doc.clash_data.tests = doc.clash_tests
    doc.u2m = 0.3048
    return doc, n, test, (r1, r2, r3, r4), (inner, outer)


def test_api_snapshot_enriches_in_walk_order():
    doc, n, test, (r1, r2, r3, r4), (inner, outer) = _clash_doc()
    with nav.FakeNav(doc):
        assert [t.DisplayName for t in clashdata.tests()] == ['MEP vs ARCH', 'Empty', 'Other']
        assert clashdata.test_by_name('mep vs arch') is test
        assert clashdata.test_by_name('nope') is None
        assert [r.DisplayName for r in clashdata.results(test)] == ['Clash1', 'Clash2', 'Clash3', 'Clash4']
        seen = []
        rows = clashdata.snapshot(test, progress=lambda f, label: seen.append(f))
        assert [r['id'] for r in rows] == [0, 1, 2, 3]
        assert [r['name'] for r in rows] == ['Clash1', 'Clash2', 'Clash3', 'Clash4']
        assert seen[0] == 0.0 and seen[-1] == 1.0
        first = rows[0]
        assert first['test'] == 'MEP vs ARCH' and first['test_guid'] == test.Guid
        assert first['guid'] == r1.Guid
        assert first['model_a'] == 'MEP.rvt' and first['model_b'] == 'ARCH.rvt'
        assert _compat.approx(first['distance_m'], -0.01 * 0.3048)
        assert _compat.approx(first['center_m'], (0.3048, 0.6096, 0.9144))
        assert first['created'] == '2026-10-01T08:30:00'
        assert first['description'] == 'desc Clash1' and first['priority'] == 3 and first['comments'] == 1
        assert first['group'] is None and first['group_guid'] is None
        assert rows[1]['group'] == 'Inner' and rows[1]['group_guid'] == inner.Guid
        assert rows[2]['group_guid'] == outer.Guid and rows[2]['center_m'] is None
        assert rows[2]['model_b'] == ''
        assert first['key'] == clashdata.pair_key(first)
        assert first['trade_a'] and first['trade_b']
        everything = clashdata.snapshot_all(None)
        assert sorted(everything) == ['Empty', 'MEP vs ARCH', 'Other'] and everything['Empty'] == []


def test_api_snapshot_cancel_and_mismatch():
    doc, n, test, results, groups = _clash_doc()
    with nav.FakeNav(doc):
        _compat.raises(clashdata.Cancelled, clashdata.snapshot, test, None,
                       lambda f, label: False if f > 0 else None)
        original = clashdata._walk_leaves

        def shuffled(t):
            leaves = original(t)
            return [leaves[1], leaves[0]] + leaves[2:]
        clashdata._walk_leaves = shuffled
        try:
            _compat.raises(RuntimeError, clashdata.snapshot, test)
        finally:
            clashdata._walk_leaves = original


def test_api_groups_and_edits():
    doc, n, test, (r1, r2, r3, r4), (inner, outer) = _clash_doc()
    with nav.FakeNav(doc):
        found = clashdata.groups(test)
        assert len(found) == 1
        assert found[0]['name'] == 'Duct group' and found[0]['count'] == 2
        assert found[0]['statuses'] == {'Active': 1, 'Resolved': 1}
        assert clashdata.set_assigned([r1, r2], 'Amol') == 2
        assert clashdata.set_assigned(r4, None) == 1
        assert clashdata.set_description(r1, 'Moved duct') == 1
        assert clashdata.set_priority([r1], '2') == 1
        assert clashdata.set_assigned([], 'x') == 0
        assert clashdata.add_comment(r1, 'Looks fixed', author='AS') == 2
        calls = doc.clash_data.calls
        assert calls[0] == ('assigned', 'Clash1', 'Amol') and calls[2] == ('assigned', 'Clash4', None)
        assert ('description', 'Clash1', 'Moved duct') in calls
        assert ('priority', 'Clash1', 2) in calls
        assert calls[-1] == ('comments', 'Clash1', ['first', 'Looks fixed'])
        assert doc.transactions == ['Assign clashes', 'Assign clashes', 'Describe clashes',
                                    'Prioritise clashes', 'Comment on clash']
        assert clashdata.resolve_guid(test, r3.Guid.upper()) is r3
        assert clashdata.resolve_guid(test, '') is None
        elsewhere = doc.clash_tests[2].Children[0]
        assert clashdata.resolve_guid(test, elsewhere.Guid) is None
        assert clashdata.resolve_guid(doc.clash_tests[2], elsewhere.Guid) is elsewhere
        assert clashdata.viewpoint(r1) is not None
        clashdata.show(r1)
        assert doc.selected == [n['Duct solid'], n['Wall 1 solid']]
