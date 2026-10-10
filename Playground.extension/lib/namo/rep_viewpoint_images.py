# -*- coding: utf-8 -*-
"""Viewpoints to Images: one image per saved viewpoint into a dated folder, plus an
index.html contact sheet (thumbnails linking to the full images).

The logic is namo.capture; this module is the reports contract around it, so the
ribbon button, Report Templates, Scheduled Reports and `pynavis run` produce the same
folder. config['folder'] is the parent folder ('' = %APPDATA%\\pyNavis\\playground\\reports) and
config['name_template'] names the run's own subfolder; config['image_template'] names
each image ({n} {name} {folder} {path} {date} {file}). config['views'] is a
vp_common spec ({'mode': 'all' | 'folders' | 'list', ...}), so a scheduled run picks
up views added to a chosen folder later. The result adds 'folder' and 'index'.
"""
import os

from namo import reports

TITLE = 'Viewpoints to Images'
NAME_TEMPLATE = '{file} - Viewpoint images - {date}'


def default_config():
    from namo import capture, vp_common
    return reports.base_config(name_template=NAME_TEMPLATE, views=vp_common.all_spec(), width=1920,
                               height=1080, format='png', quality=90,
                               image_template=capture.DEFAULT_TEMPLATE, overlay=False, index_html=True)


def describe(config):
    from namo import vp_common
    return '%s, %d x %d %s' % (vp_common.describe_spec(config.get('views')), int(config.get('width') or 0),
                               int(config.get('height') or 0), str(config.get('format') or 'png').upper())


def _active(doc):
    if doc is not None:
        return doc
    from pynavis._api import Application
    return Application.ActiveDocument


def run(config, doc=None, interactive=True, progress=None):
    """Captures the chosen viewpoints; see the module docstring."""
    from namo import capture, images, naming, paths, vp_common
    document = _active(doc)
    rows = vp_common.view_rows(document)
    if not rows:
        return reports.result('info', 'No saved viewpoints', 'Save some viewpoints, then run this again.')
    chosen = vp_common.select_rows(rows, config.get('views'))
    missing = vp_common.missing_views(rows, config.get('views'))
    if not chosen:
        detail = 'None of the chosen viewpoints are in this model.'
        if missing:
            detail += ' Missing: %s.' % ', '.join(missing[:3])
        return reports.result('info', 'No viewpoints to capture', detail)
    try:
        images.check_size(config.get('width'), config.get('height'))
    except (TypeError, ValueError) as error:
        return reports.result('error', 'Image size not usable', str(error))
    values = {}
    if not naming.standard_values(document).get('file'):
        values['file'] = 'Untitled'
    # unique: the default name is dated by the DAY, and a second run that day must not
    # overwrite the first run's images and contact sheet.
    folder = reports.output_path(config, 'Viewpoint images', '', values, unique=True)
    paths.ensure_dir(folder)
    with capture.KeepState(document, [r['item'] for r in chosen]):
        results, stopped = capture.capture_rows(chosen, folder, config, document, progress, 0.0, 0.9)
    written = [r for r in results if r['path']]
    failed = [(r['row']['path'], r['error']) for r in results if r['error']]
    if stopped and not written:
        raise reports.Cancelled()
    index = None
    if config.get('index_html', True) and written:
        if progress:
            vp_common.report_step(progress, 0.92, 'Writing the contact sheet')
        thumbs = capture.thumbs(written, folder)
        items = [{'image': r['path'], 'thumb': thumbs.get(r['path']), 'caption': r['row']['name'],
                  'detail': vp_common.folder_label(r['row']['folder'])} for r in written]
        standard = naming.standard_values(document)
        meta = [('Model', standard.get('file') or 'Untitled'), ('Viewpoints', len(written)),
                ('Size', '%d x %d' % (int(config['width']), int(config['height']))),
                ('Made by', standard.get('user') or '')]
        index = os.path.join(folder, 'index.html')
        try:
            capture.write_index(index, 'Viewpoint images', standard.get('title') or '', meta,
                                [('Viewpoints', 'Click an image to open it full size.', items)])
        except (IOError, OSError) as error:
            failed.append(('index.html', str(error)))
            index = None
    level, message, detail = capture.summary([('viewpoint images', len(written), failed)], stopped, len(chosen))
    if missing and level == 'success':
        level = 'warning'
        detail = '%s %s not found.' % (detail, vp_common.plural(len(missing), 'chosen viewpoint'))
    detail = (detail + ' ' if detail else '') + folder
    out = reports.result(level, message, detail, paths=([index] if index else []) + [r['path'] for r in written])
    out['folder'] = folder
    out['index'] = index
    return out
