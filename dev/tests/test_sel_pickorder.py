# -*- coding: utf-8 -*-
"""namo.sel_pickorder: picks from selection changes, repeats, numbering, export rows."""
import _compat

from namo import sel_pickorder as po


def e(path, model='Arch.nwc', name=''):
    return {'m': model, 'i': 0, 'p': path, 'name': name or path}


def keys(*entries):
    return [po.entry_key(x) for x in entries]


def test_entry_key_ignores_case_and_index():
    assert po.entry_key({'m': 'ARCH.nwc', 'i': 3, 'p': '0/1'}) == ('arch.nwc', '0/1')


def test_click_then_ctrl_click():
    a, b, c = e('0/1'), e('0/2'), e('0/3')
    assert po.picks_from_change(None, [a]) == [a]                 # unknown before: all new
    assert po.picks_from_change(keys(a), [b]) == [b]              # plain click replaces
    assert po.picks_from_change(keys(b), [b, c]) == [c]           # Ctrl+click adds one
    assert po.picks_from_change(keys(b, c), [b]) == []            # deselect adds nothing


def test_large_added_set_is_not_a_pick():
    many = [e('0/%d' % i) for i in range(po.SMALL_SET + 1)]
    assert po.picks_from_change([], many) == []
    small = many[:3]
    assert po.picks_from_change([], small) == small               # selection order kept


def test_append_ignores_repeats():
    picks, count = po.append([e('0/1')], [e('0/2'), e('0/1', model='ARCH.NWC'), e('0/2')])
    assert [p['p'] for p in picks] == ['0/1', '0/2'] and count == 1


def test_sequence_values():
    assert po.sequence_values(3) == [1, 2, 3]
    assert po.sequence_values(3, start=10, step=5) == [10, 15, 20]
    assert po.sequence_values(2, prefix='P-', digits=3) == ['P-001', 'P-002']
    assert po.sequence_values(2, start=8, digits=2) == ['08', '09']
    assert po.sequence_values(2, start=-1, prefix='X') == ['X-1', 'X0']


def test_merged_tab_keeps_other_values():
    import datetime
    tab = po.merged_tab({'Zone': 'A', 'Count': 3, 'When': datetime.date(2026, 10, 5), 'Gone': None},
                        'Sequence', 7)
    assert tab == {'Zone': 'A', 'Count': 3, 'When': '2026-10-05', 'Sequence': 7}
    assert po.merged_tab(None, 'Sequence', 'P-1') == {'Sequence': 'P-1'}


def test_gradient():
    assert po.gradient(0) == []
    assert len(po.gradient(1)) == 1
    ramp = po.gradient(5)
    assert len(ramp) == 5 and len(set(ramp)) == 5
    assert all(len(h) == 6 for h in ramp)


def test_csv_text():
    text = po.csv_text(['A', 'B'], [[1, 'x,y'], [2.5, 'say "hi"'], [None, 'line\nbreak']])
    assert text == 'A,B\r\n1,"x,y"\r\n2.5,"say ""hi"""\r\n,"line\nbreak"\r\n'


def test_export_rows():
    headers = po.export_headers('ft')
    assert headers[-3:] == ['Centre X (ft)', 'Centre Y (ft)', 'Centre Z (ft)']
    assert po.export_headers('')[-1] == 'Centre Z'
    row = po.export_row(1, {'name': 'Duct', 'category': 'Ducts', 'element_id': '7', 'guid': 'g',
                            'source': 'MEP.nwc', 'center': (1.234567, 2.0, -3.5)})
    assert row == [1, 'Duct', 'Ducts', '7', 'g', 'MEP.nwc', 1.2346, 2.0, -3.5]
    assert po.export_row(2, {'center': None})[6:] == [None, None, None]
