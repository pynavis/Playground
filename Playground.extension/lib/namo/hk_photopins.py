# -*- coding: utf-8 -*-
"""Photo Pins: redraws the opened document's photo pins in the view (doc-opened) and
clears them when the document closes (doc-closed).

Registered in namo.hooks. Fast and guarded: it ends in photopins.refresh, the same call
the button, its Shift+Click settings and Photo Browser use, so the view always agrees
with the Show pins setting: on, the opened document's pins are drawn (the previous
document's are cleared); off, nothing stays drawn. Never raises; problems go to the
pyNavis log.
"""


def handle(name, event):
    if name not in ('doc-opened', 'doc-closed'):
        return
    try:
        from namo import photopins
        if name == 'doc-closed':
            photopins.clear_drawn()
            return
        photopins.refresh()
    except Exception as error:
        try:
            from namo import session
            session.log('warning', 'photo pins not redrawn on %s: %s' % (name, error))
        except Exception:
            pass
