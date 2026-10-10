# -*- coding: utf-8 -*-
"""Appended models: listing, identifying, file freshness, batch append and model actions.

The vocabulary every Models-panel tool shares (Batch Append, Source Files, Link
Navigator, Stale File Alert) and that Health Check, Session Stats and Preflight read:

  * an info dict per appended model (models_info): index, name, cache file, source
    file, units, creator, key. `file` is Model.FileName, the file Navisworks loaded
    (usually the NWC cache); `source` is Model.SourceFileName, the native file it was
    made from (the RVT, IFC, DWG...). Either may be '' or point somewhere that does
    not exist on this machine (an NWC exported on another PC keeps its author's RVT
    path).
  * a key per model ('<file lower>#<guid>#<n>'): stable while the document is open,
    so a pane row or a hook can find "its" model again after others were appended or
    removed. Indexes are NEVER kept across clicks: resolve_index(key) re-finds them.
  * freshness (stale_status): the source saved after the cache means a Refresh would
    load newer geometry.

Network folders: os.stat on an offline UNC share can block for seconds, so every
stat goes through reachable(), which probes each share folder at most once per
15 s (60 s when it answered) for the whole session.

The pure half (no Navisworks) comes first and is unit tested; the API half lazy-imports
pynavis so `import namo.modelmgmt` works anywhere.
"""

import csv
import io
import os
import time

from namo import naming

DEFAULT_TYPES = ['nwc', 'nwd', 'nwf', 'rvt', 'ifc', 'dwg', 'dxf', 'dgn', 'fbx', 'rcp', 'rcs',
                 'skp', '3ds', 'stp', 'step', 'igs', 'iges', 'sat', 'jt', 'prt', 'dwf', 'dwfx',
                 'obj', 'stl']

SCAN_LIMIT = 5000
STALE_TOLERANCE = 2.0           # seconds: file systems round mtimes (FAT 2 s)
REACH_OK_SECONDS = 60.0
REACH_BAD_SECONDS = 15.0

# Freshness statuses: (status text, level). level is what reports and toasts use.
CURRENT = 'Current'
OUT_OF_DATE = 'Out of date'
SOURCE_NOT_FOUND = 'Source not found'
SOURCE_OFFLINE = 'Source folder offline'
CACHE_NOT_FOUND = 'File not found'
CACHE_OFFLINE = 'Folder offline'
NO_FILE = 'No file name'
STATUS_LEVEL = {CURRENT: 'pass', OUT_OF_DATE: 'warn', SOURCE_NOT_FOUND: 'info',
                SOURCE_OFFLINE: 'info', CACHE_NOT_FOUND: 'warn', CACHE_OFFLINE: 'warn',
                NO_FILE: 'info'}


# ---- pure: paths and file types --------------------------------------------------


def parse_types(text):
    """File types from text like 'nwc, .rvt;IFC dwg': lowercase extensions without the
    dot, unique, in the order typed. Blank text gives DEFAULT_TYPES."""
    raw = str(text or '').replace(',', ' ').replace(';', ' ').replace('|', ' ').split()
    out = []
    for word in raw:
        ext = word.strip().lower().lstrip('*').lstrip('.')
        if ext and ext not in out:
            out.append(ext)
    return out or list(DEFAULT_TYPES)


def types_text(types):
    """'nwc nwd rvt' for a list of extensions."""
    return ' '.join(types or [])


def norm_path(path):
    """A comparable form of a path: absolute, normalised, case-folded. '' for blank."""
    text = str(path or '').strip().strip('"')
    if not text:
        return ''
    return os.path.normcase(os.path.normpath(os.path.abspath(text)))


def stem_key(path):
    """norm_path without the extension: 'c:\\m\\arch' for both ARCH.rvt and its
    ARCH.nwc cache, so an RVT appended directly is recognised from either file."""
    normalised = norm_path(path)
    return os.path.splitext(normalised)[0] if normalised else ''


def ext_of(path):
    return os.path.splitext(str(path or ''))[1].lower().lstrip('.')


def kind_of(path):
    """'NWC', 'RVT'... from a file name; '' when there is no extension."""
    return ext_of(path).upper()


def base_name(path):
    return str(path or '').replace('\\', '/').split('/')[-1]


def folder_of(path):
    text = str(path or '').strip()
    return os.path.dirname(text) if text else ''


def is_network(path):
    return str(path or '').startswith('\\\\') or str(path or '').startswith('//')


def share_root(path):
    """'\\\\server\\share' for a UNC path, '' otherwise (what reachability is cached by)."""
    text = str(path or '').replace('/', '\\')
    if not text.startswith('\\\\'):
        return ''
    parts = text[2:].split('\\')
    if len(parts) < 2:
        return ''
    return '\\\\' + parts[0] + '\\' + parts[1]


def format_size(size):
    """'812 KB', '12.3 MB', '1.42 GB'; '' for None."""
    if size is None:
        return ''
    size = float(size)
    for unit, factor in (('GB', 1024.0 ** 3), ('MB', 1024.0 ** 2), ('KB', 1024.0)):
        if size >= factor:
            value = size / factor
            if value >= 100:
                return '{:,.0f} {}'.format(value, unit)
            if value >= 10:
                return '{:,.1f} {}'.format(value, unit)
            return '{:,.2f} {}'.format(value, unit)
    return '{:,.0f} bytes'.format(size)


def format_time(epoch):
    """Local 'YYYY-MM-DD HH:MM' for a timestamp; '' for None."""
    if epoch is None:
        return ''
    try:
        return time.strftime('%Y-%m-%d %H:%M', time.localtime(float(epoch)))
    except (ValueError, OverflowError, OSError):
        return ''


def format_age(seconds):
    """A friendly span: 'under a minute', '12 minutes', '5 hours', '3 days', '7 weeks'."""
    if seconds is None:
        return ''
    seconds = abs(float(seconds))
    if seconds < 60:
        return 'under a minute'
    minutes = int(seconds // 60)
    if minutes < 60:
        return '%d minute%s' % (minutes, '' if minutes == 1 else 's')
    hours = int(seconds // 3600)
    if hours < 48:
        return '%d hour%s' % (hours, '' if hours == 1 else 's')
    days = int(seconds // 86400)
    if days < 70:
        return '%d days' % days
    weeks = days // 7
    return '%d weeks' % weeks


def plural(count, noun, plural_form=None):
    """'1 model' / '3 models' / '1,204 items'."""
    word = noun if count == 1 else (plural_form or noun + 's')
    return '%s %s' % ('{:,}'.format(count), word)


def join_names(names, limit=3):
    """'A, B and C' / 'A, B, C and 4 more' for a toast detail."""
    names = [str(n) for n in names]
    if not names:
        return ''
    if len(names) == 1:
        return names[0]
    if len(names) <= limit:
        return '%s and %s' % (', '.join(names[:-1]), names[-1])
    return '%s and %d more' % (', '.join(names[:limit]), len(names) - limit)


# ---- pure: folder scan and manifests ------------------------------------------------


def scan_folder(folder, types, recursive=True, limit=SCAN_LIMIT):
    """(files, truncated): model files under folder whose extension is in types,
    [{'path', 'name', 'folder', 'relative', 'ext', 'size', 'mtime'}] sorted naturally
    by relative path. Office lock files (~$...) and hidden folders are skipped.
    truncated is True when more than `limit` files matched."""
    wanted = set(t.lower() for t in types or [])
    out = []
    truncated = False
    root = os.path.abspath(folder)
    for current, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if not d.startswith('.')) if recursive else []
        for name in files:
            if name.startswith('~$') or name.startswith('.'):
                continue
            ext = ext_of(name)
            if wanted and ext not in wanted:
                continue
            path = os.path.join(current, name)
            try:
                info = os.stat(path)
                size, mtime = info.st_size, info.st_mtime
            except (IOError, OSError):
                size, mtime = None, None
            out.append({'path': path, 'name': name, 'folder': current,
                        'relative': os.path.relpath(path, root), 'ext': ext,
                        'size': size, 'mtime': mtime})
            if len(out) > limit:
                truncated = True
                break
        if truncated:
            break
    out = out[:limit]
    out.sort(key=lambda f: naming.natural_key(f['relative']))
    return out, truncated


_PATH_HEADERS = ('path', 'file', 'filename', 'file name', 'file path', 'model', 'models')
_ORDER_HEADERS = ('order', 'sequence', 'seq', '#', 'no', 'number')
_TRADE_HEADERS = ('trade', 'discipline')


def _cell(row, index):
    if index is None or index >= len(row):
        return ''
    value = row[index]
    if value is None:
        return ''
    if isinstance(value, float) and value == int(value):
        return str(int(value))
    return str(value).strip()


def _order_value(text):
    try:
        return float(str(text).replace(',', '.'))
    except (TypeError, ValueError):
        return None


def parse_manifest_rows(rows, base_folder=''):
    """(entries, problems) from manifest rows (lists of cells).

    A first row naming a path column ('path', 'file', 'model'...) is a header and may
    also name 'order' and 'trade' columns. Without a header the first column is the
    path, a numeric second column the order and the next text column the trade.
    Relative paths are taken from base_folder. Blank rows and rows starting with '#'
    are skipped. entries [{'path', 'order', 'trade', 'row'}] sorted by order (rows
    without one keep their place after the ordered ones, in file order).
    """
    rows = [list(r) for r in rows if r is not None]
    problems = []
    columns = {'path': 0, 'order': None, 'trade': None}
    start = 0
    if rows:
        header = [str(c or '').strip().lower() for c in rows[0]]
        if any(h in _PATH_HEADERS for h in header):
            start = 1
            columns = {'path': None, 'order': None, 'trade': None}
            for index, name in enumerate(header):
                if name in _PATH_HEADERS and columns['path'] is None:
                    columns['path'] = index
                elif name in _ORDER_HEADERS and columns['order'] is None:
                    columns['order'] = index
                elif name in _TRADE_HEADERS and columns['trade'] is None:
                    columns['trade'] = index
        else:
            columns = {'path': 0, 'order': None, 'trade': None}
    entries = []
    for number, row in enumerate(rows[start:], start + 1):
        path = _cell(row, columns['path']).strip('"')
        if not path or path.startswith('#'):
            continue
        order = _order_value(_cell(row, columns['order'])) if columns['order'] is not None else None
        trade = _cell(row, columns['trade']) if columns['trade'] is not None else ''
        if start == 0:
            rest = [_cell(row, i) for i in range(1, len(row))]
            if rest and order is None and _order_value(rest[0]) is not None:
                order = _order_value(rest[0])
                rest = rest[1:]
            if rest and not trade:
                trade = rest[0]
        if not os.path.isabs(path) and not is_network(path):
            path = os.path.normpath(os.path.join(base_folder or '', path))
        entries.append({'path': path, 'order': order, 'trade': trade, 'row': number})
    if not entries and rows:
        problems.append('No file paths were found in the manifest.')
    ordered = [e for e in entries if e['order'] is not None]
    unordered = [e for e in entries if e['order'] is None]
    ordered.sort(key=lambda e: (e['order'], e['row']))
    return ordered + unordered, problems


def manifest_rows(path):
    """The raw rows of a manifest: .xlsx through pynavis.xl (first sheet), .csv through
    the csv module (UTF-8, BOM tolerated), anything else one path per line. Raises
    ValueError with a sentence when the file cannot be read."""
    ext = ext_of(path)
    try:
        if ext in ('xlsx', 'xlsm'):
            from pynavis import xl
            return xl.read(path)
        with io.open(path, 'r', encoding='utf-8-sig') as handle:
            text = handle.read()
    except (IOError, OSError) as error:
        raise ValueError('Could not read %s: %s' % (base_name(path), error))
    except Exception as error:
        raise ValueError('Could not read %s as a workbook: %s' % (base_name(path), error))
    lines = text.splitlines()
    if ext in ('csv', 'tsv'):
        delimiter = '\t' if ext == 'tsv' else (';' if lines and lines[0].count(';') > lines[0].count(',') else ',')
        return [row for row in csv.reader(lines, delimiter=delimiter)]
    return [[line.strip()] for line in lines]


def read_manifest(path):
    """(entries, problems) for a manifest file (see parse_manifest_rows)."""
    rows = manifest_rows(path)
    return parse_manifest_rows(rows, os.path.dirname(os.path.abspath(path)))


def appended_index(infos):
    """{'paths': set of norm paths, 'stems': set of stem keys} of what is appended, from
    models_info() dicts (file and source)."""
    paths = set()
    stems = set()
    for info in infos:
        for path in (info.get('file'), info.get('source')):
            if path:
                paths.add(norm_path(path))
                stems.add(stem_key(path))
    return {'paths': paths, 'stems': stems}


def plan_append(candidates, infos):
    """Rows for the Batch Append preview: each candidate dict (with 'path') gets
    'status' ('New', 'Appended', 'Missing', 'Repeated') and 'checked' (True for New).
    'Appended' also matches an RVT whose NWC cache is loaded (same folder and stem)."""
    index = appended_index(infos)
    seen = set()
    out = []
    for candidate in candidates:
        row = dict(candidate)
        normalised = norm_path(row['path'])
        exists = row.get('exists')
        if exists is None:
            exists = os.path.isfile(row['path'])
        if normalised in seen:
            status = 'Repeated'
        elif not exists:
            status = 'Missing'
        elif normalised in index['paths'] or stem_key(row['path']) in index['stems']:
            status = 'Appended'
        else:
            status = 'New'
        seen.add(normalised)
        row['status'] = status
        row['checked'] = status == 'New'
        out.append(row)
    return out


# ---- pure: freshness ----------------------------------------------------------------


def stale_status(cache_path, cache_sig, source_path, source_sig, tolerance=STALE_TOLERANCE):
    """Freshness of one model from its two files.

    cache_sig / source_sig are (mtime, size) tuples, or the strings 'missing' /
    'offline' (see signature()), or None when that path is blank. Returns
    {'status', 'level', 'detail', 'delta'}: delta is source mtime minus cache mtime in
    seconds when both are known, else None.
    """
    def known(sig):
        return isinstance(sig, tuple)

    delta = None
    if known(cache_sig) and known(source_sig):
        delta = float(source_sig[0]) - float(cache_sig[0])
    if not cache_path and not source_path:
        return {'status': NO_FILE, 'level': 'info', 'delta': None,
                'detail': 'The model carries no file name (embedded in an NWD).'}
    if cache_path and cache_sig == 'offline':
        return {'status': CACHE_OFFLINE, 'level': 'warn', 'delta': None,
                'detail': 'The network folder of %s does not answer.' % base_name(cache_path)}
    if cache_path and cache_sig == 'missing':
        return {'status': CACHE_NOT_FOUND, 'level': 'warn', 'delta': None,
                'detail': '%s is not where the model was loaded from; a Refresh cannot reload it.'
                          % base_name(cache_path)}
    same = bool(source_path) and norm_path(source_path) == norm_path(cache_path)
    if not source_path or same:
        return {'status': CURRENT, 'level': 'pass', 'delta': None,
                'detail': 'Loaded directly from %s.' % base_name(cache_path or source_path)}
    if source_sig == 'offline':
        return {'status': SOURCE_OFFLINE, 'level': 'info', 'delta': None,
                'detail': 'The network folder of %s does not answer.' % base_name(source_path)}
    if source_sig == 'missing' or not known(source_sig):
        return {'status': SOURCE_NOT_FOUND, 'level': 'info', 'delta': None,
                'detail': '%s is not on this computer (normal for a model exported elsewhere).'
                          % base_name(source_path)}
    if not cache_path:
        return {'status': CURRENT, 'level': 'pass', 'delta': None,
                'detail': 'Only the source file is known.'}
    if delta is not None and delta > tolerance:
        return {'status': OUT_OF_DATE, 'level': 'warn', 'delta': delta,
                'detail': '%s was saved %s after %s.' % (base_name(source_path), format_age(delta),
                                                       base_name(cache_path))}
    return {'status': CURRENT, 'level': 'pass', 'delta': delta,
            'detail': '%s is not newer than %s.' % (base_name(source_path), base_name(cache_path))}


def stale_summary(rows):
    """(level, message, detail) for a toast from stale rows ({'name', 'status'})."""
    total = len(rows)
    if not total:
        return ('info', 'No models to check', 'Append models first.')
    late = [r for r in rows if r['status'] == OUT_OF_DATE]
    lost = [r for r in rows if r['status'] in (CACHE_NOT_FOUND, CACHE_OFFLINE)]
    if late:
        detail = '%s. Refresh loads the newer files.' % join_names([r['name'] for r in late])
        if lost:
            detail += ' %s cannot be found.' % plural(len(lost), 'file')
        return ('warning', '%s out of date' % plural(len(late), 'model'), detail)
    if lost:
        return ('warning', '%s not found' % plural(len(lost), 'model file'),
                '%s. Check the folder or re-append them.' % join_names([r['name'] for r in lost]))
    unknown = [r for r in rows if STATUS_LEVEL.get(r['status']) == 'info']
    if unknown and len(unknown) == total:
        return ('info', 'No source files to compare', 'The models were exported elsewhere or are embedded.')
    return ('success', 'All %s are current' % plural(total, 'model'),
            ('%d without a source file on this computer.' % len(unknown)) if unknown else None)


# ---- pure: model keys -------------------------------------------------------------------


def model_keys(pairs):
    """Keys for models from [(file_name, guid_text)] in model order: '<file lower>#<guid>#<n>'
    where n counts earlier models with the same file and guid (the same file appended
    twice gets #0 and #1)."""
    counts = {}
    out = []
    for file_name, guid in pairs:
        base = '%s#%s' % (str(file_name or '').lower(), str(guid or '').lower())
        n = counts.get(base, 0)
        counts[base] = n + 1
        out.append('%s#%d' % (base, n))
    return out


def duplicate_files(infos):
    """{norm file path: [indexes]} for files appended more than once."""
    seen = {}
    for info in infos:
        path = norm_path(info.get('file') or info.get('source'))
        if path:
            seen.setdefault(path, []).append(info['index'])
    return dict((k, v) for k, v in seen.items() if len(v) > 1)


# ---- file signatures (stat with a reachability guard) -------------------------------------


def _reach_cache():
    from namo import session
    cache = session.get('mdl', 'reach')
    if cache is None:
        cache = session.set('mdl', 'reach', {})
    return cache


def reachable(path):
    """False when path is on a network share that does not answer (probed at most once
    per 15 s; 60 s once it answered). Local paths are always reachable."""
    root = share_root(path)
    if not root:
        return True
    cache = _reach_cache()
    now = time.time()
    hit = cache.get(root.lower())
    if hit is not None:
        ok, stamp = hit
        if now - stamp < (REACH_OK_SECONDS if ok else REACH_BAD_SECONDS):
            return ok
    try:
        ok = os.path.isdir(root)
    except Exception:
        ok = False
    cache[root.lower()] = (ok, now)
    return ok


def signature(path):
    """(mtime, size) of a file, 'missing' when it is not there, 'offline' when its
    network share does not answer, None for a blank path. Never raises."""
    if not path:
        return None
    if not reachable(path):
        return 'offline'
    try:
        info = os.stat(path)
    except (IOError, OSError):
        return 'missing'
    except Exception:
        return 'missing'
    if not os.path.isfile(path):
        return 'missing'
    return (float(info.st_mtime), int(info.st_size))


# ---- API half ------------------------------------------------------------------------------


def _doc(doc):
    if doc is not None:
        return doc
    from pynavis._api import Application
    return Application.ActiveDocument


def has_models(doc=None):
    try:
        document = _doc(doc)
        return document is not None and document.Models.Count > 0
    except Exception:
        return False


def models_info(doc=None):
    """[{'index', 'model', 'root', 'name', 'file', 'source', 'kind', 'units', 'creator',
    'guid', 'key', 'transformed'}] for every appended model, model order. name is the
    source file's base name (else the loaded file's)."""
    document = _doc(doc)
    collection = document.Models
    infos = []
    for index in range(collection.Count):
        model = collection[index]
        file_name = _text(lambda: model.FileName)
        source = _text(lambda: model.SourceFileName)
        units = _text(lambda: str(model.Units))
        creator = _text(lambda: model.Creator)
        guid = _text(lambda: str(model.Guid))
        try:
            transformed = not model.Transform.IsIdentity()
        except Exception:
            transformed = False
        name = base_name(source or file_name) or 'Model %d' % (index + 1)
        infos.append({'index': index, 'model': model, 'root': model.RootItem, 'name': name,
                      'file': file_name, 'source': source,
                      'kind': kind_of(source or file_name), 'units': units,
                      'creator': creator, 'guid': guid, 'transformed': transformed})
    keys = model_keys([(i['file'] or i['source'], i['guid']) for i in infos])
    for info, key in zip(infos, keys):
        info['key'] = key
    return infos


def _text(getter):
    try:
        value = getter()
    except Exception:
        return ''
    return '' if value is None else str(value)


def resolve_index(key, doc=None):
    """The CURRENT index of the model with this key, or None when it is gone."""
    for info in models_info(doc):
        if info['key'] == key:
            return info['index']
    return None


def info_for(key, doc=None):
    for info in models_info(doc):
        if info['key'] == key:
            return info
    return None


def stale_rows(doc=None, infos=None, tolerance=STALE_TOLERANCE):
    """Freshness of every model: [{'index', 'key', 'name', 'file', 'source', 'cache_time',
    'source_time', 'cache_size', 'source_size', 'delta', 'status', 'level', 'detail'}]."""
    rows = []
    for info in infos if infos is not None else models_info(doc):
        cache_sig = signature(info['file'])
        source_sig = signature(info['source'])
        verdict = stale_status(info['file'], cache_sig, info['source'], source_sig, tolerance)
        row = {'index': info['index'], 'key': info['key'], 'name': info['name'],
               'file': info['file'], 'source': info['source'],
               'cache_time': cache_sig[0] if isinstance(cache_sig, tuple) else None,
               'cache_size': cache_sig[1] if isinstance(cache_sig, tuple) else None,
               'source_time': source_sig[0] if isinstance(source_sig, tuple) else None,
               'source_size': source_sig[1] if isinstance(source_sig, tuple) else None}
        row.update(verdict)
        rows.append(row)
    return rows


def newest_file_time(rows):
    """The latest loaded-file time among stale rows (when the newest model data
    arrived), or None."""
    times = [r['cache_time'] for r in rows if r.get('cache_time') is not None]
    return max(times) if times else None


def count_items(root, budget=None, tick=None):
    """{'items', 'geometry', 'sampled'} under a model root, counted natively through
    DescendantsAndSelf; stops after `budget` items (sampled True). tick(done) every
    5,000 items; returning exactly False raises namo.items.Cancelled."""
    from namo.items import Cancelled
    items = geometry = 0
    sampled = False
    for item in root.DescendantsAndSelf:
        items += 1
        if item.HasGeometry:
            geometry += 1
        if tick is not None and items % 5000 == 0 and tick(items) == False:  # noqa: E712
            raise Cancelled()
        if budget is not None and items >= budget:
            sampled = True
            break
    return {'items': items, 'geometry': geometry, 'sampled': sampled}


def models_of_items(items, doc=None):
    """Distinct models (info dicts, model order) that the items belong to."""
    from namo import items as _items
    document = _doc(doc)
    infos = models_info(document)
    roots = [(info['root'], info) for info in infos]
    found = {}
    for item in _items.as_list(items):
        index = None
        try:
            index = int(document.Models.CreatePathId(item).ModelIndex)
        except Exception:
            index = None
        if index is not None and 0 <= index < len(infos):
            found[index] = infos[index]
            continue
        node = item
        last = item
        while node is not None:
            last = node
            node = node.Parent
        for root, info in roots:
            try:
                if root.Equals(last):
                    found[info['index']] = info
                    break
            except Exception:
                continue
    return [found[i] for i in sorted(found)]


def roots_for(keys, doc=None):
    """Root items of the models with these keys (missing keys skipped), model order."""
    wanted = set(keys)
    return [info['root'] for info in models_info(doc) if info['key'] in wanted]


def select_models(keys, doc=None):
    from namo import items as _items
    return _items.select(roots_for(keys, doc), doc=_doc(doc))


def zoom_models(keys, doc=None):
    from namo import items as _items
    roots = roots_for(keys, doc)
    if not roots:
        return False
    return _items.zoom(roots, doc=_doc(doc))


def isolate_models(keys, doc=None):
    """Hides every other model and shows these (items hidden inside them stay hidden).
    One undo step. Returns how many models are shown."""
    from pynavis.viewpoints import transaction
    from namo import items as _items
    document = _doc(doc)
    infos = models_info(document)
    wanted = set(keys)
    keep = [i['root'] for i in infos if i['key'] in wanted]
    others = [i['root'] for i in infos if i['key'] not in wanted]
    if not keep:
        return 0
    with transaction('Isolate models', document):
        if others:
            document.Models.SetHidden(_items.collection(others), True)
        document.Models.SetHidden(_items.collection(keep), False)
    return len(keep)


def set_models_hidden(keys, hidden, doc=None):
    """Hides or shows whole models (their root items). One undo step. Returns the count."""
    from pynavis.viewpoints import transaction
    from namo import items as _items
    document = _doc(doc)
    roots = roots_for(keys, document)
    if not roots:
        return 0
    with transaction('Hide models' if hidden else 'Show models', document):
        document.Models.SetHidden(_items.collection(roots), bool(hidden))
    return len(roots)


def show_all_models(doc=None):
    """Shows every model root (items hidden inside models stay hidden). One undo step."""
    document = _doc(doc)
    return set_models_hidden([i['key'] for i in models_info(document)], False, document)


def model_hidden(info):
    try:
        return bool(info['root'].IsHidden)
    except Exception:
        return False


def remove_models(keys, doc=None):
    """Removes models from the document, highest index first, each index re-resolved
    now. Returns (removed names, failed names)."""
    document = _doc(doc)
    wanted = set(keys)
    targets = [i for i in models_info(document) if i['key'] in wanted]
    removed, failed = [], []
    for info in sorted(targets, key=lambda i: -i['index']):
        index = resolve_index(info['key'], document)
        if index is None:
            failed.append(info['name'])
            continue
        try:
            ok = document.TryRemoveFile(index)
        except Exception:
            ok = False
        (removed if ok else failed).append(info['name'])
    removed.reverse()
    return removed, failed


def refresh_files(doc=None):
    """Document.UpdateFiles(): reloads every model whose file changed. Returns its
    boolean (True when Navisworks reloaded something)."""
    return bool(_doc(doc).UpdateFiles())


def model_folder(info):
    """The best folder to open for a model: the loaded file's when it exists, else the
    source file's, else ''."""
    for path in (info.get('file'), info.get('source')):
        if path and isinstance(signature(path), tuple):
            return path
    for path in (info.get('file'), info.get('source')):
        if path and os.path.isdir(folder_of(path)):
            return folder_of(path)
    return ''


def report_config(doc, label, base=None):
    """A report config for a ribbon run: files go to the document's folder when it is
    saved (else Documents), named '{file} - <label> - {date}' ('<label> - {date}' for
    an unsaved document). base: the report's own defaults to start from."""
    config = dict(base or {})
    try:
        name = doc.FileName or ''
    except Exception:
        name = ''
    folder = os.path.dirname(name) if name else ''
    if not folder or not os.path.isdir(folder):
        folder = os.path.join(os.path.expanduser('~'), 'Documents')
    config['folder'] = folder
    config['name_template'] = ('{file} - %s - {date}' % label) if name else ('%s - {date}' % label)
    return config


def append_files(paths, doc=None, report=None):
    """Appends files one at a time with Document.TryAppendFile, so each gets progress,
    a cancel point before it and its own failure. report(fraction, label) may raise a
    Cancelled (any class of that name): the batch then stops between files.

    Returns {'appended': [path], 'failed': [(path, reason)], 'seconds': {path: s},
    'stopped': bool, 'new_keys': [model keys added]}.
    """
    document = _doc(doc)
    before = set(i['key'] for i in models_info(document))
    out = {'appended': [], 'failed': [], 'seconds': {}, 'stopped': False, 'new_keys': []}
    total = len(paths)
    for number, path in enumerate(paths):
        if report is not None:
            try:
                report(float(number) / max(1, total),
                       'Appending %s (%d of %d)' % (base_name(path), number + 1, total))
            except Exception as error:
                if type(error).__name__ == 'Cancelled':
                    out['stopped'] = True
                    break
                raise
        if not os.path.isfile(path):
            out['failed'].append((path, 'The file is not there any more.'))
            continue
        started = time.time()
        try:
            ok = document.TryAppendFile(path)
            reason = '' if ok else 'Navisworks could not read it.'
        except Exception as error:
            ok = False
            reason = str(error) or type(error).__name__
        out['seconds'][path] = round(time.time() - started, 2)
        if ok:
            out['appended'].append(path)
        else:
            out['failed'].append((path, reason))
    if report is not None and not out['stopped']:
        try:
            report(1.0, 'Done')
        except Exception:
            pass
    out['new_keys'] = [i['key'] for i in models_info(document) if i['key'] not in before]
    return out
