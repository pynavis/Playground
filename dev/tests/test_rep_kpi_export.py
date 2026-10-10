# -*- coding: utf-8 -*-
"""rep_kpi_export: the reports contract, table shaping, CSV quoting with BOM, README, and a
full non-interactive run (clash tables empty with a note outside Navisworks, history read
from namo.clashdata's store)."""
import datetime
import io
import json
import os

import _compat

from namo import clashdata, issues, issuestore, paths, reports, rep_kpi_export

DOC = r'C:\Projects\Tower\Coordination.nwf'
NOW = datetime.datetime(2026, 10, 5, 14, 30, 0)


class FakeDoc(object):
    def __init__(self, path):
        self.FileName = path


def test_contract_and_columns():
    config = rep_kpi_export.default_config()
    assert config['folder'] == '' and config['name_template'] == '{file} KPI'
    assert rep_kpi_export.TITLE == reports.title_of('kpi_export')
    assert rep_kpi_export.describe(config).startswith('5 tables as CSV and JSON')
    for table in rep_kpi_export.TABLE_NAMES:
        names = [n for n, _d in rep_kpi_export.COLUMNS[table]]
        assert len(names) == len(set(names)) and names[-1] == 'snapshot_time', table


def test_issue_and_comment_rows():
    issue = issues.new_issue({'title': 'Duct, "big" one', 'priority': 'High', 'due': '2026-10-01',
                              'labels': ['L2', 'MEP'],
                              'location': {'point': [1.5, 2, 3], 'units': 'Feet', 'level': 'L2'},
                              'source': {'kind': 'clash', 'ref': 't|r'}}, 'amol',
                             datetime.datetime(2026, 9, 1, 8, 0))
    issue['id'] = 'RFI-001'
    issue = issues.apply_changes(issue, {'status': 'In progress'}, 'kim', NOW, note='go')[0]
    rows = rep_kpi_export.issue_rows([issue], 'Tower.nwf', '2026-10-05T14:30:00', datetime.date(2026, 10, 5))
    row = rows[0]
    assert row['issue_key'] == issue['guid'] and row['is_open'] == 1 and row['priority_rank'] == 2
    assert row['days_overdue'] == 4 and row['is_overdue'] == 1 and row['age_days'] == 34
    assert row['age_bucket'] == 'Over 30 days' and row['labels'] == 'L2; MEP'
    assert row['location_x'] == 1.5 and row['source'] == 'clash'
    closed = issues.apply_changes(issue, {'status': 'Closed'}, 'kim', NOW)[0]
    assert rep_kpi_export.issue_rows([closed], 'M', 'T')[0]['age_days'] == 34
    comments = rep_kpi_export.comment_rows([issue], 'Tower.nwf', 'T')
    assert comments[0]['status_from'] == 'Open' and comments[0]['status_to'] == 'In progress'
    text = rep_kpi_export.csv_text('issues', rows)
    lines = text.split('\r\n')
    assert lines[0].startswith('issue_key,issue_id,model,title')
    assert '"Duct, ""big"" one"' in lines[1]
    assert text.endswith('\r\n')
    assert rep_kpi_export._cell(2.0) == '2' and rep_kpi_export._cell(0.25) == '0.25'
    assert rep_kpi_export._cell(True) == '1' and rep_kpi_export._cell(None) == ''


def test_clash_rows_and_history():
    by_test = {'Ducts vs Beams': [
        {'test_guid': 'T1', 'guid': 'R1', 'name': 'Clash1', 'status': 'New', 'distance_m': -0.05,
         'center_m': (1.0, 2.0, 3.0), 'key': 'a|b@1,2,3'},
        {'test_guid': 'T1', 'guid': 'R2', 'name': 'Clash2', 'status': 'Resolved'}]}
    results, tests, truncated = rep_kpi_export.clash_rows(by_test, 'M', 'T')
    assert [r['result_key'] for r in results] == ['T1|R1', 'T1|R2'] and not truncated
    assert results[0]['is_open'] == 1 and results[1]['is_open'] == 0
    assert tests == [{'test_key': 'T1', 'test': 'Ducts vs Beams', 'model': 'M', 'total': 2, 'new': 1,
                      'active': 0, 'reviewed': 0, 'approved': 0, 'resolved': 1, 'open': 1,
                      'snapshot_time': 'T'}]
    results, tests, truncated = rep_kpi_export.clash_rows(by_test, 'M', 'T', limit=1)
    assert len(results) == 1 and truncated and tests[0]['total'] == 2
    history = rep_kpi_export.history_rows([({'id': 'h1', 'time': '2026-10-01T09:00:00', 'label': 'Week 40'},
                                            {'Ducts vs Beams': [{'key': 'k1', 'status': 'Active'}]})],
                                          'M', 'T')
    assert history[0]['history_key'] == 'h1|Ducts vs Beams|k1' and history[0]['is_open'] == 1
    readme = rep_kpi_export.readme_text(['issues'], 'M', 'T', ['A note.'])
    assert 'Note: A note.' in readme and 'issue_key' in readme


def test_run_writes_the_folder():
    folder = _compat.tmpdir('g8-rep-kpi')
    previous = paths.redirect(folder)
    try:
        s = issuestore.IssueStore(DOC)
        s.create({'title': 'One'}, user='amol')
        issue = s.create({'title': 'Two', 'status': 'Closed'}, user='amol')
        s.add_comment(issue['id'], 'Checked', user='kim')
        clashdata.save_history(DOC, {'Ducts vs Beams': [{'key': 'k1', 'test': 'Ducts vs Beams',
                                                          'status': 'New', 'distance_m': -0.02}]},
                               label='Week 40')
        out = os.path.join(folder, 'bi')
        result = reports.run('kpi_export', {'folder': out}, doc=FakeDoc(DOC), interactive=False)
        assert result['level'] == 'warning', result                  # clash tables noted as empty
        assert 'Clash Detective is not available' in result['detail']
        target = os.path.join(out, 'Coordination KPI')
        names = sorted(os.listdir(target))
        assert names == sorted(['README.txt'] + ['%s.%s' % (t, e) for t in rep_kpi_export.TABLE_NAMES
                                                  for e in ('csv', 'json')])
        with open(os.path.join(target, 'issues.csv'), 'rb') as handle:
            data = handle.read()
        assert data.startswith(b'\xef\xbb\xbf') and data.count(b'\r\n') == 3
        with io.open(os.path.join(target, 'issue_comments.json'), encoding='utf-8') as handle:
            comments = json.load(handle)
        assert comments[-1]['text'] == 'Checked'
        with io.open(os.path.join(target, 'clash_history.json'), encoding='utf-8') as handle:
            history = json.load(handle)
        assert len(history) == 1 and history[0]['history_label'] == 'Week 40'
        flat = reports.run('kpi_export', {'folder': out, 'name_template': '', 'tables': ['issues'],
                                          'formats': ['csv']}, doc=FakeDoc(DOC), interactive=False)
        assert flat['level'] == 'success' and os.path.exists(os.path.join(out, 'issues.csv'))
    finally:
        paths.redirect(previous)
