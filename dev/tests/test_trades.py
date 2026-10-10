# -*- coding: utf-8 -*-
"""namo.trades: trade classification from model file names."""
import _compat

from namo import trades


def test_common_file_names():
    cases = [
        ('PRJ-ARCH-L01.nwc', 'Architecture'), ('A-101.rvt', 'Architecture'),
        ('Tower_AR_Model.nwc', 'Architecture'), ('Interiors.nwc', 'Architecture'),
        ('S-Frame.rvt', 'Structure'), ('PRJ_STR_Core.nwc', 'Structure'),
        ('Structural Steel.nwc', 'Structure'), ('PRJ_ST_L1.nwc', 'Structure'),
        ('M-Ductwork.nwc', 'Mechanical'), ('PRJ-MECH-L01.nwc', 'Mechanical'),
        ('HVAC_Level 2.nwc', 'Mechanical'), ('MEP_HVAC.nwc', 'Mechanical'),
        ('E-Lighting.nwc', 'Electrical'), ('PRJ-ELEC.nwc', 'Electrical'),
        ('Cable Trays L3.nwc', 'Electrical'),
        ('P-Plumbing.nwc', 'Plumbing'), ('Sanitary Drainage.nwc', 'Plumbing'),
        ('MEP-Plumbing.nwc', 'Plumbing'),
        ('FP-Sprinklers.nwc', 'Fire Protection'), ('Sprinkler_L1.nwc', 'Fire Protection'),
        ('Fire Protection.nwc', 'Fire Protection'), ('PRJ_FP_L2.nwc', 'Fire Protection'),
        ('C-Site.nwc', 'Civil'), ('Civil_Roads.nwc', 'Civil'), ('Topo.nwc', 'Civil'),
    ]
    for name, trade in cases:
        assert trades.trade_of(name) == trade, (name, trades.explain(name), trade)


def test_unassigned_and_false_positives():
    for name in ('Tower A.nwc', 'Block C.nwc', 'MEP.nwc', 'research.nwc', 'Coordination.nwf',
                 'Model.nwd', '', None, 'Federated 2026.nwd', 'Zone E.nwc'):
        assert trades.trade_of(name) == trades.UNASSIGNED, (name, trades.explain(name))


def test_folders_are_ignored():
    assert trades.trade_of(r'\\server\ARCH\Models\M-Ducts.nwc') == 'Mechanical'
    assert trades.trade_of('C:/Mechanical/Tower A.nwc') == 'Unassigned'
    assert trades.basename_of(r'C:\a\B.nwc') == 'b.nwc'


def test_custom_rules_first():
    rules = [(r'\bmep\b', 'Mechanical'), ('[', 'Broken regex is skipped')] + trades.DEFAULT_RULES
    assert trades.trade_of('MEP.nwc', rules) == 'Mechanical'
    assert trades.trade_of('A-101.nwc', [['^a-', 'Arch (custom)']]) == 'Arch (custom)'
    assert trades.trade_of('A-101.nwc', []) == 'Unassigned'
    assert trades.explain('PRJ-MECH.nwc')[0] == 'Mechanical'
    assert trades.explain('nothing.nwc') == ('Unassigned', None)
    assert trades.classify(['A-1.nwc', 'S-1.nwc']) == {'A-1.nwc': 'Architecture', 'S-1.nwc': 'Structure'}


def test_rules_from_config():
    cfg = {'trade_rules': [['^x-', 'Special'], ['(', 'bad'], 'junk', ['', 'empty']]}
    rules = trades.rules_from_config(cfg)
    assert rules[0] == ('^x-', 'Special')
    assert len(rules) == 1 + len(trades.DEFAULT_RULES)
    assert trades.trade_of('X-Thing.nwc', rules) == 'Special'


def test_rules_from_saved_config():
    from namo import config, paths
    folder = _compat.tmpdir('f2-trades-config')
    previous = paths.redirect(folder)
    try:
        config.save({'trade_rules': [['^zz', 'Zed']]})
        assert trades.trade_of('ZZ-model.nwc', trades.rules_from_config()) == 'Zed'
    finally:
        paths.redirect(previous)


def test_default_trades_are_known_names():
    from namo import config
    for _pattern, trade in trades.DEFAULT_RULES:
        assert trade in config.DEFAULT_TRADES, trade
