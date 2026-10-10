# -*- coding: utf-8 -*-
"""namo.propwrite: value inference, lines, merging, spreadsheet plans and matching,
find/replace, mapping profiles, coverage, data links; and the API half (key indexes,
batched writes, find scanning, mapping) through the fake layer."""
import io
import os

import _compat
import test_propindex as pf

from namo import propindex, propwrite, xlsx


# ---- values and lines -------------------------------------------------------------


def test_infer_value():
    assert propwrite.infer_value('12') == 12
    assert propwrite.infer_value(' -3 ') == -3
    assert propwrite.infer_value('1.5') == 1.5
    assert propwrite.infer_value('2e3') == 2000.0
    assert propwrite.infer_value('007') == '007'
    assert propwrite.infer_value('"12"') == '12'
    assert propwrite.infer_value('TRUE') is True
    assert propwrite.infer_value('yes') == 'yes'
    assert propwrite.infer_value('99999999999') == '99999999999'
    assert propwrite.infer_value('') == ''
    assert propwrite.infer_value(None) == ''
    assert propwrite.infer_value('1,234') == '1,234'


def test_parse_and_format_lines():
    pairs, problems = propwrite.parse_lines('Status = Approved\n\n# note\nPhase=2\nRatio = 0.5\nstatus = Done')
    assert problems == []
    assert pairs == [('Status', 'Done'), ('Phase', 2), ('Ratio', 0.5)]
    pairs = [('Code', '007'), ('Ref', '12'), ('Count', 3), ('Ok', True), ('Name', 'x')]
    text = propwrite.format_lines(pairs)
    assert text == 'Code = 007\nRef = "12"\nCount = 3\nOk = true\nName = x'
    assert propwrite.parse_lines(text)[0] == pairs
    _p, problems = propwrite.parse_lines('Nope\n= 3')
    assert problems == ['Line 1 needs a name and a value: Name = Value.',
                        'Line 2 has no property name before the equals sign.']
    _p, problems = propwrite.parse_lines('\n'.join('P%d = %d' % (i, i) for i in range(12)))
    assert problems == ['Write at most 10 properties at a time (12 given).']
    assert propwrite.parse_lines('  ')[1] == ['Type at least one line like Status = Approved.']


def test_merge_writable_and_same_tab():
    existing = {'A': 1, 'B': 'x'}
    assert propwrite.merge(existing, {'B': 'y', 'C': None}) == {'A': 1, 'B': 'y', 'C': ''}
    assert propwrite.merge(existing, {'C': 3}, replace=True) == {'C': 3}
    assert propwrite.merge(None, {'Big': 2 ** 40}) == {'Big': str(2 ** 40)}
    assert propwrite.writable(float('nan')) == 'nan'
    assert propwrite.same_tab({'A': 1, 'B': 'x'}, {'A': 1, 'B': 'x'})
    assert not propwrite.same_tab({'A': 1}, {'A': 2})
    assert not propwrite.same_tab(None, {'A': 1})
    assert propwrite.value_label(True) == 'Yes' and propwrite.value_label('a') == '"a"'


# ---- spreadsheets ---------------------------------------------------------------------


def test_key_kinds_and_detection():
    assert propwrite.key_kind('Element ID') == propwrite.KEY_ELEMENT_ID
    assert propwrite.key_kind(' guid ') == propwrite.KEY_GUID
    assert propwrite.key_kind('Element > Mark') == ('prop', 'Element', 'Mark')
    assert propwrite.key_kind('Status') is None
    assert propwrite.detect_key(['Status', 'IFC GUID', 'Element ID']) == (1, propwrite.KEY_GUID)
    assert propwrite.detect_key(['a', 'b']) == (None, None)
    assert propwrite.key_label(('prop', 'Element', 'Mark')) == 'Element > Mark'


def test_cells_and_headers():
    assert propwrite.cell_text(123456.0) == '123456'
    assert propwrite.cell_text(1.5) == '1.5'
    assert propwrite.normalise_key('{ABC-DEF}', propwrite.KEY_GUID) == 'abc-def'
    assert propwrite.cell_value(3.0) == 3 and propwrite.cell_value('') is None
    assert propwrite.cell_value(2.5) == 2.5 and propwrite.cell_value(True) is True
    headers, rows = propwrite.headers_of([['', ''], ['Element ID', 'Status'], [101.0, 'Open']])
    assert headers == ['Element ID', 'Status'] and rows == [[101.0, 'Open']]


def _sheet():
    headers = ['Element ID', 'Status', 'Cost', 'Ignored']
    rows = [[101.0, 'Open', 12.5, 'x'], ['', 'orphan', '', ''], [102.0, 'Closed', '', 'y'],
            [999.0, 'Ghost', 1.0, ''], [101.0, 'Reopened', 13.0, ''], ['', '', '', '']]
    return headers, rows


def test_plan_match_and_preview():
    headers, rows = _sheet()
    plan = propwrite.plan_rows(headers, rows, 0, propwrite.KEY_ELEMENT_ID, ['Status', 'Cost'])
    assert [e['row'] for e in plan['rows']] == [6, 4, 5]
    assert plan['rows'][0]['values'] == {'Status': 'Reopened', 'Cost': 13}
    assert plan['rows'][1]['values'] == {'Status': 'Closed'}
    assert plan['blank'] == [3]
    assert plan['duplicates'] == [(6, 2)]
    index = {'101': ['w1'], '102': ['w2a', 'w2b']}
    matching = propwrite.match_rows(plan['rows'], index)
    assert [e['row'] for e, _i in matching['matched']] == [6, 4]
    assert [e['row'] for e in matching['unmatched']] == [5]
    assert [e['row'] for e, _i in matching['ambiguous']] == [4]
    preview = propwrite.preview_rows(plan, matching)
    assert [r['cells'][:3] for r in preview] == [[4, '102', 'Matches 2 items'], [5, '999', 'Not found'],
                                                 [6, '101', 'Matched, replaces row 2']]
    assert preview[2]['cells'][3] == 'Cost = 13, Status = Reopened'
    head, out = propwrite.unmatched_sheet(headers, rows, plan, matching, 0)
    assert head == ['Row', 'Element ID', 'Status', 'Cost', 'Ignored']
    assert out == [[5, 999.0, 'Ghost', 1.0, '']]


# ---- find and replace -----------------------------------------------------------------


def test_compile_find_modes():
    plain = propwrite.compile_find('wall', 'Wall')
    assert plain('basic wall wall') == 'basic Wall Wall'
    assert plain('Wall') is None                     # no change: not a match to report
    assert propwrite.compile_find('wall', 'X', match_case=True)('Wall') is None
    regex = propwrite.compile_find(r'L(\d+)', r'Level \1', regex=True)
    assert regex('L3 and L10') == 'Level 3 and Level 10'
    whole = propwrite.compile_find('a|ab', 'Z', regex=True, whole=True)
    assert whole('ab') == 'Z' and whole('abc') is None
    literal = propwrite.compile_find('a.b', r'\1', whole=True)
    assert literal('a.b') == r'\1' and literal('axb') is None
    _compat.raises(ValueError, propwrite.compile_find, '', 'x')
    error = _compat.raises(ValueError, propwrite.compile_find, '(', 'x', regex=True)
    assert str(error).startswith('The pattern does not read')


def test_plan_and_group_changes():
    apply = propwrite.compile_find('old', 'new')
    readings = [('i1', 'Element', 'Mark', 'old-1', False), ('i1', 'Playground', 'Note', 'old', True),
                ('i2', 'Element', 'Mark', 'keep', False), ('i2', 'Item', 'Name', 'old', False)]
    changes = propwrite.plan_changes(readings, apply)
    assert [(c['item'], c['new'], c['custom']) for c in changes] == [
        ('i1', 'new-1', False), ('i1', 'new', True), ('i2', 'new', False)]
    grouped = propwrite.group_changes(changes)
    assert grouped == [('i1', {'Playground Corrected': {'Element - Mark': 'new-1'}, 'Playground': {'Note': 'new'}}),
                       ('i2', {'Playground Corrected': {'Item - Name': 'new'}})]
    assert propwrite.typed_like(3, '4') == 4
    assert propwrite.typed_like(3, 'four') == 'four'
    assert propwrite.typed_like('3', '4') == '4'


# ---- mapper ---------------------------------------------------------------------------

PROFILE = '''# Standard fields
tab: Standard Data
System: Element > System Name | IFC > SystemName | Item > Layer
Level: Element > Level | Element > Reference Level ~ /^Level (\\d+)/L\\1/
Level [ARCH*.rvt]: Element > Base Constraint
Code: Element > Comments ~ /([A-Z]{3}-\\d+)/
'''


def test_parse_and_format_profile():
    profile, problems = propwrite.parse_profile(PROFILE)
    assert problems == []
    assert profile['tab'] == 'Standard Data'
    assert propwrite.field_names(profile) == ['System', 'Level', 'Code']
    level = profile['fields'][1]
    assert level['sources'] == [['Element', 'Level'], ['Element', 'Reference Level']]
    assert level['pattern'] == r'^Level (\d+)' and level['replace'] == r'L\1'
    assert profile['fields'][2]['model'] == 'ARCH*.rvt'
    assert profile['fields'][3]['replace'] is None
    again, problems = propwrite.parse_profile(propwrite.format_profile(profile))
    assert problems == [] and again == profile


def test_profile_problems():
    _p, problems = propwrite.parse_profile('Bad line\nX: Mark\nY: A > B ~ /(/\nZ: A > B ~ nope\ntab:')
    assert problems[0].startswith('Line 1: write Field:')
    assert 'Line 2: source "Mark" needs Category > Property.' in problems
    assert 'Line 2: field X has no sources.' in problems
    assert any(p.startswith('Line 3: The pattern does not read') for p in problems)
    assert any(p.startswith('Line 4: Write the regex between slashes') for p in problems)
    assert problems[-1] == 'Line 5: the tab needs a name.'
    assert propwrite.parse_profile('')[1] == ['Add at least one field, like System: Element > System Name.']
    assert propwrite.parse_modifier(r'/a\/b/c/') == ('a/b', 'c')


def test_map_values_and_coverage():
    profile, _ = propwrite.parse_profile(PROFILE)
    duct = {('Element', 'System Name'): '', ('Item', 'Layer'): 'M-SUPPLY', ('Element', 'Reference Level'): 'Level 3',
            ('Element', 'Comments'): 'tag AHU-12 here'}
    read = lambda c, p: duct.get((c, p))
    mapped = propwrite.map_values(profile, read, 'MEP.rvt')
    assert mapped == {'System': ('M-SUPPLY', 'Item > Layer'), 'Level': ('L3', 'Element > Reference Level'),
                      'Code': ('AHU-12', 'Element > Comments')}
    wall = {('Element', 'Base Constraint'): 'Level 1', ('Element', 'Level'): 'Level 2'}
    mapped = propwrite.map_values(profile, lambda c, p: wall.get((c, p)), 'ARCH-01.rvt')
    assert mapped['Level'] == ('Level 1', 'Element > Base Constraint')
    assert mapped['System'] == (None, None)
    records = [('MEP.rvt', {'System': ('a', 's'), 'Level': (None, None)}),
               ('MEP.rvt', {'System': ('b', 's'), 'Level': ('L1', 's')}),
               ('ARCH.rvt', {'System': (None, None), 'Level': ('L1', 's')})]
    rows = propwrite.coverage(records, ['System', 'Level'])
    assert rows == [('ARCH.rvt', 'System', 1, 0, 0.0), ('ARCH.rvt', 'Level', 1, 1, 1.0),
                    ('MEP.rvt', 'System', 2, 2, 1.0), ('MEP.rvt', 'Level', 2, 1, 0.5)]
    assert propwrite.apply_modifier('x', '', None) == 'x'
    assert propwrite.apply_modifier('abc', 'z', None) is None


# ---- data links -------------------------------------------------------------------------


def test_link_records_and_state():
    link = propwrite.new_link('Asset data', r'C:\D\assets.xlsx', 'Sheet1', 'Element ID',
                              propwrite.KEY_ELEMENT_ID, ['Status'], 'Assets')
    assert link['key'] == 'Element ID'
    assert propwrite.link_key_kind(link) == propwrite.KEY_ELEMENT_ID
    assert propwrite.link_key_kind(dict(link, key='Element > Mark')) == ('prop', 'Element', 'Mark')
    assert propwrite.link_state(link, None) == 'Source file missing'
    assert propwrite.link_state(link, 100.0) == 'Not refreshed yet'
    done = dict(link, last_refresh='2026-10-05 10:00', file_mtime=100.0, id='L1',
                stats={'matched': 3, 'unmatched': 1, 'changed': 2})
    assert propwrite.link_state(done, 100.4) == 'Up to date'
    assert propwrite.link_state(done, 200.0) == 'File changed since the last refresh'
    rows = propwrite.link_rows([done], lambda path: 100.0)
    assert rows[0]['value'] == 'L1'
    assert rows[0]['cells'][1] == 'assets.xlsx' and rows[0]['cells'][6] == 'Up to date'
    assert rows[0]['cells'][7] == '3 matched, 1 unmatched, 2 changed'
    assert len(rows[0]['cells']) == len(propwrite.LINK_HEADERS)


# ---- files --------------------------------------------------------------------------------


def test_read_table_csv_and_xlsx():
    folder = _compat.tmpdir('g2_propwrite_tables')
    csv_path = os.path.join(folder, 'a.csv')
    with io.open(csv_path, 'w', encoding='utf-8-sig', newline='') as handle:
        handle.write(u'Element ID;Status;Code\r\n101;Open;007\r\n102;Done;1.5\r\n')
    rows = propwrite.read_table(csv_path)
    assert rows[0] == ['Element ID', 'Status', 'Code']
    assert rows[1] == [101.0, 'Open', '007'] and rows[2][2] == 1.5
    assert propwrite.table_sheets(csv_path) == ['']
    xlsx_path = os.path.join(folder, 'b.xlsx')
    xlsx.write_simple(xlsx_path, [{'name': 'Data', 'headers': ['GUID', 'Cost'], 'rows': [['ab', 12.5]]}])
    assert propwrite.table_sheets(xlsx_path) == ['Data']
    rows = propwrite.read_table(xlsx_path, 'Data')
    assert rows[0] == ['GUID', 'Cost'] and rows[1] == ['ab', 12.5]


# ---- API half -------------------------------------------------------------------------------


def _install_props(fake):
    """Adds custom-tab reading/writing to the fake pynavis.props."""
    import sys
    props = sys.modules['pynavis.props']
    calls = []

    def get_custom(item, tab):
        values = dict((p, v) for (c, p), v in item.props.items() if c == tab)
        return values or None

    def set_custom(items_, tab, values, doc=None, progress=None):
        for item in items_:
            for key in [k for k in item.props if k[0] == tab]:
                del item.props[key]
            for name, value in values.items():
                item.props[(tab, name)] = value
            item.editable.add(tab)
            calls.append((item.DisplayName, tab, dict(values)))
        return len(items_), []

    def remove_custom(items_, tab, doc=None, progress=None):
        removed = 0
        for item in items_:
            keys = [k for k in item.props if k[0] == tab]
            for key in keys:
                del item.props[key]
            removed += 1 if keys else 0
        return removed, []
    props.get_custom = get_custom
    props.set_custom = set_custom
    props.remove_custom = remove_custom
    return calls


def test_write_tabs_merges_in_one_transaction():
    doc, n = pf.tree()
    with pf.Fake(doc) as fake:
        calls = _install_props(fake)
        plan = [(n['Wall 2'], {'Playground': {'Phase': 2}}), (n['Wall 1'], {'Playground': {'Status': 'Open'}}),
                (n['Duct'], {'Playground': {}})]
        result = propwrite.write_tabs(plan, doc, name='Write properties')
        assert result == {'written': 2, 'unchanged': 1, 'errors': []}
        assert doc.transactions == ['Write properties']
        assert n['Wall 2'].props[('Playground', 'Status')] == 'Open'     # merged, kept
        assert n['Wall 2'].props[('Playground', 'Phase')] == 2
        again = propwrite.write_tabs([(n['Wall 1'], {'Playground': {'Status': 'Open'}})], doc)
        assert again['unchanged'] == 1 and len(calls) == 2
        removed, errors = propwrite.remove_tab([n['Wall 1'], n['Duct']], 'Playground', doc)
        assert removed == 1 and errors == []


def test_key_index_scan_find_and_map():
    doc, n = pf.tree()
    with pf.Fake(doc, 'Meters'):
        reader = propindex.Reader(doc, 'auto')
        objs = propindex.scope_items('model', 'objects', doc)
        ids = propwrite.key_index(objs, propwrite.KEY_ELEMENT_ID, reader)
        assert sorted(ids) == ['101', '102'] and ids['101'] == [n['Wall 1']]
        guids = propwrite.key_index(objs, propwrite.KEY_GUID, reader)
        assert pf.UID.lower() in guids and len(guids) == 2           # UniqueId + derived IFC GUID
        marks = propwrite.key_index(objs, ('prop', 'Element', 'Mark'), reader)
        assert list(marks) == ['w1']
        apply = propwrite.compile_find('Open', 'Closed')
        changes = propwrite.scan_find(objs, apply, reader)
        assert [(c['item'].DisplayName, c['category'], c['custom']) for c in changes] == [
            ('Wall 2', 'Playground', True)]
        walls = propwrite.scan_find(objs, propwrite.compile_find('wall', 'Partition'), reader,
                                    only=('Item', 'Name'))
        assert [c['new'] for c in walls] == ['Partition 1', 'Partition 2']
        profile, _ = propwrite.parse_profile('System: Element > System Name | Element > Category')
        mapped = propwrite.map_items(profile, objs, reader)
        assert [(m, v['System'][0]) for _i, m, v in mapped] == [
            ('ARCH.rvt', 'Walls'), ('ARCH.rvt', 'Walls'), ('MEP.rvt', 'SA-1'), ('MEP.rvt', 'Pipes')]


def test_element_id_keys_skip_nested_parts_that_repeat_the_type_id():
    # Refit (field fact): nested parts under a family instance carry the TYPE's id in
    # their Element ID tab; only real elements carry the LcRevitData_Element category.
    entries = [('fixture', ['36725269'], 0, True), ('part a', ['36725265'], 0, False),
               ('part b', ['36725265'], 0, False), ('dwg block', ['77'], 1, False)]
    assert propwrite.drop_type_ids(entries) == [('fixture', ['36725269']), ('dwg block', ['77'])]
    # a model whose exporter never wrote the category keeps every id (the old rule)
    plain = [('a', ['1'], 0, False), ('b', ['2'], None, False)]
    assert propwrite.drop_type_ids(plain) == [('a', ['1']), ('b', ['2'])]
    real = pf.nav._Ns(PropertyCategories=[pf.Cat('Element', [], internal='LcRevitData_Element')])
    assert propwrite.is_revit_element(real)
    assert not propwrite.is_revit_element(pf.nav._Ns(PropertyCategories=[pf.Cat('Element ID', [])]))
    assert not propwrite.is_revit_element(object())


def test_is_custom_category():
    assert propwrite.is_custom_category(pf.Cat('x', [], editable=True))
    assert propwrite.is_custom_category(pf.Cat('x', [], internal='LcOaPropOverrideCat'))
    assert not propwrite.is_custom_category(pf.Cat('Element', []))
