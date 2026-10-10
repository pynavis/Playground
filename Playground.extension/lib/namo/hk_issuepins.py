# -*- coding: utf-8 -*-
"""Issue Pins: redraws the opened document's issue pins when Issue Pins is on (doc-opened),
and clears them when the document closes (doc-closed).

Registered in namo.hooks for doc-opened and doc-closed. Fast and guarded: when pins are
off (the session flag Issue Pins sets) it returns at once; otherwise it reads the new document's
register (small JSON files, or the model's database) and draws its open issues,
clearing the previous document's pins. Never raises; problems go to the pyNavis log.
"""


def handle(name, event):
    if name not in ('doc-opened', 'doc-closed'):
        return
    try:
        from namo import issueapi
        if not issueapi.pins_on():
            return
        if name == 'doc-closed':
            issueapi.clear_pins()
            return
        issueapi.redraw_pins()
    except Exception as error:
        try:
            from namo import session
            session.log('warning', 'issue pins not redrawn on %s: %s' % (name, error))
        except Exception:
            pass
