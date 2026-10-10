# -*- coding: utf-8 -*-
"""namo.docdb: SQL text and value handling, run against real SQLite through SqliteBackend.

The Navisworks backend itself needs Navisworks; dev/notes/foundation-F2.md lists the
in-app checks for it."""
import _compat
from _compat import raises

from namo import docdb, session


def sqlite_backend():
    try:
        return docdb.SqliteBackend()
    except ImportError:
        raise _compat.SkipTest('sqlite3 not available on this engine')


def with_backend(fn):
    def wrapper():
        backend = sqlite_backend()
        previous = docdb.use_backend(backend)
        try:
            return fn(backend)
        finally:
            docdb.use_backend(previous)
            backend.close()
    wrapper.__name__ = fn.__name__
    return wrapper


def test_sql_text_is_parameterised_and_matches_the_contract():
    assert docdb.SQL_CREATE_KV == ('CREATE TABLE IF NOT EXISTS playground_kv '
                                   '(key TEXT PRIMARY KEY, value TEXT, updated TEXT)')
    assert docdb.SQL_CREATE_RECORDS == ('CREATE TABLE IF NOT EXISTS playground_records '
                                        '(collection TEXT, id TEXT, value TEXT, updated TEXT, '
                                        'PRIMARY KEY (collection, id))')
    for name in dir(docdb):
        if name.startswith('SQL_') and name not in ('SQL_CREATE_KV', 'SQL_CREATE_RECORDS', 'SQL_TABLES'):
            sql = getattr(docdb, name)
            assert "'" not in sql, name                       # values only through @parameters
    assert docdb.params(value='v', key='k') == [('@key', 'k'), ('@value', 'v')]
    assert docdb.statement(docdb.SQL_KV_DELETE, key='a') == (docdb.SQL_KV_DELETE, [('@key', 'a')])


def test_encode_decode():
    assert docdb.encode({'b': 1, 'a': [1, 'x']}) == '{"a":[1,"x"],"b":1}'
    assert docdb.encode('caf' + chr(0xE9)) == '"caf\\u00e9"'           # ASCII-only text
    assert docdb.decode('{"a":1}') == {'a': 1}
    assert docdb.decode(None, 'd') == 'd'
    assert docdb.decode('', 'd') == 'd'
    assert docdb.decode('{bad', 'd') == 'd'
    raises(TypeError, docdb.encode, object())


def test_pure_helpers():
    assert docdb.create_statements([]) == [(docdb.SQL_CREATE_KV, []), (docdb.SQL_CREATE_RECORDS, [])]
    assert docdb.create_statements(['PLAYGROUND_KV']) == [(docdb.SQL_CREATE_RECORDS, [])]
    assert docdb.create_statements(['playground_kv', 'playground_records']) == []
    assert docdb.filter_keys(['b', 'a', 'ab', None, 'B'], 'a') == ['a', 'ab']
    assert docdb.filter_keys(['b', 'a'], '') == ['a', 'b']
    rows = [('RFI-10', '{"t":1}'), ('RFI-9', '{"id":"other","t":2}'), ('X', '5'), ('bad', '{')]
    # A dict keeps its own 'id' (setdefault); other values are wrapped; bad JSON is skipped;
    # the order is natural by id ('other' < 'RFI-10' < 'X').
    assert docdb.rows_to_records(rows) == [{'id': 'other', 't': 2}, {'id': 'RFI-10', 't': 1},
                                           {'id': 'X', 'value': 5}]


def test_available_is_false_outside_navisworks():
    assert docdb.use_backend(None) is None
    assert docdb.available() is False                      # no Navisworks API here
    assert docdb.kv_get('x', 'default') == 'default'       # reads never raise
    assert docdb.kv_keys() == []
    assert docdb.records('rfis') == []
    raises(IOError, docdb.kv_set, 'x', 1)                   # writes do
    raises(IOError, docdb.record_put, 'c', 'i', {})


@with_backend
def test_kv_round_trip(backend):
    assert docdb.available()
    assert docdb.kv_get('pins', []) == []                   # tables not created by reads
    assert backend.query(docdb.SQL_TABLES, []) == []
    docdb.kv_set('pins', [{'x': 1.5, 'label': 'A'}])
    assert docdb.kv_get('pins') == [{'label': 'A', 'x': 1.5}]
    docdb.kv_set('pins', {'replaced': True})
    assert docdb.kv_get('pins') == {'replaced': True}
    docdb.kv_set('store:other', 3)
    docdb.kv_set('a', None)
    assert docdb.kv_get('a', 'dflt') is None                # stored null is a value
    assert docdb.kv_keys() == ['a', 'pins', 'store:other']
    assert docdb.kv_keys('store:') == ['store:other']
    assert docdb.kv_delete('pins') is True
    assert docdb.kv_delete('pins') is False
    assert docdb.kv_get('pins', 'gone') == 'gone'
    rows = backend.query('SELECT key, updated FROM playground_kv WHERE key = @key', [('@key', 'a')])
    assert rows and len(rows[0][1]) == 19                    # 'YYYY-MM-DDTHH:MM:SS'


@with_backend
def test_records_round_trip(backend):
    assert docdb.records('rfis') == []
    assert docdb.record_get('rfis', 'RFI-1') is None
    docdb.record_put('rfis', 'RFI-10', {'title': 'Ten'})
    docdb.record_put('rfis', 'RFI-9', {'id': 'RFI-9', 'title': 'Nine'})
    docdb.record_put('issues', 'I-1', {'title': 'Other collection'})
    assert [r['id'] for r in docdb.records('rfis')] == ['RFI-9', 'RFI-10']
    assert docdb.record_get('rfis', 'RFI-10') == {'id': 'RFI-10', 'title': 'Ten'}
    docdb.record_put('rfis', 'RFI-10', {'title': 'Ten again'})
    assert docdb.record_get('rfis', 'RFI-10')['title'] == 'Ten again'
    assert docdb.collections() == ['issues', 'rfis']
    assert docdb.record_delete('rfis', 'RFI-9') is True
    assert docdb.record_delete('rfis', 'RFI-9') is False
    assert [r['id'] for r in docdb.records('rfis')] == ['RFI-10']
    assert len(docdb.records('issues')) == 1


@with_backend
def test_damaged_values_are_skipped(backend):
    docdb.kv_set('ok', 1)
    backend.execute([("INSERT OR REPLACE INTO playground_kv (key, value, updated) VALUES ('bad', '{', '')", [])])
    assert docdb.kv_get('bad', 'dflt') == 'dflt'
    docdb.record_put('c', 'good', {'a': 1})
    backend.execute([("INSERT INTO playground_records (collection, id, value, updated) "
                      "VALUES ('c', 'broken', 'nope', '')", [])])
    assert [r['id'] for r in docdb.records('c')] == ['good']
    assert any('not valid JSON' in text for _l, text in session.recent_log('warning'))


@with_backend
def test_write_failures_raise_ioerror(backend):
    docdb.kv_set('x', 1)
    backend.connection.execute('DROP TABLE playground_kv')
    backend.connection.execute('CREATE TABLE playground_kv (other TEXT)')    # wrong shape
    raises(IOError, docdb.kv_set, 'x', 2)
    assert docdb.kv_get('x', 'dflt') == 'dflt'               # read failure: default, logged


class Recorder(object):
    """A backend that records what docdb asks for: proves creation runs as a Reset
    transaction once, before the data write."""

    def __init__(self):
        self.calls = []
        self.tables = []

    def query(self, sql, pairs):
        self.calls.append(('query', sql, pairs))
        if sql == docdb.SQL_TABLES:
            return [(t,) for t in self.tables]
        return []

    def execute(self, statements, reset=False):
        self.calls.append(('execute', [s for s, _p in statements], reset))
        for sql, _p in statements:
            if sql == docdb.SQL_CREATE_KV:
                self.tables.append('playground_kv')
            if sql == docdb.SQL_CREATE_RECORDS:
                self.tables.append('playground_records')
        return [1] * len(statements)


def test_tables_are_created_once_in_a_reset_transaction():
    recorder = Recorder()
    previous = docdb.use_backend(recorder)
    try:
        docdb.kv_set('a', 1)
        docdb.kv_set('b', 2)
    finally:
        docdb.use_backend(previous)
    executes = [c for c in recorder.calls if c[0] == 'execute']
    assert executes[0] == ('execute', [docdb.SQL_CREATE_KV, docdb.SQL_CREATE_RECORDS], True)
    assert executes[1] == ('execute', [docdb.SQL_KV_SET], False)
    assert executes[2] == ('execute', [docdb.SQL_KV_SET], False)
    assert len(executes) == 3
