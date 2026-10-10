# -*- coding: utf-8 -*-
"""Images in batches: saved viewpoints, clash results and Playground issues, plus the
index.html contact sheet that goes with them.

Every capture goes through namo.images (Document.GenerateImage / TestsImageForResult)
inside ONE KeepState (images.ViewKeeper plus the user's hidden items and overrides
when the captured views carry their own), so the user's view comes back afterwards. A cancel between images stops the batch and keeps what was written
(the caller says "Stopped after N"). Failures per image are collected, never fatal.

The contact sheet is a namo.htmlreport page whose thumbnails (JPEG, 480 px, in a
'thumbs' folder beside it) link to the full images by RELATIVE paths, so the folder
can be zipped and sent as it is.

Issues come from namo.issues / namo.issueapi when that module set is installed
(guarded import); without it the issues source reports itself unavailable.
"""
import os

FORMATS = [('PNG', 'png'), ('JPG', 'jpg')]
THUMB_PX = 480
DEFAULT_TEMPLATE = '{n:00} {name}'
CLASH_TEMPLATE = '{n:000} {name}'
ISSUE_TEMPLATE = '{id} {title}'


# ---- pure ---------------------------------------------------------------------------


def file_names(entries, template, ext, fallback='Image'):
    """Safe, unique (case-insensitive) file names for entries (dicts of tokens),
    numbered {n} from 1. A '/' in a token becomes ' - '."""
    from namo import naming, paths
    ext = ext.lstrip('.').lower()
    taken = set()
    out = []
    for index, values in enumerate(entries):
        tokens = {}
        for key in values:
            value = values[key]
            tokens[key] = value.replace('/', ' - ') if isinstance(value, str) else value
        tokens['n'] = index + 1
        name, _missing = naming.render(template or DEFAULT_TEMPLATE, tokens)
        # an empty token leaves its separator hanging: '{folder}_{name}' at top level
        name = naming.sanitize(name).strip(' _-.')
        name = paths.safe_filename(name) if name else ''
        if not name or name == 'untitled':
            name = paths.safe_filename('%s %d' % (fallback, index + 1))
        base = name
        count = 2
        while (name + '.' + ext).lower() in taken:
            name = '%s (%d)' % (base, count)
            count += 1
        taken.add((name + '.' + ext).lower())
        out.append(name + '.' + ext)
    return out


def ext_for(fmt):
    return 'jpg' if str(fmt).lower() in ('jpg', 'jpeg') else 'png'


def relative_url(path, start):
    """A URL path from folder start to path, with forward slashes and spaces kept
    as %20 (for href/src in the contact sheet)."""
    rel = os.path.relpath(path, start).replace('\\', '/')
    out = []
    for ch in rel:
        if ch == ' ':
            out.append('%20')
        elif ch in '#%?':
            out.append('%%%02X' % ord(ch))
        else:
            out.append(ch)
    return ''.join(out)


def grid_html(items, folder, columns=4):
    """Raw HTML for a contact-sheet grid: [{'image', 'thumb', 'caption', 'detail'}]
    (absolute paths), linked relative to folder. Text is escaped here."""
    from namo import htmlreport
    parts = ['<div class="gal" style="--cols:%d">' % int(columns)]
    for item in items:
        image = relative_url(item['image'], folder)
        thumb = relative_url(item.get('thumb') or item['image'], folder)
        caption = htmlreport.escape(item.get('caption') or '')
        detail = item.get('detail')
        parts.append('<figure><a href="%s"><img src="%s" alt="%s" loading="lazy" '
                     'style="display:block;width:100%%;height:auto;border:1px solid var(--line)"></a>'
                     '<figcaption>%s%s</figcaption></figure>' % (
                         htmlreport.escape(image), htmlreport.escape(thumb), caption, caption,
                         ('<br><span style="color:var(--muted)">%s</span>' % htmlreport.escape(detail))
                         if detail else ''))
    parts.append('</div>')
    return ''.join(parts)


def summary(sections, stopped, total):
    """(level, message, detail) for a capture run: sections [(label, written, failed
    [(name, error)])]."""
    from namo import vp_common
    written = sum(s[1] for s in sections)
    failed = [f for s in sections for f in s[2]]
    if stopped:
        return ('warning', 'Stopped after %s of %s' % (vp_common.count_text(written), vp_common.plural(total, 'image')),
                'The images saved so far are in the folder.')
    if failed and not written:
        return ('error', 'Could not save the images', '%s: %s' % failed[0])
    parts = ['%s %s' % (vp_common.count_text(s[1]), s[0]) for s in sections if s[1]]
    if failed:
        return ('warning', 'Saved %s, %s failed' % (vp_common.plural(written, 'image'),
                                                    vp_common.count_text(len(failed))), '%s: %s' % failed[0])
    if not written:
        return ('info', 'No images saved', 'Nothing matched the choices.')
    return ('success', 'Saved %s' % vp_common.plural(written, 'image'), ', '.join(parts) + '.')


def image_fields(cfg, folder_default, template_key='image_template', with_template=True):
    """ui.form fields for size, format, quality, file names and the folder."""
    from namo import vp_common
    width, height = int(cfg.get('width') or 1920), int(cfg.get('height') or 1080)
    size = '%dx%d' % (width, height)
    if size not in [v for _l, v in vp_common.size_options()]:
        size = vp_common.CUSTOM
    fields = [
        {'kind': 'choice', 'key': 'size', 'label': 'Image size', 'options': vp_common.size_options(),
         'default': size},
        {'kind': 'int', 'key': 'width', 'label': 'Width', 'suffix': 'px', 'min': 16, 'max': 8000,
         'default': width, 'enabled_if': ('size', vp_common.CUSTOM)},
        {'kind': 'int', 'key': 'height', 'label': 'Height', 'suffix': 'px', 'min': 16, 'max': 8000,
         'default': height, 'enabled_if': ('size', vp_common.CUSTOM)},
        {'kind': 'radio', 'key': 'format', 'label': 'Format', 'options': FORMATS, 'inline': True,
         'default': ext_for(cfg.get('format', 'png'))},
        {'kind': 'int', 'key': 'quality', 'label': 'JPG quality', 'suffix': '%', 'min': 30, 'max': 100,
         'default': int(cfg.get('quality') or 90), 'enabled_if': ('format', 'jpg')},
    ]
    if with_template:
        fields.append({'kind': 'text', 'key': template_key, 'label': 'File names',
                       'default': cfg.get(template_key) or DEFAULT_TEMPLATE, 'required': True,
                       'hint': 'Tokens: {n:00} {name} {folder} {date} {file}'})
    fields.append({'kind': 'folder', 'key': 'folder', 'label': 'Save in',
                   'default': cfg.get('folder') or folder_default, 'required': True,
                   'hint': 'A dated folder for this run is made inside it.'})
    return fields


def image_values(cfg, values):
    """cfg updated from image_fields' values (size resolved)."""
    from namo import vp_common
    out = dict(cfg)
    size = vp_common.size_from(values.get('size'), values.get('width'), values.get('height'))
    if size is not None:
        out['width'], out['height'] = size
    for key in ('format', 'quality', 'folder', 'image_template'):
        if key in values and values[key] is not None:
            out[key] = values[key]
    return out


CLASH_STATUSES = ['New', 'Active', 'Reviewed', 'Approved', 'Resolved']


def source_fields(cfg, folder_default, have_views, have_tests, have_issues):
    """The ui.form fields of Batch Image Export's first step: the sources, then
    image_fields (no file name template) and 'open'."""
    fields = [{'kind': 'label', 'text': 'Sources', 'muted': True}]
    fields.append({'kind': 'check', 'key': 'views_on', 'label': 'Saved viewpoints',
                   'default': cfg['views_on'] and have_views})
    fields.append({'kind': 'check', 'key': 'clashes_on', 'label': 'Clash results (top-level groups and clashes)',
                   'default': cfg['clashes_on'] and have_tests})
    if have_issues:
        fields.append({'kind': 'check', 'key': 'issues_on', 'label': 'Playground issues with a saved view',
                       'default': cfg['issues_on']})
    else:
        fields.append({'kind': 'label', 'text': 'Playground issues are not available in this installation.',
                       'muted': True})
    fields.append({'kind': 'separator'})
    fields += image_fields(cfg, folder_default, with_template=False)
    fields.append({'kind': 'check', 'key': 'open', 'label': 'Open the contact sheet when done',
                   'default': cfg['open']})
    return fields


def source_validator(have_views, have_tests):
    """The ui.form validate(values) of the sources step."""
    def validate(values):
        if not (values.get('views_on') or values.get('clashes_on') or values.get('issues_on')):
            return 'Tick at least one source.'
        if values.get('views_on') and not have_views:
            return {'views_on': 'This model has no saved viewpoints.'}
        if values.get('clashes_on') and not have_tests:
            return {'clashes_on': 'This model has no clash tests with results.'}
        return None
    return validate


def clash_fields(cfg):
    """The ui.form fields of the clash step. Statuses and the cap are required: an
    empty status list would mean every status to clash_units, and a blank cap None."""
    return [
        {'kind': 'multi', 'key': 'statuses', 'label': 'Statuses', 'options': CLASH_STATUSES,
         'default': cfg.get('statuses') or ['New', 'Active'], 'required': True},
        {'kind': 'int', 'key': 'cap', 'label': 'Ask before saving more than', 'suffix': 'clash images',
         'min': 1, 'max': 100000, 'default': int(cfg.get('cap') or 300), 'required': True},
    ]


def issue_fields(cfg, statuses):
    """The ui.form fields of the issues step (statuses: namo.issues.STATUSES). Required:
    an empty list would mean the default Open and In progress to pick_issues."""
    return [
        {'kind': 'multi', 'key': 'issue_statuses', 'label': 'Issue statuses', 'options': statuses,
         'default': cfg.get('issue_statuses') or [s for s in statuses if s in ('Open', 'In progress')],
         'required': True},
    ]


def size_of(cfg):
    from namo import images
    return images.check_size(int(cfg.get('width') or 1920), int(cfg.get('height') or 1080))


# ==== API half ======================================================================


TEMP_VIEW = '.Playground view to restore'


def carries_state(saved):
    """True when a saved viewpoint stores hidden items or colour overrides, which
    Navisworks applies to the model when the view is recalled."""
    try:
        return bool(saved.ContainsVisibilityOverrides) or bool(saved.ContainsAppearanceOverrides)
    except Exception:
        return False


class KeepState(object):
    """with KeepState(doc, saved_items): ... puts the user's view back afterwards.

    images.ViewKeeper restores the camera and the saved viewpoint that was current.
    When any view about to be captured stores hidden items or overrides, recalling
    it changes the MODEL, and re-applying the old current view would not undo what
    the user hid by hand since. So first the user's own state is captured
    (SavedViewpoints.CaptureRuntimeOverrides) into a temporary saved viewpoint;
    afterwards it is recalled, the camera put back and the temporary view removed,
    all inside ONE transaction, so the undo list gains one entry that changes
    nothing. Never raises on exit."""

    def __init__(self, doc, saved_items=()):
        self.doc = doc
        self.need = any(carries_state(s) for s in saved_items)
        self.temp = None
        self.tx = None
        self.keeper = None

    def __enter__(self):
        from namo import images, session, vp_common
        if self.need:
            try:
                from pynavis.viewpoints import transaction
                self.tx = transaction('Keep the view', self.doc)
                self.tx.__enter__()
                snapshot = self.doc.SavedViewpoints.CaptureRuntimeOverrides()
                snapshot.DisplayName = TEMP_VIEW
                self.doc.SavedViewpoints.AddCopy(snapshot)
                self.temp = vp_common.find_child(self.doc.SavedViewpoints.RootItem, TEMP_VIEW)
            except Exception as error:
                session.log('warning', 'could not keep the view state: %s' % error)
                self.temp = None
        # Re-applying the saved viewpoint that was current is only harmless when it
        # stores no hidden items or overrides: one that does would put its own state
        # back over what the user hid or showed by hand since recalling it (the
        # captured views here change no hidden state, so the camera alone suffices).
        try:
            current = self.doc.SavedViewpoints.CurrentSavedViewpoint
        except Exception:
            current = None
        restore = self.temp is None and not carries_state(current)
        self.keeper = images.ViewKeeper(self.doc, restore_saved=restore)
        self.keeper.__enter__()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        from namo import session
        if self.temp is not None:
            try:
                self.doc.SavedViewpoints.CurrentSavedViewpoint = self.temp
            except Exception as error:
                session.log('warning', 'could not put the view state back: %s' % error)
        try:
            self.keeper.__exit__(None, None, None)
        except Exception:
            pass
        if self.temp is not None:
            try:
                self.doc.SavedViewpoints.Remove(self.temp)
            except Exception as error:
                session.log('warning', 'could not remove %s: %s' % (TEMP_VIEW, error))
        if self.tx is not None:
            try:
                self.tx.__exit__(None, None, None)
            except Exception:
                pass
        return False


def capture_rows(rows, folder, cfg, doc=None, report=None, start=0.0, span=1.0, total=None):
    """Captures saved viewpoint rows (vp_common.view_rows) into folder. Returns
    (results [{'row', 'path', 'error'}], stopped). Wrap in KeepState."""
    from namo import images, session, vp_common
    ext = ext_for(cfg.get('format', 'png'))
    entries = [{'name': r['name'], 'folder': r['folder'], 'path': r['path']} for r in rows]
    names = file_names(entries, cfg.get('image_template') or DEFAULT_TEMPLATE, ext, 'Viewpoint')
    width, height = size_of(cfg)
    style = 'overlay' if cfg.get('overlay') else 'scene'
    results = []
    count = len(rows)
    for index, (row, name) in enumerate(zip(rows, names)):
        if vp_common.report_step(report, start + span * float(index) / max(1, count),
                                 'Viewpoint %d of %d: %s' % (index + 1, count, row['name'])):
            return results, True
        path = os.path.join(folder, name)
        try:
            images.capture_saved(row['item'], path, width=width, height=height, doc=doc, style=style,
                                 quality=cfg.get('quality', 90))
            results.append({'row': row, 'path': path, 'error': None})
        except Exception as error:
            if vp_common.is_cancel(error):
                return results, True
            session.log('warning', 'image of %s failed: %s' % (row['path'], error))
            results.append({'row': row, 'path': None, 'error': str(error)})
    return results, False


def thumbs(results, folder):
    """Writes a thumbnail per written image into folder/thumbs; returns
    {image path: thumb path} (an image whose thumbnail failed links to itself)."""
    from namo import images, session
    out = {}
    target = os.path.join(folder, 'thumbs')
    for result in results:
        path = result.get('path')
        if not path:
            continue
        thumb = os.path.join(target, os.path.splitext(os.path.basename(path))[0] + '.jpg')
        try:
            images.thumbnail(path, thumb, max_width=THUMB_PX, quality=82)
            out[path] = thumb
        except Exception as error:
            session.log('warning', 'thumbnail of %s failed: %s' % (path, error))
            out[path] = path
    return out


def write_index(path, title, subtitle, meta, sections):
    """The contact sheet. sections [(heading, intro, items for grid_html)]."""
    from namo import htmlreport
    folder = os.path.dirname(os.path.abspath(path))
    report = htmlreport.Report(title, subtitle=subtitle, meta=meta)
    for heading, intro, grid_items in sections:
        if not grid_items:
            continue
        report.section(heading, intro=intro)
        report.html(grid_html(grid_items, folder))
    return report.save(path)


def run_batch(document, folder, cfg, views=None, clashes=None, issues=None, report=None):
    """Batch Image Export: views (view rows), clashes [(test name, units)], issues
    (issue units) into folder/Viewpoints, folder/Clashes/<test>, folder/Issues, then
    folder/index.html. Returns {'sections': [(label, written, failed)], 'stopped',
    'total', 'index', 'folder'}."""
    from namo import naming, paths, vp_common
    views = views or []
    clashes = clashes or []
    issues = issues or []
    total = len(views) + sum(len(u) for _t, u in clashes) + len(issues)
    done = [0]
    sections = []
    index_sections = []
    stopped = False

    def share(count):
        start = 0.9 * done[0] / max(1, total)
        done[0] += count
        return start, 0.9 * count / max(1, total)

    with KeepState(document, [r['item'] for r in views]):
        if views:
            target = paths.ensure_dir(os.path.join(folder, 'Viewpoints'))
            start, span = share(len(views))
            results, stopped = capture_rows(views, target, cfg, document, report, start, span)
            written = [r for r in results if r['path']]
            sections.append(('viewpoint images', len(written), [(r['row']['path'], r['error'])
                                                                for r in results if r['error']]))
            index_sections.append(('Viewpoints', None, [{'image': r['path'], 'caption': r['row']['name'],
                                                         'detail': vp_common.folder_label(r['row']['folder'])}
                                                        for r in written]))
        for test_name, units in clashes:
            if stopped:
                break
            target = paths.ensure_dir(os.path.join(folder, 'Clashes', naming.sanitize(test_name, for_file=True)))
            start, span = share(len(units))
            results, stopped = capture_clashes(test_name, units, target, cfg, document, report, start, span)
            written = [r for r in results if r['path']]
            sections.append(('clash images', len(written), [(r['unit']['name'], r['error'])
                                                             for r in results if r['error']]))
            index_sections.append(('Clashes: %s' % test_name, None,
                                   [{'image': r['path'], 'caption': r['unit']['name'], 'detail': r['unit']['status']}
                                    for r in written]))
        if issues and not stopped:
            target = paths.ensure_dir(os.path.join(folder, 'Issues'))
            start, span = share(len(issues))
            results, stopped = capture_issues(issues, target, cfg, document, report, start, span)
            written = [r for r in results if r['path']]
            sections.append(('issue images', len(written), [(r['unit']['name'], r['error'])
                                                             for r in results if r['error']]))
            index_sections.append(('Issues', None, [{'image': r['path'], 'caption': r['unit']['name'],
                                                     'detail': r['unit']['status']} for r in written]))
    written_all = [item for _h, _i, items in index_sections for item in items]
    index = None
    if written_all:
        vp_common.report_step(report, 0.92, 'Writing the contact sheet')
        made = thumbs([{'path': item['image']} for item in written_all], folder)
        for _h, _i, items in index_sections:
            for item in items:
                item['thumb'] = made.get(item['image'])
        standard = naming.standard_values(document)
        meta = [('Model', standard.get('file') or 'Untitled'), ('Images', len(written_all)),
                ('Made by', standard.get('user') or '')]
        index = os.path.join(folder, 'index.html')
        try:
            write_index(index, 'Batch images', standard.get('title') or '', meta, index_sections)
        except (IOError, OSError):
            index = None
    return {'sections': sections, 'stopped': stopped, 'total': total, 'index': index, 'folder': folder}


# ---- clashes ------------------------------------------------------------------------


def clash_tests(doc=None):
    """[(test, name, top-level unit count)] of every clash test with results."""
    from namo import clashdata
    out = []
    for test in clashdata.tests(doc):
        try:
            count = len(list(test.Children))
        except Exception:
            count = 0
        out.append((test, clashdata.test_path(test), count))
    return out


def clash_units(test, statuses=None):
    """Top-level groups and ungrouped results of a test, as [{'result', 'name',
    'status', 'group'}], filtered by status names (None = all)."""
    from Autodesk.Navisworks.Api.Clash import ClashResult, ClashResultGroup
    wanted = set(s.lower() for s in statuses) if statuses else None
    out = []
    for child in test.Children:
        if not isinstance(child, (ClashResult, ClashResultGroup)):
            continue
        status = str(child.Status)
        if wanted is not None and status.lower() not in wanted:
            continue
        out.append({'result': child, 'name': str(child.DisplayName), 'status': status,
                    'group': isinstance(child, ClashResultGroup)})
    return out


def capture_clashes(test_name, units, folder, cfg, doc=None, report=None, start=0.0, span=1.0):
    """Images of clash units into folder. Returns (results, stopped)."""
    from namo import images, session, vp_common
    ext = ext_for(cfg.get('format', 'png'))
    entries = [{'name': u['name'], 'status': u['status'], 'test': test_name} for u in units]
    names = file_names(entries, cfg.get('clash_template') or CLASH_TEMPLATE, ext, 'Clash')
    width, height = size_of(cfg)
    results = []
    for index, (unit, name) in enumerate(zip(units, names)):
        if vp_common.report_step(report, start + span * float(index) / max(1, len(units)),
                                 '%s: %d of %d' % (test_name, index + 1, len(units))):
            return results, True
        path = os.path.join(folder, name)
        try:
            images.clash(unit['result'], path, width=width, height=height, doc=doc,
                         quality=cfg.get('quality', 90))
            results.append({'unit': unit, 'path': path, 'error': None})
        except Exception as error:
            if vp_common.is_cancel(error):
                return results, True
            session.log('warning', 'clash image %s failed: %s' % (unit['name'], error))
            results.append({'unit': unit, 'path': None, 'error': str(error)})
    return results, False


# ---- issues (another module set; guarded) ---------------------------------------------


def issues_module():
    """namo.issues when Playground issues are installed and offer what this needs
    (list, go_to, STATUSES), else None. Never raises."""
    try:
        from namo import issues as _issues
    except Exception:
        return None
    for name in ('list', 'go_to', 'STATUSES'):
        if not hasattr(_issues, name):
            return None
    return _issues


def issues_available():
    return issues_module() is not None


def issue_statuses():
    _issues = issues_module()
    if _issues is None:
        return []
    return [str(s) for s in _issues.STATUSES]


def pick_issues(records, statuses=None):
    """Issues that hold a camera, filtered by status names (None = Open and In
    progress), as [{'record', 'id', 'title', 'name', 'status'}]. Pure."""
    wanted = set(s.lower() for s in statuses) if statuses else set(['open', 'in progress'])
    out = []
    for record in records or []:
        if not isinstance(record, dict):
            continue
        cam = record.get('camera')
        if not cam or not cam.get('position'):
            continue
        status = str(record.get('status') or 'Open')
        if status.lower() not in wanted:
            continue
        ident = str(record.get('id') or '')
        title = str(record.get('title') or '')
        out.append({'record': record, 'id': ident, 'title': title, 'status': status,
                    'name': ('%s %s' % (ident, title)).strip() or 'Issue'})
    return out


def issue_units(statuses=None, doc=None):
    """The document's issues with a camera (see pick_issues); [] without issues."""
    _issues = issues_module()
    if _issues is None:
        return []
    try:
        records = _issues.list(doc)
    except Exception:
        records = []
    return pick_issues(records, statuses)


def _go_to_issue(unit, doc):
    """Puts the issue's camera on the view (namo.issues.go_to: units converted),
    without touching the selection."""
    _issues = issues_module()
    result = _issues.go_to(unit['record'], doc, select=False)
    if isinstance(result, dict) and not result.get('moved'):
        raise RuntimeError('the issue has no view to show')


def capture_issues(units, folder, cfg, doc=None, report=None, start=0.0, span=1.0):
    from namo import images, session, vp_common
    ext = ext_for(cfg.get('format', 'png'))
    entries = [{'id': u['id'], 'title': u['title'], 'name': u['name'], 'status': u['status']} for u in units]
    names = file_names(entries, cfg.get('issue_template') or ISSUE_TEMPLATE, ext, 'Issue')
    width, height = size_of(cfg)
    results = []
    for index, (unit, name) in enumerate(zip(units, names)):
        if vp_common.report_step(report, start + span * float(index) / max(1, len(units)),
                                 'Issue %d of %d' % (index + 1, len(units))):
            return results, True
        path = os.path.join(folder, name)
        try:
            _go_to_issue(unit, doc)
            images.capture(path, width=width, height=height, doc=doc, quality=cfg.get('quality', 90))
            results.append({'unit': unit, 'path': path, 'error': None})
        except Exception as error:
            if vp_common.is_cancel(error):
                return results, True
            session.log('warning', 'issue image %s failed: %s' % (unit['name'], error))
            results.append({'unit': unit, 'path': None, 'error': str(error)})
    return results, False
