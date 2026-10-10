# -*- coding: utf-8 -*-
"""namo.find_library: library entries, merge rules, files (publish, list, rename, delete)."""
import datetime
import os

import _compat

from namo import find_library as fl
from namo import paths

Q = {'or': [{'and': [{'category': 'Element', 'prop': 'Category', 'op': 'equals', 'value': 'Ducts'}]}]}


def entry(name, folder=None, value='Ducts'):
    q = {'or': [{'and': [{'category': 'Element', 'prop': 'Category', 'op': 'equals', 'value': value}]}]}
    return {'name': name, 'folder': folder, 'query': q}


def test_clean_entry():
    assert fl.clean_entry(entry(' Ducts ', ' Systems '))['name'] == 'Ducts'
    assert fl.clean_entry(entry('Ducts', ' '))['folder'] is None
    assert fl.clean_entry({'name': 'Static', 'folder': None, 'items': 3}) is None
    assert fl.clean_entry({'name': '', 'query': Q}) is None
    assert fl.clean_entry('junk') is None
    # regression: export_all's 'DisplayString:Ducts' is published as 'Ducts'
    published = fl.clean_entry(entry('Ducts', None, 'DisplayString:Ducts'))
    assert published['query'] == Q


def test_merge():
    old = [entry('Ducts', 'Systems', 'old'), entry('Pipes')]
    new = [entry('ducts', 'SYSTEMS', 'new'), entry('Walls')]
    merged = fl.merge(old, new)
    assert [e['name'] for e in merged] == ['ducts', 'Pipes', 'Walls']
    assert merged[0]['query']['or'][0]['and'][0]['value'] == 'new'
    assert [e['name'] for e in fl.merge(old, new, replace=True)] == ['ducts', 'Walls']
    assert fl.merge([entry('A'), entry('a')], []) == [entry('A')]      # duplicates collapse


def test_read_library():
    lib = fl.make_library('MEP', [entry('Ducts')], 'amol', datetime.datetime(2026, 10, 5, 14, 30, 1, 5))
    assert lib['updated'] == '2026-10-05T14:30:01'
    back = fl.read_library(lib)
    assert back['name'] == 'MEP' and back['sets'][0]['name'] == 'Ducts'
    assert fl.read_library({'format': 'x'}) is None
    assert fl.read_library(dict(lib, version=2)) is None


def test_rows():
    rows = fl.choose_rows([entry('Ducts', 'Systems')])
    assert rows == [{'value': 0, 'cells': ['Systems', 'Ducts', 'Element > Category = Ducts']}]
    libs = [{'name': 'MEP', 'path': 'p', 'count': 3, 'updated': '2026-10-05T14:30:00', 'user': 'amol'}]
    assert fl.library_rows(libs) == [{'value': 'p', 'cells': ['MEP', 3, '2026-10-05 14:30:00', 'amol']}]


def test_import_spec():
    lib = fl.make_library('MEP', [entry('Ducts', 'Systems'), entry('Pipes')])
    spec = fl.import_spec(lib, [1, 7])
    assert spec == {'sets': [{'name': 'Pipes', 'folder': None, 'query': entry('Pipes')['query']}]}


def test_files_publish_list_rename_delete():
    folder = _compat.tmpdir('setslibrary')
    path, total, added = fl.publish('MEP coordination', [entry('Ducts'), {'name': 'x', 'items': 2}],
                                    where=folder, user='amol')
    assert os.path.basename(path) == 'MEP coordination.json' and (total, added) == (1, 1)
    path, total, added = fl.publish('MEP coordination', [entry('Pipes')], where=folder, user='amol')
    assert (total, added) == (2, 1)
    path2, total, _added = fl.publish('Other', [entry('Walls')], replace=True, where=folder, user='b')
    paths.atomic_write_text(os.path.join(folder, 'broken.json'), '{not json')
    listed = fl.list_libraries(folder)
    assert [lib['name'] for lib in listed] == ['MEP coordination', 'Other']
    assert listed[0]['count'] == 2 and listed[0]['user'] == 'amol'
    renamed = fl.rename(path2, 'Walls only')
    assert os.path.basename(renamed) == 'Walls only.json' and not os.path.exists(path2)
    assert fl.load(renamed)['name'] == 'Walls only'
    _compat.raises(ValueError, fl.rename, renamed, 'MEP coordination')
    _compat.raises(ValueError, fl.rename, renamed, '  ')
    assert fl.delete(renamed) and not fl.delete(renamed)
