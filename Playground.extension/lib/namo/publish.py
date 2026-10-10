# -*- coding: utf-8 -*-
"""NWD Publisher: versioned NWD files with publish properties, older versions archived.

Names come from a template (namo.naming) such as
'{project}_{file}_{date:%Y%m%d}_v{version:00}.nwd'. The version is found by scanning
the target folder: every existing file that fits the template (with ANY date, so the
count carries on from yesterday's v03 to today's v04) gives its number, and the next
publish takes the highest plus one. Older versions can be moved into an Archive
subfolder after a successful publish. Each publish is logged per document in
namo.store ('nwd-publish-history').

Three ways to write the file:
  * 'publish': Document.PublishFile(path, NwdExportOptions, PublishProperties), with
    title, author, comments, copyright, expiry... (pynavis.export.publish_nwd has no
    title or author, so this module sets PublishProperties itself);
  * 'export': Document.ExportToNwd(path, NwdExportOptions), a plain copy;
  * 'save': pynavis.export.save_nwd(path): Save As, so the OPEN document becomes the
    NWD afterwards (the form says so).

Pure half first (unit tested), API half after (lazy imports).
"""

import datetime
import os
import re

from namo import naming

TEMPLATES_TOOL = 'nwd_publisher'
DEFAULT_TEMPLATE = '{project}_{file}_{date:%Y%m%d}_v{version:00}.nwd'
ARCHIVE_FOLDER = 'Archive'
HISTORY_STORE = 'nwd-publish-history'
METHODS = ('publish', 'export', 'save')
METHOD_LABELS = [('Publish (with the properties below)', 'publish'),
                 ('Export a copy (no publish properties)', 'export'),
                 ('Save as NWD (the open document becomes the NWD)', 'save')]
DATE_TOKENS = ('date', 'time', 'datetime', 'year', 'month', 'day')
TOKEN_HINT = ('Tokens: {project} {project_number} {company} {file} {title} {user} '
              '{date:%Y%m%d} {time} {version:00}')

DEFAULTS = {
    'folder': '',
    'subfolder': 'Published',
    'template': DEFAULT_TEMPLATE,
    'method': 'publish',
    'archive': True,
    'title': '',
    'author': '',
    'subject': '',
    'comments': '',
    'copyright': '',
    'keywords': '',
    'published_for': '',
    'publisher': '',
    'expiry_days': 0,
    'exclude_hidden': False,
    'embed_xrefs': True,
    'allow_resave': True,
    'display_on_open': False,
    'preflight': True,
    'preflight_profile': 'Standard',
    'open_folder': True,
}

_VERSION_MARK = 'zqversionqz'
_WILD_MARK = 'zqwildqz'
_SEPARATORS = '_-. '


# ---- pure: settings -------------------------------------------------------------------


def normalize_settings(values):
    """DEFAULTS overlaid with the known keys of values, types tidied."""
    out = dict(DEFAULTS)
    for key in DEFAULTS:
        if isinstance(values, dict) and key in values and values[key] is not None:
            out[key] = values[key]
    for key in ('archive', 'exclude_hidden', 'embed_xrefs', 'allow_resave', 'display_on_open',
                'preflight', 'open_folder'):
        out[key] = bool(out[key])
    try:
        out['expiry_days'] = max(0, int(out['expiry_days']))
    except (TypeError, ValueError):
        out['expiry_days'] = 0
    if out['method'] not in METHODS:
        out['method'] = 'publish'
    for key in ('folder', 'subfolder', 'template', 'title', 'author', 'subject', 'comments',
                'copyright', 'keywords', 'published_for', 'publisher', 'preflight_profile'):
        out[key] = str(out[key] or '')
    if not out['template'].strip():
        out['template'] = DEFAULT_TEMPLATE
    return out


# ---- pure: names and versions -------------------------------------------------------------


def _pieces(template):
    """[('text', str) | ('token', raw)] for a template; '{{' and '}}' are literal braces."""
    out = []
    text = template or ''
    i = 0
    buf = []
    while i < len(text):
        if text.startswith('{{', i) or text.startswith('}}', i):
            buf.append(text[i])
            i += 2
            continue
        match = naming.TOKEN.match(text, i) if text[i] == '{' else None
        if match:
            if buf:
                out.append(['text', ''.join(buf)])
                buf = []
            out.append(['token', match.group(0)])
            i = match.end()
            continue
        buf.append(text[i])
        i += 1
    if buf:
        out.append(['text', ''.join(buf)])
    return out


def _render(template, values):
    """(text, missing): the template rendered token by token. A token that renders
    empty takes the separators before it with it (or, at the very start, the ones
    after it), so '{project}_{file}' with no project gives 'file', not '_file', and
    'A - {x} - B' with no x gives 'A - B'."""
    pieces = _pieces(template)
    missing = []
    empty = []
    for index, piece in enumerate(pieces):
        if piece[0] != 'token':
            continue
        text, lost = naming.render(piece[1], values)
        for name in lost:
            if name not in missing:
                missing.append(name)
        piece[1] = text
        if not text:
            empty.append(index)
    for index in empty:
        before = pieces[index - 1] if index > 0 else None
        after = pieces[index + 1] if index + 1 < len(pieces) else None
        if before is not None and before[0] == 'text' and before[1].rstrip(_SEPARATORS) != before[1]:
            before[1] = before[1].rstrip(_SEPARATORS)
        elif after is not None and after[0] == 'text':
            after[1] = after[1].lstrip(_SEPARATORS)
    return ''.join(p[1] for p in pieces), missing


def _tidy_stem(stem):
    """Doubled separators collapsed ('A__B' -> 'A_B') and none left at the ends."""
    text = re.sub(r'([_\-.])\1+', r'\1', stem)
    text = re.sub(r' {2,}', ' ', text)
    return text.strip(_SEPARATORS)


def _clean(name):
    """A tidy, Windows-safe NWD file name."""
    from namo import paths
    stem, ext = os.path.splitext(name)
    if ext.lower() != '.nwd':
        stem, ext = name, '.nwd'
    stem = _tidy_stem(stem) or 'Published'
    return paths.safe_filename(stem + ext, max_len=200)


def template_problems(template):
    """Sentences about a template that cannot work: unknown tokens, no version token."""
    from namo import naming as _n
    problems = []
    known = set(['project', 'project_number', 'company', 'file', 'title', 'user', 'version']
                + list(DATE_TOKENS))
    unknown = [t for t in _n.tokens(template) if t.lower() not in known]
    if unknown:
        problems.append('Unknown token%s: %s.' % ('' if len(unknown) == 1 else 's',
                                                   ', '.join('{%s}' % t for t in unknown)))
    if not any(t.lower() == 'version' for t in _n.tokens(template)):
        problems.append('Add {version} (for example v{version:00}) so every publish gets its own number.')
    return problems


def render_name(template, values, version):
    """(file name, missing tokens): the template rendered with values plus {version},
    separators left by empty tokens collapsed, '.nwd' ensured, made Windows-safe."""
    tokens = dict(values or {})
    tokens['version'] = int(version)
    text, missing = _render(template or DEFAULT_TEMPLATE, tokens)
    return _clean(text), missing


def name_pattern(template, values):
    """A compiled regex matching every file name the template can produce with these
    values, any date or time, and any version: group 1 is the version number. None
    when the template has no {version}."""
    tokens = dict(values or {})
    if not any(t.lower() == 'version' for t in naming.tokens(template or DEFAULT_TEMPLATE)):
        return None
    tokens['version'] = _VERSION_MARK
    for key in DATE_TOKENS:
        tokens[key] = _WILD_MARK
    text, _missing = _render(template or DEFAULT_TEMPLATE, tokens)
    name = _clean(text)
    escaped = re.escape(name)
    escaped = escaped.replace(re.escape(_VERSION_MARK), r'(\d+)', 1)
    escaped = escaped.replace(re.escape(_VERSION_MARK), r'\d+')
    escaped = escaped.replace(re.escape(_WILD_MARK), r'.+?')
    return re.compile('^' + escaped + '$', re.IGNORECASE)


def versions_in(template, values, names):
    """[(version, name)] for the names that fit the template, sorted by version."""
    pattern = name_pattern(template, values)
    if pattern is None:
        return []
    out = []
    for name in names:
        match = pattern.match(name)
        if match:
            try:
                out.append((int(match.group(1)), name))
            except (TypeError, ValueError):
                continue
    out.sort(key=lambda pair: (pair[0], naming.natural_key(pair[1])))
    return out


def next_version(template, values, existing_names):
    """The highest version among existing names that fit the template, plus one (1
    when none do). Gaps do not matter: v01 and v03 give 4."""
    found = versions_in(template, values, existing_names)
    return (found[-1][0] + 1) if found else 1


def plan_target(template, values, existing_names):
    """(version, name) of the next file, bumped past any name already taken (case-
    insensitively) even when it does not fit the pattern."""
    taken = set(n.lower() for n in existing_names)
    version = next_version(template, values, existing_names)
    name, _missing = render_name(template, values, version)
    if not any(t.lower() == 'version' for t in naming.tokens(template or DEFAULT_TEMPLATE)):
        if name.lower() in taken:
            stem, ext = os.path.splitext(name)
            n = 2
            while ('%s (%d)%s' % (stem, n, ext)).lower() in taken:
                n += 1
            name = '%s (%d)%s' % (stem, n, ext)
        return version, name
    tries = 0
    while name.lower() in taken and tries < 10000:
        version += 1
        tries += 1
        name, _missing = render_name(template, values, version)
    return version, name


def _norm(path):
    text = str(path or '').strip().strip('"')
    if not text:
        return ''
    return os.path.normcase(os.path.normpath(os.path.abspath(text)))


def protected_paths(doc_path, model_paths=()):
    """The files a publish must never write over or move: the open document's own
    file and every file an appended model was loaded from or made from (normalised,
    blanks dropped)."""
    out = set()
    for path in [doc_path] + list(model_paths or []):
        normalised = _norm(path)
        if normalised:
            out.add(normalised)
    return out


def is_protected(path, protected):
    return _norm(path) in set(protected or ())


def target_problem(path, protected, exists=None):
    """None when the NWD may be written at path, else a sentence: the path is the open
    document or one of its model files, or a file is already there. Nothing is ever
    overwritten."""
    if is_protected(path, protected):
        return ('%s is the open document or one of its model files. Change the folder or the '
                'file name.' % os.path.basename(path))
    there = os.path.exists(path) if exists is None else exists
    if there:
        return '%s is already there. Nothing was overwritten; try again.' % os.path.basename(path)
    return None


def archive_plan(folder_names, template, values, new_name, archive_names=(), keep=()):
    """[{'name', 'target', 'version'}]: the older versions in the folder (those that fit
    the template, except new_name) and the file name each gets inside Archive,
    ' (2)'-style unique against archive_names and each other. Version order. keep:
    file names that must stay where they are (the open document, appended models)."""
    taken = set(n.lower() for n in archive_names)
    staying = set(str(n).lower() for n in keep or ())
    out = []
    for version, name in versions_in(template, values, folder_names):
        if name.lower() == str(new_name).lower() or name.lower() in staying:
            continue
        target = name
        if target.lower() in taken:
            stem, ext = os.path.splitext(name)
            n = 2
            while ('%s (%d)%s' % (stem, n, ext)).lower() in taken:
                n += 1
            target = '%s (%d)%s' % (stem, n, ext)
        taken.add(target.lower())
        out.append({'name': name, 'target': target, 'version': version})
    return out


def publish_fields(props):
    """(options, properties, expiry_days): NwdExportOptions and PublishProperties
    values by live property name, from a settings dict. Text fields are included only
    when not blank, so PublishProperties keeps its own default otherwise."""
    props = normalize_settings(props)
    options = {'ExcludeHiddenItems': props['exclude_hidden'], 'EmbedXrefs': props['embed_xrefs']}
    properties = {'AllowResave': props['allow_resave'], 'DisplayOnOpen': props['display_on_open']}
    for key, field in (('title', 'Title'), ('author', 'Author'), ('subject', 'Subject'),
                       ('comments', 'Comments'), ('copyright', 'Copyright'),
                       ('keywords', 'Keywords'), ('published_for', 'PublishedFor'),
                       ('publisher', 'Publisher')):
        text = props[key].strip()
        if text:
            properties[field] = text
    return options, properties, props['expiry_days']


def history_record(path, version, method, size, preflight_text, user, doc_path, archived,
                   when=None):
    """The JSON record logged for one publish."""
    stamp = (when or datetime.datetime.now()).strftime('%Y-%m-%dT%H:%M:%S')
    return {'time': stamp, 'user': user, 'path': path, 'name': os.path.basename(path),
            'version': int(version), 'method': method, 'size': size,
            'preflight': preflight_text, 'document': doc_path, 'archived': int(archived)}


def save_question(name, doc_name):
    """The confirm before Save as NWD, which re-points the open document."""
    was = doc_name or 'This document'
    return ('Save as NWD makes %s the open document. %s stays on disk as it was last saved, '
            'and changes made since then go only into the NWD.\n\nSave as %s?' % (name, was, name))


def confirm_text(name, folder, method, to_archive=0, doc_name=''):
    """The question asked before anything is written: the exact file and folder, what
    will move to Archive, and (Save as NWD) what happens to the open document."""
    verb = {'publish': 'Publish', 'export': 'Export', 'save': 'Save as'}.get(method, 'Publish')
    lines = ['%s %s?' % (verb, name), '', 'Folder: %s' % folder]
    if to_archive:
        lines.append('%d older version%s will move into %s.' % (
            to_archive, '' if to_archive == 1 else 's', ARCHIVE_FOLDER))
    if method == 'save':
        was = doc_name or 'The document you have open'
        lines.extend(['', '%s becomes the open document. %s stays on disk as it was last saved, and '
                          'changes made since then go only into the NWD.' % (name, was)])
    else:
        lines.extend(['', 'The open document is not changed.'])
    return '\n'.join(lines)


def toast_text(name, folder, archived, archive_failed, history_note, method, size=None):
    """(level, message, detail) after a successful write: what was written, where and
    how big, then what was moved."""
    verb = {'publish': 'Published', 'export': 'Exported', 'save': 'Saved as'}.get(method, 'Published')
    message = '%s %s' % (verb, name)
    parts = ['%s%s.' % (os.path.join(folder, name), (', %s' % _size_text(size)) if size else '')]
    if method == 'save':
        parts.append('It is now the open document.')
    if archived:
        parts.append('%d older version%s moved to %s.' % (archived, '' if archived == 1 else 's',
                                                          ARCHIVE_FOLDER))
    level = 'success'
    if archive_failed:
        level = 'warning'
        parts.append('%d could not be moved (open elsewhere?): %s.'
                     % (len(archive_failed), ', '.join(archive_failed[:3])))
    if history_note:
        level = 'warning'
        parts.append(history_note)
    return level, message, ' '.join(parts)


def _size_text(size):
    size = float(size)
    for unit, factor in (('GB', 1024.0 ** 3), ('MB', 1024.0 ** 2), ('KB', 1024.0)):
        if size >= factor:
            return '{:,.1f} {}'.format(size / factor, unit)
    return '{:,.0f} bytes'.format(size)


def default_folder(doc_path):
    """The document's folder, else Documents, else the user profile."""
    if doc_path:
        folder = os.path.dirname(doc_path)
        if folder and os.path.isdir(folder):
            return folder
    documents = os.path.join(os.path.expanduser('~'), 'Documents')
    return documents if os.path.isdir(documents) else os.path.expanduser('~')


def start_folder(settings, doc_path):
    """The folder the form opens on: the saved one when it still exists, else
    default_folder()."""
    folder = str((settings or {}).get('folder') or '')
    return folder if folder and os.path.isdir(folder) else default_folder(doc_path)


def target_folder(settings):
    """folder joined with the (optional) subfolder."""
    folder = settings.get('folder') or ''
    sub = str(settings.get('subfolder') or '').strip().strip('\\/')
    return os.path.join(folder, sub) if sub else folder


def form_fields(settings, doc_path, profiles, user):
    """The NWD Publisher form (namo.ui.form fields) pre-filled from settings; profiles are
    the preflight profile names, user the default author."""
    settings = normalize_settings(settings)
    profiles = list(profiles) or ['Standard']
    folder = start_folder(settings, doc_path)
    chosen_profile = settings['preflight_profile'] if settings['preflight_profile'] in profiles \
        else profiles[0]
    method_hint = ('Save as NWD makes the open document the NWD from then on; '
                   'Publish and Export leave it as it is.')
    return [
        {'kind': 'folder', 'key': 'folder', 'label': 'Folder', 'default': folder, 'required': True},
        {'kind': 'text', 'key': 'subfolder', 'label': 'Subfolder', 'default': settings['subfolder'],
         'hint': 'Created when missing. Leave blank to publish straight into the folder.'},
        {'kind': 'text', 'key': 'template', 'label': 'File name', 'default': settings['template'],
         'required': True, 'hint': TOKEN_HINT,
         'validate': lambda text: ' '.join(template_problems(text)) or None},
        {'kind': 'radio', 'key': 'method', 'label': 'How', 'options': METHOD_LABELS,
         'default': settings['method'], 'fallback': None, 'hint': method_hint},
        {'kind': 'check', 'key': 'archive', 'label': 'Move older versions into an Archive folder',
         'default': settings['archive']},
        {'kind': 'separator'},
        {'kind': 'text', 'key': 'title', 'label': 'Title', 'default': settings['title'],
         'enabled_if': ('method', 'publish'), 'hint': 'Blank uses the file name; tokens work here too.'},
        {'kind': 'text', 'key': 'author', 'label': 'Author',
         'default': settings['author'] or user, 'enabled_if': ('method', 'publish')},
        {'kind': 'text', 'key': 'comments', 'label': 'Comments', 'default': settings['comments'],
         'enabled_if': ('method', 'publish')},
        {'kind': 'text', 'key': 'copyright', 'label': 'Copyright', 'default': settings['copyright'],
         'enabled_if': ('method', 'publish')},
        {'kind': 'int', 'key': 'expiry_days', 'label': 'Expires after (days)', 'min': 0, 'max': 3650,
         'default': settings['expiry_days'], 'enabled_if': ('method', 'publish'),
         'hint': '0 means it never expires.'},
        {'kind': 'check', 'key': 'allow_resave', 'label': 'Recipients may save it again',
         'default': settings['allow_resave'], 'enabled_if': ('method', 'publish')},
        {'kind': 'check', 'key': 'exclude_hidden', 'label': 'Leave hidden items out',
         'default': settings['exclude_hidden'], 'enabled_if': ('method', ['publish', 'export'])},
        {'kind': 'separator'},
        {'kind': 'check', 'key': 'preflight', 'label': 'Run Preflight first and stop on a failure',
         'default': settings['preflight']},
        {'kind': 'choice', 'key': 'preflight_profile', 'label': 'Preflight profile',
         'options': profiles, 'default': chosen_profile, 'fallback': None, 'enabled_if': ('preflight', True)},
        {'kind': 'check', 'key': 'open_folder', 'label': 'Open the folder afterwards',
         'default': settings['open_folder']},
        {'kind': 'text', 'key': 'save_as', 'label': 'Save these settings as',
         'hint': 'A profile name for next time, shared with the team. Blank saves nothing.'},
    ]



# ---- API half -------------------------------------------------------------------------------


def _doc(doc):
    if doc is not None:
        return doc
    from pynavis._api import Application
    return Application.ActiveDocument


def publish(doc, path, method, props):
    """Writes the NWD at path. Raises whatever Navisworks raises (a locked file, a
    folder without write access) for the caller to report."""
    document = _doc(doc)
    if method == 'save':
        from pynavis import export
        export.save_nwd(path, doc=document)
        return
    from pynavis._api import Api
    options_fields, property_fields, expiry_days = publish_fields(props)
    options = Api.NwdExportOptions()
    for field in sorted(options_fields):
        setattr(options, field, options_fields[field])
    if method == 'export':
        document.ExportToNwd(path, options)
        return
    properties = Api.PublishProperties()
    for field in sorted(property_fields):
        setattr(properties, field, property_fields[field])
    if expiry_days > 0:
        from System import DateTime
        properties.ExpiryDate = DateTime.Now.AddDays(float(expiry_days))
    document.PublishFile(path, options, properties)


def archive(folder, plan):
    """Moves each planned file into folder\\Archive. Returns (moved names, failed names)."""
    from namo import paths
    if not plan:
        return [], []
    target = os.path.join(folder, ARCHIVE_FOLDER)
    moved, failed = [], []
    try:
        paths.ensure_dir(target)
    except Exception:
        return [], [entry['name'] for entry in plan]
    for entry in plan:
        destination = os.path.join(target, entry['target'])
        try:
            if os.path.exists(destination):
                raise IOError('already in the archive')
            os.rename(os.path.join(folder, entry['name']), destination)
            moved.append(entry['name'])
        except Exception:
            failed.append(entry['name'])
    return moved, failed


def list_files(folder):
    """File names in a folder ([] when it does not exist)."""
    try:
        return sorted(n for n in os.listdir(folder) if os.path.isfile(os.path.join(folder, n)))
    except OSError:
        return []


def log_history(record, doc=None, doc_path=None):
    """Adds the record to the publish history of the document (doc_path: its file as it
    was BEFORE publishing, since Save as NWD renames the open document). Returns None,
    or a sentence when it could not be written."""
    try:
        from namo import store
        records = store.RecordStore(HISTORY_STORE, doc_path=doc_path, doc=_doc(doc))
        records.add(record, prefix='P', width=4)
        return None
    except Exception as error:
        return 'The publish history could not be written (%s).' % (str(error) or type(error).__name__)


def history(doc=None):
    """The document's publish records, oldest first."""
    try:
        from namo import store
        return store.records_for_active_doc(HISTORY_STORE, doc=_doc(doc)).list()
    except Exception:
        return []


def _templates():
    from namo import templates
    return templates.Templates(TEMPLATES_TOOL)


def profile_names():
    try:
        return _templates().names()
    except Exception:
        return []


def load_profile(name):
    try:
        found = _templates().get(name)
    except Exception:
        found = None
    return normalize_settings(found) if found is not None else None


def save_profile(name, settings):
    return _templates().save(name, normalize_settings(settings))
