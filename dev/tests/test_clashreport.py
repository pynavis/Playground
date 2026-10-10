# -*- coding: utf-8 -*-
"""namo.clashreport pure half, plus fake_data(): realistic clash rows every Clash Reports
test builds its reports from (several tests, groups, all statuses, trades, levels, grids,
found dates, assignees, awkward names). Deterministic on both engines (own LCG, no
`random`), so reports built from it are identical under CPython and IronPython."""
import datetime

import _compat
from _compat import approx, raises

from namo import clashreport as cr

TODAY = datetime.datetime(2026, 10, 5)

MODELS = [('Hospital_ARC.nwc', 'Architecture'), ('Hospital_STR.nwc', 'Structure'),
          ('Hospital_MEC.nwc', 'Mechanical'), ('Hospital_PLB.nwc', 'Plumbing'),
          ('Hospital_ELE.nwc', 'Electrical'), ('Hospital_FPS.nwc', 'Fire Protection')]
ELEMENTS = {
    'Architecture': ('Ceilings', ['Compound Ceiling 600x600', 'Basic Wall Interior 138mm', 'Door Single 900']),
    'Structure': ('Structural Framing', ['Beam W310x39', 'Beam UB 406x178', 'Column UC 305x305']),
    'Mechanical': ('Ducts', ['Duct Rectangular 600x400', 'Duct Round 350', 'Flex Duct 200']),
    'Plumbing': ('Pipes', ['Pipe Copper 54mm', 'Pipe PVC 110mm', 'Valve Gate 50']),
    'Electrical': ('Cable Trays', ['Cable Tray 300x50', 'Conduit 25mm', 'Light Fixture & Driver']),
    'Fire Protection': ('Sprinklers', ['Sprinkler Pendent K80', 'Pipe Steel 65mm', 'Sprinkler Main 100']),
}
TESTS = [
    # (name, type, tolerance m, models A, models B, rows, clearance)
    ('Ducts vs Beams', 'Hard', 0.01, [2], [1], 220, False),
    ('Pipes vs Walls', 'Hard', 0.0, [3], [0], 170, False),
    ('Sprinklers vs Ceilings', 'Clearance', 0.025, [5], [0, 4], 140, True),
    ('MEP: Ducts / Trays [L2]', 'Hard (conservative)', 0.005, [2, 3], [4], 70, False),
]
LEVELS = ['Level 1', 'Level 2', 'Level 3', 'Level 4', 'Roof']
GRID_X = 'ABCDEFG'
PEOPLE = ['', '', '', 'Mechanical', 'Jane Smith', 'Structure', 'Raj Patel', 'Plumbing']
STATUS_WHEEL = ['New', 'New', 'New', 'Active', 'Active', 'Active', 'Reviewed', 'Approved', 'Resolved',
                'Resolved']


class Lcg(object):
    """Small deterministic generator: same numbers on every Python."""

    def __init__(self, seed):
        self.state = seed & 0x7FFFFFFF

    def next(self):
        self.state = (1103515245 * self.state + 12345) & 0x7FFFFFFF
        return self.state

    def below(self, n):
        return self.next() % n

    def unit(self):
        return self.next() / float(0x7FFFFFFF)

    def pick(self, seq):
        return seq[self.below(len(seq))]


def fake_rows(seed=11, today=TODAY):
    """{test name: [snapshot-like rows]} (not shaped)."""
    rng = Lcg(seed)
    out = {}
    for t_index, (name, _type, _tol, side_a, side_b, count, clearance) in enumerate(TESTS):
        rows = []
        group_no = 0
        group = None
        group_left = 0
        for i in range(count):
            if group_left <= 0 and rng.below(10) < 4:
                group_no += 1
                group_left = 2 + rng.below(6)
                group = ('G%02d %s %s-%d' % (group_no, rng.pick(LEVELS), rng.pick(GRID_X), 1 + rng.below(9)),
                         'g-%d-%d' % (t_index, group_no))
            in_group = group_left > 0
            group_left -= 1
            model_a, trade_a = MODELS[rng.pick(side_a)]
            model_b, trade_b = MODELS[rng.pick(side_b)]
            element_a = rng.below(40)
            element_b = rng.below(60)
            cat_a, names_a = ELEMENTS[trade_a]
            cat_b, names_b = ELEMENTS[trade_b]
            status = rng.pick(STATUS_WHEEL)
            age = rng.below(75)
            created = today - datetime.timedelta(days=age, hours=rng.below(8))
            level = None if rng.below(25) == 0 else rng.pick(LEVELS)
            grid = None if rng.below(12) == 0 else '%s-%d' % (rng.pick(GRID_X), 1 + rng.below(9))
            if clearance:
                distance = round(rng.unit() * 0.025, 4)
            else:
                distance = -round(0.001 + rng.unit() * 0.18, 4)
            center = (round(rng.unit() * 80, 2), round(rng.unit() * 40, 2), round(rng.unit() * 18, 2))
            approved = status == 'Approved'
            row = {
                'id': i, 'name': 'Clash%d' % (i + 1), 'test': name, 'test_guid': 't-%d' % t_index,
                'guid': 'r-%d-%d' % (t_index, i), 'status': status,
                'distance': distance, 'distance_m': distance, 'center': center, 'center_m': center,
                'item_a': '%s|/0/%d' % (model_a.lower(), element_a),
                'item_b': '%s|/0/%d' % (model_b.lower(), element_b),
                'item_a_name': names_a[element_a % 3], 'item_b_name': names_b[element_b % 3],
                'model_a': model_a, 'model_b': model_b, 'trade_a': trade_a, 'trade_b': trade_b,
                'cat_a': cat_a, 'cat_b': cat_b, 'level': level, 'grid': grid,
                'assigned': rng.pick(PEOPLE), 'group': group[0] if in_group else None,
                'group_guid': group[1] if in_group else None,
                'created': created.strftime('%Y-%m-%dT%H:%M:%S'),
                'approved_time': (created + datetime.timedelta(days=3)).strftime('%Y-%m-%dT%H:%M:%S')
                if approved else None,
                'resolved_time': None, 'approved_by': 'Amol Shah' if approved else '',
                'description': '' if rng.below(3) else 'Raise duct 150 mm',
                'priority': 3, 'comments': rng.below(4),
            }
            rows.append(row)
        out[name] = rows
    # awkward text that every writer must escape or keep
    first = out[TESTS[0][0]][0]
    first['description'] = '<script>alert("x")</script> & move > 50 mm'
    first['item_a_name'] = u'Duct <Supply> & Return ± Café'
    return out


def fake_data(seed=11, today=TODAY, unit='mm', with_ids=True):
    """A clashreport data dict (shaped rows) for four tests, ~600 clashes."""
    rows_by_test = fake_rows(seed, today)
    tests = []
    for name, type_, tol, _a, _b, _count, _clear in TESTS:
        tests.append({'name': name, 'path': 'Coordination/%s' % name if '/' not in name else name,
                      'type': type_, 'state': 'Up to date' if name != 'Pipes vs Walls' else 'Out of date',
                      'tolerance_m': tol, 'last_run': datetime.datetime(2026, 10, 4, 17, 30),
                      'guid': 'guid-' + name, 'rows': cr.shape_rows(rows_by_test[name], unit, today)})
    return {'title': 'Clash report', 'project': 'St Mary Hospital', 'project_number': 'P-1042',
            'company': '', 'file': 'Hospital Coordination', 'doc_title': 'Hospital Coordination',
            'user': 'Amol Shah', 'generated': datetime.datetime(2026, 10, 5, 9, 15),
            'doc_units': 'Millimeters', 'unit': unit, 'trades_order': ['Architecture', 'Structure', 'Mechanical',
                                                                        'Electrical', 'Plumbing', 'Fire Protection'],
            'tests': tests, 'notes': [], 'live': {}}


def cross_engine(name, payload):
    """Cross-engine golden check: CPython stores sha1(payload) under name in a shared temp
    file; IronPython asserts it gets the same digest (skipped when CPython has not run)."""
    import binascii
    import hashlib
    import json
    import os
    import tempfile
    digest = binascii.hexlify(hashlib.sha1(payload).digest()).decode('ascii')
    folder = os.path.join(tempfile.gettempdir(), 'playground-tests')
    if not os.path.isdir(folder):
        os.makedirs(folder)
    path = os.path.join(folder, 'clash_reports-digests.json')
    try:
        with open(path, 'r') as handle:
            known = json.load(handle)
    except Exception:
        known = {}
    if not _compat.IRONPYTHON:
        known[name] = digest
        with open(path, 'w') as handle:
            json.dump(known, handle, indent=2, sort_keys=True)
        return digest
    if name in known:
        assert known[name] == digest, '%s differs between CPython and IronPython' % name
    return digest


# ---- tests --------------------------------------------------------------------------------------


def test_fake_data_is_realistic_and_stable():
    data = fake_data()
    rows = cr.all_rows(data)
    assert len(rows) == 600
    tally = cr.counts(rows)
    assert all(tally['by_status'][s] > 20 for s in cr.STATUSES)
    assert any(r['group'] for r in rows) and any(not r['group'] for r in rows)
    assert any(r['level'] is None for r in rows) and any(r['grid'] is None for r in rows)
    assert fake_data()['tests'][0]['rows'][5] == data['tests'][0]['rows'][5]


def test_status_names_and_open():
    assert cr.status_name('new') == 'New' and cr.status_name(' RESOLVED ') == 'Resolved'
    assert cr.status_name(None) == '' and cr.status_name('Odd') == 'Odd'
    assert cr.is_open('Reviewed') and not cr.is_open('Approved') and not cr.is_open('')
    assert cr.ordered_statuses(['resolved', 'New', 'x']) == ['New', 'Resolved']
    assert cr.ordered_statuses([]) == cr.STATUSES
    assert cr.statuses_text(cr.OPEN) == 'open clashes (New, Active, Reviewed)'
    assert cr.statuses_text(None) == 'all statuses'
    assert cr.statuses_text(['Active', 'New']) == 'New, Active'


def test_units_and_lengths():
    assert cr.report_unit('auto', 'Millimeters') == 'mm'
    assert cr.report_unit('auto', 'Feet') == 'ft'
    assert cr.report_unit('m', 'Feet') == 'm'
    assert cr.report_unit(None, 'Meters') == 'm'
    assert cr.to_unit(-0.0423, 'mm') == -42.3
    assert cr.to_unit(0.3048, 'ft') == 1.0
    assert cr.to_unit(None, 'mm') is None
    assert cr.to_unit(-0.00001, 'mm') == 0.0
    assert cr.number_text(-1234.56, 'mm') == '-1,234.6'
    assert cr.number_text(-0.01, 'mm') == '0.0'
    assert cr.length_text(0.01, 'mm') == '10 mm'
    assert cr.length_text(0.025, 'm') == '0.025 m'
    assert cr.length_text(0.0, 'mm') == '0 mm'
    assert cr.length_text(None, 'mm') == ''
    assert cr.test_type_label('HardConservative') == 'Hard (conservative)'
    assert cr.test_type_label('Duplicate') == 'Duplicates'
    assert cr.test_state_label('Old') == 'Out of date' and cr.test_state_label('Complete') == 'Up to date'


def test_shape_row_adds_display_fields():
    row = {'status': 'active', 'distance_m': -0.0421, 'created': '2026-09-30T10:00:00',
           'approved_time': None}
    shaped = cr.shape_row(row, 'mm', TODAY)
    assert shaped['status'] == 'Active' and shaped['open']
    assert shaped['dist'] == -42.1
    assert shaped['found'] == datetime.datetime(2026, 9, 30, 10, 0)
    assert shaped['age'] == 5
    assert shaped['approved'] is None and shaped['image'] is None and shaped['cat_a'] == ''
    assert row['status'] == 'active'                          # input untouched
    bare = cr.shape_row({'status': 'New'}, 'mm', None)
    assert bare['dist'] is None and bare['age'] is None and bare['found'] is None


def test_counts_kpis_and_oldest():
    data = fake_data()
    tally = cr.counts(data['tests'][0]['rows'])
    assert tally['total'] == 220
    assert tally['open'] == sum(tally['by_status'][s] for s in cr.OPEN)
    assert tally['closed'] + tally['open'] == tally['total']
    k = cr.kpis(data)
    assert k['tests'] == 4 and k['total'] == 600
    oldest = k['oldest']
    assert oldest['open'] and oldest['age'] == max(r['age'] for r in cr.all_rows(data) if r['open'])
    assert cr.oldest_open([]) is None
    assert cr.counts([{'status': 'Weird'}])['other'] == 1


def test_tallies_order_and_blanks():
    rows = [{'status': 'New', 'level': 'Level 10'}, {'status': 'New', 'level': 'Level 2'},
            {'status': 'Active', 'level': None}, {'status': 'Resolved', 'level': 'Level 2'},
            {'status': 'Reviewed', 'level': 'Level 10'}]
    assert cr.tally(rows, 'level', blank=cr.NO_LEVEL) == [('Level 10', 2), ('Level 2', 1), ('No level', 1)]
    assert cr.tally(rows, 'level', open_only=False, limit=2) == [('Level 2', 2), ('Level 10', 2)]
    assert cr.tally(rows, lambda r: r['status'], open_only=False)[0] == ('New', 2)


def test_age_tally_buckets():
    rows = [{'status': 'New', 'age': 0}, {'status': 'New', 'age': 9}, {'status': 'Active', 'age': 31},
            {'status': 'Resolved', 'age': 99}, {'status': 'Reviewed', 'age': None}]
    assert cr.age_tally(rows) == [('0-7 days', 1), ('8-14 days', 1), ('15-30 days', 0), ('Over 30 days', 1),
                                  ('Unknown', 1)]
    assert cr.age_tally([{'status': 'New', 'age': 3}])[-1] == ('Over 30 days', 0)


def test_pair_tally_is_unordered():
    rows = [{'status': 'New', 'trade_a': 'Structure', 'trade_b': 'Mechanical'},
            {'status': 'Active', 'trade_a': 'Mechanical', 'trade_b': 'Structure'},
            {'status': 'New', 'trade_a': 'Plumbing', 'trade_b': ''},
            {'status': 'Resolved', 'trade_a': 'Mechanical', 'trade_b': 'Structure'}]
    assert cr.pair_tally(rows) == [('Mechanical', 'Structure', 2, 1), ('Plumbing', 'Unassigned', 1, 1)]
    models = cr.pair_tally([{'status': 'New', 'model_a': 'B.nwc', 'model_b': 'A.nwc'}], 'model')
    assert models == [('A.nwc', 'B.nwc', 1, 1)]


def test_matrix_upper_triangle_and_order():
    rows = [{'status': 'New', 'trade_a': 'Mechanical', 'trade_b': 'Structure'},
            {'status': 'Active', 'trade_a': 'Structure', 'trade_b': 'Mechanical'},
            {'status': 'Active', 'trade_a': 'Mechanical', 'trade_b': 'Mechanical'},
            {'status': 'Resolved', 'trade_a': 'Plumbing', 'trade_b': 'Structure'},
            {'status': 'New', 'trade_a': 'Zeta', 'trade_b': 'Structure'}]
    m = cr.matrix(rows, 'trade', order=['Structure', 'Mechanical'])
    assert m['labels'] == ['Structure', 'Mechanical', 'Zeta']
    assert m['grid'] == [[0, 2, 1], [None, 1, 0], [None, None, 0]]
    assert m['involving'] == [3, 3, 1] and m['total'] == 4
    new_only = cr.matrix(rows, 'trade', statuses=['New'])
    assert new_only['total'] == 2 and 'Plumbing' not in new_only['labels']
    assert cr.matrix([], 'trade')['labels'] == []


def test_heat_step():
    assert cr.heat_step(0, 10) == 0 and cr.heat_step(None, 10) == 0 and cr.heat_step(5, 0) == 0
    assert cr.heat_step(10, 10) == 6 and cr.heat_step(1, 10) == 1 and cr.heat_step(5, 10) == 3
    assert cr.heat_step(1, 1000) == 1


def test_groups_view():
    data = fake_data()
    groups = cr.groups_view(data['tests'][0]['rows'])
    assert groups and all(g['test'] == 'Ducts vs Beams' for g in groups)
    first = groups[0]
    members = [r for r in data['tests'][0]['rows'] if r['group_guid'] == 'g-0-1']
    assert first['count'] == len(members)
    assert first['worst'] == min(r['dist'] for r in members)
    assert sum(first['by_status'].values()) == first['count']
    assert cr.groups_view([{'status': 'New', 'group': None}]) == []


def test_text_helpers():
    test = {'type': 'Hard', 'tolerance_m': 0.01, 'last_run': datetime.datetime(2026, 10, 4, 17, 30),
            'state': 'Out of date'}
    assert cr.test_line(test, 'mm') == 'Hard, tolerance 10 mm, last run 2026-10-04 17:30 (out of date)'
    assert cr.test_line({'type': 'Clearance', 'state': 'Not run'}, 'm') == 'Clearance, not run'
    tally = cr.counts([{'status': 'New'}, {'status': 'New'}, {'status': 'Resolved'}])
    assert cr.counts_line(tally) == '3 clashes: 2 New, 1 Resolved'
    assert cr.counts_line(cr.counts([])) == 'No clashes'
    assert cr.status_mix_text({'New': 0, 'Active': 1200}) == '1,200 Active'
    assert cr.tests_text([]) == 'Every test with results'
    assert cr.tests_text(['A']) == 'A' and cr.tests_text(['A', 'B']) == '2 tests'
    assert cr.plural(1, 'clash', 'clashes') == '1 clash' and cr.plural(1500, 'test') == '1,500 tests'
    assert cr.file_values('') == {'file': 'Untitled'}
    assert cr.dominant(['A', '', 'B', 'B', None]) == 'B' and cr.dominant([]) == ''


def test_image_planning():
    assert cr.image_counts({'A': 500, 'B': 20}, 300) == {'A': 300, 'B': 20}
    assert cr.image_counts({'A': 500}, 0) == {'A': 500}
    assert cr.over_cap({'A': 301}, 300) and not cr.over_cap({'A': 300}, 300)
    assert not cr.over_cap({'A': 999}, None)
    data = fake_data()
    plan = cr.thumbnail_plan(data, cr.OPEN, 10)
    assert all(len(v) == 10 for v in plan.values())
    assert all(r['open'] for v in plan.values() for r in v)
    note = cr.image_note({'made': 5, 'failed': 2, 'skipped': 1}, 8, 300, True)
    assert note.startswith('Thumbnails show the first 300') and '3 of 8 thumbnails' in note
    assert cr.image_note({'made': 3}, 3, 300, False) == ''


def test_subset_keeps_every_test():
    data = fake_data()
    only = cr.subset(data, lambda r: r['trade_a'] == 'Fire Protection')
    assert [t['name'] for t in only['tests']] == [t['name'] for t in data['tests']]
    assert not only['tests'][0]['rows'] and only['tests'][2]['rows']
    assert len(data['tests'][2]['rows']) == 140              # original untouched


def test_stage_maps_and_cancels():
    seen = []
    stage = cr.Stage(lambda f, label: seen.append(round(f, 3)))
    stage.sub(0.5, 0.5)(0.5, 'x')
    stage.sub(0.5, 0.5).sub(0.5, 0.5)(1.0)
    assert seen == [0.75, 1.0]
    assert cr.Stage(None)(0.3) is True
    from namo import items
    raises(items.Cancelled, cr.Stage(lambda f, label: False), 0.1)
    assert cr.Stage(lambda f, label: None)(0.2) is True
    assert approx(cr.Stage(None, 0.2, 0.5).sub(0.5, 0.5).start, 0.45)


def test_listed_text_and_oriented_matrix():
    assert cr.listed_text(162, cr.OPEN) == '162 clashes listed (New, Active, Reviewed)'
    assert cr.listed_text(220, None) == 'All 220 clashes listed'
    assert cr.listed_text(1, None) == '1 clash listed'
    rows = [{'status': 'New', 'model_a': 'MEC.nwc', 'model_b': 'STR.nwc'},
            {'status': 'Active', 'model_a': 'MEC.nwc', 'model_b': 'STR.nwc'},
            {'status': 'New', 'model_a': 'STR.nwc', 'model_b': 'MEC.nwc'},
            {'status': 'Resolved', 'model_a': 'PLB.nwc', 'model_b': 'ARC.nwc'}]
    m = cr.oriented_matrix(rows, 'model')
    assert m['rows'] == ['MEC.nwc', 'STR.nwc'] and m['cols'] == ['MEC.nwc', 'STR.nwc']
    assert m['grid'] == [[None, 2], [1, None]] and m['total'] == 3
    forced = cr.matrix(rows, 'model', labels=['STR.nwc', 'MEC.nwc'])
    assert forced['labels'] == ['STR.nwc', 'MEC.nwc'] and forced['grid'][0][1] == 3


# ---- API half through the fake Navisworks layer (dev/tests/test_items.py) -----------------------

import test_items as nav  # noqa: E402


def fake_clash_doc():
    """A fake document with two clash tests (one with a nested group) on the fake model tree
    of test_items: a duct in MEP.nwc against two walls in ARCH.nwc."""
    doc, n = nav.model_tree()
    duct, w1, w2 = n['Duct solid'], n['Wall 1 solid'], n['Wall 2 solid']
    r1 = nav.ClashResult('Clash1', duct, w1, (1.0, 2.0, 3.0))
    r2 = nav.ClashResult('Clash2', duct, w2, (5.0, 2.0, 3.0), status='Active', distance=-0.2)
    r3 = nav.ClashResult('Clash3', duct, w1, (1400.0, 2.0, 3.0), status='Resolved')
    r4 = nav.ClashResult('Clash4', w1, w2, (3.0, 0.0, 0.0), status='Reviewed')
    r2.AssignedTo = nav.Assignee('Jane Smith')
    test_a = nav.ClashTest('Ducts vs Walls', [r1, nav.ClashResultGroup('G1', [r2, r3])])
    test_b = nav.ClashTest('Walls vs Walls', [r4, nav.ClashResult('Clash5', w2, w1, (600.0, 1000.0, 0.0),
                                                                  status='Approved')])
    doc.clash_tests = [test_a, nav.ClashTest('Empty', []), test_b]
    doc.clash_data = nav.FakeTestsData()
    doc.clash_data.tests = doc.clash_tests
    doc.Units = 'Millimeters'
    doc.u2m = 0.001
    return doc, test_a, test_b


class Redirected(object):
    """with Redirected('name') as folder: namo data and settings under a scratch folder."""

    def __init__(self, name):
        self.name = name

    def __enter__(self):
        from namo import paths
        self.folder = _compat.tmpdir(self.name)
        self.previous = paths.redirect(self.folder)
        try:
            from pynavis import settings
            self.settings = settings
            self.old_settings = settings._APPDATA_OVERRIDE
            settings._APPDATA_OVERRIDE = self.folder
        except ImportError:
            self.settings = None
        return self.folder

    def __exit__(self, *exc):
        from namo import paths
        paths.redirect(self.previous)
        if self.settings is not None:
            self.settings._APPDATA_OVERRIDE = self.old_settings
        return False


def test_api_collect_reads_tests_into_data():
    doc, test_a, test_b = fake_clash_doc()
    with Redirected('clashreport-collect'):
        with nav.FakeNav(doc):
            found, missing = cr.resolve_tests([], doc)
            assert [t.DisplayName for t in found] == ['Ducts vs Walls', 'Walls vs Walls']
            assert missing == []
            found, missing = cr.resolve_tests(['walls vs walls', 'Nope'], doc)
            assert [t.DisplayName for t in found] == ['Walls vs Walls'] and missing == ['Nope']
            assert cr.status_counts(test_a) == {'New': 1, 'Active': 1, 'Reviewed': 0, 'Approved': 0, 'Resolved': 1}
            seen = []
            data = cr.collect([test_a, test_b], doc, lambda f, label: seen.append(f))
    assert seen[-1] == 1.0 and all(0.0 <= f <= 1.0 for f in seen)
    assert data['unit'] == 'mm' and data['doc_units'] == 'Millimeters'
    assert [t['name'] for t in data['tests']] == ['Ducts vs Walls', 'Walls vs Walls']
    rows = data['tests'][0]['rows']
    assert [r['name'] for r in rows] == ['Clash1', 'Clash2', 'Clash3']
    assert rows[0]['cat_a'] == 'Ducts' and rows[0]['cat_b'] == 'Walls'
    assert rows[1]['dist'] == -0.2 and rows[1]['group'] == 'G1' and rows[1]['open']
    assert rows[2]['status'] == 'Resolved' and not rows[2]['open']
    assert rows[0]['age'] is not None
    assert len(data['live']['Ducts vs Walls']) == 3
    assert data['tests'][0]['type'] == 'Custom' and data['tests'][0]['last_run'] is None


def test_api_collect_cancels():
    doc, test_a, _test_b = fake_clash_doc()
    from namo import items
    with Redirected('clashreport-cancel'):
        with nav.FakeNav(doc):
            raises(items.Cancelled, cr.collect, [test_a], doc, lambda f, label: False)
