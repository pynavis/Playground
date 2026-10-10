# -*- coding: utf-8 -*-
"""namo.modelmgmt: types, folder scans, manifests, append plans, freshness, keys, and the
API half (models_info, append_files, remove/isolate/hide) through a fake document."""
import io
import os
import time

import _compat

from namo import modelmgmt as mm


def test_parse_types():
    assert mm.parse_types('nwc, .RVT;ifc  *.dwg nwc') == ['nwc', 'rvt', 'ifc', 'dwg']
    assert mm.parse_types('') == mm.DEFAULT_TYPES
    assert mm.types_text(['nwc', 'rvt']) == 'nwc rvt'


def test_paths_and_kinds():
    assert mm.norm_path(r'C:\A\..\B\x.NWC') == mm.norm_path(r'c:\b\X.nwc')
    assert mm.stem_key(r'C:\M\Arch.rvt') == mm.stem_key(r'c:\m\ARCH.nwc')
    assert mm.kind_of('a/b/c.nwc') == 'NWC' and mm.kind_of('noext') == ''
    assert mm.base_name(r'C:\M\Arch.rvt') == 'Arch.rvt'
    assert mm.share_root(r'\\srv\proj\models\a.nwc') == r'\\srv\proj'
    assert mm.share_root(r'C:\x') == ''
    assert mm.norm_path('') == ''


def test_formatting():
    assert mm.format_size(None) == ''
    assert mm.format_size(512) == '512 bytes'
    assert mm.format_size(2048) == '2.00 KB'
    assert mm.format_size(12.5 * 1024 * 1024) == '12.5 MB'
    assert mm.format_size(250 * 1024 ** 3) == '250 GB'
    assert mm.format_age(30) == 'under a minute'
    assert mm.format_age(60) == '1 minute'
    assert mm.format_age(7200) == '2 hours'
    assert mm.format_age(3 * 86400) == '3 days'
    assert mm.format_age(100 * 86400) == '14 weeks'
    assert mm.plural(1, 'model') == '1 model' and mm.plural(1204, 'item') == '1,204 items'
    assert mm.join_names(['a']) == 'a'
    assert mm.join_names(['a', 'b', 'c']) == 'a, b and c'
    assert mm.join_names(['a', 'b', 'c', 'd', 'e']) == 'a, b, c and 2 more'
    assert mm.format_time(None) == ''
    assert len(mm.format_time(time.time())) == 16


def _touch(path, text='x', mtime=None):
    folder = os.path.dirname(path)
    if not os.path.isdir(folder):
        os.makedirs(folder)
    with io.open(path, 'w', encoding='utf-8') as handle:
        handle.write(text)
    if mtime is not None:
        os.utime(path, (mtime, mtime))


def test_scan_folder_recursive_types_and_limit():
    root = _compat.tmpdir('mm_scan' + ('_ipy' if _compat.IRONPYTHON else '_cpy'))
    _touch(os.path.join(root, 'Level 10.nwc'))
    _touch(os.path.join(root, 'Level 2.nwc'))
    _touch(os.path.join(root, 'notes.txt'))
    _touch(os.path.join(root, '~$lock.nwc'))
    _touch(os.path.join(root, 'sub', 'MEP.rvt'))
    _touch(os.path.join(root, '.hidden', 'x.nwc'))
    files, cut = mm.scan_folder(root, ['nwc', 'rvt'])
    assert [f['relative'] for f in files] == ['Level 2.nwc', 'Level 10.nwc', os.path.join('sub', 'MEP.rvt')]
    assert not cut and files[0]['size'] == 1 and files[0]['ext'] == 'nwc'
    files, cut = mm.scan_folder(root, ['nwc', 'rvt'], recursive=False)
    assert [f['name'] for f in files] == ['Level 2.nwc', 'Level 10.nwc']
    files, cut = mm.scan_folder(root, ['nwc', 'rvt'], limit=1)
    assert cut and len(files) == 1


def test_manifest_rows_header_order_trade():
    rows = [['Order', 'File', 'Trade'], ['2', 'b.nwc', 'Mech'], ['1', 'a.nwc', 'Arch'],
            ['', 'c.nwc', ''], ['', '', ''], ['', '# comment', '']]
    entries, problems = mm.parse_manifest_rows(rows, r'C:\m')
    assert [os.path.basename(e['path']) for e in entries] == ['a.nwc', 'b.nwc', 'c.nwc']
    assert entries[0]['trade'] == 'Arch' and entries[0]['order'] == 1.0 and not problems


def test_manifest_rows_without_header():
    rows = [[r'\\srv\p\x.nwc', '3', 'Elec'], ['rel\\y.nwc'], [r'C:\abs\z.nwc', 'Struct']]
    entries, problems = mm.parse_manifest_rows(rows, r'C:\base')
    assert entries[0]['path'] == r'\\srv\p\x.nwc' and entries[0]['order'] == 3.0
    assert entries[0]['trade'] == 'Elec'
    assert entries[1]['path'] == os.path.normpath(r'C:\base\rel\y.nwc')
    assert entries[2]['trade'] == 'Struct' and entries[2]['order'] is None
    entries, problems = mm.parse_manifest_rows([['', '']], '')
    assert entries == [] and problems


def test_read_manifest_txt_csv_xlsx():
    folder = _compat.tmpdir('mm_manifest' + ('_ipy' if _compat.IRONPYTHON else '_cpy'))
    txt = os.path.join(folder, 'list.txt')
    _touch(txt, u'# models\nA.nwc\n\n"B.nwc"\n')
    entries, _ = mm.read_manifest(txt)
    assert [os.path.basename(e['path']) for e in entries] == ['A.nwc', 'B.nwc']
    assert os.path.dirname(entries[0]['path']) == folder
    csv_path = os.path.join(folder, 'list.csv')
    _touch(csv_path, u'\ufeffpath;order;trade\nB.nwc;2;M\nA.nwc;1;A\n')
    entries, _ = mm.read_manifest(csv_path)
    assert [os.path.basename(e['path']) for e in entries] == ['A.nwc', 'B.nwc']
    assert entries[1]['trade'] == 'M'
    from namo import xlsx
    xl_path = os.path.join(folder, 'list.xlsx')
    xlsx.write_simple(xl_path, [{'name': 'Models', 'headers': ['Model', 'Order'],
                                 'rows': [['Z.nwc', 2], ['Y.nwc', 1]]}])
    entries, _ = mm.read_manifest(xl_path)
    assert [os.path.basename(e['path']) for e in entries] == ['Y.nwc', 'Z.nwc']
    _compat.raises(ValueError, mm.read_manifest, os.path.join(folder, 'missing.txt'))


def test_plan_append_statuses():
    infos = [{'file': r'C:\M\ARCH.nwc', 'source': r'C:\M\ARCH.rvt'},
             {'file': r'C:\M\MEP.nwc', 'source': ''}]
    candidates = [{'path': r'C:\M\ARCH.rvt', 'exists': True},
                  {'path': r'c:\m\mep.NWC', 'exists': True},
                  {'path': r'C:\M\STR.nwc', 'exists': True},
                  {'path': r'C:\M\STR.nwc', 'exists': True},
                  {'path': r'C:\M\gone.nwc', 'exists': False},
                  {'path': r'C:\M\MEP.rvt', 'exists': True}]
    rows = mm.plan_append(candidates, infos)
    assert [r['status'] for r in rows] == ['Appended', 'Appended', 'New', 'Repeated', 'Missing', 'Appended']
    assert [r['checked'] for r in rows] == [False, False, True, False, False, False]


def test_stale_status_cases():
    current = mm.stale_status(r'C:\a.nwc', (100.0, 1), r'C:\a.rvt', (99.0, 1))
    assert current['status'] == mm.CURRENT and current['level'] == 'pass'
    late = mm.stale_status(r'C:\a.nwc', (100.0, 1), r'C:\a.rvt', (100.0 + 86400 * 2, 1))
    assert late['status'] == mm.OUT_OF_DATE and 'a.rvt was saved 2 days after a.nwc' in late['detail']
    rounding = mm.stale_status(r'C:\a.nwc', (100.0, 1), r'C:\a.rvt', (101.5, 1))
    assert rounding['status'] == mm.CURRENT
    assert mm.stale_status(r'C:\a.nwc', 'missing', r'C:\a.rvt', (1.0, 1))['status'] == mm.CACHE_NOT_FOUND
    assert mm.stale_status(r'\\s\p\a.nwc', 'offline', '', None)['status'] == mm.CACHE_OFFLINE
    assert mm.stale_status(r'C:\a.nwc', (1.0, 1), r'D:\other\a.rvt', 'missing')['status'] == mm.SOURCE_NOT_FOUND
    assert mm.stale_status(r'C:\a.nwc', (1.0, 1), r'\\s\p\a.rvt', 'offline')['status'] == mm.SOURCE_OFFLINE
    assert mm.stale_status(r'C:\a.ifc', (1.0, 1), r'c:\A.IFC', (1.0, 1))['status'] == mm.CURRENT
    assert mm.stale_status('', None, '', None)['status'] == mm.NO_FILE
    for status, level in mm.STATUS_LEVEL.items():
        assert level in ('pass', 'info', 'warn')


def test_stale_summary_levels():
    assert mm.stale_summary([])[0] == 'info'
    rows = [{'name': 'A', 'status': mm.CURRENT}, {'name': 'B', 'status': mm.OUT_OF_DATE}]
    level, message, detail = mm.stale_summary(rows)
    assert level == 'warning' and message == '1 model out of date' and detail.startswith('B.')
    level, message, detail = mm.stale_summary([{'name': 'A', 'status': mm.CACHE_NOT_FOUND}])
    assert level == 'warning' and message == '1 model file not found'
    level, message, _ = mm.stale_summary([{'name': 'A', 'status': mm.SOURCE_NOT_FOUND}])
    assert level == 'info'
    level, message, detail = mm.stale_summary([{'name': 'A', 'status': mm.CURRENT},
                                               {'name': 'B', 'status': mm.SOURCE_NOT_FOUND}])
    assert level == 'success' and message == 'All 2 models are current' and '1 without' in detail


def test_model_keys_and_duplicates():
    keys = mm.model_keys([('A.nwc', 'G1'), ('a.NWC', 'g1'), ('B.nwc', 'G2')])
    assert keys == ['a.nwc#g1#0', 'a.nwc#g1#1', 'b.nwc#g2#0']
    infos = [{'index': 0, 'file': r'C:\a.nwc'}, {'index': 1, 'file': r'c:\A.NWC'},
             {'index': 2, 'file': r'C:\b.nwc'}]
    dups = mm.duplicate_files(infos)
    assert list(dups.values()) == [[0, 1]]


def test_signature_local_and_missing():
    folder = _compat.tmpdir('mm_sig' + ('_ipy' if _compat.IRONPYTHON else '_cpy'))
    path = os.path.join(folder, 'a.nwc')
    _touch(path, 'abc', mtime=1000000000)
    sig = mm.signature(path)
    assert sig == (1000000000.0, 3)
    assert mm.signature(os.path.join(folder, 'nope.nwc')) == 'missing'
    assert mm.signature(folder) == 'missing'
    assert mm.signature('') is None
    assert mm.reachable(r'C:\anything')


# ---- API half through the fake document ---------------------------------------------------

import test_items as nav  # noqa: E402


class _Model(object):
    def __init__(self, path, root):
        self.FileName = path
        self.SourceFileName = path.replace('.nwc', '.rvt')
        self.Units = 'Meters'
        self.Creator = 'Revit'
        self.Guid = 'guid-' + os.path.basename(path).lower()
        self.RootItem = root
        self.Transform = nav._Ns(IsIdentity=lambda: True)


class _AppendDoc(nav.Document):
    def __init__(self, models=()):
        nav.Document.__init__(self, models)
        self.removed = []

    def TryAppendFile(self, path):
        if 'bad' in path:
            return False
        root = nav.ModelItem(os.path.basename(path), geometry=True, box=((0, 0, 0), (1, 1, 1)))
        self.Models.models.append(_Model(path, root))
        return True

    def TryRemoveFile(self, index):
        self.removed.append(index)
        del self.Models.models[index]
        return True

    def UpdateFiles(self):
        return True


def _two_models():
    a = nav.ModelItem('A', [nav.ModelItem('wall', geometry=True, box=((0, 0, 0), (1, 1, 1)))])
    b = nav.ModelItem('B', [nav.ModelItem('duct', geometry=True, box=((5, 0, 0), (6, 1, 1)))])
    return _AppendDoc([_Model(r'C:\M\ARCH.nwc', a), _Model(r'C:\M\MEP.nwc', b)])


def test_models_info_keys_and_resolve():
    doc = _two_models()
    with nav.FakeNav(doc):
        infos = mm.models_info(doc)
        assert [i['name'] for i in infos] == ['ARCH.rvt', 'MEP.rvt']
        assert infos[0]['kind'] == 'RVT' and infos[0]['units'] == 'Meters'
        assert not infos[0]['transformed']
        assert mm.resolve_index(infos[1]['key'], doc) == 1
        assert mm.resolve_index('nope', doc) is None
        found = mm.models_of_items([infos[1]['root'].Children[0], infos[1]['root']], doc)
        assert [i['name'] for i in found] == ['MEP.rvt']


def test_append_files_counts_failures_and_new_keys():
    folder = _compat.tmpdir('mm_append' + ('_ipy' if _compat.IRONPYTHON else '_cpy'))
    good = os.path.join(folder, 'STR.nwc')
    bad = os.path.join(folder, 'bad.nwc')
    _touch(good)
    _touch(bad)
    doc = _two_models()
    labels = []
    with nav.FakeNav(doc):
        out = mm.append_files([good, bad, os.path.join(folder, 'gone.nwc')], doc,
                              report=lambda f, label: labels.append(label))
        assert out['appended'] == [good]
        assert [os.path.basename(p) for p, _ in out['failed']] == ['bad.nwc', 'gone.nwc']
        assert len(out['new_keys']) == 1 and out['new_keys'][0].startswith(good.lower())
        assert labels[0] == 'Appending STR.nwc (1 of 3)' and labels[-1] == 'Done'
        assert not out['stopped']


def test_append_files_stops_between_files():
    folder = _compat.tmpdir('mm_append_stop' + ('_ipy' if _compat.IRONPYTHON else '_cpy'))
    paths = [os.path.join(folder, 'a%d.nwc' % i) for i in range(3)]
    for p in paths:
        _touch(p)
    doc = _two_models()
    Cancelled = type('Cancelled', (Exception,), {})
    calls = []

    def report(fraction, label):
        calls.append(label)
        if len(calls) == 2:
            raise Cancelled()

    with nav.FakeNav(doc):
        out = mm.append_files(paths, doc, report=report)
    assert out['stopped'] and out['appended'] == [paths[0]]


def test_remove_isolate_hide():
    doc = _two_models()
    with nav.FakeNav(doc):
        infos = mm.models_info(doc)
        assert mm.isolate_models([infos[1]['key']], doc) == 1
        calls = doc.Models.calls
        assert calls[0][0] == 'hidden' and calls[0][2] is True and calls[0][1][0].DisplayName == 'A'
        assert calls[1][2] is False and calls[1][1][0].DisplayName == 'B'
        assert mm.set_models_hidden([infos[0]['key']], True, doc) == 1
        assert mm.show_all_models(doc) == 2
        assert doc.transactions == ['Isolate models', 'Hide models', 'Show models']
        removed, failed = mm.remove_models([infos[0]['key'], infos[1]['key']], doc)
        assert removed == ['ARCH.rvt', 'MEP.rvt'] and failed == []
        assert doc.removed == [1, 0]
        assert mm.refresh_files(doc) is True
