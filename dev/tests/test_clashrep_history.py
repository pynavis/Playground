# -*- coding: utf-8 -*-
"""clashrep_history: baselines, deltas and trend series on constructed histories."""
import datetime

import _compat  # noqa: F401  (puts lib on the path)

from namo import clashdata
from namo import clashrep_history as hist

NOW = datetime.datetime(2026, 10, 5, 9, 0)


def _row(pair, cell, status='New', name=None, test='T1', **extra):
    row = {'item_a': pair[0], 'item_b': pair[1], 'center_m': cell, 'status': status, 'test': test,
           'name': name or '%s-%s' % pair, 'trade_a': 'Mechanical', 'trade_b': 'Structure', 'grid': 'C-4',
           'level': 'Level 2', 'distance_m': -0.05}
    row.update(extra)
    row['key'] = clashdata.pair_key(row)
    return row


def _entry(entry_id, when, counts, label=None):
    return {'id': entry_id, 'time': when.strftime('%Y-%m-%dT%H:%M:%S'), 'label': label or when.strftime(
        '%Y-%m-%d %H:%M:%S'), 'counts': counts}


def _counts(**by_status):
    return {'total': sum(by_status.values()), 'by_status': by_status}


def _history(rows):
    """Rows as they come back from clashdata.load_history (compact HISTORY_FIELDS)."""
    return clashdata.expand_rows(clashdata.HISTORY_FIELDS, clashdata.compact_rows(rows))


def test_open_closed_and_totals():
    assert hist.open_closed(_counts(New=3, Active=2, Reviewed=1, Approved=4, Resolved=5)) == (6, 9, 15)
    assert hist.open_closed({'total': 2, 'by_status': {'new': 1, 'NEW': 1}}) == (2, 0, 2)
    assert hist.open_closed(None) == (0, 0, 0)
    entry = _entry('h1', NOW, {'A': _counts(New=2, Resolved=1), 'B': _counts(Active=4)})
    assert hist.entry_totals(entry) == {'tests': 2, 'open': 6, 'closed': 1, 'total': 7}
    assert hist.entry_totals(entry, ['B', 'Missing']) == {'tests': 1, 'open': 4, 'closed': 0, 'total': 4}


def test_entry_text():
    entry = _entry('h1', datetime.datetime(2026, 10, 4, 17, 30), {'A': _counts(New=1240)})
    assert hist.entry_text(entry) == '2026-10-04 17:30: 1 test, 1,240 clashes, 1,240 open'
    entry['label'] = 'Before the meeting'
    assert hist.entry_text(entry).startswith('Before the meeting, 2026-10-04 17:30: ')


def test_pick_and_find_baseline():
    entries = [_entry('h1', datetime.datetime(2026, 10, 1, 8), {}),
               _entry('h2', datetime.datetime(2026, 10, 4, 18), {}, label='Meeting 4'),
               _entry('h3', datetime.datetime(2026, 10, 5, 7), {})]
    assert hist.pick_baseline(entries, NOW)['id'] == 'h2'
    assert hist.pick_baseline(entries[2:], NOW)['id'] == 'h3'          # only today: the latest
    assert hist.pick_baseline([], NOW) is None
    assert hist.find_entry(entries, 'auto', NOW)['id'] == 'h2'
    assert hist.find_entry(entries, '', NOW)['id'] == 'h2'
    assert hist.find_entry(entries, 'latest')['id'] == 'h3'
    assert hist.find_entry(entries, 'previous')['id'] == 'h2'
    assert hist.find_entry(entries[:1], 'previous') is None
    assert hist.find_entry(entries, 'h1')['id'] == 'h1'
    assert hist.find_entry(entries, 'meeting 4')['id'] == 'h2'
    assert hist.find_entry(entries, 'nope') is None
    assert hist.age_text(datetime.datetime(2026, 10, 4, 23), NOW) == '1 day ago'
    assert hist.age_text(datetime.datetime(2026, 9, 5), NOW) == '30 days ago'
    assert hist.age_text(NOW, NOW) == 'today' and hist.age_text(None, NOW) == ''


def test_delta_buckets_and_totals():
    old_t1 = [_row(('a', 'b'), (0, 0, 0)),                                  # still open
              _row(('c', 'd'), (1, 1, 1)),                                  # gone -> fixed
              _row(('e', 'f'), (2, 2, 2)),                                  # resolved now -> fixed
              _row(('g', 'h'), (3, 3, 3), status='Approved')]               # closed then: ignored
    new_t1 = [_row(('b', 'a'), (0, 0, 0), status='Active'),
              _row(('e', 'f'), (2, 2, 2), status='Resolved'),
              _row(('x', 'y'), (4, 4, 4)),                                  # new
              _row(('p', 'q'), (5, 5, 5), status='Approved')]               # new but closed
    new_t2 = [_row(('m', 'n'), (6, 6, 6), test='T2')]
    d = hist.delta({'T1': _history(old_t1), 'Gone test': []}, {'T1': new_t1, 'T2': new_t2}, ['T1', 'T2'])
    t1, t2 = d['tests']
    assert t1['baseline'] and t1['then_open'] == 3 and t1['now_open'] == 2
    assert [r['name'] for r in t1['new']] == ['x-y']
    assert [(r['name'], how) for r, how in t1['fixed']] == [('c-d', 'Gone'), ('e-f', 'Resolved')]
    assert [r['name'] for r in t1['persisting']] == ['b-a']
    assert [(o['status'], n['status']) for o, n in t1['changed']] == [('New', 'Active'), ('New', 'Resolved')]
    assert t1['net'] == -1
    assert not t2['baseline'] and t2['then_open'] is None and t2['new'] == [] and t2['now_open'] == 1
    assert d['totals'] == {'then_open': 3, 'now_open': 2, 'new': 1, 'fixed': 2, 'persisting': 1, 'changed': 2,
                           'net': -1}
    assert d['without_baseline'] == ['T2'] and d['dropped'] == []
    assert hist.delta_headline(d) == '1 new, 2 fixed, 1 still open'
    loose = hist.delta({'T1': [], 'Old': []}, {'T1': []})
    assert loose['dropped'] == ['Old']


def test_trend_points_partial_and_current():
    t1 = datetime.datetime(2026, 9, 1, 8)
    t2 = datetime.datetime(2026, 9, 8, 8)
    t3 = datetime.datetime(2026, 9, 8, 17)
    entries = [_entry('h2', t2, {'A': _counts(New=5, Resolved=5), 'B': _counts(Active=2)}),
               _entry('h1', t1, {'A': _counts(New=10)}),
               _entry('h3', t3, {'A': _counts(New=2, Resolved=8), 'B': _counts(Approved=2)})]
    current = {'time': NOW, 'counts': {'A': _counts(Resolved=10), 'B': _counts(Active=1)}}
    points, names = hist.trend_points(entries, None, current)
    assert names == ['A', 'B']
    assert [p['id'] for p in points] == ['h1', 'h2', 'h3', None]
    assert [p['open'] for p in points] == [10, 7, 2, 1]
    assert [p['closed'] for p in points] == [0, 5, 10, 10]
    assert points[0]['partial'] and points[0]['per_test'] == {'A': 10, 'B': None}
    assert not points[1]['partial'] and points[1]['present'] == 2
    labels = hist.point_labels(points)
    assert labels == ['2026-09-01', '2026-09-08 08:00', '2026-09-08 17:00', 'Now']
    only_a, names_a = hist.trend_points(entries, ['A'])
    assert names_a == ['A'] and [p['open'] for p in only_a] == [10, 5, 2]
    rows = hist.burndown_rows(points, labels, [None, (1, 4), (0, 5), None])
    assert rows[0] == ['2026-09-01', '', '1 of 2', 10, 0, 10, None, None, None]
    assert hist.own_label('Meeting 4', t1) == 'Meeting 4' and hist.own_label(None, None) == ''
    assert rows[1][6:] == [1, 4, -3] and rows[3][1] == 'Current state'
    assert hist.trend_summary(points) == 'Open clashes went from 10 to 1 over 4 points (down 9).'
    assert hist.trend_summary(points[:1]) == ''


def test_flows_compare_consecutive_points():
    a1 = [_row(('a', 'b'), (0, 0, 0)), _row(('c', 'd'), (1, 1, 1))]
    a2 = [_row(('a', 'b'), (0, 0, 0)), _row(('x', 'y'), (9, 9, 9))]
    a3 = [_row(('a', 'b'), (0, 0, 0), status='Resolved')]
    flow = hist.flows([{'A': a1}, {'A': a2}, None, {'A': a3, 'B': []}], ['A', 'B'])
    assert flow == [None, (1, 1), None, None]
    flow = hist.flows([{'A': a1}, {'A': a2}, {'A': a3}], ['A'])
    assert flow[2] == (0, 2)


def test_thin_and_due():
    labels = ['d%d' % i for i in range(20)]
    thinned = hist.thin(labels, 8)
    assert thinned[0] == 'd0' and thinned[-1] == 'd19' and sum(1 for l in thinned if l) <= 9
    assert hist.thin(['a', 'b'], 8) == ['a', 'b']
    entries = [_entry('h1', datetime.datetime(2026, 10, 5, 6), {})]
    assert not hist.due_for_auto(entries, NOW, 4)
    assert hist.due_for_auto(entries, NOW, 3)
    assert hist.due_for_auto([], NOW, 4)
    assert hist.due_for_auto(entries, NOW, 0)


def test_snapshot_message():
    entry = {'counts': {'A': _counts(New=3, Resolved=2), 'B': _counts(Active=1)}}
    message, detail = hist.snapshot_message(entry, 'Kept on this computer.')
    assert message == 'Snapshot saved: 2 tests, 6 clashes'
    assert detail == '4 open. Kept on this computer. Clash Delta and Clash Trends can compare with it.'
