# -*- coding: utf-8 -*-
"""namo.selecttools: Select Similar rows and queries, Filter Selection, the visible
frontier behind Invert, Select by File rows and Save as Set names."""
import datetime

import _compat

from namo import selecttools as st


PROPS = [
    {'category': 'Item', 'property': 'Name', 'value': 'Basic Wall'},
    {'category': 'Item', 'property': 'GUID', 'value': '6f1c2a10-1111-2222-3333-444455556666'},
    {'category': 'Item', 'property': 'Hidden', 'value': False},
    {'category': 'Element', 'property': 'Category', 'value': 'Walls'},
    {'category': 'Element', 'property': 'Family', 'value': 'Basic Wall'},
    {'category': 'Element', 'property': 'Type', 'value': 'Generic - 200mm'},
    {'category': 'Element', 'property': 'Mark', 'value': 'W-12'},
    {'category': 'Element', 'property': 'Width', 'value': 0.2},
    {'category': 'Element', 'property': 'Comments', 'value': ''},
    {'category': 'Element', 'property': 'Created', 'value': datetime.datetime(2026, 1, 1)},
    {'category': 'Element ID', 'property': 'Value', 'value': '312045'},
    {'category': 'Element', 'property': 'Category', 'value': 'Duplicate'},
]


def test_similar_rows_filters_and_flags():
    rows = st.similar_rows(PROPS)
    keys = [r['key'] for r in rows]
    assert 'Element > Comments' not in keys                 # blank value
    assert 'Element > Created' not in keys                  # dates cannot be searched natively
    assert keys.count('Element > Category') == 1            # first value kept
    by_key = dict((r['key'], r) for r in rows)
    assert by_key['Element > Category']['text'] == 'Walls'
    assert by_key['Element > Width']['kind'] == 'float'
    assert by_key['Item > GUID']['identity']
    assert by_key['Item > Hidden']['identity']              # view state, not a description
    assert by_key['Element > Mark']['identity']
    assert by_key['Element ID > Value']['identity']
    assert not by_key['Item > Name']['identity']            # 'Basic Wall' is not unique
    assert not by_key['Element > Type']['identity']


def test_identity_rules():
    assert st.is_identity('Item', 'Name', 'Wall [312045]')
    assert st.is_identity('Item', 'Name', 'Basic Wall:Generic:312045')
    assert not st.is_identity('Item', 'Name', 'Level 3')
    assert st.is_identity('Element', 'IfcGUID', '2O2Fr$t4X7Zf8NOew3FLOH')
    assert st.is_identity('Element', 'Export GUID', 'x')
    assert st.is_identity('IFC', 'Description', '2O2Fr$t4X7Zf8NOew3FLOH')   # value looks like one
    assert not st.is_identity('Element', 'Level', 'Level 1')
    assert st.looks_unique('6f1c2a10-1111-2222-3333-444455556666')
    assert not st.looks_unique('')


def test_default_checked():
    rows = st.similar_rows(PROPS)
    assert st.default_checked(rows, ['Element > Width', 'Nope > Nothing']) == ['Element > Width']
    assert st.default_checked(rows, []) == ['Element > Category', 'Element > Family', 'Element > Type']
    assert st.default_checked([], ['Element > Width']) == []


def test_similar_query_types_each_value():
    rows = st.similar_rows(PROPS)
    by_key = dict((r['key'], r) for r in rows)
    q = st.similar_query([by_key['Element > Category'], by_key['Element > Width'],
                          by_key['Item > Hidden']])
    conds = q['or'][0]['and']
    assert conds[0] == {'category': 'Element', 'prop': 'Category', 'op': 'equals', 'value': 'Walls',
                        'ignore_case': True}
    assert [c['op'] for c in conds[1:3]] == ['ge', 'le']    # float window
    assert conds[3]['value'] is False and 'ignore_case' not in conds[3]
    assert st.similar_query([]) is None


def test_similar_summary():
    rows = st.similar_rows(PROPS)[:2]
    level, message, detail = st.similar_summary(1204, rows, 'model')
    assert level == 'success' and message == 'Selected 1,204 similar items'
    assert detail.startswith('Item > Name = Basic Wall')
    level, message, detail = st.similar_summary(1, rows, 'same_model', dropped=rows[1:])
    assert level == 'warning' and message == 'Selected 1 similar item'
    assert 'same model as the item' in detail and 'Left out' in detail
    assert st.similar_summary(0, rows, 'model')[0] == 'info'


def test_table_rows_and_visibility():
    rows = st.similar_rows(PROPS)
    shown = st.visible_similar_rows(rows, False)
    assert all(not r['identity'] for r in shown)
    assert len(st.visible_similar_rows(rows, True)) == len(rows)
    table = st.table_rows(shown, ['Element > Type'])
    ticked = [t['value'] for t in table if t['checked']]
    assert ticked == ['Element > Type']
    assert table[0]['cells'] == [shown[0]['category'], shown[0]['property'], shown[0]['text']]


def test_merge_property_counts():
    merged = st.merge_property_counts([('b', 'x', 2), ('A', 'y', 1)], [('b', 'x', 5)])
    assert merged == [('A', 'y', 1), ('b', 'x', 5)]


def test_filter_indices_and_summary():
    readings = [(True, 'Ducts'), (True, 'Pipes'), (False, None), (True, 'ducts')]
    cond = {'category': 'Element', 'property': 'Category', 'op': 'equals', 'value': 'Ducts'}
    assert st.filter_indices(readings, cond, keep=True) == [0, 3]
    assert st.filter_indices(readings, cond, keep=False) == [1, 2]
    missing = {'category': 'Element', 'property': 'Category', 'op': 'missing'}
    assert st.filter_indices(readings, missing) == [2]
    level, message, detail = st.filter_summary(312, 1040, True, 'Element > Category = Ducts')
    assert (level, message) == ('success', 'Kept 312 of 1,040')
    level, message, detail = st.filter_summary(312, 1040, False, 'x')
    assert message == 'Removed 728 of 1,040' and detail.startswith('312 left')
    assert st.filter_summary(0, 10, True, 'x')[1] == 'No item would stay selected'
    assert st.filter_summary(10, 10, True, 'x')[0] == 'info'


def test_value_options():
    options = st.value_options([('Ducts', 3, 'Ducts'), ('(no value)', 2, None), ('Pipes', 1, 'Pipes')])
    assert options == [('Ducts  (3)', 'Ducts'), ('Pipes  (1)', 'Pipes'), ('Type a value', st.OTHER)]


def test_filter_ops_are_rules_ops():
    from namo import rules
    assert [op for op, _l in st.filter_ops()] == rules.OP_NAMES


class N(object):
    def __init__(self, name, children=(), hidden=False):
        self.name = name
        self.hidden = hidden
        self.Children = list(children)
        self.Parent = None
        for c in self.Children:
            c.Parent = self

    def __repr__(self):
        return self.name


def _hidden_or_ancestor(node):
    while node is not None:
        if node.hidden:
            return True
        node = node.Parent
    return False


def test_visible_frontier():
    #  root - A - a1 (hidden)
    #       |   + a2
    #       + B (hidden) - b1
    #       + C - c1
    a1, a2, b1, c1 = N('a1', hidden=True), N('a2'), N('b1'), N('c1')
    a, b, c = N('A', [a1, a2]), N('B', [b1], hidden=True), N('C', [c1])
    root = N('root', [a, b, c])
    hidden = set([a1, b])
    ancestors = set([a, root])
    out = st.visible_frontier([root], hidden, ancestors, lambda n: n.Children, _hidden_or_ancestor)
    assert [n.name for n in out] == ['a2', 'C']
    # an inverted node inside a hidden branch is dropped, a clean one kept whole
    out = st.visible_frontier([b1, c, a1], hidden, ancestors, lambda n: n.Children, _hidden_or_ancestor)
    assert [n.name for n in out] == ['C']


def test_hidden_query_uses_internal_names():
    q = st.hidden_query('LcOaNode', 'LcOaNodeHidden')
    cond = q['or'][0]['and'][0]
    assert cond['by_display'] is False and cond['value'] is True and cond['op'] == 'equals'


def test_hidden_query_is_valid_for_pynavis():
    try:
        from pynavis import _query
    except ImportError:
        raise _compat.SkipTest('pynavis not importable')
    q = _query.Query.from_dict(st.hidden_query('LcOaNode', 'LcOaNodeHidden'))
    assert _query.validate(q) == []
    assert q.groups[0][0].by_display is False


def test_file_rows_and_checked():
    models = [{'index': 0, 'name': 'Arch.nwc', 'file': r'C:\m\Arch.nwc', 'source': r'C:\m\Arch.rvt',
               'units': 'Feet'},
              {'index': 1, 'name': 'MEP.ifc', 'file': '', 'source': '', 'units': 'Millimeters'}]
    rows = st.file_rows(models, {0: 25000, 1: 12})
    assert rows[0] == {'value': 0, 'cells': ['Arch.nwc', 'RVT', 'Feet', '20,000+']}
    assert rows[1]['cells'][1] == 'IFC' and rows[1]['cells'][3] == '12'
    assert st.checked_files(models, ['mep.IFC']) == [1]
    assert st.source_type('noext') == ''


def test_set_names():
    values = st.name_values(['Ducts', 'Ducts', 'Pipes', ''], ['Arch.nwc'], 1204,
                            {'date': datetime.date(2026, 10, 5), 'file': 'Hospital'})
    name, missing = st.set_name(st.SAVE_DEFAULTS['template'], values)
    assert name == 'Ducts - 1,204 items - 2026-10-05' and missing == []
    name, missing = st.set_name('{model} {nope}', values)
    assert name == 'Arch.nwc {nope}' and missing == ['nope']
    assert st.set_name('   ', {})[0] == 'Selection'
    assert st.set_name('{category}', {'category': ''})[0] == 'Selection'
    assert st.most_common([], 'x') == 'x'


def test_panel_yaml_lines_are_key_value():
    """Regression: two-line captions must be written with the two characters backslash-n.
    A real line break leaves a bare line that pyNavis' flat YAML reader skips, so the
    button showed only its first word ('Select' instead of 'Select Similar')."""
    import io
    import os
    tab = os.path.join(_compat.ROOT, 'Playground.extension', 'Model.tab')
    bad = []
    for panel in ('Select.panel', 'Find.panel'):
        for folder, _dirs, files in os.walk(os.path.join(tab, panel)):
            if 'bundle.yaml' not in files:
                continue
            path = os.path.join(folder, 'bundle.yaml')
            with io.open(path, 'r', encoding='utf-8') as handle:
                for line in handle.read().split(chr(10)):
                    text = line.strip()
                    if text and not text.startswith('#') and not text.startswith('- ') and ':' not in text:
                        bad.append('%s: %s' % (path, text))
    assert bad == [], bad
