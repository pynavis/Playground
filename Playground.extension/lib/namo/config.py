# -*- coding: utf-8 -*-
"""Playground-wide settings: one JSON file shared by every Playground tool.

Stored through pynavis.settings under the tool key 'playground', i.e.
%APPDATA%\\pyNavis\\settings\\playground.json. Per-tool options belong in each bundle's own
script.get_config(); this file holds what several tools agree on: who the user is, the
project, where team data lives, the trade list and classification rules, report units and
the date format.

    cfg = config.load()                 # DEFAULTS overlaid with the saved values, normalised
    config.save({'company': 'Acme'})    # writes the given keys over the current values
    config.get('data_mode')             # one value
    config.user_name()                  # never empty

Pure stdlib (pynavis.settings is stdlib-only). Outside the pyNavis runtime, where
pynavis is not importable, an identical built-in reader/writer is used, so this module
imports and works anywhere. Test seam: _APPDATA_OVERRIDE (set it with
namo.paths.redirect(folder)), never the real %APPDATA%.
"""
import copy
import datetime
import json
import os
import re

TOOL = 'playground'

# Test seam: a folder used instead of %APPDATA% for the settings file.
_APPDATA_OVERRIDE = None

MODES = ('local', 'shared', 'model')
REPORT_UNITS = ('auto', 'mm', 'm', 'ft', 'in')
DEFAULT_TRADES = ['Architecture', 'Structure', 'Mechanical', 'Electrical', 'Plumbing',
                  'Fire Protection', 'Civil', 'Unassigned']


def _windows_user():
    return (os.environ.get('USERNAME') or os.environ.get('USER') or 'user').strip() or 'user'


DEFAULTS = {
    'user': _windows_user(),     # the Windows user name until someone sets a display name
    'project_name': '',
    'project_number': '',
    'company': '',
    'data_mode': 'local',        # 'local' | 'shared' | 'model' (inside the NWF/NWD via docdb)
    'shared_root': '',           # network folder for team data
    'trades': list(DEFAULT_TRADES),
    'trade_rules': [],           # [[regex, trade], ...] checked before trades.DEFAULT_RULES
    'report_units': 'auto',      # 'auto' (document units) | 'mm' | 'm' | 'ft' | 'in'
    'date_format': '%Y-%m-%d',
}


# ---- the pynavis.settings backend (or an identical stand-in) -------------------


class _BuiltinSettings(object):
    """Same file, same rules as pynavis.settings, for engines where pynavis is absent."""

    _APPDATA_OVERRIDE = None

    def _root(self):
        base = self._APPDATA_OVERRIDE or os.environ.get('APPDATA', '')
        return os.path.join(base, 'pyNavis', 'settings')

    def path_for(self, tool):
        return os.path.join(self._root(), tool + '.json')

    def load(self, tool, defaults):
        try:
            with open(self.path_for(tool), 'r') as handle:
                stored = json.load(handle)
        except Exception:
            return dict(defaults)
        if not isinstance(stored, dict):
            return dict(defaults)
        result = dict(defaults)
        for key in defaults:
            if key in stored:
                result[key] = stored[key]
        return result

    def save(self, tool, values):
        from namo import paths
        paths.ensure_dir(self._root())
        paths.atomic_write_text(self.path_for(tool), json.dumps(values, indent=2, sort_keys=True))


_BUILTIN = _BuiltinSettings()


def _backend():
    try:
        from pynavis import settings
        return settings
    except ImportError:
        return _BUILTIN


def _with_backend(fn):
    """Runs fn(backend) with this module's override applied to the backend, then restores it."""
    backend = _backend()
    if _APPDATA_OVERRIDE is None:
        return fn(backend)
    previous = getattr(backend, '_APPDATA_OVERRIDE', None)
    backend._APPDATA_OVERRIDE = _APPDATA_OVERRIDE
    try:
        return fn(backend)
    finally:
        backend._APPDATA_OVERRIDE = previous


# ---- public API -------------------------------------------------------------------


def defaults():
    """A deep copy of DEFAULTS (safe to mutate)."""
    return copy.deepcopy(DEFAULTS)


def path():
    """The settings file: %APPDATA%\\pyNavis\\settings\\playground.json."""
    return _with_backend(lambda b: b.path_for(TOOL))


def _text(value, fallback=''):
    if value is None:
        return fallback
    return str(value).strip()


def _valid_rule(pair):
    if not isinstance(pair, (list, tuple)) or len(pair) != 2:
        return False
    pattern, trade = pair
    if not isinstance(pattern, str) or not pattern.strip() or not _text(trade):
        return False
    try:
        re.compile(pattern)
    except Exception:
        return False
    return True


def normalise(values):
    """values (a full settings dict) with every key checked: unknown modes and units fall
    back to their defaults, text is stripped, trades become a list of non-empty names,
    trade_rules keep only [regex, trade] pairs whose regex compiles, and a date_format
    that strftime cannot use becomes '%Y-%m-%d'. Returns a new dict."""
    out = defaults()
    for key in DEFAULTS:
        if key in values:
            out[key] = copy.deepcopy(values[key])
    for key in ('user', 'project_name', 'project_number', 'company', 'shared_root'):
        out[key] = _text(out.get(key))
    if not out['user']:
        out['user'] = _windows_user()
    mode = _text(out.get('data_mode')).lower()
    out['data_mode'] = mode if mode in MODES else 'local'
    units = _text(out.get('report_units')).lower()
    out['report_units'] = units if units in REPORT_UNITS else 'auto'
    trades = out.get('trades')
    if isinstance(trades, (list, tuple)):
        names = []
        for name in trades:
            name = _text(name)
            if name and name not in names:
                names.append(name)
        out['trades'] = names or list(DEFAULT_TRADES)
    else:
        out['trades'] = list(DEFAULT_TRADES)
    rules = out.get('trade_rules')
    out['trade_rules'] = ([[p[0], _text(p[1])] for p in rules if _valid_rule(p)]
                          if isinstance(rules, (list, tuple)) else [])
    fmt = out.get('date_format')
    try:
        if not isinstance(fmt, str) or not fmt.strip():
            raise ValueError
        datetime.datetime(2026, 1, 31, 13, 45).strftime(fmt)
    except Exception:
        fmt = '%Y-%m-%d'
    out['date_format'] = fmt
    return out


def load():
    """DEFAULTS overlaid with the saved settings, normalised. Never raises: a missing or
    damaged file gives the defaults (pynavis.settings.load never raises)."""
    try:
        stored = _with_backend(lambda b: b.load(TOOL, defaults()))
    except Exception:
        stored = defaults()
    return normalise(stored)


def save(values):
    """Writes values (any subset of the keys; unknown keys are ignored) over the current
    settings and returns the full normalised dict that was saved. Raises IOError/OSError
    when the file cannot be written."""
    current = load()
    for key in DEFAULTS:
        if key in values:
            current[key] = values[key]
    current = normalise(current)
    _with_backend(lambda b: b.save(TOOL, current))
    return current


def get(key, default=None):
    """One setting (normalised); default for a key that is not a Playground setting."""
    if key not in DEFAULTS:
        return default
    return load()[key]


def user_name():
    """The display name for stamps and 'assigned to' fields: config 'user', else the
    Windows user name. Never empty."""
    return load()['user'] or _windows_user()
