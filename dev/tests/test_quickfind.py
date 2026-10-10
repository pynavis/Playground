# -*- coding: utf-8 -*-
"""namo.quickfind: fields, signature, the one-string index format, narrowing search,
result display, and a size/speed check on both engines."""
import time

import _compat

from namo import quickfind as qf


KEYS = ['name', 'class', 'element_id', 'category', 'type', 'level']


def sample_rows(n=6):
    rows = [
        (0, '0/1/1', ['Basic Wall', 'Solid', '312045', 'Walls', 'Generic - 200mm', 'Level 1']),
        (0, '0/1/2', ['Basic Wall', 'Solid', '312046', 'Walls', 'Generic - 300mm', 'Level 2']),
        (1, '0/4', ['Rectangular Duct', 'Solid', '900001', 'Ducts', 'Mitered Elbows', 'Level 3']),
        (1, '0/5', ['Pipe Types', 'Solid', '900002', 'Pipes', 'Standard', 'Level 3']),
        (1, '0/6', ['Supply Diffuser', 'Block', '900003', 'Air Terminals', '600x600', 'Level 10']),
        (0, '0/7', ['Door', 'Block', '400100', 'Doors', 'Single Flush', 'Level 1']),
    ]
    return rows[:n]


def test_field_specs_always_start_with_name():
    specs = qf.field_specs(['level', 'type'])
    assert [s['key'] for s in specs] == ['name', 'type', 'level']
    assert [s['key'] for s in qf.field_specs(None)] == ['name']
    assert qf.field_specs(qf.FIELD_KEYS)[0]['key'] == 'name'


def test_clean():
    assert qf.clean(None) == ''
    assert qf.clean(' a\tb\r\nc ') == 'a b  c'
    assert qf.FIELD_SEP not in qf.clean('x' + qf.FIELD_SEP + 'y')
    assert qf.clean(12) == '12'


def test_signature_compares_models_and_fields():
    models = [{'name': 'Arch.NWC', 'size': 10, 'mtime': 5}]
    a = qf.signature(models, KEYS)
    assert a['models'] == [['arch.nwc', 10, 5]]
    assert qf.same_signature(a, qf.signature([{'name': 'arch.nwc', 'size': 10, 'mtime': 5}], KEYS))
    assert not qf.same_signature(a, qf.signature([{'name': 'arch.nwc', 'size': 11, 'mtime': 5}], KEYS))
    assert not qf.same_signature(a, qf.signature(models, KEYS[:-1]))
    assert not qf.same_signature(a, None)


def test_encode_decode_round_trip():
    sig = qf.signature([{'name': 'a.nwc', 'size': 1, 'mtime': 2}], KEYS)
    rows = sample_rows()
    rows.append((0, '0/9', ['Odd' + qf.ROW_SEP + 'name', '', '', '', '', '']))
    data = qf.encode(sig, ['Arch.nwc', 'MEP.nwc'], rows, sampled=True, built='2026-10-05T10:00:00')
    assert data['count'] == len(rows) and data['fields'] == KEYS
    back = qf.decode(data)
    assert back['models'] == ['Arch.nwc', 'MEP.nwc'] and back['sampled'] is True
    assert back['rows'][:6] == [(m, p, v) for m, p, v in sample_rows()]
    assert back['rows'][6][2][0] == 'Odd name'           # separators scrubbed, row intact
    assert qf.decode({'format': 'other'}) is None
    assert qf.decode(dict(data, version=99)) is None
    assert qf.decode(qf.encode(sig, [], []))['rows'] == []


def test_decode_pads_short_rows():
    data = qf.encode(qf.signature([], KEYS), ['a'], [(0, '0', ['Only name'])])
    back = qf.decode(data)
    assert back['rows'][0][2] == ['Only name', '', '', '', '', '']


def test_json_file_round_trip():
    from namo import paths
    folder = _compat.tmpdir('quickfind')
    path = paths.write_json(folder + '/index.json', qf.encode(qf.signature([], KEYS), ['a'], sample_rows()))
    back = qf.decode(paths.load_json(path))
    assert len(back['rows']) == 6
    with open(path, 'rb') as handle:
        raw = handle.read()
    assert b'\\u' not in raw                              # separators written raw, never escaped


def test_extends():
    assert qf.extends('wal', 'wall')
    assert qf.extends('wall', 'wall 3')
    assert qf.extends('WALL', 'wall l1')
    assert not qf.extends('wall', 'wal')
    assert not qf.extends(None, 'x')
    assert not qf.extends('  ', ' a')


def test_search_and_narrowing():
    index = qf.QuickIndex(KEYS, ['Arch.nwc', 'MEP.nwc'], sample_rows())
    total, ranked = index.search('wall')
    assert total == 2 and [i for _s, i in ranked] == [0, 1]
    assert index.all_matches() == [0, 1]
    total, ranked = index.search('wall 312045')            # narrowed from the last matches
    assert total == 1 and ranked[0][1] == 0
    total, ranked = index.search('lvl 3')                 # fuzzy: 'Level 3'
    assert total >= 2
    assert set(i for _s, i in ranked) >= set([2, 3])
    total, ranked = index.search('900003')
    assert [i for _s, i in ranked] == [4]                 # ids match as written, not scattered
    total, ranked = index.search('90')
    assert total >= 3                                     # short numbers stay fuzzy
    assert qf.exact_words(['12', '123', 'a123', '4567']) == ['123', '4567']
    assert index.search('') == (0, [])
    total, ranked = index.search('zzzz')
    assert total == 0 and ranked == []
    total, ranked = index.search('level', limit=2)
    assert total == 6 and len(ranked) == 2


def test_entry_and_display():
    index = qf.QuickIndex(KEYS, ['Arch.nwc', 'MEP.nwc'], sample_rows())
    assert index.entry(2) == {'m': 'MEP.nwc', 'i': 1, 'p': '0/4'}
    shown = index.display(2, '900001')
    assert shown['name'] == 'Rectangular Duct' and shown['model'] == 'MEP.nwc'
    assert shown['detail'] == 'Element ID: 900001'
    start, end = shown['detail_spans'][0]
    assert shown['detail'][start:end] == '900001'
    shown = index.display(0, 'basic')
    assert shown['name_spans'] == [(0, 5)]
    assert shown['detail'] == 'Walls, Generic - 200mm'    # name matched: category, type


def test_best_field_prefers_more_words():
    pos, hit = qf.best_field(KEYS, sample_rows()[2][2], 'mitered l3')
    assert KEYS[pos] in ('type', 'level') and hit
    pos, hit = qf.best_field(KEYS, ['', '', '', '', '', ''], 'x')
    assert pos is None and hit == []


def test_pieces():
    assert qf.pieces('abcdef', [(1, 3)]) == [('a', False), ('bc', True), ('def', False)]
    assert qf.pieces('abc', []) == [('abc', False)]
    assert qf.pieces('abc', [(0, 3)]) == [('abc', True)]
    assert qf.pieces('', []) == [('', False)]


def test_status_text():
    assert qf.status_text(104233, 0, 0, '') == 'Type to search 104,233 elements'
    assert qf.status_text(10, 0, 0, 'x') == 'No matches'
    assert qf.status_text(10, 1, 1, 'x') == '1 match'
    assert qf.status_text(10, 1204, 200, 'x') == '1,204 matches, showing the best 200'
    assert qf.status_text(500000, 3, 3, 'x', sampled=True).endswith(
        '(index sampled: the first 500,000 elements)')


def test_speed_100000_rows():
    rows = []
    for i in range(100000):
        rows.append((i % 5, '0/%d/%d' % (i % 97, i), ['Element %d' % i, 'Solid', str(300000 + i),
                                                       'Walls' if i % 3 else 'Ducts', 'Type %d' % (i % 40),
                                                       'Level %d' % (i % 12)]))
    started = time.time()
    data = qf.encode(qf.signature([], KEYS), ['m'] * 5, rows)
    back = qf.decode(data)
    index = qf.QuickIndex(back['fields'], back['models'], back['rows'])
    loaded = time.time() - started
    started = time.time()
    total, _ranked = index.search('du')
    first = time.time() - started
    started = time.time()
    total2, _ranked = index.search('duc l11')
    narrowed = time.time() - started
    assert total >= total2 > 0
    limit = 30.0 if _compat.IRONPYTHON else 10.0
    assert loaded < limit and first < limit
    assert narrowed <= first + 0.5
