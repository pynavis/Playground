# -*- coding: utf-8 -*-
"""Folder Watch: notices when an appended model's file changes on disk and offers a refresh.

No FileSystemWatcher (its events arrive on worker threads, and the Navisworks API may
only be touched on the UI thread): a DispatcherTimer on the UI thread compares the
modification time and size of every watched model file each interval (30 s by
default). A change is only reported once it has held still for two polls, so a file
that is still being written (an NWC export, a copy over the network) is not reported
half way. Offline network folders are skipped quietly (modelmgmt.reachable).

What is watched: the files of the appended models (the loaded file, usually the NWC,
and optionally the native source file it was made from) that lie inside the watched
folders. With no folders configured, the folders of the appended models are watched.

When something changed, a small notification window slides in at the bottom right of
Navisworks without taking focus: "3 models updated" with Refresh now (Document.
UpdateFiles), Later, and Show (opens the Source Files pane on the first one). Any
refresh, ours or Navisworks' own, re-reads the files as the new baseline, so the NWC
that a refresh regenerates is never reported as a change.

State lives in a session holder (the timer must outlive the click that started it).
Settings are shared by the toggle, its Shift+Click options and the hooks through
pynavis.settings under one explicit key, because hooks cannot use the bundle's own
script.get_config: {'folders', 'interval', 'watch_sources', 'remember', 'active'}.
'remember' restores watching at the next start of Navisworks when it was on.

The ribbon toggle's pressed state can only be set from the toggle's own run; when the
startup hook restores watching it sets the runtime's ToggleStateStore directly (best
effort) so the button shows the truth.
"""

import os

TOOL = 'playground_folderwatch'
DEFAULTS = {'folders': [], 'interval': 30, 'watch_sources': True, 'remember': False,
            'active': False}
TOGGLE_KEY = 'Project.tab/Models.panel/Folder_Watch.toggle'
NOTICE_KEY = 'playground-folderwatch-notice'
HOLDER = 'folderwatch'
MIN_INTERVAL = 10
MAX_INTERVAL = 600


# ---- pure: settings -------------------------------------------------------------------------


def normalize(values):
    """Settings with every key present and sane: folders a list of non-empty
    strings (duplicates removed, order kept), interval clamped to 10..600 s."""
    out = dict(DEFAULTS)
    out.update(values or {})
    folders = out.get('folders') or []
    if isinstance(folders, str):
        folders = folders.splitlines()
    clean = []
    seen = set()
    for folder in folders:
        text = str(folder or '').strip().strip('"')
        if text and text.lower() not in seen:
            seen.add(text.lower())
            clean.append(text)
    out['folders'] = clean
    try:
        interval = int(out.get('interval') or DEFAULTS['interval'])
    except (TypeError, ValueError):
        interval = DEFAULTS['interval']
    out['interval'] = max(MIN_INTERVAL, min(MAX_INTERVAL, interval))
    for key in ('watch_sources', 'remember', 'active'):
        out[key] = bool(out.get(key))
    return out


def load_config():
    try:
        from pynavis import settings
        return normalize(settings.load(TOOL, DEFAULTS))
    except Exception:
        return normalize({})


def save_config(values):
    from pynavis import settings
    settings.save(TOOL, normalize(values))


# ---- pure: what to watch ----------------------------------------------------------------------


def default_folders(infos):
    """Folders of the appended models' loaded files, sorted, no duplicates."""
    from namo import modelmgmt
    seen = {}
    for info in infos:
        folder = modelmgmt.folder_of(info.get('file') or info.get('source'))
        if folder:
            seen.setdefault(modelmgmt.norm_path(folder), folder)
    return [seen[k] for k in sorted(seen)]


def inside(path, folders_norm):
    """True when path lies in (or under) one of the normalised folders."""
    from namo import modelmgmt
    target = modelmgmt.norm_path(path)
    for folder in folders_norm:
        if target == folder or target.startswith(folder.rstrip(os.sep) + os.sep):
            return True
    return False


def watched_files(infos, folders=None, watch_sources=True):
    """[(path, model key, model name)] to poll: each model's loaded file and (with
    watch_sources) its source file, when they lie in the watched folders (all
    models' folders when folders is empty). A path shared by two models is listed
    once per model."""
    from namo import modelmgmt
    chosen = [modelmgmt.norm_path(f) for f in (folders or default_folders(infos))]
    out = []
    for info in infos:
        paths = [info.get('file')]
        if watch_sources and info.get('source') and \
                modelmgmt.norm_path(info.get('source')) != modelmgmt.norm_path(info.get('file')):
            paths.append(info.get('source'))
        for path in paths:
            if path and inside(path, chosen):
                out.append((path, info['key'], info['name']))
    return out


# ---- pure: the watcher ------------------------------------------------------------------------


class Watcher(object):
    """Turns successive file signatures into "changed and settled" reports.

    poll({path: signature}) returns the paths whose signature differs from the
    baseline AND was the same on the previous poll (two polls in a row). New paths
    join the baseline silently; 'offline' (and None) signatures are ignored until the
    folder answers again. rebase() takes the given signatures as the new normal."""

    def __init__(self):
        self.baseline = {}
        self.pending = {}

    def rebase(self, signatures):
        self.baseline = {}
        self.pending = {}
        for path, sig in signatures.items():
            if sig not in (None, 'offline'):
                self.baseline[path] = sig

    def forget_missing(self, paths):
        """Drops paths no longer watched (a model was removed)."""
        keep = set(paths)
        for table in (self.baseline, self.pending):
            for path in list(table):
                if path not in keep:
                    del table[path]

    def poll(self, signatures):
        settled = []
        for path in sorted(signatures):
            sig = signatures[path]
            if sig in (None, 'offline'):
                continue
            if path not in self.baseline:
                self.baseline[path] = sig
                self.pending.pop(path, None)
                continue
            if sig == self.baseline[path]:
                self.pending.pop(path, None)
                continue
            if self.pending.get(path) == sig:
                settled.append(path)
                self.baseline[path] = sig
                del self.pending[path]
            else:
                self.pending[path] = sig
        return settled


def changed_models(settled, files):
    """[(key, name)] of the models whose files settled, model order, each once."""
    by_path = {}
    for path, key, name in files:
        by_path.setdefault(path, []).append((key, name))
    hit = set()
    for path in settled:
        for key, _name in by_path.get(path, []):
            hit.add(key)
    out = []
    seen = set()
    for _path, key, name in files:
        if key in hit and key not in seen:
            seen.add(key)
            out.append((key, name))
    return out


def notice_texts(names, limit=5):
    """(title, lines) for the notification: '3 models updated' and their names."""
    from namo import modelmgmt
    count = len(names)
    title = '%s updated' % modelmgmt.plural(count, 'model')
    lines = list(names[:limit])
    if count > limit:
        lines.append('and %d more' % (count - limit))
    return title, lines


def status_texts(config, files, folders):
    """(message, detail) for the toast when watching starts."""
    from namo import modelmgmt
    if not files:
        return ('Folder Watch is on', 'Nothing to watch yet: models you append from now on are '
                'watched. Checks every %d s.' % config['interval'])
    return ('Folder Watch is on', 'Watching %s in %s; checks every %d s.'
            % (modelmgmt.plural(len(files), 'model file'), modelmgmt.plural(len(folders), 'folder'),
               config['interval']))


# ---- API half: the live watcher ------------------------------------------------------------------


def holder():
    from namo import session
    return session.holder(HOLDER)


def is_on():
    return bool(getattr(holder(), 'on', False))


def _log(message, level='error'):
    try:
        from namo import session
        session.log(level, 'Folder Watch: %s' % message)
    except Exception:
        pass


def _doc():
    from pynavis._api import Application
    return Application.ActiveDocument


def _infos():
    from namo import modelmgmt
    document = _doc()
    if document is None:
        return []
    try:
        return modelmgmt.models_info(document)
    except Exception:
        return []


def _signatures(files):
    from namo import modelmgmt
    out = {}
    for path, _key, _name in files:
        if path not in out:
            out[path] = modelmgmt.signature(path)
    return out


def _current_files(config):
    infos = _infos()
    return infos, watched_files(infos, config['folders'], config['watch_sources'])


def sync_toggle(on):
    """Best effort: sets the ribbon toggle's pressed state from outside its own run
    (the runtime's public ToggleStateStore). Never raises."""
    try:
        import clr
        clr.AddReference('PyNavis.Runtime')
        from PyNavis.Runtime.Ribbon import ToggleStateStore
        ToggleStateStore.Set(TOGGLE_KEY, bool(on))
        return True
    except Exception:
        return False


def rebase():
    """Takes the current files as the new normal (after a refresh, an append, a new
    document). Never raises."""
    held = holder()
    watcher = getattr(held, 'watcher', None)
    if watcher is None:
        return
    try:
        config = getattr(held, 'config', None) or load_config()
        infos, files = _current_files(config)
        watcher.rebase(_signatures(files))
        held.files = files
        held.model_keys = [i['key'] for i in infos]
        held.changed = []
    except Exception as error:
        _log('rebase failed: %s' % error)


def start(config=None, logger=None):
    """Starts watching (or restarts with new settings). Returns {'ok', 'message',
    'detail', 'level'} for a toast."""
    from namo import ui
    ui.load_wpf()       # WindowsBase is not referenced in a fresh engine (startup hook)
    from System import TimeSpan
    from System.Windows.Threading import DispatcherPriority, DispatcherTimer
    held = holder()
    config = normalize(config or load_config())
    stop(save=False, quiet=True)
    held.config = config
    held.logger = logger if logger is not None else ui.pinned_logger()
    held.watcher = Watcher()
    held.changed = []
    held.document = None
    timer = DispatcherTimer(DispatcherPriority.Background)
    timer.Interval = TimeSpan.FromSeconds(config['interval'])
    held.tick_handler = ui.safe(lambda *args: tick(), 'Folder Watch tick', held.logger)
    timer.Tick += held.tick_handler
    held.timer = timer
    held.on = True
    rebase()
    _watch_document(_doc())
    timer.Start()
    config['active'] = True
    try:
        save_config(config)
    except Exception as error:
        _log('could not save settings: %s' % error, 'warning')
    files = getattr(held, 'files', []) or []
    folders = config['folders'] or default_folders(_infos())
    message, detail = status_texts(config, files, folders)
    return {'ok': True, 'level': 'success', 'message': message, 'detail': detail}


def stop(save=True, quiet=False):
    """Stops the timer and closes the notice. save=True records 'active' False (the
    user switched it off); the app-closing hook stops with save=False so 'remember'
    can bring it back next time."""
    held = holder()
    timer = getattr(held, 'timer', None)
    if timer is not None:
        try:
            timer.Stop()
        except Exception:
            pass
        try:
            timer.Tick -= held.tick_handler
        except Exception:
            pass
    held.timer = None
    _watch_document(None)
    close_notice()
    held.on = False
    if save:
        try:
            config = load_config()
            config['active'] = False
            save_config(config)
        except Exception as error:
            _log('could not save settings: %s' % error, 'warning')
    return True


def _watch_document(document):
    """Follows Navisworks' own refreshes: FilesUpdated on the watched document rebases."""
    held = holder()
    old = getattr(held, 'document', None)
    handler = getattr(held, 'files_updated', None)
    if old is document:
        return
    if old is not None and handler is not None:
        try:
            old.FilesUpdated -= handler
        except Exception:
            pass
    held.document = document
    if document is None:
        return
    if handler is None:
        from namo import ui
        handler = ui.safe(lambda *args: rebase(), 'Folder Watch files updated',
                          getattr(held, 'logger', None))
        held.files_updated = handler
    try:
        document.FilesUpdated += handler
    except Exception as error:
        _log('could not follow refreshes: %s' % error, 'warning')


def tick():
    """One poll (the timer calls it on the UI thread)."""
    held = holder()
    if not getattr(held, 'on', False):
        return
    document = _doc()
    if document is not getattr(held, 'document', None):
        _watch_document(document)
        rebase()
        return
    config = held.config
    infos, files = _current_files(config)
    keys = [i['key'] for i in infos]
    if keys != getattr(held, 'model_keys', None):
        # models appended or removed: new files join the baseline quietly
        held.model_keys = keys
        held.watcher.forget_missing([p for p, _k, _n in files])
    held.files = files
    settled = held.watcher.poll(_signatures(files))
    if not settled:
        return
    fresh = changed_models(settled, files)
    pending = list(getattr(held, 'changed', []) or [])
    known = set(k for k, _n in pending)
    for key, name in fresh:
        if key not in known:
            pending.append((key, name))
    held.changed = [p for p in pending if p[0] in set(keys)]
    if held.changed:
        show_notice(held.changed)


# ---- the notification window -------------------------------------------------------------------


def build_notice(changed, on_refresh, on_later, on_show, logger=None):
    """The unshown notification window for [(key, name)] changes."""
    from namo import ui
    ui.load_wpf()
    from System.Windows import Thickness, WindowStartupLocation
    from System.Windows.Controls import DockPanel, Dock, StackPanel
    title, lines = notice_texts([n for _k, n in changed])
    win = ui.window(title, width=360, height=None, resizable=False)
    win.WindowStartupLocation = WindowStartupLocation.Manual
    win.Topmost = False
    body = StackPanel()
    body.Margin = Thickness(16, 14, 16, 12)
    body.Children.Add(ui.heading(title))
    hint = ui.hint('Their files changed on disk since they were loaded.')
    hint.Margin = Thickness(0, 4, 0, 8)
    body.Children.Add(hint)
    for line in lines:
        item = ui.text(line, 13, wrap=False)
        item.Margin = Thickness(0, 0, 0, 2)
        body.Children.Add(item)
    refresh = ui.button('Refresh now', on_refresh, 'primary', logger)
    later = ui.button('Later', on_later, 'secondary', logger)
    show = ui.button('Show', on_show, 'quiet', logger)
    later.IsCancel = True
    bar = ui.footer([refresh, later], left=show, padding=16)
    layout = DockPanel()
    DockPanel.SetDock(bar, Dock.Bottom)
    layout.Children.Add(bar)
    layout.Children.Add(body)
    win.Content = layout
    win.Tag = {'refresh': refresh, 'later': later, 'show': show, 'title': title, 'lines': lines}
    return win


def _place(win):
    from namo import ui
    try:
        scale = ui.dpi_scale(win) or 1.0
        left, top, right, bottom = ui.host_rect()
        host = (left / scale, top / scale, right / scale, bottom / scale)
        x, y = ui.place_rect(host, (win.ActualWidth or 360.0, win.ActualHeight or 180.0),
                             'bottom-right', margin=24)
        win.Left = x
        win.Top = y
    except Exception as error:
        _log('could not place the notice: %s' % error, 'warning')


def close_notice():
    try:
        from namo import ui
        ui.Modeless.close(NOTICE_KEY)
    except Exception:
        pass


def show_notice(changed):
    """Shows (or replaces) the non-activating notification for the changed models."""
    from namo import ui
    held = holder()
    logger = getattr(held, 'logger', None)
    close_notice()

    def refresh_clicked():
        close_notice()
        refresh_now()

    def later_clicked():
        close_notice()

    def show_clicked():
        close_notice()
        from namo import sourcefiles
        try:
            from pynavis import panes
            panes.show(sourcefiles.PANE_KEY)
        except Exception as error:
            _log('could not open Source Files: %s' % error, 'warning')
        if changed:
            sourcefiles.show_model(changed[0][0])

    def builder(win):
        ui.non_activating(win)
        win.Loaded += ui.safe(lambda *args: _place(win), 'Folder Watch place', logger)
        return None

    def factory():
        return build_notice(changed, refresh_clicked, later_clicked, show_clicked, logger)

    try:
        ui.Modeless(NOTICE_KEY, 'Models updated', builder, window_factory=factory).show()
    except Exception as error:
        _log('could not show the notice: %s' % error)


def refresh_now():
    """Document.UpdateFiles, then a new baseline; toasts the outcome."""
    from namo import modelmgmt
    held = holder()
    names = [n for _k, n in (getattr(held, 'changed', []) or [])]
    try:
        updated = modelmgmt.refresh_files(_doc())
    except Exception as error:
        _toast('error', 'Could not refresh the models', str(error) or type(error).__name__)
        return
    rebase()
    if updated:
        _toast('success', 'Refreshed %s' % modelmgmt.plural(len(names), 'model') if names
               else 'Refreshed the changed models', modelmgmt.join_names(names) or None)
    else:
        _toast('info', 'Nothing needed refreshing', 'Navisworks found no newer files.')


def _toast(level, message, detail=None):
    try:
        from pynavis import toast
        toast.show(level, message, detail)
    except Exception:
        pass
