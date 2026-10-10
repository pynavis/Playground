# -*- coding: utf-8 -*-
"""namo.team_settings: the Playground Settings form's conversions and validation."""
import _compat

from namo import config, paths, team_settings as ts


def test_trades_and_rules_text():
    assert ts.parse_trades(' Arch \n\nmech\nArch\nMech\n') == ['Arch', 'mech']
    assert ts.trades_text(['A', 'B']) == 'A\nB'
    rules, errors = ts.parse_rules('\\bmep\\b = Mechanical\n# note\n\na=b = Odd\nnoequals\n = X\n[bad = Y\n')
    assert rules == [['\\bmep\\b', 'Mechanical'], ['a=b', 'Odd']]
    assert errors[0] == 'Line 5: write it as pattern = Trade.'
    assert errors[1] == 'Line 6: both the pattern and the trade are needed.'
    assert errors[2].startswith('Line 7: the pattern does not work')
    assert ts.rules_text([['x', 'Y']]) == 'x = Y'


def test_fields_reflect_config():
    cfg = config.defaults()
    cfg['date_format'] = '%Y%m%d'
    specs = ts.fields(cfg)
    keys = [f.get('key') for f in specs if f.get('key')]
    assert keys == ['user', 'company', 'project_name', 'project_number', 'data_mode', 'shared_root',
                    'trades', 'trade_rules', 'report_units', 'date_format']
    date = [f for f in specs if f.get('key') == 'date_format'][0]
    assert date['options'][-1] == ('20261005  (%Y%m%d)', '%Y%m%d')
    assert date['options'][0] == ('2026-10-05  (%Y-%m-%d)', '%Y-%m-%d')


def test_validation():
    good = {'user': 'Amy', 'data_mode': 'local', 'shared_root': '', 'trades': 'Arch', 'trade_rules': '',
            'date_format': '%Y-%m-%d'}
    assert ts.validate(good) == {}
    bad = dict(good, user=' ', data_mode='shared', trades='', trade_rules='x', date_format='%Y-%m-%d')
    problems = ts.validate(bad)
    assert problems == {'user': 'Enter your name.',
                        'shared_root': 'Pick the shared folder, or keep data on this computer.',
                        'trade_rules': 'Line 1: write it as pattern = Trade.',
                        'trades': 'List at least one trade.'}
    problems = ts.validate(dict(good, shared_root='\\\\offline\\share'), folder_exists=lambda p: False)
    assert problems == {'shared_root': 'That folder cannot be reached right now.'}


def test_save_roundtrip_into_a_temp_root():
    folder = _compat.tmpdir('team_settings')
    previous = paths.redirect(folder)
    try:
        values = {'user': ' Amy ', 'company': 'Acme', 'project_name': 'Tower', 'project_number': '42',
                  'data_mode': 'local', 'shared_root': '', 'trades': 'Arch\nMech', 'trade_rules': 'arc = Arch',
                  'report_units': 'mm', 'date_format': '%d/%m/%Y'}
        saved = config.save(ts.to_config(values))
        assert saved['user'] == 'Amy' and saved['trades'] == ['Arch', 'Mech']
        assert saved['trade_rules'] == [['arc', 'Arch']] and saved['report_units'] == 'mm'
        assert config.load()['date_format'] == '%d/%m/%Y'
        assert ts.summary(saved) == 'Data: this computer only.'
        assert ts.summary(dict(saved, data_mode='shared', shared_root='S:\\team')) == \
            'Data: a shared folder (team), shared folder S:\\team.'
    finally:
        paths.redirect(previous)
