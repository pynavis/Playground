# -*- coding: utf-8 -*-
"""namo.folderwatch pure half: settings, what is watched, the two-poll watcher, texts;
and the hook handler's switches."""
import os

import _compat

from namo import folderwatch as fw


def _infos():
    return [{'key': 'a#0', 'name': 'ARCH.rvt', 'file': r'C:\Proj\Models\ARCH.nwc', 'source': r'C:\Proj\Revit\ARCH.rvt'},
            {'key': 'm#0', 'name': 'MEP.nwc', 'file': r'C:\Proj\Models\MEP.nwc', 'source': r'C:\Proj\Models\MEP.nwc'},
            {'key': 's#0', 'name': 'STR.nwc', 'file': r'\\srv\share\STR.nwc', 'source': ''}]


def test_normalize_settings():
    out = fw.normalize({'folders': 'C:\\A\n\n c:\\a \n"D:\\B"', 'interval': 2, 'remember': 1})
    assert out['folders'] == ['C:\\A', 'D:\\B']
    assert out['interval'] == fw.MIN_INTERVAL and out['remember'] is True and out['active'] is False
    assert fw.normalize({'interval': 'junk'})['interval'] == 30
    assert fw.normalize({'interval': 99999})['interval'] == fw.MAX_INTERVAL
    assert sorted(fw.normalize(None)) == sorted(fw.DEFAULTS)


def test_default_folders_and_inside():
    folders = fw.default_folders(_infos())
    from namo import modelmgmt
    assert sorted(modelmgmt.norm_path(f) for f in folders) == sorted(
        [modelmgmt.norm_path(r'C:\Proj\Models'), modelmgmt.norm_path('\\\\srv\\share\\')])
    norm = [modelmgmt.norm_path(r'C:\Proj')]
    assert fw.inside(r'C:\Proj\Models\x.nwc', norm)
    assert not fw.inside(r'C:\Project2\x.nwc', norm)


def test_watched_files_defaults_sources_and_folders():
    files = fw.watched_files(_infos())
    assert [(os.path.basename(p), k) for p, k, n in files] == [('ARCH.nwc', 'a#0'), ('MEP.nwc', 'm#0'),
                                                               ('STR.nwc', 's#0')]
    files = fw.watched_files(_infos(), folders=[r'C:\Proj'])
    assert [os.path.basename(p) for p, k, n in files] == ['ARCH.nwc', 'ARCH.rvt', 'MEP.nwc']
    files = fw.watched_files(_infos(), folders=[r'C:\Proj'], watch_sources=False)
    assert [os.path.basename(p) for p, k, n in files] == ['ARCH.nwc', 'MEP.nwc']


def test_watcher_needs_two_settled_polls():
    w = fw.Watcher()
    w.rebase({'a': (1.0, 10), 'b': (1.0, 10), 'c': 'offline'})
    assert w.poll({'a': (1.0, 10), 'b': (1.0, 10)}) == []
    assert w.poll({'a': (2.0, 11), 'b': (1.0, 10)}) == []          # changed: pending
    assert w.poll({'a': (3.0, 12), 'b': (1.0, 10)}) == []          # still being written
    assert w.poll({'a': (3.0, 12), 'b': (1.0, 10)}) == ['a']       # held still: report
    assert w.poll({'a': (3.0, 12), 'b': (1.0, 10)}) == []          # reported once
    # a change that reverts before settling is not reported
    assert w.poll({'a': (3.0, 12), 'b': (5.0, 1)}) == []
    assert w.poll({'a': (3.0, 12), 'b': (1.0, 10)}) == []
    assert w.poll({'a': (3.0, 12), 'b': (1.0, 10)}) == []


def test_watcher_new_offline_missing_and_forget():
    w = fw.Watcher()
    w.rebase({'a': (1.0, 1)})
    assert w.poll({'a': 'offline', 'n': (9.0, 9)}) == []           # offline ignored, new joins
    assert w.baseline['n'] == (9.0, 9) and w.baseline['a'] == (1.0, 1)
    assert w.poll({'a': 'missing'}) == []
    assert w.poll({'a': 'missing'}) == ['a']                       # deleted counts as a change
    w.forget_missing(['n'])
    assert sorted(w.baseline) == ['n']


def test_changed_models_and_texts():
    files = [('p1', 'a#0', 'ARCH'), ('p2', 'a#0', 'ARCH'), ('p3', 'm#0', 'MEP'), ('p4', 's#0', 'STR')]
    assert fw.changed_models(['p2', 'p1', 'p4'], files) == [('a#0', 'ARCH'), ('s#0', 'STR')]
    title, lines = fw.notice_texts(['A', 'B', 'C', 'D', 'E', 'F', 'G'])
    assert title == '7 models updated' and lines[-1] == 'and 2 more' and len(lines) == 6
    title, lines = fw.notice_texts(['A'])
    assert title == '1 model updated' and lines == ['A']
    message, detail = fw.status_texts(fw.normalize({}), [], [])
    assert message == 'Folder Watch is on' and 'Nothing to watch yet' in detail
    message, detail = fw.status_texts(fw.normalize({'interval': 60}), files, ['x', 'y'])
    assert detail == 'Watching 4 model files in 2 folders; checks every 60 s.'


def test_hook_is_quiet_when_off():
    from namo import hk_folderwatch, session
    session.clear(fw.HOLDER)
    hk_folderwatch.handle('doc-opened', {'name': 'doc-opened'})
    hk_folderwatch.handle('app-closing', {'name': 'app-closing'})
    hk_folderwatch.handle('startup', {'name': 'startup', 'runner': True})
    assert not fw.is_on()
