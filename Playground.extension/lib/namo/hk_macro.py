# -*- coding: utf-8 -*-
"""Macro Recorder hook: while recording, appends each pyNavis command that ran.

Returns at once when nothing is being recorded (a session flag, no file access).
"""


def command_of(event):
    """The bundle key in a before/after-command event, or None.

    pyNavis hands hooks __event__ as a .NET Dictionary[str, object], which has no
    .get() under IronPython 3.4: read it with 'in' and [] (a Python dict works too)."""
    if event is None:
        return None
    try:
        return event['command'] if 'command' in event else None
    except Exception:
        return None


def handle(name, event):
    if name != 'after-command':
        return
    from namo import session
    if not getattr(session.holder('macro_rec'), 'recording', False):
        return
    command = command_of(event)
    if not command:
        return
    from namo import macros
    macros.record_command(command)
