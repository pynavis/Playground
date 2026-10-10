# -*- coding: utf-8 -*-
"""namo.clashassign: who moves, auto plans, history ownership, the dashboard numbers,
and units/assign/history through the fakes and a scratch store."""
import datetime

import _compat
import test_clashset_tests as cf

from namo import clashassign as ca
from namo import clashname as cn
from namo import paths

TODAY = datetime.datetime(2026, 10, 5)
P = ca.DEFAULT_PRIORITY


def _row(trade_a, trade_b, status='New', created='2026-09-25T08:00:00'):
    return {'trade_a': trade_a, 'trade_b': trade_b, 'status': status, 'created': created}


def test_priority_list_forms():
    assert ca.priority_list('Structure > Mechanical > structure') == ['Structure', 'Mechanical']
    assert ca.priority_list('A\nB\n\nC') == ['A', 'B', 'C']
    assert ca.priority_list(['X', 'x', 'Y']) == ['X', 'Y']
    assert ca.priority_list('') == []


def test_saved_settings_reads_the_bundle_key():
    calls = []

    def loader(key, defaults):
        calls.append(key)
        return {'priority': 'Structure > Mechanical', 'names': 'Mechanical = Jane Smith\nnonsense'}
    assert ca.saved_settings(loader) == (['Structure', 'Mechanical'], {'mechanical': 'Jane Smith'})
    assert calls == [ca.SETTINGS_KEY]
    assert ca.saved_settings(lambda key, defaults: {'priority': [], 'names': ''}) == (list(P), {})
    assert ca.saved_settings(lambda key, defaults: 1 / 0) == (list(P), {})


def test_settings_key_matches_the_bundle_path():
    """The key pynavis.script.get_config derives for Clash Assigner's folder."""
    import re
    bundle = 'Coordinate.tab/Clash_Results.panel/Clash_Assigner.pushbutton'
    assert ca.SETTINGS_KEY == 'cfg_' + re.sub(r'[^a-z0-9]+', '_', bundle.lower()).strip('_')


def test_mover_follows_priority():
    assert ca.mover('Structure', 'Mechanical', P) == 'Mechanical'
    assert ca.mover('Fire Protection', 'Architecture', P) == 'Fire Protection'
    assert ca.mover('Plumbing', 'Electrical', P) == 'Electrical'
    assert ca.mover('Civil', 'Structure', P) == 'Civil'
    assert ca.mover('Mechanical', 'mechanical', P) == 'Mechanical'
    assert ca.mover('Unassigned', 'Structure', P) is None
    assert ca.mover('', '', P) is None
    assert ca.mover('Civil', 'Landscape', P) == 'Civil'


def test_dominant_pair_ignores_order():
    rows = [_row('Mechanical', 'Structure'), _row('Structure', 'Mechanical'), _row('Electrical', 'Structure')]
    assert ca.dominant_pair(rows) == ('Mechanical', 'Structure')
    assert ca.dominant_pair([]) == ('', '')


def test_names_map_and_assignee():
    names = ca.names_map('Mechanical = J. Smith\nbad line\n Plumbing =  A. Lee ')
    assert names == {'mechanical': 'J. Smith', 'plumbing': 'A. Lee'}
    assert ca.assignee_for('Mechanical', names) == 'J. Smith'
    assert ca.assignee_for('Electrical', names) == 'Electrical'
    assert ca.names_map({'X': 'Y', 'Z': ''}) == {'x': 'Y'}


def test_plan_auto_buckets():
    units = [{'name': 'g1', 'rows': [_row('Structure', 'Mechanical')], 'assigned': '', 'open': True},
             {'name': 'g2', 'rows': [_row('Unassigned', 'Mechanical')], 'assigned': '', 'open': True},
             {'name': 'g3', 'rows': [_row('Plumbing', 'Electrical')], 'assigned': 'Bob', 'open': True},
             {'name': 'g4', 'rows': [_row('Plumbing', 'Electrical', 'Resolved')], 'assigned': '',
              'open': False}]
    planned = ca.plan_auto(units, P, {'mechanical': 'J. Smith'})
    assert [(u['name'], n) for u, n in planned['assign']] == [('g1', 'J. Smith')]
    assert [u['name'] for u in planned['undecided']] == ['g2']
    assert [u['name'] for u in planned['kept']] == ['g3']
    assert [u['name'] for u in planned['closed']] == ['g4']
    again = ca.plan_auto(units, P, {}, reassign=True)
    assert [(u['name'], n) for u, n in again['assign']] == [('g1', 'Mechanical'), ('g3', 'Electrical')]
    text = ca.confirm_text(planned)
    assert text.startswith('Assign 1 item:') and 'J. Smith: 1' in text
    assert 'could not be decided' in text and 'left alone' in text


def test_ownership_takes_latest_change():
    r1 = ca.new_record([['T', 'g1', 'G1', 'group', '', 'Mechanical']], 'amol', 'auto',
                       datetime.datetime(2026, 9, 1, 8, 0, 0))
    r2 = ca.new_record([['T', 'g1', 'G1', 'group', 'Mechanical', 'Plumbing'],
                        ['T', 'c9', 'Clash9', 'clash', '', 'Electrical']], 'kim', 'manual',
                       datetime.datetime(2026, 9, 20, 9, 30, 0))
    assert r1['id'].startswith('bic-20260901-080000-')
    owners = ca.ownership([r2, r1, 'junk'])
    assert owners['g1']['to'] == 'Plumbing' and owners['g1']['since'] == '2026-09-20T09:30:00'
    assert owners['g1']['by'] == 'kim'
    assert owners['c9']['from'] == ''


def test_dashboard_numbers():
    units = [{'guid': 'g1', 'name': 'G1', 'test': 'T', 'assigned': 'Plumbing', 'open': True,
              'rows': [_row('a', 'b', created='2026-08-01T00:00:00'), _row('a', 'b', 'Resolved')]},
             {'guid': 'g2', 'name': 'G2', 'test': 'T', 'assigned': 'Plumbing', 'open': True,
              'rows': [_row('a', 'b', created='2026-10-01T00:00:00')]},
             {'guid': 'c3', 'name': 'C3', 'test': 'T', 'assigned': '', 'open': True,
              'rows': [_row('a', 'b', created='2026-09-20T00:00:00')]},
             {'guid': 'c4', 'name': 'C4', 'test': 'T', 'assigned': 'X', 'open': False,
              'rows': [_row('a', 'b', 'Approved')]}]
    owners = {'g1': {'to': 'Plumbing', 'since': '2026-09-20T09:30:00'},
              'g2': {'to': 'Someone else', 'since': '2026-09-01T00:00:00'}}
    board = ca.dashboard(units, owners, TODAY)
    assert board['open'] == 3 and board['clashes'] == 3
    first = board['by_assignee'][0]
    assert first['assignee'] == 'Plumbing' and first['items'] == 2 and first['clashes'] == 2
    assert first['oldest'] == 65 and _compat.approx(first['average'], 34.5)
    assert first['buckets'] == [1, 0, 0, 1]
    assert board['by_assignee'][1]['assignee'] == 'Not assigned'
    assert [r['unit']['name'] for r in board['oldest']] == ['G1', 'C3', 'G2']
    assert board['oldest'][0]['held'] == 15
    assert board['oldest'][2]['held'] is None


def test_unit_cells():
    unit = {'test': 'T', 'name': 'G', 'kind': 'group', 'rows': [_row('Mechanical', 'Structure')],
            'status': 'New', 'assigned': ''}
    assert ca.unit_cells(unit) == ['T', 'G', 'Group', 1, 'New', '', 'Mechanical / Structure']


def test_units_assign_and_history_through_fakes():
    folder = _compat.tmpdir('clashassign')
    previous = paths.redirect(folder)
    try:
        doc, test = cf.clash_doc()
        with cf.ClashNav(doc) as fake:
            entry = cn.read_test(test, doc)
            units = ca.units_of(entry)
            assert [(u['kind'], u['name'], len(u['rows'])) for u in units] == [
                ('clash', 'Clash1', 1), ('group', 'Group 1', 2)]
            changes = ca.assign([(units[1], 'Mechanical'), (units[0], 'Plumbing')], doc)
            assert doc.transactions[0] == 'Assign clashes'
            assert [c[0] for c in fake.data.calls if c[0] == 'assigned'] == ['assigned', 'assigned']
            assert changes == [['Ducts vs Walls', units[1]['guid'], 'Group 1', 'group', '', 'Mechanical'],
                               ['Ducts vs Walls', units[0]['guid'], 'Clash1', 'clash', '', 'Plumbing']]
            fake.Api.Assignee  # the fake layer has an Assignee
    finally:
        paths.redirect(previous)


def test_history_store_local_fallback_round_trip():
    folder = _compat.tmpdir('clashassign-history')
    previous = paths.redirect(folder)
    try:
        from namo import store
        records = store.RecordStore(ca.STORE, doc_path=r'C:\P\Hospital.nwf', mode='local')
        records.put(ca.new_record([['T', 'g1', 'G1', 'group', '', 'Mechanical']], 'amol', 'auto',
                                  datetime.datetime(2026, 9, 1, 8, 0, 0)))
        owners = ca.ownership(records.list())
        assert owners['g1']['to'] == 'Mechanical'
    finally:
        paths.redirect(previous)


def test_ownership_is_also_found_by_name():
    # A rebuilt test may hand its results new ids: held days must survive that.
    record = ca.new_record([['T', 'old-guid', 'G1', 'group', '', 'Mechanical']], 'amol', 'auto',
                           datetime.datetime(2026, 9, 1, 8, 0, 0))
    owners = ca.ownership([record])
    unit = {'guid': 'new-guid', 'test': 'T', 'name': 'G1', 'assigned': 'Mechanical', 'rows': []}
    assert ca.held_days(unit, owners, datetime.datetime(2026, 9, 11, 8, 0, 0)) == 10
    assert ca.held_days(dict(unit, name='Other'), owners, datetime.datetime(2026, 9, 11)) is None


def test_assign_many_units_rebuilds_the_test_once():
    # Regression: Auto mode wrote one document edit per unit however many there were.
    from namo import clashname
    doc, test = cf.clash_doc()
    with cf.ClashNav(doc) as fake:
        entry = clashname.read_test(test, doc)
        units = ca.units_of(entry)
        changes = ca.assign([(units[0], 'Plumbing'), (units[1], 'Mechanical')], doc, limit=1)
        assert [c[0] for c in fake.data.calls if c[0] == 'assigned'] == []
        assert [c for c in fake.data.calls if c[0] == 'replace'] == [('replace', 0, 'Ducts vs Walls')]
        assert doc.transactions == []          # one bare swap, as Clash Grouper commits
        fresh = doc.clash_tests[0]
        assert fresh.Children[0].AssignedTo.DisplayName == 'Plumbing'
        group = fresh.Children[1]
        assert group.AssignedTo.DisplayName == 'Mechanical'
        assert group.Children[0].AssignedTo.DisplayName == 'Mechanical'
        assert group.Children[1].Children[0].AssignedTo.DisplayName == 'Mechanical'
        assert [c.Body for c in group.Comments] == ['keep me']
        assert [c[5] for c in changes] == ['Plumbing', 'Mechanical']
        assert units[0]['assigned'] == 'Plumbing'
