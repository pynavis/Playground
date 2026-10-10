# -*- coding: utf-8 -*-
"""namo.paths: roots, document keys, safe names, atomic writes, JSON files, the lock."""
import hashlib
import io
import os
import threading
import time

import _compat
from _compat import raises

from namo import config, paths, session


def isolated(fn):
    """Runs the test with data_root() and the settings file in a scratch folder."""
    def wrapper():
        folder = _compat.tmpdir('f2-paths-' + fn.__name__)
        previous = paths.redirect(folder)
        try:
            return fn(folder)
        finally:
            paths.redirect(previous)
    wrapper.__name__ = fn.__name__
    return wrapper


@isolated
def test_data_root_is_created_under_the_redirect(folder):
    root = paths.data_root()
    assert root == os.path.join(folder, 'pyNavis', 'playground')
    assert os.path.isdir(root)
    assert paths.appdata() == folder


def test_redirect_restores():
    before = paths.appdata()
    folder = _compat.tmpdir('f2-paths-restore')
    previous = paths.redirect(folder)
    assert paths.appdata() == folder and config._APPDATA_OVERRIDE == folder
    paths.redirect(previous)
    assert paths.appdata() == before and config._APPDATA_OVERRIDE == previous


@isolated
def test_team_root_falls_back_and_uses_a_reachable_share(folder):
    assert paths.team_root() == paths.data_root()
    assert not paths.team_available()
    share = os.path.join(folder, 'share')
    config.save({'shared_root': share})
    paths.forget_reachability()
    assert paths.team_root() == paths.data_root()          # not there yet
    os.makedirs(share)
    assert paths.team_root() == paths.data_root()          # unreachable result is cached
    paths.forget_reachability()
    assert paths.team_root() == share
    assert paths.team_available()


def test_doc_key_matches_pynavis_memory_identity():
    path = r'C:\Projects\Tower\Coordination Model.nwf'
    lowered = path.lower()
    digest = hashlib.sha1(lowered.encode('utf-8')).hexdigest()[:8]
    assert paths.doc_key(path) == 'coordination_model-' + digest
    assert paths.doc_key(path.upper()) == paths.doc_key(path)          # case-insensitive
    assert paths.doc_key(r'D:\Other\Coordination Model.nwf') != paths.doc_key(path)
    assert paths.doc_key('') == 'untitled'
    assert paths.doc_key(None) == 'untitled'
    assert paths.doc_key('   ') == 'untitled'
    long_name = 'x' * 80 + '.nwd'
    assert len(paths.doc_key(long_name)) == 40 + 1 + 8


def test_doc_key_shared_uses_the_basename_only():
    a = paths.doc_key(r'S:\Projects\Tower\Model.nwf', shared=True)
    b = paths.doc_key(r'\\server\projects\Tower\MODEL.nwf', shared=True)
    c = paths.doc_key('T:/Tower/model.nwf', shared=True)
    assert a == b == c
    digest = hashlib.sha1('model.nwf'.encode('utf-8')).hexdigest()[:8]
    assert a == 'model-' + digest
    assert paths.doc_key(r'S:\Projects\Tower\Model.nwf') != a


def test_doc_key_agrees_with_pynavis_memory_when_available():
    try:
        from pynavis import memory
    except ImportError:
        raise _compat.SkipTest('pynavis.memory not importable')
    path = r'C:\Projects\Tower\Coordination Model.nwf'
    expected = os.path.splitext(os.path.basename(memory.path_for(path, 'root')))[0]
    assert paths.doc_key(path) == expected


def test_safe_filename():
    assert paths.safe_filename('Clash: A/B?') == 'Clash_ A_B_'
    assert paths.safe_filename('a<>b') == 'a_b'                      # runs collapse
    assert paths.safe_filename('name. . ') == 'name'
    assert paths.safe_filename('  lead') == 'lead'
    assert paths.safe_filename('CON') == '_CON'
    assert paths.safe_filename('com1.txt') == '_com1.txt'
    assert paths.safe_filename('Console') == 'Console'
    assert paths.safe_filename('') == 'untitled'
    assert paths.safe_filename(None) == 'untitled'
    assert paths.safe_filename('???') == 'untitled'
    assert paths.safe_filename('tab\there') == 'tab_here'
    long_name = 'r' * 100 + '.xlsx'
    cut = paths.safe_filename(long_name, max_len=40)
    assert len(cut) == 40 and cut.endswith('.xlsx')
    assert paths.safe_filename('a/b', replacement='-') == 'a-b'
    assert paths.safe_filename('Caf' + chr(0xE9)) == 'Caf' + chr(0xE9)


@isolated
def test_unique_path_and_ensure_dir(folder):
    target = os.path.join(folder, 'deep', 'er', 'report.xlsx')
    assert paths.ensure_dir(os.path.dirname(target)) == os.path.dirname(target)
    assert paths.ensure_dir(os.path.dirname(target))                # twice is fine
    assert paths.unique_path(target) == target
    paths.atomic_write_text(target, 'x')
    second = paths.unique_path(target)
    assert second == os.path.join(folder, 'deep', 'er', 'report (2).xlsx')
    paths.atomic_write_text(second, 'y')
    assert paths.unique_path(target).endswith('report (3).xlsx')


@isolated
def test_atomic_writes(folder):
    target = os.path.join(folder, 'sub', 'file.txt')
    text = 'line one\nline two ' + chr(0x2192) + '\n'
    assert paths.atomic_write_text(target, text) == target
    with io.open(target, 'rb') as handle:
        assert handle.read() == text.encode('utf-8')                 # no newline translation
    assert paths.read_text(target) == text
    paths.atomic_write_bytes(target, b'\x00\x01')
    with io.open(target, 'rb') as handle:
        assert handle.read() == b'\x00\x01'
    leftovers = [n for n in os.listdir(os.path.dirname(target)) if n.endswith('.tmp')]
    assert leftovers == []
    assert paths.read_text(os.path.join(folder, 'missing.txt'), 'default') == 'default'


@isolated
def test_atomic_write_failure_raises_ioerror_and_keeps_the_old_file(folder):
    target = os.path.join(folder, 'keep.txt')
    paths.atomic_write_text(target, 'original')
    blocked = os.path.join(folder, 'a_folder')
    os.makedirs(blocked)
    raises(IOError, paths.atomic_write_text, blocked, 'cannot replace a folder')
    assert paths.read_text(target) == 'original'
    assert [n for n in os.listdir(folder) if n.endswith('.tmp')] == []


@isolated
def test_json_files_and_quarantine(folder):
    good = os.path.join(folder, 'good.json')
    paths.write_json(good, {'b': [1, 2], 'a': 'caf' + chr(0xE9)})
    assert paths.load_json(good) == {'a': 'caf' + chr(0xE9), 'b': [1, 2]}
    with io.open(good, 'r', encoding='utf-8') as handle:
        text = handle.read()
    assert text.index('"a"') < text.index('"b"') and text.endswith('\n')
    assert paths.load_json(os.path.join(folder, 'none.json'), 'dflt') == 'dflt'
    bad = os.path.join(folder, 'bad.json')
    with io.open(bad, 'w', encoding='utf-8') as handle:
        handle.write(u'{not json')
    assert paths.load_json(bad, {'fresh': True}) == {'fresh': True}
    assert not os.path.exists(bad)
    moved = [n for n in os.listdir(folder) if n.startswith('bad.json.corrupt-')]
    assert len(moved) == 1
    assert any('damaged' in text for _lvl, text in session.recent_log('warning'))
    empty = os.path.join(folder, 'empty.json')
    with io.open(empty, 'w', encoding='utf-8') as handle:
        handle.write(u'  ')
    assert paths.load_json(empty, 5) == 5
    with io.open(bad, 'w', encoding='utf-8') as handle:
        handle.write(u'[1,')
    assert paths.load_json(bad, None, move_aside=False) is None
    assert os.path.exists(bad)
    with io.open(bad, 'wb') as handle:
        handle.write(b'\xef\xbb\xbf{"bom": 1}')
    assert paths.load_json(bad) == {'bom': 1}


@isolated
def test_quarantine_numbers_repeated_names(folder):
    first = os.path.join(folder, 'x.json')
    for _ in range(2):
        with io.open(first, 'w', encoding='utf-8') as handle:
            handle.write(u'oops')
        assert paths.quarantine(first) is not None
    assert len([n for n in os.listdir(folder) if '.corrupt-' in n]) == 2


@isolated
def test_file_lock(folder):
    target = os.path.join(folder, 'team.json')
    with paths.FileLock(target) as lock:
        assert lock.held and os.path.exists(target + '.lock')
        with paths.FileLock(target, timeout=0.2) as other:
            assert not other.held                                    # busy: ran without it
    assert not os.path.exists(target + '.lock')
    with io.open(target + '.lock', 'w') as handle:
        handle.write(u'stale')
    old = time.time() - 120
    os.utime(target + '.lock', (old, old))
    with paths.FileLock(target, timeout=1.0, stale=30.0) as lock:
        assert lock.held                                             # stale lock broken
    assert not os.path.exists(target + '.lock')


@isolated
def test_file_lock_serialises_threads(folder):
    target = os.path.join(folder, 'counter.json')
    paths.write_json(target, {'n': 0})

    def bump():
        for _ in range(5):
            with paths.FileLock(target, timeout=10.0):
                data = paths.load_json(target, {'n': 0})
                data['n'] += 1
                paths.write_json(target, data)

    threads = [threading.Thread(target=bump) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert paths.load_json(target)['n'] == 20


@isolated
def test_only_team_root_logs_an_unreachable_share_and_only_once(folder):
    marker = 'is not reachable'
    count = lambda: len([1 for _lvl, text in session.recent_log('warning') if marker in text])
    before = count()
    # probing any folder says nothing in the log
    assert paths.is_reachable(os.path.join(folder, 'no such folder')) is False
    assert paths.is_reachable(os.path.join(folder, 'another')) is False
    assert count() == before
    share = os.path.join(folder, 'share')
    config.save({'shared_root': share})
    paths.forget_reachability()
    session.set('paths', 'unreachable_logged', {})
    for _ in range(5):                                  # dozens of calls per click in real use
        assert paths.team_root() == paths.data_root()
    assert count() == before + 1
    os.makedirs(share)
    paths.forget_reachability()
    assert paths.team_root() == share and count() == before + 1
    os.rmdir(share)                                     # away again after being back: one more line
    paths.forget_reachability()
    assert paths.team_root() == paths.data_root() and paths.team_root() == paths.data_root()
    assert count() == before + 2


def test_replace_retries_can_fail_fast():
    folder = _compat.tmpdir('f2-paths-retries')
    target = os.path.join(folder, 'held')
    os.makedirs(os.path.join(target, 'child'))          # a non-empty folder: os.replace onto it fails
    temp = os.path.join(folder, 'new.tmp')
    with io.open(temp, 'wb') as handle:
        handle.write(b'x')
    slept = []
    real_sleep = paths.time.sleep
    paths.time.sleep = slept.append
    try:
        raises(IOError, paths._replace, temp, target, 1)
        assert slept == []                              # one attempt, no waiting
        raises(IOError, paths._replace, temp, target, 3)
        assert len(slept) == 2                          # waits between attempts, not after the last
        slept[:] = []
        raises(IOError, paths._replace, temp, target)
        assert len(slept) == paths.REPLACE_RETRIES - 1
        slept[:] = []
        raises(IOError, paths.atomic_write_text, target, 'text', 'utf-8', 1)
        assert slept == [] and [n for n in os.listdir(folder) if n.endswith('.tmp')] == ['new.tmp']
    finally:
        paths.time.sleep = real_sleep
    assert paths.atomic_write_text(os.path.join(folder, 'ok.txt'), 'fine', retries=1)
