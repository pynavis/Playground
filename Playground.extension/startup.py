# -*- coding: utf-8 -*-
"""Runs the Playground startup handlers (see lib/namo/hooks.py) at boot and on every Reload.

Silent when all is well. Nothing may escape: a startup.py that raises makes pyNavis
toast "Playground startup.py failed" on every Reload. A problem (the namo library itself
failing to import) goes to the pyNavis log instead.
"""
try:
    from namo import hooks
    hooks.dispatch('startup', {'name': 'startup', 'runner': bool(globals().get('__runner__', False))})
except Exception:
    try:
        import traceback
        from pynavis import script
        script.get_logger().error('Playground: startup could not run: ' + traceback.format_exc())
    except Exception:
        pass
