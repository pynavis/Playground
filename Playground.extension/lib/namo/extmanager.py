# -*- coding: utf-8 -*-
"""Extension Manager: install, update and remove pyNavis extensions from a registry.

The registry is a JSON file (a URL or a file path, set with Shift+Click) listing
extensions: {"extensions": [{"name", "description", "author", "version", "homepage",
"download" (a zip URL, a file path, or a path relative to the registry file),
"sha256" (optional)}]}. Default: <team_root>\\playground-team\\extension-registry.json or
<team_root>\\extension-registry.json when one exists, else a placeholder URL that fails
with a sentence saying how to set one.

Install downloads the zip (TLS 1.2, counted progress, Cancel works), checks the SHA-256
when the registry gives one, finds the *.extension folder inside (at the top, in a
single top folder like a GitHub zip, or loose tabs), extracts it with every path checked
(no entry may land outside the target), and swaps it into
%APPDATA%\\pyNavis\\extensions\\<name>.extension; an older copy goes to
%APPDATA%\\pyNavis\\playground\\trash\\<stamp> <name>.extension first. .playground-install.json inside
records what was installed. Uninstall moves the folder to the same trash. pyNavis and
Playground themselves are never touched. Reload happens once, when the window closes.

Pure half: parse_registry, compare_versions, status_rows, zip_root, safe_target,
resolve_download, PROTECTED. Files: extract_zip, scan_installed, install_zip,
uninstall. Network: download (WebRequest), load_registry.
"""
import datetime
import hashlib
import io
import json
import os
import re
import shutil
import zipfile

from namo import buttonmaker, hotkeys, paths, session, ui

PROTECTED = ('pynavis', 'playground')
MANIFEST = '.playground-install.json'
PLACEHOLDER = 'https://example.invalid/playground/extension-registry.json'
REGISTRY_NAMES = (os.path.join('playground-team', 'extension-registry.json'), 'extension-registry.json')
_NAME = re.compile(r'^[A-Za-z0-9][A-Za-z0-9 _.\-]{0,63}$')

# ---- pure --------------------------------------------------------------------------------


def parse_registry(data):
    """([entry], [problem]) from a registry body (a dict with 'extensions' or a list)."""
    items = data.get('extensions') if isinstance(data, dict) else data
    if not isinstance(items, list):
        return [], ['The registry has no "extensions" list.']
    entries = []
    problems = []
    seen = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            problems.append('Entry %d is not an object.' % (index + 1))
            continue
        name = str(item.get('name') or '').strip()
        if name.lower().endswith('.extension'):
            name = name[:-len('.extension')]
        if not _NAME.match(name) or '..' in name:
            problems.append('Entry %d has no usable name.' % (index + 1))
            continue
        if name.lower() in seen:
            problems.append('%s is listed twice; the first entry is used.' % name)
            continue
        download = str(item.get('download') or '').strip()
        if not download:
            problems.append('%s has no download.' % name)
            continue
        sha = str(item.get('sha256') or '').strip().lower()
        if sha and not re.match(r'^[0-9a-f]{64}$', sha):
            problems.append('%s has a sha256 that is not 64 hex digits; it will not be checked.' % name)
            sha = ''
        seen.add(name.lower())
        entries.append({'name': name, 'description': str(item.get('description') or ''),
                        'author': str(item.get('author') or ''), 'version': str(item.get('version') or ''),
                        'homepage': str(item.get('homepage') or ''), 'download': download, 'sha256': sha})
    entries.sort(key=lambda e: e['name'].lower())
    return entries, problems


def _version_key(text):
    text = re.sub(r'^[vV](?=\d)', '', str(text or '').strip())
    parts = re.findall(r'\d+|[A-Za-z]+', text)
    numbers = []
    suffix = ()
    for index, part in enumerate(parts):
        if part.isdigit():
            numbers.append(int(part))
        else:
            suffix = tuple(p.lower() for p in parts[index:])
            break
    while numbers and numbers[-1] == 0:
        numbers.pop()
    # A release (no suffix) sorts after any pre-release of the same numbers.
    return (tuple(numbers), 0 if suffix else 1, suffix)


def compare_versions(a, b):
    """-1, 0 or 1: '1.10' > '1.9', '2.0' == '2', '1.2.0-beta' < '1.2.0'."""
    ka, kb = _version_key(a), _version_key(b)
    return (ka > kb) - (ka < kb)


def is_protected(name):
    return (name or '').strip().lower().replace('.extension', '') in PROTECTED


def status_of(entry, installed):
    if installed is None:
        return 'Not installed'
    if is_protected(entry['name']):
        return 'Managed by its installer'
    if entry.get('version') and installed.get('version') and \
            compare_versions(entry['version'], installed['version']) > 0:
        return 'Update available'
    return 'Installed'


def status_rows(entries, installed):
    """Table rows (value: name): Extension, Available, Installed, Status, Author, About;
    registry entries first, then installed extensions the registry does not list."""
    by_name = dict((i['name'].lower(), i) for i in installed)
    rows = []
    listed = set()
    for entry in entries:
        found = by_name.get(entry['name'].lower())
        listed.add(entry['name'].lower())
        rows.append({'value': entry['name'], 'cells': [
            entry['name'], entry.get('version') or '', (found or {}).get('version') or ('yes' if found else ''),
            status_of(entry, found), entry.get('author') or '', entry.get('description') or '']})
    for item in sorted(installed, key=lambda i: i['name'].lower()):
        if item['name'].lower() in listed:
            continue
        status = 'Managed by its installer' if is_protected(item['name']) else 'Not in the registry'
        rows.append({'value': item['name'], 'cells': [item['name'], '', item.get('version') or 'yes',
                                                      status, '', item['folder']]})
    return rows


def resolve_download(download, registry_location):
    """An absolute URL or path for a download given next to a registry."""
    if re.match(r'^(https?|file)://', download, re.IGNORECASE) or os.path.isabs(download) or \
            download.startswith('\\\\'):
        return download
    if re.match(r'^https?://', registry_location or '', re.IGNORECASE):
        base = registry_location.rsplit('/', 1)[0]
        return '%s/%s' % (base, download.replace('\\', '/').lstrip('/'))
    folder = os.path.dirname(registry_location or '')
    return os.path.normpath(os.path.join(folder, download))


def zip_root(names, wanted=None):
    """(prefix, folder name) of the extension inside a zip: the prefix every member of
    the extension starts with, and the *.extension folder to create. Raises ValueError
    with a sentence when the zip holds none, or several."""
    names = [n.replace('\\', '/') for n in names]
    roots = set()
    for name in names:
        parts = name.split('/')
        for index, part in enumerate(parts[:-1]):
            if part.lower().endswith('.extension'):
                roots.add('/'.join(parts[:index + 1]) + '/')
                break
    if len(roots) > 1:
        if wanted:
            for root in roots:
                if root.rstrip('/').split('/')[-1].lower() == wanted.lower() + '.extension':
                    return root, root.rstrip('/').split('/')[-1]
        raise ValueError('That zip holds %d extensions; the registry must point at one.' % len(roots))
    if roots:
        root = roots.pop()
        return root, root.rstrip('/').split('/')[-1]
    if not wanted:
        raise ValueError('That zip holds no pyNavis extension.')
    tops = set(n.split('/')[0] for n in names if '/' in n)
    loose_tabs = [n for n in names if n.split('/')[0].lower().endswith('.tab')]
    if loose_tabs:
        return '', wanted + '.extension'
    if len(tops) == 1:
        top = tops.pop()
        if any(n.split('/')[1].lower().endswith('.tab') for n in names if n.startswith(top + '/') and n.count('/') >= 2):
            return top + '/', wanted + '.extension'
    raise ValueError('That zip holds no pyNavis extension (no *.extension or *.tab folder).')


def safe_target(dest, relative):
    """The full path for a zip member below dest, or None when it would escape dest."""
    rel = relative.replace('\\', '/')
    if not rel or rel.startswith('/') or re.match(r'^[A-Za-z]:', rel):
        return None
    parts = [p for p in rel.split('/') if p not in ('', '.')]
    if any(p == '..' for p in parts):
        return None
    target = os.path.normpath(os.path.join(dest, *parts))
    base = os.path.normpath(dest)
    if os.path.normcase(target) != os.path.normcase(base) and \
            not os.path.normcase(target).startswith(os.path.normcase(base) + os.sep):
        return None
    return target


def file_url_path(location):
    """The local path a file: URL names ('file:///C:/x/a.zip' -> 'C:\\x\\a.zip',
    'file://server/share/a.zip' -> '\\\\server\\share\\a.zip'); other text unchanged."""
    if not (location or '').lower().startswith('file:'):
        return location
    try:
        from urllib.parse import unquote
        rest = unquote(location[5:])
    except Exception:
        rest = location[5:]
    if rest.startswith('///'):
        rest = rest[3:]
    elif rest.startswith('//'):
        rest = rest[2:]
        if not re.match(r'^[A-Za-z]:', rest):
            return '\\\\' + rest.replace('/', '\\')
    elif rest.startswith('/'):
        rest = rest[1:]
    return rest.replace('/', '\\')


def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        while True:
            block = handle.read(1 << 16)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


# ---- files ----------------------------------------------------------------------------------


def extract_zip(zip_path, dest, wanted=None, progress=None):
    """Extracts the extension inside zip_path into dest (created). Returns (folder name,
    files written). ValueError for a zip that holds no extension or an unsafe path."""
    with zipfile.ZipFile(zip_path) as archive:
        names = archive.namelist()
        prefix, folder = zip_root(names, wanted)
        members = [n for n in names if n.replace('\\', '/').startswith(prefix) and not n.endswith('/')]
        if not members:
            raise ValueError('The extension folder in that zip is empty.')
        written = 0
        for index, member in enumerate(members):
            relative = member.replace('\\', '/')[len(prefix):]
            target = safe_target(dest, relative)
            if target is None:
                raise ValueError('The zip has an unsafe path: %s' % member)
            paths.ensure_dir(os.path.dirname(target))
            with archive.open(member) as source:
                with open(target, 'wb') as out:
                    shutil.copyfileobj(source, out)
            written += 1
            if progress is not None and index % 20 == 0:
                progress(float(index) / len(members), 'Extracting %d of %d files' % (index, len(members)))
    return folder, written


def _yaml_name(folder):
    path = os.path.join(folder, 'extension.yaml')
    if not os.path.exists(path):
        return None
    with io.open(path, encoding='utf-8-sig') as handle:
        values, _layout = buttonmaker.read_flat_yaml(handle.read())
    return values.get('name')


def scan_installed(roots):
    """[{'name', 'folder', 'version', 'source', 'root'}] for every *.extension directly in
    the roots (pyNavis' own discovery rule)."""
    out = []
    for root in roots:
        if not root or not os.path.isdir(root):
            continue
        for name in sorted(os.listdir(root)):
            folder = os.path.join(root, name)
            if not name.lower().endswith('.extension') or not os.path.isdir(folder):
                continue
            manifest = paths.load_json(os.path.join(folder, MANIFEST), {}, move_aside=False)
            manifest = manifest if isinstance(manifest, dict) else {}
            out.append({'name': name[:-len('.extension')], 'folder': folder, 'root': root,
                        'version': str(manifest.get('version') or ''),
                        'source': str(manifest.get('source') or ''),
                        'yaml_name': _yaml_name(folder) or name[:-len('.extension')]})
    return out


def install_zip(zip_path, entry, root, trash_root, now=None, progress=None):
    """Swaps the zip's extension into root\\<name>.extension. Returns the folder.
    The old copy (if any) goes to trash_root first; a failed extract leaves it in place."""
    name = entry['name']
    if is_protected(name):
        raise ValueError('%s is installed by its own installer, not here.' % name)
    stamp = (now or datetime.datetime.now()).strftime('%Y%m%d-%H%M%S')
    paths.ensure_dir(root)
    staging = os.path.join(root, '.%s.installing-%s' % (name, stamp))
    if os.path.exists(staging):
        shutil.rmtree(staging, ignore_errors=True)
    try:
        extract_zip(zip_path, staging, name, progress)
        target = os.path.join(root, name + '.extension')
        if os.path.exists(target):
            hotkeys.trash(target, trash_root)
        os.rename(staging, target)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    paths.write_json(os.path.join(target, MANIFEST), {
        'name': name, 'version': entry.get('version') or '', 'source': entry.get('download') or '',
        'sha256': entry.get('sha256') or '', 'installed': stamp})
    return target


def uninstall(folder, trash_root):
    name = os.path.basename(folder)
    if is_protected(name):
        raise ValueError('%s is removed with its own uninstaller.' % name[:-len('.extension')])
    return hotkeys.trash(folder, trash_root)


def default_registry(team_root):
    for name in REGISTRY_NAMES:
        candidate = os.path.join(team_root, name)
        if os.path.isfile(candidate):
            return candidate
    return PLACEHOLDER


# ---- network ----------------------------------------------------------------------------------


def _is_url(location):
    return bool(re.match(r'^https?://', location or '', re.IGNORECASE))


def _web_request(url):
    from System.Net import SecurityProtocolType, ServicePointManager, WebRequest
    try:
        ServicePointManager.SecurityProtocol = ServicePointManager.SecurityProtocol | SecurityProtocolType.Tls12
    except Exception:
        pass
    request = WebRequest.Create(url)
    request.Timeout = 30000
    try:
        # An office proxy that signs people in with their Windows account.
        from System.Net import CredentialCache
        if request.Proxy is not None:
            request.Proxy.Credentials = CredentialCache.DefaultCredentials
    except Exception:
        pass
    try:
        request.UserAgent = 'Playground Extension Manager'
    except Exception:
        pass
    return request


def download(location, target, progress=None):
    """Copies a URL (http/https) or a file to target, reporting progress(fraction, label).
    Raises IOError with a sentence on failure."""
    paths.ensure_dir(os.path.dirname(target))
    if not _is_url(location):
        source = file_url_path(location)
        if not os.path.isfile(source):
            raise IOError('The file %s does not exist.' % source)
        shutil.copy2(source, target)
        return target
    from System import Array, Byte
    from System.IO import File, FileMode
    try:
        response = _web_request(location).GetResponse()
    except Exception as error:
        raise IOError('Could not download %s: %s' % (location, error))
    total = int(response.ContentLength)
    stream = response.GetResponseStream()
    out = File.Open(target, FileMode.Create)
    try:
        buffer = Array.CreateInstance(Byte, 65536)
        done = 0
        while True:
            count = stream.Read(buffer, 0, buffer.Length)
            if count <= 0:
                break
            out.Write(buffer, 0, count)
            done += count
            if progress is not None:
                fraction = float(done) / total if total > 0 else 0.0
                progress(fraction, 'Downloaded %s of %s KB' % ('{:,}'.format(done // 1024),
                                                             '{:,}'.format(total // 1024) if total > 0 else '?'))
    finally:
        out.Close()
        stream.Close()
        response.Close()
    return target


def load_registry(location):
    """(entries, problems) from a registry URL or file. IOError with a sentence when it
    cannot be read."""
    if _is_url(location):
        from System.IO import StreamReader
        try:
            response = _web_request(location).GetResponse()
            reader = StreamReader(response.GetResponseStream())
            try:
                text = reader.ReadToEnd()
            finally:
                reader.Close()
                response.Close()
        except Exception as error:
            raise IOError('Could not read the registry at %s: %s' % (location, error))
    else:
        if not os.path.isfile(location):
            raise IOError('The registry file %s does not exist.' % location)
        text = paths.read_text(location, '')
    try:
        data = json.loads(text)
    except ValueError:
        raise IOError('The registry at %s is not valid JSON.' % location)
    return parse_registry(data)


# ---- the window --------------------------------------------------------------------------------


def _toast(level, message, detail=None):
    try:
        from pynavis import toast
        toast.show(level, message, detail)
    except Exception:
        session.log('info', '%s %s' % (message, detail or ''))


def status_text(entries, problems, notice=None, changed=0):
    """The window's status line. notice: why there is no registry to show (not set,
    unreachable); problems: registry entries that were skipped."""
    if notice:
        text = notice
    else:
        text = '%d extension%s in the registry' % (len(entries), '' if len(entries) == 1 else 's')
        if problems:
            text += '; %d entr%s skipped: %s' % (len(problems), 'y' if len(problems) == 1 else 'ies', problems[0])
    if changed:
        text = text.rstrip('.') + '; pyNavis reloads when you close this window'
    return text


def run_window(location, entries, problems, user_root, roots, trash_root, temp_folder, notice=None):
    """The modal manager. Returns how many extensions changed (the caller reloads).
    notice: a sentence shown in place of the registry count when no registry was read."""
    from namo import progress as namo_progress
    state = {'changed': 0}

    def installed():
        return scan_installed(roots)

    def rows():
        return status_rows(entries, installed())

    def status_line():
        return status_text(entries, problems, notice, state['changed'])

    def entry_named(name):
        for entry in entries:
            if entry['name'].lower() == name.lower():
                return entry
        return None

    def installed_named(name):
        for item in installed():
            if item['name'].lower() == name.lower():
                return item
        return None

    def install(values, update=False):
        from pynavis import forms
        for name in values:
            entry = entry_named(name)
            if entry is None:
                _toast('info', '%s is not in the registry' % name, 'Only listed extensions can be installed.')
                continue
            if is_protected(name):
                _toast('info', '%s is managed by its installer' % name, 'Use its own setup to update it.')
                continue
            current = installed_named(name)
            if current is not None and not update:
                if not forms.confirm('%s is already installed. Install it again over the current copy?' % name,
                                     title='Extension Manager'):
                    continue
            if current is not None and os.path.normcase(current['root']) != os.path.normcase(user_root):
                _toast('warning', '%s is installed in %s' % (name, current['root']),
                       'Only extensions in your own extensions folder can be replaced here.')
                continue
            url = resolve_download(entry['download'], location)
            zip_path = os.path.join(temp_folder, '%s.zip' % paths.safe_filename(name))

            def work(report, url=url, zip_path=zip_path, entry=entry):
                download(url, zip_path, lambda f, label: report(0.8 * f, label))
                if entry.get('sha256') and sha256_of(zip_path) != entry['sha256']:
                    raise IOError('The download does not match the registry checksum; nothing was installed.')
                return install_zip(zip_path, entry, user_root, trash_root,
                                   progress=lambda f, label: report(0.8 + 0.2 * f, label))
            try:
                outcome = namo_progress.run('Installing %s' % name, work, 'Downloading')
            except (IOError, OSError, ValueError, zipfile.BadZipfile) as error:
                _toast('error', 'Could not install %s' % name, str(error))
                continue
            finally:
                if os.path.exists(zip_path):
                    try:
                        os.remove(zip_path)
                    except OSError:
                        pass
            if outcome is namo_progress.CANCELLED:
                continue
            state['changed'] += 1
            _toast('success', '%s %s' % ('Updated' if current else 'Installed', name),
                   'Version %s. pyNavis reloads when you close the window.' % (entry.get('version') or '?'))

    def do_uninstall(values):
        from pynavis import forms
        for name in values:
            item = installed_named(name)
            if item is None:
                continue
            if is_protected(name):
                _toast('info', '%s is managed by its installer' % name, 'Remove it with its own uninstaller.')
                continue
            if os.path.normcase(item['root']) != os.path.normcase(user_root):
                _toast('warning', '%s is not in your extensions folder' % name,
                       'Remove %s from config.json to stop loading it.' % item['root'])
                continue
            if not forms.confirm('Remove %s? It moves to the Playground trash folder, so it can be restored.' % name,
                                 title='Extension Manager'):
                continue
            try:
                uninstall(item['folder'], trash_root)
            except (IOError, OSError, ValueError) as error:
                _toast('error', 'Could not remove %s' % name,
                       'A file in it is in use. Close what has it open, then try again. %s' % error)
                continue
            state['changed'] += 1
            _toast('success', 'Removed %s' % name, 'Moved to %s' % trash_root)
        holder['win'].Tag.update(rows(), status_line())

    def do_open(values):
        for name in values[:1]:
            item = installed_named(name)
            if item is not None:
                ui.show_in_explorer(item['folder'])
            else:
                _toast('info', '%s is not installed' % name)

    def do_homepage(values):
        for name in values[:1]:
            entry = entry_named(name)
            if entry and entry.get('homepage'):
                from namo import ribbon
                ribbon.open_url(entry['homepage'])
            else:
                _toast('info', '%s has no homepage in the registry' % name)

    holder = {}

    # Install and Update download behind a progress window. pyNavis' progress window
    # re-enables the Navisworks main window when it closes, which under this MODAL list
    # would leave Navisworks live behind it. So they close the list, install, and the list
    # comes back with the new state (ui.modal_loop).
    def build(defer):
        actions = [{'label': 'Install', 'fn': lambda v: defer(lambda: install(list(v))), 'primary': True},
                   {'label': 'Update', 'fn': lambda v: defer(lambda: install(list(v), update=True))},
                   {'label': 'Remove', 'fn': do_uninstall},
                   {'label': 'Open folder', 'fn': do_open},
                   {'label': 'Homepage', 'fn': do_homepage}]
        holder['win'] = ui.build_table(
            'Extension Manager', ['Extension', 'Available', 'Installed', 'Status', 'Author', 'About'],
            rows(), actions, status=status_line(), width=980, height=560)
        return holder['win']
    ui.modal_loop(build)
    return state['changed']
