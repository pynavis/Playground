# -*- coding: utf-8 -*-
"""namo.timeliner: schedule sheets, validation, hierarchy, import plans, status, health,
and the API half driven through a fake DocumentTimeliner."""
import contextlib
import datetime
import sys
import types

import _compat
from namo import timeliner as tl

D = datetime.datetime

HEADER = ['Task ID', 'Parent ID', 'Name', 'Start', 'End', 'Actual start', 'Actual end',
          'Task type', 'Attach', 'Progress %', 'User1']


def _sheet(*rows):
    return [['Project schedule'], [], HEADER] + [list(r) for r in rows]


# ---- headers and cells ----------------------------------------------------------------------


def test_headers_aliases_and_detection():
    assert tl.field_of('  Planned  Start: ') == 'start'
    assert tl.field_of('Finish') == 'end'
    assert tl.field_of('% Complete') == 'progress'
    assert tl.field_of('Text 3') == 'user3'
    assert tl.field_of('Level') is None
    index, mapping = tl.find_header(_sheet())
    assert index == 2 and mapping['name'] == 2 and mapping['user1'] == 10
    assert tl.find_header([['a', 'b'], ['Name']]) == (None, {})


def test_cell_text_and_progress_scale():
    assert tl.cell_text(12.0) == '12' and tl.cell_text(1.5) == '1.5' and tl.cell_text(None) == ''
    assert tl.cell_text('  A1 ') == 'A1'
    assert tl.progress_scale([0.25, 1.0, None, '']) == 100.0
    assert tl.progress_scale([0, 1]) == 1.0
    assert tl.progress_scale([25, 50]) == 1.0
    assert tl.progress_scale(['50%', 0.5]) == 1.0
    assert tl.parse_progress(0.25, 100.0) == (25.0, None)
    assert tl.parse_progress('45%') == (45.0, None)
    assert tl.parse_progress('') == (None, None)
    assert tl.parse_progress(120)[1].startswith('Progress must be from 0 to 100')
    assert tl.parse_progress('lots')[1] == 'Progress "lots" is not a number.'


# ---- parsing and validation --------------------------------------------------------------


def test_parse_valid_sheet_with_parents_dates_and_types():
    parsed = tl.parse_rows(_sheet(
        ['1', '', 'Level 1', '2026-10-01', '2026-10-28', None, None, 'construct', '', 0, 'A'],
        ['1.1', '1', 'Columns', 46296.0, '05/10/2026', None, None, 'Construct',
         'Element > Category = Columns', 0.5, ''],
        ['1.2', '1', 'Slab', '2026-10-06', '2026-10-28', '2026-10-07', None, 'Demolish',
         'Structure/Slabs', 1.0, ''],
    ))
    assert parsed['header_row'] == 3 and parsed['hierarchy'] == 'parent'
    assert parsed['scale'] == 100.0
    errors = [p for p in parsed['problems'] if p['level'] == 'error']
    assert errors == []
    one, cols, slab = parsed['tasks']
    assert one['type'] == 'Construct' and one['user'] == {1: 'A'}
    assert cols['start'] == D(2026, 10, 1) and cols['end'] == D(2026, 10, 5)
    assert cols['progress'] == 50.0 and slab['progress'] == 100.0
    assert slab['actual_start'] == D(2026, 10, 7)
    assert 'attach' in cols['present'] and 'actual_end' not in slab['present']
    roots = tl.build_tree(parsed['tasks'])
    assert [r['id'] for r in roots] == ['1']
    assert [c['id'] for c in roots[0]['children']] == ['1.1', '1.2']
    assert [(t['id'], d) for t, d in tl.walk_tree(roots)] == [('1', 0), ('1.1', 1), ('1.2', 1)]


def test_month_first_dates():
    parsed = tl.parse_rows(_sheet(['1', '', 'A', '05/10/2026', '06/10/2026']), day_first=False)
    assert parsed['tasks'][0]['start'] == D(2026, 5, 10)


def test_validation_errors_and_warnings():
    parsed = tl.parse_rows(_sheet(
        ['1', '', 'Good', '2026-10-01', '2026-10-02'],
        ['2', '', '', '2026-10-01', '2026-10-02'],
        ['3', '', 'Bad date', 'soon', '2026-10-02'],
        ['4', '', 'Backwards', '2026-10-05', '2026-10-02'],
        ['1', '', 'Duplicate', '2026-10-01', '2026-10-02'],
        ['6', '99', 'Orphan', '2026-10-01', '2026-10-02'],
        ['7', '3', 'Child of bad', '2026-10-01', '2026-10-02'],
        ['8', '', 'Odd type', '2026-10-01', '2026-10-02', None, None, 'Paint'],
        ['', '', 'No id', '2026-10-01', '2026-10-02'],
        ['9', '', 'Too much', '2026-10-01', '2026-10-02', None, None, '', '', 150],
        ['10', '10', 'Self', '2026-10-01', '2026-10-02'],
    ))
    by_row = {}
    for p in parsed['problems']:
        by_row.setdefault(p['row'], []).append((p['level'], p['field'], p['message']))
    assert by_row[5] == [('error', 'name', 'The task has no name.')]
    assert by_row[6][0][2] == 'Start "soon" is not a date.'
    assert by_row[7][0][2] == 'End is before Start.'
    assert by_row[8][0][2] == 'Task ID 1 is also used on row 4.'
    assert by_row[9][0][2] == 'Parent ID 99 does not exist.'
    assert by_row[10][0][2] == 'Its parent on row 6 has problems.'
    assert by_row[11][0][0] == 'warning' and 'Paint' in by_row[11][0][2]
    assert by_row[12] == [('warning', 'id', 'No Task ID: a later merge cannot update this task.')]
    assert by_row[13][0][2].startswith('Progress must be from 0 to 100')
    assert by_row[14][0][2] == 'The task names itself as its parent.'
    ok = [t['name'] for t in parsed['tasks'] if t['ok']]
    assert ok == ['Good', 'Odd type', 'No id']


def test_parent_may_exist_in_the_model_and_cycles():
    parsed = tl.parse_rows(_sheet(['5', 'M1', 'Under model task']), existing_ids=['M1'])
    assert parsed['tasks'][0]['ok']
    parsed = tl.parse_rows(_sheet(['a', 'c', 'A'], ['b', 'a', 'B'], ['c', 'b', 'C'], ['d', 'c', 'D'],
                                  ['e', '', 'E']))
    messages = [(p['row'], p['message']) for p in parsed['problems']]
    assert (4, 'Parent IDs form a loop: a > c > b > a.') in messages or \
        any('Parent IDs form a loop' in m for r, m in messages if r == 4)
    assert [t['id'] for t in parsed['tasks'] if t['ok']] == ['e']
    assert any(m == 'Its parent on row 6 has problems.' for r, m in messages if r == 7)


def test_wbs_and_outline_hierarchies():
    rows = [['WBS', 'Name', 'Start', 'End'], ['1', 'A', '2026-10-01', '2026-10-02'],
            ['1.1', 'A1', '2026-10-01', '2026-10-02'], ['1.1.1', 'A11', '', ''],
            ['2', 'B', '', ''], ['3.4', 'Lost', '', '']]
    parsed = tl.parse_rows(rows)
    assert parsed['hierarchy'] == 'wbs'
    roots = tl.build_tree(parsed['tasks'])
    assert [r['id'] for r in roots] == ['1', '2', '3.4']
    assert roots[0]['children'][0]['children'][0]['name'] == 'A11'
    assert any(p['message'] == 'No task has WBS 3; placed at the top level.' for p in parsed['problems'])
    rows = [['Outline level', 'Name'], [1, 'Site'], [2, 'Dig'], [3, 'Dig north'], [2, 'Pour'], [1, 'Frame']]
    parsed = tl.parse_rows(rows)
    assert parsed['hierarchy'] == 'outline'
    roots = tl.build_tree(parsed['tasks'])
    assert [r['name'] for r in roots] == ['Site', 'Frame']
    assert [c['name'] for c in roots[0]['children']] == ['Dig', 'Pour']
    assert roots[0]['children'][0]['children'][0]['name'] == 'Dig north'
    assert roots[0].get('auto_id')


def test_no_header():
    parsed = tl.parse_rows([['a', 'b'], [1, 2]])
    assert parsed['header_row'] is None and parsed['problems'][0]['level'] == 'error'


# ---- import plans --------------------------------------------------------------------------


def _existing():
    return [
        {'key': (0,), 'parent_key': None, 'id': 'A', 'name': 'Alpha'},
        {'key': (0, 0), 'parent_key': (0,), 'id': 'A1', 'name': 'Alpha one'},
        {'key': (1,), 'parent_key': None, 'id': 'B', 'name': 'Beta'},
        {'key': (2,), 'parent_key': None, 'id': 'B', 'name': 'Beta again'},
    ]


def test_plan_merge():
    parsed = tl.parse_rows(_sheet(
        ['A1', 'A', 'Alpha one renamed', '2026-10-01', '2026-10-03'],
        ['N1', 'A', 'New under Alpha'],
        ['N2', '', 'New root'],
        ['N3', 'N2', 'New child of new root'],
        ['B', 'A', 'Beta moved?'],
    ), existing_ids=['A', 'A1', 'B'])
    plan = tl.plan_import(parsed, _existing(), 'merge')
    assert [(k, t['id']) for k, t in plan['updates']] == [((0, 0), 'A1'), ((1,), 'B')]
    assert [t['id'] for t in plan['adds'][(0,)]] == ['N1']
    assert [t['id'] for t in plan['new_roots']] == ['N2']
    assert [t['id'] for t in plan['new_roots'][0]['children']] == ['N3']
    assert plan['created'] == 3 and plan['updated'] == 2
    assert plan['kept_in_place'] == 1 and plan['ambiguous'] == ['B']


def test_plan_replace():
    parsed = tl.parse_rows(_sheet(['1', '', 'One'], ['2', '1', 'Two'], ['3', '', '']))
    plan = tl.plan_import(parsed, _existing(), 'replace')
    assert plan['created'] == 2 and plan['skipped'] == 1 and [r['id'] for r in plan['roots']] == ['1']
    _compat.raises(ValueError, tl.plan_import, parsed, [], 'append')


# ---- status, durations, health ----------------------------------------------------------------


def test_status_and_durations():
    today = D(2026, 10, 10)
    assert tl.task_status({'progress': 100.0}, today) == 'Complete'
    assert tl.task_status({'actual_end': D(2026, 10, 1)}, today) == 'Complete'
    assert tl.task_status({'progress': 20.0, 'end': D(2026, 10, 9)}, today) == 'In progress, late'
    assert tl.task_status({'actual_start': D(2026, 10, 1), 'end': D(2026, 10, 20)}, today) == 'In progress'
    assert tl.task_status({'start': D(2026, 10, 9)}, today) == 'Late start'
    assert tl.task_status({'start': D(2026, 10, 19)}, today) == 'Not started'
    assert tl.task_status({}, today) == 'No dates'
    assert tl.duration_days(D(2026, 10, 1), D(2026, 10, 2, 12)) == 1.5
    assert tl.duration_days(None, D(2026, 10, 1)) is None
    assert tl.outline_number((0, 2, 1)) == '1.3.2'
    rows = [{'start': D(2026, 10, 5), 'end': D(2026, 10, 9)}, {'start': D(2026, 9, 1), 'end': None,
                                                                 'actual_end': D(2026, 12, 1)}]
    assert tl.schedule_bounds(rows) == (D(2026, 9, 1), D(2026, 10, 9))
    assert tl.schedule_bounds(rows, actual=True) == (D(2026, 9, 1), D(2026, 12, 1))


def test_health_checks_and_score():
    rows = [
        {'has_children': True, 'attach_kind': 'none'},
        {'start': D(2026, 1, 1), 'end': D(2026, 1, 5), 'attach_kind': 'sets'},
        {'start': D(2026, 1, 1), 'end': D(2026, 1, 1), 'attach_kind': 'items'},
        {'start': None, 'end': D(2026, 1, 1), 'attach_kind': 'none'},
        {'start': D(2026, 1, 9), 'end': D(2026, 1, 1), 'attach_kind': 'search'},
    ]
    objects = {1: set(['a', 'b']), 2: set(['b', 'c']), 4: set(['d'])}
    report = tl.health(rows, objects, set(['a', 'b', 'c', 'd', 'e', 'f']))
    assert report['leaves'] == [1, 2, 3, 4]
    assert report['unattached'] == [3]
    assert report['missing_dates'] == [3]
    assert report['zero_duration'] == [2]
    assert report['end_before_start'] == [4]
    assert report['overlap'] == {'b': [1, 2]}
    assert report['unscheduled'] == set(['e', 'f']) and report['scheduled'] == 4
    # parts: unattached 1/4, dates 2/4, overlap 1/4, unscheduled 2/6
    expected = 100 * (1 - (0.25 * 0.25 + 0.25 * 0.5 + 0.15 * 0.25 + 0.35 * (2 / 6.0)))
    assert report['score'] == int(round(expected))
    assert tl.score_tone(90) == 'good' and tl.score_tone(70) == 'warn' and tl.score_tone(10) == 'bad'
    assert tl.health([])['score'] == 0


def test_template_rows_and_attach_parsing():
    examples = tl.template_rows([])
    assert len(examples) == 3 and examples[1][1] == '1' and examples[1][8].startswith('Element >')
    rows = [{'key': (0,), 'parent_key': None, 'id': 'A', 'name': 'Alpha', 'user': ['u1', '', ''] + [''] * 7},
            {'key': (0, 0), 'parent_key': (0,), 'id': 'A1', 'name': 'One', 'attach_hint': 'S/T',
             'progress': 50.0}]
    out = tl.template_rows(rows)
    assert out[0][:3] == ['A', '', 'Alpha'] and out[0][10] == 'u1'
    assert out[1][:3] == ['A1', 'A', 'One'] and out[1][8] == 'S/T' and out[1][9] == 50.0
    assert tl.split_attach('Set A\r\n\n Element > Category = Ducts ') == ['Set A', 'Element > Category = Ducts']
    assert tl.classify_attach('Set A', lambda p: p == 'Set A') == ('set', 'Set A')
    kind, conds = tl.classify_attach('Element > Category = Ducts', lambda p: False)
    assert kind == 'rule' and conds[0]['property'] == 'Category'
    kind, conds = tl.classify_attach('Element > Category = Ducts & Element > Level = L2', lambda p: False)
    assert kind == 'rule' and [c['value'] for c in conds] == ['Ducts', 'L2']
    targets = tl.attach_targets([{'row': 4, 'attach': 'Set A\nElement > Category = Ducts\nnope'},
                                 {'row': 5, 'attach': ''}], lambda p: p == 'Set A')
    assert list(targets) == [4] and targets[4]['sets'] == ['Set A']
    assert targets[4]['rules'][0][0]['value'] == 'Ducts' and targets[4]['misses'][0][0] == 'nope'
    assert tl.classify_attach('Nothing here', lambda p: False)[0] == 'miss'


# ---- API half through a fake TimeLiner ----------------------------------------------------------


class FakeSelection(object):
    def __init__(self):
        self.items = None
        self.sources = None

    @property
    def IsClear(self):
        return self.items is None and self.sources is None

    @property
    def HasSelectionSources(self):
        return self.sources is not None

    HasSearch = False

    @property
    def HasExplicitSelection(self):
        return self.items is not None

    @property
    def DisplayString(self):
        return 'sets' if self.sources is not None else 'items' if self.items is not None else ''

    def CopyFrom(self, value):
        if isinstance(value, FakeSources):
            self.sources, self.items = list(value), None
        else:
            self.items, self.sources = list(value), None

    def Clear(self):
        self.items = self.sources = None

    def GetSelectedItems(self, doc):
        return list(self.items or [])


class FakeSources(list):
    def Add(self, item):
        self.append(item)


class Children(list):
    def Add(self, item):
        item.Parent = self.owner
        self.append(item)

    @property
    def Count(self):
        return len(self)

    def IndexOf(self, item):
        for i, x in enumerate(self):
            if x is item:
                return i
        return -1


class FakeTask(object):
    def __init__(self):
        self.DisplayName = ''
        self.DisplayId = ''
        self.PlannedStartDate = self.PlannedEndDate = None
        self.ActualStartDate = self.ActualEndDate = None
        self.SimulationTaskTypeName = ''
        self.ProgressPercent = None
        self.IsEnabled = False
        self.IsPlannedEnabled = self.IsActualEnabled = False
        for n in range(1, 11):
            setattr(self, 'User%d' % n, '')
        self.Selection = FakeSelection()
        self.Children = Children()
        self.Children.owner = self
        self.Parent = None

    def CreateCopyWithoutChildren(self):
        copy = FakeTask()
        for name in ('DisplayName', 'DisplayId', 'PlannedStartDate', 'PlannedEndDate',
                     'ActualStartDate', 'ActualEndDate', 'SimulationTaskTypeName',
                     'ProgressPercent', 'IsEnabled'):
            setattr(copy, name, getattr(self, name))
        for n in range(1, 11):
            setattr(copy, 'User%d' % n, getattr(self, 'User%d' % n))
        copy.Selection.items = None if self.Selection.items is None else list(self.Selection.items)
        copy.Selection.sources = None if self.Selection.sources is None else list(self.Selection.sources)
        return copy

    def CreateCopy(self):
        copy = self.CreateCopyWithoutChildren()
        for child in self.Children:
            twin = child.CreateCopy()
            twin.Parent = copy
            copy.Children.Add(twin)
        return copy


class FakeTimeliner(object):
    def __init__(self):
        self.root = FakeTask()
        self.calls = []
        self.SimulationTaskTypes = [types.SimpleNamespace(DisplayName=n) for n in ('Construct', 'Demolish')]
        self.refuse_copy = False
        self.edit_replaces_children = False     # the other way TaskEdit might treat children

    @property
    def Tasks(self):
        return self.root.Children

    TasksRoot = property(lambda self: self.root)

    def TasksCopyFrom(self, roots):
        if self.refuse_copy:
            raise RuntimeError('refused')
        self.calls.append(('TasksCopyFrom', len(list(roots))))
        self.root.Children = Children()
        self.root.Children.owner = self.root
        for task in roots:
            self.root.Children.Add(task)

    def TasksClear(self):
        self.calls.append(('TasksClear',))
        self.root.Children = Children()
        self.root.Children.owner = self.root

    def TaskAddCopy(self, task):
        self.calls.append(('TaskAddCopy',))
        self.root.Children.Add(task)

    def TaskEdit(self, *args):
        values = args[-1]
        if len(args) == 2:
            parent, index = self.root, args[0]
        else:
            parent, index = args[0], args[1]
        self.calls.append(('TaskEdit', index))
        old = parent.Children[index]
        if self.edit_replaces_children:
            for child in old.Children:
                child.Parent = None             # the old branch is gone: its references are dead
        else:
            values.Children = old.Children
        for child in values.Children:
            child.Parent = values
        values.Parent = parent
        parent.Children[index] = values


class _DateTime(object):
    def __init__(self, dt):
        self.Year, self.Month, self.Day = dt.year, dt.month, dt.day
        self.Hour, self.Minute, self.Second, self.Millisecond = dt.hour, dt.minute, dt.second, 0
        self.Kind = 'Local'


@contextlib.contextmanager
def fake_timeliner():
    fake = FakeTimeliner()
    doc = types.SimpleNamespace(transactions=[], SelectionSets=types.SimpleNamespace(
        CreateSelectionSource=lambda saved: ('source', saved)))
    saved_modules = {}
    names = ('pynavis', 'pynavis._api', 'pynavis.viewpoints', 'Autodesk', 'Autodesk.Navisworks',
             'Autodesk.Navisworks.Api', 'Autodesk.Navisworks.Api.Timeliner')
    if not _compat.IRONPYTHON:
        # CPython has no .NET: fake the three System modules timeliner/dates import.
        names = names + ('System', 'System.Collections', 'System.Collections.Generic')
    for name in names:
        saved_modules[name] = sys.modules.get(name)
    package = types.ModuleType('pynavis')
    package.__path__ = []
    api_module = types.ModuleType('pynavis._api')
    api_module.Api = types.SimpleNamespace(SavedItem=object, SelectionSourceCollection=FakeSources,
                                           ModelItemCollection=list)
    api_module.Application = types.SimpleNamespace(ActiveDocument=doc)
    api_module.add_reference = lambda name: None
    viewpoints = types.ModuleType('pynavis.viewpoints')

    @contextlib.contextmanager
    def transaction(name, d=None):
        doc.transactions.append(name)
        yield None
    viewpoints.transaction = transaction
    tl_module = types.ModuleType('Autodesk.Navisworks.Api.Timeliner')
    tl_module.TimelinerTask = FakeTask
    tl_module.TimelinerDocumentExtensions = types.SimpleNamespace(GetTimeliner=lambda d: fake)
    autodesk = types.ModuleType('Autodesk')
    autodesk.__path__ = []
    nw = types.ModuleType('Autodesk.Navisworks')
    nw.__path__ = []
    nw_api = types.ModuleType('Autodesk.Navisworks.Api')
    nw_api.__path__ = []
    autodesk.Navisworks = nw
    nw.Api = nw_api
    nw_api.Timeliner = tl_module
    system = types.ModuleType('System')
    system.__path__ = []
    collections_ = types.ModuleType('System.Collections')
    collections_.__path__ = []
    generic = types.ModuleType('System.Collections.Generic')

    class _List(list):
        def __class_getitem__(cls, item):
            return cls

        def Add(self, item):
            self.append(item)
    generic.List = _ListFactory(_List)
    system.DateTime = lambda *a: _DateTime(D(*a[:6]))
    system.DateTimeKind = types.SimpleNamespace(Local='Local')
    package._api = api_module
    package.viewpoints = viewpoints
    modules = {'pynavis': package, 'pynavis._api': api_module, 'pynavis.viewpoints': viewpoints,
               'Autodesk': autodesk, 'Autodesk.Navisworks': nw, 'Autodesk.Navisworks.Api': nw_api,
               'Autodesk.Navisworks.Api.Timeliner': tl_module, 'System': system,
               'System.Collections': collections_, 'System.Collections.Generic': generic}
    for name in names:
        sys.modules[name] = modules[name]
    try:
        yield fake, doc
    finally:
        for name in names:
            if saved_modules[name] is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = saved_modules[name]


class _ListFactory(object):
    def __init__(self, cls):
        self.cls = cls

    def __getitem__(self, item):
        return self.cls


def _require_fakes():
    """Both engines: CPython gets fake System modules, IronPython uses the real ones."""


def _seed(fake):
    alpha = FakeTask()
    alpha.DisplayName, alpha.DisplayId = 'Alpha', 'A'
    one = FakeTask()
    one.DisplayName, one.DisplayId = 'Alpha one', 'A1'
    one.Selection.items = ['wall']
    alpha.Children.Add(one)
    beta = FakeTask()
    beta.DisplayName, beta.DisplayId = 'Beta', 'B'
    fake.root.Children.Add(alpha)
    fake.root.Children.Add(beta)


def test_api_snapshot_and_types():
    _require_fakes()
    with fake_timeliner() as (fake, doc):
        _seed(fake)
        rows = tl.snapshot(doc)
        assert [(r['key'], r['id'], r['outline'], r['has_children']) for r in rows] == [
            ((0,), 'A', '1', True), ((0, 0), 'A1', '1.1', False), ((1,), 'B', '2', False)]
        assert rows[1]['attach_kind'] == 'items' and rows[1]['parent_key'] == (0,)
        assert tl.task_types(doc) == ['Construct', 'Demolish']
        assert tl.selected_items(rows[1]['task'], doc) == ['wall']
        assert tl.selected_items(rows[0]['task'], doc) is None


def test_api_commit_merge_rebuilds_once():
    _require_fakes()
    with fake_timeliner() as (fake, doc):
        _seed(fake)
        parsed = tl.parse_rows(_sheet(
            ['A1', 'A', 'Alpha one renamed', '2026-10-01', '2026-10-03', None, None, '', 'Set X', 40],
            ['N1', 'A', 'New under Alpha'],
            ['N2', '', 'New root'], ['N3', 'N2', 'Grandchild']), existing_ids=['A', 'A1', 'B'])
        plan = tl.plan_import(parsed, tl.snapshot(doc), 'merge')

        def attach_for(task):
            return ('sets', ['saved:' + task['attach']]) if task.get('attach') else None
        route = tl.commit_import(plan, attach_for, doc)
        assert route == 'TasksCopyFrom' and doc.transactions == ['Import TimeLiner tasks']
        assert fake.calls == [('TasksCopyFrom', 3)]
        rows = tl.snapshot(doc)
        assert [(r['outline'], r['id'], r['name']) for r in rows] == [
            ('1', 'A', 'Alpha'), ('1.1', 'A1', 'Alpha one renamed'), ('1.2', 'N1', 'New under Alpha'),
            ('2', 'B', 'Beta'), ('3', 'N2', 'New root'), ('3.1', 'N3', 'Grandchild')]
        renamed = rows[1]['task']
        assert renamed.ProgressPercent == 40.0 and renamed.IsPlannedEnabled
        assert renamed.PlannedStartDate.Day == 1 and renamed.Selection.sources == [('source', 'saved:Set X')]
        assert rows[2]['task'].IsEnabled


def test_api_commit_replace_falls_back_to_add_copy():
    _require_fakes()
    with fake_timeliner() as (fake, doc):
        _seed(fake)
        fake.refuse_copy = True
        parsed = tl.parse_rows(_sheet(['1', '', 'One'], ['2', '1', 'Two']))
        plan = tl.plan_import(parsed, [], 'replace')
        assert tl.commit_import(plan, lambda t: None, doc) == 'TaskAddCopy'
        assert fake.calls == [('TasksClear',), ('TaskAddCopy',)]
        assert [(r['outline'], r['name']) for r in tl.snapshot(doc)] == [('1', 'One'), ('1.1', 'Two')]


def test_api_edit_tasks_uses_task_edit():
    _require_fakes()
    with fake_timeliner() as (fake, doc):
        _seed(fake)
        rows = tl.snapshot(doc)

        def set_progress(values):
            values.ProgressPercent = 75.0
        written, errors = tl.edit_tasks([(rows[1], set_progress), (rows[2], set_progress)], doc,
                                        'Set progress')
        assert (written, errors) == (2, [])
        assert fake.calls == [('TaskEdit', 0), ('TaskEdit', 1)]
        again = tl.snapshot(doc)
        assert again[1]['progress'] == 75.0 and again[2]['progress'] == 75.0
        assert again[1]['attach_kind'] == 'items'


def test_api_edit_tasks_keeps_children_however_task_edit_treats_them():
    # Regression: a summary task was edited through CreateCopyWithoutChildren and live
    # references taken before the loop. If TaskEdit replaces a task's children with the
    # copy's, that deleted the whole branch and stranded the edits still to come.
    _require_fakes()
    for replaces in (False, True):
        with fake_timeliner() as (fake, doc):
            _seed(fake)
            fake.edit_replaces_children = replaces
            rows = tl.snapshot(doc)

            def set_progress(values):
                values.ProgressPercent = 60.0
            written, errors = tl.edit_tasks([(rows[0], set_progress), (rows[1], set_progress)], doc)
            assert (written, errors) == (2, []), (replaces, errors)
            assert fake.calls == [('TaskEdit', 0), ('TaskEdit', 0)]          # the child first
            again = tl.snapshot(doc)
            assert [(r['id'], r['progress']) for r in again] == [('A', 60.0), ('A1', 60.0), ('B', None)]
            assert again[1]['attach_kind'] == 'items'


def test_api_snapshot_failure_is_a_sentence():
    _require_fakes()
    with fake_timeliner() as (fake, doc):
        _seed(fake)

        class Broken(object):
            Tasks = property(lambda self: (_ for _ in ()).throw(ValueError('member missing')))
        error = _compat.raises(RuntimeError, tl.snapshot, doc, Broken())
        assert error is None or 'TimeLiner could not be read' in str(error)


def test_api_commit_failure_is_a_sentence():
    _require_fakes()
    with fake_timeliner() as (fake, doc):
        _seed(fake)
        fake.refuse_copy = True
        fake.TaskAddCopy = lambda task: (_ for _ in ()).throw(ValueError('no'))
        parsed = tl.parse_rows(_sheet(['1', '', 'One']))
        plan = tl.plan_import(parsed, [], 'replace')
        _compat.raises(RuntimeError, tl.commit_import, plan, lambda t: None, doc)
