# -*- coding: utf-8 -*-
"""Playground Settings: the form over namo.config (user, project, company, where team data
lives, trades and trade rules, report units, date format).

Pure half (tested): text <-> list conversions for the two multi-line fields, the field
specs for namo.ui.form, validation (shared folder reachable when the mode needs it,
every trade rule compiles, the date format works) and the values handed to
namo.config.save.
"""
import datetime
import os
import re

MODE_OPTIONS = [('This computer only', 'local'), ('A shared folder (team)', 'shared'),
                ('Inside the model (NWF/NWD)', 'model')]
UNIT_OPTIONS = [('Document units', 'auto'), ('Millimetres', 'mm'), ('Metres', 'm'),
                ('Feet', 'ft'), ('Inches', 'in')]
DATE_OPTIONS = ['%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%d.%m.%Y', '%d %b %Y']


def trades_text(trades):
    return '\n'.join(trades or [])


def parse_trades(text):
    """Non-empty, de-duplicated (case-insensitive) trade names, order kept."""
    out = []
    seen = set()
    for line in (text or '').splitlines():
        name = line.strip()
        if name and name.lower() not in seen:
            seen.add(name.lower())
            out.append(name)
    return out


def rules_text(rules):
    return '\n'.join('%s = %s' % (pattern, trade) for pattern, trade in (rules or []))


def parse_rules(text):
    """([[regex, trade]], [sentence]) from 'regex = Trade' lines (the last '=' splits,
    so a pattern may hold '='). Blank lines and lines starting with # are skipped."""
    rules = []
    errors = []
    for number, line in enumerate((text or '').splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
        if '=' not in stripped:
            errors.append('Line %d: write it as pattern = Trade.' % number)
            continue
        pattern, trade = stripped.rsplit('=', 1)
        pattern, trade = pattern.strip(), trade.strip()
        if not pattern or not trade:
            errors.append('Line %d: both the pattern and the trade are needed.' % number)
            continue
        try:
            re.compile(pattern)
        except re.error as error:
            errors.append('Line %d: the pattern does not work (%s).' % (number, error))
            continue
        rules.append([pattern, trade])
    return rules, errors


def date_example(fmt):
    try:
        return datetime.datetime(2026, 10, 5, 14, 30).strftime(fmt)
    except Exception:
        return None


def fields(cfg):
    """namo.ui.form fields for the current settings."""
    fmt = cfg.get('date_format') or '%Y-%m-%d'
    date_choices = [('%s  (%s)' % (date_example(f), f), f) for f in DATE_OPTIONS]
    if fmt not in DATE_OPTIONS:
        date_choices.append(('%s  (%s)' % (date_example(fmt) or fmt, fmt), fmt))
    return [
        {'kind': 'text', 'key': 'user', 'label': 'Your name', 'default': cfg.get('user', ''),
         'hint': 'Stamped on comments, issues and reports.', 'required': True},
        {'kind': 'text', 'key': 'company', 'label': 'Company', 'default': cfg.get('company', '')},
        {'kind': 'text', 'key': 'project_name', 'label': 'Project name', 'default': cfg.get('project_name', '')},
        {'kind': 'text', 'key': 'project_number', 'label': 'Project number',
         'default': cfg.get('project_number', '')},
        {'kind': 'separator'},
        {'kind': 'radio', 'key': 'data_mode', 'label': 'Keep Playground data on',
         'options': MODE_OPTIONS, 'default': cfg.get('data_mode', 'local'), 'fallback': 'local'},
        {'kind': 'folder', 'key': 'shared_root', 'label': 'Shared folder', 'default': cfg.get('shared_root', ''),
         'hint': 'A network folder everyone can write to. Templates and presets live here whenever it is set.'},
        {'kind': 'separator'},
        {'kind': 'textarea', 'key': 'trades', 'label': 'Trades (one per line)', 'rows': 5,
         'default': trades_text(cfg.get('trades'))},
        {'kind': 'textarea', 'key': 'trade_rules', 'label': 'Trade rules (pattern = Trade, one per line)', 'rows': 4,
         'default': rules_text(cfg.get('trade_rules')),
         'hint': 'Matched against model file names before the built-in rules, e.g. \\bmep\\b = Mechanical'},
        {'kind': 'choice', 'key': 'report_units', 'label': 'Report units', 'options': UNIT_OPTIONS,
         'default': cfg.get('report_units', 'auto'), 'fallback': 'auto'},
        {'kind': 'choice', 'key': 'date_format', 'label': 'Date format', 'options': date_choices, 'default': fmt, 'fallback': None},
    ]


def validate(values, folder_exists=None):
    """{key: sentence} for problems (empty when everything is fine)."""
    exists = folder_exists or os.path.isdir
    problems = {}
    if not (values.get('user') or '').strip():
        problems['user'] = 'Enter your name.'
    shared = (values.get('shared_root') or '').strip()
    if values.get('data_mode') == 'shared' and not shared:
        problems['shared_root'] = 'Pick the shared folder, or keep data on this computer.'
    elif shared and not exists(shared):
        problems['shared_root'] = 'That folder cannot be reached right now.'
    _rules, errors = parse_rules(values.get('trade_rules'))
    if errors:
        problems['trade_rules'] = errors[0]
    if not parse_trades(values.get('trades')):
        problems['trades'] = 'List at least one trade.'
    if date_example(values.get('date_format') or '') is None:
        problems['date_format'] = 'That date format does not work.'
    return problems


def to_config(values):
    """The dict for namo.config.save."""
    rules, _errors = parse_rules(values.get('trade_rules'))
    return {'user': (values.get('user') or '').strip(), 'company': (values.get('company') or '').strip(),
            'project_name': (values.get('project_name') or '').strip(),
            'project_number': (values.get('project_number') or '').strip(),
            'data_mode': values.get('data_mode') or 'local',
            'shared_root': (values.get('shared_root') or '').strip(),
            'trades': parse_trades(values.get('trades')), 'trade_rules': rules,
            'report_units': values.get('report_units') or 'auto',
            'date_format': values.get('date_format') or '%Y-%m-%d'}


def summary(saved):
    """The toast detail after saving."""
    where = dict((v, l) for l, v in MODE_OPTIONS).get(saved.get('data_mode'), saved.get('data_mode'))
    text = 'Data: %s' % where[:1].lower() + where[1:]
    if saved.get('shared_root'):
        text += ', shared folder %s' % saved['shared_root']
    return text + '.'
