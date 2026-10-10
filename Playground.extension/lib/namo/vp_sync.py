# -*- coding: utf-8 -*-
"""Viewpoint Sync: copy saved-viewpoint folders between Navisworks files through a
package (namo.vpexport records in a .nvp.json file; a Navisworks viewpoint .xml is
read too).

Import plans first (pure, tested): which records, where they land (the target
folder in front of each record's own folder path), and what happens to a name that
is already there (skip / replace in place / keep both as 'Name (2)'). The API half
then builds each viewpoint detached from a copy of the current view (so it keeps
the user's lighting and render style unless the record says otherwise), converts
lengths when the package was made in other units, and files everything in ONE
transaction.
"""
import os

POLICIES = [('Skip it', 'skip'), ('Replace it', 'replace'), ('Keep both', 'keep')]     # (label, value)
OUTCOME_TEXT = {'created': 'Created', 'replaced': 'Replaced', 'skipped': 'Skipped (name taken)',
                'failed': 'Failed'}


# ---- pure ---------------------------------------------------------------------------


def target_folder(target, folder, keep_paths=True):
    """Where a record from `folder` lands under `target` ('' = top level).
    keep_paths False flattens every record straight into target."""
    parts = [p.strip() for p in str(target or '').replace('\\', '/').split('/') if p.strip()]
    if keep_paths:
        parts += [p for p in str(folder or '').split('/') if p]
    return '/'.join(parts)


def chosen(records, folders):
    """Records whose folder is one of `folders` (exact paths; '' = top level)."""
    wanted = set(folders)
    return [r for r in records if (r.get('folder') or '') in wanted]


def plan(records, target, policy, exists, keep_paths=True):
    """[{'record', 'folder', 'name', 'action'}] with action 'create', 'replace',
    'skip' or 'keep' (keep both: the name gets ' (2)'). exists(folder, name) says
    whether the document already holds that name in that folder. Names repeated
    inside the package itself count as taken once the first one is planned."""
    planned = set()
    out = []
    for record in records:
        folder = target_folder(target, record.get('folder'), keep_paths)
        name = str(record['name'])
        key = (folder, name.lower())
        taken = exists(folder, name) or key in planned
        if not taken:
            action = 'create'
        elif policy == 'replace' and key not in planned:
            action = 'replace'
        elif policy == 'skip':
            action = 'skip'
        else:
            action = 'keep'
        planned.add(key)
        out.append({'record': record, 'folder': folder, 'name': name, 'action': action})
    return out


def plan_counts(steps):
    counts = {'create': 0, 'replace': 0, 'skip': 0, 'keep': 0}
    for step in steps:
        counts[step['action']] += 1
    return counts


def plan_sentence(steps):
    """'Create 12, replace 3, skip 1.' for the confirm prompt."""
    from namo import vp_common
    c = plan_counts(steps)
    parts = []
    if c['create'] + c['keep']:
        parts.append('create %s' % vp_common.plural(c['create'] + c['keep'], 'viewpoint'))
    if c['replace']:
        parts.append('replace %s' % vp_common.count_text(c['replace']))
    if c['skip']:
        parts.append('skip %s' % vp_common.count_text(c['skip']))
    text = ', '.join(parts) or 'nothing to do'
    return text[0].upper() + text[1:] + '.'


def report_rows(results):
    """Table rows [folder, name, outcome] for the output window."""
    from namo import vp_common
    return [[vp_common.folder_label(r['folder']), r['name'], OUTCOME_TEXT.get(r['outcome'], r['outcome'])
             + ((': ' + r['error']) if r.get('error') else '')] for r in results]


def import_fields(cfg):
    """The ui.form fields of the import step (cfg: the tool's settings with 'target',
    'keep_paths', 'policy', 'clip', 'comments')."""
    return [
        {'kind': 'text', 'key': 'target', 'label': 'Put them in folder', 'default': cfg['target'],
         'hint': 'Empty: the top level. Use / for subfolders.'},
        {'kind': 'check', 'key': 'keep_paths', 'label': 'Keep the package folders under it',
         'default': cfg['keep_paths']},
        {'kind': 'radio', 'key': 'policy', 'label': 'When a viewpoint with that name exists',
         'options': POLICIES, 'default': cfg['policy'], 'fallback': None, 'inline': True},
        {'kind': 'check', 'key': 'clip', 'label': 'Bring the section planes', 'default': cfg['clip']},
        {'kind': 'check', 'key': 'comments', 'label': 'Bring the comments', 'default': cfg['comments']},
    ]


def default_package_name(doc_path, date_text):
    from namo import vp_common
    return '%s - Viewpoints - %s.nvp.json' % (vp_common.file_stem(doc_path), date_text)


# ==== API half ======================================================================


def existing_lookup(document):
    """exists(folder, name) over the current tree (one walk, cached)."""
    from namo import vp_common
    names = set()
    for row in vp_common.view_rows(document, include_animations=True):
        names.add((row['folder'], row['name'].lower()))
    return lambda folder, name: (folder, str(name).lower()) in names


def _restore_extras(viewpoint, cam):
    from pynavis._api import Api
    for key, attr in (('linear', 'LinearSpeed'), ('angular', 'AngularSpeed')):
        if cam.get(key):
            try:
                setattr(viewpoint, attr, float(cam[key]))
            except Exception:
                pass
    if cam.get('render'):
        value = getattr(Api.ViewpointRenderStyle, str(cam['render']), None)
        if value is not None:
            try:
                viewpoint.RenderStyle = value
            except Exception:
                pass
    if cam.get('lighting'):
        value = getattr(Api.ViewpointLighting, str(cam['lighting']), None)
        if value is not None:
            try:
                viewpoint.Lighting = value
            except Exception:
                pass


def build_viewpoint(base, record, same_units, include_clip=True):
    """A detached Viewpoint for a record (already in document units)."""
    from namo import camera, vp_common
    viewpoint = base.CreateCopy()
    if include_clip and record.get('clip'):
        vp_common.apply_clip_state(viewpoint, record['clip'])
    else:
        viewpoint.ClipPlanes.Enabled = False
    cam = record['camera']
    built = None
    if same_units and cam.get('json'):
        try:
            trial = viewpoint.CreateCopy()
            if trial.TrySetCamera(str(cam['json'])):
                built = trial
        except Exception:
            built = None
    if built is None:
        built = camera.to_viewpoint(cam, base=viewpoint)
    _restore_extras(built, cam)
    return built


def apply(document, steps, units_from, include_clip=True, include_comments=True, report=None):
    """Files the planned steps in ONE transaction. Returns (results, stopped):
    results [{'folder', 'name', 'outcome', 'error'}]."""
    from pynavis.viewpoints import transaction
    from namo import session, vp_common, vpexport
    doc_units = str(document.Units)
    k = vp_common.unit_factor(units_from or doc_units, doc_units)
    same = abs(k - 1.0) < 1e-12
    policy_of = {'create': 'keep', 'keep': 'keep', 'replace': 'replace', 'skip': 'skip'}
    results = []
    stopped = False
    with transaction('Import viewpoints', document):
        base = document.CurrentViewpoint.CreateCopy()
        for index, step in enumerate(steps):
            if vp_common.report_step(report, float(index) / max(1, len(steps)),
                                     'Importing %s (%d of %d)' % (step['name'], index + 1, len(steps))):
                stopped = True
                break
            entry = {'folder': step['folder'], 'name': step['name'], 'outcome': 'skipped', 'error': ''}
            if step['action'] == 'skip':
                results.append(entry)
                continue
            try:
                record = vpexport.scale_record(step['record'], k)
                viewpoint = build_viewpoint(base, record, same, include_clip)
                comments = record.get('comments') if include_comments else None
                _live, outcome = vp_common.add_view(document, step['folder'], step['name'], viewpoint=viewpoint,
                                                    comments=comments, policy=policy_of[step['action']])
                entry['outcome'] = outcome
            except Exception as error:
                if vp_common.is_cancel(error):
                    stopped = True
                    break
                session.log('warning', 'Viewpoint Sync: %s failed: %s' % (step['name'], error))
                entry['outcome'] = 'failed'
                entry['error'] = str(error)
            results.append(entry)
    return results, stopped


def summary(results, stopped, total):
    from namo import vp_common
    made = len([r for r in results if r['outcome'] in ('created', 'replaced')])
    replaced = len([r for r in results if r['outcome'] == 'replaced'])
    skipped = len([r for r in results if r['outcome'] == 'skipped'])
    failed = [r for r in results if r['outcome'] == 'failed']
    extra = []
    if replaced:
        extra.append('%s replaced' % vp_common.count_text(replaced))
    if skipped:
        extra.append('%s skipped' % vp_common.count_text(skipped))
    noted = (' (%s)' % ', '.join(extra)) if extra else ''
    if stopped:
        return ('warning', 'Stopped after %s of %s' % (vp_common.count_text(made), vp_common.plural(total, 'viewpoint')),
                'Ctrl+Z removes the imported ones.')
    if failed and not made:
        return ('error', 'Could not import the viewpoints', '%s: %s' % (failed[0]['name'], failed[0]['error']))
    if failed:
        return ('warning', 'Imported %s, %s failed%s' % (vp_common.plural(made, 'viewpoint'),
                                                         vp_common.count_text(len(failed)), noted),
                '%s: %s' % (failed[0]['name'], failed[0]['error']))
    if not made:
        return ('info', 'No viewpoints imported', 'Every name was already there and Skip was chosen.')
    return ('success', 'Imported %s%s' % (vp_common.plural(made, 'viewpoint'), noted), 'One Ctrl+Z removes them all.')


def package_path_default(document):
    from namo import dates, vp_common
    path = vp_common.doc_path(document)
    return os.path.join(vp_common.default_folder(path),
                        default_package_name(path, dates.format(dates.now(), '%Y-%m-%d')))
