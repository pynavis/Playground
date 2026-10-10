# -*- coding: utf-8 -*-
"""Where Playground issues live: one record per issue, per model file, in the data mode
namo.config chooses, plus the session events every issue view listens to.

    from namo import issuestore
    s = issuestore.for_doc()                  # the active document's register
    rows = s.list()                           # normalised issues, natural id order
    issue = s.create({'title': 'Duct hits beam'}, prefix='RFI-')
    issue, note = s.update('RFI-001', {'status': 'Resolved'}, note='Fixed on site')
    s.add_comment('RFI-001', 'Checked by Jane')
    s.add_image('RFI-001', r'C:\\temp\\shot.jpg', kind='screenshot', move=True)
    issuestore.subscribe('my-view', lambda kind, ids, key: refresh())

Storage (a namo.store RecordStore named 'issues' for the document):

    local    %APPDATA%\\pyNavis\\playground\\docs\\<doc key>\\issues\\<id>.json
    shared   <shared folder>\\docs\\<file name key>\\issues\\<id>.json  (team; one file per
             issue so people editing DIFFERENT issues never collide)
    model    inside the NWF/NWD (namo.docdb records, collection 'issues'): travels with
             the model; the user must SAVE the model to keep changes; not undoable

Images (snapshots, screenshots, BCF snapshots) are files in a media folder:

    local / shared   <the issues folder>\\_media\\<issue guid>\\
    model            %APPDATA%\\pyNavis\\playground\\issue-media\\<issue guid>\\  (LOCAL to this computer:
                     the records travel inside the model, the pictures do not)

Concurrency in a shared folder: last writer wins PER ISSUE. Every save re-reads the
stored record under a lock; when it changed since the editor loaded it (its 'rev'
moved on) the saved fields are the writer's, but comments and images from the other
version are merged in, and save() returns a sentence saying who else changed it.
New ids are handed out under the same folder lock RecordStore.add uses, so two people
adding at once never get the same number.

Writes need a saved document (the register is keyed by the model file): NotSaved says
so. Reads of an unsaved document return nothing.

Session events: every write here calls notify(kind, ids, key) so the Issues pane, the
pins and any other open view refresh, whichever tool made the change. Listeners live
in a namo.session holder (they survive pyNavis' per-run module reload) and must be
quick and never raise (they are wrapped and logged anyway).
"""

import copy
import hashlib
import os
import re
import shutil
import traceback

from namo import issues, paths, session
from namo import store as _store

NAME = 'issues'
MEDIA = '_media'
MODEL_MEDIA = 'issue-media'
_EVENTS = 'issues_events'
_CACHE = 'issues_cache'
# One plain folder name: a guid from a hand-edited register never reaches outside _media.
_SAFE_SEGMENT = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]*$')


class NotSaved(ValueError):
    """The document has no file yet, so it has no issue register."""


NOT_SAVED = 'Save the model first: issues are kept with the model file.'


# ---- session events -------------------------------------------------------------------


def _events():
    holder = session.holder(_EVENTS)
    if getattr(holder, 'listeners', None) is None:
        holder.listeners = {}
        holder.version = 0
    return holder


def subscribe(key, fn):
    """Calls fn(kind, ids, doc_key) after every issue write in this session ('created',
    'updated', 'deleted', 'imported'). One listener per key: subscribing again with the
    same key replaces it (a Reload re-subscribes cleanly). Returns an unsubscribe
    callable."""
    holder = _events()
    holder.listeners[str(key)] = fn

    def unsubscribe():
        current = holder.listeners.get(str(key))
        if current is fn:
            holder.listeners.pop(str(key), None)
    return unsubscribe


def unsubscribe(key):
    """Removes the listener under key. True when one was there."""
    return _events().listeners.pop(str(key), None) is not None


def listeners():
    """Sorted listener keys (tests, diagnostics)."""
    return sorted(_events().listeners)


def version():
    """A counter bumped by every notify(): views compare it to skip needless reloads."""
    return _events().version


def notify(kind, ids, doc_key=None):
    """Tells every listener that issues changed. Never raises."""
    holder = _events()
    holder.version += 1
    for key in sorted(holder.listeners):
        fn = holder.listeners.get(key)
        if fn is None:
            continue
        try:
            fn(kind, [str(i) for i in ids or []], doc_key)
        except Exception:
            session.log('error', 'issue listener %s failed:\n%s' % (key, traceback.format_exc()))


# ---- documents ------------------------------------------------------------------------


def active_doc():
    """The active Navisworks document (None outside Navisworks)."""
    try:
        from pynavis._api import Application
        return Application.ActiveDocument
    except Exception:
        return None


def doc_path_of(doc):
    """The document's file name ('' when unsaved or unreadable)."""
    if doc is None:
        return ''
    try:
        return str(doc.FileName or '')
    except Exception:
        return ''


def for_doc(doc=None, mode=None):
    """The IssueStore of a document (default: the active one)."""
    document = doc if doc is not None else active_doc()
    return IssueStore(doc_path_of(document), doc=document, mode=mode)


# ---- pure helpers ------------------------------------------------------------------------


def image_name(kind, ext, existing, now=None):
    """'snapshot-20261005-143000.jpg' (with ' (2)' style suffixes '-2' when taken)."""
    when = now or issues._now()
    base = '%s-%s' % (kind or 'image', when.strftime('%Y%m%d-%H%M%S'))
    ext = ext if ext.startswith('.') else '.' + ext
    taken = set(e.lower() for e in existing)
    name = base + ext
    n = 2
    while name.lower() in taken:
        name = '%s-%d%s' % (base, n, ext)
        n += 1
    return name


# ---- the store ----------------------------------------------------------------------------


class IssueStore(object):
    """The issue register of one model file. Attributes: doc_path, doc, mode (effective),
    note (a user-facing sentence when the data mode fell back, else None), folder (the
    records folder, None in model mode), key (the document key events carry)."""

    def __init__(self, doc_path, doc=None, mode=None):
        self.doc_path = doc_path or ''
        self.doc = doc
        self.records = _store.RecordStore(NAME, doc_path=self.doc_path, doc=doc, mode=mode)
        self.mode = self.records.mode
        self.note = self.records.note
        self.folder = self.records.folder
        self.key = paths.doc_key(self.doc_path)

    def __repr__(self):
        return '<IssueStore %s %s>' % (self.key, self.mode)

    # -- state --

    @property
    def saved(self):
        """True when the document has a file (and so a register)."""
        return bool(self.doc_path)

    def require_saved(self):
        if not self.saved:
            raise NotSaved(NOT_SAVED)

    def describe(self):
        """'Local data' / 'Shared folder' / 'In the model (save to keep)' + fallback note."""
        text = {'local': 'Local data', 'shared': 'Shared folder',
                'model': 'In the model (save the model to keep changes)'}.get(self.mode, self.mode)
        return text

    # -- reading --

    def _path(self, issue_id):
        return os.path.join(self.folder, _store.id_to_filename(issue_id))

    def _read_files(self):
        """Records from the folder, re-reading only files whose size or time changed
        since the last read in this session (a shared folder of hundreds of issues stays
        quick to refresh)."""
        if not os.path.isdir(self.folder):
            return []
        cache_holder = session.holder(_CACHE)
        caches = getattr(cache_holder, 'folders', None)
        if caches is None:
            caches = cache_holder.folders = {}
        cache = caches.setdefault(os.path.normcase(self.folder), {})
        try:
            names = sorted(os.listdir(self.folder))
        except OSError as error:
            session.log('warning', 'could not list %s: %s' % (self.folder, error))
            return []
        out = []
        seen = set()
        for name in names:
            if not name.lower().endswith('.json'):
                continue
            path = os.path.join(self.folder, name)
            try:
                info = os.stat(path)
            except OSError:
                continue
            signature = (info.st_mtime, info.st_size)
            seen.add(name)
            hit = cache.get(name)
            if hit is not None and hit[0] == signature:
                record = hit[1]
            else:
                record = paths.load_json(path, None)
                if not isinstance(record, dict):
                    cache.pop(name, None)
                    continue
                if not record.get('id'):
                    record['id'] = _store.filename_to_id(name)
                record = issues.normalise(record)
                cache[name] = (signature, record)
            out.append(copy.deepcopy(record))
        for name in _pylist_keys(cache):
            if name not in seen:
                cache.pop(name, None)
        return out

    def list(self):
        """Every issue (normalised dicts), natural id order. [] for an unsaved document.
        Never raises."""
        if not self.saved:
            return []
        try:
            if self.mode == 'model':
                rows = [issues.normalise(r) for r in self.records.list()]
            else:
                rows = self._read_files()
        except Exception:
            session.log('error', 'issues could not be read:\n%s' % traceback.format_exc())
            return []
        return sorted(rows, key=lambda r: issues.id_sort_key(r.get('id')))

    def get(self, issue_id):
        """The issue with exactly this id (any case on disk), normalised, or None."""
        if not self.saved or not str(issue_id or '').strip():
            return None
        try:
            record = self.records.get(str(issue_id).strip())
        except Exception:
            record = None
        if record is None and self.mode == 'model':
            wanted = str(issue_id).strip().lower()
            for row in self.records.list():
                if str(row.get('id', '')).lower() == wanted:
                    record = row
                    break
        return issues.normalise(record) if isinstance(record, dict) else None

    def find(self, id_or_guid):
        """By id first, then by guid. None when absent."""
        found = self.get(id_or_guid)
        if found is not None:
            return found
        return self.find_guid(id_or_guid)

    def find_guid(self, guid):
        wanted = str(guid or '').strip().lower()
        if not wanted:
            return None
        for issue in self.list():
            if issue['guid'] == wanted:
                return issue
        return None

    def by_guid(self, rows=None):
        """{guid: issue} for every issue (or the given rows)."""
        return dict((i['guid'], i) for i in (rows if rows is not None else self.list()))

    def sources(self, kind, rows=None):
        """{source ref: issue id} for issues made from a source kind ('clash', 'bcf')."""
        out = {}
        for issue in rows if rows is not None else self.list():
            source = issue.get('source') or {}
            if source.get('kind') == kind and source.get('ref'):
                out[source['ref']] = issue['id']
        return out

    # -- writing --

    def _lock(self, path):
        if self.mode == 'model':
            return _NoLock()
        paths.ensure_dir(os.path.dirname(path))
        return paths.FileLock(path)

    def create(self, fields, prefix=None, title_pattern=None, title_values=None, user=None,
               now=None, notify_now=True):
        """Saves a new issue built from fields and returns it with its id: prefix
        ('RFI-'; default 'ISS-') + the next free number for that prefix, handed out under
        the folder lock. title_pattern ('{type} {n:000}') fills the title when fields
        has none ({n} is the new number; title_values add tokens). ValueError when the
        result has no title; NotSaved; IOError."""
        self.require_saved()
        from namo import config, naming
        user = user if user is not None else config.user_name()
        record = issues.new_issue(fields, user, now)
        prefix = issues.clean_prefix(prefix) or issues.DEFAULT_PREFIX
        record['doc'] = os.path.basename(self.doc_path)

        def assign():
            number = self.records.next_number(prefix)
            record['id'] = issues.format_id(prefix, number)
            record['number'] = number
            if not record['title'] and title_pattern:
                values = naming.standard_values(self.doc) if self.doc is not None else {}
                values.update({'type': record['type'], 'trade': record['trade'],
                               'user': user, 'priority': record['priority']})
                values.update(title_values or {})
                text, _missing = naming.render(title_pattern, values, counter=number)
                record['title'] = naming.sanitize(text)
            if not record['title']:
                raise ValueError('Give the issue a title.')
            problems = issues.validate(record)
            if problems:
                raise ValueError(problems[0])
            record['rev'] = 1
            self.records.put(record)

        if self.mode == 'model':
            assign()
        else:
            paths.ensure_dir(self.folder)
            with paths.FileLock(os.path.join(self.folder, '_add')):
                assign()
        if notify_now:
            notify('created', [record['id']], self.key)
        return issues.normalise(record)

    def save(self, issue, base_rev=None, user=None, now=None, notify_now=True):
        """Writes an issue (replacing the stored one) and returns (issue, note).

        base_rev: the rev the caller loaded. When the stored issue has moved on since
        (someone else saved), last writer wins for fields and the other version's
        comments and images are merged in; note is then a sentence for a toast, else
        None. The saved issue's rev is one more than both."""
        self.require_saved()
        record = issues.normalise(issue)
        if not record['id']:
            raise ValueError('An issue needs an id; create it first.')
        problems = issues.validate(record)
        if problems:
            raise ValueError(problems[0])
        note = None
        path = self._path(record['id']) if self.mode != 'model' else None
        with self._lock(path):
            stored = self.get(record['id'])
            if stored is not None:
                base = record['rev'] if base_rev is None else base_rev
                if stored['rev'] > base:
                    record = issues.merge_for_save(record, stored)
                    note = issues.conflict_note(stored)
                record['rev'] = max(record['rev'], stored['rev']) + 1
            else:
                record['rev'] = max(1, record['rev'] + 1)
            self.records.put(record)
        if notify_now:
            notify('updated', [record['id']], self.key)
        return issues.normalise(record), note

    def update(self, issue_id, changes, note=None, user=None, now=None, base_rev=None):
        """Applies changes ({field: value}) with issues.apply_changes and saves.
        Returns (issue, conflict note or None). ValueError for an unknown id."""
        from namo import config
        current = self.get(issue_id)
        if current is None:
            raise ValueError('There is no issue %s in this model.' % issue_id)
        user = user if user is not None else config.user_name()
        updated, changed = issues.apply_changes(current, changes, user, now, note)
        if not changed:
            return current, None
        return self.save(updated, base_rev=base_rev if base_rev is not None else current['rev'],
                         user=user, now=now)

    def add_comment(self, issue_id, text, status_change=None, user=None, now=None):
        """Appends a comment and saves (merging, never losing anyone's). Returns the issue."""
        from namo import config
        current = self.get(issue_id)
        if current is None:
            raise ValueError('There is no issue %s in this model.' % issue_id)
        user = user if user is not None else config.user_name()
        updated = issues.add_comment_to(current, text, user, now, status_change)
        issue, _note = self.save(updated, base_rev=current['rev'], user=user, now=now)
        return issue

    def delete(self, issue_id):
        """Removes the issue and its media folder. True when it existed."""
        self.require_saved()
        current = self.get(issue_id)
        if current is None:
            return False
        removed = self.records.delete(current['id'])
        folder = self.media_folder(current)
        if os.path.isdir(folder):
            try:
                shutil.rmtree(folder)
            except Exception as error:
                session.log('warning', 'could not remove %s: %s' % (folder, error))
        notify('deleted', [current['id']], self.key)
        return bool(removed)

    # -- images --

    def media_root(self):
        if self.folder:
            return os.path.join(self.folder, MEDIA)
        return os.path.join(paths.data_root(), MODEL_MEDIA)

    def media_folder(self, issue, create=False):
        """The folder holding one issue's images (keyed by guid)."""
        name = str(issue.get('guid') or 'unknown')
        if not _SAFE_SEGMENT.match(name):
            name = 'invalid-' + hashlib.sha1(name.encode('utf-8')).hexdigest()[:12]
        folder = os.path.join(self.media_root(), name)
        if create:
            paths.ensure_dir(folder)
        return folder

    def image_path(self, issue, image):
        """Full path of one image entry ('' when the entry has no file)."""
        name = str((image or {}).get('file') or '')
        if not name:
            return ''
        if os.path.isabs(name):
            return name
        return os.path.join(self.media_folder(issue), name)

    def images_on_disk(self, issue):
        """[(image entry, path)] for images whose file exists."""
        out = []
        for image in issue.get('images') or []:
            path = self.image_path(issue, image)
            if path and os.path.exists(path):
                out.append((image, path))
        return out

    def snapshot_path(self, issue):
        """The first existing snapshot (else any image) path, or None."""
        found = self.images_on_disk(issue)
        for image, path in found:
            if image.get('kind') == 'snapshot':
                return path
        return found[0][1] if found else None

    def add_image(self, issue_id, source_path, kind='screenshot', caption='', move=False,
                  replace_kind=False, user=None, now=None, notify_now=True, extra=None):
        """Copies (or moves) an image file into the issue's media folder and records it.
        replace_kind=True drops earlier images of the same kind (their files too): the
        Update view snapshot. extra: more keys for the image entry ({'bcf_viewpoint':
        guid}). Returns the saved issue."""
        from namo import config
        current = self.get(issue_id)
        if current is None:
            raise ValueError('There is no issue %s in this model.' % issue_id)
        if not source_path or not os.path.exists(source_path):
            raise IOError('The image %s does not exist.' % source_path)
        user = user if user is not None else config.user_name()
        folder = self.media_folder(current, create=True)
        ext = os.path.splitext(source_path)[1].lower() or '.jpg'
        existing = [i['file'] for i in current['images']]
        try:
            existing += os.listdir(folder)
        except OSError:
            pass
        name = image_name(kind, ext, existing, now)
        target = os.path.join(folder, name)
        if move:
            shutil.move(source_path, target)
        else:
            shutil.copyfile(source_path, target)
        dropped = []
        if replace_kind:
            dropped = [i for i in current['images'] if i.get('kind') == kind]
            current['images'] = [i for i in current['images'] if i.get('kind') != kind]
        entry = {'file': name, 'kind': kind, 'caption': caption or '',
                 'created': issues.stamp(now), 'by': user}
        for key in sorted(extra or {}):
            entry.setdefault(key, extra[key])
        if kind == 'snapshot':
            current['images'].insert(0, entry)
        else:
            current['images'].append(entry)
        current['modified'] = issues.stamp(now)
        current['modified_by'] = user
        issue, _note = self.save(current, base_rev=current['rev'], user=user, now=now,
                                 notify_now=notify_now)
        for old in dropped:
            path = self.image_path(current, old)
            if path and os.path.exists(path) and path != target:
                try:
                    os.remove(path)
                except OSError:
                    pass
        return issue

    def remove_image(self, issue_id, file_name):
        """Forgets an image and deletes its file. Returns the saved issue."""
        current = self.get(issue_id)
        if current is None:
            raise ValueError('There is no issue %s in this model.' % issue_id)
        keep = [i for i in current['images'] if i['file'] != file_name]
        gone = [i for i in current['images'] if i['file'] == file_name]
        if not gone:
            return current
        current['images'] = keep
        issue, _note = self.save(current, base_rev=current['rev'])
        for image in gone:
            path = self.image_path(current, image)
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass
        return issue


class _NoLock(object):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _pylist_keys(mapping):
    return [k for k in mapping]


# ---- one-call creation (namo.issues.create) ----------------------------------------------


def template_fields(template, now=None):
    """(fields, prefix, title_pattern) a template contributes (pure)."""
    from namo import issue_templates
    t = issue_templates.normalise(template)
    fields = {'type': t['type'], 'priority': t['priority'], 'trade': t['trade'],
              'assignee': t['assignee'], 'description': t['description'],
              'labels': list_copy(t['labels'])}
    if t['due_days'] is not None:
        from namo import dates
        when = now or issues._now()
        due = dates.add_days(when, int(t['due_days']))
        fields['due'] = due.strftime('%Y-%m-%d') if due is not None else ''
    return fields, t['prefix'], t['title_pattern']


def list_copy(values):
    return [v for v in values or []]


def create_issue(fields, doc=None, template=None, capture=False, image=True, title_values=None,
                 source=None):
    """namo.issues.create: template defaults under fields, optional capture of the
    current view, saved, snapshot attached. Returns the issue."""
    from namo import issue_templates
    s = for_doc(doc)
    s.require_saved()
    merged = {}
    prefix = issues.DEFAULT_PREFIX
    pattern = None
    if template is not None:
        resolved = issue_templates.resolve(template) if not isinstance(template, dict) else template
        if resolved is None:
            raise ValueError('There is no issue template called %s.' % template)
        merged, prefix, pattern = template_fields(resolved)
    for key in fields or {}:
        value = fields[key]
        if value not in (None, '') or key not in merged:
            merged[key] = value
    if source is not None:
        merged['source'] = source
    shot = None
    if capture:
        from namo import issueapi
        shot = issueapi.capture(s.doc, image=image)
        for key in ('camera', 'camera_units', 'elements', 'location'):
            if shot.get(key) is not None and not merged.get(key):
                merged[key] = shot[key]
    values = dict(title_values or {})
    if shot is not None:
        values.update(capture_title_values(shot))
    issue = s.create(merged, prefix=prefix, title_pattern=pattern, title_values=values)
    if shot is not None and shot.get('image'):
        try:
            issue = s.add_image(issue['id'], shot['image'], kind='snapshot', move=True)
        except Exception as error:
            session.log('warning', 'snapshot not attached to %s: %s' % (issue['id'], error))
    return issue


def capture_title_values(shot):
    """Title tokens from a capture: level, grid, element, model."""
    location = shot.get('location') or {}
    elements = shot.get('elements') or []
    first = elements[0] if elements else {}
    return {'level': location.get('level') or '', 'grid': location.get('grid') or '',
            'element': first.get('name') or '', 'model': first.get('model') or ''}
