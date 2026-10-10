# -*- coding: utf-8 -*-
"""Playground data stored INSIDE the document: Navisworks' per-document SQLite database.

Navisworks gives every document a SQLite database (Document.Database) that is saved
with the NWF/NWD. Playground keeps two tables there, created on the first write:

    playground_kv      (key TEXT PRIMARY KEY, value TEXT, updated TEXT)
    playground_records (collection TEXT, id TEXT, value TEXT, updated TEXT,
                    PRIMARY KEY (collection, id))

Values are JSON text. Writing makes the document modified: the data travels with the
file once the user saves it. Nothing here is undoable with Ctrl+Z.

    docdb.available()                        # False outside Navisworks / without a document
    docdb.kv_set('issue-pins', pins)         # raises IOError when it cannot write
    docdb.kv_get('issue-pins', [])           # never raises; default when missing or unreadable
    docdb.record_put('rfis', 'RFI-001', {...}); docdb.records('rfis')

Split: the SQL text, JSON (de)serialisation and row shaping are pure and unit tested
against real SQLite (SqliteBackend, also handy for other modules' tests through
use_backend). NavisworksBackend is the API half; it lazy-imports pynavis._api, so this
module imports anywhere. API members used (all in the 2026 dump):
    Document.Database -> DocumentDatabase
    DocumentDatabase.Value -> NavisworksConnection
    DocumentDatabase.BeginTransaction(DatabaseChangedAction) -> NavisworksTransaction
    NavisworksTransaction.Connection / Commit() / Rollback()
    NavisworksConnection.CreateCommand() / State / Open() / Close()
    NavisworksCommand(String, NavisworksConnection) / CommandText / Parameters /
        ExecuteNonQuery() / ExecuteReader()
    NavisworksParameterCollection.AddWithValue(String, Object)
    NavisworksDataAdapter(NavisworksCommand) + DbDataAdapter.Fill(DataTable) (inherited)
    NavisWorksDataReader.Read() / FieldCount / IsDBNull(i) / GetValue(i) / Close()
Reads go through NavisworksDataAdapter.Fill (Autodesk's documented route, which opens
and closes the connection itself), falling back to ExecuteReader on an explicitly
opened connection. Table creation runs in a DatabaseChangedAction.Reset transaction
(schema change), data writes in an Edited one. See dev/notes/foundation-F2.md for the
in-app checks these assumptions still need.
"""
import datetime
import json

from namo import naming, session

KV_TABLE = 'playground_kv'
RECORDS_TABLE = 'playground_records'

SQL_CREATE_KV = ('CREATE TABLE IF NOT EXISTS playground_kv '
                 '(key TEXT PRIMARY KEY, value TEXT, updated TEXT)')
SQL_CREATE_RECORDS = ('CREATE TABLE IF NOT EXISTS playground_records '
                      '(collection TEXT, id TEXT, value TEXT, updated TEXT, '
                      'PRIMARY KEY (collection, id))')
SQL_TABLES = ("SELECT name FROM sqlite_master WHERE type = 'table' "
              "AND name IN ('playground_kv', 'playground_records')")
SQL_KV_GET = 'SELECT value FROM playground_kv WHERE key = @key'
SQL_KV_SET = ('INSERT OR REPLACE INTO playground_kv (key, value, updated) '
              'VALUES (@key, @value, @updated)')
SQL_KV_DELETE = 'DELETE FROM playground_kv WHERE key = @key'
SQL_KV_KEYS = 'SELECT key FROM playground_kv'
SQL_REC_LIST = 'SELECT id, value FROM playground_records WHERE collection = @collection'
SQL_REC_GET = 'SELECT value FROM playground_records WHERE collection = @collection AND id = @id'
SQL_REC_PUT = ('INSERT OR REPLACE INTO playground_records (collection, id, value, updated) '
               'VALUES (@collection, @id, @value, @updated)')
SQL_REC_DELETE = 'DELETE FROM playground_records WHERE collection = @collection AND id = @id'
SQL_REC_COLLECTIONS = 'SELECT DISTINCT collection FROM playground_records'

CREATE = ((KV_TABLE, SQL_CREATE_KV), (RECORDS_TABLE, SQL_CREATE_RECORDS))

# Test seam: a backend object used instead of the active document (see use_backend).
_BACKEND_OVERRIDE = None


# ---- pure helpers ------------------------------------------------------------------


def encode(value):
    """The JSON text stored for a value (sorted keys, ASCII only, compact).
    Raises TypeError/ValueError for values JSON cannot hold."""
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(',', ':'))


def decode(text, default=None):
    """The value stored as JSON text; default for NULL, '' or text that will not parse."""
    if text is None:
        return default
    try:
        text = str(text)
        if not text.strip():
            return default
        return json.loads(text)
    except Exception:
        session.log('warning', 'document data value is not valid JSON; ignored')
        return default


def now_text():
    """The 'updated' stamp: local time, ISO 8601 to the second."""
    return datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S')


def params(**values):
    """Named SQL parameters as a sorted list of ('@name', value) pairs (deterministic)."""
    return [('@' + name, values[name]) for name in sorted(values)]


def statement(sql, **values):
    """(sql, params(**values)): one parameterised statement."""
    return (sql, params(**values))


def create_statements(present):
    """CREATE TABLE statements for the Playground tables missing from present (table names)."""
    present = [str(name).lower() for name in present]
    return [(sql, []) for table, sql in CREATE if table not in present]


def filter_keys(keys, prefix=''):
    """Keys starting with prefix (case-sensitive), sorted."""
    prefix = prefix or ''
    return sorted(str(k) for k in keys if k is not None and str(k).startswith(prefix))


def rows_to_records(rows):
    """[(id, json_text)] -> [dict] in natural id order. A dict value gets 'id' set to the
    row id when it has none; any other value becomes {'id': id, 'value': value}. Rows
    whose JSON will not parse are skipped (logged)."""
    out = []
    for row in rows:
        record_id, text = str(row[0]), row[1]
        value = decode(text, _MISSING)
        if value is _MISSING:
            continue
        if isinstance(value, dict):
            value.setdefault('id', record_id)
        else:
            value = {'id': record_id, 'value': value}
        out.append(value)
    return sorted(out, key=lambda r: naming.natural_key(str(r.get('id', ''))))


class _Missing(object):
    pass


_MISSING = _Missing()


# ---- backends ------------------------------------------------------------------------


class SqliteBackend(object):
    """A backend over Python's sqlite3 (CPython, and IronPython where IronPython.SQLite
    is present). Runs the exact same SQL as the document; for tests and offline tools.

        previous = docdb.use_backend(docdb.SqliteBackend())   # ':memory:' by default
        try: ... finally: docdb.use_backend(previous)
    """

    def __init__(self, path=':memory:'):
        import sqlite3
        self.connection = sqlite3.connect(path)

    @staticmethod
    def _bind(pairs):
        return dict((name.lstrip('@:$'), value) for name, value in pairs)

    def query(self, sql, pairs):
        cursor = self.connection.execute(sql, self._bind(pairs))
        try:
            return [tuple(row) for row in cursor.fetchall()]
        finally:
            cursor.close()

    def execute(self, statements, reset=False):
        counts = []
        try:
            for sql, pairs in statements:
                cursor = self.connection.execute(sql, self._bind(pairs))
                counts.append(cursor.rowcount if cursor.rowcount is not None else -1)
                cursor.close()
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise
        return counts

    def close(self):
        self.connection.close()


def _from_db(value):
    """A .NET database value as a plain Python value (DBNull -> None)."""
    if value is None:
        return None
    try:
        from System import DBNull
        if isinstance(value, DBNull):
            return None
    except Exception:
        pass
    return value


class NavisworksBackend(object):
    """The document's own database (API half; needs Navisworks)."""

    def __init__(self, doc):
        if doc is None:
            raise IOError('There is no open document.')
        self.doc = doc

    def _database(self):
        database = self.doc.Database
        if database is None:
            raise IOError('This document has no database.')
        return database

    def query(self, sql, pairs):
        connection = self._database().Value
        if connection is None:
            raise IOError('The document database has no connection.')
        route = session.get('docdb', 'read_route')
        routes = [self._read_adapter, self._read_reader]
        if route == 'reader':
            routes.reverse()
        last = None
        for reader in routes:
            try:
                rows = reader(connection, sql, pairs)
                session.set('docdb', 'read_route', 'reader' if reader == self._read_reader else 'adapter')
                return rows
            except Exception as error:
                last = error
                session.log('debug', 'docdb read via %s failed: %s' % (reader.__name__, error))
        raise IOError('Could not read the document database: %s' % last)

    @staticmethod
    def _read_adapter(connection, sql, pairs):
        import clr
        clr.AddReference('System.Data')
        from System.Data import DataTable
        from pynavis import _api  # noqa: F401 (loads Autodesk.Navisworks.Api first)
        from Autodesk.Navisworks.Api.Data import NavisworksCommand, NavisworksDataAdapter
        command = NavisworksCommand(sql, connection)
        for name, value in pairs:
            command.Parameters.AddWithValue(name, value)
        adapter = NavisworksDataAdapter(command)
        table = DataTable()
        adapter.Fill(table)
        width = table.Columns.Count
        rows = []
        for row in table.Rows:
            rows.append(tuple(_from_db(row[i]) for i in range(width)))
        return rows

    @staticmethod
    def _read_reader(connection, sql, pairs):
        import clr
        clr.AddReference('System.Data')
        from System.Data import ConnectionState
        opened = False
        if connection.State != ConnectionState.Open:
            connection.Open()
            opened = True
        try:
            command = connection.CreateCommand()
            command.CommandText = sql
            for name, value in pairs:
                command.Parameters.AddWithValue(name, value)
            reader = command.ExecuteReader()
            rows = []
            try:
                while reader.Read():
                    width = reader.FieldCount
                    rows.append(tuple(None if reader.IsDBNull(i) else _from_db(reader.GetValue(i))
                                      for i in range(width)))
            finally:
                reader.Close()
            return rows
        finally:
            if opened:
                connection.Close()

    def execute(self, statements, reset=False):
        from pynavis import _api  # noqa: F401 (loads Autodesk.Navisworks.Api first)
        from Autodesk.Navisworks.Api.Data import DatabaseChangedAction
        action = DatabaseChangedAction.Reset if reset else DatabaseChangedAction.Edited
        transaction = self._database().BeginTransaction(action)
        committed = False
        try:
            connection = transaction.Connection
            counts = []
            for sql, pairs in statements:
                command = connection.CreateCommand()
                command.CommandText = sql
                try:
                    command.Transaction = transaction
                except Exception:
                    pass
                for name, value in pairs:
                    command.Parameters.AddWithValue(name, value)
                counts.append(int(command.ExecuteNonQuery()))
            transaction.Commit()
            committed = True
            return counts
        finally:
            if not committed:
                try:
                    transaction.Rollback()
                except Exception:
                    pass
            try:
                transaction.Dispose()
            except Exception:
                pass


def use_backend(backend):
    """Test seam: every call uses backend (None restores the document). Returns the
    previous override."""
    global _BACKEND_OVERRIDE
    previous = _BACKEND_OVERRIDE
    _BACKEND_OVERRIDE = backend
    return previous


def _active_doc(doc):
    if doc is not None:
        return doc
    from pynavis._api import Application
    return Application.ActiveDocument


def _backend(doc=None):
    if _BACKEND_OVERRIDE is not None:
        return _BACKEND_OVERRIDE
    return NavisworksBackend(_active_doc(doc))


def _present(backend):
    return [str(row[0]).lower() for row in backend.query(SQL_TABLES, [])]


def _read(doc, table, sql, pairs):
    """Rows, [] when the table does not exist yet, None when the read failed (logged)."""
    try:
        backend = _backend(doc)
        if table not in _present(backend):
            return []
        return backend.query(sql, pairs)
    except Exception as error:
        session.log('warning', 'could not read document data: %s' % error)
        return None


def _write(doc, statements):
    """Runs statements in one Edited transaction, creating the tables first (in a Reset
    transaction) when they are missing. Raises IOError on any failure."""
    try:
        backend = _backend(doc)
        missing = create_statements(_present(backend))
        if missing:
            backend.execute(missing, reset=True)
        return backend.execute(statements)
    except IOError:
        raise
    except Exception as error:
        raise IOError('Could not write Playground data into the document: %s' % error)


# ---- public API -----------------------------------------------------------------------


def available(doc=None):
    """True when the document database can be read here (Navisworks, an open document).
    Never raises."""
    try:
        _present(_backend(doc))
        return True
    except Exception:
        return False


def kv_get(key, default=None, doc=None):
    """The JSON value stored under key, or default (missing, unreadable). Never raises."""
    rows = _read(doc, KV_TABLE, SQL_KV_GET, params(key=str(key)))
    if not rows:
        return default
    return decode(rows[0][0], default)


def kv_set(key, value, doc=None):
    """Stores value (JSON-serialisable) under key, replacing any previous value. The
    document becomes modified. Raises IOError when it cannot write."""
    text = encode(value)
    _write(doc, [statement(SQL_KV_SET, key=str(key), value=text, updated=now_text())])


def kv_delete(key, doc=None):
    """Removes key. True when a row was removed. Raises IOError when it cannot write."""
    if not _read(doc, KV_TABLE, SQL_KV_GET, params(key=str(key))):
        return False
    counts = _write(doc, [statement(SQL_KV_DELETE, key=str(key))])
    return bool(counts and counts[0] > 0)


def kv_keys(prefix='', doc=None):
    """Sorted keys starting with prefix (case-sensitive). [] when unreadable."""
    rows = _read(doc, KV_TABLE, SQL_KV_KEYS, []) or []
    return filter_keys([row[0] for row in rows], prefix)


def records(collection, doc=None):
    """Every record in a collection as dicts, natural id order (see rows_to_records).
    [] when unreadable. Never raises."""
    rows = _read(doc, RECORDS_TABLE, SQL_REC_LIST, params(collection=str(collection))) or []
    return rows_to_records(rows)


def record_get(collection, id, doc=None):
    """One record (dict, 'id' filled in) or None. Never raises."""
    rows = _read(doc, RECORDS_TABLE, SQL_REC_GET,
                 params(collection=str(collection), id=str(id)))
    if not rows:
        return None
    found = rows_to_records([(str(id), rows[0][0])])
    return found[0] if found else None


def record_put(collection, id, value, doc=None):
    """Stores value (JSON-serialisable, usually a dict) as one record, replacing any record
    with that id. Raises IOError when it cannot write."""
    text = encode(value)
    _write(doc, [statement(SQL_REC_PUT, collection=str(collection), id=str(id),
                           value=text, updated=now_text())])


def record_delete(collection, id, doc=None):
    """Removes one record. True when a row was removed. Raises IOError when it cannot write."""
    if not _read(doc, RECORDS_TABLE, SQL_REC_GET,
                 params(collection=str(collection), id=str(id))):
        return False
    counts = _write(doc, [statement(SQL_REC_DELETE, collection=str(collection), id=str(id))])
    return bool(counts and counts[0] > 0)


def collections(doc=None):
    """Sorted names of every record collection in the document. [] when unreadable."""
    rows = _read(doc, RECORDS_TABLE, SQL_REC_COLLECTIONS, []) or []
    return sorted(str(row[0]) for row in rows if row[0] is not None)
