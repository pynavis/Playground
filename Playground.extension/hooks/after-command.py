# -*- coding: utf-8 -*-
"""Hands the 'after-command' event to every Playground tool that listens for it (see lib/namo/hooks.py).

One file per event is all pyNavis allows, so the tools share it through a dispatcher
that isolates each handler: one tool raising never disables the others. Nothing may
escape this file either: pyNavis switches a hook off for the session after three
failures in a row, which would silently take every listener down with it. A problem
(the namo library itself failing to import) goes to the pyNavis log instead.
"""
try:
    from namo import hooks
    hooks.dispatch('after-command', __event__)
except Exception:
    try:
        import traceback
        from pynavis import script
        script.get_logger().error('Playground: the after-command hook could not run: ' + traceback.format_exc())
    except Exception:
        pass
