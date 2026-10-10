# -*- coding: utf-8 -*-
"""Batch PDF Printer: an ordered set of saved viewpoints as one PDF handout.

Title page (title, project name and number, company, model, date, author, how many
views), an optional contents page (or pages), then one landscape page per viewpoint:
its name and folder, the image filling the page, its comments under it, a footer line
and 'Page n of m'. A4, A3, Letter or Tabloid.

Images are captured as JPEG (namo.images with a quality setting) into a temporary
folder and embedded unchanged by namo.pdf (the README's rule: JPEG, never RGBA PNG,
into PDFs), every page box the same size so the handout reads as a set. The temporary
folder is removed afterwards.

config['views'] is a vp_common spec; config['order'] an optional [[folder, name]]
hand order (views it does not name follow in tree order). The page plan and layout
are pure functions below (tested).
"""
import os
import shutil
import time

from namo import reports

TITLE = 'Batch PDF Printer'
NAME_TEMPLATE = '{file} - Viewpoints - {date}'
PAPERS = ['A4', 'A3', 'Letter', 'Tabloid']
MARGIN = 12.0
HEADER_MM = 15.0
COMMENT_BAND_MM = 20.0
FOOTER_GAP_MM = 3.0
CONTENTS_SIZE = 10
MAX_SIDE_PX = 4000
INK = (26, 26, 26)
MUTED = (107, 107, 107)
LINE = (214, 214, 214)


def default_config():
    from namo import vp_common
    return reports.base_config(name_template=NAME_TEMPLATE, views=vp_common.all_spec(), order=[],
                               paper='A4', quality=85, dpi=150, title_page=True, contents=True,
                               comments=True, title='', footer=u'{project} · {file} · {date}')


def describe(config):
    from namo import vp_common
    return '%s, %s landscape, JPEG %d%%' % (vp_common.describe_spec(config.get('views')),
                                           str(config.get('paper') or 'A4'), int(config.get('quality') or 85))


def option_fields(cfg):
    """The ui.form fields of the Batch PDF button's options step (cfg: default_config
    plus 'open' and 'hand_order')."""
    return [
        {'kind': 'radio', 'key': 'hand_order', 'label': 'Page order',
         'options': [('Folder order', False), ('Set the order by hand', True)], 'default': bool(cfg['hand_order']),
         'inline': True},
        {'kind': 'choice', 'key': 'paper', 'label': 'Paper (landscape)', 'options': PAPERS,
         'default': cfg['paper'] if cfg['paper'] in PAPERS else 'A4'},
        {'kind': 'radio', 'key': 'dpi', 'label': 'Image detail', 'inline': True,
         'options': [('Standard (150 dpi)', 150), ('High (220 dpi)', 220)], 'default': int(cfg['dpi'] or 150), 'fallback': 150},
        {'kind': 'int', 'key': 'quality', 'label': 'JPEG quality', 'suffix': '%', 'min': 40, 'max': 100,
         'default': int(cfg['quality'] or 85)},
        {'kind': 'text', 'key': 'title', 'label': 'Title', 'default': cfg['title'],
         'placeholder': 'Empty: the model name'},
        {'kind': 'check', 'key': 'title_page', 'label': 'Title page', 'default': cfg['title_page']},
        {'kind': 'check', 'key': 'contents', 'label': 'Contents page', 'default': cfg['contents']},
        {'kind': 'check', 'key': 'comments', 'label': 'Viewpoint comments under each image',
         'default': cfg['comments']},
        {'kind': 'text', 'key': 'footer', 'label': 'Page footer', 'default': cfg['footer'],
         'hint': 'Tokens: {project} {project_number} {file} {date} {user} {company}'},
        {'kind': 'check', 'key': 'open', 'label': 'Open the PDF when done', 'default': cfg['open']},
    ]


# ---- pure layout -------------------------------------------------------------------


def page_box(paper, comments=True, margin=MARGIN):
    """(page width, page height, image box (x, y, w, h)) in mm for a landscape
    view page: under a header, above the comments band and the footer."""
    from namo import pdf
    width, height = pdf.page_size(paper, landscape=True)
    top = margin + HEADER_MM
    bottom = height - margin - FOOTER_GAP_MM - (COMMENT_BAND_MM if comments else 0.0)
    return width, height, (margin, top, width - 2 * margin, max(10.0, bottom - top))


def image_pixels(box_w, box_h, dpi, max_side=MAX_SIDE_PX):
    """(w, h) pixels for an image filling box_w x box_h mm at dpi, the long side
    capped at max_side (the aspect ratio kept)."""
    w = box_w / 25.4 * float(dpi)
    h = box_h / 25.4 * float(dpi)
    scale = min(1.0, float(max_side) / max(w, h))
    return max(16, int(round(w * scale))), max(16, int(round(h * scale)))


def contents_rows_per_page(paper, margin=MARGIN):
    from namo import pdf
    _w, height = pdf.page_size(paper, landscape=True)
    usable = height - 2 * margin - 22.0
    return max(5, int(usable // pdf.line_height(CONTENTS_SIZE, 1.5)))


def plan_pages(count, title_page, contents, per_contents_page):
    """(contents page count, page number of the first view) for `count` views."""
    contents_pages = 0
    if contents and count:
        contents_pages = (count + per_contents_page - 1) // per_contents_page
    first = 1 + (1 if title_page else 0) + contents_pages
    return contents_pages, first


DOT = u'·'


def footer_text(template, values):
    """The rendered footer; parts separated by a middle dot ({project} . {file}) keep
    their dots only between parts that are not empty."""
    from namo import naming
    text, _missing = naming.render(template or '', values)
    parts = [naming.sanitize(p) for p in text.split(DOT)]
    return (u' %s ' % DOT).join(p for p in parts if p)


def comment_text(comments):
    """The comments of a view as one block: 'Author: text' lines."""
    lines = []
    for comment in comments or []:
        body = ' '.join(str(comment.get('body') or '').split())
        if not body:
            continue
        author = comment.get('author')
        lines.append(('%s: %s' % (author, body)) if author else body)
    return '\n'.join(lines)


def build(path, views, config, values, created=None):
    """Writes the PDF. views: [{'name', 'folder', 'image' (jpeg path or None),
    'comments' [dicts]}]. Pure apart from reading the JPEG files. Returns path."""
    from namo import pdf
    paper = config.get('paper') or 'A4'
    with_comments = bool(config.get('comments', True))
    title = config.get('title') or values.get('title') or values.get('file') or 'Viewpoints'
    doc = pdf.Document(size=paper, landscape=True, margin_mm=MARGIN, title=title,
                       author=values.get('user') or None, subject='Viewpoints', created=created)
    per = contents_rows_per_page(paper)
    contents_pages, first = plan_pages(len(views), config.get('title_page', True), config.get('contents', True), per)
    footer = footer_text(config.get('footer'), values)

    def foot(page):
        if footer:
            page.text(page.left, page.height - MARGIN / 2.0 - 1.2, footer, size=8, color=MUTED,
                      max_width=page.content_width * 0.7)

    if config.get('title_page', True):
        page = doc.page()
        y = page.top + page.content_height * 0.28
        y = page.wrap(page.left, y, page.content_width * 0.8, title, size=26, bold=True, color=INK, max_lines=3)
        page.line(page.left, y + 4, page.left + 60, y + 4, width_mm=0.6, color=INK)
        y += 12
        rows = [('Project', ' '.join(p for p in (values.get('project_number'), values.get('project')) if p)),
                ('Company', values.get('company')), ('Model', values.get('file')),
                ('Date', str(values.get('date') or '')), ('Prepared by', values.get('user')),
                ('Viewpoints', '{:,}'.format(len(views)))]
        for label, value in rows:
            if not value:
                continue
            page.text(page.left, y, label, size=10, color=MUTED)
            page.text(page.left + 32, y, str(value), size=10, color=INK, max_width=page.content_width - 40)
            y += pdf.line_height(10, 1.7)
        foot(page)

    if contents_pages:
        for c in range(contents_pages):
            page = doc.page()
            page.text(page.left, page.top, 'Contents', size=16, bold=True, color=INK)
            y = page.top + 12
            for i in range(c * per, min(len(views), (c + 1) * per)):
                view = views[i]
                label = view['name'] if not view.get('folder') else '%s / %s' % (view['folder'], view['name'])
                page.text(page.left, y, '%d' % (i + 1), size=CONTENTS_SIZE, color=MUTED)
                page.text(page.left + 10, y, label, size=CONTENTS_SIZE, color=INK, max_width=page.content_width - 30)
                page.text(page.right, y, '%d' % (first + i), size=CONTENTS_SIZE, color=MUTED, align='right')
                y += pdf.line_height(CONTENTS_SIZE, 1.5)
            foot(page)

    width, height, box = page_box(paper, with_comments)
    for view in views:
        page = doc.page()
        page.text(page.left, page.top, view['name'], size=14, bold=True, color=INK, max_width=page.content_width)
        if view.get('folder'):
            page.text(page.left, page.top + 7.5, view['folder'], size=9, color=MUTED, max_width=page.content_width)
        x, y, w, h = box
        if view.get('image'):
            page.image(view['image'], x, y, w, h, fit=True)
        else:
            page.rect(x, y, w, h, stroke=LINE, width_mm=0.3)
            page.text(x + w / 2.0, y + h / 2.0, 'No image: %s' % (view.get('error') or 'capture failed'),
                      size=10, color=MUTED, align='center', max_width=w - 10)
        if with_comments:
            text = comment_text(view.get('comments'))
            if text:
                page.wrap(page.left, y + h + 3.0, page.content_width, text, size=9, color=INK, max_lines=4)
        page.line(page.left, page.height - MARGIN + 1.0, page.right, page.height - MARGIN + 1.0,
                  width_mm=0.2, color=LINE)
        foot(page)
    doc.page_numbers(size=8, color=MUTED)
    return doc.save(path)


# ---- the report ------------------------------------------------------------------------


def _active(doc):
    if doc is not None:
        return doc
    from pynavis._api import Application
    return Application.ActiveDocument


def run(config, doc=None, interactive=True, progress=None):
    """Captures, lays out and saves the PDF; see the module docstring."""
    from namo import capture, images, naming, paths, session, vp_common
    document = _active(doc)
    rows = vp_common.view_rows(document)
    if not rows:
        return reports.result('info', 'No saved viewpoints', 'Save some viewpoints, then run this again.')
    chosen = vp_common.apply_order(vp_common.select_rows(rows, config.get('views')), config.get('order'))
    if not chosen:
        return reports.result('info', 'No viewpoints to print', 'None of the chosen viewpoints are in this model.')
    paper = config.get('paper') if config.get('paper') in PAPERS else 'A4'
    config = dict(config)
    config['paper'] = paper
    values = naming.standard_values(document)
    if not values.get('file'):
        values['file'] = 'Untitled'
    path = reports.output_path(config, 'Viewpoints', 'pdf', {'file': values['file']})
    _w, _h, box = page_box(paper, bool(config.get('comments', True)))
    width, height = image_pixels(box[2], box[3], int(config.get('dpi') or 150))
    temp = os.path.join(paths.data_root(), 'tmp', 'batch-pdf-%d' % int(time.time() * 1000))
    paths.ensure_dir(temp)
    views = []
    stopped = False
    try:
        with capture.KeepState(document, [r['item'] for r in chosen]):
            for index, row in enumerate(chosen):
                if vp_common.report_step(progress, 0.85 * index / len(chosen),
                                         'Capturing %d of %d: %s' % (index + 1, len(chosen), row['name'])):
                    stopped = True
                    break
                view = {'name': row['name'], 'folder': row['folder'], 'image': None, 'error': None,
                        'comments': vp_common.comments_of(row['item'])}
                image = os.path.join(temp, '%04d.jpg' % (index + 1))
                try:
                    images.capture_saved(row['item'], image, width=width, height=height, doc=document,
                                         quality=int(config.get('quality') or 85))
                    view['image'] = image
                except Exception as error:
                    if vp_common.is_cancel(error):
                        stopped = True
                        break
                    session.log('warning', 'Batch PDF: %s failed: %s' % (row['path'], error))
                    view['error'] = str(error)
                views.append(view)
        if stopped and not views:
            raise reports.Cancelled()
        vp_common.report_step(progress, 0.9, 'Writing the PDF')
        try:
            build(path, views, config, values)
        except (IOError, OSError) as error:
            return reports.result('error', 'Could not save the PDF',
                                  '%s. Close it in your PDF viewer, then try again.' % error)
    finally:
        shutil.rmtree(temp, ignore_errors=True)
    failed = [v for v in views if v['error']]
    pages = len(views)
    if stopped:
        out = reports.result('warning', 'Stopped after %s' % vp_common.plural(pages, 'viewpoint'),
                             'The PDF holds the pages made so far. %s' % path, paths=[path])
    elif failed:
        out = reports.result('warning', 'PDF saved, %s without an image' % vp_common.plural(len(failed), 'page'),
                             '%s: %s' % (failed[0]['name'], failed[0]['error']), paths=[path])
    else:
        out = reports.result('success', 'Saved %s as a PDF' % vp_common.plural(pages, 'viewpoint'), path,
                             paths=[path])
    out['pdf'] = path
    return out
