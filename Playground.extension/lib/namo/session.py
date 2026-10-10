# -*- coding: utf-8 -*-
"""State that outlives one run, plus the one logger every namo module shares.

pyNavis drops every module whose file lives under an extension's lib folder from
sys.modules before each run, so module globals in lib\\namo are fresh on every click.
Anything that must survive (an open window, a timer, an event subscription, a cache)
lives on a holder: a plain module object registered under 'playground_<key>' in
sys.modules. It has no __file__, so the per-run sweep never removes it, and it lasts
for the life of the engine (until Navisworks closes).

Pure stdlib; imports nothing from Navisworks.
"""
import sys
import time
import types

PREFIX = 'playground_'
LOG_KEEP = 200


def holder(key):
    """The module object stored under sys.modules['playground_' + key], created on first use.

    Set attributes on it freely: holder('camsync').timer = t. The same object comes back
    on every later call in this engine's life, whichever tool asks.
    """
    name = PREFIX + str(key)
    existing = sys.modules.get(name)
    if existing is None:
        existing = types.ModuleType(name)
        sys.modules[name] = existing
    return existing


def get(key, attr, default=None):
    """holder(key).attr, or default when the attribute was never set."""
    return getattr(holder(key), attr, default)


def set(key, attr, value):  # noqa: A001 (contract name; shadows the builtin inside this module)
    """Stores value as holder(key).attr and returns it."""
    setattr(holder(key), attr, value)
    return value


def clear(key):
    """Forgets a holder completely (its attributes go with it). True when one existed."""
    name = PREFIX + str(key)
    if name in sys.modules:
        del sys.modules[name]
        return True
    return False


def keys():
    """Sorted keys of every holder created so far (without the 'playground_' prefix)."""
    return sorted(name[len(PREFIX):] for name in list(sys.modules) if name.startswith(PREFIX))


# ---- logging --------------------------------------------------------------------


def _pynavis_logger():
    try:
        from pynavis import script
        return script.get_logger()
    except Exception:
        return None


def log(level, message):
    """Writes one line to the pyNavis log ('debug' | 'info' | 'warning' | 'error').

    Inside Navisworks this goes through pynavis.script.get_logger(): the pyNavis log
    file, and warnings/errors also echo into an output window that is ALREADY open
    (a log call never opens one). Outside the runtime (CPython tests) the line is
    only kept in memory. Either way the last 200 lines are readable through
    recent_log(), which tests use to assert that something was logged. Never raises.
    """
    level = level if level in ('debug', 'info', 'warning', 'error', 'success') else 'info'
    text = 'Playground: %s' % (message,)
    try:
        lines = get('log', 'lines')
        if lines is None:
            lines = set('log', 'lines', [])
        lines.append((time.time(), level, text))
        if len(lines) > LOG_KEEP:
            del lines[:len(lines) - LOG_KEEP]
    except Exception:
        pass
    logger = _pynavis_logger()
    if logger is None:
        return
    try:
        getattr(logger, level)(text)
    except Exception:
        pass


def recent_log(level=None):
    """The last logged lines as [(level, text)], oldest first; filter by level if given."""
    lines = get('log', 'lines') or []
    return [(lvl, text) for _t, lvl, text in lines if level is None or lvl == level]
