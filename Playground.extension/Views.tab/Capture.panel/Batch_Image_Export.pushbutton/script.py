"""Saves images of saved viewpoints, clash results and Playground issues in one run, with one index.html."""
import os

from namo import capture, dates, paths, progress, ui, vp_common
from pynavis import forms, script, toast

TITLE = 'Batch Image Export'
DEFAULTS = {'views_on': True, 'clashes_on': False, 'issues_on': False, 'views': None, 'tests': [],
            'statuses': ['New', 'Active'], 'cap': 300, 'issue_statuses': [], 'width': 1280, 'height': 720,
            'format': 'jpg', 'quality': 88, 'folder': '', 'open': True}


def ask_sources(document, cfg, have_views, have_tests, have_issues):
    fields = capture.source_fields(cfg, vp_common.default_folder(vp_common.doc_path(document)),
                                   have_views, have_tests, have_issues)
    return ui.form(TITLE, fields, ok='Next', width=500, validate=capture.source_validator(have_views, have_tests))


def ask_clashes(document, cfg):
    """[(test name, units)] or None when cancelled."""
    tests = [t for t in capture.clash_tests(document) if t[2]]
    rows = [{'value': name, 'cells': [name, count]} for _test, name, count in tests]
    remembered = [name for name in cfg.get('tests') or [] if name in [t[1] for t in tests]]
    picked = ui.choose('%s: clash tests' % TITLE, rows, ['Test', 'Groups and clashes'],
                       checked=remembered or [t[1] for t in tests], ok='Next')
    if picked is None:
        return None
    values = ui.form(TITLE, capture.clash_fields(cfg),
                     intro='One image per top-level group and per clash outside a group, from its own clash view.',
                     ok='Next')
    if values is None:
        return None
    cfg['tests'] = picked
    cfg['statuses'] = values['statuses']
    cfg['cap'] = values['cap']
    out = []
    for test, name, _count in tests:
        if name in picked:
            units = capture.clash_units(test, values['statuses'])
            if units:
                out.append((name, units))
    total = sum(len(u) for _n, u in out)
    if total > values['cap']:
        if not forms.confirm('This saves %s clash images, which can take a while. Continue?'
                             % vp_common.count_text(total), TITLE):
            return None
    return out


def ask_issues(document, cfg):
    statuses = capture.issue_statuses()
    values = ui.form(TITLE, capture.issue_fields(cfg, statuses), intro='One image per issue that has a saved view.',
                     ok='Next')
    if values is None:
        return None
    cfg['issue_statuses'] = values['issue_statuses']
    return capture.issue_units(values['issue_statuses'], document)


def run():
    document = vp_common.active_doc()
    if not vp_common.has_models(document):
        toast.info('No model open', 'Open or append a model, then run Batch Image Export again.')
        return
    cfg = script.get_config(DEFAULTS)
    rows = vp_common.view_rows(document)
    try:
        have_tests = any(t[2] for t in capture.clash_tests(document))
    except Exception:
        have_tests = False
    have_issues = capture.issues_available()
    if not rows and not have_tests and not have_issues:
        toast.info('Nothing to capture', 'This model has no saved viewpoints and no clash results.')
        return
    values = ask_sources(document, cfg, bool(rows), have_tests, have_issues)
    if values is None:
        return
    cfg = capture.image_values(cfg, values)
    for key in ('views_on', 'clashes_on', 'issues_on', 'open'):
        cfg[key] = bool(values.get(key))
    views = []
    if cfg['views_on']:
        picked = vp_common.choose_views('%s: viewpoints' % TITLE, rows, cfg.get('views'), ok='Next')
        if picked is None:
            return
        views, cfg['views'] = picked
    clashes = []
    if cfg['clashes_on']:
        clashes = ask_clashes(document, cfg)
        if clashes is None:
            return
    issues = []
    if cfg['issues_on'] and have_issues:
        issues = ask_issues(document, cfg)
        if issues is None:
            return
    script.save_config(cfg)
    if not views and not clashes and not issues:
        toast.info('Nothing matched the choices', 'No viewpoints, clashes or issues were picked.')
        return
    folder = os.path.join(cfg['folder'], '%s - Images - %s' % (vp_common.file_stem(vp_common.doc_path(document)),
                                                               dates.format(dates.now(), '%Y-%m-%d %H%M')))
    try:
        paths.ensure_dir(folder)
    except (IOError, OSError) as error:
        toast.error('Could not make the folder', '%s. Choose another folder.' % error)
        return
    outcome = progress.run(TITLE, lambda report: capture.run_batch(document, folder, cfg, views, clashes, issues,
                                                                   report), 'Capturing')
    if outcome is progress.CANCELLED:
        return
    if outcome['stopped'] and not any(s[1] for s in outcome['sections']):
        return
    level, message, detail = capture.summary(outcome['sections'], outcome['stopped'], outcome['total'])
    toast.show(level, message, '%s %s' % (detail, folder))
    if cfg['open'] and outcome.get('index'):
        try:
            ui.open_path(outcome['index'])
        except Exception:
            pass


run()
