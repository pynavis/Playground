# -*- coding: utf-8 -*-
"""hk_clashhistory: the automatic snapshot on save. The decision is pure and checked in
order; take() runs through the fake Navisworks layer; handle() is quiet when off."""
import datetime
import os

import _compat  # noqa: F401

import test_clashreport as fx
from namo import hk_clashhistory as hk

NOW = datetime.datetime(2026, 10, 5, 12, 0)
ON = dict(hk.DEFAULTS, auto_on_save=True)


def _entry(hours_ago, counts):
    when = NOW - datetime.timedelta(hours=hours_ago)
    return {'id': 'h%d' % hours_ago, 'time': when.strftime('%Y-%m-%dT%H:%M:%S'), 'counts': counts}


def test_load_config_normalises():
    assert hk.load_config(lambda tool, defaults: {'auto_on_save': 1, 'max_results': '20', 'min_hours': 'x',
                                                  'tests': 'nope'}) == \
        {'auto_on_save': True, 'max_results': 20, 'min_hours': 4.0, 'tests': []}
    assert hk.load_config(lambda tool, defaults: 1 / 0) == hk.DEFAULTS
    assert hk.DEFAULTS['auto_on_save'] is False and hk.DEFAULTS['max_results'] == 50000


def test_decide_order():
    counts = {'A': {'New': 3, 'Active': 1}}
    assert hk.decide(hk.DEFAULTS, 'C:/m.nwf', 'local', [], counts, NOW) == (False, 'off')
    assert not hk.decide(ON, '', 'local', [], counts, NOW)[0]
    go, reason = hk.decide(ON, 'C:/m.nwf', 'model', [], counts, NOW)
    assert not go and 'kept in the model' in reason
    go, reason = hk.decide(ON, 'C:/m.nwf', 'local', [_entry(1, {})], counts, NOW)
    assert not go and 'less than 4 hours' in reason
    assert hk.decide(ON, 'C:/m.nwf', 'local', [_entry(5, {})], None, NOW) == (True, '')
    assert hk.decide(ON, 'C:/m.nwf', 'local', [], {'A': {'New': 0}}, NOW) == (False, 'no clash results')
    capped = dict(ON, max_results=3)
    go, reason = hk.decide(capped, 'C:/m.nwf', 'shared', [], counts, NOW)
    assert not go and reason == '4 results are over the 3 cap'
    same = _entry(9, {'A': {'total': 4, 'by_status': {'new': 3, 'Active': 1, 'Resolved': 0}}})
    go, reason = hk.decide(ON, 'C:/m.nwf', 'local', [same], counts, NOW)
    assert not go and 'have not changed' in reason
    changed = _entry(9, {'A': {'total': 4, 'by_status': {'New': 2, 'Active': 2}}})
    assert hk.decide(ON, 'C:/m.nwf', 'local', [changed], counts, NOW) == (True, '')
    more_tests = _entry(9, {'A': {'total': 4, 'by_status': {'New': 3, 'Active': 1}}, 'B': {'total': 0}})
    assert hk.decide(ON, 'C:/m.nwf', 'local', [more_tests], counts, NOW) == (True, '')


def test_handle_is_silent_when_off():
    with fx.Redirected('hk-clashhistory-off'):
        hk.handle('doc-saved', {'name': 'doc-saved'})
        hk.handle('doc-opened', {'name': 'doc-opened'})


def test_take_records_once_then_waits():
    doc, test_a, test_b = fx.fake_clash_doc()
    from namo import clashdata
    with fx.Redirected('hk-clashhistory-take') as folder:
        doc.FileName = os.path.join(folder, 'Hospital.nwf')
        now = datetime.datetime.now().replace(microsecond=0)     # snapshots are stamped with the clock
        with fx.nav.FakeNav(doc):
            entry, reason = hk.take(ON, doc, now)
            assert reason == '' and entry is not None and entry['label'] == now.strftime('Saved %Y-%m-%d %H:%M')
            assert sorted(entry['counts']) == ['Ducts vs Walls', 'Walls vs Walls']
            again, reason = hk.take(ON, doc, now + datetime.timedelta(hours=1))
            assert again is None and 'less than 4 hours' in reason
            later, reason = hk.take(ON, doc, now + datetime.timedelta(hours=5))
            assert later is None and 'have not changed' in reason
            test_a.Children[0].Status = fx.nav._Enum('Resolved')
            later, reason = hk.take(dict(ON, tests=['Ducts vs Walls']), doc, now + datetime.timedelta(hours=5))
            assert later is not None and sorted(later['counts']) == ['Ducts vs Walls']
            assert len(clashdata.list_history(doc.FileName)) == 2
