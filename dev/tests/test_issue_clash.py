# -*- coding: utf-8 -*-
"""namo.issue_clash pure half: who moves, priority bands, due dates, units from snapshot
rows, issue fields and BCF topics for a clash unit."""
import datetime

import _compat

from namo import issue_clash

TODAY = datetime.date(2026, 10, 5)


def _row(guid, status='New', distance=-0.06, trade_a='Mechanical', trade_b='Structure', **extra):
    row = {'guid': guid, 'name': 'Clash%s' % guid, 'status': status, 'distance_m': distance,
           'trade_a': trade_a, 'trade_b': trade_b, 'item_a_name': 'Duct', 'item_b_name': 'Beam',
           'model_a': 'MEP.nwc', 'model_b': 'STR.nwc', 'assigned': '', 'center': (1.0, 2.0, 3.0),
           'grid': 'C-4', 'level': 'Level 2', 'created': '2026-10-01T08:00:00'}
    row.update(extra)
    return row


def test_move_order_and_mover():
    assert issue_clash.move_order('Structure\nMechanical\n\nmechanical') == ['Structure', 'Mechanical']
    assert issue_clash.move_order('A > B > C') == ['A', 'B', 'C']
    assert issue_clash.move_order(['X', ' x ', 'Y']) == ['X', 'Y']
    order = issue_clash.DEFAULT_MOVE_ORDER
    assert issue_clash.mover('Mechanical', 'Structure', order) == 'Mechanical'
    assert issue_clash.mover('Structure', 'Plumbing', order) == 'Plumbing'
    assert issue_clash.mover('Structure', 'Landscape', order) == 'Landscape'   # unlisted moves
    assert issue_clash.mover('Mechanical', 'mechanical', order) == 'Mechanical'
    assert issue_clash.mover('Mechanical', 'Unassigned', order) == ''
    assert issue_clash.mover('Zeta', 'Alpha', order) == 'Alpha'                 # tie: natural order


def test_bands_priority_and_due():
    pairs, bad = issue_clash.parse_bands('0.2 = Critical\n0.05=high\n\nbad line\n0.01 = ??')
    assert pairs == [(0.2, 'Critical'), (0.05, 'High')] and bad == ['bad line', '0.01 = ??']
    assert issue_clash.bands_of('nothing useful') == [tuple(b) for b in issue_clash.DEFAULT_BANDS]
    assert issue_clash.bands_of([[0.01, 'Normal'], [0.3, 'Critical']])[0] == (0.3, 'Critical')
    assert issue_clash.priority_for(-0.25) == 'Critical'
    assert issue_clash.priority_for(-0.06) == 'High'
    assert issue_clash.priority_for(-0.02) == 'Normal'
    assert issue_clash.priority_for(-0.001) == 'Low'
    assert issue_clash.priority_for(0.01) == 'Low'                               # clearance
    assert issue_clash.priority_for(None) == 'Normal'
    assert issue_clash.due_for('High', today=TODAY) == '2026-10-12'
    assert issue_clash.due_for('Low', {'Low': None}, TODAY) == ''
    assert issue_clash.due_for('Critical', today=datetime.datetime(2026, 10, 5, 9)) == '2026-10-08'


def test_build_units_groups_and_singles():
    rows = [_row('a'), _row('b'), _row('c'), _row('d')]
    top_of = {'b': ('G1', 'Duct group'), 'd': ('G1', 'Duct group')}
    units = issue_clash.build_units(rows, top_of)
    assert [(u['kind'], u['guid'], len(u['rows'])) for u in units] == [
        ('clash', 'a', 1), ('group', 'g1', 2), ('clash', 'c', 1)]
    assert issue_clash.wanted(units[0], ['new']) and not issue_clash.wanted(units[0], ['Resolved'])
    units[1]['rows'][1]['distance_m'] = -0.3
    assert issue_clash.worst_row(units[1])['guid'] == 'd'
    assert issue_clash.dominant_pair([_row('x'), _row('y', trade_a='Electrical'), _row('z')]) == \
        ('Mechanical', 'Structure')
    assert issue_clash.source_ref('T1', 'G1') == 't1|g1'


def test_distance_text():
    assert issue_clash.distance_text(-0.045, 'Millimeters') == '45 mm'
    assert issue_clash.distance_text(0.012, 'Meters') == '+12 mm'
    assert issue_clash.distance_text(-0.0254 * 1.75, 'Feet') == '1.8 in'
    assert issue_clash.distance_text(None, 'Feet') == ''


def test_unit_fields_by_rule():
    unit = {'kind': 'group', 'guid': 'g1', 'name': 'Duct group',
            'rows': [_row('a', distance=-0.07), _row('b', distance=-0.21)]}
    fields, values, ref = issue_clash.unit_fields(unit, 'Ducts vs Beams', 'T1', None,
                                                  ['Mechanical', 'Structure'], today=TODAY,
                                                  doc_units='Millimeters')
    assert ref == 't1|g1'
    assert fields['priority'] == 'Critical' and fields['due'] == '2026-10-08'
    assert fields['trade'] == 'Mechanical' and fields['assignee'] == ''
    assert fields['type'] == 'Clash' and fields['labels'] == ['Clash']
    assert fields['location'] == {'point': [1.0, 2.0, 3.0], 'units': 'Millimeters',
                                  'level': 'Level 2', 'grid': 'C-4'}
    assert 'Clash test: Ducts vs Beams' in fields['description']
    assert '2 clashes, deepest 210 mm' in fields['description']
    assert fields['source']['kind'] == 'clash' and fields['source']['clashes'] == 2
    assert values['clash'] == 'Duct group' and values['a'] == 'Duct' and values['test'] == 'Ducts vs Beams'
    person = {'kind': 'clash', 'guid': 'c', 'name': 'Clash9',
              'rows': [_row('c', assigned='Jane Smith')]}
    fields, _v, _r = issue_clash.unit_fields(person, 'T', 't', None, ['Mechanical'], today=TODAY)
    assert fields['assignee'] == 'Jane Smith' and fields['trade'] == 'Mechanical'
    trade = {'kind': 'clash', 'guid': 'd', 'name': 'Clash10', 'rows': [_row('d', assigned='structure')]}
    fields, _v, _r = issue_clash.unit_fields(trade, 'T', 't', None, ['Mechanical', 'Structure'],
                                             today=TODAY)
    assert fields['trade'] == 'Structure' and fields['assignee'] == ''
    undecided = {'kind': 'clash', 'guid': 'e', 'name': 'Clash11',
                 'rows': [_row('e', trade_b='Unassigned', distance=0.004)]}
    fields, _v, _r = issue_clash.unit_fields(undecided, 'T', 't', None, [], today=TODAY)
    assert fields['trade'] == '' and fields['priority'] == 'Low'


def test_topic_for_unit():
    unit = {'kind': 'clash', 'guid': '3f2504e0-4f89-41d3-9a0c-0305e82c3301', 'name': 'Clash1',
            'rows': [_row('3f2504e0-4f89-41d3-9a0c-0305e82c3301', status='Active')]}
    topic = issue_clash.topic_for_unit(unit, 'Ducts vs Beams', 'T1', None, ['Mechanical'], 'amol',
                                       'Meters')
    assert topic['guid'] == '3f2504e0-4f89-41d3-9a0c-0305e82c3301'
    assert topic['type'] == 'Clash' and topic['status'] == 'Open'
    assert topic['title'] == 'Clash1: Duct vs Beam'
    assert topic['labels'] == ['Ducts vs Beams', 'Mechanical']
    assert topic['assigned_to'] == 'Mechanical' and topic['priority'] == 'High'
    resolved = {'kind': 'clash', 'guid': 'x', 'name': 'C', 'rows': [_row('x', status='Resolved')]}
    assert issue_clash.topic_for_unit(resolved, 'T', 't')['status'] == 'Resolved'
    approved = {'kind': 'clash', 'guid': 'y', 'name': 'C', 'rows': [_row('y', status='Approved')]}
    assert issue_clash.topic_for_unit(approved, 'T', 't')['status'] == 'Closed'


def test_who_moves_follows_clash_assigner():
    # Clash to Issues must use Clash Assigner's saved order, never its own copy, so the
    # trade that gets the issue is the trade Clash Assigner would assign.
    from namo import clashassign
    saved = lambda key, defaults: {'priority': ['Mechanical', 'Structure'], 'names': ''}  # noqa: E731
    assert issue_clash.who_moves({'who_moves': ['Electrical', 'Plumbing']}, saved) == \
        ['Mechanical', 'Structure']
    nothing_saved = lambda key, defaults: defaults  # noqa: E731
    assert issue_clash.who_moves({'who_moves': ['Electrical']}, nothing_saved) == \
        list(clashassign.DEFAULT_PRIORITY)
    order = issue_clash.who_moves(None, saved)
    assert issue_clash.mover('Mechanical', 'Structure', order) == 'Structure'
