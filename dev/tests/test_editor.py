# -*- coding: utf-8 -*-
"""namo.editor pure half: indentation, block indent, newlines, find, syntax checks,
completion context and ranking, the bundle tree."""
import io
import os

import _compat

from namo import editor as ed


def test_indent_after():
    assert ed.indent_after('if x:') == '    '
    assert ed.indent_after('    for a in b:  ') == '        '
    assert ed.indent_after('    def f(x):  # note') == '        '
    assert ed.indent_after('        return x') == '    '
    assert ed.indent_after('    pass') == ''
    assert ed.indent_after('x = 1') == ''
    assert ed.indent_after('\tx = 1') == '    '
    assert ed.indent_after("    print('a:')") == '    '


def test_indent_block():
    text = 'a\nb\n\nc\nd'
    new, start, length = ed.indent_block(text, 2, 4)            # 'b\n\nc' partly selected
    assert new == 'a\n    b\n\n    c\nd' and start == 2 and new[start:start + length] == '    b\n\n    c'
    back, start, length = ed.indent_block(new, 2, length, dedent=True)
    assert back == text
    assert ed.indent_block('  x', 0, 0, dedent=True)[0] == 'x'
    assert ed.indent_block('\tx', 0, 0, dedent=True)[0] == 'x'
    new, _s, _l = ed.indent_block('a\nb\n', 0, 2)                # selection ends after a line break
    assert new == '    a\nb\n'
    assert ed.block_span('ab\ncd\nef', 4, 0) == (3, 5)


def test_newlines_and_find():
    assert ed.normalize_newlines('a\r\nb\nc\rd', True) == 'a\r\nb\r\nc\r\nd'
    assert ed.normalize_newlines('a\r\nb', False) == 'a\nb'
    text = 'Alpha beta ALPHA'
    assert ed.find_index(text, 'alpha', 1) == 11
    assert ed.find_index(text, 'alpha', 12) == 0                 # wraps
    assert ed.find_index(text, 'alpha', 1, match_case=True) == -1
    assert ed.find_index(text, 'alpha', 11, backwards=True) == 0
    assert ed.find_index(text, 'alpha', 0, backwards=True) == 11  # wraps back
    assert ed.find_index(text, '', 0) == -1


def test_syntax_error():
    assert ed.syntax_error('x = 1\r\nprint(x)\r\n') is None
    line, column, message = ed.syntax_error('x = 1\nif x\n    pass\n')
    assert line == 2 and message


def test_completion_context_and_names():
    assert ed.completion_context('    doc.Mod') == ('doc', 'Mod')
    assert ed.completion_context('x = Application.ActiveDocument.') == ('Application.ActiveDocument', '')
    assert ed.completion_context('pri') == ('', 'pri')
    assert ed.completion_context('x = 3.') is None
    assert ed.completion_context('a..b') is None
    assert ed.completion_context('') == ('', '')
    assert ed.completion_context('make().na') is None
    source = 'from pynavis import forms, toast as t\nimport os.path\nimport json as j\nmy_value = 1\n'
    assert ed.imports_of(source) == {'forms': 'pynavis.forms', 't': 'pynavis.toast', 'os': 'os', 'j': 'json'}
    names = ed.base_names(source)
    assert 'my_value' in names and 'forms' in names and 'while' in names and 'len' in names
    assert ed.identifiers('a bb ccc bb') == ['bb', 'ccc']


def test_rank_names():
    names = ['Models', 'modelItems', 'ActiveView', 'CurrentSelection', 'mode', '_private']
    assert ed.rank_names('Mod', names)[:3] == ['Models', 'mode', 'modelItems']
    assert ed.rank_names('cs', names) == []
    assert ed.rank_names('cursel', names) == ['CurrentSelection']
    assert ed.rank_names('', names) == ['ActiveView', 'CurrentSelection', 'Models', 'mode', 'modelItems']
    assert 'mode' not in ed.rank_names('mode', ['mode'])


def test_complete_falls_back_to_names_in_the_file():
    source = 'thing = make()\nthing.alpha = 1\nthing.alpine = 2\nvalue = th'
    assert ed.complete(source, 'thing.al') == ['alpha', 'alpine']
    assert ed.complete(source, 'value = th') == ['thing']
    assert ed.complete(source, 'x = 3.') == []
    assert ed.complete(source, '') == []


def _write(path, text=''):
    folder = os.path.dirname(path)
    if not os.path.isdir(folder):
        os.makedirs(folder)
    with io.open(path, 'w', encoding='utf-8') as handle:
        handle.write(text)


def make_extension(base):
    ext = os.path.join(base, 'MyTools.extension')
    _write(os.path.join(ext, 'extension.yaml'), u'name: MyTools\n')
    _write(os.path.join(ext, 'startup.py'), u'"""Start."""\n')
    _write(os.path.join(ext, 'lib', 'helpers.py'), u'X = 1\n')
    panel = os.path.join(ext, 'MyTools.tab', 'Tools.panel')
    _write(os.path.join(panel, 'bundle.yaml'), u'layout:\n  - Count_Doors\n')
    _write(os.path.join(panel, 'Count_Doors.pushbutton', 'script.py'), u'"""Counts doors."""\nx = 1\n')
    _write(os.path.join(panel, 'Count_Doors.pushbutton', 'config.py'), u'"""Options."""\n')
    _write(os.path.join(panel, 'Count_Doors.pushbutton', 'icon.png'), u'')
    _write(os.path.join(panel, 'Two.stack', 'B.pushbutton', 'script.py'), u'"""B."""\n')
    _write(os.path.join(panel, 'Two.stack', 'C.pushbutton', 'script.py'), u'"""C."""\n')
    return ext


def test_scan_tree_flatten_and_filter():
    base = _compat.tmpdir('editor_tree')
    ext = make_extension(base)
    tree = ed.scan_tree(ext, 'MyTools')
    assert tree['label'] == 'MyTools' and tree['kind'] == 'ext'
    assert [n['label'] for n in tree['children']] == ['MyTools', 'lib', 'extension.yaml', 'startup.py']
    rows = ed.flatten([tree], set([ext.lower()]))
    assert [r[1]['label'] for r in rows] == ['MyTools', 'MyTools', 'lib', 'extension.yaml', 'startup.py']
    everything = ed.all_folder_paths([tree])
    labels = [(d, n['label']) for d, n in ed.flatten([tree], everything)]
    assert (3, 'Count Doors') in labels and (4, 'script.py') in labels and (4, 'config.py') in labels
    assert (2, 'helpers.py') in labels and 'icon.png' not in [l for _d, l in labels]
    found = ed.filter_tree([tree], 'config')
    labels = [n['label'] for _d, n in ed.flatten(found, ed.all_folder_paths(found))]
    assert labels == ['MyTools', 'MyTools', 'Tools', 'Count Doors', 'config.py']
    assert ed.filter_tree([tree], '') == [tree]


def test_bundle_of_and_writable():
    base = _compat.tmpdir('editor_bundle')
    ext = make_extension(base)
    script = os.path.join(ext, 'MyTools.tab', 'Tools.panel', 'Count_Doors.pushbutton', 'script.py')
    assert ed.bundle_of(script) == (ext, os.path.dirname(script), False)
    config = os.path.join(os.path.dirname(script), 'config.py')
    assert ed.bundle_of(config)[2] is True
    assert ed.bundle_of(os.path.join(ext, 'lib', 'helpers.py')) is None
    assert ed.bundle_of(os.path.join(base, 'loose.py')) is None
    items = [{'name': 'pyNavis', 'folder': 'a', 'writable': True}, {'name': 'MyTools', 'folder': 'b', 'writable': True},
             {'name': 'Locked', 'folder': 'c', 'writable': False}, {'name': 'MyTools', 'folder': 'B', 'writable': True}]
    assert [i['name'] for i in ed.writable_extensions(items)] == ['MyTools']
    assert ed.caret_text(3, 7) == 'Line 3, column 7'


def test_line_helpers():
    text = 'ab\ncd\r\nef'
    assert ed.line_of(text, 0) == 1 and ed.line_of(text, 3) == 2 and ed.line_of(text, 8) == 3
    assert ed.line_start(text, 1) == 0 and ed.line_start(text, 2) == 3 and ed.line_start(text, 3) == 7
    assert ed.line_start(text, 9) == 7
