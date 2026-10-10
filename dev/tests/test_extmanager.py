# -*- coding: utf-8 -*-
"""namo.extmanager: registry parsing, versions, statuses, zip layouts, safe extraction,
install/update/remove between temp folders (a local zip, never the network)."""
import io
import json
import os
import zipfile

import _compat

from namo import extmanager as em


def test_parse_registry():
    data = {'extensions': [
        {'name': 'Acme Tools', 'version': '1.2', 'download': 'acme.zip', 'author': 'Acme', 'sha256': 'A' * 64},
        {'name': 'acme tools', 'download': 'x.zip'},
        {'name': '../evil', 'download': 'x.zip'},
        {'name': 'NoDownload'},
        {'name': 'Bad.extension', 'download': 'b.zip', 'sha256': 'xyz'},
        'junk']}
    entries, problems = em.parse_registry(data)
    assert [e['name'] for e in entries] == ['Acme Tools', 'Bad']
    assert entries[0]['sha256'] == 'a' * 64 and entries[1]['sha256'] == ''
    assert problems == ['acme tools is listed twice; the first entry is used.',
                        'Entry 3 has no usable name.', 'NoDownload has no download.',
                        'Bad has a sha256 that is not 64 hex digits; it will not be checked.',
                        'Entry 6 is not an object.']
    assert em.parse_registry({'nope': 1}) == ([], ['The registry has no "extensions" list.'])
    assert em.parse_registry([{'name': 'L', 'download': 'l.zip'}])[0][0]['name'] == 'L'


def test_versions():
    assert em.compare_versions('1.10', '1.9') == 1
    assert em.compare_versions('2.0', '2') == 0
    assert em.compare_versions('1.2.0-beta', '1.2.0') == -1
    assert em.compare_versions('v3', '2.9.9') == 1
    assert em.compare_versions('', '0.1') == -1


def test_status_rows():
    entries = [{'name': 'Acme', 'version': '2.0', 'author': 'A', 'description': 'd'},
               {'name': 'Beta', 'version': '1.0', 'author': '', 'description': ''},
               {'name': 'Playground', 'version': '9', 'author': '', 'description': ''}]
    installed = [{'name': 'Acme', 'version': '1.5', 'folder': 'f1'}, {'name': 'Mine', 'version': '', 'folder': 'f2'},
                 {'name': 'Playground', 'version': '', 'folder': 'f3'}, {'name': 'pyNavis', 'version': '', 'folder': 'f4'}]
    rows = em.status_rows(entries, installed)
    assert [(r['value'], r['cells'][3]) for r in rows] == [
        ('Acme', 'Update available'), ('Beta', 'Not installed'), ('Playground', 'Managed by its installer'),
        ('Mine', 'Not in the registry'), ('pyNavis', 'Managed by its installer')]
    assert rows[0]['cells'][:3] == ['Acme', '2.0', '1.5']
    assert rows[3]['cells'][2] == 'yes'


def test_resolve_download():
    assert em.resolve_download('https://x/a.zip', 'C:\\r\\reg.json') == 'https://x/a.zip'
    assert em.resolve_download('a.zip', 'https://h/p/reg.json') == 'https://h/p/a.zip'
    assert em.resolve_download('sub\\a.zip', 'C:\\r\\reg.json') == os.path.normpath('C:\\r\\sub\\a.zip')
    assert em.resolve_download('\\\\srv\\a.zip', 'C:\\r\\reg.json') == '\\\\srv\\a.zip'


def test_zip_roots():
    assert em.zip_root(['Acme.extension/A.tab/P.panel/X.pushbutton/script.py']) == ('Acme.extension/', 'Acme.extension')
    assert em.zip_root(['repo-main/README.md', 'repo-main/Acme.extension/extension.yaml']) == \
        ('repo-main/Acme.extension/', 'Acme.extension')
    assert em.zip_root(['A.tab/P.panel/X.pushbutton/script.py'], 'Acme') == ('', 'Acme.extension')
    assert em.zip_root(['top/A.tab/P.panel/script.py', 'top/README.md'], 'Acme') == ('top/', 'Acme.extension')
    raised = _compat.raises(ValueError, em.zip_root, ['a/One.extension/x', 'b/Two.extension/y'])
    assert '2 extensions' in str(raised)
    assert em.zip_root(['a/One.extension/x', 'b/Two.extension/y'], 'two') == ('b/Two.extension/', 'Two.extension')
    raised = _compat.raises(ValueError, em.zip_root, ['readme.txt'], 'Acme')
    assert 'no pyNavis extension' in str(raised)


def test_safe_target():
    dest = os.path.join('C:' + os.sep, 'dest')
    assert em.safe_target(dest, 'A.tab/x.py') == os.path.join(dest, 'A.tab', 'x.py')
    assert em.safe_target(dest, '../evil.py') is None
    assert em.safe_target(dest, 'a/../../evil.py') is None
    assert em.safe_target(dest, '/abs.py') is None
    assert em.safe_target(dest, 'C:/abs.py') is None
    assert em.safe_target(dest, '') is None


def _zip(path, files):
    with zipfile.ZipFile(path, 'w') as archive:
        for name, text in files:
            archive.writestr(name, text)
    return path


def test_install_update_remove():
    base = _compat.tmpdir('extmanager_flow')
    root = os.path.join(base, 'extensions')
    trash = os.path.join(base, 'trash')
    v1 = _zip(os.path.join(base, 'acme1.zip'), [
        ('acme-main/README.md', 'hi'),
        ('acme-main/Acme.extension/extension.yaml', 'name: Acme\n'),
        ('acme-main/Acme.extension/Acme.tab/P.panel/X.pushbutton/script.py', '"""X."""\n')])
    registry = os.path.join(base, 'registry.json')
    with io.open(registry, 'w', encoding='utf-8') as handle:
        handle.write(u'%s' % json.dumps({'extensions': [{'name': 'Acme', 'version': '1.0', 'download': 'acme1.zip',
                                                          'sha256': em.sha256_of(v1)}]}))
    entries, problems = em.load_registry(registry)
    assert problems == [] and entries[0]['name'] == 'Acme'
    url = em.resolve_download(entries[0]['download'], registry)
    downloaded = em.download(url, os.path.join(base, 'tmp', 'a.zip'))
    assert em.sha256_of(downloaded) == entries[0]['sha256']
    folder = em.install_zip(downloaded, entries[0], root, trash)
    assert folder == os.path.join(root, 'Acme.extension')
    assert os.path.isfile(os.path.join(folder, 'Acme.tab', 'P.panel', 'X.pushbutton', 'script.py'))
    installed = em.scan_installed([root])
    assert installed[0]['name'] == 'Acme' and installed[0]['version'] == '1.0' and installed[0]['yaml_name'] == 'Acme'
    v2 = _zip(os.path.join(base, 'acme2.zip'), [('Acme.tab/P.panel/Y.pushbutton/script.py', '"""Y."""\n')])
    folder = em.install_zip(v2, {'name': 'Acme', 'version': '2.0', 'download': 'acme2.zip'}, root, trash)
    assert os.path.isdir(os.path.join(folder, 'Acme.tab', 'P.panel', 'Y.pushbutton'))
    assert not os.path.exists(os.path.join(folder, 'Acme.tab', 'P.panel', 'X.pushbutton'))
    assert len(os.listdir(trash)) == 1 and em.scan_installed([root])[0]['version'] == '2.0'
    bad = _zip(os.path.join(base, 'bad.zip'), [('Acme.extension/../../evil.py', 'x')])
    raised = _compat.raises(ValueError, em.install_zip, bad, {'name': 'Acme'}, root, trash)
    assert 'unsafe path' in str(raised)
    assert em.scan_installed([root])[0]['version'] == '2.0'         # the failed update kept the old copy
    assert [n for n in os.listdir(root) if 'installing' in n] == []
    em.uninstall(folder, trash)
    assert em.scan_installed([root]) == [] and len(os.listdir(trash)) == 2
    raised = _compat.raises(ValueError, em.install_zip, v2, {'name': 'Playground'}, root, trash)
    assert 'own installer' in str(raised)
    raised = _compat.raises(ValueError, em.uninstall, os.path.join(root, 'pyNavis.extension'), trash)
    assert 'own uninstaller' in str(raised)


def test_registry_errors_and_default():
    base = _compat.tmpdir('extmanager_registry')
    raised = _compat.raises(IOError, em.load_registry, os.path.join(base, 'missing.json'))
    assert 'does not exist' in str(raised)
    broken = os.path.join(base, 'broken.json')
    with io.open(broken, 'w', encoding='utf-8') as handle:
        handle.write(u'{nope')
    assert 'not valid JSON' in str(_compat.raises(IOError, em.load_registry, broken))
    assert em.default_registry(base) == em.PLACEHOLDER
    os.makedirs(os.path.join(base, 'playground-team'))
    target = os.path.join(base, 'playground-team', 'extension-registry.json')
    with io.open(target, 'w', encoding='utf-8') as handle:
        handle.write(u'{"extensions": []}')
    assert em.default_registry(base) == target
    raised = _compat.raises(IOError, em.download, os.path.join(base, 'x.zip'), os.path.join(base, 'y.zip'))
    assert 'does not exist' in str(raised)


def test_file_url_downloads():
    # 'file:///C:/x.zip' used to become '/C:/x.zip' (the first 7 characters cut), which
    # never exists: a registry pointing at file URLs could not install anything.
    assert em.file_url_path('file:///C:/ext/a%20b.zip') == r'C:\ext\a b.zip'
    assert em.file_url_path('file://C:/ext/a.zip') == r'C:\ext\a.zip'
    assert em.file_url_path('file://server/share/a.zip') == r'\\server\share\a.zip'
    assert em.file_url_path(r'C:\ext\a.zip') == r'C:\ext\a.zip'
    base = _compat.tmpdir('extmanager_file_url')
    source = _zip(os.path.join(base, 'acme.zip'), [('Acme.extension/extension.yaml', 'name: Acme\n')])
    url = 'file:///' + os.path.abspath(source).replace(os.sep, '/')
    copied = em.download(url, os.path.join(base, 'tmp', 'a.zip'))
    assert em.sha256_of(copied) == em.sha256_of(source)
