# -*- coding: utf-8 -*-
"""namo.clashmatrix: codes, sources, the Trades and Matrix sheets, planning, the template
workbook round trip, and build() through the fake clash layer."""
import os

import _compat
import test_clashset_tests as cf

from namo import clashmatrix as cm


def test_parse_code_forms():
    assert cm.parse_code('', 'Meters') is None
    assert cm.parse_code(None, 'Meters') is None
    spec = cm.parse_code('H', 'Meters')
    assert spec['type'] == 'hard' and spec['tolerance'] == 0.0
    assert _compat.approx(cm.parse_code('h10mm', 'Meters')['tolerance'], 0.01)
    assert cm.parse_code('HC 5mm', 'Millimeters')['type'] == 'hard_conservative'
    assert _compat.approx(cm.parse_code('C 50mm', 'Millimeters')['tolerance'], 50.0)
    assert _compat.approx(cm.parse_code('Clearance 2"', 'Feet')['tolerance'], 2.0 / 12)
    assert cm.parse_code('d', 'Meters')['type'] == 'duplicate'
    assert cm.parse_code('Duplicates 1mm', 'Millimeters')['tolerance'] == 1.0
    assert _compat.approx(cm.parse_code('H 0.25', 'Feet')['tolerance'], 0.25)


def test_parse_code_errors_are_sentences():
    error = _compat.raises(ValueError, cm.parse_code, 'C', 'Meters')
    assert 'clearance test needs a distance' in str(error)
    error = _compat.raises(ValueError, cm.parse_code, 'X 10', 'Meters')
    assert 'not a test code' in str(error)
    error = _compat.raises(ValueError, cm.parse_code, 'H ten', 'Meters')
    assert 'not a length' in str(error)
    _compat.raises(ValueError, cm.parse_code, 1.0, 'Meters')
    _compat.raises(ValueError, cm.parse_code, 'Hx', 'Meters')


def test_code_for_reads_back():
    assert cm.code_for('clearance', 50.0, 'Millimeters') == 'C 50mm'
    assert cm.code_for('hard', 0.0, 'Meters') == 'H'
    spec = cm.parse_code(cm.code_for('hard_conservative', 0.005, 'Meters'), 'Meters')
    assert spec['type'] == 'hard_conservative' and _compat.approx(spec['tolerance'], 0.005)


def test_cell_refs():
    assert cm.cell_ref(0, 0) == 'A1'
    assert cm.cell_ref(4, 27) == 'AB5'
    assert cm.col_letter(701) == 'ZZ'


def test_classify_sources():
    assert cm.classify_source('Set: MEP/Ducts') == {'kind': 'set', 'path': 'MEP/Ducts',
                                                    'folder': False, 'search': None}
    assert cm.classify_source('folder: MEP')['folder'] is True
    assert cm.classify_source('Model: L1-*.nwc') == {'kind': 'model', 'name': 'L1-*.nwc'}
    assert cm.classify_source('MEP/Ducts')['kind'] == 'set'
    search = cm.classify_source('Element > Category = Ducts')
    assert search['kind'] == 'search'
    assert search['query']['or'][0]['and'][0]['value'] == 'Ducts'
    assert search['label'] == 'Element > Category = Ducts'
    both = cm.classify_source('Element > Category = Ducts\nItem > Name contains Supply')
    assert len(both['query']['or'][0]['and']) == 2
    many = cm.classify_source('Element > Category is one of Ducts, Pipes')
    assert len(many['query']['or']) == 2


def test_classify_source_errors():
    error = _compat.raises(ValueError, cm.classify_source, 'Item > Name matches ^P\\d+')
    assert 'cannot search' in str(error)
    error = _compat.raises(ValueError, cm.classify_source, 'Search: Level >= 3')
    assert 'needs a category' in str(error)
    _compat.raises(ValueError, cm.classify_source, 'Set:')
    _compat.raises(ValueError, cm.classify_source, '   ')


def test_read_trades_with_header_and_continuations():
    rows = [['Clash matrix trades'], ['Trade', 'Source', 'Notes'],
            ['Ducts', 'Set: MEP/Ducts', ''],
            ['', 'Set: MEP/Duct fittings', 'more'],
            ['Beams', '', ''],
            ['ducts', 'Model: HVAC.nwc', ''],
            ['Walls', 'Element > Category = Walls', '']]
    trades, problems = cm.read_trades(rows)
    assert [t for t, _s in trades] == ['Ducts', 'Walls']
    assert [s for s, _ref in trades[0][1]] == ['Set: MEP/Ducts', 'Set: MEP/Duct fittings',
                                              'Model: HVAC.nwc']
    assert trades[0][1][1][1] == 'B4'
    assert problems == ['Trades B5: Beams has no source.']


def test_read_trades_without_header():
    trades, problems = cm.read_trades([['A', 'Set: X'], ['', 'Set: Y']])
    assert trades == [('A', [('Set: X', 'B1'), ('Set: Y', 'B2')])]
    assert problems == []
    trades, problems = cm.read_trades([['', 'Set: X']])
    assert trades == [] and problems == ['Trades B1: a source with no trade above it.']


def _matrix_rows():
    return [['', 'Ducts', 'Beams', 'Walls'],
            ['Ducts', 'H', 'C 50mm', ''],
            ['Beams', 'C 50mm', '', 'Q'],
            ['Walls', 'H 10mm', '', 'D'],
            ['Pipes', 'H', '', '']]


def test_read_matrix_entries_and_problems():
    entries, problems = cm.read_matrix(_matrix_rows(), 'Millimeters')
    cells = [(e['a'], e['b'], e['type'], e['tolerance'], e['cell']) for e in entries]
    assert cells == [('Ducts', 'Ducts', 'hard', 0.0, 'B2'), ('Ducts', 'Beams', 'clearance', 50.0, 'C2'),
                     ('Beams', 'Ducts', 'clearance', 50.0, 'B3'), ('Walls', 'Ducts', 'hard', 10.0, 'B4'),
                     ('Walls', 'Walls', 'duplicate', 0.0, 'D4'), ('Pipes', 'Ducts', 'hard', 0.0, 'B5')]
    assert len(problems) == 1 and problems[0].startswith('Matrix D3: "Q" is not a test code')
    assert cm.read_matrix([[], ['']], 'Meters') == ([], ['The Matrix sheet is empty.'])


def test_plan_tests_dedupes_mirrors_and_names():
    trades = cm.trade_sources([('Ducts', [('Set: MEP/Ducts', 'B2')]),
                               ('Beams', [('Set: STR/Beams', 'B3')]),
                               ('Walls', [('Model: ARCH.nwc', 'B4')])])
    entries, _p = cm.read_matrix(_matrix_rows(), 'Millimeters')
    tests, problems, notes = cm.plan_tests(trades, entries, '{a} vs {b} ({type} {tolerance})',
                                           'Millimeters')
    assert [t['name'] for t in tests] == ['Ducts vs Ducts (Hard )', 'Ducts vs Beams (Clearance 50 mm)',
                                          'Walls vs Ducts (Hard 10 mm)', 'Walls vs Walls (Duplicates )']
    assert _compat.approx(tests[1]['tolerance_m'], 0.05)
    assert problems == ['Matrix B5: Pipes is not on the Trades sheet.']
    assert notes == ['Matrix B3 repeats C2; that test is made once.']


def test_plan_tests_unique_names_and_counter():
    trades = cm.trade_sources([('A', [('Set: A', 'B1')]), ('B', [('Set: B', 'B2')])])
    entries = [{'a': 'A', 'b': 'B', 'type': 'hard', 'tolerance': 0.0, 'cell': 'C2', 'code': 'H'},
               {'a': 'A', 'b': 'B', 'type': 'clearance', 'tolerance': 0.05, 'cell': 'C3', 'code': 'C 50mm'}]
    tests, problems, notes = cm.plan_tests(trades, entries, 'T{n:00}', 'Meters')
    assert [t['name'] for t in tests] == ['T01', 'T02']
    tests, _p, _n = cm.plan_tests(trades, entries, 'Same', 'Meters')
    assert [t['name'] for t in tests] == ['Same', 'Same (2)']


def test_template_round_trip_reads_back():
    folder = _compat.tmpdir('clashmatrix')
    path = os.path.join(folder, 'matrix.xlsx')
    rows = [('Ducts', 'Set: MEP/Ducts', 'Search set'), ('Beams', 'Set: STR/Beams', 'Static set'),
            ('Mechanical', 'Model: MEP.nwc', 'Whole model')]
    cm.write_template(path, rows, 'Millimeters')
    trades, entries, problems = cm.read_workbook(path, 'Millimeters')
    assert sorted(trades) == ['beams', 'ducts', 'mechanical']
    assert trades['ducts'][1] == [{'kind': 'set', 'path': 'MEP/Ducts', 'folder': False, 'search': None}]
    assert entries == [] and problems == []
    from pynavis import xl
    assert xl.sheets(path) == ['Read me', 'Trades', 'Matrix']
    matrix = xl.read(path, 'Matrix')
    assert matrix[0][1:] == ['Ducts', 'Beams', 'Mechanical']
    assert [r[0] for r in matrix[1:]] == ['Ducts', 'Beams', 'Mechanical']


def test_template_opens_in_openpyxl():
    _compat.require_cpython('openpyxl is CPython only')
    import openpyxl
    folder = _compat.tmpdir('clashmatrix-openpyxl')
    path = os.path.join(folder, 'm.xlsx')
    cm.write_template(path, [('A', 'Set: A', ''), ('B', 'Model: B.nwc', '')], 'Feet')
    wb = openpyxl.load_workbook(path)
    assert wb.sheetnames == ['Read me', 'Trades', 'Matrix']
    assert wb['Matrix'].freeze_panes == 'B2'
    assert 'ft' in ' '.join(str(c.value) for c in wb['Read me']['A'] if c.value)


def test_read_workbook_reports_missing_sheets():
    def reader(path, sheet):
        return []
    trades, entries, problems = cm.read_workbook('x.xlsx', 'Meters', reader=reader)
    assert problems and 'empty' in problems[-1]


def test_template_rows_from_sets_and_models():
    doc, named = cf.new_doc()
    with cf.ClashNav(doc):
        cf.add_set(doc, 'MEP/Ducts', [named['Duct']], query={'or': []})
        cf.add_set(doc, 'STR/Ducts', [])
        rows = cm.template_rows(doc)
    assert rows[0] == ('Ducts', 'Set: MEP/Ducts', 'Search set')
    assert rows[1] == ('Ducts (2)', 'Set: STR/Ducts', 'Static set')
    assert rows[2][1] == 'Model: ARCH.rvt' and rows[2][0] == 'Architecture'
    assert rows[3][1] == 'Model: MEP.rvt'


def test_build_creates_search_sets_and_tests_in_one_step():
    doc, named = cf.new_doc()
    with cf.ClashNav(doc) as fake:
        cf.add_set(doc, 'MEP/Ducts', [named['Duct']])
        trades = cm.trade_sources([('Ducts', [('Set: MEP/Ducts', 'B2')]),
                                   ('Walls', [('Element > Category = Walls', 'B3')]),
                                   ('Ghost', [('Set: Nope', 'B4')])])
        tests = [{'name': 'Ducts vs Walls', 'a': 'Ducts', 'b': 'Walls', 'type': 'hard',
                  'tolerance_m': 0.0}, {'name': 'Ducts vs Ghost', 'a': 'Ducts', 'b': 'Ghost',
                                        'type': 'hard', 'tolerance_m': 0.0}]
        rows = cm.build(tests, trades, 'skip', doc)
        assert doc.transactions == ['Clash matrix']
        assert [r['outcome'] for r in rows] == ['created', 'failed']
        assert rows[0]['linked'] is True
        assert rows[1]['detail'] == 'Selection set "Nope" is not in this model.'
        assert ('create', 'Walls', 'Clash Matrix') in fake.sets.calls
        assert [t.DisplayName for t in doc.clash_tests] == ['Ducts vs Walls']
        again = cm.build(tests[:1], trades, 'skip', doc)
        assert again[0]['outcome'] == 'skipped'
        assert ('update', 'Walls') in fake.sets.calls


def test_own_set_finds_deduped_names_in_the_tool_folder():
    doc, named = cf.new_doc()
    with cf.ClashNav(doc):
        cf.add_set(doc, 'MEP/Walls', [])
        mine = cf.add_set(doc, 'Clash Matrix/Walls (2)', [])
        cf.add_set(doc, 'Clash Matrix/Walls extra', [])
        assert cm.own_set('Walls', doc) is mine
        assert cm.own_set('walls', doc) is mine
        assert cm.own_set('Doors', doc) is None
