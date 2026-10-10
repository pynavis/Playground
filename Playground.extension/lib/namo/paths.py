# -*- coding: utf-8 -*-
"""Where Playground keeps its files, and how it writes them safely.

    %APPDATA%\\pyNavis\\playground\\                 data_root(): this user's data (reports, stores, logs)
    <config shared_root>\\              team_root(): team data when a shared folder is set
                                        and reachable, else data_root()

Document identity follows pynavis.memory: everything derives from the LOWERCASED full
path, '<stem, 40 chars>-<sha1[:8]>', so the same file reached through a differently cased
path lands on the same key. Team data keys by the lowercased BASENAME only, because
colleagues map the same share to different drive letters.

Every write is atomic (a temp file beside the target, then os.replace), so a crash or a
full disk never leaves a half-written file where the user's data was. A JSON file that
will not parse is renamed '<file>.corrupt-<timestamp>' and reads as the default.

Pure stdlib. Test seam: redirect(folder) points data_root() AND the Playground settings file
(namo.config) at a scratch folder; redirect(None) restores both.
"""
import hashlib
import io
import json
import os
import random
import time

from namo import session

# Test seam: a folder used instead of %APPDATA% (see redirect()).
_APPDATA_OVERRIDE = None

_RESERVED = set(['CON', 'PRN', 'AUX', 'NUL', 'CLOCK$'] +
                ['COM%d' % i for i in range(1, 10)] + ['LPT%d' % i for i in range(1, 10)])
_INVALID = '<>:"/\\|?*'
_REACH_OK_SECONDS = 60.0
_REACH_BAD_SECONDS = 15.0


# ---- roots ----------------------------------------------------------------------


def appdata():
    """The base folder for per-user data: %APPDATA% (or the redirect() folder)."""
    return _APPDATA_OVERRIDE or os.environ.get('APPDATA') or os.path.expanduser('~')


def redirect(folder):
    """Test seam: data_root() becomes <folder>\\pyNavis\\playground and namo.config reads and writes
    <folder>\\pyNavis\\settings\\playground.json. redirect(None) restores the real locations.
    Returns the previous folder (or None)."""
    global _APPDATA_OVERRIDE
    previous = _APPDATA_OVERRIDE
    _APPDATA_OVERRIDE = folder
    from namo import config
    config._APPDATA_OVERRIDE = folder
    forget_reachability()
    return previous


def data_root():
    """%APPDATA%\\pyNavis\\playground, created on demand."""
    return ensure_dir(os.path.join(appdata(), 'pyNavis', 'playground'))


def shared_root():
    """The configured shared folder (config 'shared_root'), stripped; '' when unset."""
    from namo import config
    return (config.get('shared_root') or '').strip()


def team_available():
    """True when a shared folder is configured and reachable right now."""
    shared = shared_root()
    return bool(shared) and is_reachable(shared)


def team_root():
    """The configured shared folder when set and reachable, else data_root().

    Reachability is cached per session (60 s when reachable, 15 s when not), because
    probing an offline network share can block for many seconds.
    """
    shared = shared_root()
    if shared:
        ok = is_reachable(shared)
        _note_shared(shared, ok)
        if ok:
            return shared
    return data_root()


def _note_shared(shared, ok):
    """Logs the shared folder going away once, not on every team_root() call (dozens
    per click), and again only after it has been reachable in between. Returns True
    when a line was logged."""
    key = os.path.normcase(os.path.abspath(shared))
    logged = session.get('paths', 'unreachable_logged')
    if logged is None:
        logged = session.set('paths', 'unreachable_logged', {})
    if ok:
        logged.pop(key, None)
        return False
    if key in logged:
        return False
    logged[key] = True
    session.log('warning', 'shared folder %s is not reachable; using local data' % shared)
    return True


def is_reachable(folder):
    """True when folder exists as a directory; cached briefly per session (see team_root).
    Says nothing in the log: it probes any folder for any caller. The one line about the
    SHARED folder being away is team_root()'s."""
    if not folder:
        return False
    key = os.path.normcase(os.path.abspath(folder))
    cache = session.get('paths', 'reachable')
    if cache is None:
        cache = session.set('paths', 'reachable', {})
    now = time.time()
    hit = cache.get(key)
    if hit is not None:
        ok, stamp = hit
        if now - stamp < (_REACH_OK_SECONDS if ok else _REACH_BAD_SECONDS):
            return ok
    try:
        ok = os.path.isdir(folder)
    except Exception:
        ok = False
    cache[key] = (ok, now)
    return ok


def forget_reachability():
    """Drops the reachability cache so the next team_root() probes again."""
    session.set('paths', 'reachable', {})


# ---- names and keys -------------------------------------------------------------


def _key_stem(text):
    stem = os.path.splitext(os.path.basename(text))[0]
    cleaned = ''.join(c if (c.isalnum() or c in '-_') else '_' for c in stem)
    return cleaned[:40] or 'untitled'


def doc_key(doc_path, shared=False):
    """A folder-safe key for a document: '<stem, 40 chars>-<sha1[:8]>'.

    The hash is of the lowercased full path (pynavis.memory's identity rule), or, with
    shared=True, of the lowercased basename only. '' or None gives 'untitled'.
    """
    text = doc_path or ''
    if not text.strip():
        return 'untitled'
    lowered = text.lower()          # NOT stripped or normalised: same bytes pynavis.memory hashes
    if shared:
        lowered = lowered.replace('/', '\\').rstrip('\\').split('\\')[-1]
    digest = hashlib.sha1(lowered.encode('utf-8')).hexdigest()[:8]
    return '%s-%s' % (_key_stem(lowered), digest)


def safe_filename(text, max_len=80, replacement='_'):
    """text made safe as one Windows file name.

    Characters Windows refuses (<>:"/\\|? * and control characters) become replacement,
    runs of it collapse, leading spaces and trailing dots/spaces go, reserved device names
    (CON, PRN, AUX, NUL, COM1..9, LPT1..9, also with an extension) get the replacement as
    a prefix, and the result is cut to max_len keeping a short extension. Empty input
    gives 'untitled'.
    """
    text = '' if text is None else str(text)
    out = []
    for ch in text:
        if ch in _INVALID or ord(ch) < 32:
            out.append(replacement)
        else:
            out.append(ch)
    name = ''.join(out)
    if replacement:
        double = replacement + replacement
        while double in name:
            name = name.replace(double, replacement)
    name = name.lstrip(' ').rstrip('. ')
    if not name or name.strip(replacement + ' .') == '':
        return 'untitled'
    if name.split('.')[0].strip().upper() in _RESERVED:
        name = (replacement or '_') + name
    if max_len and len(name) > max_len:
        stem, ext = os.path.splitext(name)
        if ext and len(ext) <= 8 and len(ext) < max_len:
            name = stem[:max_len - len(ext)].rstrip('. ') + ext
        else:
            name = name[:max_len]
        name = name.rstrip('. ') or 'untitled'
    return name


def unique_path(path):
    """path itself when nothing is there, else 'name (2).ext', 'name (3).ext', ..."""
    if not os.path.exists(path):
        return path
    stem, ext = os.path.splitext(path)
    for n in range(2, 10000):
        candidate = '%s (%d)%s' % (stem, n, ext)
        if not os.path.exists(candidate):
            return candidate
    raise IOError('No free file name for %s' % path)


def ensure_dir(path):
    """Creates the folder (and parents) when missing; returns path."""
    if path and not os.path.isdir(path):
        try:
            os.makedirs(path)
        except OSError:
            if not os.path.isdir(path):
                raise
    return path


# ---- atomic writes --------------------------------------------------------------


def _temp_beside(path):
    return '%s.%d-%06d.tmp' % (path, os.getpid(), random.randint(0, 999999))


REPLACE_RETRIES = 6


def _replace(temp, path, retries=None):
    """os.replace with a few short retries: antivirus and indexers hold new files briefly.
    retries: how many attempts (default 6, which can sleep about a second in total; 1
    fails at once, for a caller on the UI thread that retries on its own next tick)."""
    last = None
    attempts = REPLACE_RETRIES if retries is None else max(1, int(retries))
    for attempt in range(attempts):
        try:
            try:
                os.replace(temp, path)
            except AttributeError:      # very old runtimes have no os.replace
                if os.path.exists(path):
                    os.remove(path)
                os.rename(temp, path)
            return
        except OSError as error:
            last = error
            if attempt + 1 < attempts:
                time.sleep(0.05 * (attempt + 1))
    raise IOError('Could not replace %s: %s' % (path, last))


def _remove_quietly(path):
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError:
        pass


def atomic_write_bytes(path, data, retries=None):
    """Replaces path with data (bytes); on failure path is left exactly as it was.
    Creates the parent folder. Raises IOError naming the file on failure. retries: see
    _replace (1 = fail fast instead of sleeping while something holds the file)."""
    ensure_dir(os.path.dirname(os.path.abspath(path)))
    temp = _temp_beside(path)
    try:
        try:
            with io.open(temp, 'wb') as handle:
                handle.write(data)
        except (IOError, OSError) as error:
            raise IOError('Could not write %s: %s' % (path, error))
        _replace(temp, path, retries)
    finally:
        _remove_quietly(temp)
    return path


def atomic_write_text(path, text, encoding='utf-8', retries=None):
    """Replaces path with text, written exactly as given (no newline translation).
    Same guarantees and retries as atomic_write_bytes. Returns path."""
    if not isinstance(text, str):
        text = str(text)
    return atomic_write_bytes(path, text.encode(encoding), retries)


def read_text(path, default=None):
    """The file's text (UTF-8, a BOM tolerated), or default when missing or unreadable."""
    try:
        with io.open(path, 'r', encoding='utf-8-sig') as handle:
            return handle.read()
    except Exception:
        return default


# ---- JSON files -----------------------------------------------------------------


def quarantine(path):
    """Renames a damaged file to '<file>.corrupt-<YYYYmmdd-HHMMSS>' (numbered when that is
    taken) and logs it. Returns the new path, or None when the rename failed."""
    stamp = time.strftime('%Y%m%d-%H%M%S')
    target = '%s.corrupt-%s' % (path, stamp)
    n = 2
    while os.path.exists(target):
        target = '%s.corrupt-%s-%d' % (path, stamp, n)
        n += 1
    try:
        os.rename(path, target)
    except OSError as error:
        session.log('error', 'could not move aside damaged file %s: %s' % (path, error))
        return None
    session.log('warning', 'damaged file %s moved aside to %s' % (path, os.path.basename(target)))
    return target


def load_json(path, default=None, move_aside=True):
    """The parsed JSON in path, or default.

    Missing file: default. Unreadable (locked) file: default, logged, left alone.
    Empty or unparseable file: moved aside with quarantine() (unless move_aside=False),
    logged, default. Never raises.
    """
    if not path or not os.path.exists(path):
        return default
    try:
        with io.open(path, 'r', encoding='utf-8-sig') as handle:
            text = handle.read()
    except Exception as error:
        session.log('warning', 'could not read %s: %s' % (path, error))
        return default
    try:
        if not text.strip():
            raise ValueError('empty file')
        return json.loads(text)
    except Exception as error:
        session.log('warning', 'damaged JSON in %s: %s' % (path, error))
        if move_aside:
            quarantine(path)
        return default


def dumps(value):
    """The JSON text every Playground file uses: indent 2, sorted keys, unicode kept, final newline."""
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + '\n'


def write_json(path, value):
    """Atomically writes value as JSON (see dumps). Raises IOError on write problems,
    TypeError/ValueError when value is not JSON-serialisable. Returns path."""
    return atomic_write_text(path, dumps(value))


# ---- a small cross-process lock -------------------------------------------------


class FileLock(object):
    """Context manager: holds '<path>.lock' (exclusive create) while a read-modify-write
    runs, so two people saving the same team file do not lose each other's change.

        with paths.FileLock(store_file):
            data = paths.load_json(store_file, {}); data['x'] = 1; paths.write_json(store_file, data)

    Waits up to timeout seconds; a lock older than stale seconds is broken (its owner
    crashed). When the lock cannot be had in time the block still runs (logged), because
    a stuck lock file must never stop someone from saving. .held tells which happened.
    """

    def __init__(self, path, timeout=3.0, stale=30.0):
        self.lock_path = path + '.lock'
        self.timeout = timeout
        self.stale = stale
        self.held = False

    def __enter__(self):
        ensure_dir(os.path.dirname(os.path.abspath(self.lock_path)))
        deadline = time.time() + self.timeout
        while True:
            try:
                fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except Exception:
                fd = None
            if fd is not None:
                self.held = True
                try:
                    os.write(fd, ('%d %s' % (os.getpid(), os.environ.get('USERNAME', ''))).encode('utf-8'))
                except Exception:
                    pass        # the owner note is informational; the file's existence is the lock
                finally:
                    os.close(fd)
                return self
            try:
                age = time.time() - os.path.getmtime(self.lock_path)
            except OSError:
                age = None          # vanished meanwhile, or the folder refuses lock files
            if age is not None and age > self.stale:
                _remove_quietly(self.lock_path)
                session.log('warning', 'broke a stale lock %s (%d s old)' % (self.lock_path, age))
                continue
            if time.time() > deadline:
                session.log('warning', 'lock %s is busy or cannot be created; continuing without it'
                            % self.lock_path)
                return self
            time.sleep(0.02 if age is None else 0.05)

    def __exit__(self, exc_type, exc, tb):
        if self.held:
            _remove_quietly(self.lock_path)
            self.held = False
        return False
