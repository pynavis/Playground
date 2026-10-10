# -*- coding: utf-8 -*-
"""Appends many model files at once from a folder or a manifest, after a preview of what is new."""
import os

from namo import hk_sessionstats, modelmgmt, progress, transforms, ui

from pynavis import app, script, toast

DEFAULTS = {'source': 'folder', 'folder': '', 'recursive': True,
            'types': modelmgmt.types_text(modelmgmt.DEFAULT_TYPES), 'manifest': ''}


def start_folder(cfg, doc):
    if cfg['folder'] and os.path.isdir(cfg['folder']):
        return cfg['folder']
    name = doc.FileName or ''
    if name and os.path.isdir(os.path.dirname(name)):
        return os.path.dirname(name)
    return os.path.join(os.path.expanduser('~'), 'Documents')


def ask(cfg, doc):
    fields = [
        {'kind': 'radio', 'key': 'source', 'label': 'Append from', 'default': cfg['source'], 'fallback': None,
         'options': [('A folder', 'folder'), ('A manifest file (txt, csv or xlsx)', 'manifest')]},
        {'kind': 'folder', 'key': 'folder', 'label': 'Folder', 'default': start_folder(cfg, doc),
         'enabled_if': ('source', 'folder')},
        {'kind': 'check', 'key': 'recursive', 'label': 'Include subfolders', 'default': cfg['recursive'],
         'enabled_if': ('source', 'folder')},
        {'kind': 'text', 'key': 'types', 'label': 'File types', 'default': cfg['types'],
         'hint': 'Extensions separated by spaces. Leave empty for every model type Navisworks reads.',
         'enabled_if': ('source', 'folder')},
        {'kind': 'file_open', 'key': 'manifest', 'label': 'Manifest', 'default': cfg['manifest'],
         'filter': 'Manifests (*.txt;*.csv;*.xlsx)|*.txt;*.csv;*.xlsx|All files (*.*)|*.*',
         'hint': 'One file path per row; optional Order and Trade columns.',
         'enabled_if': ('source', 'manifest')},
    ]

    def check(values):
        if values['source'] == 'folder' and not values['folder']:
            return {'folder': 'Choose the folder to append from.'}
        if values['source'] == 'manifest' and not values['manifest']:
            return {'manifest': 'Choose the manifest file.'}
        return None
    return ui.form('Batch Append', fields, ok='Preview', validate=check, width=520)


def candidates(answer):
    """(candidate dicts, note or problem sentence, whether a trade column is worth showing)."""
    if answer['source'] == 'folder':
        types = modelmgmt.parse_types(answer['types'])
        files, cut = modelmgmt.scan_folder(answer['folder'], types, answer['recursive'])
        if not files:
            return [], 'Nothing matching %s in %s.' % (' '.join(types[:8]), answer['folder']), False
        for f in files:
            f['shown_folder'] = os.path.dirname(f['relative'])
            f['trade'] = ''
        note = ('Showing the first {:,} files.'.format(len(files))) if cut else None
        return files, note, False
    try:
        entries, problems = modelmgmt.read_manifest(answer['manifest'])
    except ValueError as error:
        return [], str(error), False
    out = []
    for entry in entries:
        path = entry['path']
        try:
            info = os.stat(path)
            size, mtime, exists = info.st_size, info.st_mtime, os.path.isfile(path)
        except (IOError, OSError):
            size, mtime, exists = None, None, False
        out.append({'path': path, 'name': os.path.basename(path), 'shown_folder': os.path.dirname(path),
                    'ext': modelmgmt.ext_of(path), 'size': size, 'mtime': mtime, 'exists': exists,
                    'trade': entry.get('trade') or ''})
    if not out:
        return [], problems[0] if problems else 'The manifest lists no files.', False
    return out, None, any(c['trade'] for c in out)


def preview(rows, trades, note):
    columns = ['File', 'Folder', 'Type', 'Size, MB', 'Modified', 'Status'] + (['Trade'] if trades else [])
    table = []
    for index, row in enumerate(rows):
        size = round(row['size'] / 1048576.0, 1) if row.get('size') is not None else ''
        cells = [row['name'], row['shown_folder'], row['ext'].upper(), size,
                 modelmgmt.format_time(row.get('mtime')), row['status']]
        if trades:
            cells.append(row['trade'])
        table.append({'value': index, 'cells': cells})
    new = sum(1 for r in rows if r['status'] == 'New')
    done = sum(1 for r in rows if r['status'] == 'Appended')
    prompt = '%s ticked.' % modelmgmt.plural(new, 'new file')
    if done:
        prompt += ' %s already appended.' % ('1 file is' if done == 1 else '{:,} files are'.format(done))
    if note:
        prompt += ' ' + note
    checked = [i for i, r in enumerate(rows) if r['checked']]
    return ui.choose('Batch Append', table, columns, multiselect=True, checked=checked,
                     prompt=prompt, ok='Append', width=860, height=600)


def seconds_by_key(doc, result):
    """{new model key: seconds its file took} matched by folder and file stem."""
    by_stem = {}
    for path, seconds in result['seconds'].items():
        by_stem[modelmgmt.stem_key(path)] = seconds
    out = {}
    for info in modelmgmt.models_info(doc):
        if info['key'] not in result['new_keys']:
            continue
        for path in (info['file'], info['source']):
            if path and modelmgmt.stem_key(path) in by_stem:
                out[info['key']] = by_stem[modelmgmt.stem_key(path)]
                break
    return out


def took(seconds):
    if seconds >= 60:
        return modelmgmt.format_age(seconds)
    return '%d s' % int(round(seconds))


def run():
    doc = app.get_doc()
    cfg = script.get_config(DEFAULTS)
    answer = ask(cfg, doc)
    if answer is None:
        return
    cfg.update(answer)
    script.save_config(cfg)
    found, note, trades = candidates(answer)
    if not found:
        toast.info('No model files found', note)
        return
    rows = modelmgmt.plan_append(found, modelmgmt.models_info(doc) if modelmgmt.has_models(doc) else [])
    picked = preview(rows, trades, note)
    if picked is None:
        return
    paths = [rows[i]['path'] for i in picked]
    if not paths:
        toast.info('Nothing appended', 'No files were ticked.')
        return
    result = progress.run('Batch Append', lambda report: modelmgmt.append_files(paths, doc, report),
                          'Appending')
    if result is progress.CANCELLED:
        return
    appended, failed = result['appended'], result['failed']
    if result['new_keys']:
        hk_sessionstats.record_batch(doc, seconds_by_key(doc, result))
    presets, _preset_failures = transforms.apply_auto_presets(result['new_keys'], doc)
    extra = (' Transform presets applied to %s.' % modelmgmt.join_names(presets)) if presets else ''
    if result['stopped']:
        toast.info('Appended %d of %d files' % (len(appended), len(paths)), 'Stopped before the rest.' + extra)
    elif not appended:
        name, why = failed[0]
        toast.error('Could not append the files', '%s: %s' % (os.path.basename(name), why))
    elif failed:
        name, why = failed[0]
        toast.warning('Appended %s, %d failed' % (modelmgmt.plural(len(appended), 'file'), len(failed)),
                      '%s: %s%s' % (os.path.basename(name), why, extra))
    else:
        toast.success('Appended %s' % modelmgmt.plural(len(appended), 'file'),
                      'Took %s.%s' % (took(sum(result['seconds'].values())), extra))


run()
