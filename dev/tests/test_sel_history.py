# -*- coding: utf-8 -*-
"""namo.sel_history: compact states, signatures, the cursor, and skipping its own restores."""
import _compat

from namo import sel_history as sh


def entries(*paths):
    return [{'m': 'Arch.nwc', 'i': 0, 'p': p} for p in paths]


def state(*paths):
    return sh.make_state(entries(*paths), len(paths), '10:00:00', 'Walls')


def test_compact_round_trip():
    data = [{'m': 'A.nwc', 'i': 0, 'p': '0/1'}, {'m': 'B.nwc', 'i': 1, 'p': '0/2'},
            {'m': 'A.nwc', 'i': 0, 'p': '0/3'}]
    models, refs = sh.compact(data)
    assert models == ['A.nwc', 'B.nwc']
    assert refs == [(0, 0, '0/1'), (1, 1, '0/2'), (0, 0, '0/3')]
    assert sh.expand({'models': models, 'refs': refs}) == data


def test_signature_is_order_independent_and_counts():
    a = sh.signature(entries('0/1', '0/2'), 2)
    b = sh.signature(list(reversed(entries('0/1', '0/2'))), 2)
    assert a == b
    assert sh.signature(entries('0/1', '0/2'), 3) != a
    upper = [{'m': 'ARCH.NWC', 'i': 0, 'p': '0/1'}, {'m': 'arch.nwc', 'i': 5, 'p': '0/2'}]
    assert sh.signature(upper, 2) == a                   # file case and model index ignored


def test_make_state_caps_items():
    many = [{'m': 'A', 'i': 0, 'p': str(i)} for i in range(sh.MAX_ITEMS + 10)]
    s = sh.make_state(many, len(many))
    assert s['stored'] == sh.MAX_ITEMS and s['count'] == sh.MAX_ITEMS + 10


def test_record_and_cursor():
    h = sh.new_history()
    assert sh.record(h, state('1'), now=0)
    assert sh.record(h, state('2'), now=1)
    assert not sh.record(h, state('2'), now=2)           # same selection again
    assert sh.record(h, state('3'), now=3)
    assert h['cursor'] == 2 and len(h['states']) == 3
    assert sh.target(h, -1) == 1 and sh.target(h, 1) is None
    h['cursor'] = 0
    assert sh.record(h, state('4'), now=4)               # forward states dropped
    assert [s['refs'][0][2] for s in h['states']] == ['1', '4']


def test_expected_restore_is_skipped_once():
    h = sh.new_history()
    for p in ('1', '2', '3'):
        sh.record(h, state(p), now=0)
    h['cursor'] = 1
    sh.expect(h, state('2')['sig'], now=100)
    assert not sh.record(h, state('2'), now=101)
    assert h['expected'] is None and h['cursor'] == 1 and len(h['states']) == 3
    sh.expect(h, state('2')['sig'], now=100)
    assert sh.record(h, state('9'), now=101)             # a different selection clears it
    assert h['expected'] is None


def test_expected_expires():
    h = sh.new_history()
    sh.record(h, state('1'), now=0)
    sh.record(h, state('2'), now=0)
    h['cursor'] = 0
    sh.expect(h, state('2')['sig'], now=0)
    assert sh.record(h, state('2'), now=sh.EXPECT_SECONDS + 1)


def test_alias_after_partial_restore():
    h = sh.new_history()
    sh.record(h, state('1', '2'), now=0)
    sh.record(h, state('3'), now=0)
    restored = sh.make_state(entries('1'), 1)            # '2' no longer resolves
    h['cursor'] = 0
    h['alias'] = (0, restored['sig'])
    assert sh.is_current(h, restored['sig'])
    assert not sh.record(h, restored, now=0)             # not a new selection
    assert len(h['states']) == 2


def test_cap_states():
    h = sh.new_history()
    for i in range(sh.MAX_STATES + 5):
        sh.record(h, state(str(i)), now=0)
    assert len(h['states']) == sh.MAX_STATES
    assert h['states'][0]['refs'][0][2] == '5'
    assert h['cursor'] == sh.MAX_STATES - 1


def test_describe_and_rows():
    h = sh.new_history()
    sh.record(h, state('1', '2', '3'), now=0)
    sh.record(h, state('4'), now=0)
    message, detail = sh.describe(h, 0, resolved=2, missing=1)
    assert message == 'Selection 1 of 2'
    assert detail == '2 items, mostly Walls, selected 10:00:00 (1 no longer in the model)'
    rows = sh.list_rows(h)
    assert [r['value'] for r in rows] == [1, 0]           # newest first
    assert rows[0]['cells'][4] == 'Current' and rows[1]['cells'][4] == ''
    assert rows[1]['cells'][2] == 3
