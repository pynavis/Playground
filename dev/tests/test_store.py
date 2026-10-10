# -*- coding: utf-8 -*-
"""namo.store: Store and RecordStore in local, shared and model (docdb) modes."""
import io
import os
import threading

import _compat
from _compat import raises

from namo import config, docdb, paths, session, store

DOC = r'C:\Projects\Tower\Coordination.nwf'


def isolated(fn):
    def wrapper():
        folder = _compat.tmpdir('f2-store-' + fn.__name__)
        previous = paths.redirect(folder)
        try:
            return fn(folder)
        finally:
            paths.redirect(previous)
    wrapper.__name__ = fn.__name__
    return wrapper


@isolated
def test_local_layout(folder):
    s = store.Store('issue-pins', DOC)
    assert s.mode == 'local' and s.note is None and s.scope == 'doc'
    assert s.path == os.path.join(folder, 'pyNavis', 'playground', 'docs', paths.doc_key(DOC), 'issue-pins.json')
    g = store.Store('last-color-scheme', scope='global')
    assert g.path == os.path.join(folder, 'pyNavis', 'playground', 'global', 'last-color-scheme.json')
    u = store.Store('x')                                     # no document: 'untitled'
    assert os.path.join('docs', 'untitled') in u.path
    raises(ValueError, store.Store, 'x', DOC, 'project')
    raises(ValueError, store.Store, 'x', DOC, 'doc', 'cloud')
    raises(ValueError, store.Store, '  ')


@isolated
def test_load_save_update_delete(folder):
    s = store.Store('pins', DOC)
    assert s.load() is None and s.load([]) == [] and not s.exists()
    s.save([1, 2])
    assert s.exists() and s.load() == [1, 2]
    assert s.update(lambda v: v + [3]) == [1, 2, 3]
    assert s.update(lambda v: v.append(4)) == [1, 2, 3, 4]          # None return: in-place edit
    fresh = store.Store('counts', DOC)
    assert fresh.update(lambda v: v.update(n=1), default={}) == {'n': 1}
    assert fresh.update(lambda v: dict(v, n=v['n'] + 1)) == {'n': 2}
    assert fresh.load() == {'n': 2}
    first_default = {}
    store.Store('d', DOC).update(lambda v: v.update(a=1), default=first_default)
    assert first_default == {}                                       # default is copied
    assert s.delete() is True and s.delete() is False and s.load('gone') == 'gone'
    assert not os.path.exists(s.path + '.lock')


@isolated
def test_damaged_file_is_moved_aside(folder):
    s = store.Store('pins', DOC)
    paths.ensure_dir(os.path.dirname(s.path))
    with io.open(s.path, 'w', encoding='utf-8') as handle:
        handle.write(u'{"half":')
    assert s.load(default=[]) == []
    names = os.listdir(os.path.dirname(s.path))
    assert any(n.startswith('pins.json.corrupt-') for n in names)
    s.save(['new'])
    assert s.load() == ['new']


@isolated
def test_save_failure_raises_ioerror(folder):
    s = store.Store('pins', DOC)
    os.makedirs(s.path)                                              # a folder blocks the file
    raises(IOError, s.save, [1])
    assert s.load('dflt') == 'dflt'


@isolated
def test_mode_comes_from_config(folder):
    config.save({'data_mode': 'shared', 'shared_root': os.path.join(folder, 'share')})
    paths.forget_reachability()
    s = store.Store('pins', DOC)                                     # share missing: local
    assert s.mode == 'local' and 'unreachable' in s.note
    os.makedirs(os.path.join(folder, 'share'))
    paths.forget_reachability()
    s = store.Store('pins', DOC)
    assert s.mode == 'shared' and s.note is None
    key = paths.doc_key(DOC, shared=True)
    assert s.path == os.path.join(folder, 'share', 'docs', key, 'pins.json')
    other_drive = store.Store('pins', r'X:\Mapped\Elsewhere\COORDINATION.nwf')
    assert other_drive.path == s.path                               # same file name, same data
    g = store.Store('teamwide', scope='global')
    assert g.path == os.path.join(folder, 'share', 'global', 'teamwide.json')
    s.save({'shared': True})
    assert other_drive.load() == {'shared': True}
    assert store.Store('pins', DOC, mode='local').mode == 'local'   # explicit mode wins


@isolated
def test_shared_mode_without_a_folder_says_so(folder):
    s = store.Store('pins', DOC, mode='shared')
    assert s.mode == 'local' and s.note == 'No shared folder is set in Playground settings; using local data.'


@isolated
def test_model_mode_falls_back_without_a_document_database(folder):
    s = store.Store('pins', DOC, mode='model')
    assert s.mode == 'local' and s.note
    assert any('document database unavailable' in text for _l, text in session.recent_log('warning'))
    g = store.Store('pins', scope='global', mode='model')
    assert g.mode == 'local' and g.note is None                      # global is never in the model


def with_sqlite(fn):
    def wrapper():
        try:
            backend = docdb.SqliteBackend()
        except ImportError:
            raise _compat.SkipTest('sqlite3 not available on this engine')
        previous = docdb.use_backend(backend)
        folder = _compat.tmpdir('f2-store-' + fn.__name__)
        previous_root = paths.redirect(folder)
        try:
            return fn(backend)
        finally:
            paths.redirect(previous_root)
            docdb.use_backend(previous)
            backend.close()
    wrapper.__name__ = fn.__name__
    return wrapper


@with_sqlite
def test_model_mode_uses_docdb(backend):
    s = store.Store('pins', DOC, mode='model')
    assert s.mode == 'model' and s.path is None and s.note is None
    assert s.load([]) == [] and not s.exists()
    s.save([{'x': 1}])
    assert s.exists() and s.load() == [{'x': 1}]
    assert docdb.kv_get('store:pins') == [{'x': 1}]
    assert s.update(lambda v: v + [{'x': 2}]) == [{'x': 1}, {'x': 2}]
    assert s.delete() and s.load('gone') == 'gone'
    config.save({'data_mode': 'model'})
    assert store.Store('pins', DOC).mode == 'model'                  # from config
    r = store.RecordStore('rfis', DOC)
    assert r.mode == 'model' and r.folder is None
    r.put({'id': 'RFI-002', 'title': 'B'})
    added = r.add({'title': 'C'}, prefix='RFI-')
    assert added['id'] == 'RFI-003'
    assert [x['id'] for x in r.list()] == ['RFI-002', 'RFI-003']
    assert r.get('RFI-002')['title'] == 'B'
    assert r.delete('RFI-002') and not r.delete('RFI-002')
    assert r.ids() == ['RFI-003']


@isolated
def test_record_store_files(folder):
    r = store.RecordStore('rfis', DOC)
    assert r.folder == os.path.join(folder, 'pyNavis', 'playground', 'docs', paths.doc_key(DOC), 'rfis')
    assert r.list() == [] and r.next_number('RFI-') == 1 and r.get('RFI-1') is None
    r.put({'id': 'RFI-10', 'title': 'Ten'})
    r.put({'id': 'RFI-9', 'title': 'Nine'})
    r.put({'id': 'a/b: c?', 'title': 'Odd id'})
    assert [x['id'] for x in r.list()] == ['a/b: c?', 'RFI-9', 'RFI-10']
    assert r.get('a/b: c?')['title'] == 'Odd id'
    assert r.next_number('RFI-') == 11 and r.next_number('rfi-') == 11 and r.next_number('X') == 1
    r.put({'id': 'RFI-10', 'title': 'Ten again'})
    assert r.get('RFI-10')['title'] == 'Ten again'
    assert r.delete('RFI-9') is True and r.delete('RFI-9') is False
    raises(ValueError, r.put, {'title': 'no id'})
    raises(ValueError, r.put, {'id': '  '})
    g = store.RecordStore('macros', scope='global')
    assert g.folder == os.path.join(folder, 'pyNavis', 'playground', 'global', 'macros')


@isolated
def test_record_store_skips_damaged_files(folder):
    r = store.RecordStore('rfis', DOC)
    r.put({'id': 'RFI-1'})
    with io.open(os.path.join(r.folder, 'RFI-2.json'), 'w', encoding='utf-8') as handle:
        handle.write(u'nope')
    with io.open(os.path.join(r.folder, 'RFI-3.json'), 'w', encoding='utf-8') as handle:
        handle.write(u'{"title": "no id inside"}')
    with io.open(os.path.join(r.folder, 'notes.txt'), 'w', encoding='utf-8') as handle:
        handle.write(u'ignored')
    assert [x['id'] for x in r.list()] == ['RFI-1', 'RFI-3']
    assert any(n.startswith('RFI-2.json.corrupt-') for n in os.listdir(r.folder))


@isolated
def test_record_add_allocates_unique_numbers_across_threads(folder):
    r = store.RecordStore('issues', DOC)
    made = []

    def worker():
        for _ in range(5):
            made.append(r.add({'title': 'x'}, prefix='ISS-', width=4)['id'])

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(set(made)) == 20
    assert sorted(made)[0] == 'ISS-0001' and sorted(made)[-1] == 'ISS-0020'
    assert len(r.list()) == 20


def test_id_file_names_round_trip():
    for record_id in ('RFI-001', 'a/b: c?', 'CON', 'trailing.', 'caf' + chr(0xE9), '50%', 'x y'):
        name = store.id_to_filename(record_id)
        assert name.endswith('.json')
        assert paths.safe_filename(name) == name, name
        assert store.filename_to_id(name) == record_id, (record_id, name)
    assert store.id_to_filename('RFI-001') == 'RFI-001.json'


def test_next_number_of():
    assert store.next_number_of(['RFI-001', 'RFI-007', 'X-99', 'RFI-abc']) == 100
    assert store.next_number_of(['RFI-001', 'RFI-007', 'X-99'], 'RFI-') == 8
    assert store.next_number_of([], 'RFI-') == 1
    assert store.next_number_of(['rfi-5'], 'RFI-') == 6


def test_for_active_doc_needs_navisworks():
    raises(ImportError, store.for_active_doc, 'pins')
