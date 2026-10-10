# -*- coding: utf-8 -*-
"""namo.issues pure half: records, statuses, numbering, filters, sorting, aging,
statistics, pins, merging and the BCF mapping. Runs on CPython and IronPython 3.4."""
import datetime

import _compat

from namo import issues

NOW = datetime.datetime(2026, 10, 5, 14, 30, 0)
TODAY = datetime.date(2026, 10, 5)


def _issue(id_, status='Open', priority='Normal', trade='', assignee='', due='', created=None,
           title=None, **extra):
    record = issues.new_issue(dict({'title': title or 'Issue %s' % id_, 'status': status,
                                    'priority': priority, 'trade': trade, 'assignee': assignee,
                                    'due': due}, **extra), 'amol', created or NOW)
    record['id'] = id_
    record['number'] = issues.split_id(id_)[1]
    return record


def test_canonical_status_and_priority():
    assert issues.canonical_status('in-progress') == 'In progress'
    assert issues.canonical_status('Reopened') == 'Open'
    assert issues.canonical_status('DONE') == 'Resolved'
    assert issues.canonical_status('cancelled') == 'Void'
    assert issues.canonical_status('closed') == 'Closed'
    assert issues.canonical_status('weird', default=None) is None
    assert issues.canonical_status('') == 'Open'
    assert issues.canonical_priority('Medium') == 'Normal'
    assert issues.canonical_priority('blocker') == 'Critical'
    assert issues.canonical_priority('1') == 'Critical'
    assert issues.canonical_priority('5') == 'Low'
    assert issues.canonical_priority('??', default=None) is None


def test_ids_and_prefixes():
    assert issues.split_id('RFI-012') == ('RFI-', 12)
    assert issues.split_id('X') == ('X', None)
    assert issues.format_id('RFI-', 7) == 'RFI-007'
    assert issues.format_id('ISS-', 1234) == 'ISS-1234'
    assert issues.clean_prefix('rfi') == 'RFI-'
    assert issues.clean_prefix('HOLD-') == 'HOLD-'
    assert issues.clean_prefix('a b/c') == 'ABC-'
    assert issues.clean_prefix('') == ''
    ids = ['RFI-010', 'rfi-9', 'HOLD-002', 'RFI-001']
    assert sorted(ids, key=issues.id_sort_key) == ['HOLD-002', 'RFI-001', 'rfi-9', 'RFI-010']


def test_labels():
    assert issues.labels_from_text('a, b; B,, c') == ['a', 'b', 'c']
    assert issues.labels_text(['x', ' ', 'y']) == 'x, y'


def test_new_issue_and_normalise():
    issue = issues.new_issue({'title': ' Duct hits beam ', 'status': 'closed', 'due': '12/10/2026',
                              'labels': 'L2, MEP'}, 'amol', NOW)
    assert issue['title'] == 'Duct hits beam'
    assert issue['status'] == 'Closed'
    assert issue['closed'] == '2026-10-05T14:30:00'
    assert issue['due'] == '2026-10-12'
    assert issue['labels'] == ['L2', 'MEP']
    assert issue['created'] == issue['modified'] == '2026-10-05T14:30:00'
    assert issue['created_by'] == 'amol'
    assert len(issue['guid']) == 36 and issue['guid'] == issue['guid'].lower()
    junk = issues.normalise({'id': 'ISS-004', 'status': 'nonsense', 'priority': None,
                             'comments': [{'text': 'hi'}, 'junk'], 'elements': 'x',
                             'location': {'point': [1, 2]}, 'keep_me': 5})
    assert junk['number'] == 4
    assert junk['status'] == 'Open' and junk['priority'] == 'Normal'
    assert len(junk['comments']) == 1 and junk['comments'][0]['guid']
    assert junk['elements'] == [] and junk['location'] is None
    assert junk['keep_me'] == 5
    assert junk['source'] == {'kind': 'manual', 'ref': ''}


def test_validate():
    assert issues.validate(_issue('A-1')) == []
    bad = _issue('A-1')
    bad['title'] = ''
    bad['due'] = 'never'
    problems = issues.validate(bad)
    assert len(problems) == 2


def test_apply_changes_status_comment_and_closed():
    issue = _issue('RFI-001')
    later = datetime.datetime(2026, 10, 6, 9, 0, 0)
    out, changed = issues.apply_changes(issue, {'status': 'resolved', 'assignee': ' Jane '},
                                        'kim', later, note='Fixed on site')
    assert changed == ['assignee', 'status']
    assert out['status'] == 'Resolved' and out['assignee'] == 'Jane'
    assert out['closed'] == '2026-10-06T09:00:00'
    assert out['modified_by'] == 'kim'
    last = out['comments'][-1]
    assert last['status_change'] == {'from': 'Open', 'to': 'Resolved'}
    assert issues.comment_text(last) == 'Status: Open > Resolved. Fixed on site'
    reopened, changed = issues.apply_changes(out, {'status': 'Open'}, 'kim', later)
    assert reopened['closed'] == ''
    same, changed = issues.apply_changes(reopened, {'assignee': 'Jane'}, 'kim', later)
    assert changed == [] and same['modified'] == reopened['modified']
    _compat.raises(ValueError, issues.apply_changes, issue, {'id': 'X'})
    _compat.raises(ValueError, issues.apply_changes, issue, {'status': 'maybe'})
    _compat.raises(ValueError, issues.apply_changes, issue, {'due': 'soonish'})
    _compat.raises(ValueError, issues.apply_changes, issue, {'title': '  '})
    noted, changed = issues.apply_changes(issue, {}, 'kim', later, note='Just a note')
    assert changed == ['comments'] and noted['comments'][-1]['text'] == 'Just a note'


def test_add_comment_to():
    issue = _issue('A-1')
    out = issues.add_comment_to(issue, 'Checked', 'kim', NOW)
    assert out['comments'][-1]['author'] == 'kim'
    _compat.raises(ValueError, issues.add_comment_to, issue, '  ')


def test_merge_for_save_keeps_everyones_comments():
    base = _issue('A-1')
    mine = issues.add_comment_to(base, 'mine', 'me', NOW)
    mine['title'] = 'My title'
    theirs = issues.add_comment_to(base, 'theirs', 'them', NOW + datetime.timedelta(minutes=1))
    theirs['images'] = [{'file': 'shot.jpg', 'kind': 'screenshot'}]
    theirs['rev'] = 5
    theirs['modified_by'] = 'them'
    theirs['modified'] = '2026-10-05T14:31:00'
    merged = issues.merge_for_save(mine, theirs)
    assert merged['title'] == 'My title'
    assert [c['text'] for c in merged['comments']] == ['mine', 'theirs']
    assert merged['images'][0]['file'] == 'shot.jpg'
    assert merged['rev'] == 5
    note = issues.conflict_note(theirs)
    assert 'them' in note and '14:31' in note


def test_due_state_and_aging():
    late = _issue('A-1', due='2026-10-01')
    soon = _issue('A-2', due='2026-10-07')
    today = _issue('A-3', due='2026-10-05')
    later = _issue('A-4', due='2026-11-01')
    none = _issue('A-5')
    done = _issue('A-6', status='Closed', due='2026-09-01')
    assert issues.due_state(late, TODAY) == 'overdue'
    assert issues.days_overdue(late, TODAY) == 4
    assert issues.due_note(late, TODAY) == '4 days late'
    assert issues.due_state(soon, TODAY) == 'soon'
    assert issues.due_note(soon, TODAY) == 'Due in 2 days'
    assert issues.due_note(today, TODAY) == 'Due today'
    assert issues.due_state(later, TODAY) == 'later'
    assert issues.due_state(none, TODAY) == 'none'
    assert issues.due_state(done, TODAY) == 'done' and issues.days_overdue(done, TODAY) == 0
    old = _issue('A-7', created=datetime.datetime(2026, 9, 1, 8, 0))
    assert issues.age_days(old, TODAY) == 34


def test_filter_issues():
    rows = [_issue('A-1', trade='Mechanical', assignee='Jane', priority='High', due='2026-10-01'),
            _issue('A-2', status='In progress', trade='Electrical'),
            _issue('A-3', status='Resolved', trade='Mechanical', labels=['L2']),
            _issue('A-4', status='Void', title='Duplicate of A-1'),
            _issue('A-5', trade='', assignee='')]
    ids = lambda found: [i['id'] for i in found]  # noqa: E731
    assert ids(issues.filter_issues(rows, status='open')) == ['A-1', 'A-2', 'A-5']
    assert ids(issues.filter_issues(rows, status='closed')) == ['A-3']
    assert ids(issues.filter_issues(rows, status=['Void', 'in-progress'])) == ['A-2', 'A-4']
    assert ids(issues.filter_issues(rows, trade='mechanical')) == ['A-1', 'A-3']
    assert ids(issues.filter_issues(rows, trade='No trade')) == ['A-4', 'A-5']
    assert ids(issues.filter_issues(rows, assignee='Unassigned', status='open')) == ['A-2', 'A-5']
    assert ids(issues.filter_issues(rows, priority='high')) == ['A-1']
    assert ids(issues.filter_issues(rows, text='duplicate a-1')) == ['A-4']
    assert ids(issues.filter_issues(rows, due='overdue', today=TODAY)) == ['A-1']
    assert ids(issues.filter_issues(rows, labels=['l2'])) == ['A-3']
    assert ids(issues.filter_issues(rows, status='all', trade='')) == ['A-1', 'A-2', 'A-3', 'A-4', 'A-5']
    assert ids(issues.filter(rows, status='open', trade='Electrical')) == ['A-2']


def test_filter_exact_status_is_not_the_group():
    # 'Open' / 'Closed' (exact statuses, as the pane, BCF Export and Meeting Mode pass them)
    # mean that status only; 'open' / 'closed' are the Unresolved / Resolved-or-closed groups.
    rows = [_issue('A-1'), _issue('A-2', status='In progress'), _issue('A-3', status='Resolved'),
            _issue('A-4', status='Closed')]
    ids = lambda found: [i['id'] for i in found]  # noqa: E731
    assert ids(issues.filter_issues(rows, status='Open')) == ['A-1']
    assert ids(issues.filter_issues(rows, status='Closed')) == ['A-4']
    assert ids(issues.filter_issues(rows, status=['Closed'])) == ['A-4']
    assert ids(issues.filter_issues(rows, status='open')) == ['A-1', 'A-2']
    assert ids(issues.filter_issues(rows, status='closed')) == ['A-3', 'A-4']
    assert ids(issues.filter_issues(rows, status=['Open', 'Resolved'])) == ['A-1', 'A-3']


def test_sorting():
    rows = [_issue('A-10', priority='Low'), _issue('A-2', priority='Critical', due='2026-10-09'),
            _issue('A-3', status='Closed', priority='Critical'),
            _issue('A-1', priority='Critical', due='2026-10-08')]
    assert [i['id'] for i in issues.sort_issues(rows)] == ['A-1', 'A-2', 'A-10', 'A-3']
    assert [i['id'] for i in issues.sort_issues(rows, 'id')] == ['A-1', 'A-2', 'A-3', 'A-10']
    assert [i['id'] for i in issues.sort_issues(rows, 'priority')][:3] == ['A-1', 'A-2', 'A-3']
    assert [i['id'] for i in issues.sort_issues(rows, 'due')] == ['A-1', 'A-2', 'A-3', 'A-10']
    assert [i['id'] for i in issues.sort_issues(rows, 'id', descending=True)][0] == 'A-10'


def test_distinct_and_tally():
    rows = [_issue('A-1', trade='Mechanical'), _issue('A-2', trade='electrical'),
            _issue('A-3', trade=''), _issue('A-4', trade='Mechanical')]
    assert issues.distinct(rows, 'trade', blank='No trade') == ['electrical', 'Mechanical', 'No trade']
    assert issues.tally(rows, 'trade', 'No trade') == [('Mechanical', 2), ('electrical', 1),
                                                         ('No trade', 1)]
    assert issues.tally(rows, 'priority', 'Normal', order=issues.URGENCY) == [
        ('Critical', 0), ('High', 0), ('Normal', 4), ('Low', 0)]


def test_counts_status_line_and_summary():
    rows = [_issue('A-1', due='2026-10-01', trade='Mechanical', priority='High',
                   created=datetime.datetime(2026, 9, 1, 8, 0)),
            _issue('A-2', due='2026-10-08', trade='Mechanical'),
            _issue('A-3', status='Closed', trade='Electrical'),
            _issue('A-4', status='Void'),
            _issue('A-5', status='In progress', trade='Electrical', priority='Critical')]
    rows[2]['closed'] = '2026-10-03T10:00:00'
    c = issues.counts(rows, TODAY)
    assert (c['total'], c['open'], c['overdue'], c['soon'], c['closed'], c['void']) == (5, 3, 1, 1, 1, 1)
    assert issues.status_line(rows, today=TODAY) == '3 open, 1 overdue, 5 in total'
    assert issues.status_line(rows, shown=2, today=TODAY).endswith('2 shown')
    s = issues.summary(rows, TODAY)
    assert s['kpis'] == {'open': 3, 'overdue': 1, 'due_week': 1, 'closed_recent': 1}
    assert s['open_by_trade'] == [('Electrical', 1), ('Mechanical', 2)][::-1] or \
        s['open_by_trade'] == [('Mechanical', 2), ('Electrical', 1)]
    assert s['open_by_priority'][0] == ('Critical', 1)
    assert [i['id'] for i in s['overdue']] == ['A-1']
    assert [i['id'] for i in s['recently_closed']] == ['A-3']
    assert s['aging'][-1] == ('Over 30 days', 1)
    assert [t for t, _members in s['by_trade']] == ['Mechanical', 'Electrical']


def test_points_cameras_and_pins():
    issue = _issue('A-1', location={'point': [1.0, 2.0, 3.0], 'units': 'Meters'})
    assert issues.point_in(issue, 'Meters') == (1.0, 2.0, 3.0)
    feet = issues.point_in(issue, 'Feet')
    assert _compat.approx(feet, (1 / 0.3048, 2 / 0.3048, 3 / 0.3048), 1e-9)
    issue['camera'] = {'position': [10.0, 0.0, 0.0], 'focal_distance': 5.0, 'projection': 'persp'}
    issue['camera_units'] = 'Meters'
    cam = issues.camera_in(issue, 'Millimeters')
    assert _compat.approx(cam['position'], [10000.0, 0.0, 0.0], 1e-9)
    assert _compat.approx(cam['focal_distance'], 5000.0, 1e-9)
    # Pins are a real 1.2 m in every model: metres, feet, millimetres, unknown units.
    assert issues.pin_height(1.0) == 1.2
    assert _compat.approx(issues.pin_height(0.3048), 1.2 / 0.3048, 1e-9)
    assert _compat.approx(issues.pin_height(0.001), 1200.0, 1e-9)
    assert issues.pin_height(None) == 1.2 and issues.pin_height(0) == 1.2
    # 1.37 million feet from the origin the pin is the same size, not a fraction of that.
    far = issues.pin_segments((1370000.0, 1370000.0, 30.0), issues.pin_height(0.3048))
    tops = [max(a[2], b[2]) - 30.0 for a, b, _dashed in far]
    lows = [min(a[2], b[2]) - 30.0 for a, b, _dashed in far]
    assert abs(max(tops) + min(lows)) < 1e-6 and max(tops) < 0.5 / 0.3048   # centred on the point
    wide = [max(abs(a[i] - b[i]) for i in (0, 1)) for a, b, _dashed in far]
    assert max(wide) < 1.0 / 0.3048                             # never storey sized
    # One family with Photo Pins: the shared glyph (namo.pins), sized from 1.4 x height.
    from namo import photopins, pins
    segments = issues.pin_segments((0, 0, 0), 2.0)
    assert len(segments) == pins.SEGMENT_COUNT
    assert segments == pins.segments((0, 0, 0), 2.8) == photopins.pin_segments((0, 0, 0), 2.8)
    assert segments[0][2] is False
    assert issues.pin_label_point((0, 0, 0), 2.0) == pins.top((0, 0, 0), 2.8)   # the label sits on the marker
    issue['number'] = 12
    issue['type'] = 'RFI'
    issue['title'] = 'Duct hits the transfer beam above the corridor on level two'
    label = issues.pin_label(issue)
    assert label.startswith('#12 RFI: Duct') and label.endswith('...') and len(label) <= 40


def test_snapshot_size():
    assert issues.snapshot_size(1920, 1080) == (1280, 720)
    assert issues.snapshot_size(800, 1600) == (640, 1280)
    assert issues.snapshot_size(0, 0) == (1280, 720)
    assert issues.snapshot_size(None, 'x') == (1280, 720)


def test_to_topic_and_components():
    issue = _issue('RFI-012', trade='Mechanical', labels=['L2'], assignee='Jane', due='2026-10-12',
                   camera={'position': [10.0, 20.0, 5.0], 'rotation': None, 'direction': [0, 1, 0],
                           'up': [0, 0, 1], 'projection': 'persp', 'height_field': 0.785398,
                           'aspect': 1.6},
                   elements=[{'ifc_guid': '2O2Fr$t4X7Zf8NOew3FLOH', 'element_id': '123'},
                             {'ifc_guid': 'not-a-guid'}, {'ifc_guid': '2O2Fr$t4X7Zf8NOew3FLOH'},
                             {'ifc_guid': '0000000000000000000000', 'element_id': ''}])
    issue['type'] = 'RFI'
    issue = issues.apply_changes(issue, {'status': 'In progress'}, 'kim', NOW, note='Looking')[0]
    components, skipped = issues.components_of(issue)
    assert [c['ifc_guid'] for c in components] == ['2O2Fr$t4X7Zf8NOew3FLOH', '0000000000000000000000']
    assert components[0]['originating_system'] == 'Autodesk Revit'
    assert components[1]['originating_system'] == ''
    assert skipped == 1
    topic = issues.to_topic(issue, unit_to_m=0.3048, snapshot_name='snapshot.png')
    assert topic['status'] == 'In Progress' and topic['type'] == 'RFI'
    assert topic['labels'] == ['L2', 'Mechanical']
    assert topic['index'] == 12 and topic['assigned_to'] == 'Jane'
    assert topic['comments'][-1]['comment'] == 'Status: Open > In progress. Looking'
    vp = topic['viewpoints'][0]
    cam = vp['visinfo']['camera']
    assert cam['type'] == 'PerspectiveCamera'
    assert _compat.approx(cam['CameraViewPoint'], (3.048, 6.096, 1.524), 1e-9)
    assert _compat.approx(cam['FieldOfView'], 45.0, 1e-4)
    bare = issues.to_topic(_issue('A-1'))
    assert bare['viewpoints'] == []


def test_from_topic_create_update_keep():
    topic = {'guid': 'abc', 'type': 'Clash', 'status': 'In Progress', 'title': 'Pipe vs duct',
             'priority': 'Major', 'labels': ['electrical', 'Level 2'], 'assigned_to': 'Jane',
             'due_date': '2026-10-12T00:00:00', 'description': 'Look',
             'creation_date': '2026-10-01T08:00:00Z', 'creation_author': 'bob',
             'modified_date': '2026-10-04T08:00:00Z',
             'comments': [{'guid': 'C1', 'date': '2026-10-02T08:00:00Z', 'author': 'bob',
                           'comment': 'First'}],
             'viewpoints': [{'visinfo': {'camera': {'type': 'PerspectiveCamera'},
                                         'selection': [{'ifc_guid': 'x'}]}}]}
    trades = ['Mechanical', 'Electrical']
    made = issues.from_topic(topic, None, trades, 'amol', NOW)
    assert made['action'] == 'create'
    assert made['fields']['trade'] == 'Electrical'
    assert made['fields']['labels'] == ['Level 2']
    assert made['fields']['status'] == 'In progress' and made['fields']['priority'] == 'High'
    assert made['fields']['due'] == '2026-10-12'
    assert made['fields']['created_by'] == 'bob'
    assert len(made['new_comments']) == 1 and made['new_comments'][0]['guid'] == 'c1'
    assert made['camera'] == {'type': 'PerspectiveCamera'}
    assert made['components'] == [{'ifc_guid': 'x'}]
    local = _issue('A-1')
    local['comments'] = [{'guid': 'c1', 'text': 'First'}]
    local['modified'] = '2026-10-01T00:00:00'
    update = issues.from_topic(topic, local, trades)
    assert update['action'] == 'update' and update['new_comments'] == []
    local['modified'] = '2026-10-10T00:00:00'
    keep = issues.from_topic(topic, local, trades)
    assert keep['action'] == 'keep'
