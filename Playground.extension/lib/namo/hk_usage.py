# -*- coding: utf-8 -*-
"""Usage Analytics hook: before-command stamps the time, after-command appends one line.

Off unless the user opted in (Usage Analytics asks on its first click). Records the
bundle key, title, user, machine and duration only: never a document name. While it is
off, a cached 'enabled: False' in the session returns before anything is imported.
"""
import time


def command_of(event):
    """The bundle key in the event, or None. pyNavis' __event__ is a .NET
    Dictionary[str, object] (no .get() under IronPython 3.4): read it with 'in' and []."""
    if event is None:
        return None
    try:
        return event['command'] if 'command' in event else None
    except Exception:
        return None


def handle(name, event):
    if name not in ('before-command', 'after-command'):
        return
    command = command_of(event)
    if not command:
        return
    from namo import session
    holder = session.holder('usage')
    settings = getattr(holder, 'settings', None)
    if settings is not None and not settings.get('enabled') and \
            time.time() - getattr(holder, 'loaded', 0) < 30.0:
        return
    from namo import usage
    if name == 'before-command':
        usage.before(command)
    else:
        usage.after(command)
