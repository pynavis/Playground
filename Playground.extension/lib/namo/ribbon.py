# -*- coding: utf-8 -*-
"""The ribbon as data: every pyNavis button and every native Navisworks command, and
safe ways to run them from code. Shared by the Command Palette, macros, the Hotkey
Manager, usage analytics and the Environment Doctor.

Public API
----------
Pure (unit tested on both engines, no .NET):

    parse_chord(text, allow_bare=False) -> (canonical, error)
        pyNavis' ChordParser exactly: Ctrl/Alt/Shift plus ONE key (A-Z, 0-9, F1-F24, Left,
        Up, Right, Down, Home, End, PgUp, PgDn), Ctrl or Alt required unless allow_bare.
        canonical is 'Ctrl+Alt+Shift+Key' order; error is the runtime's own sentence.
    chord_or_none(text, allow_bare=False) -> canonical or None
    normalize_key(key)               BundleKeys.Normalize: NN_ prefixes dropped per segment
    same_key(a, b)                   normalised, case-insensitive equality
    bundle_key(ext_dir, bundle_dir)  'Tab.tab/Panel.panel/Thing.pushbutton'
    flatten_title(text)              BundleTitles.Flatten ('Record\\nMacro' -> 'Record Macro')
    title_from_folder(name)          'Clash_Report.pushbutton' -> 'Clash Report'
    command_path(*parts)             'Playground > Dev > Automate' (blank parts skipped)
    resolve_bindings(buttons, overrides, allow_bare=False) -> (bound, problems)
        ShortcutMap.Build exactly: buttons [{'key', 'shortcut'}] in ribbon order; a user
        entry (even None) replaces the default; first wins on a conflict.
    find_conflicts(pairs) -> {key: owner_key}  first-wins conflicts among (key, chord) pairs
    needs_text(rule) -> 'a selection' ...      a context: rule in words
    native_key(tab_id, item_id, tab_title='', panel_title='', label='')
    mru_push(mru, key, limit=40) -> new list   most recent first, case-insensitive dedupe
    Job                                        the deferred-run state machine (see below)

Navisworks / runtime (lazy .NET imports; every call is safe outside Navisworks and
returns empty results there):

    buttons(extensions=None) -> [command]     every pyNavis pushbutton-shaped bundle
    other_items(extensions=None) -> [command] dock panels, url buttons, link buttons
    find_button(key, extension=None) -> PushButtonModel or None
    button_command(key, extension=None) -> command dict or None
    native_commands(include_pynavis=False) -> [command]   AdWindows ribbon items
    find_native(key) -> command or None
    gate_held() / gate_title()                PyNavis.Runtime.Execution.RunGate
    run_bundle(key_or_model, ...) -> Job      deferred until the RunGate is free
    run_native(key_or_command, ...) -> Job    deferred, CanExecute checked first
    execute_native(item) -> (ok, message)     immediate: CanExecute, then Execute
    open_url(url) / run_link(plugin_id) / toggle_pane(key)
    reload()                                  pyNavis Reload

A command is a plain dict: {'kind': 'bundle' | 'native' | 'pane' | 'url' | 'link',
'key', 'title', 'path' (tab > panel), 'tooltip', 'shortcut' (resolved chord or ''),
'default' (author chord or ''), 'engine', 'extension', 'tab', 'panel', 'hidden' (a
*.nobutton), 'toggle', 'context' (rule text or ''), 'enabled', 'directory',
'script', 'model' or 'item' (the live object, never serialised)}.

How deferral works: a running pyNavis script holds the RunGate, so a script that wants
to start another (the palette, a macro step) cannot call ScriptExecutor.Run itself.
run_bundle() returns a Job ticked by a DispatcherTimer (50 ms) on the UI thread: it
waits until RunGate.IsHeld is False, then hands ScriptExecutor.Run to the dispatcher as
a .NET delegate (so the run starts from the message loop, never nested inside a Python
frame), then polls the DispatcherOperation until it completed. A step that raised
leaves a traceback in PyNavis.Runtime.Ai.FailureLog, which marks the job failed.
Timeouts: 15 s for the gate by default (someone else's long tool), toasted.

Native commands: AdWindows passes the RibbonItem itself to its ICommand; the item's own
CommandHandler is used when set, else the ribbon's, else ComponentManager's.
CanExecute(item) is asked first. UNVERIFIED in Navisworks (see dev/notes/dev_team.md).
"""
import re
import time

from namo import session

# ---- chords (pyNavis Input/ChordParser.cs) ---------------------------------------------

KEY_NAMES = ([chr(c) for c in range(ord('A'), ord('Z') + 1)] +
             [chr(c) for c in range(ord('0'), ord('9') + 1)] +
             ['F%d' % i for i in range(1, 25)] +
             ['Left', 'Up', 'Right', 'Down', 'Home', 'End', 'PgUp', 'PgDn'])
_KEYS = dict((name.lower(), name) for name in KEY_NAMES)
BARE_HINT = 'bindings need Ctrl or Alt (set shortcuts.allowBareKeys to permit bare keys)'


def parse_chord(text, allow_bare=False):
    """(canonical, None) or (None, error) with pyNavis' own error text."""
    if text is None or not str(text).strip():
        return None, 'empty binding'
    text = str(text)
    ctrl = alt = shift = False
    key = None
    for raw in text.split('+'):
        part = raw.strip()
        low = part.lower()
        if low == 'ctrl':
            ctrl = True
        elif low == 'alt':
            alt = True
        elif low == 'shift':
            shift = True
        elif low in _KEYS:
            if key is not None:
                return None, "'%s': more than one key" % text
            key = _KEYS[low]
        else:
            return None, "'%s': unknown token '%s'" % (text, part)
    if key is None:
        return None, "'%s': no key" % text
    if not allow_bare and not (ctrl or alt):
        return None, "'%s': %s" % (text, BARE_HINT)
    parts = []
    if ctrl:
        parts.append('Ctrl')
    if alt:
        parts.append('Alt')
    if shift:
        parts.append('Shift')
    parts.append(key)
    return '+'.join(parts), None


def chord_or_none(text, allow_bare=False):
    """The canonical chord, or None when text does not parse."""
    chord, _error = parse_chord(text, allow_bare)
    return chord


def chord_error_sentence(error):
    """A pyNavis parse error as a sentence for a form hint."""
    if not error:
        return None
    if error == 'empty binding':
        return 'Press a key combination.'
    if 'Ctrl or Alt' in error:
        return 'A shortcut needs Ctrl or Alt.'
    if 'more than one key' in error:
        return 'Use one key with Ctrl, Alt or Shift.'
    if 'no key' in error:
        return 'Add a key after the modifiers.'
    if 'unknown token' in error:
        return 'Use letters, digits, F1 to F24, arrows, Home, End, PgUp or PgDn.'
    return error[:1].upper() + error[1:] + '.'


# ---- bundle keys and titles -----------------------------------------------------------

_ORDER_PREFIX = re.compile(r'^\d{2,}_')
_BREAK = re.compile(r'[ \t]*\\n[ \t]*')
_RUNS = re.compile(r'[ \t]{2,}')
SUFFIXES = ('.splitpushbutton', '.splitbutton', '.pushbutton', '.nobutton', '.urlbutton',
            '.linkbutton', '.smartbutton', '.dockpane', '.slideout', '.pulldown', '.toggle',
            '.stack', '.panel', '.tab', '.extension')


def normalize_key(key):
    """BundleKeys.Normalize: a leading NN_ (two or more digits) dropped from every segment."""
    if not key or '_' not in key:
        return key
    return '/'.join(_ORDER_PREFIX.sub('', segment) for segment in key.split('/'))


def same_key(a, b):
    if a is None or b is None:
        return False
    return normalize_key(a).lower() == normalize_key(b).lower()


def bundle_key(ext_dir, bundle_dir):
    """The extension-relative bundle key (forward slashes, prefixes dropped)."""
    import os
    rel = os.path.relpath(bundle_dir, ext_dir)
    return normalize_key(rel.replace('\\', '/'))


def flatten_title(text):
    """BundleTitles.Flatten: every literal \\n becomes one space, space runs collapse."""
    if text is None:
        return None
    return _RUNS.sub(' ', _BREAK.sub(' ', str(text))).strip()


def strip_suffix(name):
    lower = name.lower()
    for suffix in SUFFIXES:
        if lower.endswith(suffix):
            return name[:-len(suffix)]
    return name


def title_from_folder(name):
    """The default caption pyNavis derives from a folder name."""
    return _ORDER_PREFIX.sub('', strip_suffix(name)).replace('_', ' ')


def command_path(*parts):
    return ' > '.join(str(p).strip() for p in parts if p is not None and str(p).strip())


# ---- bindings (pyNavis Input/ShortcutMap.cs) ------------------------------------------


def resolve_bindings(buttons, overrides, allow_bare=False):
    """({key_lower: chord}, [problem]) the way ShortcutMap.Build resolves them.

    buttons: [{'key', 'shortcut'}] in ribbon walk order (duplicate keys: first wins).
    overrides: {key: chord or None} from config.json (keys normalised here)."""
    by_key = {}
    order = []
    for button in buttons:
        key = button.get('key')
        if not key:
            continue
        low = normalize_key(key).lower()
        if low in by_key:
            continue
        by_key[low] = button
        order.append(low)
    user = {}
    problems = []
    for raw in sorted(overrides or {}):
        low = normalize_key(raw).lower()
        user[low] = overrides[raw]
        if low not in by_key:
            problems.append("shortcut override for unknown tool '%s' ignored" % raw)
    bound = {}
    owner = {}
    for low in order:
        button = by_key[low]
        text = user[low] if low in user else button.get('shortcut')
        if text is None or text == '':
            continue
        chord, error = parse_chord(text, allow_bare)
        if chord is None:
            problems.append("'%s': %s" % (button.get('key'), error))
            continue
        if chord in owner:
            problems.append("'%s' wants %s but '%s' already has it - first wins"
                            % (button.get('key'), chord, by_key[owner[chord]].get('key')))
            continue
        owner[chord] = low
        bound[low] = chord
    return bound, problems


def find_conflicts(pairs):
    """{key: earlier_key} for every (key, chord) that loses a chord to an earlier one.
    pairs in ribbon order; chords compared canonically; None/'' skipped."""
    owners = {}
    lost = {}
    for key, chord in pairs:
        canonical = chord_or_none(chord, True) if chord else None
        if not canonical:
            continue
        if canonical in owners:
            lost[key] = owners[canonical]
        else:
            owners[canonical] = key
    return lost


# ---- context rules in words ------------------------------------------------------------

CONDITION_WORDS = {
    'doc': 'an open model', 'selection': 'a selection', 'clash-tests': 'clash tests',
    'clash-results': 'clash results', 'viewpoints': 'saved viewpoints',
    'selection-sets': 'selection sets', 'multi-model': 'two or more models',
}
NEGATED_WORDS = {
    'doc': 'no open model', 'selection': 'nothing selected', 'clash-tests': 'no clash tests',
    'clash-results': 'no clash results', 'viewpoints': 'no saved viewpoints',
    'selection-sets': 'no selection sets', 'multi-model': 'a single model',
}


def needs_text(rule):
    """A context: rule in words: 'doc & selection' -> 'an open model and a selection'.
    '' for an empty rule; the rule itself when it does not parse."""
    text = (rule or '').strip()
    if not text:
        return ''
    try:
        alternatives = []
        for group in text.split('|'):
            words = []
            for term in group.split('&'):
                term = term.strip()
                negate = False
                while term.startswith('!'):
                    negate = not negate
                    term = term[1:].strip()
                name = term.lower()
                if not name:
                    raise ValueError(rule)
                table = NEGATED_WORDS if negate else CONDITION_WORDS
                words.append(table.get(name, ('not ' + name) if negate else name))
            alternatives.append(' and '.join(words))
        return ' or '.join(alternatives)
    except ValueError:
        return text


# ---- native command keys and MRU -----------------------------------------------------


def native_key(tab_id, item_id, tab_title='', panel_title='', label=''):
    """A stable key for a native ribbon item: its ribbon Id when it has one."""
    tab = (tab_id or tab_title or '').strip()
    if item_id and str(item_id).strip():
        return 'native:%s/%s' % (tab, str(item_id).strip())
    return 'native:%s/%s/%s' % (tab, (panel_title or '').strip(), (label or '').strip())


def mru_push(mru, key, limit=40):
    """A new most-recent-first list with key in front (case-insensitive dedupe)."""
    out = [key]
    low = (key or '').lower()
    for item in mru or []:
        if isinstance(item, str) and item.lower() != low:
            out.append(item)
    return out[:max(1, int(limit))]


def clean_label(text):
    """A ribbon caption on one line (AdWindows captions carry real line breaks)."""
    if text is None:
        return ''
    value = str(text).replace('\r\n', ' ').replace('\n', ' ').replace('\r', ' ')
    return _RUNS.sub(' ', value).strip()


# ---- deferred runs: the pure state machine --------------------------------------------


class Job(object):
    """One deferred run, advanced by tick() until it returns False.

    gate_held() -> bool; dispatch() -> handle (may raise); is_done(handle) -> bool;
    outcome(handle) -> (ok, message). on_done(job) runs once at the end whatever
    happened (job.state is 'done', 'failed', 'timeout' or 'cancelled'; job.ok and
    job.message say how it went)."""

    def __init__(self, label, gate_held, dispatch, is_done=None, outcome=None,
                 timeout_s=15.0, clock=None, on_done=None, wait_gate=True):
        self.label = label
        self.gate_held = gate_held
        self.dispatch = dispatch
        self.is_done = is_done or (lambda handle: True)
        self.outcome = outcome or (lambda handle: (True, ''))
        self.timeout_s = float(timeout_s)
        self.clock = clock or time.time
        self.on_done = on_done
        self.wait_gate = wait_gate
        self.started = self.clock()
        self.state = 'waiting'
        self.handle = None
        self.ok = None
        self.message = ''

    @property
    def active(self):
        return self.state in ('waiting', 'running')

    def cancel(self):
        if self.active:
            self._finish('cancelled', False, 'Stopped')

    def _finish(self, state, ok, message):
        self.state = state
        self.ok = ok
        self.message = message or ''
        if self.on_done is not None:
            callback, self.on_done = self.on_done, None
            callback(self)

    def tick(self):
        """Advances the job; returns True while it still needs ticks."""
        if self.state == 'waiting':
            if self.wait_gate and self.gate_held():
                if self.clock() - self.started > self.timeout_s:
                    self._finish('timeout', False, 'Something else is still running.')
                return self.active
            try:
                self.handle = self.dispatch()
            except Exception as error:
                self._finish('failed', False, str(error) or error.__class__.__name__)
                return False
            self.state = 'running'
        if self.state == 'running':
            if not self.is_done(self.handle):
                return True
            try:
                ok, message = self.outcome(self.handle)
            except Exception as error:
                ok, message = False, str(error)
            self._finish('done' if ok else 'failed', ok, message)
        return self.active


# ==================================================================================
# Runtime half (PyNavis.Runtime and AdWindows; every function survives their absence)
# ==================================================================================

PYNAVIS_TAB_PREFIX = 'PYNAVIS_TAB_'


def _runtime():
    import clr
    try:
        clr.AddReference('PyNavis.Runtime')
    except Exception:
        pass
    from PyNavis.Runtime import RuntimeHost
    return RuntimeHost


def extensions():
    """RuntimeHost.Extensions as a list ([] outside Navisworks)."""
    try:
        return list(_runtime().Extensions)
    except Exception:
        return []


def _binding_of(model):
    try:
        from PyNavis.Runtime.Input import ShortcutManager
        chord = ShortcutManager.BindingFor(model)
        return str(chord) if chord is not None else ''
    except Exception:
        return ''


def _ribbon_item_of(key):
    try:
        from PyNavis.Runtime.Ribbon import ButtonRegistry
        return ButtonRegistry.Find(key)
    except Exception:
        return None


def _text(value):
    return '' if value is None else str(value)


def _button_dict(ext, tab, panel, model):
    key = _text(model.BundleKey)
    item = None if model.NoUi else _ribbon_item_of(key)
    enabled = True
    if item is not None:
        try:
            enabled = bool(item.IsEnabled)
        except Exception:
            enabled = True
    rule = ''
    try:
        if model.ContextRule is not None:
            rule = _text(model.ContextRule.Text)
    except Exception:
        rule = ''
    return {
        'kind': 'bundle', 'key': key, 'title': flatten_title(_text(model.Title)),
        'path': command_path(_text(tab.Title), _text(panel.Title)),
        'tooltip': _text(model.Tooltip), 'shortcut': _binding_of(model),
        'default': _text(model.Shortcut), 'engine': _text(model.EngineId),
        'extension': _text(ext.Name), 'tab': _text(tab.Title), 'panel': _text(panel.Title),
        'hidden': bool(model.NoUi), 'toggle': bool(model.IsToggle), 'context': rule,
        'enabled': enabled, 'directory': _text(model.Directory),
        'script': _text(model.ScriptPath), 'config_script': _text(model.ConfigScriptPath),
        'model': model,
    }


def buttons(exts=None):
    """Every pushbutton-shaped bundle (pushbutton, nobutton, toggle, smartbutton), in
    the ribbon walk order pyNavis resolves shortcuts in."""
    out = []
    for ext in (extensions() if exts is None else exts):
        for tab in ext.Tabs:
            for panel in tab.Panels:
                for model in panel.Buttons:
                    try:
                        out.append(_button_dict(ext, tab, panel, model))
                    except Exception as error:
                        session.log('warning', 'ribbon: skipped a button: %s' % error)
    return out


def other_items(exts=None):
    """Dock panels, url buttons and link buttons (they are not pushbuttons)."""
    out = []
    try:
        from PyNavis.Runtime.Bundles import DockPaneModel, LinkButtonModel, UrlButtonModel
    except Exception:
        return out
    for ext in (extensions() if exts is None else exts):
        for tab in ext.Tabs:
            for panel in tab.Panels:
                for item in list(panel.Items) + list(panel.Slideout):
                    base = {'extension': _text(ext.Name), 'tab': _text(tab.Title),
                            'panel': _text(panel.Title), 'shortcut': '', 'default': '',
                            'engine': '', 'hidden': False, 'toggle': False, 'context': '',
                            'enabled': True, 'script': '', 'config_script': '',
                            'path': command_path(_text(tab.Title), _text(panel.Title))}
                    try:
                        if isinstance(item, DockPaneModel):
                            base.update({'kind': 'pane', 'key': _text(item.BundleKey),
                                         'title': flatten_title(_text(item.Title)),
                                         'tooltip': _text(item.Tooltip),
                                         'directory': _text(item.Directory), 'model': item})
                        elif isinstance(item, UrlButtonModel):
                            base.update({'kind': 'url', 'key': 'url:' + _text(item.Url),
                                         'title': flatten_title(_text(item.Title)),
                                         'tooltip': _text(item.Tooltip) or _text(item.Url),
                                         'directory': _text(item.Directory), 'url': _text(item.Url),
                                         'model': item})
                        elif isinstance(item, LinkButtonModel):
                            base.update({'kind': 'link', 'key': 'link:' + _text(item.PluginId),
                                         'title': flatten_title(_text(item.Title)),
                                         'tooltip': _text(item.Tooltip),
                                         'directory': _text(item.Directory),
                                         'plugin': _text(item.PluginId), 'model': item})
                        else:
                            continue
                    except Exception:
                        continue
                    out.append(base)
    return out


def find_button(key, extension=None, exts=None):
    """The live PushButtonModel for a bundle key (normalised, case-insensitive), the
    named extension's first when given and present, else the first anywhere."""
    if not key:
        return None
    first = None
    for ext in (extensions() if exts is None else exts):
        for tab in ext.Tabs:
            for panel in tab.Panels:
                for model in panel.Buttons:
                    if same_key(_text(model.BundleKey), key):
                        if extension is None or _text(ext.Name).lower() == str(extension).lower():
                            return model
                        if first is None:
                            first = model
    return first


def button_command(key, extension=None):
    """The command dict for one bundle key, or None."""
    for ext in extensions():
        for tab in ext.Tabs:
            for panel in tab.Panels:
                for model in panel.Buttons:
                    if same_key(_text(model.BundleKey), key) and (
                            extension is None or _text(ext.Name).lower() == str(extension).lower()):
                        return _button_dict(ext, tab, panel, model)
    if extension is not None:
        return button_command(key)
    return None


def extension_of(key):
    """Name of the first extension holding a bundle key ('' when none)."""
    for ext in extensions():
        for tab in ext.Tabs:
            for panel in tab.Panels:
                for model in panel.Buttons:
                    if same_key(_text(model.BundleKey), key):
                        return _text(ext.Name)
    return ''


# ---- native ribbon (AdWindows) ------------------------------------------------------


def _adwindows():
    import clr
    clr.AddReference('AdWindows')
    import Autodesk.Windows as aw
    return aw


def _label_of(item):
    for attr in ('Text', 'Name', 'Description'):
        try:
            value = clean_label(getattr(item, attr))
        except Exception:
            value = ''
        if value:
            return value
    try:
        tip = item.ToolTip
        if isinstance(tip, str) and tip.strip():
            return clean_label(tip)
    except Exception:
        pass
    return ''


def _tooltip_of(item):
    try:
        tip = item.ToolTip
        if isinstance(tip, str):
            return clean_label(tip)
        for attr in ('Content', 'Title'):
            value = getattr(tip, attr, None)
            if isinstance(value, str) and value.strip():
                return clean_label(value)
    except Exception:
        pass
    try:
        return clean_label(item.Description)
    except Exception:
        return ''


def _walk_items(aw, items, parents):
    """(item, parents) for every runnable command item, depth first."""
    for item in items:
        try:
            if not item.IsVisible:
                continue
        except Exception:
            pass
        if isinstance(item, aw.RibbonRowPanel):
            for found in _walk_items(aw, item.Items, parents):
                yield found
            continue
        if isinstance(item, aw.RibbonListButton):
            label = _label_of(item)
            for found in _walk_items(aw, item.Items, parents + ([label] if label else [])):
                yield found
            continue
        menu_items = getattr(item, 'Items', None) if isinstance(item, aw.RibbonMenuItem) else None
        if menu_items is not None and getattr(item, 'HasItems', False):
            label = _label_of(item)
            for found in _walk_items(aw, menu_items, parents + ([label] if label else [])):
                yield found
            continue
        if isinstance(item, aw.RibbonCommandItem):
            yield item, parents


def native_commands(include_pynavis=False):
    """Every runnable item on the Navisworks ribbon (buttons, toggles, menu entries),
    pyNavis' own tabs left out unless asked. [] when AdWindows is unavailable."""
    try:
        aw = _adwindows()
        ribbon = aw.ComponentManager.Ribbon
    except Exception:
        return []
    if ribbon is None:
        return []
    out = []
    seen = set()
    for tab in ribbon.Tabs:
        try:
            tab_id = _text(tab.Id)
            if tab_id.startswith(PYNAVIS_TAB_PREFIX) and not include_pynavis:
                continue
            tab_title = clean_label(tab.Title) or tab_id
            contextual = bool(getattr(tab, 'IsContextualTab', False))
            for panel in tab.Panels:
                source = panel.Source
                if source is None:
                    continue
                panel_title = clean_label(source.Title) or clean_label(panel.Id)
                for item, parents in _walk_items(aw, source.Items, []):
                    label = _label_of(item)
                    if not label:
                        continue
                    key = native_key(tab_id, _text(item.Id), tab_title, panel_title, label)
                    if key.lower() in seen:
                        continue
                    seen.add(key.lower())
                    title = ' > '.join(parents + [label]) if parents else label
                    enabled = True
                    try:
                        enabled = bool(item.IsEnabled)
                    except Exception:
                        pass
                    out.append({
                        'kind': 'native', 'key': key, 'title': title,
                        'path': command_path(tab_title, panel_title), 'tooltip': _tooltip_of(item),
                        'shortcut': '', 'default': '', 'engine': '', 'extension': 'Navisworks',
                        'tab': tab_title, 'panel': panel_title, 'hidden': False,
                        'toggle': isinstance(item, aw.RibbonToggleButton), 'context': '',
                        'enabled': enabled, 'directory': '', 'script': '', 'config_script': '',
                        'contextual': contextual, 'item': item,
                    })
        except Exception as error:
            session.log('warning', 'ribbon: skipped a tab while listing commands: %s' % error)
    return out


def find_native(key):
    """The native command for a key (see native_key), or None."""
    if not key:
        return None
    low = key.lower()
    for command in native_commands():
        if command['key'].lower() == low:
            return command
    return None


def _handler_for(aw, item):
    handler = None
    try:
        handler = item.CommandHandler
    except Exception:
        handler = None
    if handler is None:
        try:
            handler = aw.ComponentManager.Ribbon.CommandHandler
        except Exception:
            handler = None
    if handler is None:
        try:
            handler = aw.ComponentManager.CommandHandler
        except Exception:
            handler = None
    return handler


def execute_native(item, label=None):
    """Runs a native ribbon item now: (True, '') or (False, sentence). Never raises."""
    label = label or _label_of(item) or 'That command'
    try:
        aw = _adwindows()
    except Exception:
        return False, 'The Navisworks ribbon is not available here.'
    try:
        if not item.IsEnabled:
            return False, '%s is not available right now.' % label
    except Exception:
        pass
    handler = _handler_for(aw, item)
    if handler is None:
        return False, '%s cannot be run from here.' % label
    try:
        if not handler.CanExecute(item):
            return False, '%s is not available right now.' % label
    except Exception as error:
        session.log('warning', 'ribbon: CanExecute failed for %s: %s' % (label, error))
    try:
        handler.Execute(item)
    except Exception as error:
        session.log('error', 'ribbon: running %s failed: %s' % (label, error))
        return False, '%s failed: %s' % (label, error)
    return True, ''


# ---- the RunGate and deferred runs ---------------------------------------------------


def gate_held():
    try:
        _runtime()
        from PyNavis.Runtime.Execution import RunGate
        return bool(RunGate.IsHeld)
    except Exception:
        return False


def gate_title():
    try:
        _runtime()
        from PyNavis.Runtime.Execution import RunGate
        return _text(RunGate.CurrentTitle)
    except Exception:
        return ''


_JOBS = 'ribbon_jobs'


def _wpf():
    """References the WPF assemblies the dispatcher calls need (once per engine is enough;
    AddReference of a loaded assembly is cheap)."""
    import clr
    for name in ('WindowsBase', 'PresentationCore'):
        try:
            clr.AddReference(name)
        except Exception:
            pass


def _start_timer(job, interval_ms=50):
    """Ticks job on the UI thread until it finishes; the timer lives in a session holder."""
    _wpf()
    from System import TimeSpan
    from System.Windows.Threading import DispatcherPriority, DispatcherTimer
    holder = session.holder(_JOBS)
    timers = getattr(holder, 'timers', None)
    if timers is None:
        timers = []
        holder.timers = timers
    timer = DispatcherTimer(DispatcherPriority.Background)
    timer.Interval = TimeSpan.FromMilliseconds(interval_ms)
    state = {'busy': False}

    def tick(sender, args):
        if state['busy']:
            return
        state['busy'] = True
        keep = False
        try:
            keep = job.tick()
        except Exception as error:
            session.log('error', 'ribbon: a deferred run failed: %s' % error)
            keep = False
        finally:
            state['busy'] = False
        if not keep:
            try:
                timer.Stop()
            except Exception:
                pass
            if timer in timers:
                timers.remove(timer)
    timer.Tick += tick
    timers.append(timer)
    timer.Start()
    return timer


def _toast(level, message, detail=None):
    try:
        from pynavis import toast
        toast.show(level, message, detail)
    except Exception:
        session.log('info', '%s %s' % (message, detail or ''))


def _default_done(job):
    if job.state == 'timeout':
        busy = gate_title()
        _toast('info', 'Could not start %s' % job.label,
               ('%s is still running.' % busy) if busy else 'Something else is still running.')
    elif job.state == 'failed' and job.message:
        _toast('error', '%s did not finish' % job.label, job.message)


def _bundle_dispatch(model, config=False):
    """Clears the bundle's last traceback, then queues ScriptExecutor.Run(model) (or
    RunConfig for its config.py) on the dispatcher as a .NET delegate. Returns the
    DispatcherOperation."""
    _runtime()
    _wpf()
    from System import Action
    from System.Windows.Threading import Dispatcher, DispatcherPriority
    from PyNavis.Runtime.Bundles import PushButtonModel
    from PyNavis.Runtime.Execution import ScriptExecutor
    try:
        from PyNavis.Runtime.Ai import FailureLog
        FailureLog.Clear(model.Directory)
    except Exception:
        pass
    run = Action[PushButtonModel](ScriptExecutor.RunConfig if config else ScriptExecutor.Run)
    return Dispatcher.CurrentDispatcher.BeginInvoke(DispatcherPriority.Background, run, model)


def _operation_done(op):
    _wpf()
    from System.Windows.Threading import DispatcherOperationStatus
    return op.Status in (DispatcherOperationStatus.Completed, DispatcherOperationStatus.Aborted)


def _bundle_outcome(model):
    def outcome(op):
        try:
            from System.Windows.Threading import DispatcherOperationStatus
            if op.Status == DispatcherOperationStatus.Aborted:
                return False, 'The run was aborted.'
        except Exception:
            pass
        try:
            from PyNavis.Runtime.Ai import FailureLog
            if FailureLog.LastFor(model.Directory):
                return False, 'It stopped with an error; the output window has the details.'
        except Exception:
            pass
        return True, ''
    return outcome


def run_bundle(key_or_model, extension=None, on_done=None, timeout_s=15.0, start=True,
               config=False):
    """Runs a pyNavis bundle as soon as the RunGate is free (after the calling script
    returned); config=True runs its config.py (the Shift+Click action). Returns the Job
    (None when the bundle is unknown, toasted). on_done(job) replaces the default toast
    on timeout or failure."""
    model = key_or_model
    if isinstance(key_or_model, str):
        model = find_button(key_or_model, extension)
        if model is None:
            _toast('warning', 'That command is not loaded',
                   'Reload pyNavis if you just added it: %s' % key_or_model)
            return None
    label = flatten_title(_text(model.Title)) or 'That command'
    job = Job(label, gate_held, lambda: _bundle_dispatch(model, config), _operation_done,
              _bundle_outcome(model), timeout_s=timeout_s, on_done=on_done or _default_done)
    job.model = model
    if start:
        _start_timer(job)
    return job


def run_native(key_or_command, on_done=None, timeout_s=15.0, start=True):
    """Runs a native ribbon command once the RunGate is free. Returns the Job, or None
    when the key is unknown (toasted)."""
    command = key_or_command
    if isinstance(key_or_command, str):
        command = find_native(key_or_command)
        if command is None:
            _toast('warning', 'That Navisworks command was not found',
                   'It may sit on a tab that is not loaded: %s' % key_or_command)
            return None
    item = command['item']
    label = command.get('title') or _label_of(item)

    def dispatch():
        return execute_native(item, label)

    def outcome(result):
        return result
    job = Job(label, gate_held, dispatch, None, outcome, timeout_s=timeout_s,
              on_done=on_done or _default_done)
    job.command = command
    if start:
        _start_timer(job)
    return job


def schedule(job, interval_ms=50):
    """Starts ticking a Job built elsewhere (macros chain their own)."""
    return _start_timer(job, interval_ms)


def open_url(url):
    try:
        from pynavis import script
        script.open_url(url)
        return True
    except Exception:
        try:
            import os
            os.startfile(url)
            return True
        except Exception:
            return False


def run_link(plugin_id):
    """Executes another add-in (a *.linkbutton's plugin:). (ok, message)."""
    try:
        from System import Array, String
        from pynavis._api import Application
        if Application.Plugins.FindPlugin(plugin_id) is None:
            return False, 'The add-in %s is not loaded.' % plugin_id
        Application.Plugins.ExecuteAddInPlugin(plugin_id, Array[String]([]))
        return True, ''
    except Exception as error:
        return False, str(error)


def toggle_pane(key):
    """Shows or hides a pyNavis dock panel by bundle key. (ok, message)."""
    try:
        from pynavis import panes
        if panes.toggle(key):
            return True, ''
        return False, 'The panel has no slot yet. Add slots with Panel slots on the pyNavis tab.'
    except Exception as error:
        return False, str(error)


def reload():
    """pyNavis Reload (rescans extensions, rebuilds the ribbon and shortcuts)."""
    from pynavis import script
    script.reload_pynavis()


def user_config_path():
    """%APPDATA%\\pyNavis\\config.json as the runtime knows it."""
    try:
        return _text(_runtime().UserConfigPath)
    except Exception:
        import os
        return os.path.join(os.environ.get('APPDATA', ''), 'pyNavis', 'config.json')
