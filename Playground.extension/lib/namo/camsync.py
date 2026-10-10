# -*- coding: utf-8 -*-
"""Camera Sync: the camera mirrored live between Navisworks sessions on this machine
(two model versions side by side, an NWD next to its NWF, a federation next to one
trade model).

Protocol (one small JSON file per session, %APPDATA%\\pyNavis\\playground\\camsync\\<pid>.json,
always written atomically):
    {'format': 'playground-camsync', 'version': 1, 'pid', 'started' (epoch seconds when
     this Sync was switched on), 'seq' (counts up per write, from 1 for every Sync),
     'time' (epoch seconds), 'title' (document title), 'units' (document units),
     'camera': namo.camera dict (position, rotation, lens, Viewpoint.GetCamera json)
               or None for a presence-only file}

Writing: CurrentViewpoint.Changed (a direct subscription, so it keeps working while
other pyNavis tools run) marks the camera dirty; a 40 ms DispatcherTimer writes once
the camera has been still for 80 ms, or every 250 ms while it keeps moving, so the
other window follows an orbit instead of waiting for it to end.

Reading: a 120 ms DispatcherTimer lists the folder, ignores files of sessions that
are no longer running (and deletes them; liveness is asked once a second per pid),
and applies the newest other session's camera when it is new: another 'started'
(the other window switched Camera Sync off and on, so its seq began again) or a
higher seq. TrySetCamera(json) on a CreateCopy of the current view and
one CurrentViewpoint.CopyFrom; when the other model is in other units, or Navisworks
refuses the json, the camera dict is converted and written instead.

Echo loops: an 'applying' flag covers the CopyFrom itself, and the camera as it
stands right after an apply is remembered: a write that would only send that same
camera back is skipped, however late Navisworks raises Changed. Never a worker
thread; every late callback is wrapped and logged. stop() (toggle off), a fresh
start() (also after Reload) and shutdown() (app closing, via hk_camsync) stop both
timers, unhook both events and delete this session's file. The running Sync's stop
is also parked in an AppDomain slot (the way pyNavis' Hide Tabs parks its tabs), so
a start() in an engine that lost the session holder still stops the old timers
instead of running two Syncs side by side.
"""
import json
import os
import time

FORMAT = 'playground-camsync'
VERSION = 1
POLL_MS = 120
WRITE_TICK_MS = 40
DELAY_S = 0.08
MAX_WAIT_S = 0.25
FRESH_S = 2.0               # a file touched this recently is read whatever its stamp says
WRITE_RETRIES = 5           # a failed camera write is tried again this many times
ALIVE_S = 1.0               # how long one "is that process running" answer is trusted
HOLDER = 'camsync'
SLOT = 'Playground.CameraSync'


# ---- pure ---------------------------------------------------------------------------


def file_name(pid):
    return '%d.json' % int(pid)


def pid_of(name):
    """The pid in '<pid>.json', or None."""
    base = os.path.basename(str(name))
    if not base.lower().endswith('.json'):
        return None
    stem = base[:-5]
    return int(stem) if stem.isdigit() else None


def _plain(value):
    if isinstance(value, tuple):
        return [_plain(v) for v in value]
    if isinstance(value, list):
        return [_plain(v) for v in value]
    return value


def message(pid, seq, cam, units, title='', now=None, started=0.0):
    """The message dict a session writes."""
    clean = None
    if cam is not None:
        clean = dict((k, _plain(v)) for k, v in cam.items())
    return {'format': FORMAT, 'version': VERSION, 'pid': int(pid), 'seq': int(seq),
            'started': float(started or 0.0),
            'time': float(now if now is not None else time.time()), 'title': str(title or ''),
            'units': str(units or 'Meters'), 'camera': clean}


def dumps(msg):
    return json.dumps(msg, sort_keys=True)


def parse(text):
    """A message dict from file text, or None when it is not a valid one (a torn
    read, another format, a camera without position or rotation)."""
    try:
        data = json.loads(text)
    except Exception:
        return None
    if not isinstance(data, dict) or data.get('format') != FORMAT:
        return None
    try:
        data['pid'] = int(data['pid'])
        data['seq'] = int(data['seq'])
        data['time'] = float(data.get('time') or 0.0)
        data['started'] = float(data.get('started') or 0.0)
    except (KeyError, TypeError, ValueError):
        return None
    cam = data.get('camera')
    if cam is not None:
        if not isinstance(cam, dict):
            return None
        pos, rot = cam.get('position'), cam.get('rotation')
        if not pos or not rot or len(pos) != 3 or len(rot) != 4:
            return None
    return data


def pick_partner(entries, own_pid, alive):
    """The newest entry {'pid', 'mtime', ...} of another live session, or None.
    alive(pid) says whether that session still runs."""
    best = None
    for entry in entries:
        pid = entry.get('pid')
        if pid is None or pid == own_pid or not alive(pid):
            continue
        if best is None or (entry.get('mtime') or 0) > (best.get('mtime') or 0):
            best = entry
    return best


def stamp_of(msg):
    """(started, seq): what `seen` remembers per pid."""
    return (float(msg.get('started') or 0.0), int(msg['seq']))


def should_apply(msg, seen):
    """True when msg carries a camera newer than the last one applied from that
    session (seen: {pid: (started, seq)}). seq begins again at 1 whenever the other
    window switches Camera Sync off and on (same pid, a new 'started'), so a lower
    seq from a later start is new too; comparing seq alone would leave this window
    deaf to that one until its count passed the old one."""
    if msg is None or msg.get('camera') is None:
        return False
    last = seen.get(msg['pid'])
    if last is None:
        return True
    started, seq = stamp_of(msg)
    if started != last[0]:
        return True
    return seq > last[1]


def file_changed(stamp, last, now, fresh=FRESH_S):
    """Whether a partner file is worth reading: its (mtime, size) differs from the
    one read last, or it was written within `fresh` seconds (two writes can share a
    stamp where file times are coarse, and the size barely changes)."""
    if stamp != last:
        return True
    return (float(now) - float(stamp[0])) < fresh


def write_due(now, first_change, last_change, delay=DELAY_S, max_wait=MAX_WAIT_S):
    """Whether a pending camera write should go now: the camera has been still for
    `delay`, or has kept moving for `max_wait` since the first unsent change."""
    if first_change is None or last_change is None:
        return False
    return (now - last_change) >= delay or (now - first_change) >= max_wait


def convert(cam, from_units, to_units):
    """The camera in to_units (lengths scaled; Navisworks' json dropped when the
    units differ, since it cannot be rescaled)."""
    from namo import vp_common, vpexport
    k = vp_common.unit_factor(from_units, to_units)
    if abs(k - 1.0) < 1e-12:
        return dict(cam)
    return vpexport.scale_camera(cam, k)


def status_text(partner):
    """(message, detail) for the start toast."""
    if partner is None:
        return ('Waiting for another session', 'Turn on Camera Sync in the other Navisworks window too.')
    detail = partner.get('title') or ''
    return ('Syncing with Navisworks (PID %d)' % partner['pid'], detail or None)


# ==== live half (Navisworks, UI thread only) =========================================


def own_pid():
    try:
        return int(os.getpid())
    except Exception:
        from System.Diagnostics import Process
        return int(Process.GetCurrentProcess().Id)


def folder():
    from namo import paths
    return paths.ensure_dir(os.path.join(paths.data_root(), 'camsync'))


def process_alive(pid):
    """True while a process with that pid runs Navisworks (Roamer)."""
    try:
        from System.Diagnostics import Process
        process = Process.GetProcessById(int(pid))
    except Exception:
        return False
    try:
        if process.HasExited:
            return False
        name = str(process.ProcessName or '').lower()
        return 'roamer' in name or not name
    except Exception:
        return True


def holder():
    from namo import session
    return session.holder(HOLDER)


def current():
    """The running Sync, or None."""
    sync = getattr(holder(), 'sync', None)
    if sync is not None and getattr(sync, 'running', False):
        return sync
    return None


def is_running():
    return current() is not None


class Sync(object):
    """One session's camera sync. Lives on the session holder between runs."""

    def __init__(self, log=None, alive=None, root=None):
        # Modules bound now, during the toggle's run: the timer callbacks fire long
        # after it, when pyNavis may have swept lib modules out of sys.modules.
        from namo import camera, paths, session, vp_common, vpexport
        self._camera, self._paths, self._session, self._common = camera, paths, session, vp_common
        self._vpexport = vpexport
        self._application = None
        try:
            from pynavis import toast
            self._toast = toast
        except Exception:
            self._toast = None
        self.partner_title = ''
        self.log = log
        self.alive = alive or process_alive
        self.pid = own_pid()
        self.root = root or folder()
        self.path = os.path.join(self.root, file_name(self.pid))
        self.seq = 0
        self.started = time.time()
        self.checked = {}
        self.write_failures = 0
        self.running = False
        self.applying = False
        self.last_applied = None
        self.seen = {}
        self.stamps = {}
        self.partner = None
        self.first_change = None
        self.last_change = None
        self.doc = None
        self.poll_timer = None
        self.write_timer = None
        self.handlers = {}

    # -- logging and safety

    def _report(self, text):
        try:
            if self.log is not None:
                self.log.error('Camera Sync: %s' % text)
                return
        except Exception:
            pass
        try:
            self._session.log('error', 'Camera Sync: %s' % text)
        except Exception:
            pass

    def _safe(self, work):
        try:
            work()
        except Exception as error:
            self._report(str(error))

    # -- files

    def _units(self):
        try:
            return str(self.doc.Units)
        except Exception:
            return 'Meters'

    def _title(self):
        try:
            return str(self.doc.Title or '')
        except Exception:
            return ''

    def write(self, presence=False):
        camera, paths, vp_common = self._camera, self._paths, self._common
        cam = None
        if not presence and self.doc is not None:
            cam = camera.capture(self.doc)
            tol = 1e-4 / vp_common.to_meters_factor(self._units())
            if self.last_applied is not None and vp_common.same_camera(cam, self.last_applied, tol, 0.01):
                return False
        self.seq += 1
        # retries=1: this runs on the UI thread while the user navigates. A busy file fails
        # at once (no sleeping retries inside paths) and _on_write_tick tries again shortly.
        paths.atomic_write_text(self.path, dumps(message(self.pid, self.seq, cam, self._units(), self._title(),
                                                         started=self.started)), retries=1)
        return True

    def _entries(self):
        out = []
        try:
            names = os.listdir(self.root)
        except Exception:
            return out
        for name in names:
            pid = pid_of(name)
            if pid is None or pid == self.pid:
                continue
            path = os.path.join(self.root, name)
            try:
                stat = os.stat(path)
            except Exception:
                continue
            out.append({'pid': pid, 'path': path, 'mtime': stat.st_mtime, 'size': stat.st_size})
        return out

    def _is_alive(self, pid):
        """self.alive(pid), asked at most once every ALIVE_S per pid: the poll runs
        eight times a second and a process lookup is not free."""
        now = time.time()
        known = self.checked.get(pid)
        if known is not None and 0.0 <= now - known[0] < ALIVE_S:
            return known[1]
        answer = bool(self.alive(pid))
        self.checked[pid] = (now, answer)
        return answer

    def _forget_dead(self, entries):
        live = []
        for entry in entries:
            if self._is_alive(entry['pid']):
                live.append(entry)
            else:
                try:
                    os.remove(entry['path'])
                except Exception:
                    pass
        return live

    def poll(self):
        paths = self._paths
        if not self.running or self.doc is None:
            return
        entries = self._forget_dead(self._entries())
        partner = pick_partner(entries, self.pid, lambda pid: True)
        self._announce(partner)
        if partner is None:
            return
        stamp = (partner['mtime'], partner['size'])
        if not file_changed(stamp, self.stamps.get(partner['pid']), time.time()):
            return
        text = paths.read_text(partner['path'])
        msg = parse(text) if text else None
        if msg is None:
            return                      # a torn read: the next tick sees the whole file
        self.stamps[partner['pid']] = stamp
        self.partner_title = msg.get('title') or ''
        if should_apply(msg, self.seen):
            self.apply(msg)
            self.seen[msg['pid']] = stamp_of(msg)

    def _announce(self, partner):
        before = self.partner
        now = partner['pid'] if partner is not None else None
        if before == now:
            return
        self.partner = now
        toast = self._toast
        if toast is None:
            return
        try:
            if now is not None:
                toast.info('Syncing with Navisworks (PID %d)' % now)
            elif before is not None:
                toast.info('Camera sync partner closed', 'Waiting for another session.')
        except Exception:
            pass

    def apply(self, msg):
        camera, vp_common = self._camera, self._common
        k = vp_common.unit_factor(msg.get('units') or self._units(), self._units())
        cam = dict(msg['camera']) if abs(k - 1.0) < 1e-12 else self._vpexport.scale_camera(msg['camera'], k)
        here = camera.capture(self.doc)
        tol = 1e-4 / vp_common.to_meters_factor(self._units())
        if vp_common.same_camera(here, cam, tol, 0.01):
            self.last_applied = here
            return False
        viewpoint = None
        if cam.get('json'):
            try:
                trial = self.doc.CurrentViewpoint.CreateCopy()
                if trial.TrySetCamera(str(cam['json'])):
                    viewpoint = trial
            except Exception:
                viewpoint = None
        if viewpoint is None:
            viewpoint = camera.to_viewpoint(cam, doc=self.doc)
        self.applying = True
        try:
            self.doc.CurrentViewpoint.CopyFrom(viewpoint)
        finally:
            self.applying = False
        self.last_applied = camera.capture(self.doc)
        self.first_change = self.last_change = None
        return True

    # -- events and timers

    def _on_changed(self, sender, args):
        def work():
            if self.applying or not self.running:
                return
            now = time.time()
            if self.first_change is None:
                self.first_change = now
            self.last_change = now
            if self.write_timer is not None and not self.write_timer.IsEnabled:
                self.write_timer.Start()
        self._safe(work)

    def _on_write_tick(self, sender, args):
        def work():
            if not self.running:
                self.write_timer.Stop()
                return
            if write_due(time.time(), self.first_change, self.last_change):
                self.write_timer.Stop()
                self.first_change = self.last_change = None
                try:
                    self.write()
                    self.write_failures = 0
                except Exception:
                    # The file was busy (the other window reading it, a virus scanner).
                    # The camera at rest must still get across, so try again shortly,
                    # a few times, rather than leave the other window one move behind.
                    self.write_failures += 1
                    if self.write_failures <= WRITE_RETRIES:
                        self.first_change = self.last_change = time.time()
                        self.write_timer.Start()
                    raise
        self._safe(work)

    def _on_poll_tick(self, sender, args):
        self._safe(self.poll)

    def _on_document(self, sender, args):
        def work():
            self._subscribe(self._application.ActiveDocument)
            self.seen = {}
            self.stamps = {}
            self.last_applied = None
        self._safe(work)

    def _subscribe(self, document):
        previous = self.doc
        if previous is document:
            return
        if previous is not None:
            try:
                previous.CurrentViewpoint.Changed -= self.handlers['changed']
            except Exception:
                pass
        self.doc = document
        if document is not None:
            document.CurrentViewpoint.Changed += self.handlers['changed']

    def start(self):
        """Hooks the active document, writes a presence file and starts polling.
        Returns the partner entry seen at once (or None)."""
        from System import TimeSpan
        from System.Windows.Threading import DispatcherPriority, DispatcherTimer
        from pynavis._api import Application
        self._application = Application
        # Python bound methods become new delegates on every access: keep ONE of
        # each, so -= later removes exactly what += added.
        self.handlers = {'changed': self._on_changed, 'document': self._on_document,
                         'write': self._on_write_tick, 'poll': self._on_poll_tick}
        self.poll_timer = DispatcherTimer(DispatcherPriority.Background)
        self.poll_timer.Interval = TimeSpan.FromMilliseconds(POLL_MS)
        self.write_timer = DispatcherTimer(DispatcherPriority.Background)
        self.write_timer.Interval = TimeSpan.FromMilliseconds(WRITE_TICK_MS)
        try:
            self.poll_timer.Tick += self.handlers['poll']
            self.write_timer.Tick += self.handlers['write']
            Application.ActiveDocumentChanged += self.handlers['document']
            self._subscribe(Application.ActiveDocument)
            self.running = True
            self.write(presence=True)
            entries = self._forget_dead(self._entries())
            partner = pick_partner(entries, self.pid, lambda pid: True)
            if partner is not None:
                self.partner = partner['pid']
                text = None
                try:
                    from namo import paths
                    text = paths.read_text(partner['path'])
                except Exception:
                    text = None
                msg = parse(text) if text else None
                partner = dict(partner)
                partner['title'] = (msg or {}).get('title') or ''
            self.poll_timer.Start()
            return partner
        except Exception:
            self.stop()
            raise

    def stop(self):
        """Stops everything start() set up and deletes this session's file. Each
        step guarded on its own, so one failure never leaves another attached."""
        self.running = False

        def stop_timers():
            for timer, key in ((self.poll_timer, 'poll'), (self.write_timer, 'write')):
                if timer is not None:
                    timer.Stop()
                    try:
                        timer.Tick -= self.handlers[key]
                    except Exception:
                        pass

        def unhook_app():
            from pynavis._api import Application
            if 'document' in self.handlers:
                Application.ActiveDocumentChanged -= self.handlers['document']

        def unhook_doc():
            if 'changed' in self.handlers:
                self._subscribe(None)

        def remove_file():
            if os.path.exists(self.path):
                os.remove(self.path)
        for step in (stop_timers, unhook_app, unhook_doc, remove_file):
            self._safe(step)


def _slot(value=None, clear=False):
    """The AppDomain slot holding the running Sync's stop (a System.Action), or None.
    Never raises; outside .NET there is no slot."""
    try:
        from System import AppDomain
        if clear or value is not None:
            AppDomain.CurrentDomain.SetData(SLOT, value)
            return value
        return AppDomain.CurrentDomain.GetData(SLOT)
    except Exception:
        return None


def _stop_orphan():
    """Stops a Sync this engine no longer holds (its stop was parked in the slot)."""
    parked = _slot()
    if parked is None:
        return
    _slot(clear=True)
    try:
        parked()
    except Exception:
        pass


def start(log=None):
    """Stops any previous Sync (toggle, Reload) and starts a new one. Returns the
    partner entry or None."""
    if not stop():
        _stop_orphan()
    sync = Sync(log=log)
    holder().sync = sync
    partner = sync.start()
    try:
        from System import Action
        _slot(Action(sync.stop))
    except Exception:
        pass
    return partner


def stop():
    """Stops the running Sync, if any. Returns True when one was running."""
    h = holder()
    sync = getattr(h, 'sync', None)
    if sync is None:
        return False
    was = bool(getattr(sync, 'running', False))
    try:
        sync.stop()
    finally:
        h.sync = None
        _slot(clear=True)
    return was


def shutdown():
    """App closing: stop and remove this session's file. Never raises."""
    try:
        stop()
    except Exception:
        pass
    try:
        path = os.path.join(folder(), file_name(own_pid()))
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass
