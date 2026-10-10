# -*- coding: utf-8 -*-
"""Hotkey Manager: one list of every command, with chords you can assign or clear.

pyNavis bundles keep their user chords in %APPDATA%\\pyNavis\\config.json under
shortcuts.bindings, keyed by bundle key (the same file and rules as pyNavis' own
Shortcuts editor). Native Navisworks ribbon commands have no binding table, so a chord
for one becomes a generated *.nobutton in MyTools.extension\\MyTools.tab\\Hotkeys.panel
whose script runs that command; the panel also gets a visible Hotkeys button that opens
this manager, so it is never an empty panel.

Pure half (tested on both engines, and under IronPython against the real
PyNavisConfig.Load):
    read_config(path) -> (root, error)        root keeps the file's key order
    dumps_config(root) -> text                JsonPretty's layout: 2-space indent, ': ',
                                              raw non-ASCII, CRLF after the last brace
    overrides_of(root) / allow_bare_of(root)
    apply_binding_changes(root, changes, defaults) -> root
        changes {key: chord or None}; only those keys are touched (spelling and NN_
        variants of the same key removed), a chord equal to the author default removes
        the override, None disables a default (null), empty sections are removed
    write_config(path, root)                  atomic; refuses an unparsable existing file
    HotkeyModel(rows)                         the editor's state: set/clear/reset, first-
                                              wins conflicts, what may be saved
    bundle_rows(commands, overrides, natives_by_bundle) / native_rows(natives, bound)
    native_folder(...) helpers for the generated *.nobutton bundles
API half: load(), save(), the window (show()).
"""
import collections
import datetime
import io
import json
import os
import shutil

from namo import buttonmaker, paths, ribbon, ui

HOTKEYS_PANEL = 'Hotkeys'
HOTKEYS_TAB = 'MyTools'
MANAGER_KEY = 'Dev.tab/Build.panel/Hotkey_Manager.pushbutton'

# ---- config.json -----------------------------------------------------------------------


def read_config(path):
    """(root, None) with key order kept, or (None, sentence) when the file exists but is
    not valid JSON (pyNavis refuses to overwrite such a file, and so do we). A missing or
    empty file is an empty root."""
    if not path or not os.path.exists(path):
        return collections.OrderedDict(), None
    try:
        with io.open(path, encoding='utf-8-sig') as handle:
            text = handle.read()
    except (IOError, OSError) as error:
        return None, 'Could not read %s: %s' % (os.path.basename(path), error)
    if not text.strip():
        return collections.OrderedDict(), None
    try:
        root = json.loads(text, object_pairs_hook=collections.OrderedDict)
    except ValueError:
        return None, ('%s is not valid JSON, so nothing was saved. Fix the file or delete it.'
                      % path)
    if not isinstance(root, dict):
        return None, '%s does not hold a JSON object, so nothing was saved.' % path
    return root, None


def dumps_config(root):
    """The text pyNavis' JsonPretty writes: two-space indent, '": "', raw non-ASCII,
    '\\n' between lines and '\\r\\n' after the closing brace."""
    return json.dumps(root, indent=2, ensure_ascii=False, separators=(',', ': ')) + '\r\n'


def overrides_of(root):
    """{key as written: chord or None} from shortcuts.bindings (non-text values are None,
    as pyNavis reads them)."""
    out = collections.OrderedDict()
    shortcuts = root.get('shortcuts') if isinstance(root, dict) else None
    bindings = shortcuts.get('bindings') if isinstance(shortcuts, dict) else None
    if not isinstance(bindings, dict):
        return out
    for key in bindings:
        value = bindings[key]
        out[key] = value if isinstance(value, str) else None
    return out


def allow_bare_of(root):
    shortcuts = root.get('shortcuts') if isinstance(root, dict) else None
    value = shortcuts.get('allowBareKeys') if isinstance(shortcuts, dict) else None
    return value is True


def override_for(overrides, key):
    """(present, value) for a bundle key, matching keys the way pyNavis does."""
    found = False
    value = None
    for raw in overrides:
        if ribbon.same_key(raw, key):
            found, value = True, overrides[raw]          # last spelling wins, like the C# load
    return found, value


def apply_binding_changes(root, changes, defaults):
    """Writes chords for the changed keys into root (mutated and returned).

    changes {bundle key: canonical chord or None}; defaults {bundle key: author chord or
    None}. A chord equal to the default removes the override; None for a key with a
    default writes null (disabled); None without a default removes the override."""
    shortcuts = root.get('shortcuts')
    if not isinstance(shortcuts, dict):
        shortcuts = collections.OrderedDict()
    bindings = shortcuts.get('bindings')
    if not isinstance(bindings, dict):
        bindings = collections.OrderedDict()
    for key in sorted(changes):
        wanted = changes[key]
        default = None
        for dkey in defaults:
            if ribbon.same_key(dkey, key):
                default = ribbon.chord_or_none(defaults[dkey], True)
        for raw in list(bindings):
            if ribbon.same_key(raw, key):
                del bindings[raw]
        canonical = ribbon.normalize_key(key)
        if wanted == default:
            continue
        if wanted is None:
            if default is not None:
                bindings[canonical] = None
            continue
        bindings[canonical] = wanted
    if bindings:
        shortcuts['bindings'] = bindings
    elif 'bindings' in shortcuts:
        del shortcuts['bindings']
    if shortcuts:
        root['shortcuts'] = shortcuts
    elif 'shortcuts' in root:
        del root['shortcuts']
    return root


def write_config(path, root):
    """Atomic write of root to path in pyNavis' layout. Refuses (IOError) when the file
    on disk is not valid JSON any more."""
    _current, error = read_config(path)
    if error:
        raise IOError(error)
    paths.ensure_dir(os.path.dirname(path))
    paths.atomic_write_text(path, dumps_config(root))
    return path


def _runtime_save_bindings(path, bindings):
    """Hands the whole bindings map to pyNavis' own saver, the one its Shortcuts editor
    uses (PyNavisConfig.SaveShortcutBindings: re-reads the file, replaces only
    shortcuts.bindings, writes beside the file and swaps it in). True when it wrote;
    False when the runtime is not there (tests under CPython), so the caller writes the
    same layout itself. IOError with the runtime's sentence when the save failed."""
    try:
        ribbon._runtime()
        from PyNavis.Runtime.Config import PyNavisConfig
        from System import String
        from System.Collections.Generic import Dictionary
        table = Dictionary[String, String]()
    except Exception:
        return False
    for key in bindings:
        value = bindings[key]
        table[str(key)] = value if isinstance(value, str) else None
    try:
        PyNavisConfig.SaveShortcutBindings(path, table)
    except Exception as error:
        raise IOError(str(getattr(error, 'Message', None) or error))
    return True


def write_bindings(path, root):
    """Saves root's shortcuts.bindings into config.json at path: through pyNavis' own
    saver when the runtime is loaded (the field-proven route, and it re-reads the file
    at the moment of saving, so a key something else changed meanwhile is kept), else
    by writing root in the same layout. Raises IOError when nothing could be saved."""
    if not _runtime_save_bindings(path, overrides_of(root)):
        write_config(path, root)
    return path


def save_bindings(path, changes, defaults):
    """Read-modify-write of config.json changing only these keys. Returns the root."""
    root, error = read_config(path)
    if error:
        raise IOError(error)
    apply_binding_changes(root, changes, defaults)
    write_bindings(path, root)
    return root


# ---- the editor's state -------------------------------------------------------------------


class HotkeyModel(object):
    """Rows [{'key', 'kind' ('bundle' | 'native'), 'title', 'path', 'default',
    'current', 'extension'}] in ribbon order (bundles first, natives after). Chords are
    canonical text or None."""

    def __init__(self, rows, allow_bare=False):
        self.rows = rows
        self.allow_bare = allow_bare
        self.by_key = dict((r['key'].lower(), r) for r in rows)
        self.initial = dict((r['key'].lower(), r.get('current')) for r in rows)

    def row(self, key):
        return self.by_key.get((key or '').lower())

    def set(self, key, text):
        """Assigns a chord; returns None or a sentence saying why it was refused."""
        row = self.row(key)
        if row is None:
            return 'That command is no longer listed.'
        chord, error = ribbon.parse_chord(text, self.allow_bare)
        if chord is None:
            return ribbon.chord_error_sentence(error)
        row['current'] = chord
        return None

    def clear(self, key):
        row = self.row(key)
        if row is not None:
            row['current'] = None

    def reset(self, key):
        row = self.row(key)
        if row is not None:
            row['current'] = row.get('default')

    def conflicts(self):
        """{key_lower: title of the earlier row holding the same chord}."""
        owners = {}
        lost = {}
        for row in self.rows:
            chord = row.get('current')
            if not chord:
                continue
            if chord in owners:
                lost[row['key'].lower()] = owners[chord]['title']
            else:
                owners[chord] = row
        return lost

    def owner_of(self, chord, except_key=None):
        """The first row (other than except_key) holding chord, or None."""
        for row in self.rows:
            if row.get('current') == chord and row['key'].lower() != (except_key or '').lower():
                return row
        return None

    def dirty_keys(self):
        return [r['key'] for r in self.rows if r.get('current') != self.initial[r['key'].lower()]]

    def blocking_conflicts(self):
        """Conflicts that involve a changed row (on either side): these stop a save.
        Older conflicts between untouched commands are shown but never block."""
        dirty = set(k.lower() for k in self.dirty_keys())
        lost = self.conflicts()
        out = {}
        for key, owner_title in lost.items():
            row = self.by_key[key]
            owner = self.owner_of(row['current'], row['key'])
            if key in dirty or (owner is not None and owner['key'].lower() in dirty):
                out[key] = owner_title
        return out

    def can_save(self):
        return bool(self.dirty_keys()) and not self.blocking_conflicts()

    def changes(self, kind):
        return dict((r['key'], r.get('current')) for r in self.rows
                    if r['kind'] == kind and r.get('current') != self.initial[r['key'].lower()])

    def defaults(self):
        return dict((r['key'], r.get('default')) for r in self.rows if r['kind'] == 'bundle')

    def note(self, key):
        """What the last column says for a row."""
        row = self.row(key)
        lost = self.conflicts()
        if row is None:
            return ''
        if row['key'].lower() in lost:
            return 'Taken by %s' % lost[row['key'].lower()]
        changed = row.get('current') != self.initial[row['key'].lower()]
        if changed:
            return 'Changed'
        if row['kind'] == 'bundle' and row.get('current') != row.get('default'):
            return 'Custom' if row.get('current') else 'Turned off'
        return ''


def bundle_rows(commands, overrides, hidden_keys=()):
    """Rows for pyNavis bundles the way pyNavis' ShortcutsModel builds them: current =
    the user entry (None = turned off; an unparsable one shows the default) else the
    default. hidden_keys: bundle keys left out (the generated native hotkeys)."""
    hidden = set(k.lower() for k in hidden_keys)
    rows = []
    seen = set()
    for command in commands:
        key = command['key']
        low = ribbon.normalize_key(key).lower()
        if not key or low in seen or low in hidden:
            continue
        seen.add(low)
        default = ribbon.chord_or_none(command.get('default'), True)
        present, value = override_for(overrides, key)
        if present:
            current = None if value is None else (ribbon.chord_or_none(value, True) or default)
        else:
            current = default
        rows.append({'key': key, 'kind': 'bundle', 'title': command.get('title') or key,
                     'path': command_path_of(command), 'default': default,
                     'current': current, 'extension': command.get('extension') or ''})
    return rows


def command_path_of(command):
    return ribbon.command_path(command.get('extension'), command.get('path'))


def native_rows(natives, bound):
    """Rows for native ribbon commands; bound {native key lower: chord}."""
    rows = []
    for command in natives:
        rows.append({'key': command['key'], 'kind': 'native', 'title': command['title'],
                     'path': ribbon.command_path('Navisworks', command.get('path')),
                     'default': None, 'current': bound.get(command['key'].lower()),
                     'extension': 'Navisworks'})
    return rows


def table_rows(model, query_kind='all'):
    """Cells for the window's table: Command, Where, Shortcut, Default, Note."""
    out = []
    for row in model.rows:
        if query_kind == 'bound' and not row.get('current'):
            continue
        out.append({'value': row['key'],
                    'cells': [row['title'], row['path'], row.get('current') or '',
                              row.get('default') or '', model.note(row['key'])]})
    return out


def status_text(model):
    changed = len(model.dirty_keys())
    blocking = model.blocking_conflicts()
    bound = len([r for r in model.rows if r.get('current')])
    text = '%s commands, %s with a shortcut' % ('{:,}'.format(len(model.rows)), '{:,}'.format(bound))
    if changed:
        text += '; %d changed' % changed
    if blocking:
        text += '; fix %d conflict%s to save' % (len(blocking), '' if len(blocking) == 1 else 's')
    return text


# ---- native hotkey bundles ----------------------------------------------------------------


def hotkeys_panel(root):
    return os.path.join(buttonmaker.extension_folder(root), HOTKEYS_TAB + '.tab',
                        HOTKEYS_PANEL + '.panel')


def scan_native_bundles(root):
    """{native key lower: {'folder', 'key' (bundle key), 'chord', 'title', 'command'}} from
    the generated *.nobutton bundles (bundle.yaml 'command:')."""
    panel = hotkeys_panel(root)
    out = {}
    if not os.path.isdir(panel):
        return out
    ext = buttonmaker.extension_folder(root)
    for name in sorted(os.listdir(panel)):
        folder = os.path.join(panel, name)
        if not name.lower().endswith('.nobutton') or not os.path.isdir(folder):
            continue
        yaml_path = os.path.join(folder, 'bundle.yaml')
        if not os.path.exists(yaml_path):
            continue
        with io.open(yaml_path, encoding='utf-8-sig') as handle:
            values, _layout = buttonmaker.read_flat_yaml(handle.read())
        command = values.get('command')
        if not command:
            continue
        out[command.lower()] = {'folder': folder, 'key': ribbon.bundle_key(ext, folder),
                                'chord': ribbon.chord_or_none(values.get('shortcut'), True),
                                'title': values.get('title') or '', 'command': command}
    return out


def unique_stem(panel_folder, title):
    stem = buttonmaker.folder_stem(title)
    taken = set()
    if os.path.isdir(panel_folder):
        taken = set(buttonmaker.layout_stem(n) for n in os.listdir(panel_folder))
    candidate = stem
    n = 2
    while buttonmaker.layout_stem(candidate) in taken:
        candidate = '%s_%d' % (stem, n)
        n += 1
    return candidate


def manager_button_spec(namo_lib):
    return {'title': 'Hotkeys', 'tooltip': 'Opens the Playground Hotkey Manager to change these shortcuts.',
            'template': 'bundle', 'bundle_key': MANAGER_KEY, 'extension': 'Playground',
            'tab': HOTKEYS_TAB, 'panel': HOTKEYS_PANEL, 'icon': 'keys', 'namo_lib': namo_lib}


def native_spec(root, command_key, label, where, chord, namo_lib):
    return {'title': label, 'template': 'native', 'kind': 'nobutton',
            'tooltip': 'Runs the Navisworks command %s (%s).' % (label, where),
            'tab': HOTKEYS_TAB, 'panel': HOTKEYS_PANEL, 'shortcut': chord,
            'folder': unique_stem(hotkeys_panel(root), label),
            'native_key': command_key, 'native_label': label, 'namo_lib': namo_lib,
            'extra_yaml': [('command', command_key)]}


def rewrite_chord(folder, chord):
    """Changes the shortcut: line of a generated bundle, keeping its other keys."""
    path = os.path.join(folder, 'bundle.yaml')
    with io.open(path, encoding='utf-8-sig') as handle:
        values, _layout = buttonmaker.read_flat_yaml(handle.read())
    pairs = [('title', values.get('title')), ('tooltip', values.get('tooltip')),
             ('shortcut', chord), ('command', values.get('command'))]
    paths.atomic_write_text(path, buttonmaker.bundle_yaml(pairs))


def trash(path, trash_root):
    """Moves a folder into trash_root as '<YYYYmmdd-HHMMSS> <name>'. Returns the new path."""
    paths.ensure_dir(trash_root)
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    target = paths.unique_path(os.path.join(trash_root, '%s %s' % (stamp, os.path.basename(path))))
    shutil.move(path, target)
    return target


def apply_native_changes(root, changes, rows_by_key, trash_root, namo_lib, make_icons=True):
    """Adds, rechords or removes generated native hotkeys. changes {native key: chord or
    None}; rows_by_key {native key lower: row} for labels. Returns (added, changed, removed)."""
    existing = scan_native_bundles(root)
    added = changed = removed = 0
    panel_yaml = os.path.join(hotkeys_panel(root), 'bundle.yaml')
    for key in sorted(changes):
        chord = changes[key]
        found = existing.get(key.lower())
        if chord is None:
            if found is not None:
                trash(found['folder'], trash_root)
                if os.path.exists(panel_yaml):
                    with io.open(panel_yaml, encoding='utf-8-sig') as handle:
                        text = handle.read()
                    paths.atomic_write_text(panel_yaml, buttonmaker.remove_layout_entry(
                        text, os.path.basename(found['folder'])))
                removed += 1
            continue
        if found is not None:
            rewrite_chord(found['folder'], chord)
            changed += 1
            continue
        if not os.path.isdir(os.path.join(hotkeys_panel(root), HOTKEYS_PANEL + '.pushbutton')):
            buttonmaker.make(root, manager_button_spec(namo_lib), icons=make_icons)
        row = rows_by_key.get(key.lower()) or {}
        label = row.get('title') or key
        where = row.get('path') or 'Navisworks'
        buttonmaker.make(root, native_spec(root, key, label, where, chord, namo_lib), icons=False)
        added += 1
    return added, changed, removed


# ==================================================================================
# API half
# ==================================================================================


def load(config_path=None, root=None):
    """The model for the live session: {'model', 'config_path', 'root', 'natives_by_key',
    'error'}."""
    config_path = config_path or ribbon.user_config_path()
    root = root or buttonmaker.user_root()
    cfg, error = read_config(config_path)
    overrides = overrides_of(cfg) if cfg is not None else collections.OrderedDict()
    allow_bare = allow_bare_of(cfg) if cfg is not None else False
    natives_on_disk = scan_native_bundles(root)
    commands = ribbon.buttons()
    by_bundle = dict((info['key'].lower(), info) for info in natives_on_disk.values())
    bound = {}
    for command in commands:
        info = by_bundle.get(ribbon.normalize_key(command['key']).lower())
        if info is not None and command.get('extension', '').lower() == buttonmaker.EXTENSION.lower():
            bound[info['command'].lower()] = ribbon.chord_or_none(command.get('shortcut'), True) or info['chord']
    for native_key, info in natives_on_disk.items():
        bound.setdefault(native_key, info['chord'])
    hidden = [info['key'] for info in natives_on_disk.values()]
    rows = bundle_rows(commands, overrides, hidden)
    natives = ribbon.native_commands()
    rows += native_rows(natives, bound)
    model = HotkeyModel(rows, allow_bare)
    return {'model': model, 'config_path': config_path, 'root': root, 'error': error,
            'natives_on_disk': natives_on_disk}


def save(state, trash_root=None):
    """Writes what changed: config.json for bundles, generated bundles for native
    commands. Returns (bundle_count, native_counts) and never reloads by itself."""
    model = state['model']
    bundle_changes = model.changes('bundle')
    native_changes = model.changes('native')
    if bundle_changes:
        save_bindings(state['config_path'], bundle_changes, model.defaults())
    counts = (0, 0, 0)
    if native_changes:
        rows_by_key = dict((r['key'].lower(), r) for r in model.rows if r['kind'] == 'native')
        counts = apply_native_changes(state['root'], native_changes, rows_by_key,
                                      trash_root or os.path.join(paths.data_root(), 'trash'),
                                      buttonmaker.namo_lib_folder())
        # A native hotkey's chord lives in its bundle.yaml: drop any config.json
        # override that would shadow it.
        cfg, _error = read_config(state['config_path'])
        current = overrides_of(cfg or {})
        stale = {}
        for info in scan_native_bundles(state['root']).values():
            present, _value = override_for(current, info['key'])
            if present:
                stale[info['key']] = info['chord']
        if stale:
            save_bindings(state['config_path'], stale, stale)
    return len(bundle_changes), counts


# ---- window ----------------------------------------------------------------------------


def _scroll_to_selection(table):
    """Keeps the edited row in view after a table reload (ui.Table has no public call
    for it yet; see the request in dev/notes/dev_team.md)."""
    grid = getattr(table, 'grid', None)
    try:
        if grid is not None and grid.SelectedItem is not None:
            grid.ScrollIntoView(grid.SelectedItem)
    except Exception:
        pass


def _recorder(allow_bare, on_change, logger):
    """pyNavis' own press-to-record field when the runtime has it, else a text box.
    Returns (element, get_text, set_text)."""
    try:
        from PyNavis.Runtime.Forms import ChordRecorder
        recorder = ChordRecorder(bool(allow_bare))
        recorder.Width = 180.0
        recorder.Height = 32.0

        def changed(text):
            on_change(text)
        recorder.ChordChanged += ui.safe(changed, 'chord recorded', logger)

        def get_text():
            return recorder.ChordText

        def set_text(value):
            recorder.ChordText = value
        return recorder, get_text, set_text
    except Exception:
        shell, box = ui.text_box('', placeholder='Ctrl+Alt+K')
        shell.Width = 180.0

        def keys(sender, args):
            from System.Windows.Input import Key
            if args.Key in (Key.Enter, Key.Return):
                on_change(box.Text.strip() or None)
                args.Handled = True
        box.PreviewKeyDown += ui.safe(keys, 'chord typed', logger)
        return shell, (lambda: box.Text.strip() or None), (lambda value: setattr(box, 'Text', value or ''))


def build_window(state, on_saved=None):
    """The Hotkey Manager window, unshown; window.Tag holds the parts."""
    ui.load_wpf()
    from System.Windows import GridLength, GridUnitType, HorizontalAlignment, VerticalAlignment
    from System.Windows.Controls import (Dock, DockPanel, Grid, Orientation, RowDefinition,
                                         StackPanel)
    from System.Windows.Input import Key, Keyboard, ModifierKeys
    logger = ui.pinned_logger()
    model = state['model']
    colors = ui.palette()
    win = ui.window('Hotkey Manager', width=900, height=640, min_width=640, min_height=420)
    parts = ui.Bag(model=model, state=state, selected=None, saved=False, kind='all')
    win.Tag = parts

    table = ui.Table(['Command', 'Where', 'Shortcut', 'Default', 'Note'],
                     table_rows(model), multiselect=False, logger=logger)
    parts.table = table

    title_block = ui.text('Select a command', bold=True, wrap=False)
    caption = ui.text('', size=12, color=colors['error'], wrap=False)
    hint = ui.hint('Click the field, then press the keys. Backspace clears it.')

    def refresh(keep=None):
        table.update(table_rows(model, parts.kind))
        if keep:
            table.select_values([keep])
            _scroll_to_selection(table)
        status.Text = status_text(model)
        save_button.IsEnabled = model.can_save()
        show_selected()

    def show_selected():
        values = table.selected_values()
        key = values[0] if values else None
        parts.selected = key
        row = model.row(key) if key else None
        enabled = row is not None
        for control in (clear_button, reset_button, recorder_element):
            control.IsEnabled = enabled
        if row is None:
            title_block.Text = 'Select a command'
            caption.Text = ''
            set_chord(None)
            return
        title_block.Text = row['title']
        set_chord(row.get('current'))
        reset_button.IsEnabled = row['kind'] == 'bundle' and row.get('current') != row.get('default')
        lost = model.conflicts().get(row['key'].lower())
        if lost:
            caption.Text = 'Taken by %s: change one of them to save.' % lost
        elif row.get('current'):
            owner = model.owner_of(row['current'], row['key'])
            caption.Text = ('%s also uses it and loses it.' % owner['title']) if owner else ''
        else:
            caption.Text = ''

    def chord_changed(text):
        key = parts.selected
        if not key:
            return
        if text is None:
            model.clear(key)
        else:
            problem = model.set(key, text)
            if problem:
                caption.Text = problem
                return
        refresh(key)

    recorder_element, get_chord, set_chord = _recorder(model.allow_bare, chord_changed, logger)

    def do_clear():
        if parts.selected:
            model.clear(parts.selected)
            refresh(parts.selected)

    def do_reset():
        if parts.selected:
            model.reset(parts.selected)
            refresh(parts.selected)

    clear_button = ui.button('Clear', do_clear, 'secondary', logger)
    reset_button = ui.button('Reset to default', do_reset, 'secondary', logger)
    table.on_change = lambda: show_selected()

    def filter_changed(text):
        table.set_filter(text)
    search, box = ui.search_box('Filter commands, tabs or shortcuts', filter_changed)
    only_bound = ui.check('Only commands with a shortcut')

    def bound_changed(sender, args):
        parts.kind = 'bound' if only_bound.IsChecked else 'all'
        refresh(parts.selected)
    only_bound.Checked += ui.safe(bound_changed, 'filter bound', logger)
    only_bound.Unchecked += ui.safe(bound_changed, 'filter bound', logger)

    def do_save():
        if not model.can_save():
            return
        parts.saved = True
        ui.close_with(win, True)

    save_button = ui.button('Save and reload', do_save, 'primary', logger)
    close_button = ui.button('Close', lambda: ui.close_with(win, False), 'secondary', logger)
    close_button.IsCancel = True
    status = ui.hint('')
    parts.status = status
    parts.save_button = save_button

    top = DockPanel()
    top.LastChildFill = True
    only_bound.Margin = ui.thickness(16, 0, 0, 0)
    only_bound.VerticalAlignment = VerticalAlignment.Center
    DockPanel.SetDock(only_bound, Dock.Right)
    top.Children.Add(only_bound)
    top.Children.Add(search)

    detail = Grid()
    detail.Margin = ui.thickness(0, 12, 0, 0)
    for _ in range(2):
        detail.RowDefinitions.Add(RowDefinition())
    left = StackPanel()
    left.Children.Add(title_block)
    left.Children.Add(caption)
    left.VerticalAlignment = VerticalAlignment.Center
    Grid.SetRow(left, 0)
    detail.Children.Add(left)
    controls = StackPanel()
    controls.Orientation = Orientation.Horizontal
    controls.HorizontalAlignment = HorizontalAlignment.Right
    for index, control in enumerate((recorder_element, clear_button, reset_button)):
        control.Margin = ui.thickness(0 if index == 0 else 8, 0, 0, 0)
        controls.Children.Add(control)
    Grid.SetRow(controls, 0)
    detail.Children.Add(controls)
    hint.Margin = ui.thickness(0, 4, 0, 0)
    Grid.SetRow(hint, 1)
    detail.Children.Add(hint)

    body = Grid()
    body.Margin = ui.thickness(16, 16, 16, 12)
    for size in ('auto', 'star', 'auto'):
        definition = RowDefinition()
        definition.Height = GridLength(1, GridUnitType.Star) if size == 'star' else GridLength.Auto
        body.RowDefinitions.Add(definition)
    Grid.SetRow(top, 0)
    body.Children.Add(top)
    table.element.Margin = ui.thickness(0, 12, 0, 0)
    Grid.SetRow(table.element, 1)
    body.Children.Add(table.element)
    Grid.SetRow(detail, 2)
    body.Children.Add(detail)

    footer = ui.footer([save_button, close_button], left=status, padding=16)
    layout = DockPanel()
    DockPanel.SetDock(footer, Dock.Bottom)
    layout.Children.Add(footer)
    layout.Children.Add(body)
    win.Content = layout

    def keys(sender, args):
        # While the shortcut field has the keyboard every chord belongs to it: Ctrl+S
        # and Ctrl+F must be recordable, not swallowed by the window.
        try:
            if recorder_element.IsKeyboardFocusWithin:
                return
        except Exception:
            pass
        if args.Key == Key.F and Keyboard.Modifiers == ModifierKeys.Control:
            box.Focus()
            box.SelectAll()
            args.Handled = True
        elif args.Key == Key.S and Keyboard.Modifiers == ModifierKeys.Control:
            do_save()
            args.Handled = True
    win.PreviewKeyDown += ui.safe(keys, 'hotkey keys', logger)

    def first_focus(sender, args):
        box.Focus()
    win.ContentRendered += ui.safe(first_focus, 'hotkey focus', logger)
    parts.refresh = refresh
    parts.chord_changed = chord_changed
    parts.search_box = box
    parts.recorder = recorder_element
    refresh()
    return win


def show(state):
    """Shows the manager modally; returns True when the user asked to save."""
    win = build_window(state)
    ui.show_modal(win)
    return bool(win.Tag.saved)
