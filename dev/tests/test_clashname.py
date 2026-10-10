# -*- coding: utf-8 -*-
"""namo.clashname: token values, planning, preview, the results tree, and both write
modes (per-item edits and the rebuild + TestsReplaceWithCopy) through the fakes."""
import _compat
import test_clashset_tests as cf

from namo import clashname as cn
from namo import paths

nav = cf.nav            # one generation of the fake classes (see cf.clash_doc)
_clash_doc = cf.clash_doc


def _row(i, name, **kw):
    row = {'id': i, 'name': name, 'test': 'T', 'grid': 'C-4', 'level': 'L2', 'model_a': 'MEP.nwc',
           'model_b': 'STR.nwc', 'trade_a': 'Mechanical', 'trade_b': 'Structure', 'status': 'New',
           'distance': -0.0384, 'group': None, 'assigned': '', 'item_a_name': 'Duct',
           'item_b_name': 'Beam'}
    row.update(kw)
    return row


def test_dominant_and_tidy():
    assert cn.dominant(['B', 'a', 'B', None, '', 'a', 'Level 10', 'Level 2']) == 'a'
    assert cn.dominant(['Level 10', 'Level 2']) == 'Level 2'
    assert cn.dominant([None, '']) == ''
    assert cn.tidy('  A \n B  ') == 'A B'
    assert len(cn.tidy('x' * 400)) == cn.MAX_NAME


def test_clash_and_group_values():
    values = cn.clash_values(_row(0, 'Clash1'), 'Meters', ('Ducts', 'Structural Framing'))
    assert values['distance'] == '-0.038 m'
    assert values['cat_a'] == 'Ducts' and values['item_b'] == 'Beam'
    rows = [_row(0, 'a', grid='C-4', distance=-0.01), _row(1, 'b', grid='D-5', distance=-0.05),
            _row(2, 'c', grid='C-4', distance=None)]
    group = cn.group_values('G1', rows, 'Millimeters', 'T')
    assert group['count'] == 3 and group['grid'] == 'C-4' and group['distance'] == '-0.1 mm'
    assert cn.group_values('G', [], 'Meters')['distance'] == ''


def test_tokens_checks():
    assert cn.needs_categories('{test} {cat_a}')
    assert not cn.needs_categories('{test} {n:000}', '')
    assert cn.unknown_tokens('{test} {date:%Y} {bogus} {CAT_A}', cn.CLASH_TOKENS) == ['bogus']


def test_plan_test_renames_only_changes_and_counts_per_test():
    rows = [_row(0, 'T 001'), _row(1, 'old'), _row(2, 'old2')]
    groups = [{'gid': 0, 'name': 'Group 1', 'ids': [1, 2]}]
    plan = cn.plan_test('T', rows, groups, '{test} {n:000}', '{grid} x{count}', 'both', 'Meters')
    assert plan['clashes'] == [(1, 'old', 'T 002'), (2, 'old2', 'T 003')]
    assert plan['groups'] == [(0, 'Group 1', 'C-4 x2')]
    assert plan['unchanged'] == 1 and plan['considered'] == 4
    only_groups = cn.plan_test('T', rows, groups, '{test}', '{level}', 'groups', 'Meters')
    assert only_groups['clashes'] == [] and only_groups['groups'] == [(0, 'Group 1', 'L2')]
    limited = cn.plan_test('T', rows, groups, 'X{n}', '', 'clashes', 'Meters', limit=2)
    assert len(limited['clashes']) == 2


def test_plan_test_uses_categories_only_when_asked():
    calls = []

    def cats(row):
        calls.append(row['id'])
        return ('Ducts', 'Walls')
    rows = [_row(0, 'a')]
    plan = cn.plan_test('T', rows, [], '{cat_a} vs {cat_b}', '', 'clashes', 'Meters', cats)
    assert plan['clashes'][0][2] == 'Ducts vs Walls' and calls == [0]
    cn.plan_test('T', rows, [], '{test}', '', 'clashes', 'Meters', cats)
    assert calls == [0]


def test_preview_statuses():
    entries = [{'name': 'T', 'rows': [_row(0, 'a'), _row(1, 'b')],
                'specs': [{'gid': 0, 'name': 'G', 'ids': [0, 1]}]}]
    rows, status, ok = cn.preview(entries, '{test} {n}', '{grid}', 'both', 'Meters')
    assert ok and status == 'Renames 2 clashes and 1 group in 1 test'
    assert rows[0] == ['T', 'Group', 'G', 'C-4'] and rows[1] == ['T', 'Clash', 'a', 'T 1']
    rows, status, ok = cn.preview(entries, '{bogus}', '', 'clashes', 'Meters')
    assert not ok and status.startswith('{bogus} is not a token')
    rows, status, ok = cn.preview(entries, '', '{grid}', 'clashes', 'Meters')
    assert not ok and status == 'Enter a name template for clashes.'
    same = [{'name': 'T', 'rows': [_row(0, 'T 1')], 'specs': []}]
    rows, status, ok = cn.preview(same, '{test} {n}', '', 'clashes', 'Meters')
    assert not ok and status == 'Every name already matches this template.'
    rows, status, ok = cn.preview(same, '{test}', '{grid}', 'groups', 'Meters')
    assert not ok and status == 'These tests have no result groups.'


def test_preview_large_shows_first_rows_only():
    big = [{'name': 'T', 'rows': [_row(i, 'x%d' % i) for i in range(cn.FULL_PREVIEW + 5)], 'specs': []}]
    rows, status, ok = cn.preview(big, 'C{n}', '', 'clashes', 'Meters')
    assert ok and len(rows) == cn.PREVIEW_ROWS
    assert status.startswith('Showing the first 25 of {:,} names'.format(cn.FULL_PREVIEW + 5))


def test_result_and_summary_text():
    assert cn.result_text(1240, 0, 3) == 'Renamed 1,240 clashes in 3 tests'
    assert cn.result_text(1, 2, 1) == 'Renamed 1 clash and 2 groups in 1 test'
    assert cn.summary_text({'clashes': 0, 'groups': 5}, 2) == 'Renames 5 groups in 2 tests'


class _Leaf(object):
    def __init__(self, name):
        self.name = name


class _Group(object):
    def __init__(self, name, children):
        self.name = name
        self.children = children


def _walk(items):
    return cn.walk_tree(items, lambda x: isinstance(x, _Group), lambda x: isinstance(x, _Leaf),
                        lambda x: x.children)


def test_walk_tree_specs_and_touched():
    tree = [_Leaf('r0'), _Group('g0', [_Leaf('r1'), _Group('g1', [_Leaf('r2')])]), _Leaf('r3'),
            _Group('g2', [_Leaf('r4')])]
    nodes, leaves, groups = _walk(tree)
    assert [l.name for l in leaves] == ['r0', 'r1', 'r2', 'r3', 'r4']
    assert [g.name for g in groups] == ['g0', 'g1', 'g2']
    specs = cn.group_specs(nodes)
    assert specs == [{'gid': 0, 'ids': [1, 2]}, {'gid': 1, 'ids': [2]}, {'gid': 2, 'ids': [4]}]
    assert cn.touched_groups(nodes, {2: 'x'}, {}) == set([0, 1])
    assert cn.touched_groups(nodes, {}, {2: 'y'}) == set([2])
    assert cn.touched_groups(nodes, {0: 'z'}, {}) == set()


def _read(doc, test):
    entry = cn.read_test(test, doc)
    return entry


def test_read_and_apply_by_edits():
    folder = _compat.tmpdir('clashname-edit')
    previous = paths.redirect(folder)
    try:
        doc, test = _clash_doc()
        with cf.ClashNav(doc) as fake:
            entry = _read(doc, test)
            assert [r['name'] for r in entry['rows']] == ['Clash1', 'Clash2', 'Clash3']
            assert [s['name'] for s in entry['specs']] == ['Group 1', 'Inner']
            plans = cn.plan_all([entry], 'DW {n:00}', 'Group {n}', 'both', 'Meters')
            result = cn.apply([entry], plans, threshold=100, doc=doc)
            assert result == {'clashes': 3, 'groups': 1, 'tests': 1, 'mode': 'edit'}
            renames = [c for c in fake.data.calls if c[0] == 'rename']
            assert [c[2] for c in renames] == ['Group 2', 'DW 01', 'DW 02', 'DW 03']
            assert doc.transactions == ['Rename clashes']
    finally:
        paths.redirect(previous)


def test_apply_by_rebuild_keeps_structure_and_comments():
    folder = _compat.tmpdir('clashname-rebuild')
    previous = paths.redirect(folder)
    try:
        doc, test = _clash_doc()
        with cf.ClashNav(doc) as fake:
            entry = _read(doc, test)
            plans = cn.plan_all([entry], '{test} {n:000}', '', 'clashes', 'Meters')
            result = cn.apply([entry], plans, threshold=1, doc=doc)
            assert result['mode'] == 'rebuild'
            assert getattr(test, 'dead', False)
            fresh = doc.clash_tests[0]
            assert str(fresh.Guid) == str(test.Guid) and fresh is not test
            assert fresh.Children[0].DisplayName == 'Ducts vs Walls 001'
            group = fresh.Children[1]
            assert group.DisplayName == 'Group 1'
            assert [c.Body for c in group.Comments] == ['keep me']
            assert group.Children[0].DisplayName == 'Ducts vs Walls 002'
            assert group.Children[1].DisplayName == 'Inner'
            assert group.Children[1].Children[0].DisplayName == 'Ducts vs Walls 003'
            assert [c for c in fake.data.calls if c[0] == 'replace'] == [('replace', 0, 'Ducts vs Walls')]
    finally:
        paths.redirect(previous)


def test_rebuild_copies_untouched_groups_whole():
    doc, test = _clash_doc()
    with cf.ClashNav(doc):
        entry = {'test': test, 'nodes': None}
        nodes, leaves, groups = cn.walk_tree(
            test.Children, lambda x: isinstance(x, nav.ClashResultGroup),
            lambda x: isinstance(x, nav.ClashResult), lambda x: x.Children)
        entry.update({'nodes': nodes, 'leaves': leaves, 'groups': groups})
        new_test = cn.rebuild(entry, {0: 'Only first'}, {})
        assert new_test.Children[0].DisplayName == 'Only first'
        assert new_test.Children[1].DisplayName == 'Group 1'
        assert [c.DisplayName for c in new_test.Children[1].Children] == ['Clash2', 'Inner']


def test_threshold_defaults_low_and_forgets_the_old_default():
    # Regression: the first build renamed up to 3,000 clashes one document edit at a
    # time; pyNavis measured such edits at ~170 ms each on a big model.
    assert cn.DEFAULT_THRESHOLD <= 200
    assert cn.threshold_of({}) == cn.DEFAULT_THRESHOLD
    assert cn.threshold_of({'threshold': 3000}) == cn.DEFAULT_THRESHOLD
    assert cn.threshold_of({'threshold': 0}) == cn.DEFAULT_THRESHOLD
    assert cn.threshold_of({'threshold': 'x'}) == cn.DEFAULT_THRESHOLD
    assert cn.threshold_of({'threshold': 50}) == 50
    assert cn.threshold_of({'threshold': 100000}) == 100000
