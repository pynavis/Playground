# -*- coding: utf-8 -*-
"""Team Sync: share Playground settings through a team folder (a UNC share or a synced or
cloned folder) laid out as <team folder>\\playground-team\\:

    config.json        project name and number, company, trades, trade rules, report
                       units, date format (the team part of Playground Settings)
    templates\\*.json   namo.templates files (report templates, macros, ...)
    presets\\ libraries\\ rules\\   any files, copied as they are
    shortcuts.json     {bundle key: chord or null}: pyNavis bindings for the team
    extensions.json    ["\\\\server\\tools\\extensions", ...]: extension roots to load
    version.json       {"stamp", "by"}: written by every Push

Pull compares the team folder with what this machine pulled last time and shows the
difference per area (added, changed, removed), then copies into the local data root
(%APPDATA%\\pyNavis\\playground), backing up every file it replaces or removes under
<data_root>\\backups\\team-sync <stamp>\\. Files the user made locally and never pulled
are left alone. config.json is merged into Playground Settings (only the team keys),
shortcuts.json into pyNavis' config.json bindings (only the keys it names), and
extensions.json adds missing roots to config.json "extensions".
Push (for whoever manages the team setup) writes the local content into the team folder
and a new version stamp. hk_teamsync: with "Pull at startup" on, a worker thread reads
the team stamp (never blocking Navisworks on a slow share); when it changed, the pull
runs on the UI thread once no pyNavis script is running (it rewrites config.json, which
pyNavis itself writes from the UI thread right after startup).

Pure half: AREAS, manifest(), diff(), plan_pull(), summary_lines(), merge_config(),
merge_shortcuts(), merge_roots(), needs_pull(). Files: pull(), push(); state in
<data_root>\\team-sync.json.
"""
import collections
import datetime
import hashlib
import io
import json
import os
import shutil

from namo import config as namo_config
from namo import hotkeys, paths, ribbon, session

TEAM_DIR = 'playground-team'
STATE_FILE = 'team-sync.json'
# (area, team path, kind): 'tree' copies files, 'merge' is read and merged.
AREAS = [('config', 'config.json', 'merge'), ('templates', 'templates', 'tree'),
         ('presets', 'presets', 'tree'), ('libraries', 'libraries', 'tree'),
         ('rules', 'rules', 'tree'), ('shortcuts', 'shortcuts.json', 'merge'),
         ('extensions', 'extensions.json', 'merge')]
AREA_LABELS = {'config': 'Project settings', 'templates': 'Templates', 'presets': 'Presets',
               'libraries': 'Libraries', 'rules': 'Rules', 'shortcuts': 'Shortcuts',
               'extensions': 'Extension folders'}
TEAM_CONFIG_KEYS = ('project_name', 'project_number', 'company', 'trades', 'trade_rules',
                    'report_units', 'date_format')
STATE_DEFAULTS = {'team_folder': '', 'auto_pull': False, 'stamp': '', 'pulled': {},
                  'last_pull': '', 'last_push': ''}

# ---- pure -------------------------------------------------------------------------------


def area_of(rel):
    """The area a team-relative path belongs to, or None."""
    head = rel.split('/', 1)[0]
    for area, team_path, _kind in AREAS:
        if head.lower() == team_path.lower():
            return area
    return None


def sha1_of(path):
    digest = hashlib.sha1()
    with open(path, 'rb') as handle:
        while True:
            block = handle.read(65536)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def manifest(folder):
    """{team-relative path with '/': sha1} of every file the areas cover under folder."""
    out = {}
    if not folder or not os.path.isdir(folder):
        return out
    for area, team_path, kind in AREAS:
        target = os.path.join(folder, team_path)
        if kind == 'merge':
            if os.path.isfile(target):
                out[team_path] = sha1_of(target)
            continue
        if not os.path.isdir(target):
            continue
        for current, dirs, files in os.walk(target):
            dirs[:] = sorted(d for d in dirs if not d.startswith('.'))
            for name in sorted(files):
                if name.startswith('.') or name.endswith('.lock') or '.corrupt-' in name:
                    continue
                full = os.path.join(current, name)
                rel = os.path.relpath(full, folder).replace('\\', '/')
                out[rel] = sha1_of(full)
    return out


def local_path(data_root, rel):
    """Where a tree file lands on this machine."""
    return os.path.join(data_root, *rel.split('/'))


def diff(team, local, pulled):
    """{area: {'added', 'changed', 'removed'}} for a Pull.

    team / local: manifests; pulled: {rel: sha1} recorded at the last pull. added = on
    the team, not here; changed = here but different (merge areas: different from what
    was last pulled); removed = pulled before, gone from the team now, still here."""
    out = collections.OrderedDict()
    for area, _team_path, _kind in AREAS:
        out[area] = {'added': [], 'changed': [], 'removed': []}
    for rel in sorted(team):
        area = area_of(rel)
        if area is None:
            continue
        kind = [k for a, _p, k in AREAS if a == area][0]
        if kind == 'merge':
            if pulled.get(rel) is None:
                out[area]['added'].append(rel)
            elif pulled.get(rel) != team[rel]:
                out[area]['changed'].append(rel)
            continue
        if rel not in local:
            out[area]['added'].append(rel)
        elif local[rel] != team[rel]:
            out[area]['changed'].append(rel)
    for rel in sorted(pulled):
        area = area_of(rel)
        if area is None or rel in team:
            continue
        kind = [k for a, _p, k in AREAS if a == area][0]
        if kind == 'tree' and rel in local:
            out[area]['removed'].append(rel)
    return out


def count(changes):
    return sum(len(v['added']) + len(v['changed']) + len(v['removed']) for v in changes.values())


def summary_lines(changes):
    """['Templates: 2 added, 1 changed', ...] for the areas with differences."""
    lines = []
    for area in changes:
        parts = []
        for word in ('added', 'changed', 'removed'):
            n = len(changes[area][word])
            if n:
                parts.append('%d %s' % (n, word))
        if parts:
            lines.append('%s: %s' % (AREA_LABELS[area], ', '.join(parts)))
    return lines


def merge_config(current, team):
    """(values to save, changed keys): only the team keys, normalised by namo.config."""
    values = {}
    changed = []
    if not isinstance(team, dict):
        return values, changed
    for key in TEAM_CONFIG_KEYS:
        if key in team and team[key] != current.get(key):
            values[key] = team[key]
            changed.append(key)
    return values, changed


def merge_shortcuts(root, team):
    """config.json root with the team's bindings written over the same keys (others
    kept). Returns the number of keys written. team: {key: chord or None}."""
    if not isinstance(team, dict):
        return 0
    shortcuts = root.get('shortcuts')
    if not isinstance(shortcuts, dict):
        shortcuts = collections.OrderedDict()
        root['shortcuts'] = shortcuts
    bindings = shortcuts.get('bindings')
    if not isinstance(bindings, dict):
        bindings = collections.OrderedDict()
        shortcuts['bindings'] = bindings
    written = 0
    for key in sorted(team):
        value = team[key]
        if value is not None and not isinstance(value, str):
            continue
        for raw in list(bindings):
            if ribbon.same_key(raw, key):
                del bindings[raw]
        bindings[ribbon.normalize_key(key)] = value
        written += 1
    if not bindings:
        del shortcuts['bindings']
    if not shortcuts:
        del root['shortcuts']
    return written


def merge_roots(root, team_roots):
    """Adds the team's extension roots to config.json "extensions" (case-insensitive,
    order kept, never removing). Returns how many were added."""
    if not isinstance(team_roots, list):
        return 0
    current = root.get('extensions')
    if not isinstance(current, list):
        current = []
    known = set(str(r).strip().rstrip('\\/').lower() for r in current if isinstance(r, str))
    added = 0
    for item in team_roots:
        if not isinstance(item, str) or not item.strip():
            continue
        norm = item.strip().rstrip('\\/').lower()
        if norm in known:
            continue
        current.append(item.strip())
        known.add(norm)
        added += 1
    if added:
        root['extensions'] = current
    return added


def needs_pull(team_stamp, local_stamp):
    return bool(team_stamp) and team_stamp != local_stamp


def new_stamp(now=None):
    return (now or datetime.datetime.now()).strftime('%Y-%m-%dT%H:%M:%S')


# ---- state --------------------------------------------------------------------------------


def state_path(data_root=None):
    return os.path.join(data_root or paths.data_root(), STATE_FILE)


def load_state(data_root=None):
    stored = paths.load_json(state_path(data_root), {})
    out = dict(STATE_DEFAULTS)
    out['pulled'] = {}
    if isinstance(stored, dict):
        for key in STATE_DEFAULTS:
            if key in stored:
                out[key] = stored[key]
    if not isinstance(out['pulled'], dict):
        out['pulled'] = {}
    out['auto_pull'] = bool(out['auto_pull'])
    return out


def save_state(state, data_root=None):
    paths.write_json(state_path(data_root), state)
    return state


def team_folder(state):
    """The configured team folder, else Playground's shared folder; '' when neither is set."""
    folder = (state.get('team_folder') or '').strip()
    if folder:
        return folder
    try:
        return (namo_config.get('shared_root') or '').strip()
    except Exception:
        return ''


def team_dir(folder):
    return os.path.join(folder, TEAM_DIR)


def read_stamp(team):
    data = paths.load_json(os.path.join(team, 'version.json'), {}, move_aside=False)
    return str(data.get('stamp') or '') if isinstance(data, dict) else ''


# ---- pull -----------------------------------------------------------------------------------


def preview(folder, data_root=None):
    """{'team', 'changes', 'count', 'lines', 'stamp', 'error'} without changing anything."""
    data_root = data_root or paths.data_root()
    team = team_dir(folder)
    if not folder:
        return {'error': 'Set the team folder first.'}
    if not os.path.isdir(folder):
        return {'error': '%s cannot be reached right now. Check the network or the drive, '
                         'or pick another folder with Change folder.' % folder,
                'unreachable': True}
    if not os.path.isdir(team):
        return {'error': 'There is no %s folder in %s. Push from the machine that holds the '
                         'team setup first.' % (TEAM_DIR, folder)}
    state = load_state(data_root)
    team_files = manifest(team)
    local = manifest(data_root)
    changes = diff(team_files, local, state.get('pulled') or {})
    return {'team': team, 'changes': changes, 'count': count(changes),
            'lines': summary_lines(changes), 'stamp': read_stamp(team), 'error': None,
            'manifest': team_files}


def _backup(path, backup_root, rel):
    target = os.path.join(backup_root, *rel.split('/'))
    paths.ensure_dir(os.path.dirname(target))
    shutil.copy2(path, target)


def pull(folder, data_root=None, config_path=None, now=None):
    """Applies a Pull. Returns {'copied', 'removed', 'config', 'shortcuts', 'roots',
    'backup', 'lines', 'needs_reload'}. Raises IOError for files it cannot write."""
    data_root = data_root or paths.data_root()
    found = preview(folder, data_root)
    if found.get('error'):
        raise IOError(found['error'])
    team = found['team']
    changes = found['changes']
    stamp = new_stamp(now)
    backup_root = os.path.join(data_root, 'backups', 'team-sync %s' % stamp.replace(':', ''))
    result = {'copied': 0, 'removed': 0, 'config': [], 'shortcuts': 0, 'roots': 0,
              'backup': None, 'lines': found['lines'], 'needs_reload': False}
    state = load_state(data_root)
    pulled = dict(state.get('pulled') or {})
    for area, _team_path, kind in AREAS:
        bucket = changes[area]
        if kind == 'tree':
            for rel in bucket['added'] + bucket['changed']:
                target = local_path(data_root, rel)
                if os.path.exists(target):
                    _backup(target, backup_root, rel)
                    result['backup'] = backup_root
                paths.ensure_dir(os.path.dirname(target))
                shutil.copy2(os.path.join(team, *rel.split('/')), target)
                pulled[rel] = found['manifest'][rel]
                result['copied'] += 1
            for rel in bucket['removed']:
                target = local_path(data_root, rel)
                if os.path.exists(target):
                    _backup(target, backup_root, rel)
                    result['backup'] = backup_root
                    os.remove(target)
                pulled.pop(rel, None)
                result['removed'] += 1
            continue
        rel = [p for a, p, _k in AREAS if a == area][0]
        if not (bucket['added'] or bucket['changed']):
            continue
        data = paths.load_json(os.path.join(team, rel), None, move_aside=False)
        if area == 'config':
            values, changed = merge_config(namo_config.load(), data)
            if values:
                namo_config.save(values)
            result['config'] = changed
        else:
            path = config_path or _user_config_path()
            root, error = hotkeys.read_config(path)
            if error:
                raise IOError(error)
            if area == 'shortcuts':
                result['shortcuts'] = merge_shortcuts(root, data)
                if result['shortcuts']:
                    # pyNavis' own saver when it is loaded (see hotkeys.write_bindings).
                    hotkeys.write_bindings(path, root)
                    result['needs_reload'] = True
            else:
                result['roots'] = merge_roots(root, data)
                if result['roots']:
                    hotkeys.write_config(path, root)
                    result['needs_reload'] = True
        pulled[rel] = found['manifest'][rel]
    state['pulled'] = pulled
    state['stamp'] = found['stamp'] or state.get('stamp') or ''
    state['last_pull'] = stamp
    save_state(state, data_root)
    return result


def _user_config_path():
    return ribbon.user_config_path()


# ---- push ------------------------------------------------------------------------------------


def push(folder, data_root=None, config_path=None, user=None, now=None):
    """Writes this machine's content into the team folder (files it replaces are backed
    up beside it in playground-team\\.backup\\<stamp>). Returns {'files', 'stamp', 'backup'}."""
    data_root = data_root or paths.data_root()
    if not folder:
        raise IOError('Set the team folder first.')
    if not os.path.isdir(folder):
        raise IOError('The team folder %s is not reachable.' % folder)
    team = team_dir(folder)
    paths.ensure_dir(team)
    stamp = new_stamp(now)
    backup_root = os.path.join(team, '.backup', stamp.replace(':', ''))
    written = 0
    backup = None
    local = manifest(data_root)
    team_files = manifest(team)
    for rel in sorted(local):
        area = area_of(rel)
        if area is None or [k for a, _p, k in AREAS if a == area][0] != 'tree':
            continue
        target = os.path.join(team, *rel.split('/'))
        if rel in team_files and team_files[rel] == local[rel]:
            continue
        if os.path.exists(target):
            _backup(target, backup_root, rel)
            backup = backup_root
        paths.ensure_dir(os.path.dirname(target))
        shutil.copy2(local_path(data_root, rel), target)
        written += 1
    cfg = namo_config.load()
    team_cfg = collections.OrderedDict((k, cfg[k]) for k in TEAM_CONFIG_KEYS)
    written += _write_json_if_changed(os.path.join(team, 'config.json'), team_cfg, backup_root)
    root, error = hotkeys.read_config(config_path or _user_config_path())
    if error:
        raise IOError(error)
    bindings = collections.OrderedDict(hotkeys.overrides_of(root))
    written += _write_json_if_changed(os.path.join(team, 'shortcuts.json'), bindings, backup_root)
    roots = [r for r in (root.get('extensions') or []) if isinstance(r, str)]
    written += _write_json_if_changed(os.path.join(team, 'extensions.json'), roots, backup_root)
    paths.write_json(os.path.join(team, 'version.json'),
                     {'stamp': stamp, 'by': user or namo_config.user_name()})
    state = load_state(data_root)
    state['last_push'] = stamp
    state['stamp'] = stamp
    pulled = manifest(team)
    state['pulled'] = pulled
    save_state(state, data_root)
    return {'files': written, 'stamp': stamp, 'backup': backup}


def _write_json_if_changed(path, value, backup_root):
    text = json.dumps(value, indent=2, sort_keys=isinstance(value, dict) and not
                      isinstance(value, collections.OrderedDict), ensure_ascii=False) + '\n'
    if os.path.exists(path):
        with io.open(path, encoding='utf-8-sig') as handle:
            if handle.read() == text:
                return 0
        _backup(path, backup_root, os.path.basename(path))
    paths.atomic_write_text(path, text)
    return 1


# ---- startup check (hk_teamsync) ---------------------------------------------------------------


def _read_json_quietly(path):
    """Parsed JSON or None. Never logs and never moves a damaged file aside, so it is
    safe on a worker thread (Playground's logger echoes into the output window)."""
    try:
        with io.open(path, 'r', encoding='utf-8-sig') as handle:
            return json.loads(handle.read())
    except Exception:
        return None


def startup_probe(data_root=None):
    """The worker-thread half of the startup check (hk_teamsync): the team folder when
    "Pull at startup" is on and the team's version stamp differs from the one pulled
    here, else None. Plain file reads only: no Navisworks, no WPF, no logging, no
    writes. A slow or offline share blocks only the calling thread. May raise."""
    stored = _read_json_quietly(state_path(data_root))
    state = stored if isinstance(stored, dict) else {}
    if not state.get('auto_pull'):
        return None
    folder = team_folder(state)
    if not folder:
        return None
    team = team_dir(folder)
    if not os.path.isdir(team):
        return None
    data = _read_json_quietly(os.path.join(team, 'version.json'))
    stamp = str(data.get('stamp') or '') if isinstance(data, dict) else ''
    if not needs_pull(stamp, state.get('stamp')):
        return None
    return folder


def startup_check(data_root=None, on_result=None):
    """The whole startup check in one call: probe the stamp, pull when it changed.
    on_result(result_or_error) gets the outcome. Never raises. hk_teamsync runs the two
    halves apart: startup_probe() on a worker thread, pull() on the UI thread."""
    try:
        folder = startup_probe(data_root)
        if not folder:
            return None
        result = pull(folder, data_root)
        if on_result is not None:
            on_result(result)
        return result
    except Exception as error:
        session.log('warning', 'team sync at startup: %s' % error)
        if on_result is not None:
            on_result(error)
        return error


def result_toast(result):
    """(level, message, detail) for a pull result or an error."""
    if isinstance(result, Exception):
        return ('warning', 'Team settings were not updated', str(result))
    parts = []
    if result['copied']:
        parts.append('%d file%s' % (result['copied'], '' if result['copied'] == 1 else 's'))
    if result['removed']:
        parts.append('%d removed' % result['removed'])
    if result['config']:
        parts.append('project settings')
    if result['shortcuts']:
        parts.append('%d shortcut%s' % (result['shortcuts'], '' if result['shortcuts'] == 1 else 's'))
    if result['roots']:
        parts.append('%d extension folder%s' % (result['roots'], '' if result['roots'] == 1 else 's'))
    detail = ', '.join(parts) if parts else 'Nothing changed.'
    if result.get('needs_reload'):
        detail += '. Reload pyNavis to apply them.'
    return ('success', 'Team settings updated', detail)


# ---- the window ---------------------------------------------------------------------------------


def build_window(folder, found, state):
    """The Team Sync window, unshown. window.Tag.action is 'pull', 'push', 'folder' or
    None after it closes; window.Tag.auto_pull is the check box."""
    from namo import ui
    ui.load_wpf()
    from System.Windows.Controls import Dock, DockPanel, StackPanel
    logger = ui.pinned_logger()
    win = ui.window('Team Sync', width=560)
    parts = ui.Bag(action=None, auto_pull=bool(state.get('auto_pull')))
    win.Tag = parts
    body = StackPanel()
    body.Margin = ui.thickness(24, 20, 24, 16)
    body.Children.Add(ui.text('Team folder', size=12, bold=True))
    where = ui.text(folder or 'Not set', wrap=True)
    where.Margin = ui.thickness(0, 2, 0, 12)
    body.Children.Add(where)
    stamps = []
    if found.get('stamp'):
        stamps.append('Team content from %s' % found['stamp'].replace('T', ' '))
    if state.get('last_pull'):
        stamps.append('last pulled here %s' % state['last_pull'].replace('T', ' '))
    if stamps:
        body.Children.Add(ui.hint(', '.join(stamps) + '.'))
    heading = ui.text('Pull would change', size=12, bold=True)
    heading.Margin = ui.thickness(0, 16, 0, 4)
    body.Children.Add(heading)
    if found.get('error'):
        body.Children.Add(ui.text(found['error'], wrap=True))
    elif found.get('lines'):
        for line in found['lines']:
            body.Children.Add(ui.text(line, wrap=True))
        note = ui.hint('Files it replaces or removes are backed up first; files you made '
                       'yourself are left alone.')
        note.Margin = ui.thickness(0, 8, 0, 0)
        body.Children.Add(note)
    else:
        body.Children.Add(ui.text('Nothing: this computer matches the team folder.'))
    auto = ui.check('Pull at startup when the team content changes', parts.auto_pull)
    auto.Margin = ui.thickness(0, 16, 0, 0)
    body.Children.Add(auto)

    def finish(action):
        parts.action = action
        parts.auto_pull = bool(auto.IsChecked)
        ui.close_with(win, True)

    def close():
        parts.auto_pull = bool(auto.IsChecked)
        ui.close_with(win, False)

    pull_button = ui.button('Pull', lambda: finish('pull'), 'primary', logger)
    pull_button.IsEnabled = bool(found.get('count')) and not found.get('error')
    push_button = ui.button('Push', lambda: finish('push'), 'secondary', logger)
    push_button.IsEnabled = bool(folder) and not found.get('unreachable')
    folder_button = ui.button('Change folder', lambda: finish('folder'), 'secondary', logger)
    close_button = ui.button('Close', close, 'secondary', logger)
    close_button.IsCancel = True
    footer = ui.footer([pull_button, push_button, close_button], left=folder_button)
    win.Closing += ui.safe(lambda s, e: setattr(parts, 'auto_pull', bool(auto.IsChecked)),
                           'team sync closing', logger)
    layout = DockPanel()
    DockPanel.SetDock(footer, Dock.Bottom)
    layout.Children.Add(footer)
    layout.Children.Add(body)
    win.Content = layout
    parts.auto = auto
    parts.pull_button = pull_button
    parts.push_button = push_button
    parts.finish = finish
    return win
