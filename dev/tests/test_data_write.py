# -*- coding: utf-8 -*-
"""namo.data_write pure half: write summaries, preview status, plans from matches,
paths, preview rows and data link ids."""
import _compat  # noqa: F401  (puts lib on sys.path)
import os

from namo import data_write, propwrite


def test_write_summary():
    assert data_write.write_summary({'written': 3, 'unchanged': 0, 'errors': []}) == (
        'success', 'Wrote 3 items', '')
    assert data_write.write_summary({'written': 1, 'unchanged': 2, 'errors': []})[2] == \
        '2 already up to date.'
    assert data_write.write_summary({'written': 0, 'unchanged': 4, 'errors': []})[0] == 'info'
    level, message, detail = data_write.write_summary({'written': 2, 'unchanged': 0, 'errors': ['Wall: denied']})
    assert (level, message, detail) == ('warning', 'Wrote 2 items, 1 failed', 'Wall: denied')
    stopped = data_write.write_summary({'written': 40, 'unchanged': 0, 'errors': [], 'stopped': True})
    assert stopped[:2] == ('warning', 'Stopped after 40 items')
    # Refit: no toast promises an undo step nobody has seen work for COM-written tabs.
    for outcome in ({'written': 3, 'unchanged': 0, 'errors': []},
                    {'written': 40, 'unchanged': 0, 'errors': [], 'stopped': True}):
        assert 'undo' not in ' '.join(data_write.write_summary(outcome)).lower()
    assert data_write.sentences('Tab Playground.', '', '2 already up to date.') == 'Tab Playground. 2 already up to date.'
    assert data_write.sentences('', '') == ''


def _matching():
    headers = ['Element ID', 'Status']
    rows = [[1.0, 'A'], [2.0, 'B'], [3.0, 'C'], [1.0, 'D'], ['', 'x']]
    plan = propwrite.plan_rows(headers, rows, 0, propwrite.KEY_ELEMENT_ID, ['Status'])
    index = {'1': ['w1'], '2': ['w2', 'w2b']}
    return plan, propwrite.match_rows(plan['rows'], index)


def test_match_status_and_plan():
    plan, matching = _matching()
    assert data_write.match_status(plan, matching) == (
        '2 matched, 1 not found, 1 match several items, 1 repeated keys (the later row wins), '
        '1 rows without a key')
    targets = data_write.plan_from_matching(matching, 'Data')
    assert targets == [('w1', {'Data': {'Status': 'D'}}), ('w2', {'Data': {'Status': 'B'}}),
                       ('w2b', {'Data': {'Status': 'B'}})]


def test_paths_rows_and_ids():
    folder = os.path.join('C:' + os.sep, 'D')
    assert data_write.unmatched_path(os.path.join(folder, 'assets.xlsx')) == \
        os.path.join(folder, 'assets - unmatched.xlsx')
    changes = [{'item': 'i1', 'category': 'Element', 'property': 'Mark', 'old': 'a', 'new': 'b', 'custom': False},
               {'item': 'i2', 'category': 'Playground', 'property': 'Note', 'old': 'a', 'new': 3, 'custom': True}]
    rows = data_write.change_rows(changes)
    assert rows[0]['cells'] == ['i1', 'Playground Corrected', 'Element - Mark', 'a', 'b']
    assert rows[1]['cells'] == ['i2', 'Playground', 'Note', 'a', '3']
    cov = data_write.coverage_rows([('A.rvt', 'System', 4, 3, 0.75)])
    assert cov == [{'cells': ['A.rvt', 'System', 4, 3, '75%'], 'value': 0}]
    assert data_write.next_link_id([]) == 'L001'
    assert data_write.next_link_id([{'id': 'L002'}, {'id': 'L010'}, {'id': 'x'}]) == 'L011'


def test_example_profile_reads():
    profile, problems = propwrite.parse_profile(data_write.EXAMPLE_PROFILE)
    assert problems == []
    assert propwrite.field_names(profile) == ['System', 'Level', 'Mark']
