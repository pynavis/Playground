# -*- coding: utf-8 -*-
"""namo.templates: named configs per tool, team-shared, import/export."""
import io
import json
import os

import _compat
from _compat import raises

from namo import config, paths, templates


def isolated(fn):
    def wrapper():
        folder = _compat.tmpdir('f2-templates-' + fn.__name__)
        previous = paths.redirect(folder)
        try:
            return fn(folder)
        finally:
            paths.redirect(previous)
    wrapper.__name__ = fn.__name__
    return wrapper


@isolated
def test_save_get_names(folder):
    t = templates.Templates('clash_excel')
    assert t.path == os.path.join(folder, 'pyNavis', 'playground', 'templates', 'clash_excel.json')
    assert t.names() == [] and t.get('x') is None
    config.save({'user': 'Pat'})
    assert t.save('Weekly 10', {'tests': ['A'], 'folder': ''}) == 'Weekly 10'
    t.save('Weekly 9', {'tests': ['B']})
    t.save('  daily  ', {'tests': []})
    assert t.names() == ['daily', 'Weekly 9', 'Weekly 10']
    got = t.get('weekly 10')                                    # case-insensitive lookup
    assert got == {'tests': ['A'], 'folder': ''}
    got['tests'].append('mutated')
    assert t.get('Weekly 10')['tests'] == ['A']                 # a copy
    info = t.info('Weekly 10')
    assert info['user'] == 'Pat' and len(info['updated']) == 19
    t.save('WEEKLY 10', {'tests': ['C']})                       # replaces, keeps one entry
    assert t.names() == ['daily', 'Weekly 9', 'WEEKLY 10']
    with io.open(t.path, 'r', encoding='utf-8') as handle:
        body = json.load(handle)
    assert body['format'] == 'playground-templates' and body['tool'] == 'clash_excel'
    raises(ValueError, t.save, '  ', {})
    raises(ValueError, t.save, 'x', ['not', 'a', 'dict'])
    raises(ValueError, templates.Templates, '')


@isolated
def test_delete_and_rename(folder):
    t = templates.Templates('zone_takeoff')
    t.save('A', {'n': 1})
    t.save('B', {'n': 2})
    assert t.delete('a') is True and t.delete('A') is False
    assert t.rename('B', 'C') == 'C'
    assert t.names() == ['C'] and t.get('C') == {'n': 2}
    t.save('D', {'n': 3})
    raises(ValueError, t.rename, 'C', 'd')
    raises(ValueError, t.rename, 'missing', 'E')
    raises(ValueError, t.rename, 'C', ' ')
    assert t.rename('C', 'c') == 'c'                            # case-only rename is fine
    assert t.names() == ['c', 'D']


@isolated
def test_export_and_import(folder):
    source = templates.Templates('clash_html')
    source.save('One', {'a': 1})
    source.save('Two', {'a': 2})
    out = os.path.join(folder, 'exported.json')
    assert source.export(out) == 2
    assert source.export(os.path.join(folder, 'one.json'), names=['one', 'missing']) == 1
    target = templates.Templates('clash_html')
    target.delete('One')
    target.save('Two', {'a': 'local'})
    assert target.import_file(out) == 2
    assert target.names() == ['One', 'Two', 'Two (2)']
    assert target.get('Two') == {'a': 'local'} and target.get('Two (2)') == {'a': 2}
    assert target.import_file(out, replace=True) == 2
    assert target.get('Two') == {'a': 2}
    other = templates.Templates('kpi_export')
    error = raises(ValueError, other.import_file, out)
    assert 'clash_html' in str(error)
    junk = os.path.join(folder, 'junk.json')
    with io.open(junk, 'w', encoding='utf-8') as handle:
        handle.write(u'{"hello": 1}')
    raises(ValueError, other.import_file, junk)
    raises(ValueError, other.import_file, os.path.join(folder, 'nope.json'))
    with io.open(junk, 'w', encoding='utf-8') as handle:
        handle.write(u'{broken')
    raises(ValueError, other.import_file, junk)
    assert os.path.exists(junk)                                  # an import never moves it aside


@isolated
def test_damaged_file_reads_empty_and_is_kept_aside(folder):
    t = templates.Templates('preflight')
    paths.ensure_dir(os.path.dirname(t.path))
    with io.open(t.path, 'w', encoding='utf-8') as handle:
        handle.write(u'{oops')
    assert t.names() == []
    t.save('Fresh', {})
    assert t.names() == ['Fresh']
    assert any('.corrupt-' in n for n in os.listdir(os.path.dirname(t.path)))


@isolated
def test_all_tools_and_team_root(folder):
    assert templates.all_tools() == []
    templates.Templates('b_tool').save('x', {})
    templates.Templates('a_tool').save('y', {})
    empty = templates.Templates('c_tool')
    empty.save('z', {})
    empty.delete('z')
    assert templates.all_tools() == ['a_tool', 'b_tool']
    share = os.path.join(folder, 'team')
    os.makedirs(share)
    config.save({'shared_root': share})
    paths.forget_reachability()
    t = templates.Templates('a_tool')
    assert t.path == os.path.join(share, 'templates', 'a_tool.json')
    assert t.names() == [] and templates.all_tools() == []
