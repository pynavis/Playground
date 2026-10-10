# -*- coding: utf-8 -*-
"""namo.clashrules: the condition language, evaluation, first-match planning, the
shipped examples, and the writer (status, assignee restore, comments) through fakes."""
import datetime

import _compat
import test_clashset_tests as cf

from namo import clashrules as cr

nav = cf.nav

TODAY = datetime.datetime(2026, 10, 5)


def _row(i, **kw):
    row = {'id': i, 'name': 'Clash%d' % (i + 1), 'test': 'T', 'status': 'New', 'distance': -0.002,
           'distance_m': -0.002, 'created': '2026-09-01T08:00:00', 'model_a': 'MEP.nwc',
           'model_b': 'STR.nwc', 'trade_a': 'Mechanical', 'trade_b': 'Structure', 'grid': 'C-4',
           'level': 'L2', 'assigned': '', 'group': None, 'item_a_name': 'Duct', 'item_b_name': 'Beam',
           'item_a': 'ka%d' % i, 'item_b': 'kb%d' % i, 'comments': 0, 'priority': 3,
           'description': ''}
    row.update(kw)
    return row


def test_compile_length_conditions_to_metres():
    c = cr.compile_condition('depth < 3 mm', 'Feet')
    assert c['field'] == 'depth' and c['op'] == 'lt' and _compat.approx(c['value'], 0.003)
    c = cr.compile_condition('Depth <= 1/8"', 'Feet')
    assert _compat.approx(c['value'], 0.003175)
    c = cr.compile_condition('distance between -5mm and 0', 'Millimeters')
    assert _compat.approx(c['value'], [-0.005, 0.0])
    c = cr.compile_condition('depth between 1 and 5 mm', 'Meters')
    assert _compat.approx(c['value'], [0.001, 0.005])
    c = cr.compile_condition('gap > 2', 'Millimeters')
    assert _compat.approx(c['value'], 0.002)


def test_compile_other_fields():
    assert cr.compile_condition('age > 30', 'Meters')['field'] == 'age'
    assert cr.compile_condition('Trade pair = Structure / Mechanical', 'Meters')['value'] == \
        'mechanical|structure'
    pairs = cr.compile_condition('trades is one of A / B; C vs D', 'Meters')['value']
    assert pairs == ['a|b', 'c|d']
    side = cr.compile_condition('Either: Element > Category = Ducts', 'Meters')
    assert side['side'] == 'either' and side['category'] == 'Element'
    assert cr.compile_condition('status is one of new, Active', 'Meters')['op'] == 'in_list'
    assert cr.compile_condition('same model = yes', 'Meters')['field'] == 'same_model'


def test_compile_errors_are_sentences():
    for line, words in (('colour = red', 'not a clash field'),
                        ('depth < three', 'not a length'),
                        ('status = Done', 'not a status'),
                        ('trade pair = Mechanical / Structure / Electrical', 'write a pair'),
                        ('A: Category = Ducts', 'needs a category'),
                        ('age > old', 'has no comparison'),
                        ('age >= x', 'needs a number')):
        error = _compat.raises(ValueError, cr.compile_condition, line, 'Meters')
        assert words in str(error), (line, str(error))


def test_compile_rule_problems():
    rule, problems = cr.compile_rule({'name': 'R', 'conditions': ['depth < 3mm'], 'status': ''},
                                     'Meters')
    assert problems == ['R changes nothing: set a status, an assignee or a note.']
    rule, problems = cr.compile_rule({'name': 'R', 'conditions': [], 'status': 'Approved'}, 'Meters')
    assert problems == ['R has no conditions.']
    rule, problems = cr.compile_rule({'conditions': 'A: Element > Category = Ducts\nage > 3',
                                      'status': 'active'}, 'Meters')
    assert problems == [] and rule['needs_live'] and rule['status'] == 'Active'


def test_examples_compile_cleanly():
    for rule in cr.EXAMPLE_RULES:
        _compiled, problems = cr.compile_rule(rule, 'Millimeters')
        assert problems == [], problems
        _compiled, problems = cr.compile_rule(rule, 'Feet')
        assert problems == [], problems


def test_field_values():
    row = _row(0, distance_m=-0.004, model_b='mep.NWC', trade_b='mechanical')
    assert cr.field_value(row, 'depth') == (True, 0.004)
    assert cr.field_value(row, 'distance') == (True, -0.004)
    assert cr.field_value(row, 'age', TODAY) == (True, 34)
    assert cr.field_value(row, 'same_model') == (True, True)
    assert cr.field_value(row, 'same_trade') == (True, True)
    assert cr.field_value(row, 'trade_pair') == (True, 'mechanical|mechanical')
    assert cr.field_value(_row(0, distance_m=None), 'depth') == (False, None)
    assert cr.field_value(_row(0, created=None), 'age', TODAY) == (False, None)


def test_condition_holds_with_reader_and_sides():
    def reader(row, side, category, prop):
        if prop == 'category':
            return True, 'Ducts' if side == 'a' else 'Walls'
        return (True, 'Supply') if side == 'b' else (False, None)
    row = _row(0)
    holds = cr.condition_holds
    assert holds(cr.compile_condition('B: Mechanical > System = Supply', 'Meters'), row, TODAY, reader)
    assert not holds(cr.compile_condition('A: Mechanical > System = Supply', 'Meters'), row, TODAY, reader)
    assert holds(cr.compile_condition('Either: Mechanical > System = Supply', 'Meters'), row, TODAY, reader)
    assert not holds(cr.compile_condition('Both: Mechanical > System = Supply', 'Meters'), row, TODAY, reader)
    assert holds(cr.compile_condition('category a = ducts', 'Meters'), row, TODAY, reader)
    assert not holds(cr.compile_condition('category a = ducts', 'Meters'), row, TODAY, None)
    assert holds(cr.compile_condition('trade pair contains structure', 'Meters'), row, TODAY)
    assert holds(cr.compile_condition('trade pair = Structure / Mechanical', 'Meters'), row, TODAY)


def test_first_match_and_plan():
    rules_list = [{'name': 'Tiny', 'conditions': ['depth < 3 mm'], 'status': 'Approved'},
                  {'name': 'Ducts', 'conditions': ['trade a = Mechanical'], 'assign': '{trade_a}',
                   'note': 'Moves: {item_a} at {distance}'},
                  {'name': 'Off', 'enabled': False, 'conditions': ['age > 1'], 'status': 'Resolved'}]
    compiled = [cr.compile_rule(r, 'Meters')[0] for r in rules_list]
    rows = {'T2': [_row(0, distance_m=-0.001, distance=-0.001),
                   _row(1, distance_m=-0.01, distance=-0.01),
                   _row(2, distance_m=-0.01, trade_a='Electrical'),
                   _row(3, distance_m=-0.002, status='Approved')],
            'T10': [_row(0, distance_m=-0.05, assigned='Mechanical')]}
    planned = cr.plan(rows, compiled, 'Meters', TODAY)
    assert [c['matched'] for c in planned['counts']] == [2, 2, 0]
    assert [c['changed'] for c in planned['counts']] == [1, 2, 0]
    assert planned['total'] == 5 and planned['matched'] == 4 and planned['changed'] == 3
    changes = planned['changes']['T2']
    assert changes[0] == {'id': 0, 'rule': 0, 'status': 'Approved', 'assign': None, 'note': ''}
    assert changes[1]['assign'] == 'Mechanical' and changes[1]['note'] == 'Moves: Duct at -0.01 m'
    assert planned['changes']['T10'][0]['assign'] is None
    assert cr.summary_text(planned) == '4 of 5 clashes match a rule; 3 will change.'


def test_describe_and_form_validation():
    when, then = cr.describe_rule({'name': 'R', 'mode': 'any', 'conditions': ['a = 1', 'b = 2'],
                                   'status': 'Active', 'note': 'x'})
    assert when == 'a = 1 or b = 2' and then == 'Status Active, Note'
    errors = cr.validate_form({'name': 'R', 'conditions': 'depth < x', 'status': 'Active'}, 'Meters')
    assert 'conditions' in errors and 'not a length' in errors['conditions']
    errors = cr.validate_form({'name': 'R', 'conditions': 'depth < 3mm', 'status': ''}, 'Meters')
    assert 'status' in errors
    fields = cr.rule_form_fields(cr.EXAMPLE_RULES[0])
    assert [f['key'] for f in fields] == ['name', 'conditions', 'mode', 'status', 'assign', 'note',
                                          'enabled']


def test_canonical_pair():
    assert cr.canonical_pair('Structure / Mechanical') == 'mechanical|structure'
    assert cr.canonical_pair('A vs B') == 'a|b'
    assert cr.canonical_pair('Ducts') == 'ducts|ducts'
    assert cr.canonical_pair('A / B / C') == ''


def test_apply_writes_status_restores_assignee_and_comments():
    doc, named = cf.new_doc()
    results = [cf.Result('Clash1'), cf.Result('Clash2')]
    results[0].AssignedTo = nav.Assignee('Mechanical')
    test = cf.ClashTest('T', results)
    doc.clash_tests.append(test)

    class Clobbering(cf.FakeClashData):
        def TestsEditResultStatus(self, result, status, who):
            cf.FakeClashData.TestsEditResultStatus(self, result, status, who)
            result.AssignedTo = who            # the behaviour pynavis assumes

    doc.clash_data = Clobbering(doc)
    planned = {'changes': {'T': [{'id': 0, 'rule': 0, 'status': 'Approved', 'assign': None,
                                  'note': 'Auto'},
                                 {'id': 1, 'rule': 0, 'status': None, 'assign': 'Electrical',
                                  'note': ''}]}}
    with cf.ClashNav(doc) as fake:
        totals = cr.apply({'T': {'leaves': results, 'test': test}}, planned, doc)
        assert totals == {'status': 1, 'assign': 1, 'notes': 1, 'tests': 1, 'restored': 1,
                          'mode': 'edit'}
        assert results[0].AssignedTo.DisplayName == 'Mechanical'
        assert [c.Body for c in results[0].Comments] == ['first', 'Auto']
        assert results[1].AssignedTo.DisplayName == 'Electrical'
        assert doc.transactions == ['Status rules']
        status_calls = [c for c in fake.data.calls if c[0] == 'status']
        assert status_calls[0][2] == 'Approved'


def test_apply_is_one_undo_step_across_tests():
    doc, named = cf.new_doc()
    first, second = [cf.Result('Clash1')], [cf.Result('Clash2')]
    test_t, test_u = cf.ClashTest('T', first), cf.ClashTest('U', second)
    doc.clash_tests.extend([test_t, test_u])
    change = {'id': 0, 'rule': 0, 'status': None, 'assign': 'Electrical', 'note': ''}
    planned = {'changes': {'T': [dict(change)], 'U': [dict(change)]}}
    with cf.ClashNav(doc):
        totals = cr.apply({'T': {'leaves': first, 'test': test_t},
                           'U': {'leaves': second, 'test': test_u}}, planned, doc)
        assert totals['tests'] == 2 and totals['assign'] == 2
        assert doc.transactions == ['Status rules']


def test_count_edits():
    planned = {'changes': {'T': [{'id': 0, 'status': 'Approved', 'assign': None, 'note': 'x'},
                                 {'id': 1, 'status': None, 'assign': 'E', 'note': ''}],
                           'U': []}}
    assert cr.count_edits(planned) == 3


def test_apply_many_changes_rebuilds_each_test_once():
    # Regression: Status Rules edited every matching clash in place (up to three
    # document edits per clash); above the limit each test is rebuilt and swapped once.
    doc, test = cf.clash_doc()
    from namo import clashname
    with cf.ClashNav(doc) as fake:
        entry = clashname.read_test(test, doc)
        entry['leaves'][1].AssignedTo = nav.Assignee('Mechanical')
        planned = {'changes': {entry['name']: [
            {'id': 0, 'rule': 0, 'status': 'Approved', 'assign': None, 'note': 'Auto'},
            {'id': 1, 'rule': 0, 'status': 'Resolved', 'assign': None, 'note': ''},
            {'id': 2, 'rule': 0, 'status': None, 'assign': 'Electrical', 'note': ''}]}}
        totals = cr.apply({entry['name']: entry}, planned, doc, limit=1)
        assert totals['mode'] == 'rebuild'
        assert (totals['status'], totals['assign'], totals['notes'], totals['tests']) == (2, 1, 1, 1)
        assert [c[0] for c in fake.data.calls if c[0] in ('status', 'assigned', 'comments')] == []
        assert [c for c in fake.data.calls if c[0] == 'replace'] == [('replace', 0, 'Ducts vs Walls')]
        fresh = doc.clash_tests[0]
        assert fresh is not test and str(fresh.Guid) == str(test.Guid)
        first = fresh.Children[0]
        assert str(first.Status) == 'Approved'
        assert [c.Body for c in first.Comments] == ['first', 'Auto']
        group = fresh.Children[1]
        assert group.DisplayName == 'Group 1' and [c.Body for c in group.Comments] == ['keep me']
        second = group.Children[0]
        assert str(second.Status) == 'Resolved' and second.AssignedTo.DisplayName == 'Mechanical'
        third = group.Children[1].Children[0]
        assert str(third.Status) == 'New' and third.AssignedTo.DisplayName == 'Electrical'
        # one rebuilt test is committed bare, exactly as Clash Grouper does it
        assert doc.transactions == []


def test_several_rebuilt_tests_share_one_undo_step():
    from namo import clashname, clashset_edit
    assert clashset_edit.needs_transaction('edit', 1)
    assert clashset_edit.needs_transaction('rebuild', 2)
    assert not clashset_edit.needs_transaction('rebuild', 1)
    doc, test = cf.clash_doc()
    other = cf.ClashTest('Second', [cf.Result('ClashA')])
    doc.clash_tests.append(other)
    with cf.ClashNav(doc) as fake:
        first, second = clashname.read_test(test, doc), clashname.read_test(other, doc)
        change = {'id': 0, 'rule': 0, 'status': 'Active', 'assign': None, 'note': ''}
        planned = {'changes': {first['name']: [dict(change)], second['name']: [dict(change)]}}
        totals = cr.apply({first['name']: first, second['name']: second}, planned, doc, limit=1)
        assert totals['mode'] == 'rebuild' and totals['tests'] == 2
        assert len([c for c in fake.data.calls if c[0] == 'replace']) == 2
        assert doc.transactions == ['Status rules']
