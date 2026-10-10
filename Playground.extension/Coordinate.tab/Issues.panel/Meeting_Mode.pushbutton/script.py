# -*- coding: utf-8 -*-
"""Runs a coordination meeting through the chosen issues, one at a time, and writes the minutes."""
from pynavis import script, toast

from namo import config, issue_meeting, issueapi, issuestore, ui


def run():
    if ui.is_runner():
        toast.info('Meeting mode needs the Navisworks window', 'It cannot run under pynavis run.')
        return
    if issue_meeting.activate_open():
        toast.info('A meeting is already running', 'End it in the Meeting mode window before '
                   'starting another.')
        return
    doc = issuestore.active_doc()
    if doc is None or not issueapi.has_model(doc):
        toast.info('No model open', 'Open the model the issues belong to, then start the meeting.')
        return
    store = issuestore.for_doc(doc)
    if not store.saved:
        toast.info('Save the model first', issuestore.NOT_SAVED)
        return
    rows = store.list()
    if not rows:
        toast.info('No issues yet', 'Raise issues in the Issues panel, with Issue Stamps or Clash '
                   'to Issues, then run the meeting.')
        return
    me = script.bind()
    saved = me.get_config(dict(issue_meeting.DEFAULTS))
    answers = ui.form('Meeting mode', issue_meeting.filter_fields(rows, saved),
                      intro='Which issues go on the agenda?', ok='Start meeting', width=520)
    if answers is None:
        return
    saved.update(answers)
    me.save_config(saved)
    chosen = issue_meeting.choose(rows, answers)
    if not chosen:
        toast.info('No issues match', 'Tick more statuses, trades or priorities, or allow any due date.')
        return
    issue_meeting.open_window([i['id'] for i in chosen], store, doc, me, script.get_logger(),
                              follow=bool(answers['follow']), user=config.user_name())


run()
