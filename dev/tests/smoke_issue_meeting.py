# -*- coding: utf-8 -*-
"""Meeting Mode under IronPython + WPF: the meeting window built with sample issues through
a fake environment, driven through next/previous, status, decision, assignee/due edits,
screenshot, mark discussed and End meeting (minutes written), and rendered off screen to a PNG in
the test's temp folder."""
import _compat

_compat.require_ironpython()

import os  # noqa: E402

import clr  # noqa: E402

clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')
clr.AddReference('WindowsBase')

import smoke_issueui as pane_smoke  # noqa: E402

from namo import issue_meeting, paths, png  # noqa: E402



def _setup(name):
    folder = _compat.tmpdir('smoke-meeting-' + name)
    previous = paths.redirect(folder)
    store, made = pane_smoke._seed(folder)
    env = pane_smoke.FakeEnv(folder)
    return folder, previous, store, made, env


def test_meeting_flow_and_minutes():
    folder, previous, store, made, env = _setup('flow')
    try:
        ids = [i['id'] for i in issue_meeting.choose(store.list(), {})]
        assert ids[0] == 'RFI-001'
        meeting = issue_meeting.Meeting(ids, store, env, env.doc, follow=True, user='amol')
        win = meeting.build()
        assert win.Content is not None
        assert meeting.counter.Text.startswith('Issue 1 of %d' % len(ids))
        assert meeting.heading.Text.startswith('RFI-001')
        assert not meeting.prev_button.IsEnabled and meeting.next_button.IsEnabled
        assert not meeting.status_buttons['In progress'].IsEnabled
        meeting.go(1)
        assert env.went[-1] == ids[1]
        meeting.go(-1)
        meeting.set_status('Resolved')
        assert store.get('RFI-001')['status'] == 'Resolved'
        assert store.get('RFI-001')['comments'][-1]['text'].startswith('Meeting ')
        meeting.decision_box.Text = 'Lower the duct 150 mm below the beam.'
        meeting.add_decision()
        assert store.get('RFI-001')['comments'][-1]['text'].endswith('Lower the duct 150 mm below the beam.')
        meeting.assignee_box.Text = 'Ken'
        meeting.due_box.Text = 'soon'
        meeting.apply_edits()
        assert meeting.edit_note.Text.startswith('Not a date')
        meeting.due_box.Text = '2030-02-01'
        meeting.apply_edits()
        issue = store.get('RFI-001')
        assert issue['assignee'] == 'Ken' and issue['due'] == '2030-02-01'
        meeting.screenshot()
        assert [i['kind'] for i in store.get('RFI-001')['images']].count('screenshot') == 1
        meeting.mark_discussed()
        assert meeting.log['position'] == 1
        counts = issue_meeting.counts(meeting.log)
        assert counts['decisions'] == 1 and counts['status_changes'] == 1 and counts['reassigned'] == 1
        env.opened = []
        meeting.end()
        assert meeting.finished and env.opened and env.opened[0].endswith('.html')
        assert env.toasts[-1][1] == 'Minutes written'
        meeting._closed()                                       # the Closed event after End: no second write
        assert len(env.opened) == 1
    finally:
        paths.redirect(previous)


def test_ending_with_nothing_done_writes_nothing():
    folder, previous, store, made, env = _setup('empty')
    try:
        meeting = issue_meeting.Meeting([made[1]['id']], store, env, env.doc)
        meeting.build()
        meeting.end()
        assert env.toasts[-1][1] == 'Meeting ended' and not env.opened
    finally:
        paths.redirect(previous)


def test_render_meeting_png():
    folder, previous, store, made, env = _setup('render')
    try:
        ids = [i['id'] for i in issue_meeting.choose(store.list(), {})]
        meeting = issue_meeting.Meeting(ids, store, env, env.doc, user='amol')
        win = meeting.build()
        content = win.Content
        out = pane_smoke._render(content, os.path.join(folder, 'meeting.png'), 900.0, 700.0)
        with open(out, 'rb') as handle:
            data = handle.read()
        assert png.size(data) == (900, 700)
    finally:
        paths.redirect(previous)
