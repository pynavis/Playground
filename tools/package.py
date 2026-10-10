# -*- coding: utf-8 -*-
"""Builds the release zip of the whole extension and records its SHA-256 in the catalog.

    python tools/package.py           write dist/Playground.extension.zip, dist/catalog.json
                                      and refresh download.sha256 in catalog.json
    python tools/package.py --check   build the zip in memory only; exit 1 when catalog.json
                                      is stale or its sha256 is not this tree's zip

CPython 3.11, stdlib only. The zip holds one folder, Playground.extension/, with every
file of the extension except dev junk (__pycache__, *.pyc, editor backups, Thumbs.db).
Every leaf bundle's bundle.yaml inside the zip carries 'status: experimental' (added, or
an existing status: line replaced); the repo copy is never touched. The zip is
deterministic: entries sorted, fixed timestamps and permissions, text files with LF line
endings, so the same tree always gives the same bytes and the same SHA-256, on any
checkout.
"""
import hashlib
import io
import os
import re
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import build_catalog as bc  # noqa: E402

ROOT = bc.ROOT
DIST = os.path.join(ROOT, 'dist')
ZIP_NAME = bc.EXT_NAME + '.zip'
STAMP = 'status: experimental'
FIXED_TIME = (2020, 1, 1, 0, 0, 0)
# Text files go into the zip with LF line endings whatever the checkout did to them
# (core.autocrlf), so the SHA-256 depends on the tree's content only.
TEXT_SUFFIXES = ('.py', '.yaml', '.yml', '.xaml', '.md', '.json', '.txt', '.ps1', '.html',
                 '.css', '.csv', '.xml', '.js')


def stamp(text):
    """bundle.yaml text with 'status: experimental' as its status line."""
    lines = text.split('\n')
    for index, line in enumerate(lines):
        if re.match(r'^\s*status\s*:', line, re.IGNORECASE):
            lines[index] = STAMP
            return '\n'.join(lines)
    if text and not text.endswith('\n'):
        text += '\n'
    return text + STAMP + '\n'


def leaf_folders():
    """Extension-relative paths of every leaf bundle folder."""
    out = set()
    for dirpath, dirs, _ in os.walk(bc.EXT):
        dirs[:] = [d for d in dirs if d not in bc.JUNK_DIRS]
        if bc.kind_of(os.path.basename(dirpath)) in bc.LEAF_KINDS:
            out.add(bc.rel(dirpath))
    return out


def entries():
    """[(path inside the zip, bytes)] sorted by path."""
    leaves = leaf_folders()
    files = {}
    for path in bc.files_in(bc.EXT, True):
        with open(os.path.join(bc.EXT, path), 'rb') as handle:
            data = handle.read()
        if path.lower().endswith(TEXT_SUFFIXES):
            data = data.replace(b'\r\n', b'\n')
        files[path] = data
    for leaf in leaves:
        path = leaf + '/bundle.yaml'
        text = files[path].decode('utf-8-sig') if path in files else ''
        files[path] = stamp(text.replace('\r\n', '\n')).encode('utf-8')
    return sorted((bc.EXT_NAME + '/' + path, data) for path, data in files.items())


def build_zip():
    """The zip as bytes."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries():
            info = zipfile.ZipInfo(name, FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            info.create_system = 0
            archive.writestr(info, data, compresslevel=9)
    return buffer.getvalue()


def write(path, data):
    folder = os.path.dirname(path)
    if not os.path.isdir(folder):
        os.makedirs(folder)
    with open(path, 'wb') as handle:
        handle.write(data)


def main(argv):
    try:
        data = build_zip()
        digest = hashlib.sha256(data).hexdigest()
        text, old_text = bc.render(bc.CATALOG, digest)
    except bc.CatalogError as error:
        sys.stderr.write('package: %s\n' % error)
        return 1
    if '--check' in argv:
        if text != old_text:
            sys.stderr.write('package: catalog.json does not match this tree (sha256 %s); '
                             'run python tools/package.py\n' % digest)
            return 1
        print('package: catalog.json matches this tree; sha256 %s (%d bytes)' % (digest, len(data)))
        return 0
    write(os.path.join(DIST, ZIP_NAME), data)
    write(bc.CATALOG, text.encode('utf-8'))
    write(os.path.join(DIST, 'catalog.json'), text.encode('utf-8'))
    print('package: wrote dist/%s (%d bytes) and dist/catalog.json' % (ZIP_NAME, len(data)))
    print('sha256 %s' % digest)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
