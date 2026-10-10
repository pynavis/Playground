# -*- coding: utf-8 -*-
"""namo.bcf_exchange with a fake document (file name, units, transaction flag): issues out
to BCF 2.1 / 3.0 and back into an empty register (cameras converted between units,
comments and snapshots carried, no duplicates on re-import, newer topics update older
issues), and the saved-viewpoint plan, with namo.camera.save_view recorded instead of
called."""
import datetime
import os

import _compat

from namo import bcf, bcf_exchange, camera, issues, issuestore, paths, png

NOW = datetime.datetime(2026, 10, 5, 14, 30, 0)
SOURCE = r'C:\Projects\Tower\Coordination.nwf'
TARGET = r'C:\Projects\Tower\Federated.nwf'


class FakeDoc(object):
    def __init__(self, path, units='Feet'):
        self.FileName = path
        self.Units = units
        self.IsActiveTransaction = True        # pynavis.viewpoints.transaction leaves it alone


def _png(folder, name):
    path = os.path.join(folder, name)
    png.write(path, 4, 3, [10] * 36, 'RGB')
    return path


def _seed(folder):
    s = issuestore.IssueStore(SOURCE)
    cam = {'position': [100.0, 50.0, 10.0], 'rotation': None, 'direction': [0.6, 0.8, 0.0],
           'up': [0, 0, 1], 'projection': 'persp', 'height_field': 0.8, 'aspect': 1.5}
    a = s.create({'title': 'Duct hits beam', 'type': 'RFI', 'priority': 'Critical', 'trade': 'Mechanical',
                  'camera': cam, 'camera_units': 'Feet', 'due': '2026-10-20', 'labels': ['L2'],
                  'elements': [{'name': 'Duct', 'ifc_guid': '2O2Fr$t4X7Zf8NOew3FLOH',
                                'element_id': '123456'}, {'name': 'Plain', 'ifc_guid': None}]},
                 prefix='RFI-', user='amol')
    s.add_comment(a['id'], 'Please reroute', user='kim')
    s.update(a['id'], {'status': 'In progress'}, note='Started', user='kim')
    s.add_image(a['id'], _png(folder, 'snap.png'), kind='snapshot', user='amol')
    s.add_image(a['id'], _png(folder, 'extra.png'), kind='screenshot', user='amol')
    b = s.create({'title': 'No view here'}, user='amol')
    return s, [s.get(a['id']), s.get(b['id'])]


def _isolated(name):
    folder = _compat.tmpdir('g8-bcf-exchange-' + name)
    return folder, paths.redirect(folder)


def test_export_issues_both_versions():
    folder, previous = _isolated('export')
    try:
        store, rows = _seed(folder)
        doc = FakeDoc(SOURCE, 'Feet')
        for version, documents in (('2.1', 0), ('3.0', 1)):
            path = os.path.join(folder, 'out-%s.bcfzip' % version)
            report = bcf_exchange.export_issues(path, rows, version, doc)
            assert report['topics'] == 2 and report['snapshots'] == 1
            assert report['documents'] == documents and report['skipped_components'] == 1
            assert bcf.check(path)['errors'] == []
            data = bcf.read(path)
            assert data['project']['name'] == 'Coordination'
            topic = [t for t in data['topics'] if t['guid'] == rows[0]['guid']][0]
            assert topic['title'] == 'Duct hits beam' and topic['status'] == 'In Progress'
            assert topic['labels'] == ['L2', 'Mechanical']
            cam = topic['viewpoints'][0]['visinfo']['camera']
            assert _compat.approx(cam['CameraViewPoint'], (30.48, 15.24, 3.048), 1e-9)
            assert [c['comment'] for c in topic['comments']] == ['Please reroute',
                                                                 'Status: Open > In progress. Started']
            assert topic['viewpoints'][0]['snapshot_data'][:8] == png.SIGNATURE
            if version == '3.0':
                assert topic['document_references'][0]['description'].startswith('screenshot-')
                assert 'Void' in data['extensions']['statuses']
    finally:
        paths.redirect(previous)


def test_import_round_trip_merge_and_viewpoints():
    folder, previous = _isolated('import')
    saved_views = []
    original = camera.save_view

    def fake_save_view(name, folder=None, cam=None, comments=None, doc=None):
        saved_views.append((name, folder, cam))
        return name

    import contextlib
    from pynavis import viewpoints
    original_transaction = viewpoints.transaction
    transactions = []

    @contextlib.contextmanager
    def fake_transaction(name, doc=None):
        transactions.append(name)
        yield None

    camera.save_view = fake_save_view
    viewpoints.transaction = fake_transaction
    try:
        store, rows = _seed(folder)
        path = os.path.join(folder, 'Coordination 05.bcfzip')
        bcf_exchange.export_issues(path, rows, '2.1', FakeDoc(SOURCE, 'Feet'))
        data = bcf.read(path)
        target_doc = FakeDoc(TARGET, 'Meters')
        target = issuestore.for_doc(target_doc)
        preview = bcf_exchange.preview(data, target)
        assert (preview['topics'], preview['new'], preview['matching']) == (2, 2, 0)
        report = bcf_exchange.import_topics(data, 'Coordination 05.bcfzip',
                                            {'viewpoints': True, 'elements': False}, target_doc)
        assert (report['created'], report['updated'], report['kept']) == (2, 0, 0)
        assert report['snapshots'] == 1 and report['comments'] == 2
        made = target.find(rows[0]['guid'])
        assert made['id'] == 'RFI-001' and made['type'] == 'RFI' and made['trade'] == 'Mechanical'
        assert made['status'] == 'In progress' and made['priority'] == 'Critical'
        assert made['camera_units'] == 'Meters'
        assert _compat.approx(made['camera']['position'], (30.48, 15.24, 3.048), 1e-9)
        assert made['source']['kind'] == 'bcf' and made['images'][0]['kind'] == 'snapshot'
        assert made['images'][0]['bcf_viewpoint']
        assert [c['text'] for c in made['comments']][0] == 'Please reroute'
        assert saved_views and saved_views[0][0] == 'RFI-001 Duct hits beam'
        assert saved_views[0][1] == 'BCF/Coordination 05' and report['viewpoints'] == 1
        assert transactions == ['Import BCF viewpoints']                 # one undo step
        # the same file again: nothing duplicated, nothing overwritten
        again = bcf_exchange.import_topics(data, 'Coordination 05.bcfzip',
                                           {'viewpoints': False, 'elements': False}, target_doc)
        assert (again['created'], again['updated'], again['kept'], again['comments']) == (0, 0, 2, 0)
        assert again['snapshots'] == 0
        assert len(target.find(rows[0]['guid'])['comments']) == len(made['comments'])
        # a newer topic from another tool updates the issue and adds its comment
        topic = [t for t in data['topics'] if t['guid'] == rows[0]['guid']][0]
        topic['status'] = 'Closed'
        topic['modified_date'] = '2099-01-01T00:00:00Z'
        topic['comments'].append({'guid': bcf.guid(None), 'date': '2099-01-01T00:00:00Z',
                                  'author': 'solibri', 'comment': 'Verified on site'})
        newer = bcf_exchange.import_topics(data, 'Coordination 06.bcfzip',
                                           {'viewpoints': False, 'elements': False}, target_doc)
        assert newer['updated'] == 1 and newer['comments'] == 1
        closed = target.find(rows[0]['guid'])
        assert closed['status'] == 'Closed' and closed['closed']
        assert closed['comments'][-1]['text'] == 'Verified on site'
        assert any(issues.comment_text(c).startswith('Status: In progress > Closed. From BCF')
                   for c in closed['comments'])
    finally:
        camera.save_view = original
        viewpoints.transaction = original_transaction
        paths.redirect(previous)
