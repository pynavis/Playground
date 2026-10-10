# -*- coding: utf-8 -*-
"""Per-document and global JSON stores, in one of three places.

    s = store.Store('issue-pins', doc_path)           # one JSON value per document
    pins = s.load(default=[])
    s.save(pins)
    s.update(lambda pins: pins + [new_pin], default=[])

    r = store.RecordStore('rfis', doc_path)           # one JSON file per record
    r.put({'id': 'RFI-%03d' % r.next_number('RFI-'), 'title': 'Duct clash'})
    for rfi in r.list(): ...

Where the data lives (mode; None means config 'data_mode'):

    'local'   <data_root>\\docs\\<doc_key>\\<name>.json      and <data_root>\\global\\<name>.json
    'shared'  <team_root>\\docs\\<doc_key(shared)>\\...     and <team_root>\\global\\<name>.json
    'model'   inside the NWF/NWD (namo.docdb), scope 'doc' only

'shared' keys documents by file NAME (colleagues map drives differently) and falls back
to 'local' (logged, .note set) while the shared folder is unreachable. 'model' falls back
to 'local' (logged, .note set) when the document database is unavailable (outside
Navisworks, no document); a 'global' store is never kept in the model.

Reads never raise: a missing file is the default, a damaged one is renamed
'<file>.corrupt-<timestamp>' and reads as the default (logged). Writes are atomic and
raise IOError on failure, so callers can toast it.
"""
import copy
import os
import re

from namo import naming, paths, session

SCOPES = ('doc', 'global')
MODES = ('local', 'shared', 'model')


def _config_mode():
    try:
        from namo import config
        return config.get('data_mode') or 'local'
    except Exception:
        return 'local'


def _resolve(name, doc_path, scope, mode, doc):
    """(effective_mode, root_folder_or_None, note_or_None) for a store."""
    if scope not in SCOPES:
        raise ValueError('scope must be one of %s, not %r' % (', '.join(SCOPES), scope))
    requested = (mode or _config_mode() or 'local').lower()
    if requested not in MODES:
        raise ValueError('mode must be one of %s, not %r' % (', '.join(MODES), mode))
    note = None
    effective = requested
    if effective == 'model':
        if scope != 'doc':
            effective = 'local'
        else:
            from namo import docdb
            if docdb.available(doc):
                return 'model', None, None
            note = 'Model data is unavailable here; using local data.'
            session.log('warning', 'store %s: document database unavailable, using local files' % name)
            effective = 'local'
    if effective == 'shared':
        if paths.team_available():
            root = paths.team_root()
            if scope == 'doc':
                return 'shared', os.path.join(root, 'docs', paths.doc_key(doc_path, shared=True)), None
            return 'shared', os.path.join(root, 'global'), None
        if paths.shared_root():
            note = 'The shared folder is unreachable; using local data.'
        else:
            note = 'No shared folder is set in Playground settings; using local data.'
        session.log('warning', 'store %s: shared folder unavailable, using local files' % name)
        effective = 'local'
    root = paths.data_root()
    if scope == 'doc':
        return effective, os.path.join(root, 'docs', paths.doc_key(doc_path)), note
    return effective, os.path.join(root, 'global'), note


def _model_key(name):
    return 'store:%s' % name


class Store(object):
    """One JSON value per document (scope 'doc') or per user/team (scope 'global').

    Attributes: name, scope, mode (the EFFECTIVE mode after any fallback), path (the
    JSON file, None in model mode), note (a user-facing sentence when a fallback
    happened, else None), doc_path.
    """

    def __init__(self, name, doc_path=None, scope='doc', mode=None, doc=None):
        if not name or not str(name).strip():
            raise ValueError('a store needs a name')
        self.name = str(name).strip()
        self.doc_path = doc_path or ''
        self.scope = scope
        self.doc = doc
        self.mode, folder, self.note = _resolve(self.name, doc_path, scope, mode, doc)
        self.folder = folder
        self.path = (os.path.join(folder, paths.safe_filename(self.name) + '.json')
                     if folder else None)

    def __repr__(self):
        return '<Store %s %s %s>' % (self.name, self.scope, self.mode)

    def load(self, default=None):
        """The stored value, or default (missing, damaged, unreadable). Never raises."""
        if self.mode == 'model':
            from namo import docdb
            return docdb.kv_get(_model_key(self.name), default, doc=self.doc)
        return paths.load_json(self.path, default)

    def save(self, value):
        """Stores value (JSON-serialisable). Raises IOError when it cannot be written."""
        if self.mode == 'model':
            from namo import docdb
            docdb.kv_set(_model_key(self.name), value, doc=self.doc)
            return
        paths.write_json(self.path, value)

    def update(self, fn, default=None):
        """Read-modify-write under a lock: new = fn(current or a copy of default), saved
        and returned. When fn returns None the (mutated in place) current value is saved.
        File modes hold '<file>.lock' meanwhile so team members do not lose each other's
        edits. Raises IOError when the result cannot be written."""
        if self.mode == 'model':
            value = self.load(copy.deepcopy(default))
            new = fn(value)
            new = value if new is None else new
            self.save(new)
            return new
        with paths.FileLock(self.path):
            value = self.load(copy.deepcopy(default))
            new = fn(value)
            new = value if new is None else new
            self.save(new)
            return new

    def exists(self):
        """True when something is stored."""
        if self.mode == 'model':
            from namo import docdb
            return _model_key(self.name) in docdb.kv_keys(_model_key(self.name), doc=self.doc)
        return os.path.exists(self.path)

    def delete(self):
        """Removes the stored value. True when something was removed. IOError on failure."""
        if self.mode == 'model':
            from namo import docdb
            return bool(docdb.kv_delete(_model_key(self.name), doc=self.doc))
        if not os.path.exists(self.path):
            return False
        try:
            os.remove(self.path)
        except OSError as error:
            raise IOError('Could not delete %s: %s' % (self.path, error))
        return True


# ---- one file per record --------------------------------------------------------

_SAFE_ID_CHARS = set('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_.')


def id_to_filename(record_id):
    """A reversible file name for a record id: letters, digits, '-', '_' and '.' stay,
    everything else becomes %XX (UTF-8). A trailing dot and Windows device names are
    escaped too. NOTE Windows file names ignore case, so 'RFI-1' and 'rfi-1' share a file."""
    text = str(record_id)
    out = []
    for ch in text:
        if ch in _SAFE_ID_CHARS:
            out.append(ch)
        else:
            for byte in bytearray(ch.encode('utf-8')):
                out.append('%%%02X' % byte)
    name = ''.join(out)
    if name.endswith('.'):
        name = name[:-1] + '%2E'
    if name.split('.')[0].upper() in paths._RESERVED:
        name = '%%%02X' % ord(name[0]) + name[1:]
    return name + '.json'


def filename_to_id(filename):
    """Inverse of id_to_filename (the '.json' extension is optional)."""
    name = filename[:-5] if filename.lower().endswith('.json') else filename
    data = bytearray()
    i = 0
    while i < len(name):
        ch = name[i]
        if ch == '%' and i + 2 < len(name) and re.match(r'[0-9A-Fa-f]{2}$', name[i + 1:i + 3]):
            data.append(int(name[i + 1:i + 3], 16))
            i += 3
            continue
        data.extend(ch.encode('utf-8'))
        i += 1
    return bytes(data).decode('utf-8', 'replace')


def _trailing_number(text, prefix):
    if prefix and not text.lower().startswith(prefix.lower()):
        return None
    match = re.search(r'(\d+)$', text[len(prefix):])
    return int(match.group(1)) if match else None


def next_number_of(ids, prefix=''):
    """Pure: 1 + the largest trailing number among ids that start with prefix
    (case-insensitive), or 1 when there is none. ['RFI-001', 'RFI-007'] -> 8."""
    best = 0
    for record_id in ids:
        n = _trailing_number(str(record_id), prefix or '')
        if n is not None and n > best:
            best = n
    return best + 1


def sort_records(records):
    """Records sorted by id in natural order ('RFI-2' before 'RFI-10'). New list."""
    return sorted(records, key=lambda r: naming.natural_key(str(r.get('id', ''))))


class RecordStore(object):
    """Many records, one JSON file each, under <root>\\<name>\\ (doc or global scope).

    Separate files mean two people editing DIFFERENT records never clobber each other.
    In model mode the records live in docdb's records table (collection = name).
    Attributes as Store: name, scope, mode, folder (None in model mode), note.
    """

    def __init__(self, name, doc_path=None, scope='doc', mode=None, doc=None):
        if not name or not str(name).strip():
            raise ValueError('a record store needs a name')
        self.name = str(name).strip()
        self.doc_path = doc_path or ''
        self.scope = scope
        self.doc = doc
        self.mode, root, self.note = _resolve(self.name, doc_path, scope, mode, doc)
        self.folder = os.path.join(root, paths.safe_filename(self.name)) if root else None

    def __repr__(self):
        return '<RecordStore %s %s %s>' % (self.name, self.scope, self.mode)

    def _path(self, record_id):
        return os.path.join(self.folder, id_to_filename(record_id))

    def list(self):
        """Every record (dicts), sorted by id in natural order. Damaged files are moved
        aside and skipped (logged); a record without an 'id' gets its file's id. Never raises."""
        if self.mode == 'model':
            from namo import docdb
            return sort_records(docdb.records(self.name, doc=self.doc))
        if not os.path.isdir(self.folder):
            return []
        out = []
        try:
            names = sorted(os.listdir(self.folder))
        except OSError as error:
            session.log('warning', 'could not list %s: %s' % (self.folder, error))
            return []
        for filename in names:
            if not filename.lower().endswith('.json'):
                continue
            record = paths.load_json(os.path.join(self.folder, filename), None)
            if not isinstance(record, dict):
                continue
            if not record.get('id'):
                record['id'] = filename_to_id(filename)
            out.append(record)
        return sort_records(out)

    def ids(self):
        """Sorted ids (natural order)."""
        return [r['id'] for r in self.list()]

    def get(self, id):
        """The record with this id, or None. Never raises."""
        if self.mode == 'model':
            from namo import docdb
            return docdb.record_get(self.name, str(id), doc=self.doc)
        record = paths.load_json(self._path(id), None)
        if not isinstance(record, dict):
            return None
        record.setdefault('id', str(id))
        return record

    def put(self, record):
        """Writes one record (a dict with a non-empty 'id'), replacing any record with that
        id. Returns the record. ValueError without an id; IOError when it cannot be written."""
        if not isinstance(record, dict) or not str(record.get('id', '')).strip():
            raise ValueError("a record needs a non-empty 'id'")
        record_id = str(record['id']).strip()
        record['id'] = record_id
        if self.mode == 'model':
            from namo import docdb
            docdb.record_put(self.name, record_id, record, doc=self.doc)
            return record
        paths.write_json(self._path(record_id), record)
        return record

    def delete(self, id):
        """Removes a record. True when one was removed; IOError when it cannot be."""
        if self.mode == 'model':
            from namo import docdb
            return bool(docdb.record_delete(self.name, str(id), doc=self.doc))
        path = self._path(id)
        if not os.path.exists(path):
            return False
        try:
            os.remove(path)
        except OSError as error:
            raise IOError('Could not delete %s: %s' % (path, error))
        return True

    def next_number(self, prefix=''):
        """1 + the largest trailing number among ids starting with prefix; 1 when none."""
        return next_number_of(self._all_ids(), prefix)

    def _all_ids(self):
        if self.mode == 'model':
            return [r.get('id', '') for r in self.list()]
        if not os.path.isdir(self.folder):
            return []
        try:
            return [filename_to_id(n) for n in os.listdir(self.folder) if n.lower().endswith('.json')]
        except OSError:
            return []

    def add(self, record, prefix='', width=3):
        """Gives record the next free id (prefix + number zero-padded to width, e.g.
        'RFI-007') and writes it, holding a folder lock meanwhile so two people adding
        at once do not get the same number. Returns the record."""
        if self.mode == 'model':
            record['id'] = '%s%0*d' % (prefix, width, self.next_number(prefix))
            return self.put(record)
        paths.ensure_dir(self.folder)
        with paths.FileLock(os.path.join(self.folder, '_add')):
            record['id'] = '%s%0*d' % (prefix, width, self.next_number(prefix))
            return self.put(record)


# ---- the active document --------------------------------------------------------


def _active(doc=None):
    from pynavis import doc as _doc
    d = doc if doc is not None else _doc.get_doc()
    return d, _doc.get_filename(d)


def for_active_doc(name, **kw):
    """Store(name, doc_path=<active document's file>, doc=<active document>, **kw).
    Needs Navisworks (lazy pynavis.doc import)."""
    d, filename = _active(kw.pop('doc', None))
    return Store(name, doc_path=filename, doc=d, **kw)


def records_for_active_doc(name, **kw):
    """RecordStore for the active document, like for_active_doc."""
    d, filename = _active(kw.pop('doc', None))
    return RecordStore(name, doc_path=filename, doc=d, **kw)
