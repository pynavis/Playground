# -*- coding: utf-8 -*-
"""Macros: record pyNavis commands, play them back in order, manage them.

Recording: Record Macro turns a session flag on; hk_macro (after-command) appends every
pyNavis command that runs, with the time since the previous one, ignoring the macro
tools themselves and the Command Palette (a launcher, not a step). Native Navisworks
commands raise no pyNavis event, so they cannot be recorded from the ribbon; run them
from the Command Palette while recording (the palette adds them, and saved views and
selection sets too), or insert them in Manage Macros.

Storage: namo.templates tool 'macros' (team-shared whenever a shared folder is set).
A macro config is {'version': 1, 'steps': [step], 'stop_on_error': bool}; a step is
{'kind', 'title', 'gap'} plus, by kind: bundle {'key', 'extension'}, native {'key',
'path'}, view {'path'}, set {'path'}, pane {'key'}, url {'url'}, link {'plugin'},
wait {'seconds'}, confirm {'message'}.

Playback: a Player ticked by a DispatcherTimer. Before every step it waits until no
pyNavis script holds the RunGate; a command step runs through namo.ribbon (deferred,
so it starts from the message loop like a click) and the next waits for it to end.
Dialogs inside a step still ask the user. A step that raised stops the macro when
'stop_on_error' is on (the default), else it is counted and play goes on. Clicking
Play Macro while one plays offers to stop it.

Pure half: normalize_macro, step_label, describe, should_record, add_step, gap_of,
move_steps, delete_steps, insert_step, Player. API half: recording state, play,
play_named, stop, the Manage window.
"""
import copy
import time

from namo import camera, ribbon, session, templates, ui

TOOL = 'macros'
VERSION = 1
REC = 'macro_rec'
PLAY = 'macro_play'
KINDS = ('bundle', 'native', 'view', 'set', 'pane', 'url', 'link', 'wait', 'confirm')
COMMAND_KINDS = ('bundle', 'native', 'pane', 'url', 'link')
OWN_KEYS = (
    'Dev.tab/Automate.panel/Macro_Record.toggle',
    'Dev.tab/Automate.panel/Macros.pulldown/Play_Macro.pushbutton',
    'Dev.tab/Automate.panel/Macros.pulldown/Manage_Macros.pushbutton',
    'Dev.tab/Automate.panel/Macros.pulldown/Macro_to_Button.pushbutton',
    'Dev.tab/Automate.panel/Command_Palette.pushbutton',
)
MAX_WAIT = 600.0

# ---- pure -----------------------------------------------------------------------------


def should_record(key):
    """False for the macro tools and the palette (they are not steps)."""
    if not key:
        return False
    return not any(ribbon.same_key(key, own) for own in OWN_KEYS)


def gap_of(now, last):
    """Seconds since the previous step, one decimal, never negative."""
    if last is None:
        return 0.0
    return round(max(0.0, float(now) - float(last)), 1)


def _number(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_step(step):
    """A clean copy of one step, or None when it cannot be played."""
    if not isinstance(step, dict):
        return None
    kind = step.get('kind')
    if kind not in KINDS:
        return None
    out = {'kind': kind, 'title': str(step.get('title') or ''), 'gap': max(0.0, _number(step.get('gap')))}
    if kind == 'bundle':
        if not step.get('key'):
            return None
        out['key'] = str(step['key'])
        out['extension'] = str(step.get('extension') or '')
    elif kind in ('native', 'pane'):
        if not step.get('key'):
            return None
        out['key'] = str(step['key'])
        out['path'] = str(step.get('path') or '')
    elif kind in ('view', 'set'):
        if not step.get('path'):
            return None
        out['path'] = str(step['path'])
    elif kind == 'url':
        if not step.get('url'):
            return None
        out['url'] = str(step['url'])
    elif kind == 'link':
        if not step.get('plugin'):
            return None
        out['plugin'] = str(step['plugin'])
    elif kind == 'wait':
        out['seconds'] = min(MAX_WAIT, max(0.1, _number(step.get('seconds'), 1.0)))
    elif kind == 'confirm':
        out['message'] = str(step.get('message') or 'Continue the macro?')
    return out


def normalize_macro(config):
    """{'version', 'steps', 'stop_on_error'} with every playable step kept."""
    config = config if isinstance(config, dict) else {}
    steps = []
    for step in config.get('steps') or []:
        clean = normalize_step(step)
        if clean is not None:
            steps.append(clean)
    return {'version': VERSION, 'steps': steps,
            'stop_on_error': config.get('stop_on_error', True) is not False}


def _seconds(value):
    value = _number(value)
    if value == int(value):
        return '%d s' % int(value)
    return '%.1f s' % value


def step_label(step):
    """What a step reads as in lists: 'Clash Report', 'Wait 5 s', 'Go to view: Lobby'."""
    kind = step.get('kind')
    title = step.get('title') or ''
    if kind == 'bundle':
        return title or ribbon.title_from_folder(step.get('key', '').split('/')[-1])
    if kind == 'native':
        return 'Navisworks: %s' % (title or step.get('key'))
    if kind == 'view':
        return 'Go to view: %s' % (title or step.get('path'))
    if kind == 'set':
        return 'Select set: %s' % (title or step.get('path'))
    if kind == 'pane':
        return 'Show panel: %s' % (title or step.get('key'))
    if kind == 'url':
        return 'Open: %s' % (title or step.get('url'))
    if kind == 'link':
        return 'Run add-in: %s' % (title or step.get('plugin'))
    if kind == 'wait':
        return 'Wait %s' % _seconds(step.get('seconds'))
    if kind == 'confirm':
        return 'Ask to continue: %s' % step.get('message')
    return title or kind


def describe(config):
    macro = normalize_macro(config)
    count = len(macro['steps'])
    text = '%d step%s' % (count, '' if count == 1 else 's')
    if not macro['stop_on_error']:
        text += ', keeps going after an error'
    return text


def add_step(steps, step, now, last):
    """steps + [step with its gap]; returns the new 'last' time."""
    clean = normalize_step(dict(step, gap=gap_of(now, last)))
    if clean is not None:
        steps.append(clean)
    return now


def move_steps(steps, indices, delta):
    """(new steps, new indices) with the selected steps moved up (-1) or down (+1)
    together; a block at the edge stays put."""
    indices = sorted(set(i for i in indices if 0 <= i < len(steps)))
    if not indices or delta == 0:
        return list(steps), indices
    if (delta < 0 and indices[0] == 0) or (delta > 0 and indices[-1] == len(steps) - 1):
        return list(steps), indices
    out = list(steps)
    order = indices if delta < 0 else list(reversed(indices))
    for i in order:
        j = i + delta
        out[i], out[j] = out[j], out[i]
    return out, [i + delta for i in indices]


def delete_steps(steps, indices):
    gone = set(indices)
    return [s for i, s in enumerate(steps) if i not in gone]


def insert_step(steps, index, step):
    """steps with step inserted after index (at the start when index is None)."""
    clean = normalize_step(step)
    out = list(steps)
    if clean is None:
        return out, None
    position = 0 if index is None else min(len(out), index + 1)
    out.insert(position, clean)
    return out, position


class Player(object):
    """Plays steps in order. Injected: start_step(step) -> a ribbon.Job-like object
    (tick(), active, ok, message), or (ok, message) for an immediate step, or None when
    the target is missing; gate_held() -> bool; confirm(step) -> bool. on_finish(player)
    once at the end: player.state is 'done', 'failed', 'stopped' or 'cancelled';
    player.failures is [(step number, label, message)]."""

    def __init__(self, name, steps, stop_on_error, start_step, gate_held, confirm,
                 clock=None, on_finish=None):
        self.name = name
        self.steps = list(steps)
        self.stop_on_error = stop_on_error
        self.start_step = start_step
        self.gate_held = gate_held
        self.confirm = confirm
        self.clock = clock or time.time
        self.on_finish = on_finish
        self.index = 0
        self.job = None
        self.wait_until = None
        self.failures = []
        self.state = 'playing'

    @property
    def active(self):
        return self.state == 'playing'

    def stop(self):
        if self.active:
            if self.job is not None and getattr(self.job, 'active', False):
                try:
                    self.job.cancel()
                except Exception:
                    pass
            self._finish('stopped')

    def _finish(self, state):
        self.state = state
        if self.on_finish is not None:
            callback, self.on_finish = self.on_finish, None
            callback(self)

    def _failed(self, message):
        step = self.steps[self.index]
        self.failures.append((self.index + 1, step_label(step), message or 'It failed.'))
        if self.stop_on_error:
            self._finish('failed')
            return False
        self.index += 1
        return True

    def tick(self):
        if not self.active:
            return False
        if self.wait_until is not None:
            if self.clock() < self.wait_until:
                return True
            self.wait_until = None
            self.index += 1
        if self.job is not None:
            if self.job.active:
                self.job.tick()
            if self.job.active:
                return True
            job, self.job = self.job, None
            if not job.ok:
                return self._failed(job.message)
            self.index += 1
        if self.index >= len(self.steps):
            self._finish('done')
            return False
        if self.gate_held():
            return True
        step = self.steps[self.index]
        kind = step['kind']
        if kind == 'wait':
            self.wait_until = self.clock() + float(step.get('seconds') or 0)
            return True
        if kind == 'confirm':
            if not self.confirm(step):
                self._finish('cancelled')
                return False
            self.index += 1
            return True
        try:
            result = self.start_step(step)
        except Exception as error:
            return self._failed(str(error))
        if result is None:
            return self._failed('%s is not available here.' % step_label(step))
        if isinstance(result, tuple):
            ok, message = result
            if not ok:
                return self._failed(message)
            self.index += 1
            return True
        self.job = result
        return True


# ---- recording (session state) -----------------------------------------------------------


def _rec():
    return session.holder(REC)


def is_recording():
    return bool(getattr(_rec(), 'recording', False))


def start_recording():
    holder = _rec()
    holder.recording = True
    holder.steps = []
    holder.last = time.time()
    holder.started = holder.last


def stop_recording():
    """Turns recording off; returns the recorded steps (also kept as 'unsaved')."""
    holder = _rec()
    holder.recording = False
    steps = list(getattr(holder, 'steps', None) or [])
    holder.unsaved = steps
    holder.steps = []
    return steps


def unsaved_steps():
    return list(getattr(_rec(), 'unsaved', None) or [])


def forget_unsaved():
    _rec().unsaved = []


def _append(step):
    holder = _rec()
    if not getattr(holder, 'recording', False):
        return False
    steps = getattr(holder, 'steps', None)
    if steps is None:
        steps = []
        holder.steps = steps
    holder.last = add_step(steps, step, time.time(), getattr(holder, 'last', None))
    return True


def _was_config_run():
    """True when the command that just ended was a Shift+Click (its config.py). pyNavis
    raises after-command for those too, with the same bundle key; a settings dialog is
    not a step, and playing it back would run the tool itself instead."""
    try:
        import os
        from pynavis import script
        return os.path.basename(str(script.get_script_path() or '')).lower() == 'config.py'
    except Exception:
        return False


def record_command(key):
    """hk_macro: a pyNavis command ran (after-command). Fast and quiet."""
    if not is_recording() or not should_record(key) or _was_config_run():
        return False
    extension = ribbon.extension_of(key)
    model = ribbon.find_button(key, extension or None)
    title = ribbon.flatten_title(str(model.Title)) if model is not None else ''
    return _append({'kind': 'bundle', 'key': ribbon.normalize_key(key), 'extension': extension,
                    'title': title})


def step_from_entry(entry):
    """A step for a Command Palette entry (None for kinds hk_macro already records)."""
    kind = entry.get('kind')
    if kind == 'native':
        return {'kind': 'native', 'key': entry['key'], 'title': entry['title'], 'path': entry.get('path', '')}
    if kind in ('view', 'set'):
        return {'kind': kind, 'path': entry['target'], 'title': entry.get('name') or entry['title']}
    if kind == 'pane':
        return {'kind': 'pane', 'key': entry['key'], 'title': entry['title']}
    if kind == 'url':
        return {'kind': 'url', 'url': entry.get('url'), 'title': entry['title']}
    if kind == 'link':
        return {'kind': 'link', 'plugin': entry.get('plugin'), 'title': entry['title']}
    return None


def record_entry(entry):
    """The palette ran something pyNavis does not report: add it while recording."""
    if not is_recording():
        return False
    step = step_from_entry(entry)
    return _append(step) if step is not None else False


# ---- storage ------------------------------------------------------------------------------


def store():
    return templates.Templates(TOOL)


def names():
    return store().names()


def load(name):
    config = store().get(name)
    return None if config is None else normalize_macro(config)


def save(name, config):
    return store().save(name, normalize_macro(config))


# ---- playing ------------------------------------------------------------------------------


def _noop(job):
    return None


def view_path(folder, name):
    """The stored path of a saved viewpoint (namo.camera.view_path)."""
    return camera.view_path(folder, name)


def set_path(segments):
    """A pynavis.sets.find path: a literal '/' inside a name is written '\\/'."""
    return '/'.join(s.replace('/', '\\/') for s in segments)


def match_view(target, views):
    """The item of the first (folder_path, name, item) whose stored path is exactly
    target, or None. Exact first because viewpoint names often hold a slash themselves
    ('Level 1/2', 'North / East'), which a split-on-slash lookup can never find. The
    full lookup (exact path, then split, then bare name) is namo.camera.match_view."""
    for folder, name, item in views:
        if camera.view_path(folder, name) == target:
            return item
    return None


def match_set(target, rows):
    """The snapshot row (pynavis.sets.snapshot) of the first selection SET, never a
    folder, whose stored path is exactly target, or None. A bare name is also matched
    against sets inside folders, the way sets.find reads one."""
    names = {}
    loose = None
    for row in rows:
        names[row['key']] = row['name']
        if row.get('is_folder'):
            continue
        segments = []
        parent = row.get('parent_key') or ''
        while parent:
            segments.insert(0, names.get(parent, ''))
            parent = parent.rsplit('/', 1)[0] if '/' in parent else ''
        if set_path(segments + [row['name']]) == target:
            return row
        if loose is None and set_path([row['name']]) == target:
            loose = row
    return loose


def find_saved_view(target, doc=None):
    """The saved viewpoint a view step or palette entry names, or None."""
    return camera.find_view(target, doc)


def find_selection_set(target, doc=None):
    """The selection set (never a folder) a set step or palette entry names, or None."""
    from pynavis import sets
    from pynavis._api import Application
    document = doc if doc is not None else Application.ActiveDocument
    row = match_set(target, sets.snapshot(document))
    if row is None:
        return None
    try:
        node = document.SelectionSets.RootItem
        for index in row['key'].split('/'):
            node = node.Children[int(index)]
        return node
    except Exception as error:
        # The tree could not be walked by position: fall back to the library's lookup
        # by path, refusing a folder (a folder has no items to select).
        session.log('info', 'macros: selection set %s read by path: %s' % (target, error))
        from pynavis._api import Api
        found = sets.find(target, document)
        return None if found is None or isinstance(found, Api.FolderItem) else found


def start_step(step):
    """Starts one step for the Player (see Player)."""
    kind = step['kind']
    if kind == 'bundle':
        model = ribbon.find_button(step['key'], step.get('extension') or None)
        if model is None:
            return None
        return ribbon.run_bundle(model, step.get('extension') or None, on_done=_noop,
                                 timeout_s=MAX_WAIT, start=False)
    if kind == 'native':
        command = ribbon.find_native(step['key'])
        if command is None:
            return None
        return ribbon.run_native(command, on_done=_noop, timeout_s=MAX_WAIT, start=False)
    if kind == 'view':
        saved = find_saved_view(step['path'])
        if saved is None:
            return (False, 'The saved viewpoint %s is not in this model.' % step['path'])
        camera.recall(saved)
        return (True, '')
    if kind == 'set':
        found = find_selection_set(step['path'])
        if found is None:
            return (False, 'The selection set %s is not in this model.' % step['path'])
        from pynavis import sets
        sets.select(found)
        return (True, '')
    if kind == 'pane':
        try:
            from pynavis import panes
            return (bool(panes.show(step['key'])), 'That panel has no slot.')
        except Exception as error:
            return (False, str(error))
    if kind == 'url':
        return (ribbon.open_url(step['url']), 'Could not open %s.' % step['url'])
    if kind == 'link':
        return ribbon.run_link(step['plugin'])
    return None


def _confirm(step):
    from pynavis import forms
    return bool(forms.confirm(step.get('message') or 'Continue the macro?', title='Macro'))


def _toast(level, message, detail=None):
    try:
        from pynavis import toast
        toast.show(level, message, detail)
    except Exception:
        session.log('info', '%s %s' % (message, detail or ''))


def _finished(player):
    holder = session.holder(PLAY)
    if getattr(holder, 'player', None) is player:
        holder.player = None
    count = len(player.steps)
    if player.state == 'done':
        if player.failures:
            number, label, message = player.failures[0]
            _toast('warning', 'Macro %s finished with %d error%s' % (
                player.name, len(player.failures), '' if len(player.failures) == 1 else 's'),
                'Step %d, %s: %s' % (number, label, message))
        else:
            _toast('success', 'Macro %s finished' % player.name,
                   '%d step%s' % (count, '' if count == 1 else 's'))
    elif player.state == 'failed':
        number, label, message = player.failures[-1]
        _toast('error', 'Macro %s stopped at step %d' % (player.name, number),
               '%s: %s' % (label, message))
    elif player.state == 'stopped':
        _toast('info', 'Macro %s stopped' % player.name,
               'It ran %d of %d steps.' % (player.index, count))


def playing():
    """The active Player, or None."""
    player = getattr(session.holder(PLAY), 'player', None)
    if player is not None and getattr(player, 'active', False):
        return player
    return None


def play(name, config):
    """Starts playing a macro (after the calling script returns). Returns the Player."""
    macro = normalize_macro(config)
    player = Player(name, macro['steps'], macro['stop_on_error'], start_step, ribbon.gate_held,
                    _confirm, on_finish=_finished)
    session.holder(PLAY).player = player
    ribbon.schedule(player, 100)
    return player


def play_named(name):
    """For generated macro buttons: plays a stored macro by name, toasting problems."""
    config = load(name)
    if config is None:
        _toast('warning', 'There is no macro called %s' % name,
               'It was renamed or deleted. Make the button again with Macro to Button.')
        return None
    if not config['steps']:
        _toast('info', 'Macro %s has no steps' % name, 'Add steps in Manage Macros.')
        return None
    if playing() is not None:
        _toast('info', 'A macro is already playing', 'Click Play Macro to stop it first.')
        return None
    _toast('info', 'Playing macro %s' % name, describe(config))
    return play(name, config)


# ---- the Manage window ---------------------------------------------------------------------


def macro_rows(store_obj):
    rows = []
    for name in store_obj.names():
        info = store_obj.info(name) or {}
        config = normalize_macro(store_obj.get(name))
        rows.append({'value': name, 'cells': [name, len(config['steps']),
                                              (info.get('updated') or '').replace('T', ' ')[:16],
                                              info.get('user') or '']})
    return rows


def step_rows(steps):
    rows = []
    for index, step in enumerate(steps):
        gap = step.get('gap') or 0
        rows.append({'value': index, 'cells': [index + 1, step_label(step),
                                               ('after %s' % _seconds(gap)) if gap else '']})
    return rows


def command_choices(commands):
    """ui.choose rows for 'Add command': [{'value': step, 'cells': [title, where]}]."""
    rows = []
    for entry in commands:
        kind = entry.get('kind')
        if kind == 'bundle':
            step = {'kind': 'bundle', 'key': entry['key'], 'extension': entry.get('extension', ''),
                    'title': entry['title']}
        else:
            step = step_from_entry(entry)
        if step is None:
            continue
        rows.append({'value': step, 'cells': [step_label(step), entry.get('path') or '']})
    return rows


def build_manager(store_obj, commands_fn=None, select=None):
    """The Manage Macros window, unshown; window.Tag holds its parts. commands_fn() gives
    palette-style entries for 'Add command'."""
    ui.load_wpf()
    from System.Windows import GridLength, GridUnitType
    from System.Windows.Controls import (ColumnDefinition, Dock, DockPanel, Grid, Orientation,
                                         StackPanel, WrapPanel)
    logger = ui.pinned_logger()
    win = ui.window('Manage Macros', width=980, height=620, min_width=760, min_height=420)
    parts = ui.Bag(store=store_obj, name=None, config=None, play=None, logger=logger)
    win.Tag = parts

    macros_table = ui.Table(['Macro', 'Steps', 'Changed', 'By'], macro_rows(store_obj),
                            multiselect=False, logger=logger)
    steps_table = ui.Table(['#', 'Step', 'Recorded'], [], multiselect=True, logger=logger)
    parts.macros_table = macros_table
    parts.steps_table = steps_table
    title = ui.heading('Select a macro')
    stop_check = ui.check('Stop at the first step that fails')
    note = ui.hint('Native Navisworks commands cannot be recorded from the ribbon (they '
                   'send no event). Run them from the Command Palette while recording, '
                   'or add them here.')
    status = ui.hint('')
    parts.status = status

    def save_current(selected=None):
        if parts.name is None:
            return
        try:
            save(parts.name, parts.config)
        except (IOError, OSError) as error:
            # The shared folder went away, or the file is locked: say so, keep the edit
            # on screen so it can be saved by the next change.
            _toast('error', 'Could not save the macro %s' % parts.name, str(error))
        load_steps(selected)
        refresh_macros(parts.name)

    def load_steps(selected=None):
        steps = parts.config['steps'] if parts.config else []
        steps_table.update(step_rows(steps))
        if selected:
            steps_table.select_values(selected)
        update_buttons()

    def refresh_macros(keep=None):
        macros_table.update(macro_rows(store_obj))
        if keep:
            macros_table.select_values([keep])

    def macro_selected():
        values = macros_table.selected_values()
        name = values[0] if values else None
        if name == parts.name:
            update_buttons()
            return
        parts.name = name
        parts.config = load_from(store_obj, name) if name else None
        title.Text = name or 'Select a macro'
        stop_check.IsChecked = bool(parts.config['stop_on_error']) if parts.config else True
        load_steps()

    def update_buttons():
        has_macro = parts.config is not None
        chosen = steps_table.selected_values()
        for control in step_buttons:
            control.IsEnabled = has_macro
        for control in (up_button, down_button, delete_step_button):
            control.IsEnabled = has_macro and bool(chosen)
        for control in macro_buttons:
            control.IsEnabled = has_macro
        stop_check.IsEnabled = has_macro
        if has_macro:
            status.Text = '%s: %s' % (parts.name, describe(parts.config))
        else:
            count = len(store_obj.names())
            status.Text = ('%d macro%s' % (count, '' if count == 1 else 's')) if count else \
                'No macros yet. Record one with Record Macro, or import a file.'
        save_recording_button.IsEnabled = bool(unsaved_steps())

    macros_table.on_change = macro_selected
    steps_table.on_change = update_buttons

    def stop_changed(sender, args):
        if parts.config is not None and bool(stop_check.IsChecked) != parts.config['stop_on_error']:
            parts.config['stop_on_error'] = bool(stop_check.IsChecked)
            save_current(steps_table.selected_values())
    stop_check.Checked += ui.safe(stop_changed, 'macro stop on error', logger)
    stop_check.Unchecked += ui.safe(stop_changed, 'macro stop on error', logger)

    def move(delta):
        steps, chosen = move_steps(parts.config['steps'], steps_table.selected_values(), delta)
        parts.config['steps'] = steps
        save_current(chosen)

    def delete_chosen():
        chosen = steps_table.selected_values()
        if not chosen:
            return
        parts.config['steps'] = delete_steps(parts.config['steps'], chosen)
        save_current()

    def insert(step):
        chosen = steps_table.selected_values()
        anchor = max(chosen) if chosen else (len(parts.config['steps']) - 1 if parts.config['steps'] else None)
        steps, position = insert_step(parts.config['steps'], anchor, step)
        parts.config['steps'] = steps
        save_current([position] if position is not None else None)

    def add_wait():
        from pynavis import forms
        seconds = forms.ask_number('Seconds to wait before the next step:', default=2,
                                   min_value=0.1, max_value=MAX_WAIT, title='Add a pause')
        if seconds is not None:
            insert({'kind': 'wait', 'seconds': seconds})

    def add_confirm():
        from pynavis import forms
        message = forms.ask_string('Question to ask before going on (Yes continues, No stops):',
                                   default='Continue the macro?', title='Add a question')
        if message is not None and message.strip():
            insert({'kind': 'confirm', 'message': message.strip()})

    def add_command():
        entries = commands_fn() if commands_fn is not None else []
        rows = command_choices(entries)
        if not rows:
            _toast('info', 'No commands to add', 'Open a model, or reload pyNavis.')
            return
        picked = ui.choose('Add a command', rows, ['Command', 'Where'], multiselect=False,
                           prompt='Pick the command this step runs.')
        if picked:
            insert(picked[0])

    def rename():
        from pynavis import forms
        new = forms.ask_string('New name for %s:' % parts.name, default=parts.name, title='Rename macro')
        if new is None or not new.strip() or new.strip() == parts.name:
            return
        try:
            stored = store_obj.rename(parts.name, new.strip())
        except ValueError as error:
            _toast('warning', 'Could not rename the macro', str(error))
            return
        parts.name = None
        refresh_macros(stored)

    def duplicate():
        from namo import naming
        name = naming.unique('%s copy' % parts.name, store_obj.names())
        save(name, parts.config)
        refresh_macros(name)

    def delete_macro():
        from pynavis import forms
        if not forms.confirm('Delete the macro %s? Buttons made from it stop working.' % parts.name,
                             title='Delete macro'):
            return
        store_obj.delete(parts.name)
        parts.name = None
        parts.config = None
        refresh_macros()
        load_steps()

    def export():
        from pynavis import forms
        from namo import paths
        path = forms.save_file(filter='Playground macros (*.json)|*.json',
                               default_name=paths.safe_filename(parts.name) + '.json', title='Export macro')
        if path is None:
            return
        count = store_obj.export(path, [parts.name])
        _toast('success', 'Exported %d macro' % count, path)

    def import_file():
        from pynavis import forms
        path = forms.open_file(filter='Playground macros (*.json)|*.json', title='Import macros')
        if path is None:
            return
        try:
            count = store_obj.import_file(path)
        except ValueError as error:
            _toast('warning', 'Could not import macros', str(error))
            return
        refresh_macros()
        _toast('success', 'Imported %d macro%s' % (count, '' if count == 1 else 's'))

    def save_recording():
        from pynavis import forms
        from namo import naming
        steps = unsaved_steps()
        if not steps:
            return
        name = forms.ask_string('Name for the last recording (%d steps):' % len(steps),
                                default=naming.unique('Macro', store_obj.names()), title='Save recording')
        if name is None or not name.strip():
            return
        stored = save(name.strip(), {'steps': steps})
        forget_unsaved()
        refresh_macros(stored)

    def play_chosen():
        if parts.config is None or not parts.config['steps']:
            return
        parts.play = parts.name
        ui.close_with(win, True)

    up_button = ui.button('Move up', lambda: move(-1), 'secondary', logger)
    down_button = ui.button('Move down', lambda: move(1), 'secondary', logger)
    delete_step_button = ui.button('Remove', delete_chosen, 'secondary', logger)
    add_command_button = ui.button('Add command', add_command, 'secondary', logger)
    add_wait_button = ui.button('Add pause', add_wait, 'secondary', logger)
    add_confirm_button = ui.button('Add question', add_confirm, 'secondary', logger)
    step_buttons = [add_command_button, add_wait_button, add_confirm_button]
    rename_button = ui.button('Rename', rename, 'secondary', logger)
    duplicate_button = ui.button('Duplicate', duplicate, 'secondary', logger)
    delete_button = ui.button('Delete', delete_macro, 'secondary', logger)
    export_button = ui.button('Export', export, 'secondary', logger)
    import_button = ui.button('Import', import_file, 'secondary', logger)
    save_recording_button = ui.button('Save last recording', save_recording, 'secondary', logger)
    macro_buttons = [rename_button, duplicate_button, delete_button, export_button]
    play_button = ui.button('Play', play_chosen, 'primary', logger)
    macro_buttons.append(play_button)
    close_button = ui.button('Close', lambda: ui.close_with(win, False), 'secondary', logger)
    close_button.IsCancel = True

    def bar(controls):
        panel = WrapPanel()
        panel.Orientation = Orientation.Horizontal
        for index, control in enumerate(controls):
            control.Margin = ui.thickness(0, 8, 8, 0)
            panel.Children.Add(control)
        return panel

    left = DockPanel()
    left_bar = bar([rename_button, duplicate_button, delete_button, export_button, import_button,
                    save_recording_button])
    DockPanel.SetDock(left_bar, Dock.Bottom)
    left.Children.Add(left_bar)
    left.Children.Add(macros_table.element)

    right = DockPanel()
    head = StackPanel()
    head.Children.Add(title)
    stop_check.Margin = ui.thickness(0, 8, 0, 8)
    head.Children.Add(stop_check)
    DockPanel.SetDock(head, Dock.Top)
    right.Children.Add(head)
    tail = StackPanel()
    tail.Children.Add(bar([up_button, down_button, delete_step_button, add_command_button,
                           add_wait_button, add_confirm_button]))
    note.Margin = ui.thickness(0, 8, 0, 0)
    tail.Children.Add(note)
    DockPanel.SetDock(tail, Dock.Bottom)
    right.Children.Add(tail)
    right.Children.Add(steps_table.element)

    body = Grid()
    body.Margin = ui.thickness(16, 16, 16, 12)
    for width in (5, 7):
        column = ColumnDefinition()
        column.Width = GridLength(width, GridUnitType.Star)
        body.ColumnDefinitions.Add(column)
    left.Margin = ui.thickness(0, 0, 16, 0)
    Grid.SetColumn(left, 0)
    body.Children.Add(left)
    Grid.SetColumn(right, 1)
    body.Children.Add(right)

    footer = ui.footer([play_button, close_button], left=status, padding=16)
    layout = DockPanel()
    DockPanel.SetDock(footer, Dock.Bottom)
    layout.Children.Add(footer)
    layout.Children.Add(body)
    win.Content = layout

    parts.move = move
    parts.insert = insert
    parts.delete_chosen = delete_chosen
    parts.select_macro = lambda name: macros_table.select_values([name])
    parts.title = title
    parts.stop_check = stop_check
    load_steps()
    if select:
        macros_table.select_values([select])
    return win


def load_from(store_obj, name):
    config = store_obj.get(name)
    return None if config is None else normalize_macro(config)


def manage(commands_fn=None, select=None):
    """Shows Manage Macros; returns the name to play (Play pressed) or None."""
    win = build_manager(store(), commands_fn, select)
    ui.show_modal(win)
    return win.Tag.play


def snapshot_steps():
    """A deep copy of the steps being recorded right now (for tests and status)."""
    return copy.deepcopy(list(getattr(_rec(), 'steps', None) or []))
