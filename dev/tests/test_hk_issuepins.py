# -*- coding: utf-8 -*-
"""hk_issuepins: registered for doc-opened, quiet when pins are off, never raises when on
outside Navisworks (the failure is logged), ignores other events."""
import _compat

from namo import hk_issuepins, hooks, issueapi, session


def test_registered_for_doc_opened():
    assert 'hk_issuepins' in hooks.handlers_for('doc-opened')


def test_off_is_silent_and_on_never_raises():
    before = len(session.recent_log())
    issueapi.set_pins_on(False)
    hk_issuepins.handle('doc-opened', {'name': 'doc-opened'})
    hk_issuepins.handle('selection-changed', {'name': 'selection-changed'})
    assert len(session.recent_log()) == before
    issueapi.set_pins_on(True)
    try:
        hk_issuepins.handle('doc-opened', {'name': 'doc-opened'})
        hk_issuepins.handle('doc-closed', {'name': 'doc-closed'})
    finally:
        issueapi.set_pins_on(False)
    assert issueapi.pins_on() is False
