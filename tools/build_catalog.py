# -*- coding: utf-8 -*-
"""Builds catalog.json, the machine-readable list of every Playground tool.

    python tools/build_catalog.py                 write catalog.json
    python tools/build_catalog.py --check         exit 1 when catalog.json is stale
    python tools/build_catalog.py --sha256 HEX    also set download.sha256 (tools/package.py)
    python tools/build_catalog.py --out PATH      write somewhere else (dist/catalog.json)

CPython 3.11, stdlib only. The schema is in dev/CHARTER.md ("catalog.json (schema 1)").
Inputs, all in this repo:

  Playground.extension/   bundles and their bundle.yaml (pyNavis' flat grammar, read with
                          dev/check.py's reader) and every container's layout: list
  status.yaml             the status ledger; a tool missing from it is 'untested'
  VERSION                 the release version, one line
  dev/CATALOG.md          '**#N Title**' lines give each tool its feature-list row
  dev/sources/*.json      what research agents found for each tool (may be absent)

How each derived field is found:

  feature   Every '**#N Title**' bullet in dev/CATALOG.md names its bundle in backticks
            (`Select_Similar.pushbutton`, `Select.panel/History.stack`) or, for a few
            pulldown members, only by title. The name is matched to a bundle folder under
            the panel of the enclosing '### X.panel' heading, or of a '## ... tab X' heading
            that names a single panel (the tab breaks ties). A row that names a stack or pulldown applies to each member
            without a row of its own.
  hooks     Static, no code runs. lib/namo/hooks.py's HANDLERS list maps each hk_* module
            to its events. A tool depends on an hk_* module when (a) the module is in the
            import closure of the tool's own .py files (ast imports of namo modules,
            followed transitively through lib/namo, imports inside functions included),
            (b) the tool's own files name the module ('hk_photopins'), or (c) the owner
            comment beside that HANDLERS row names the tool's title, or (d) the tool's own
            files import a module the handler serves (see subjects()). 'startup' is not an
            event file (startup.py is shared), so it never appears.
  siblings  The other leaf bundles in the same .stack folder.
  source    The first dev/sources entry with found: true for the tool, else null. 'via'
            defaults to 'page'. 'leads' merges every file's leads for the tool, as
            {'url', 'title'} objects (title '' when unknown), de-duplicated by url.

Output is stable: containers and tools in ribbon order (tab, then each container's
layout: list, unlisted children by name), keys sorted, two-space indent, final newline.
'generated' is today's date only when something else changed; otherwise the old date is
kept, so --check does not go stale at midnight.
"""
import ast
import datetime
import glob
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DEV = os.path.join(ROOT, 'dev')
EXT_NAME = 'Playground.extension'
EXT = os.path.join(ROOT, EXT_NAME)
LIB = os.path.join(EXT, 'lib', 'namo')
CATALOG = os.path.join(ROOT, 'catalog.json')
REPO = 'https://github.com/pynavis/Playground'
MIN_PYNAVIS = '1.3.0'
SHARED = ['extension.yaml', 'startup.py', 'lib/namo/**', 'hooks/*.py']

if DEV not in sys.path:
    sys.path.insert(0, DEV)
import check  # noqa: E402  (dev/check.py: the same flat yaml reader the static checks use)

CONTAINER_KINDS = ('tab', 'panel', 'stack', 'pulldown', 'splitbutton', 'splitpushbutton', 'slideout')
LEAF_KINDS = ('pushbutton', 'toggle', 'nobutton', 'smartbutton', 'dockpane', 'urlbutton', 'linkbutton')
JUNK_DIRS = ('__pycache__', '.pytest_cache')
JUNK_FILES = ('Thumbs.db', '.DS_Store', 'desktop.ini')
JUNK_SUFFIXES = ('.pyc', '.pyo', '.orig', '.bak', '.tmp')
# Shared namo infrastructure: never a reason on its own to tie a tool to a hook.
PLUMBING = {'session', 'paths', 'config', 'store', 'ui', 'progress', 'hooks', 'docdb'}
STATUSES = ('untested', 'launched', 'verified', 'known-issue')


class CatalogError(Exception):
    pass


# ---- small helpers ------------------------------------------------------------------------

def kind_of(name):
    """'pushbutton' for 'Select_Similar.pushbutton'; None for anything else."""
    if '.' not in name:
        return None
    suffix = name.rsplit('.', 1)[1].lower()
    return suffix if suffix in CONTAINER_KINDS + LEAF_KINDS else None


def stem(name):
    return check.stem(name)


def rel(path):
    return os.path.relpath(path, EXT).replace(os.sep, '/')


def is_junk(name):
    return name in JUNK_FILES or name.endswith(JUNK_SUFFIXES)


def files_in(folder, recursive):
    out = []
    if recursive:
        for dirpath, dirs, names in os.walk(folder):
            dirs[:] = sorted(d for d in dirs if d not in JUNK_DIRS)
            out.extend(rel(os.path.join(dirpath, n)) for n in names if not is_junk(n))
    else:
        out = [rel(os.path.join(folder, n)) for n in os.listdir(folder)
               if os.path.isfile(os.path.join(folder, n)) and not is_junk(n)]
    return sorted(out)


def read_bundle_yaml(folder):
    values, layout = check.read_yaml(os.path.join(folder, 'bundle.yaml'))
    return values, layout


def title_of(folder, values):
    title = values.get('title') or ''
    if not title:
        title = re.sub(r'^\d{2,}_', '', os.path.basename(folder).rsplit('.', 1)[0]).replace('_', ' ')
    return ' '.join(title.replace('\\n', ' ').split())


def ordered_children(folder, layout):
    """Child bundle folders in pyNavis order: layout entries first, the rest by name."""
    children = [n for n in os.listdir(folder)
                if os.path.isdir(os.path.join(folder, n)) and kind_of(n)]
    by_stem = {}
    for n in children:
        by_stem.setdefault(stem(n), n)
        by_stem.setdefault(n.lower(), n)
    out = []
    for entry in layout or []:
        name = by_stem.get(entry.lower()) or by_stem.get(stem(entry))
        if name and name not in out:
            out.append(name)
    out.extend(sorted((n for n in children if n not in out), key=lambda n: n.lower()))
    return [os.path.join(folder, n) for n in out]


def read_text(path):
    with io.open(path, encoding='utf-8-sig') as handle:
        return handle.read()


# ---- status ledger -------------------------------------------------------------------------

def read_status(path):
    """status.yaml: 'key:' lines at column 0, then indented 'field: value' lines."""
    ledger = {}
    if not os.path.exists(path):
        return ledger
    current = None
    for number, raw in enumerate(read_text(path).split('\n'), 1):
        line = raw.rstrip('\r')
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        if not line[0].isspace():
            if not line.rstrip().endswith(':'):
                raise CatalogError('status.yaml line %d: expected "<bundle key>:"' % number)
            current = line.rstrip()[:-1].strip().strip('"\'')
            ledger[current] = {}
            continue
        if current is None or ':' not in line:
            raise CatalogError('status.yaml line %d: expected "  field: value"' % number)
        key, value = line.split(':', 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in '"\'':
            value = value[1:-1]
        ledger[current][key.strip()] = value
    for key, entry in ledger.items():
        status = entry.get('status', '')
        if status not in STATUSES:
            raise CatalogError('status.yaml %s: unknown status %r' % (key, status))
        if entry.get('by', '') not in ('log', 'runner', 'person'):
            raise CatalogError('status.yaml %s: by must be log, runner or person' % key)
        if status == 'verified' and entry.get('by') != 'person':
            raise CatalogError('status.yaml %s: verified needs by: person' % key)
        if not re.match(r'^\d{4}-\d{2}-\d{2}$', entry.get('date', '')):
            raise CatalogError('status.yaml %s: date must be YYYY-MM-DD' % key)
    return ledger


# ---- feature numbers from dev/CATALOG.md --------------------------------------------------

FEATURE_LINE = re.compile(r'\*\*#(\d+)\s+([^*]+?)\*\*')
TAB_HEADING = re.compile(r'^##\s.*?\btab\s+(\w+)')
PANEL_HEADING = re.compile(r'^###\s+(\w+)\.panel(?:\s*\(tab\s+(\w+)\))?')
TICKED = re.compile(r'`([^`]+)`')


def read_features(path, bundles):
    """{bundle id: feature number}. bundles: every bundle id (leaves and containers)."""
    if not os.path.exists(path):
        return {}
    by_panel = {}
    for bundle_id in bundles:
        parts = bundle_id.split('/')
        if len(parts) >= 3:
            by_panel.setdefault(stem(parts[1]), []).append(bundle_id)
    direct = {}
    tab = panel = None
    for line in read_text(path).split('\n'):
        heading = TAB_HEADING.match(line)
        if heading:
            tab, panel = heading.group(1).lower(), None
            named = re.findall(r'`(\w+)\.panel`', line)
            if len(named) == 1:
                panel = named[0].lower()
            continue
        heading = PANEL_HEADING.match(line)
        if heading:
            panel = heading.group(1).lower()
            if heading.group(2):
                tab = heading.group(2).lower()
            continue
        match = FEATURE_LINE.search(line)
        if not match or panel is None:
            continue
        number, title = int(match.group(1)), match.group(2).strip()
        names = [t.split('/')[-1] for t in TICKED.findall(line) if kind_of(t.split('/')[-1])]
        name = stem(names[0]) if names else title.replace(' ', '_').lower()
        candidates = [b for b in by_panel.get(panel, []) if stem(b.split('/')[-1]) == name]
        if len(candidates) > 1 and tab:
            candidates = [b for b in candidates if stem(b.split('/')[0]) == tab] or candidates
        if len(candidates) == 1:
            direct.setdefault(candidates[0], number)
    result = {}
    for bundle_id in bundles:
        if bundle_id in direct:
            result[bundle_id] = direct[bundle_id]
    for bundle_id in bundles:
        if bundle_id in result:
            continue
        parts = bundle_id.split('/')
        for depth in range(len(parts) - 1, 0, -1):
            parent = '/'.join(parts[:depth])
            if parent in direct and kind_of(parts[depth - 1]) not in ('tab', 'panel'):
                result[bundle_id] = direct[parent]
                break
    return result


# ---- hooks ----------------------------------------------------------------------------------

def read_handlers(path):
    """[(event, module, owner title)] from lib/namo/hooks.py's HANDLERS list."""
    text = read_text(path)
    rows = []
    for line in text.split('\n'):
        match = re.match(r"\s*\('([\w-]+)',\s*'(hk_\w+)'\),?\s*(?:#\s*(.*?)\s*(?:\[.*)?)?$", line)
        if match:
            rows.append((match.group(1), match.group(2), (match.group(3) or '').strip()))
    tree = ast.parse(text)
    declared = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, 'id', None) == 'HANDLERS' for t in node.targets):
            declared = [tuple(e.value for e in item.elts) for item in node.value.elts]
    if declared is None or [(e, m) for e, m, _ in rows] != declared:
        raise CatalogError('lib/namo/hooks.py: HANDLERS rows could not be read line by line')
    return rows


def namo_imports(path):
    """Names of lib/namo modules a .py file imports anywhere (functions included)."""
    try:
        tree = ast.parse(read_text(path))
    except SyntaxError:
        return set()
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ''
            if node.level and os.path.dirname(path) == LIB:
                module = 'namo.' + module if module else 'namo'
            if module == 'namo':
                found.update(alias.name for alias in node.names)
            elif module.startswith('namo.'):
                found.add(module.split('.')[1])
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith('namo.'):
                    found.add(alias.name.split('.')[1])
    return set(n for n in found if os.path.exists(os.path.join(LIB, n + '.py')))


class ImportGraph(object):
    def __init__(self):
        self._direct = {}

    def direct(self, module):
        if module not in self._direct:
            self._direct[module] = namo_imports(os.path.join(LIB, module + '.py'))
        return self._direct[module]

    def closure(self, start):
        seen = set()
        todo = list(start)
        while todo:
            module = todo.pop()
            if module in seen:
                continue
            seen.add(module)
            todo.extend(self.direct(module) - seen)
        return seen


def hooks_for(folder, title, handlers, graph):
    own = [os.path.join(EXT, p) for p in files_in(folder, True) if p.endswith('.py')]
    start = set()
    text = ''
    for path in own:
        start |= namo_imports(path)
        text += read_text(path)
    closure = graph.closure(start)
    events = set()
    for event, module, owner in handlers:
        if event == 'startup':
            continue
        if (module in closure or re.search(r'\b%s\b' % module, text) or (owner and owner == title)
                or start & subjects(module, graph)):
            events.add(event)
    return sorted(events)


def subjects(module, graph):
    """The namo modules an hk_* handler exists to serve: its direct imports, shared plumbing
    (PLUMBING) left out, whose name shares its first six letters with the handler's or is a
    prefix of it either way (hk_macro serves macros, hk_selhistory serves sel_history,
    hk_transformpresets serves transforms). A tool is never tied to a hook just for using
    the same infrastructure."""
    key = module[3:].replace('_', '')
    out = set()
    for name in graph.direct(module) - PLUMBING:
        other = name.replace('_', '')
        if len(os.path.commonprefix([key, other])) >= 6 or key.startswith(other) or other.startswith(key):
            out.add(name)
    return out


# ---- sources ---------------------------------------------------------------------------------

def read_sources(folder):
    """({tool id: source object}, {tool id: [lead objects]}, [warnings])."""
    sources, leads, notes = {}, {}, []
    for path in sorted(glob.glob(os.path.join(folder, '*.json'))):
        try:
            data = json.loads(read_text(path))
        except ValueError as error:
            raise CatalogError('%s: not JSON (%s)' % (os.path.relpath(path, ROOT), error))
        tools = data.get('tools')
        if not isinstance(tools, dict):
            tools = dict((k, v) for k, v in data.items() if isinstance(v, dict) and '/' in k)
        for tool_id in sorted(tools):
            entry = tools[tool_id]
            if not isinstance(entry, dict) or not entry.get('found') or tool_id in sources:
                continue
            missing = [k for k in ('quote', 'url') if not entry.get(k)]
            if missing:
                notes.append('%s: %s found but has no %s' % (os.path.basename(path), tool_id, ' or '.join(missing)))
                continue
            sources[tool_id] = {'quote': entry['quote'], 'url': entry['url'],
                                'site': entry.get('site') or '', 'date': entry.get('date') or '',
                                'via': entry.get('via') or 'page'}
        for tool_id, items in sorted((data.get('leads') or {}).items()):
            bucket = leads.setdefault(tool_id, [])
            for item in items or []:
                if isinstance(item, dict):
                    lead = {'url': item.get('url') or '', 'title': item.get('title') or ''}
                else:
                    lead = {'url': str(item), 'title': ''}
                if not lead['url']:
                    continue
                known = [b for b in bucket if b['url'] == lead['url']]
                if known:
                    if not known[0]['title']:
                        known[0]['title'] = lead['title']
                else:
                    bucket.append(lead)
    return sources, leads, notes


def source_ids(folder):
    """Every tool id a dev/sources file names, under 'tools' or 'leads'."""
    named = set()
    for path in sorted(glob.glob(os.path.join(folder, '*.json'))):
        try:
            data = json.loads(read_text(path))
        except ValueError:
            continue  # read_sources reports it
        tools = data.get('tools')
        if not isinstance(tools, dict):
            tools = dict((k, v) for k, v in data.items() if isinstance(v, dict) and '/' in k)
        named.update(tools)
        named.update(data.get('leads') or {})
    return named


# ---- the walk ----------------------------------------------------------------------------------

def walk():
    """(containers, leaves): lists of dicts in ribbon order, before status/feature/source."""
    ext_values, ext_layout = check.read_yaml(os.path.join(EXT, 'extension.yaml'))
    containers, leaves = [], []

    def visit(folder, tab, panel, parent):
        name = os.path.basename(folder)
        kind = kind_of(name)
        values, layout = read_bundle_yaml(folder)
        title = title_of(folder, values)
        bundle_id = rel(folder)
        if kind in CONTAINER_KINDS:
            containers.append({'id': bundle_id, 'title': title, 'kind': kind,
                               'files': files_in(folder, False)})
            tab = title if kind == 'tab' else tab
            panel = title if kind == 'panel' else panel
            for child in ordered_children(folder, layout):
                visit(child, tab, panel, bundle_id)
        elif kind in LEAF_KINDS:
            leaves.append({'id': bundle_id, 'folder': folder, 'title': title, 'kind': kind,
                           'tab': tab, 'panel': panel, 'container': parent, 'values': values})

    for tab in ordered_children(EXT, ext_layout):
        if kind_of(os.path.basename(tab)) == 'tab':
            visit(tab, None, None, None)
    return ext_values, containers, leaves


def icon_of(folder, files):
    for name in ('icon.png', 'icon.off.png', 'icon.on.png'):
        path = rel(os.path.join(folder, name))
        if path in files:
            return path
    return None


def build(version, sha256, generated, sources_folder=None):
    """The catalog as a dict. Raises CatalogError on bad inputs."""
    ext_values, containers, leaves = walk()
    if ext_values.get('name') != 'Playground':
        raise CatalogError('extension.yaml: name must be Playground')
    for pattern in SHARED:
        base = pattern.split('*')[0].rstrip('/')
        if not os.path.exists(os.path.join(EXT, base)):
            raise CatalogError('shared path %s is missing' % pattern)
    ids = set(leaf['id'] for leaf in leaves)
    ledger = read_status(os.path.join(ROOT, 'status.yaml'))
    unknown = sorted(set(ledger) - ids)
    if unknown:
        raise CatalogError('status.yaml names bundles that do not exist: ' + ', '.join(unknown))
    features = read_features(os.path.join(DEV, 'CATALOG.md'), [c['id'] for c in containers] + sorted(ids))
    handlers = read_handlers(os.path.join(LIB, 'hooks.py'))
    sources_folder = sources_folder or os.path.join(DEV, 'sources')
    stale = sorted(set(source_ids(sources_folder)) - ids)
    if stale:
        raise CatalogError('dev/sources names bundles that do not exist: ' + ', '.join(stale))
    sources, leads, _ = read_sources(sources_folder)
    graph = ImportGraph()
    stacks = {}
    for leaf in leaves:
        if leaf['container'] and kind_of(leaf['container'].split('/')[-1]) == 'stack':
            stacks.setdefault(leaf['container'], []).append(leaf['id'])
    tools = []
    for leaf in leaves:
        values = leaf['values']
        files = files_in(leaf['folder'], True)
        entry = ledger.get(leaf['id'], {})
        tools.append({
            'id': leaf['id'],
            'title': leaf['title'],
            'kind': leaf['kind'],
            'tab': leaf['tab'],
            'panel': leaf['panel'],
            'container': leaf['container'],
            'summary': ' '.join((values.get('tooltip') or '').replace('\\n', ' ').split()),
            'status': entry.get('status', 'untested'),
            'status_note': entry.get('note', ''),
            'status_date': entry.get('date', ''),
            'status_by': entry.get('by', ''),
            'feature': features.get(leaf['id']),
            'shortcut': values.get('shortcut') or None,
            'context': values.get('context') or None,
            'hooks': hooks_for(leaf['folder'], leaf['title'], handlers, graph),
            'files': files,
            'icon': icon_of(leaf['folder'], files),
            'source': sources.get(leaf['id']),
            'leads': leads.get(leaf['id'], []),
            'siblings': [s for s in stacks.get(leaf['container'], []) if s != leaf['id']],
        })
    return {
        'schema': 1,
        'name': 'pyNavis Playground',
        'version': version,
        'generated': generated,
        'min_pynavis': MIN_PYNAVIS,
        'repo': REPO,
        'download': {'zip': '%s/releases/download/v%s/%s.zip' % (REPO, version, EXT_NAME),
                     'sha256': sha256},
        'extension': EXT_NAME,
        'shared': list(SHARED),
        'containers': containers,
        'tools': tools,
    }


def dumps(catalog):
    return json.dumps(catalog, indent=2, sort_keys=True, ensure_ascii=False) + '\n'


def read_version():
    version = read_text(os.path.join(ROOT, 'VERSION')).strip()
    if not re.match(r'^\d+\.\d+\.\d+$', version):
        raise CatalogError('VERSION must be MAJOR.MINOR.PATCH, not %r' % version)
    return version


def load(path):
    if not os.path.exists(path):
        return None
    try:
        return json.loads(read_text(path))
    except ValueError:
        return None


def without_generated(catalog):
    copy = dict(catalog)
    copy.pop('generated', None)
    return copy


def render(path=CATALOG, sha256=None, today=None):
    """(text, old text or None) for the catalog at path, keeping its date and sha256 when
    nothing else changed."""
    version = read_version()
    old = load(path)
    if sha256 is None:
        same_version = old and old.get('version') == version
        sha256 = (old or {}).get('download', {}).get('sha256', '') if same_version else ''
    today = today or datetime.date.today().isoformat()
    catalog = build(version, sha256.lower(), today)
    if old and without_generated(old) == without_generated(json.loads(dumps(catalog))):
        catalog['generated'] = old.get('generated', today)
    old_text = read_text(path) if os.path.exists(path) else None
    return dumps(catalog), old_text


def summary(catalog):
    kinds, statuses = {}, {}
    for tool in catalog['tools']:
        kinds[tool['kind']] = kinds.get(tool['kind'], 0) + 1
        statuses[tool['status']] = statuses.get(tool['status'], 0) + 1
    fmt = lambda d: ', '.join('%s %d' % (k, d[k]) for k in sorted(d))
    sourced = sum(1 for t in catalog['tools'] if t['source'])
    with_leads = sum(1 for t in catalog['tools'] if t['leads'])
    return ('%d tools (%s); status: %s; %d containers; %d with a source, %d with leads'
            % (len(catalog['tools']), fmt(kinds), fmt(statuses), len(catalog['containers']),
               sourced, with_leads))


def main(argv):
    out = CATALOG
    if '--out' in argv:
        out = os.path.abspath(argv[argv.index('--out') + 1])
    sha256 = None
    if '--sha256' in argv:
        sha256 = argv[argv.index('--sha256') + 1]
        if not re.match(r'^[0-9a-fA-F]{64}$', sha256):
            sys.stderr.write('--sha256 needs 64 hex digits\n')
            return 2
    try:
        text, old_text = render(out, sha256)
    except CatalogError as error:
        sys.stderr.write('build_catalog: %s\n' % error)
        return 1
    _, _, notes = read_sources(os.path.join(DEV, 'sources'))
    for note in notes:
        sys.stderr.write('build_catalog: note: %s\n' % note)
    if '--check' in argv:
        if text != old_text:
            sys.stderr.write('build_catalog: %s is stale; run python tools/build_catalog.py\n'
                             % os.path.relpath(out, ROOT))
            return 1
        print('build_catalog: %s is current: %s' % (os.path.relpath(out, ROOT), summary(json.loads(text))))
        return 0
    if text != old_text:
        folder = os.path.dirname(out)
        if folder and not os.path.isdir(folder):
            os.makedirs(folder)
        with io.open(out, 'w', encoding='utf-8', newline='\n') as handle:
            handle.write(text)
    print('build_catalog: wrote %s: %s' % (os.path.relpath(out, ROOT), summary(json.loads(text))))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
