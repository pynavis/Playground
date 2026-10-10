# -*- coding: utf-8 -*-
"""namo.setexchange: the Playground sets XML (write, read back, escaping, typed values),
trees, identity keys for resolving static sets."""
import _compat

from namo import setexchange as sx


TREE = [
    {'kind': 'folder', 'name': 'By Level', 'children': [
        {'kind': 'search', 'name': 'Level 1', 'conditions': [
            {'category': 'Element', 'prop': 'Level', 'op': 'equals', 'value': 'Level 1', 'ignore_case': True},
            {'category': 'Element ID', 'prop': 'Value', 'op': 'gt', 'value': 3.5},
            {'category': 'Element', 'prop': 'Mark', 'op': 'has_property'},
            {'category': 'Item', 'op': 'has_category'},
            {'op': 'raw', 'text': 'odd <condition> & "quotes"'}]},
        {'kind': 'folder', 'name': 'Nested/Deep', 'children': [
            {'kind': 'static', 'name': 'Picked', 'items': [
                {'model': 'Arch.nwc', 'model_index': 0, 'path': '0/3/12', 'name': 'Basic Wall',
                 'element_id': '312045', 'unique_id': 'abc-123', 'instance_guid': 'GUID-1'},
                {'model': 'MEP.nwc', 'model_index': 1, 'path': '0/1', 'name': 'Duct\x01 "A"'}]}]}]},
    {'kind': 'search', 'name': 'Typed', 'conditions': [
        {'category': 'E', 'prop': 'Count', 'op': 'equals', 'value': 7},
        {'category': 'E', 'prop': 'On', 'op': 'equals', 'value': False}]},
]
META = {'document': 'Hospital & Co.nwf', 'exported': '2026-10-05T14:30:00', 'user': 'amol',
        'models': ['Arch.nwc', 'MEP.nwc']}


def test_round_trip():
    text = sx.write_xml(META, TREE)
    assert text.startswith('<?xml version="1.0" encoding="utf-8"?>\n<playground-sets version="1"')
    meta, tree = sx.read_xml(text)
    assert meta['document'] == 'Hospital & Co.nwf' and meta['models'] == ['Arch.nwc', 'MEP.nwc']
    level1 = tree[0]['children'][0]
    assert level1['conditions'][0] == {'category': 'Element', 'prop': 'Level', 'op': 'equals',
                                       'value': 'Level 1', 'ignore_case': True}
    assert level1['conditions'][1]['value'] == 3.5
    assert level1['conditions'][2] == {'category': 'Element', 'prop': 'Mark', 'op': 'has_property'}
    assert level1['conditions'][3] == {'category': 'Item', 'op': 'has_category'}
    assert level1['conditions'][4] == {'op': 'raw', 'text': 'odd <condition> & "quotes"'}
    static = tree[0]['children'][1]['children'][0]
    assert static['items'][0] == TREE[0]['children'][1]['children'][0]['items'][0]
    assert static['items'][1]['name'] == 'Duct "A"'          # control character dropped
    typed = tree[1]['conditions']
    assert typed[0]['value'] == 7 and isinstance(typed[0]['value'], int)
    assert typed[1]['value'] is False


def test_read_rejects_foreign_files():
    _compat.raises(ValueError, sx.read_xml, 'not xml at all <')
    _compat.raises(ValueError, sx.read_xml, '<exchange><x/></exchange>')
    error = _compat.raises(ValueError, sx.read_xml, '<playground-sets version="2"></playground-sets>')
    assert 'version 2' in str(error)


def test_flatten_and_describe():
    flat = sx.flatten(TREE)
    assert [(f, n['name']) for f, n in flat] == [('By Level', 'Level 1'),
                                                ('By Level/Nested\\/Deep', 'Picked'), ('', 'Typed')]
    assert sx.describe_tree(TREE) == (2, 1, 2)
    rows = sx.preview_rows(flat)
    assert rows[1]['cells'] == ['By Level/Nested/Deep', 'Picked', 'Static', '2 items']
    assert rows[0]['cells'][2] == 'Search'


def test_tree_from_keeps_order_and_needed_folders():
    rows = [{'guid': 'a', 'folder_names': ['F', 'G']}, {'guid': 'b', 'folder_names': []},
            {'guid': 'c', 'folder_names': ['F']}, {'guid': 'skip', 'folder_names': ['Unused']}]
    payloads = {'a': {'kind': 'search', 'name': 'A'}, 'b': {'kind': 'search', 'name': 'B'},
                'c': {'kind': 'static', 'name': 'C', 'items': []}}
    tree = sx.tree_from(rows, payloads)
    assert [n.get('name') for n in tree] == ['F', 'B']
    assert [n['name'] for n in tree[0]['children']] == ['G', 'C']
    assert tree[0]['children'][0]['children'][0]['name'] == 'A'


def test_identity_keys_and_index():
    ref = {'model': 'Arch.NWC', 'instance_guid': 'ABC', 'unique_id': 'U-1', 'ifc_guid': '',
           'element_id': '312045'}
    assert sx.identity_keys(ref) == [('instance_guid', 'abc'), ('unique_id', 'u-1'),
                                     ('element_id', 'arch.nwc|312045')]
    assert sx.identity_keys({'instance_guid': sx.EMPTY_GUID}) == []
    index = sx.wanted_index([ref, {'unique_id': 'u-1'}])
    assert index[('unique_id', 'u-1')] == [0, 1]
    assert sx.kinds_wanted(index) == set(['instance_guid', 'unique_id', 'element_id'])


def test_entry_of_and_query():
    assert sx.entry_of({'model': 'A', 'model_index': '2', 'path': '0/1'}) == {'m': 'A', 'i': 2, 'p': '0/1'}
    assert sx.entry_of({'model_index': 'bad'})['i'] == -1
    node = TREE[1]
    assert sx.search_query(node) == {'or': [{'and': node['conditions']}]}
    assert sx.has_raw(TREE[0]['children'][0]) and not sx.has_raw(node)


def test_value_helpers():
    assert sx.type_of(True) == 'bool' and sx.type_of(1) == 'int' and sx.type_of(1.5) == 'float'
    assert sx.value_from('2.0', 'int') == 2.0
    assert sx.value_text(0.1) == repr(0.1)
    assert sx.value_from(sx.value_text(0.1), 'float') == 0.1
