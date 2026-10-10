# -*- coding: utf-8 -*-
"""BCF Export and BCF Import: issues (or clash results) to a .bcfzip and back.

    report = bcf_exchange.export_issues(path, rows, '2.1')
    report = bcf_exchange.export_clashes(path, ['Ducts vs Beams'], ['New', 'Active'], '3.0')
    data = bcf.read(path)                                  # preview first
    preview = bcf_exchange.preview(data)                   # new / matching counts
    report = bcf_exchange.import_topics(data, 'Coordination 05.bcfzip', options)

Export: one topic per issue (Topic Guid = issue guid, so a round trip through another
tool merges back onto the same issue). Cameras go out in METRES from the issue's own
camera units; components carry the IFC GlobalId (the model's IfcGUID property, else
derived from the Revit UniqueId) with the Revit Element ID as AuthoringToolId; the
issue snapshot is the topic snapshot (converted to PNG for BCF 2.1); in 3.0 the other
images travel as attached documents. extensions.xml (3.0) declares every Playground status,
priority and template type so other tools offer the same choices.

Import: topics merge by Topic Guid (namo.issues.from_topic decides create / update /
keep by modified date; comments merge by guid, never duplicated); each topic's first
viewpoint becomes the issue camera (metres to document units) and every viewpoint a
saved viewpoint under 'BCF/<file name>' (ONE undo step for all of them, written after
the issue records because the document database must not be written inside a
viewpoint transaction); components are found by IFC GlobalId, then Element ID
(namo.issueapi.component_finder, with progress, cancel and a time budget).
Clipping planes and coloring are read but not applied to the model (noted in the
report).

API half throughout (lazy imports); the decisions it relies on are pure and tested in
namo.issues, namo.bcf and namo.issue_clash.
"""

import os

ELEMENT_BUDGET_S = 180.0
VIEWPOINT_FOLDER = 'BCF'


def _doc(doc):
    if doc is not None:
        return doc
    from pynavis._api import Application
    return Application.ActiveDocument


def project_of(doc=None):
    """{'id', 'name'} for project.bcfp: the Playground project name, else the model's."""
    from namo import bcf, config, issuestore
    document = _doc(doc)
    path = issuestore.doc_path_of(document)
    stem = os.path.splitext(os.path.basename(path))[0] if path else 'Navisworks model'
    name = config.get('project_name') or stem
    return {'id': bcf.project_guid(name), 'name': name}


def vocabulary():
    """extensions.xml lists for BCF 3.0 exports."""
    from namo import issue_templates, issues
    return {'types': [t['type'] for t in issue_templates.load()] + [issues.DEFAULT_TYPE, 'Clash'],
            'statuses': [issues.bcf_status(s) for s in issues.STATUSES],
            'priorities': list(issues.PRIORITIES)}


def _read_bytes(path):
    with open(path, 'rb') as handle:
        return handle.read()


def snapshot_bytes(path, version):
    """The image bytes for a topic snapshot: PNG for BCF 2.1 (converted through
    System.Drawing when the file is a JPEG), as stored for 3.0. None when unreadable."""
    from namo import bcf, images, issueapi
    if not path or not os.path.exists(path):
        return None
    data = _read_bytes(path)
    kind = bcf._sniff(data)
    if kind == 'png' or (version == '3.0' and kind == 'jpeg'):
        return data
    try:
        target = issueapi.temp_path('.png', 'bcf')
        images.thumbnail(path, target, max_width=1500, max_height=1500)
        converted = _read_bytes(target)
        try:
            os.remove(target)
        except OSError:
            pass
        return converted
    except Exception:
        return data if kind else None


def _metres_per(units_name, doc):
    from namo import issueapi
    return issueapi.unit_to_m(doc, units_name or issueapi.doc_units(doc))


def export_issues(path, rows, version='2.1', doc=None, snapshots=True, progress=None):
    """Writes the issues to path. Returns bcf.write's report plus 'skipped_components'
    (elements without an IFC GUID). progress(fraction, label): False cancels."""
    from namo import bcf, issues, issuestore, items
    document = _doc(doc)
    store = issuestore.for_doc(document)
    topics = []
    documents = []
    skipped = 0
    total = len(rows) or 1
    for index, issue in enumerate(rows):
        if progress is not None and progress(float(index) / total, 'Topic %d of %d'
                                             % (index + 1, len(rows))) == False:  # noqa: E712
            raise items.Cancelled()
        k = _metres_per(issue.get('camera_units'), document)
        snap_path = store.snapshot_path(issue) if snapshots else None
        topic = issues.to_topic(issue, unit_to_m=k, snapshot_name='snapshot' if snap_path else None)
        _components, missing = issues.components_of(issue)
        skipped += missing
        if snap_path and topic['viewpoints']:
            topic['viewpoints'][0]['snapshot_data'] = snapshot_bytes(snap_path, version)
        if version == '3.0' and snapshots:
            for image, image_path in store.images_on_disk(issue):
                if image_path == snap_path:
                    continue
                guid = bcf.guid(None)
                documents.append({'guid': guid, 'filename': image['file'],
                                  'description': image.get('caption') or image.get('kind') or '',
                                  'data': _read_bytes(image_path)})
                topic['document_references'].append({'guid': bcf.guid(None), 'document_guid': guid,
                                                     'description': image['file']})
        topics.append(topic)
    if progress is not None:
        progress(1.0, 'Writing %s' % os.path.basename(path))
    report = bcf.write(path, topics, version, project_of(document), documents,
                       extensions=vocabulary())
    report['skipped_components'] = skipped
    return report


def export_clashes(path, test_names, statuses, version='2.1', doc=None, snapshots=True,
                   progress=None):
    """One topic per top-level clash unit (group or ungrouped clash) of the named tests
    with one of the statuses. Returns bcf.write's report plus 'units'."""
    from namo import bcf, camera, config, issue_clash, issueapi, issues, items
    document = _doc(doc)
    k = issueapi.unit_to_m(document)
    units_name = issueapi.doc_units(document)
    user = config.user_name()
    trade_names = config.get('trades') or []
    rules = {'who_moves': issue_clash.who_moves()}       # Clash Assigner's order
    topics = []
    from namo import clashdata
    tests = [t for t in (clashdata.test_by_name(n, document) for n in test_names) if t is not None]
    span = 1.0 / (len(tests) or 1)
    for index, test in enumerate(tests):
        name, test_guid = test.DisplayName, str(test.Guid)
        base = index * span

        def read_progress(fraction, label, base=base):
            return True if progress is None else progress(base + span * 0.3 * fraction,
                                                          'Reading %s' % name)
        units, objects = issue_clash.read_units(test, document, read_progress)
        chosen = [u for u in units if issue_clash.wanted(u, statuses)]
        for number, unit in enumerate(chosen):
            if progress is not None and progress(
                    base + span * (0.3 + 0.7 * float(number) / (len(chosen) or 1)),
                    '%s: topic %d of %d' % (name, number + 1, len(chosen))) == False:  # noqa: E712
                raise items.Cancelled()
            topic = issue_clash.topic_for_unit(unit, name, test_guid, rules, trade_names, user,
                                               units_name)
            obj = objects.get(unit['guid'])
            visinfo = {'guid': bcf.guid(None), 'camera': None, 'selection': [],
                       'visibility': {'default': True, 'exceptions': []}}
            data = None
            if obj is not None:
                cam = issue_clash.unit_camera(obj, document)
                if cam is not None:
                    visinfo['camera'] = camera.to_bcf(cam, k)
                records, _objs, _total = issueapi.elements_of(issue_clash.unit_items(obj), document,
                                                              issue_clash.GROUP_ELEMENT_LIMIT)
                visinfo['selection'], _missing = issues.components_of({'elements': records})
                if snapshots:
                    try:
                        shot = issue_clash.unit_image(obj, issueapi.temp_path('.png', 'clash'),
                                                      document)
                        data = _read_bytes(shot)
                        os.remove(shot)
                    except Exception:
                        data = None
            topic['viewpoints'] = [{'guid': visinfo['guid'], 'visinfo': visinfo,
                                    'snapshot_data': data}]
            topics.append(topic)
    if not topics:
        return {'topics': 0, 'viewpoints': 0, 'snapshots': 0, 'documents': 0, 'notes': [],
                'units': 0, 'path': None}
    if progress is not None:
        progress(1.0, 'Writing %s' % os.path.basename(path))
    report = bcf.write(path, topics, version, project_of(document), extensions=vocabulary())
    report['units'] = len(topics)
    return report


# ---- import ----------------------------------------------------------------------------------


def preview(data, store=None):
    """{'topics', 'new', 'matching', 'version', 'viewpoints', 'components'} for a read BCF
    (bcf.read's dict) against the active register."""
    from namo import issuestore
    store = store or issuestore.for_doc()
    known = store.by_guid()
    out = {'topics': len(data['topics']), 'new': 0, 'matching': 0, 'version': data['version'],
           'viewpoints': 0, 'components': 0}
    for topic in data['topics']:
        if topic['guid'] in known:
            out['matching'] += 1
        else:
            out['new'] += 1
        for vp in topic['viewpoints']:
            if vp.get('visinfo'):
                out['viewpoints'] += 1
                out['components'] += len(vp['visinfo'].get('selection') or [])
    return out


def _prefix_for(type_name):
    from namo import issue_templates, issues
    template = issue_templates.find(issue_templates.load(), type_name)
    return template['prefix'] if template else issues.DEFAULT_PREFIX


def _write_snapshot(data):
    from namo import bcf, issueapi
    kind = bcf._sniff(data)
    if not kind:
        return None
    path = issueapi.temp_path('.png' if kind == 'png' else '.jpg', 'bcf')
    with open(path, 'wb') as handle:
        handle.write(data)
    return path


def import_topics(data, file_name, options=None, doc=None, progress=None):
    """Merges a read BCF (bcf.read's dict) into the register. options: {'viewpoints':
    True (saved viewpoints under BCF/<file name>), 'elements': True (find components)}.
    Returns {'created', 'updated', 'kept', 'comments', 'viewpoints', 'found', 'missing',
    'not_searched', 'snapshots', 'ids', 'notes'}. progress False cancels (what was
    imported so far stays; issues are written as they go)."""
    from namo import camera, config, issueapi, issues, issuestore, items
    from pynavis.viewpoints import transaction
    options = dict({'viewpoints': True, 'elements': True}, **(options or {}))
    document = _doc(doc)
    store = issuestore.for_doc(document)
    store.require_saved()
    user = config.user_name()
    trades = config.get('trades') or []
    units_name = issueapi.doc_units(document)
    m_to_unit = 1.0 / (issueapi.unit_to_m(document, units_name) or 1.0)
    known = store.by_guid()
    report = {'created': 0, 'updated': 0, 'kept': 0, 'comments': 0, 'viewpoints': 0,
              'found': 0, 'missing': 0, 'not_searched': 0, 'snapshots': 0, 'ids': [],
              'notes': list(data.get('notes') or [])}
    finder = None
    if options['elements']:
        def probe_progress(fraction, label):
            return True if progress is None else progress(0.05 * fraction, label)
        finder = issueapi.component_finder(document, probe_progress)
        if not finder.searchable:
            report['notes'].append('This model has no IFC GUID or Element ID properties, so BCF '
                                   'components could not be looked up.')
    budget_left = [ELEMENT_BUDGET_S]
    planted = []                                  # (issue id, title, [(name, cam, note)])
    total = len(data['topics']) or 1
    import time as _time
    try:
        for index, topic in enumerate(data['topics']):
            if progress is not None and progress(0.9 * index / total, 'Topic %d of %d'
                                                 % (index + 1, len(data['topics']))) == False:  # noqa: E712
                raise items.Cancelled()
            existing = known.get(topic['guid'])
            plan = issues.from_topic(topic, existing, trades, user)
            cam = None
            if plan['camera'] and plan['camera'].get('CameraViewPoint'):
                try:
                    cam = camera.from_bcf(plan['camera'], m_to_unit)
                except Exception:
                    cam = None
            elements = None
            if finder is not None and finder.searchable and plan['components']:
                started = _time.time()
                found, missing, skipped = issueapi.resolve_components(
                    plan['components'], document, None, max(0.0, budget_left[0]), finder)
                budget_left[0] -= _time.time() - started
                report['found'] += len(found)
                report['missing'] += missing
                report['not_searched'] += skipped
                if found:
                    elements, _objs, _total = issueapi.elements_of(found, document)
            source = {'kind': 'bcf', 'ref': file_name, 'topic': topic['guid']}
            if plan['action'] == 'create':
                fields = dict(plan['fields'])
                fields['guid'] = topic['guid']
                fields['modified'] = plan['modified'] or fields.get('created')
                fields['modified_by'] = topic.get('modified_author') or fields.get('created_by')
                fields['comments'] = plan['new_comments']
                fields['source'] = source
                if cam is not None:
                    fields['camera'] = cam
                    fields['camera_units'] = units_name
                if elements:
                    fields['elements'] = elements
                issue = store.create(fields, prefix=_prefix_for(fields.get('type')), user=user,
                                     notify_now=False)
                report['created'] += 1
                report['comments'] += len(plan['new_comments'])
            else:
                current = store.get(existing['id'])
                if current is None:
                    continue
                if plan['action'] == 'update':
                    changes = dict((k, v) for k, v in plan['fields'].items() if k in issues.EDITABLE)
                    if cam is not None:
                        changes['camera'] = cam
                        changes['camera_units'] = units_name
                    if elements:
                        changes['elements'] = elements
                    status_moves = changes.get('status') not in (None, current['status'])
                    current, changed = issues.apply_changes(
                        current, changes, user,
                        note=('From BCF %s' % file_name) if status_moves else None)
                    if changed:
                        report['updated'] += 1
                    else:
                        report['kept'] += 1
                else:
                    report['kept'] += 1
                if plan['new_comments']:
                    current['comments'] = current['comments'] + plan['new_comments']
                    current['comments'].sort(key=lambda c: (c.get('date') or '', c.get('guid')))
                    report['comments'] += len(plan['new_comments'])
                issue, _note = store.save(current, base_rev=current['rev'], notify_now=False)
            report['ids'].append(issue['id'])
            have = set(i.get('bcf_viewpoint') for i in issue.get('images') or [])
            for vp in topic['viewpoints']:
                if not vp.get('snapshot_data') or vp.get('guid') in have:
                    continue
                path = _write_snapshot(vp['snapshot_data'])
                if path is None:
                    continue
                has_snapshot = any(i.get('kind') == 'snapshot' for i in issue.get('images') or [])
                issue = store.add_image(issue['id'], path, kind='bcf' if has_snapshot else 'snapshot',
                                        caption='BCF %s' % file_name, move=True, notify_now=False,
                                        extra={'bcf_viewpoint': vp.get('guid')})
                report['snapshots'] += 1
            if options['viewpoints']:
                views = []
                for number, vp in enumerate(topic['viewpoints']):
                    visinfo = vp.get('visinfo') or {}
                    if not visinfo.get('camera'):
                        continue
                    try:
                        vp_cam = camera.from_bcf(visinfo['camera'], m_to_unit)
                    except Exception:
                        continue
                    views.append(vp_cam)
                    if visinfo.get('clipping_planes') and 'clipping' not in report:
                        report['clipping'] = True
                if views:
                    planted.append((issue['id'], issue['title'], views,
                                    (topic.get('description') or '')[:500]))
    finally:
        if report['ids']:
            issuestore.notify('imported', report['ids'], store.key)
    if planted:
        if progress is not None:
            progress(0.95, 'Saving viewpoints')
        stem = os.path.splitext(os.path.basename(file_name))[0] or 'Import'
        folder = '%s/%s' % (VIEWPOINT_FOLDER, stem.replace('/', ' '))
        with transaction('Import BCF viewpoints', document):
            for issue_id, title, views, note in planted:
                for number, vp_cam in enumerate(views):
                    name = '%s %s' % (issue_id, title) if number == 0 else \
                        '%s %s (%d)' % (issue_id, title, number + 1)
                    camera.save_view(name[:120], folder=folder, cam=vp_cam,
                                     comments=[note] if note else None, doc=document)
                    report['viewpoints'] += 1
        report['folder'] = folder
    if report.pop('clipping', False):
        report['notes'].append('Section planes in the BCF viewpoints were not applied.')
    return report


def summary_line(report):
    """'12 topics: 8 new, 3 updated, 1 unchanged' for a toast."""
    parts = []
    if report['created']:
        parts.append('%d new' % report['created'])
    if report['updated']:
        parts.append('%d updated' % report['updated'])
    if report['kept']:
        parts.append('%d kept (newer here)' % report['kept'])
    total = report['created'] + report['updated'] + report['kept']
    return '%d topic%s: %s' % (total, '' if total == 1 else 's', ', '.join(parts) or 'nothing new')


def detail_line(report):
    """Viewpoints, elements and notes in one sentence for the toast detail."""
    parts = []
    if report.get('viewpoints'):
        parts.append('%d viewpoint%s under %s' % (report['viewpoints'],
                                                  '' if report['viewpoints'] == 1 else 's',
                                                  report.get('folder', VIEWPOINT_FOLDER)))
    if report.get('found') or report.get('missing'):
        parts.append('%d element%s found, %d not found' % (report['found'],
                                                           '' if report['found'] == 1 else 's',
                                                           report['missing']))
    if report.get('not_searched'):
        parts.append('%d not searched (time limit)' % report['not_searched'])
    text = '; '.join(parts)
    if report.get('notes'):
        text = (text + '. ' if text else '') + report['notes'][0]
    return text
