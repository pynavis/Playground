# -*- coding: utf-8 -*-
"""namo.config: Playground-wide settings through pynavis.settings (never the real %APPDATA%)."""
import io
import json
import os
import sys

import _compat
from _compat import raises

from namo import config, paths

# Exercise the real pynavis.settings under CPython too (it is stdlib-only).
_PYNAVISLIB = _compat.PYNAVISLIB
if not _compat.IRONPYTHON and os.path.isdir(_PYNAVISLIB) and _PYNAVISLIB not in sys.path:
    sys.path.append(_PYNAVISLIB)


def isolated(fn):
    def wrapper():
        folder = _compat.tmpdir('f2-config-' + fn.__name__)
        previous = paths.redirect(folder)
        try:
            return fn(folder)
        finally:
            paths.redirect(previous)
    wrapper.__name__ = fn.__name__
    return wrapper


def test_defaults_match_the_contract():
    d = config.DEFAULTS
    assert sorted(d) == sorted(['user', 'project_name', 'project_number', 'company', 'data_mode',
                                'shared_root', 'trades', 'trade_rules', 'report_units',
                                'date_format'])
    assert d['data_mode'] == 'local' and d['report_units'] == 'auto'
    assert d['date_format'] == '%Y-%m-%d' and d['trade_rules'] == [] and d['shared_root'] == ''
    assert d['trades'] == ['Architecture', 'Structure', 'Mechanical', 'Electrical', 'Plumbing',
                           'Fire Protection', 'Civil', 'Unassigned']
    assert d['user']                                        # the Windows user name
    copy = config.defaults()
    copy['trades'].append('X')
    assert 'X' not in config.DEFAULTS['trades']


@isolated
def test_settings_file_lives_under_the_redirect(folder):
    assert config.path() == os.path.join(folder, 'pyNavis', 'settings', 'playground.json')
    assert not os.path.exists(config.path())
    assert config.load() == config.normalise(config.defaults())


@isolated
def test_save_merges_and_round_trips(folder):
    saved = config.save({'company': ' Acme ', 'unknown_key': 1})
    assert saved['company'] == 'Acme' and 'unknown_key' not in saved
    config.save({'project_name': 'Tower'})
    cfg = config.load()
    assert cfg['company'] == 'Acme' and cfg['project_name'] == 'Tower'
    assert config.get('company') == 'Acme'
    assert config.get('nope', 'fallback') == 'fallback'
    with io.open(config.path(), 'r', encoding='utf-8') as handle:
        stored = json.load(handle)
    assert stored['company'] == 'Acme'


@isolated
def test_normalise_repairs_bad_values(folder):
    cfg = config.normalise({'data_mode': 'cloud', 'report_units': 'furlongs',
                            'trades': ['A', '', 'A', ' B '], 'trade_rules': [['^x', 'X'], ['(', 'bad'],
                                                                            'junk', ['ok', '']],
                            'date_format': '', 'user': '  '})
    assert cfg['data_mode'] == 'local' and cfg['report_units'] == 'auto'
    assert cfg['trades'] == ['A', 'B']
    assert cfg['trade_rules'] == [['^x', 'X']]
    assert cfg['date_format'] == '%Y-%m-%d'
    assert cfg['user']                                      # never empty
    assert config.normalise({'trades': 'nope'})['trades'] == config.DEFAULT_TRADES
    assert config.normalise({'data_mode': 'SHARED'})['data_mode'] == 'shared'


@isolated
def test_damaged_file_reads_as_defaults(folder):
    paths.ensure_dir(os.path.dirname(config.path()))
    with io.open(config.path(), 'w', encoding='utf-8') as handle:
        handle.write(u'{broken')
    assert config.load()['data_mode'] == 'local'
    with io.open(config.path(), 'w', encoding='utf-8') as handle:
        handle.write(u'[1, 2]')
    assert config.load()['trades'] == config.DEFAULT_TRADES


@isolated
def test_user_name(folder):
    assert config.user_name()
    config.save({'user': 'Pat Doe'})
    assert config.user_name() == 'Pat Doe'


@isolated
def test_builtin_backend_matches_pynavis_settings_layout(folder):
    backend = config._BuiltinSettings()
    backend._APPDATA_OVERRIDE = folder
    assert backend.path_for('playground') == os.path.join(folder, 'pyNavis', 'settings', 'playground.json')
    backend.save('playground', {'company': 'Builtin', 'user': 'x'})
    assert backend.load('playground', {'company': '', 'other': 1}) == {'company': 'Builtin', 'other': 1}
    assert config.load()['company'] == 'Builtin'            # either backend reads the same file


def test_real_appdata_is_never_touched_by_the_seam():
    folder = _compat.tmpdir('f2-config-seam')
    previous = paths.redirect(folder)
    try:
        assert config.path().startswith(folder)
    finally:
        paths.redirect(previous)
    try:
        from pynavis import settings
    except ImportError:
        return
    assert settings._APPDATA_OVERRIDE is None               # restored after every call


def test_save_raises_when_it_cannot_write():
    folder = _compat.tmpdir('f2-config-blocked')
    previous = paths.redirect(folder)
    try:
        settings_dir = os.path.join(folder, 'pyNavis', 'settings')
        os.makedirs(settings_dir)
        os.makedirs(os.path.join(settings_dir, 'playground.json'))  # a folder where the file goes
        raises(EnvironmentError, config.save, {'company': 'x'})
    finally:
        paths.redirect(previous)
