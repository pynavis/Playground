# -*- coding: utf-8 -*-
"""Presentation Mode: a clean screen for a meeting, put back exactly afterwards.

On: the ribbon minimises to its tab row (AdWindows RibbonControl.AutoHideMode
= HidePanelBar, the state the ribbon's own minimise button sets), visible
add-in dock panels close (DockPanePlugin.Visible on each loaded dock panel
plugin, the switch pyNavis' own panel buttons use; the native Selection Tree
and Properties windows have no API and stay), the main
window maximises (user32 ShowWindow), and optionally the background switches
to a preset. Off (leave): each of those goes back to what it was, and only if it was
changed.

The state lives in an AppDomain slot as JSON text, not in a Python module:
Reload rebuilds pyNavis' engine and drops every module, and a state nobody
can read again would strand the user. Each change is written to the slot as
it happens, so even a half-finished entry can be undone.

It can never leave anyone stuck: with the ribbon minimised a click on the
Model tab still opens the panel with Exit Presentation on it, the
Exit_Presentation shortcut (Ctrl+Alt+F11) restores from anywhere, and the
ribbon's own minimise button or a double-click on any tab brings it back
even without Playground.

The pure half is tested on both engines; the API half lazy-imports .NET.
"""

import json

SLOT = 'Playground.PresentationMode'
DEFAULTS = {'panes': True, 'maximize': True, 'background': ''}
HIDE_MODE = 'HidePanelBar'
SW_MAXIMIZE = 3
SW_RESTORE = 9


# =============================================================================
# Pure half
# =============================================================================


def normalize_options(values):
    """{'panes': bool, 'maximize': bool, 'background': preset name or ''}."""
    from namo import look_tools
    values = values or {}
    background = str(values.get('background') or '')
    if background and look_tools.background_named(background) is None:
        background = ''
    return {'panes': bool(values.get('panes', DEFAULTS['panes'])),
            'maximize': bool(values.get('maximize', DEFAULTS['maximize'])),
            'background': background}


def option_fields(values):
    from namo import look_tools
    opts = normalize_options(values)
    return [
        {'kind': 'label', 'text': 'The ribbon always shrinks to its tabs. Choose what else changes.'},
        {'kind': 'check', 'key': 'panes', 'label': 'Close add-in panels while presenting',
         'default': opts['panes']},
        {'kind': 'check', 'key': 'maximize', 'label': 'Maximize the Navisworks window',
         'default': opts['maximize']},
        {'kind': 'choice', 'key': 'background', 'label': 'Background while presenting',
         'options': [('Keep the current background', '')] +
                    [(spec['name'], spec['name']) for spec in look_tools.BACKGROUNDS],
         'default': opts['background'], 'fallback': None},
    ]


def encode(state):
    """The slot text for a state dict (sorted keys: stable on every engine)."""
    return json.dumps(state, sort_keys=True)


def decode(text):
    """The state dict from slot text, or None for anything unreadable."""
    if not text:
        return None
    try:
        value = json.loads(str(text))
    except (TypeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def new_state():
    """What enter() records: what it changed and the value to put back.
    'ribbon' the AutoHideMode name before, 'panes' dock plugin ids it closed,
    'window' True when it maximised, 'background' the background before."""
    return {'version': 1, 'on': True, 'ribbon': None, 'panes': [], 'window': False,
            'background': None}


def changed(state):
    """True when enter() changed anything that leave() must put back."""
    return bool(state and (state.get('ribbon') is not None or state.get('panes') or state.get('window')
                           or state.get('background') is not None))


def nothing_message(notes):
    """(message, detail) when there was nothing to change."""
    return ('Nothing to change for presenting',
            notes[0] if notes else 'The ribbon is already minimized and the window maximized.')


def enter_message(state, notes):
    """(message, detail) after turning presentation mode on."""
    changed = []
    if state.get('ribbon') is not None:
        changed.append('ribbon minimized')
    if state.get('panes'):
        changed.append('%d panel%s closed' % (len(state['panes']), '' if len(state['panes']) == 1 else 's'))
    if state.get('window'):
        changed.append('window maximized')
    if state.get('background') is not None:
        changed.append('background changed')
    detail = 'Ctrl+Alt+F11 or the Exit Presentation button puts everything back.'
    if notes:
        detail = notes[0] + ' ' + detail
    message = 'Presentation mode on'
    if changed:
        message += ': ' + ', '.join(changed)
    return message, detail


def exit_message(restored, problems):
    """(level, message, detail) after turning it off."""
    if problems:
        return ('warning', 'Presentation mode off, with a problem', problems[0])
    if restored:
        return ('success', 'Presentation mode off', 'Restored the %s.' % _join(restored))
    return ('success', 'Presentation mode off', 'Nothing needed restoring.')


def _join(parts):
    if len(parts) == 1:
        return parts[0]
    return '%s and %s' % (', '.join(parts[:-1]), parts[-1])


# =============================================================================
# API half
# =============================================================================


def _slot_read():
    from System import AppDomain
    return decode(AppDomain.CurrentDomain.GetData(SLOT))


def _slot_write(state):
    from System import AppDomain
    AppDomain.CurrentDomain.SetData(SLOT, None if state is None else encode(state))


def is_on():
    """True while presentation mode holds changes to put back."""
    try:
        state = _slot_read()
    except Exception:
        return False
    return bool(state and state.get('on'))


def _ribbon():
    import clr
    clr.AddReference('AdWindows')
    from Autodesk.Windows import ComponentManager
    return ComponentManager.Ribbon


def _hide_mode(name):
    import clr
    clr.AddReference('AdWindows')
    from Autodesk.Internal.Windows import RibbonAutoHideMode
    return getattr(RibbonAutoHideMode, name)


def _main_hwnd():
    try:
        from pynavis._api import Application
        handle = Application.Gui.MainWindow.Handle
        hwnd = int(handle.ToInt64())
        if hwnd:
            return hwnd
    except Exception:
        pass
    from System.Diagnostics import Process
    return int(Process.GetCurrentProcess().MainWindowHandle.ToInt64())


def _is_zoomed(hwnd):
    import ctypes
    return bool(ctypes.windll.user32.IsZoomed(ctypes.c_void_p(hwnd)))


def _show_window(hwnd, command):
    import ctypes
    ctypes.windll.user32.ShowWindow(ctypes.c_void_p(hwnd), int(command))


def _pane(pane_id):
    """The loaded dock panel plugin with this id, or None. Never loads one: a
    panel nobody opened this session has nothing to close."""
    from pynavis._api import Application
    record = Application.Plugins.FindPlugin(str(pane_id))
    if record is None or not record.IsLoaded:
        return None
    plugin = record.LoadedPlugin
    return plugin if hasattr(plugin, 'Visible') and hasattr(plugin, 'ActivatePane') else None


def _visible_panes():
    """Ids of loaded dock panel plugins showing now."""
    from pynavis._api import Application
    out = []
    for record in Application.Plugins.PluginRecords:
        try:
            if not record.IsLoaded:
                continue
            pane_id = str(record.Id)
            plugin = _pane(pane_id)
            if plugin is not None and plugin.Visible:
                out.append(pane_id)
        except Exception:
            continue
    return sorted(out)


def _set_pane(pane_id, visible):
    """Shows or closes one dock panel; raises when it is gone."""
    plugin = _pane(pane_id)
    if plugin is None:
        raise LookupError('dock panel %s is not loaded' % pane_id)
    plugin.Visible = bool(visible)


def enter(options):
    """Turns presentation mode on. Returns (state, notes): notes are sentences
    about what could not be changed."""
    from namo import look_tools, session
    opts = normalize_options(options)
    state = new_state()
    notes = []
    _slot_write(state)
    try:
        ribbon = _ribbon()
        before = str(ribbon.AutoHideMode)
        if before != HIDE_MODE:
            ribbon.AutoHideMode = _hide_mode(HIDE_MODE)
            state['ribbon'] = before            # recorded even if it did not take: leave() sets it back
            _slot_write(state)
            if str(ribbon.AutoHideMode) != HIDE_MODE:
                session.log('warning', 'presentation mode: ribbon stayed %s' % ribbon.AutoHideMode)
                notes.append('The ribbon did not minimize.')
    except Exception as error:
        session.log('warning', 'presentation mode: ribbon not minimized: %s' % error)
        notes.append('The ribbon could not be minimized.')
    if opts['panes']:
        try:
            for pane_id in _visible_panes():
                try:
                    _set_pane(pane_id, False)
                    state['panes'].append(pane_id)
                    _slot_write(state)
                except Exception as error:
                    session.log('warning', 'presentation mode: panel %s not closed: %s' % (pane_id, error))
        except Exception as error:
            session.log('warning', 'presentation mode: panels not read: %s' % error)
    if opts['maximize']:
        try:
            hwnd = _main_hwnd()
            if hwnd and not _is_zoomed(hwnd):
                _show_window(hwnd, SW_MAXIMIZE)
                state['window'] = True
                _slot_write(state)
        except Exception as error:
            session.log('warning', 'presentation mode: window not maximized: %s' % error)
            notes.append('The window could not be maximized.')
    if opts['background']:
        current = look_tools.read_background()
        if current is None:
            notes.append('The background stayed: Navisworks did not report the current one, '
                         'so it could not be put back afterwards.')
        else:
            try:
                look_tools.set_background(look_tools.background_named(opts['background']))
                state['background'] = current
                _slot_write(state)
            except Exception as error:
                session.log('warning', 'presentation mode: background not set: %s' % error)
    return state, notes


def leave():
    """Puts back everything enter() changed. Returns (restored, problems):
    restored names what came back, problems are sentences. The slot is
    cleared even when something refuses, so a second Exit never repeats a
    half restore; what refused is named instead."""
    from namo import look_tools, session
    state = _slot_read()
    if not state:
        return [], []
    restored = []
    problems = []
    if state.get('ribbon') is not None:
        try:
            _ribbon().AutoHideMode = _hide_mode(state['ribbon'])
            restored.append('ribbon')
        except Exception as error:
            session.log('error', 'presentation mode: ribbon not restored: %s' % error)
            problems.append('The ribbon stayed minimized: double-click a ribbon tab to bring it back.')
    if state.get('panes'):
        try:
            back = 0
            for pane_id in state['panes']:
                try:
                    _set_pane(pane_id, True)
                    back += 1
                except Exception as error:
                    session.log('warning', 'presentation mode: panel %s not reopened: %s' % (pane_id, error))
            if back:
                restored.append('panels')
            if back < len(state['panes']):
                problems.append('Some panels stayed closed: open them again from their buttons.')
        except Exception as error:
            session.log('error', 'presentation mode: panels not restored: %s' % error)
            problems.append('The panels stayed closed: open them again from their buttons.')
    if state.get('window'):
        try:
            hwnd = _main_hwnd()
            if hwnd and _is_zoomed(hwnd):
                _show_window(hwnd, SW_RESTORE)
            restored.append('window size')
        except Exception as error:
            session.log('warning', 'presentation mode: window not restored: %s' % error)
    if state.get('background') is not None:
        try:
            look_tools.set_background(state['background'])
            restored.append('background')
        except Exception as error:
            session.log('warning', 'presentation mode: background not restored: %s' % error)
            problems.append('The background stayed: set it back with the Background button.')
    _slot_write(None)
    return restored, problems
