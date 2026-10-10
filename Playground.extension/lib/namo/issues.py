# -*- coding: utf-8 -*-
"""Playground issues: the coordination register (model, rules and the public API).

PUBLIC API (for every tool that reads or writes issues)
-------------------------------------------------------
    from namo import issues

    rows = issues.list()                         # every issue of the active document
    open_rows = issues.filter(rows, status='open', trade='Mechanical')
    issue = issues.get('RFI-012')                # by id (or by guid); None when absent
    issue = issues.create({'title': 'Duct hits beam', 'priority': 'High'},
                          template='RFI', capture=True)   # camera + selection + snapshot
    issue = issues.update('RFI-012', {'status': 'Resolved', 'assignee': 'Jane'})
    issue = issues.add_comment('RFI-012', 'Moved 150 mm up')
    shot = issues.capture()                      # camera, elements, location, image path
    issues.go_to(issue)                          # restores the camera, selects elements
    paths = issues.image_paths(issue)            # snapshot/screenshot files on disk
    store = issues.store()                       # the namo.issuestore.IssueStore behind it

Every API function takes doc=None (the active document). Reads never raise (an empty
list when there is no saved document); writes raise IOError (toast it) and ValueError
for bad input (a sentence fit for a toast). Writes need a SAVED document, because the
register is kept per model file: issuestore.NotSaved (a ValueError) says so.
Storage follows namo.config 'data_mode': local files, a shared team folder (one file per
issue, last writer wins per issue, comments merged) or inside the model (namo.docdb).
See namo.issuestore for where files and images live.

THE ISSUE RECORD (a JSON-safe dict; unknown keys are kept)
----------------------------------------------------------
    id            'RFI-012': template prefix + zero-padded number (per prefix)
    number        12
    guid          lowercase uuid4 text (the BCF Topic Guid)
    title, type   text; type is the template name ('RFI', 'Clash', 'Issue')
    status        one of STATUSES: Open, In progress, Resolved, Closed, Void
    priority      one of PRIORITIES: Low, Normal, High, Critical
    trade, assignee, description   text ('' when unset)
    due           'YYYY-MM-DD' or ''
    created, modified, closed      'YYYY-MM-DDTHH:MM:SS' local time ('' when unset);
                  closed is stamped when the status enters Resolved/Closed/Void
    created_by, modified_by        user names (namo.config.user_name())
    rev           save counter (last-writer-wins detection in shared folders)
    location      {'point': [x, y, z], 'units': 'Feet', 'level': 'L2', 'grid': 'C-4'} or None
    camera        namo.camera dict (document units) or None; camera_units 'Feet'
    elements      [{'entry': {'m','i','p'}, 'name', 'model', 'category', 'element_id',
                    'unique_id', 'ifc_guid', 'ifc_guid_derived'}]
    images        [{'file', 'kind' ('snapshot'|'screenshot'|'bcf'|'photo'), 'caption',
                    'created', 'by'}]  (files live in the store's media folder)
    comments      [{'guid', 'author', 'date', 'text', 'status_change': {'from', 'to'} or None}]
    source        {'kind': 'manual'|'clash'|'bcf'|'stamp', 'ref': text, ...}
    labels        [text]
    doc           the model file name the issue was raised in

The pure half (everything above the "API facade" line) is unit tested on CPython and
IronPython 3.4; nothing imports Navisworks at module level.
"""

import copy
import datetime
import re
import uuid

# The facade below defines list() and filter(); keep the builtins under private names
# so nothing in this module calls the facade by accident.
_pylist = list
_pyfilter = filter

FORMAT = 1
STATUSES = ['Open', 'In progress', 'Resolved', 'Closed', 'Void']
OPEN_STATUSES = ('Open', 'In progress')           # needs someone to act
CLOSED_STATUSES = ('Resolved', 'Closed')          # fixed (Resolved awaits verification)
DONE_STATUSES = ('Resolved', 'Closed', 'Void')    # 'closed' is stamped on entering these
PRIORITIES = ['Low', 'Normal', 'High', 'Critical']
URGENCY = ['Critical', 'High', 'Normal', 'Low']   # most urgent first (sorting, charts)
DEFAULT_TYPE = 'Issue'
DEFAULT_PREFIX = 'ISS-'
ID_WIDTH = 3
SOURCE_KINDS = ('manual', 'clash', 'bcf', 'stamp')
IMAGE_KINDS = ('snapshot', 'screenshot', 'bcf', 'photo')
NO_TRADE = 'No trade'
NO_ASSIGNEE = 'Unassigned'

# Chip tones shared by the pane, the meeting window and the reports
# (namo.htmlreport / namo.xlsx tone names).
STATUS_TONES = {'Open': 'warn', 'In progress': 'info', 'Resolved': 'good',
                'Closed': 'neutral', 'Void': 'neutral'}
PRIORITY_TONES = {'Critical': 'bad', 'High': 'warn', 'Normal': 'neutral', 'Low': 'neutral'}

# Spellings other tools use (BCF TopicStatus / Priority are free text), lower case.
_STATUS_ALIASES = {
    'open': 'Open', 'new': 'Open', 'active': 'Open', 'reopened': 'Open', 're-opened': 'Open',
    'reopen': 'Open', 'assigned': 'Open', 'opened': 'Open', 'to do': 'Open', 'todo': 'Open',
    'in progress': 'In progress', 'inprogress': 'In progress', 'in_progress': 'In progress',
    'in-progress': 'In progress', 'progress': 'In progress', 'pending': 'In progress',
    'review': 'In progress', 'reviewed': 'In progress', 'in review': 'In progress',
    'ongoing': 'In progress', 'started': 'In progress',
    'resolved': 'Resolved', 'fixed': 'Resolved', 'done': 'Resolved', 'answered': 'Resolved',
    'closed': 'Closed', 'approved': 'Closed', 'complete': 'Closed', 'completed': 'Closed',
    'verified': 'Closed', 'accepted': 'Closed',
    'void': 'Void', 'cancelled': 'Void', 'canceled': 'Void', 'rejected': 'Void',
    'invalid': 'Void', 'not an issue': 'Void', 'duplicate': 'Void', 'withdrawn': 'Void',
}
_PRIORITY_ALIASES = {
    'low': 'Low', 'minor': 'Low', 'trivial': 'Low', 'lowest': 'Low', 'info': 'Low',
    'normal': 'Normal', 'medium': 'Normal', 'moderate': 'Normal', 'standard': 'Normal',
    'default': 'Normal', 'on hold': 'Normal',
    'high': 'High', 'major': 'High', 'important': 'High', 'higher': 'High',
    'critical': 'Critical', 'blocker': 'Critical', 'urgent': 'Critical', 'highest': 'Critical',
    'severe': 'Critical', 'showstopper': 'Critical',
}

_ID_RE = re.compile(r'^(.*?)(\d+)$')


# =====================================================================================
# Pure half
# =====================================================================================

# ---- small helpers ------------------------------------------------------------------


def _text(value):
    if value is None:
        return ''
    return (u'%s' % (value,)).strip()


def _now():
    return datetime.datetime.now().replace(microsecond=0)


def stamp(when=None):
    """'YYYY-MM-DDTHH:MM:SS' for a datetime (default now), local time."""
    when = when or _now()
    return '%04d-%02d-%02dT%02d:%02d:%02d' % (when.year, when.month, when.day, when.hour,
                                              when.minute, when.second)


def new_guid():
    """A lowercase uuid4 text (the form BCF requires)."""
    return str(uuid.uuid4()).lower()


def _parse(value):
    from namo import dates
    return dates.parse(value)


def _day(value):
    """A datetime.date from anything dates.parse reads, or None."""
    dt = _parse(value)
    return dt.date() if dt is not None else None


def _today(today=None):
    if today is None:
        return datetime.date.today()
    if isinstance(today, datetime.datetime):
        return today.date()
    if isinstance(today, datetime.date):
        return today
    parsed = _day(today)
    return parsed or datetime.date.today()


def due_text(value):
    """'YYYY-MM-DD' for a due date in any readable form, '' when blank or unreadable."""
    day = _day(value) if _text(value) else None
    return day.strftime('%Y-%m-%d') if day is not None else ''


def canonical_status(text, default='Open'):
    """One of STATUSES for any common spelling ('in-progress', 'Reopened', 'Done'...);
    default when unknown or blank."""
    key = re.sub(r'\s+', ' ', _text(text).lower())
    if not key:
        return default
    for status in STATUSES:
        if status.lower() == key:
            return status
    return _STATUS_ALIASES.get(key, default)


def canonical_priority(text, default='Normal'):
    """One of PRIORITIES for any common spelling ('Medium', 'Blocker'...); default when
    unknown or blank. Numbers 1..5 (Navisworks clash priority) map 1 Critical .. 5 Low."""
    key = _text(text).lower()
    if not key:
        return default
    for priority in PRIORITIES:
        if priority.lower() == key:
            return priority
    if key in _PRIORITY_ALIASES:
        return _PRIORITY_ALIASES[key]
    if re.match(r'^\d+$', key):
        number = int(key)
        return {1: 'Critical', 2: 'High', 3: 'Normal', 4: 'Low', 5: 'Low'}.get(number, default)
    return default


def is_open(issue):
    """True for Open and In progress (someone has to act)."""
    return issue.get('status') in OPEN_STATUSES


def is_closed(issue):
    """True for Resolved and Closed (fixed); Void is neither open nor closed."""
    return issue.get('status') in CLOSED_STATUSES


def split_id(issue_id):
    """('RFI-', 12) for 'RFI-012'; (text, None) when there is no trailing number."""
    text = _text(issue_id)
    match = _ID_RE.match(text)
    if not match:
        return text, None
    return match.group(1), int(match.group(2))


def format_id(prefix, number, width=ID_WIDTH):
    """'RFI-012' from ('RFI-', 12)."""
    return '%s%0*d' % (prefix or '', width, int(number))


def clean_prefix(prefix):
    """A safe id prefix: letters, digits, '-' and '_' kept, upper-cased; '' stays ''.
    A prefix ending in a letter or digit gets a '-' so 'RFI' + 12 reads 'RFI-012'."""
    text = re.sub(r'[^A-Za-z0-9_-]', '', _text(prefix)).upper()
    if text and text[-1].isalnum():
        text += '-'
    return text


def id_sort_key(issue_id):
    """Natural sort key for ids: prefix (case-insensitive) then the number."""
    prefix, number = split_id(issue_id)
    return (prefix.lower(), number if number is not None else -1, _text(issue_id).lower())


def labels_from_text(text):
    """['a', 'b'] from 'a, b; b' (commas or semicolons, duplicates and blanks dropped,
    first spelling kept)."""
    out = []
    seen = set()
    for part in re.split(r'[,;\n]', _text(text)):
        label = part.strip()
        if label and label.lower() not in seen:
            seen.add(label.lower())
            out.append(label)
    return out


def labels_text(labels):
    return ', '.join(_text(l) for l in (labels or []) if _text(l))


# ---- records --------------------------------------------------------------------------


DEFAULTS = {
    'id': '', 'number': None, 'guid': '', 'title': '', 'type': DEFAULT_TYPE, 'status': 'Open',
    'priority': 'Normal', 'trade': '', 'assignee': '', 'due': '', 'created': '',
    'created_by': '', 'modified': '', 'modified_by': '', 'closed': '', 'rev': 0,
    'description': '', 'location': None, 'camera': None, 'camera_units': '', 'elements': [],
    'images': [], 'comments': [], 'source': None, 'labels': [], 'doc': '', 'format': FORMAT,
}


def normalise(record):
    """A complete issue dict from any stored record (a copy): every DEFAULTS key present,
    status and priority canonical, lists as lists, number read from the id when missing,
    a guid when missing, comments with guids. Unknown keys are kept. Never raises on
    junk values (they become defaults)."""
    out = copy.deepcopy(DEFAULTS)
    if isinstance(record, dict):
        for key in record:
            out[key] = copy.deepcopy(record[key])
    out['id'] = _text(out.get('id'))
    if out.get('number') is None or not isinstance(out.get('number'), int):
        _prefix, number = split_id(out['id'])
        try:
            out['number'] = int(out['number']) if out.get('number') is not None else number
        except (TypeError, ValueError):
            out['number'] = number
    out['guid'] = _text(out.get('guid')).lower() or new_guid()
    for key in ('title', 'trade', 'assignee', 'created', 'created_by',
                'modified', 'modified_by', 'closed', 'camera_units', 'doc'):
        out[key] = _text(out.get(key))
    out['description'] = u'%s' % (out.get('description') or '')
    out['type'] = _text(out.get('type')) or DEFAULT_TYPE
    out['status'] = canonical_status(out.get('status'))
    out['priority'] = canonical_priority(out.get('priority'))
    out['due'] = due_text(out.get('due'))
    try:
        out['rev'] = int(out.get('rev') or 0)
    except (TypeError, ValueError):
        out['rev'] = 0
    if not isinstance(out.get('labels'), (_pylist, tuple)):
        out['labels'] = labels_from_text(out.get('labels'))
    for key in ('elements', 'images', 'comments', 'labels'):
        value = out.get(key)
        out[key] = [v for v in value] if isinstance(value, (_pylist, tuple)) else []
    out['labels'] = [_text(l) for l in out['labels'] if _text(l)]
    out['elements'] = [e for e in out['elements'] if isinstance(e, dict)]
    out['images'] = [i for i in out['images'] if isinstance(i, dict) and _text(i.get('file'))]
    comments = []
    for comment in out['comments']:
        if not isinstance(comment, dict):
            continue
        comment = dict(comment)
        comment['guid'] = _text(comment.get('guid')).lower() or new_guid()
        comment['author'] = _text(comment.get('author'))
        comment['date'] = _text(comment.get('date'))
        comment['text'] = u'%s' % (comment.get('text') or '')
        change = comment.get('status_change')
        comment['status_change'] = change if isinstance(change, dict) else None
        comments.append(comment)
    out['comments'] = comments
    location = out.get('location')
    if not isinstance(location, dict) or not _point(location.get('point')):
        out['location'] = None
    else:
        location = dict(location)
        location['point'] = _point(location.get('point'))
        for key in ('units', 'level', 'grid'):
            location[key] = _text(location.get(key))
        out['location'] = location
    if not isinstance(out.get('camera'), dict):
        out['camera'] = None
    source = out.get('source')
    if not isinstance(source, dict):
        source = {'kind': 'manual', 'ref': ''}
    source = dict(source)
    source['kind'] = _text(source.get('kind')).lower() or 'manual'
    source['ref'] = _text(source.get('ref'))
    out['source'] = source
    out['format'] = FORMAT
    return out


def _point(value):
    """[x, y, z] floats or None."""
    try:
        if value is None or len(value) != 3:
            return None
        return [float(value[0]), float(value[1]), float(value[2])]
    except (TypeError, ValueError):
        return None


def new_issue(fields=None, user='', now=None, guid=None):
    """A fresh issue dict (no id yet: the store assigns it) from fields, stamped created
    and modified by user at now."""
    fields = dict(fields or {})
    due = _text(fields.get('due'))
    if due and not due_text(due):
        raise ValueError('Due date %s is not a date; use YYYY-MM-DD.' % due)
    when = stamp(now)
    record = normalise(fields)
    record['guid'] = _text(guid or fields.get('guid')).lower() or new_guid()
    record['created'] = _text(fields.get('created')) or when
    record['created_by'] = _text(fields.get('created_by')) or _text(user)
    record['modified'] = _text(fields.get('modified')) or record['created']
    record['modified_by'] = _text(fields.get('modified_by')) or record['created_by']
    if record['status'] in DONE_STATUSES and not record['closed']:
        record['closed'] = when
    record['rev'] = 0
    return record


def validate(issue):
    """[sentence] of problems that stop a save; [] when fine."""
    problems = []
    if not _text(issue.get('title')):
        problems.append('Give the issue a title.')
    if _text(issue.get('status')) not in STATUSES:
        problems.append('Status must be one of %s.' % ', '.join(STATUSES))
    if _text(issue.get('priority')) not in PRIORITIES:
        problems.append('Priority must be one of %s.' % ', '.join(PRIORITIES))
    due = _text(issue.get('due'))
    if due and not due_text(due):
        problems.append('Due date %s is not a date; use YYYY-MM-DD.' % due)
    return problems


def new_comment(text, author='', now=None, status_change=None, guid=None):
    """A comment dict. status_change: (from, to) or {'from', 'to'} or None."""
    change = None
    if status_change:
        if isinstance(status_change, dict):
            change = {'from': _text(status_change.get('from')), 'to': _text(status_change.get('to'))}
        else:
            change = {'from': _text(status_change[0]), 'to': _text(status_change[1])}
    return {'guid': _text(guid).lower() or new_guid(), 'author': _text(author),
            'date': stamp(now), 'text': u'%s' % (text or ''), 'status_change': change}


def comment_text(comment):
    """What a comment says, status change included: 'Status: Open > Resolved. Moved up.'"""
    text = _text(comment.get('text'))
    change = comment.get('status_change')
    if change and (_text(change.get('from')) or _text(change.get('to'))):
        head = 'Status: %s > %s.' % (_text(change.get('from')) or 'none', _text(change.get('to')))
        return head + (' ' + text if text else '')
    return text


EDITABLE = ('title', 'type', 'status', 'priority', 'trade', 'assignee', 'due', 'description',
            'labels', 'location', 'camera', 'camera_units', 'elements', 'images', 'source')


def apply_changes(issue, changes, user='', now=None, note=None):
    """A new issue dict with changes applied ({field: value}, EDITABLE fields only;
    others raise ValueError). A status change appends a comment carrying
    status_change (with note as its text) and stamps or clears 'closed'. Returns
    (issue, changed_fields) where changed_fields lists the fields that really changed
    (sorted); nothing changed means the issue is returned untouched (no new stamp)."""
    out = normalise(issue)
    unknown = sorted(k for k in changes if k not in EDITABLE)
    if unknown:
        raise ValueError('These fields cannot be edited: %s.' % ', '.join(unknown))
    changed = []
    old_status = out['status']
    for key in sorted(changes):
        value = changes[key]
        if key == 'status':
            value = canonical_status(value, default=None)
            if value is None:
                raise ValueError('Status must be one of %s.' % ', '.join(STATUSES))
        elif key == 'priority':
            value = canonical_priority(value, default=None)
            if value is None:
                raise ValueError('Priority must be one of %s.' % ', '.join(PRIORITIES))
        elif key == 'due':
            text = _text(value)
            value = due_text(text)
            if text and not value:
                raise ValueError('Due date %s is not a date; use YYYY-MM-DD.' % text)
        elif key == 'labels':
            value = labels_from_text(value) if not isinstance(value, (_pylist, tuple)) \
                else [_text(v) for v in value if _text(v)]
        elif key in ('title', 'type', 'trade', 'assignee', 'camera_units'):
            value = _text(value)
        elif key == 'description':
            value = u'%s' % (value or '')
        if key == 'title' and not value:
            raise ValueError('Give the issue a title.')
        if out.get(key) != value:
            out[key] = copy.deepcopy(value)
            changed.append(key)
    if not changed and not _text(note):
        return out, []
    when = stamp(now)
    if 'status' in changed:
        new_status = out['status']
        out['comments'].append(new_comment(note or '', user, now,
                                           status_change=(old_status, new_status)))
        if new_status in DONE_STATUSES and old_status not in DONE_STATUSES:
            out['closed'] = when
        elif new_status not in DONE_STATUSES:
            out['closed'] = ''
    elif _text(note):
        out['comments'].append(new_comment(note, user, now))
        changed.append('comments')
    out['modified'] = when
    out['modified_by'] = _text(user)
    return out, sorted(set(changed))


def add_comment_to(issue, text, user='', now=None, status_change=None):
    """A new issue dict with one comment appended (and modified stamped). ValueError for
    an empty comment without a status change."""
    if not _text(text) and not status_change:
        raise ValueError('Write a comment first.')
    out = normalise(issue)
    out['comments'].append(new_comment(text, user, now, status_change))
    out['modified'] = stamp(now)
    out['modified_by'] = _text(user)
    return out


def merge_for_save(mine, theirs):
    """Last writer wins per issue, nothing appended is lost: the result is `mine` (the
    fields being saved) with every comment and image from `theirs` that `mine` lacks
    added back (comments by guid, images by file), comments kept in date order. Used
    when the stored issue changed since the editor loaded it."""
    out = normalise(mine)
    other = normalise(theirs)
    have = set(c['guid'] for c in out['comments'])
    for comment in other['comments']:
        if comment['guid'] not in have:
            out['comments'].append(comment)
            have.add(comment['guid'])
    out['comments'] = sorted(out['comments'], key=lambda c: (c.get('date') or '', c['guid']))
    files = set(i['file'].lower() for i in out['images'])
    for image in other['images']:
        if image['file'].lower() not in files:
            out['images'].append(image)
            files.add(image['file'].lower())
    out['rev'] = max(out.get('rev') or 0, other.get('rev') or 0)
    return out


def conflict_note(theirs):
    """'Also changed by Jane at 14:02; your changes were kept and comments merged.'"""
    who = _text(theirs.get('modified_by')) or 'someone else'
    when = _parse(theirs.get('modified'))
    at = when.strftime('%H:%M') if when is not None else 'an unknown time'
    return ('%s was also changed by %s at %s; your changes were kept and comments merged.'
            % (_text(theirs.get('id')) or 'The issue', who, at))


# ---- dates: aging and due -------------------------------------------------------------


def age_days(issue, today=None):
    """Whole days since the issue was created (0 today), or None."""
    created = _day(issue.get('created'))
    if created is None:
        return None
    return (_today(today) - created).days


def days_overdue(issue, today=None):
    """Days past the due date for an OPEN issue (1 = due yesterday), else 0."""
    if not is_open(issue):
        return 0
    due = _day(issue.get('due')) if _text(issue.get('due')) else None
    if due is None:
        return 0
    return max(0, (_today(today) - due).days)


def is_overdue(issue, today=None):
    return days_overdue(issue, today) > 0


def due_state(issue, today=None, soon_days=7):
    """'overdue' | 'soon' (open, due within soon_days, today included) | 'later' |
    'none' (no due date) | 'done' (not open)."""
    if not is_open(issue):
        return 'done'
    if not _text(issue.get('due')):
        return 'none'
    due = _day(issue.get('due'))
    if due is None:
        return 'none'
    delta = (due - _today(today)).days
    if delta < 0:
        return 'overdue'
    if delta < soon_days:
        return 'soon'
    return 'later'


def due_note(issue, today=None):
    """Short words for the due column: '3 days late', 'Due today', 'Due in 2 days', ''."""
    state = due_state(issue, today)
    if state == 'overdue':
        n = days_overdue(issue, today)
        return '%d day%s late' % (n, '' if n == 1 else 's')
    if state == 'soon':
        delta = (_day(issue['due']) - _today(today)).days
        if delta == 0:
            return 'Due today'
        return 'Due in %d day%s' % (delta, '' if delta == 1 else 's')
    return ''


def closed_within(issue, days, today=None):
    """True when the issue entered Resolved/Closed within the last `days` days."""
    if not is_closed(issue):
        return False
    closed = _day(issue.get('closed')) or _day(issue.get('modified'))
    if closed is None:
        return False
    return 0 <= (_today(today) - closed).days < days


# ---- text, filters and sorting ---------------------------------------------------------


def display_title(issue):
    """'RFI-012  Duct hits beam'."""
    return ('%s  %s' % (_text(issue.get('id')), _text(issue.get('title')))).strip()


def pin_label(issue, limit=40):
    """The overlay label: '#12 RFI: Duct hits beam' (cut with ...)."""
    number = issue.get('number')
    head = '#%s' % number if number is not None else _text(issue.get('id'))
    kind = _text(issue.get('type'))
    text = '%s %s: %s' % (head, kind, _text(issue.get('title'))) if kind \
        else '%s %s' % (head, _text(issue.get('title')))
    if len(text) > limit:
        text = text[:limit - 3].rstrip() + '...'
    return text


def search_text(issue):
    """Everything a filter box matches against, lower case."""
    parts = [issue.get('id'), issue.get('title'), issue.get('type'), issue.get('status'),
             issue.get('priority'), issue.get('trade'), issue.get('assignee'),
             issue.get('description'), labels_text(issue.get('labels'))]
    location = issue.get('location') or {}
    parts += [location.get('level'), location.get('grid')]
    for comment in issue.get('comments') or []:
        parts.append(comment.get('text'))
        parts.append(comment.get('author'))
    for element in issue.get('elements') or []:
        parts.append(element.get('name'))
        parts.append(element.get('element_id'))
    return u' '.join(_text(p) for p in parts if _text(p)).lower()


def matches_text(issue, query):
    """True when every word of query appears somewhere in the issue (case-insensitive)."""
    words = [w for w in _text(query).lower().split() if w]
    if not words:
        return True
    hay = search_text(issue)
    return all(w in hay for w in words)


def _as_set(value, canon=None):
    """None (no filter) or a lower-case set from a value or list. 'all' / '' / [] = None."""
    if value is None:
        return None
    values = value if isinstance(value, (_pylist, tuple, set)) else [value]
    out = set()
    for v in values:
        text = _text(v)
        if not text or text.lower() == 'all':
            continue
        out.add((canon(text) if canon else text).lower())
    return out or None


def _status_set(status):
    if status is None:
        return None
    values = status if isinstance(status, (_pylist, tuple, set)) else [status]
    out = set()
    for v in values:
        key = _text(v).lower()
        if not key or key == 'all':
            continue
        if _text(v) in STATUSES:
            # An exact status ('Open', 'Closed') means itself only; the lower-case words
            # 'open' / 'closed' below are the groups (the pane offers both kinds).
            out.add(key)
        elif key == 'open':
            out.update(s.lower() for s in OPEN_STATUSES)
        elif key in ('closed', 'done'):
            out.update(s.lower() for s in CLOSED_STATUSES)
        else:
            out.add(canonical_status(key, default=_text(v)).lower())
    return out or None


def filter_issues(rows, status=None, trade=None, assignee=None, priority=None, type=None,
                  text='', due=None, labels=None, today=None, source=None):
    """The issues matching every given criterion, in input order.

    status: a status, a list, 'open' (Open + In progress) or 'closed' (Resolved +
    Closed); trade/assignee/priority/type/source(kind): a value or list ('No trade' /
    'Unassigned' match blanks); text: every word must appear (id, title, comments...);
    due: 'overdue' | 'soon' (within 7 days) | 'none' (no due date) | 'set'; labels: any
    of them. None, '' and 'all' mean no filter."""
    statuses = _status_set(status)
    trades = _as_set(trade)
    assignees = _as_set(assignee)
    priorities = _as_set(priority, canonical_priority)
    types = _as_set(type)
    label_set = _as_set(labels)
    sources = _as_set(source)
    due_key = _text(due).lower() or None
    out = []
    for issue in rows:
        if statuses is not None and _text(issue.get('status')).lower() not in statuses:
            continue
        if trades is not None and (_text(issue.get('trade')) or NO_TRADE).lower() not in trades:
            continue
        if assignees is not None and \
                (_text(issue.get('assignee')) or NO_ASSIGNEE).lower() not in assignees:
            continue
        if priorities is not None and _text(issue.get('priority')).lower() not in priorities:
            continue
        if types is not None and _text(issue.get('type')).lower() not in types:
            continue
        if sources is not None and \
                _text((issue.get('source') or {}).get('kind')).lower() not in sources:
            continue
        if label_set is not None and not \
                (set(_text(l).lower() for l in issue.get('labels') or []) & label_set):
            continue
        if due_key and due_key != 'all':
            state = due_state(issue, today)
            if due_key == 'overdue' and state != 'overdue':
                continue
            if due_key == 'soon' and state not in ('overdue', 'soon'):
                continue
            if due_key == 'none' and _text(issue.get('due')):
                continue
            if due_key == 'set' and not _text(issue.get('due')):
                continue
        if text and not matches_text(issue, text):
            continue
        out.append(issue)
    return out


def _rank(value, order):
    try:
        return order.index(value)
    except ValueError:
        return len(order)


SORT_KEYS = ('default', 'id', 'title', 'status', 'priority', 'trade', 'assignee', 'due',
             'created', 'modified')


def sort_key(issue, key='default'):
    """A sort key: 'default' is open (Open and In progress together) first, then most
    urgent, then earliest due (no due date last), then id; 'priority' sorts most urgent
    first; 'status' in STATUSES order; 'due' earliest first with no due date last; text
    keys naturally."""
    from namo import naming
    ident = id_sort_key(issue.get('id'))
    due = _text(issue.get('due')) or '9999-12-31'
    if key == 'id':
        return ident
    if key == 'title':
        return (naming.natural_key(_text(issue.get('title'))), ident)
    if key == 'status':
        return (_rank(issue.get('status'), STATUSES), ident)
    if key == 'priority':
        return (_rank(issue.get('priority'), URGENCY), ident)
    if key in ('trade', 'assignee'):
        return (naming.natural_key(_text(issue.get(key)) or '~'), ident)
    if key == 'due':
        return (due, ident)
    if key in ('created', 'modified'):
        return (_text(issue.get(key)), ident)
    open_now = is_open(issue)
    return (0 if open_now else 1, 0 if open_now else _rank(issue.get('status'), STATUSES),
            _rank(issue.get('priority'), URGENCY), due, ident)


def sort_issues(rows, key='default', descending=False):
    """A new list sorted by sort_key (stable)."""
    return sorted(rows, key=lambda issue: sort_key(issue, key), reverse=bool(descending))


def distinct(rows, field, blank=None):
    """Distinct non-blank values of a field, natural order ('blank' added last when some
    rows are blank and blank is given)."""
    from namo import naming
    values = {}
    has_blank = False
    for issue in rows:
        text = _text(issue.get(field))
        if not text:
            has_blank = True
            continue
        values.setdefault(text.lower(), text)
    out = sorted(values.values(), key=naming.natural_key)
    if has_blank and blank:
        out.append(blank)
    return out


# ---- statistics (Coordination Report, KPI Export, pane status line) ------------------


def counts(rows, today=None):
    """{'total', 'open', 'overdue', 'soon', 'resolved', 'closed', 'void', 'by_status'}."""
    out = {'total': len(rows), 'open': 0, 'overdue': 0, 'soon': 0, 'resolved': 0,
           'closed': 0, 'void': 0, 'by_status': dict((s, 0) for s in STATUSES)}
    for issue in rows:
        status = issue.get('status')
        if status in out['by_status']:
            out['by_status'][status] += 1
        if is_open(issue):
            out['open'] += 1
            state = due_state(issue, today)
            if state == 'overdue':
                out['overdue'] += 1
            elif state == 'soon':
                out['soon'] += 1
        elif status == 'Resolved':
            out['resolved'] += 1
        elif status == 'Closed':
            out['closed'] += 1
        elif status == 'Void':
            out['void'] += 1
    return out


def status_line(rows, shown=None, today=None):
    """'12 open, 3 overdue, 40 in total' (+ ', 9 shown' when filtered)."""
    c = counts(rows, today)
    parts = ['{:,} open'.format(c['open'])]
    if c['overdue']:
        parts.append('{:,} overdue'.format(c['overdue']))
    parts.append('{:,} in total'.format(c['total']))
    if shown is not None and shown != c['total']:
        parts.append('{:,} shown'.format(shown))
    return ', '.join(parts)


def tally(rows, field, blank, order=None):
    """[(value, count)]: in `order` when given (zero counts kept), else most common
    first then natural order; blanks counted as `blank`."""
    from namo import naming
    found = {}
    for issue in rows:
        value = _text(issue.get(field)) or blank
        found[value] = found.get(value, 0) + 1
    if order is not None:
        out = [(value, found.get(value, 0)) for value in order]
        out += sorted([(v, n) for v, n in found.items() if v not in order],
                      key=lambda p: (-p[1], naming.natural_key(p[0])))
        return out
    return sorted(found.items(), key=lambda p: (-p[1], naming.natural_key(p[0])))


def summary(rows, today=None, closed_days=7, recent_days=14, buckets=(7, 14, 30)):
    """Everything the Coordination Report shows, computed once (pure):

    {'today', 'counts', 'kpis': {'open', 'overdue', 'due_week', 'closed_recent'},
     'open_by_trade': [(trade, n)], 'open_by_priority': [(priority, n)] (Critical first),
     'open_by_assignee': [(name, n)], 'aging': [(bucket label, n)] (open issues by age),
     'overdue': [issues, most days late first], 'due_week': [issues, soonest first],
     'recently_closed': [issues closed within recent_days, latest first],
     'by_trade': [(trade, [open issues, default order])]}."""
    from namo import dates
    day = _today(today)
    open_rows = [i for i in rows if is_open(i)]
    overdue = sorted([i for i in open_rows if due_state(i, day) == 'overdue'],
                     key=lambda i: (-days_overdue(i, day), id_sort_key(i.get('id'))))
    due_week = sorted([i for i in open_rows if due_state(i, day) == 'soon'],
                      key=lambda i: (i.get('due') or '', id_sort_key(i.get('id'))))
    closed_recent = [i for i in rows if closed_within(i, closed_days, day)]
    recent = sorted([i for i in rows if closed_within(i, recent_days, day)],
                    key=lambda i: (i.get('closed') or i.get('modified') or ''), reverse=True)
    labels = dates.bucket_labels(buckets)
    aging = dict((label, 0) for label in labels)
    for issue in open_rows:
        label = dates.age_bucket(age_days(issue, day), buckets)
        if label in aging:
            aging[label] += 1
    by_trade = []
    for trade, _n in tally(open_rows, 'trade', NO_TRADE):
        members = [i for i in open_rows if (_text(i.get('trade')) or NO_TRADE) == trade]
        by_trade.append((trade, sort_issues(members)))
    return {
        'today': day.strftime('%Y-%m-%d'),
        'counts': counts(rows, day),
        'kpis': {'open': len(open_rows), 'overdue': len(overdue), 'due_week': len(due_week),
                 'closed_recent': len(closed_recent)},
        'open_by_trade': tally(open_rows, 'trade', NO_TRADE),
        'open_by_priority': tally(open_rows, 'priority', 'Normal', order=URGENCY),
        'open_by_assignee': tally(open_rows, 'assignee', NO_ASSIGNEE),
        'aging': [(label, aging[label]) for label in labels],
        'overdue': overdue,
        'due_week': due_week,
        'recently_closed': recent,
        'by_trade': by_trade,
    }


# ---- locations and pins ------------------------------------------------------------------


def point_in(issue, doc_units):
    """The issue's location point converted to doc_units, or None."""
    location = issue.get('location')
    if not location or not location.get('point'):
        return None
    point = location['point']
    stored = _text(location.get('units'))
    if not stored or not doc_units or stored == doc_units:
        return (float(point[0]), float(point[1]), float(point[2]))
    from namo import units
    try:
        k = units.from_meters(units.to_meters(1.0, stored), doc_units)
    except ValueError:
        return (float(point[0]), float(point[1]), float(point[2]))
    return (point[0] * k, point[1] * k, point[2] * k)


def camera_in(issue, doc_units):
    """The issue's camera dict converted to doc_units (position and focal distance; an
    orthographic height too), or None."""
    cam = issue.get('camera')
    if not cam:
        return None
    stored = _text(issue.get('camera_units'))
    out = copy.deepcopy(cam)
    if not stored or not doc_units or stored == doc_units:
        return out
    from namo import units
    try:
        k = units.from_meters(units.to_meters(1.0, stored), doc_units)
    except ValueError:
        return out
    out['position'] = [float(v) * k for v in cam['position']]
    if out.get('focal_distance'):
        out['focal_distance'] = float(out['focal_distance']) * k
    if str(out.get('projection', '')).startswith('ortho') and out.get('height_field'):
        out['height_field'] = float(out['height_field']) * k
    return out


PIN_HEIGHT_M = 1.2


def pin_height(unit_to_m):
    """The pin's height in MODEL UNITS: a real 1.2 m (the head ends at about 1.7 m,
    eye level) whatever the model's units, extents or distance from the origin. The
    glyph is the one Photo Pins draws (namo.pins), so the two kinds of pin read as one
    family. Never sized from the
    model box: one stray item far away would blow every pin up."""
    try:
        k = float(unit_to_m)
    except (TypeError, ValueError):
        k = 1.0
    return PIN_HEIGHT_M / k if k > 0 else PIN_HEIGHT_M


PIN_HEAD_ABOVE = 1.4        # the marker is sized from 1.4 x the pin height


def pin_segments(point, height):
    """Overlay segments for one issue pin: the shared Playground pin (namo.pins: an
    octahedron outline centred on the point that reads from any side and in plan),
    the same glyph Photo Pins draws. `height` is pin_height(); the marker is sized
    from 1.4 times that. Model units."""
    from namo import pins
    return pins.segments(point, (abs(float(height)) or 1.0) * PIN_HEAD_ABOVE)


def pin_label_point(point, height):
    """Where the pin's label sits: on top of the marker."""
    from namo import pins
    return pins.top(point, (abs(float(height)) or 1.0) * PIN_HEAD_ABOVE)


def snapshot_size(view_width, view_height, long_side=1280):
    """(w, h) for a snapshot with the view's aspect ratio, the long side long_side
    pixels, each side at least 64 (BCF readers expect under 1,500 px)."""
    try:
        w, h = float(view_width), float(view_height)
    except (TypeError, ValueError):
        w, h = 16.0, 9.0
    if w <= 0 or h <= 0:
        w, h = 16.0, 9.0
    if w >= h:
        return int(long_side), max(64, int(round(long_side * h / w)))
    return max(64, int(round(long_side * w / h))), int(long_side)


# ---- BCF mapping (pure; namo.bcf writes and reads the files) ------------------------------

BCF_STATUS = {'Open': 'Open', 'In progress': 'In Progress', 'Resolved': 'Resolved',
              'Closed': 'Closed', 'Void': 'Void'}
REVIT_SYSTEM = 'Autodesk Revit'


def bcf_status(status):
    """The TopicStatus text written for an issue status."""
    return BCF_STATUS.get(canonical_status(status), 'Open')


def components_of(issue):
    """BCF components for the issue's elements that carry a valid IFC GUID:
    [{'ifc_guid', 'authoring_tool_id', 'originating_system'}], deduped, input order;
    plus how many elements had none. Returns (components, skipped)."""
    from namo import ifcguid
    out = []
    seen = set()
    skipped = 0
    for element in issue.get('elements') or []:
        guid = _text(element.get('ifc_guid'))
        if not guid or not ifcguid.is_valid(guid):
            skipped += 1
            continue
        if guid in seen:
            continue
        seen.add(guid)
        element_id = _text(element.get('element_id'))
        out.append({'ifc_guid': guid, 'authoring_tool_id': element_id,
                    'originating_system': REVIT_SYSTEM if element_id else ''})
    return out, skipped


def _bcf_comments(issue):
    out = []
    for comment in issue.get('comments') or []:
        text = comment_text(comment)
        if not text:
            continue
        out.append({'guid': comment.get('guid') or new_guid(), 'date': comment.get('date') or '',
                    'author': comment.get('author') or '', 'comment': text,
                    'viewpoint_guid': comment.get('viewpoint_guid') or ''})
    return out


def to_topic(issue, unit_to_m=None, snapshot_name=None, viewpoint_guid=None, trades=None):
    """A namo.bcf topic dict for an issue.

    unit_to_m: metres per unit of the issue's camera (None: no viewpoint camera).
    snapshot_name: the snapshot file name in the topic folder (None: no snapshot).
    The trade is written as a label (BCF has no trade field) unless it is already one.
    One viewpoint when the issue has a camera, components or a snapshot."""
    from namo import camera as _camera
    issue = normalise(issue)
    labels = _pylist(issue['labels'])
    if issue['trade'] and issue['trade'].lower() not in [l.lower() for l in labels]:
        labels.append(issue['trade'])
    topic = {
        'guid': issue['guid'], 'type': issue['type'], 'status': bcf_status(issue['status']),
        'title': issue['title'] or issue['id'], 'priority': issue['priority'],
        'index': issue.get('number'), 'labels': labels,
        'creation_date': issue['created'], 'creation_author': issue['created_by'],
        'modified_date': issue['modified'], 'modified_author': issue['modified_by'],
        'due_date': issue['due'], 'assigned_to': issue['assignee'],
        'description': issue['description'], 'reference_links': [],
        'comments': _bcf_comments(issue), 'viewpoints': [], 'document_references': [],
        'server_id': issue['id'],
    }
    components, _skipped = components_of(issue)
    cam = issue.get('camera')
    bcf_cam = None
    if cam and unit_to_m:
        try:
            bcf_cam = _camera.to_bcf(cam, unit_to_m)
        except Exception:
            bcf_cam = None
    if bcf_cam is not None or components or snapshot_name:
        guid = (viewpoint_guid or '').lower() or new_guid()
        topic['viewpoints'].append({
            'guid': guid, 'snapshot': snapshot_name or '', 'index': 0,
            'visinfo': {'guid': guid, 'camera': bcf_cam, 'selection': components,
                        'visibility': {'default': True, 'exceptions': []},
                        'coloring': [], 'clipping_planes': [], 'lines': []}})
    return topic


def _comment_from_bcf(comment):
    return {'guid': _text(comment.get('guid')).lower() or new_guid(),
            'author': _text(comment.get('author')),
            'date': _bcf_local(comment.get('date')) or stamp(),
            'text': u'%s' % (comment.get('comment') or ''), 'status_change': None,
            'viewpoint_guid': _text(comment.get('viewpoint_guid')).lower()}


def _bcf_local(value):
    """BCF dateTime text (any zone) as our local 'YYYY-MM-DDTHH:MM:SS', '' when blank."""
    dt = _parse(value) if _text(value) else None
    return stamp(dt) if dt is not None else ''


def from_topic(topic, existing=None, trades=None, user='', now=None):
    """What a BCF topic means for the register (pure):

    {'action': 'create' | 'update' | 'keep', 'fields': {...}, 'new_comments': [...],
     'camera': namo.camera BCF dict of the first viewpoint or None,
     'components': [{'ifc_guid', 'authoring_tool_id', 'originating_system'}]}

    existing: the issue with the same guid, or None. Fields are taken from the topic
    when it is new, or when the topic was modified after the issue's last change
    ('update'); a topic no newer than the local issue only adds its new comments
    ('keep').
    trades: the configured trade names; a label equal to one (any case) becomes the
    trade and is not kept as a label."""
    trades_lower = dict((t.lower(), t) for t in (trades or []))
    labels = []
    trade = ''
    for label in topic.get('labels') or []:
        text = _text(label)
        if not text:
            continue
        if not trade and text.lower() in trades_lower:
            trade = trades_lower[text.lower()]
            continue
        labels.append(text)
    fields = {
        'title': _text(topic.get('title')) or 'Untitled topic',
        'type': _text(topic.get('type')) or DEFAULT_TYPE,
        'status': canonical_status(topic.get('status')),
        'priority': canonical_priority(topic.get('priority')),
        'assignee': _text(topic.get('assigned_to')),
        'due': due_text(topic.get('due_date')),
        'description': u'%s' % (topic.get('description') or ''),
        'labels': labels,
    }
    if trade:
        fields['trade'] = trade
    modified = _bcf_local(topic.get('modified_date')) or _bcf_local(topic.get('creation_date'))
    comments = [_comment_from_bcf(c) for c in topic.get('comments') or []]
    viewpoints = topic.get('viewpoints') or []
    first = viewpoints[0] if viewpoints else None
    visinfo = (first or {}).get('visinfo') or {}
    out = {'fields': fields, 'camera': visinfo.get('camera'),
           'components': _pylist(visinfo.get('selection') or []), 'modified': modified}
    if existing is None:
        fields['created'] = _bcf_local(topic.get('creation_date')) or stamp(now)
        fields['created_by'] = _text(topic.get('creation_author')) or _text(user)
        out['action'] = 'create'
        out['new_comments'] = comments
        return out
    have = set(_text(c.get('guid')).lower() for c in existing.get('comments') or [])
    out['new_comments'] = [c for c in comments if c['guid'] not in have]
    local = _text(existing.get('modified'))
    out['action'] = 'update' if (not local or (modified and modified > local)) else 'keep'
    return out


# =====================================================================================
# API facade (lazy imports: issuestore, issueapi)
# =====================================================================================


def store(doc=None):
    """The IssueStore of a document (default: the active one). See namo.issuestore."""
    from namo import issuestore
    return issuestore.for_doc(doc)


def list(doc=None):  # noqa: A001 (contract name)
    """Every issue of the document, natural id order. [] when there is no saved document
    or nothing can be read. Never raises."""
    try:
        return store(doc).list()
    except Exception:
        return []


def filter(rows, **criteria):  # noqa: A001 (contract name)
    """filter_issues(rows, **criteria): see there."""
    return filter_issues(rows, **criteria)


def get(issue_id, doc=None):
    """The issue with this id ('RFI-012', any case) or guid, or None. Never raises."""
    try:
        return store(doc).find(issue_id)
    except Exception:
        return None


def create(fields, doc=None, template=None, capture=False, image=True):
    """Creates and saves an issue; returns it (with its new id).

    fields: any issue fields (title required unless the template's title pattern gives
    one). template: an issue template name or dict (namo.issue_templates) supplying
    type, prefix, title pattern, priority, trade, assignee, due days, description and
    labels for anything fields leave out. capture=True records the current camera,
    the selected elements, their location and (image=True) a snapshot. Raises
    issuestore.NotSaved for an unsaved document, ValueError for bad fields, IOError
    when it cannot be written."""
    from namo import issuestore
    return issuestore.create_issue(fields, doc=doc, template=template, capture=capture,
                                   image=image)


def update(issue_id, changes, doc=None, note=None):
    """Applies changes ({field: value}, see EDITABLE) and saves; returns the issue. A
    status change records a comment (note as its text). ValueError for an unknown id
    or bad values."""
    s = store(doc)
    issue, _note = s.update(issue_id, changes, note=note)
    return issue


def add_comment(issue_id, text, doc=None, status_change=None):
    """Adds a comment and saves; returns the issue."""
    return store(doc).add_comment(issue_id, text, status_change=status_change)


def capture(doc=None, image=True):
    """The current view as issue material: {'camera', 'camera_units', 'elements',
    'location', 'image' (a temp snapshot path or None)}. Navisworks only."""
    from namo import issueapi
    return issueapi.capture(doc, image=image)


def go_to(issue, doc=None, select=True):
    """Restores the issue's camera and selects its elements. Returns
    {'moved': bool, 'selected': n, 'missing': n}. Navisworks only."""
    from namo import issueapi
    if not isinstance(issue, dict):
        wanted = issue
        issue = get(wanted, doc)
        if issue is None:
            raise ValueError('There is no issue %s in this model.' % wanted)
    return issueapi.go_to(issue, doc, select=select)


def image_paths(issue, doc=None):
    """Full paths of the issue's image files that exist on disk, in record order."""
    import os
    s = store(doc)
    out = []
    for image in issue.get('images') or []:
        path = s.image_path(issue, image)
        if path and os.path.exists(path):
            out.append(path)
    return out
