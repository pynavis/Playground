# -*- coding: utf-8 -*-
"""namo.look_ghost: config, trade grouping, chooser rows, labels, records, and the
ghost/clear API through the fake Navisworks layer."""
import datetime

import _compat

from namo import colors, look_ghost, trades

import test_colorize
import test_items as nav


def test_normalize_config_clamps():
    assert look_ghost.normalize_config(None) == {'transparency': 85, 'grey': True, 'trades': []}
    cfg = look_ghost.normalize_config({'transparency': '120', 'grey': 0, 'trades': ['Mechanical', ' ']})
    assert cfg == {'transparency': 95, 'grey': False, 'trades': ['Mechanical']}
    assert look_ghost.normalize_config({'transparency': 'x'})['transparency'] == 85
    assert look_ghost.normalize_config({'transparency': 3})['transparency'] == 10


def test_trade_groups_order():
    names = ['Tower-MECH-L2.nwc', 'Tower-MECH-L10.nwc', 'S-Frame.nwc', 'Site survey.nwc', 'notes.nwc',
             'A-101.nwc']
    groups = look_ghost.trade_groups(names, order=['Structure', 'Architecture', 'Mechanical'])
    assert [t for t, _n in groups] == ['Structure', 'Architecture', 'Mechanical', 'Civil', trades.UNASSIGNED]
    assert dict(groups)['Mechanical'] == ['Tower-MECH-L2.nwc', 'Tower-MECH-L10.nwc']


def test_chooser_rows_and_labels():
    groups = [('Mechanical', ['a.nwc', 'b.nwc', 'c.nwc', 'd.nwc']), ('Plumbing', ['p.nwc'])]
    rows = look_ghost.chooser_rows(groups, 3)
    assert rows[0]['value'] == look_ghost.SELECTION and rows[0]['cells'][1] == '3 items'
    assert rows[1]['cells'] == ['Mechanical', '4 models', 'a.nwc, b.nwc, c.nwc and 1 more']
    assert look_ghost.chooser_rows(groups, 0)[0]['value'] == 'Mechanical'
    assert look_ghost.focus_label(['Mechanical']) == 'Mechanical'
    assert look_ghost.focus_label(['Mechanical', look_ghost.SELECTION, 'Plumbing']) == \
        'Mechanical, Plumbing and the selection'
    assert look_ghost.focus_label([]) == 'nothing'


def test_records():
    cfg = look_ghost.normalize_config({})
    record = look_ghost.make_record([{'m': 'a', 'i': 1}], 'Mechanical', cfg, datetime.datetime(2026, 10, 5, 8, 0, 0))
    assert record['time'] == '2026-10-05T08:00:00' and record['transparency'] == 85
    assert look_ghost.valid_record(record)
    assert not look_ghost.valid_record({'entries': []}) and not look_ghost.valid_record(None)


def test_config_fields():
    fields = look_ghost.config_fields(look_ghost.normalize_config({'transparency': 70, 'grey': False}))
    assert fields[0]['default'] == 70 and fields[1]['default'] is False


def test_api_ghost_resets_previous_in_one_step():
    doc, n = nav.model_tree()
    with test_colorize.fake(doc):
        cfg = look_ghost.normalize_config({'transparency': 80, 'grey': True})
        others = look_ghost.ghost([n['ARCH.nwc']], cfg, previous=[n['Duct']])
        assert [o.DisplayName for o in others] == ['MEP.nwc']
        assert doc.transactions == ['Trade ghost']
        assert doc.Models.calls[0] == ('reset', [n['Duct']], None)
        assert doc.Models.calls[1] == ('color', [n['MEP.nwc']], tuple(c for c in colors.rgb01(colors.GHOST)))
        assert doc.Models.calls[2] == ('transparency', [n['MEP.nwc']], 0.8)
