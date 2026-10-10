# -*- coding: utf-8 -*-
"""namo.fourd_attach: Auto Attach rule text, matching, rendering and the object index."""
import _compat
from namo import fourd_attach as fa
from namo.items import Cancelled


def test_parse_rule_forms():
    rule = fa.parse_rule('Name ~ L(?P<level>\\d+) (?P<trade>\\w+) => Element > Level = Level {level} '
                         '& Item > Layer contains {trade}')
    assert rule['field'] == 'name' and rule['op'] == 'regex'
    assert rule['conditions'] == ['Element > Level = Level {level}', 'Item > Layer contains {trade}']
    assert rule['sets'] == []
    rule = fa.parse_rule('Task ID starts with 1.2 => set "Structure/Slabs"')
    assert rule['field'] == 'id' and rule['op'] == 'starts_with' and rule['sets'] == ['Structure/Slabs']
    rule = fa.parse_rule('User3 = MEP => sets Services/{name} & Element > Category = Ducts')
    assert rule['field'] == 'user3' and rule['sets'] == ['Services/{name}']
    assert fa.parse_rule('   ') is None and fa.parse_rule('# note') is None
    assert fa.parse_rule('Type is Demolish => set Demo')['op'] == 'equals'
    assert fa.parse_rule('Name like L? slab => set S')['op'] == 'wildcard'


def test_parse_rule_errors():
    cases = [
        ('Name contains A', 'A rule needs "=>"'),
        ('Name contains A =>', 'Nothing to attach'),
        ('Colour = red => set X', 'Start with a task field'),
        ('Name banana => set X', 'Use an operator'),
        ('Name contains => set X', 'no pattern'),
        ('Name ~ L(?P<lvl => set X', 'The pattern does not read'),
        ('Name ~ L(?P<lvl>\\d) => set Level {level}', '{level} is not a group'),
        ('Name contains A => Element > Category', 'No comparison found'),
    ]
    for line, start in cases:
        error = _compat.raises(ValueError, fa.parse_rule, line)
        assert start in str(error), (line, str(error))
    rules_, errors = fa.parse_rules('Name contains A => set X\n\nbad line\n# ok\nName = B => set Y')
    assert [r['line'] for r in rules_] == [1, 5]
    assert errors[0][0] == 3


def _row(name, id_='', user=None, children=False, type_=''):
    return {'name': name, 'id': id_, 'type': type_, 'user': user or [''] * 10, 'has_children': children}


def test_match_and_render():
    rule = fa.parse_rule('Name ~ L(?P<level>\\d+) (?P<trade>\\w+) => Element > Level = Level {level} '
                         '& Item > Layer contains {trade}')
    captures = fa.match(rule, fa.task_values(_row('Install L3 Ducts')))
    assert captures['level'] == '3' and captures['trade'] == 'Ducts' and captures['name'] == 'Install L3 Ducts'
    targets = fa.render(rule, captures)
    assert targets['conditions'][0]['value'] == 'Level 3'
    assert targets['conditions'][1] == {'category': 'Item', 'property': 'Layer', 'op': 'contains',
                                        'value': 'Ducts', 'ignore_case': True}
    assert fa.match(rule, fa.task_values(_row('Paint walls'))) is None
    contains = fa.parse_rule('Name contains slab => set Structure/{id}')
    values = fa.task_values(_row('L2 SLAB pour', '7.1'))
    assert fa.render(contains, fa.match(contains, values)) == {'sets': ['Structure/7.1'], 'conditions': []}
    equals = fa.parse_rule('User2 = mep => set S')
    assert fa.match(equals, fa.task_values(_row('x', user=['', 'MEP'] + [''] * 8))) is not None
    like = fa.parse_rule('Name like L? slab => set S')
    assert fa.match(like, fa.task_values(_row('L4 Slab'))) is not None
    assert fa.match(like, fa.task_values(_row('L14 Slab'))) is None


def test_plan_first_rule_wins_and_leaf_only():
    rules_, errors = fa.parse_rules('Name contains slab => set Slabs\nName contains L2 => set Level 2\n'
                                    'Name ~ (?P<x>Z) => Element > {x} = 1 = 2')
    assert errors == []
    rows = [_row('Level 2', children=True), _row('L2 slab'), _row('L2 walls'), _row('Roof'), _row('Z')]
    entries = fa.plan(rows, rules_)
    assert [e['index'] for e in entries] == [1, 2, 3, 4]
    assert entries[0]['targets']['sets'] == ['Slabs']
    assert entries[1]['targets']['sets'] == ['Level 2']
    assert entries[2]['rule'] is None
    assert entries[3]['error'] is not None or entries[3]['targets'] is not None
    assert len(fa.plan(rows, rules_, leaf_only=False)) == 5


def _objects():
    return [
        {'n': 'duct 1', ('Element', 'Level'): 'Level 3', ('Element', 'Category'): 'Ducts', ('', 'Mark'): 'D1'},
        {'n': 'duct 2', ('Element', 'Level'): 'Level 4', ('Element', 'Category'): 'Ducts'},
        {'n': 'pipe', ('Element', 'Level'): 'level 3', ('Element', 'Category'): 'Pipes', ('', 'Mark'): 'P1'},
        {'n': 'wall', ('Element', 'Level'): 'Level 3', ('Element', 'Category'): 'Walls',
         ('Element', 'Height'): 3.0},
        {'n': 'nothing'},
    ]


def _reader(calls):
    def read(obj, pairs):
        calls.append(len(pairs))
        out = {}
        for pair in pairs:
            if pair in obj:
                out[pair] = (True, obj[pair])
        return out
    return read


def test_object_index_reads_each_pair_once_and_finds():
    from namo import rules
    calls = []
    index = fa.ObjectIndex(_objects(), _reader(calls))
    level3 = rules.parse_cell('Element > Level = Level 3')
    ducts = rules.parse_cell('Element > Category = Ducts')
    index.prepare([[level3, ducts]])
    assert calls == [2] * 5
    assert [o['n'] for o in index.find([level3])] == ['duct 1', 'pipe', 'wall']
    assert [o['n'] for o in index.find([level3, ducts])] == ['duct 1']
    tall = rules.parse_cell('Element > Height >= 2.5')
    assert [o['n'] for o in index.find([tall])] == ['wall']
    assert calls == [2] * 5 + [1] * 5            # a new pair reads once more, only that pair
    mark = rules.parse_cell('Mark exists')
    assert [o['n'] for o in index.find([mark])] == ['duct 1', 'pipe']
    case = rules.parse_cell('Element > Level = Level 3 (match case)')
    assert [o['n'] for o in index.find([case])] == ['duct 1', 'wall']
    assert index.find([]) == []
    assert fa.condition_key(level3) in index.cache


def test_object_index_cancel():
    index = fa.ObjectIndex([{} for _ in range(450)], lambda obj, pairs: {})
    from namo import rules
    cond = rules.parse_cell('A > B = 1')
    _compat.raises(Cancelled, index.prepare, [[cond]], lambda done, total: False)
    seen = []
    index.prepare([[cond]], lambda done, total: seen.append((done, total)))
    assert seen == [(200, 450), (400, 450)]
