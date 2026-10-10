# -*- coding: utf-8 -*-
"""namo.issuestore: the issue register in local, shared and model (docdb) modes, numbering
under the folder lock, last-writer-wins merging, images and session events."""
import datetime
import io
import os

import _compat
from _compat import raises

from namo import config, docdb, issues, issuestore, paths, session

DOC = r'C:\Projects\Tower\Coordination.nwf'
NOW = datetime.datetime(2026, 10, 5, 14, 30, 0)


class FakeDoc(object):
    def __init__(self, path):
        self.FileName = path


def isolated(fn):
    def wrapper():
        folder = _compat.tmpdir('g8-issuestore-' + fn.__name__)
        previous = paths.redirect(folder)
        try:
            return fn(folder)
        finally:
            paths.redirect(previous)
            for key in issuestore.listeners():
                issuestore.unsubscribe(key)
    wrapper.__name__ = fn.__name__
    return wrapper


@isolated
def test_unsaved_document_has_no_register(folder):
    s = issuestore.IssueStore('')
    assert not s.saved and s.list() == [] and s.get('X') is None
    error = raises(issuestore.NotSaved, s.create, {'title': 'x'})
    assert 'Save the model first' in str(error)
    assert isinstance(error, ValueError)
    assert issuestore.for_doc(FakeDoc('')).saved is False


@isolated
def test_create_numbers_per_prefix_and_lists_naturally(folder):
    s = issuestore.for_doc(FakeDoc(DOC))
    assert s.mode == 'local' and s.saved
    assert s.folder == os.path.join(folder, 'pyNavis', 'playground', 'docs', paths.doc_key(DOC), 'issues')
    a = s.create({'title': 'First'}, user='amol', now=NOW)
    b = s.create({'title': 'Second', 'type': 'RFI'}, prefix='rfi', user='amol', now=NOW)
    c = s.create({}, prefix='RFI-', title_pattern='{type} {n:000} at {grid}',
                 title_values={'grid': 'C-4', 'type': 'RFI'}, user='amol', now=NOW)
    assert (a['id'], b['id'], c['id']) == ('ISS-001', 'RFI-001', 'RFI-002')
    assert c['title'] == 'RFI 002 at C-4' and c['number'] == 2
    assert a['doc'] == 'Coordination.nwf' and a['rev'] == 1
    for n in range(3, 11):
        s.create({'title': 'More %d' % n}, prefix='RFI-', user='amol', now=NOW)
    ids = [i['id'] for i in s.list()]
    assert ids[:3] == ['ISS-001', 'RFI-001', 'RFI-002'] and ids[-1] == 'RFI-010'
    assert s.get('rfi-002')['title'] == 'RFI 002 at C-4'
    assert s.find(b['guid'])['id'] == 'RFI-001'
    assert s.find('nothing') is None
    raises(ValueError, s.create, {'title': ''})
    raises(ValueError, s.create, {'title': 'x', 'due': 'whenever'})


@isolated
def test_update_comment_delete_and_events(folder):
    seen = []
    issuestore.subscribe('test', lambda kind, ids, key: seen.append((kind, tuple(ids))))
    issuestore.subscribe('broken', lambda kind, ids, key: 1 / 0)
    s = issuestore.for_doc(FakeDoc(DOC))
    issue = s.create({'title': 'Duct hits beam'}, user='amol', now=NOW)
    later = datetime.datetime(2026, 10, 6, 9, 0, 0)
    updated, note = s.update(issue['id'], {'status': 'Resolved', 'assignee': 'Jane'},
                             note='Moved up', user='kim', now=later)
    assert note is None and updated['status'] == 'Resolved' and updated['rev'] == 2
    assert updated['closed'] == '2026-10-06T09:00:00'
    assert issues.comment_text(updated['comments'][-1]) == 'Status: Open > Resolved. Moved up'
    unchanged, note = s.update(issue['id'], {'assignee': 'Jane'})
    assert unchanged['rev'] == 2
    commented = s.add_comment(issue['id'], 'Checked on site', user='kim', now=later)
    assert commented['comments'][-1]['text'] == 'Checked on site' and commented['rev'] == 3
    raises(ValueError, s.update, 'ISS-999', {'title': 'x'})
    raises(ValueError, s.add_comment, issue['id'], '  ')
    assert s.delete(issue['id']) is True and s.delete(issue['id']) is False
    assert s.list() == []
    kinds = [k for k, _ids in seen]
    assert kinds == ['created', 'updated', 'updated', 'deleted']
    assert seen[0][1] == ('ISS-001',)
    assert any('issue listener broken failed' in t for _l, t in session.recent_log('error'))
    assert issuestore.version() >= 4


@isolated
def test_last_writer_wins_merges_comments(folder):
    s = issuestore.for_doc(FakeDoc(DOC))
    issue = s.create({'title': 'Shared'}, user='amol', now=NOW)
    loaded = s.get(issue['id'])                                    # both open rev 1
    s.add_comment(issue['id'], 'From Jane', user='jane', now=NOW)  # Jane saves: rev 2
    mine, changed = issues.apply_changes(loaded, {'title': 'Mine'}, 'amol', NOW)
    saved, note = s.save(mine, base_rev=loaded['rev'])
    assert note and 'jane' in note
    assert saved['title'] == 'Mine' and saved['rev'] == 3
    assert [c['text'] for c in saved['comments']] == ['From Jane']
    clean, note = s.save(saved, base_rev=saved['rev'])
    assert note is None and clean['rev'] == 4
    # Field-level: update() applies only the changed fields to the newest version.
    s.update(issue['id'], {'assignee': 'Jane'}, user='jane')
    stale_rev = 2
    newer, note = s.update(issue['id'], {'priority': 'High'}, base_rev=stale_rev, user='amol')
    assert newer['assignee'] == 'Jane' and newer['priority'] == 'High' and note


@isolated
def test_file_cache_sees_outside_edits(folder):
    s = issuestore.for_doc(FakeDoc(DOC))
    issue = s.create({'title': 'Cached'}, user='amol', now=NOW)
    assert s.list()[0]['title'] == 'Cached'
    path = os.path.join(s.folder, 'ISS-001.json')
    record = paths.load_json(path)
    record['title'] = 'Changed by a colleague, and longer'
    paths.write_json(path, record)
    assert s.list()[0]['title'] == 'Changed by a colleague, and longer'
    with io.open(os.path.join(s.folder, 'ISS-002.json'), 'w', encoding='utf-8') as handle:
        handle.write(u'{ not json')
    assert [i['id'] for i in s.list()] == ['ISS-001']                # damaged file skipped
    assert issue['id'] == 'ISS-001'


@isolated
def test_images_media_folder_and_replace(folder):
    s = issuestore.for_doc(FakeDoc(DOC))
    issue = s.create({'title': 'With pictures'}, user='amol', now=NOW)
    src = os.path.join(folder, 'shot.jpg')
    with io.open(src, 'wb') as handle:
        handle.write(b'\xff\xd8\xff' + b'0' * 32)
    issue = s.add_image(issue['id'], src, kind='snapshot', user='amol', now=NOW)
    assert issue['images'][0]['file'] == 'snapshot-20261005-143000.jpg'
    media = s.media_folder(issue)
    assert media == os.path.join(s.folder, '_media', issue['guid'])
    assert os.path.exists(os.path.join(media, issue['images'][0]['file']))
    issue = s.add_image(issue['id'], src, kind='screenshot', user='amol', now=NOW)
    issue = s.add_image(issue['id'], src, kind='snapshot', replace_kind=True, move=True,
                        user='amol', now=NOW)
    files = [i['file'] for i in issue['images']]
    assert files == ['snapshot-20261005-143000-2.jpg', 'screenshot-20261005-143000.jpg']
    assert not os.path.exists(src)                                  # moved
    assert not os.path.exists(os.path.join(media, 'snapshot-20261005-143000.jpg'))
    assert s.snapshot_path(issue).endswith('snapshot-20261005-143000-2.jpg')
    assert len(s.images_on_disk(issue)) == 2
    issue = s.remove_image(issue['id'], 'screenshot-20261005-143000.jpg')
    assert [i['file'] for i in issue['images']] == ['snapshot-20261005-143000-2.jpg']
    raises(IOError, s.add_image, issue['id'], os.path.join(folder, 'missing.jpg'))
    assert s.delete(issue['id']) and not os.path.isdir(media)


@isolated
def test_shared_mode_keys_by_file_name(folder):
    share = os.path.join(folder, 'share')
    os.makedirs(share)
    config.save({'data_mode': 'shared', 'shared_root': share})
    paths.forget_reachability()
    s = issuestore.for_doc(FakeDoc(DOC))
    assert s.mode == 'shared' and s.note is None
    s.create({'title': 'Team issue'}, user='amol', now=NOW)
    other = issuestore.for_doc(FakeDoc(r'X:\Mapped\COORDINATION.nwf'))
    assert [i['title'] for i in other.list()] == ['Team issue']
    assert s.folder.startswith(share)


@isolated
def test_image_name_is_unique(folder):
    now = datetime.datetime(2026, 1, 2, 3, 4, 5)
    assert issuestore.image_name('snapshot', 'jpg', [], now) == 'snapshot-20260102-030405.jpg'
    taken = ['SNAPSHOT-20260102-030405.jpg', 'snapshot-20260102-030405-2.jpg']
    assert issuestore.image_name('snapshot', '.jpg', taken, now) == 'snapshot-20260102-030405-3.jpg'


def test_model_mode_records_and_local_media():
    try:
        backend = docdb.SqliteBackend()
    except ImportError:
        raise _compat.SkipTest('sqlite3 not available on this engine')
    previous = docdb.use_backend(backend)
    folder = _compat.tmpdir('g8-issuestore-model')
    previous_root = paths.redirect(folder)
    try:
        s = issuestore.IssueStore(DOC, mode='model')
        assert s.mode == 'model' and s.folder is None
        a = s.create({'title': 'In the model'}, user='amol', now=NOW)
        b = s.create({'title': 'Second'}, prefix='HOLD-', user='amol', now=NOW)
        assert (a['id'], b['id']) == ('ISS-001', 'HOLD-001')
        assert [r['id'] for r in docdb.records('issues')] == ['HOLD-001', 'ISS-001']
        assert s.get('iss-001')['title'] == 'In the model'          # case-insensitive lookup
        s.update('ISS-001', {'status': 'Closed'}, user='kim')
        assert s.get('ISS-001')['status'] == 'Closed'
        assert s.media_folder(a) == os.path.join(folder, 'pyNavis', 'playground', 'issue-media', a['guid'])
        assert s.describe().startswith('In the model')
        assert s.delete('HOLD-001') and [i['id'] for i in s.list()] == ['ISS-001']
    finally:
        paths.redirect(previous_root)
        docdb.use_backend(previous)
        backend.close()


@isolated
def test_template_fields_and_sources(folder):
    fields, prefix, pattern = issuestore.template_fields(
        {'type': 'Hold', 'prefix': 'HOLD', 'priority': 'high', 'due_days': 3, 'labels': 'Hold, Site'},
        now=NOW)
    assert prefix == 'HOLD-' and pattern == '{type} {n:000}'
    assert fields['priority'] == 'High' and fields['due'] == '2026-10-08'
    assert fields['labels'] == ['Hold', 'Site']
    s = issuestore.for_doc(FakeDoc(DOC))
    s.create({'title': 'From a clash', 'source': {'kind': 'clash', 'ref': 'T|R'}}, user='a', now=NOW)
    s.create({'title': 'Manual'}, user='a', now=NOW)
    assert s.sources('clash') == {'T|R': 'ISS-001'}
    assert issuestore.capture_title_values({'location': {'level': 'L2', 'grid': 'C-4'},
                                            'elements': [{'name': 'Duct', 'model': 'M.nwc'}]}) == \
        {'level': 'L2', 'grid': 'C-4', 'element': 'Duct', 'model': 'M.nwc'}


@isolated
def test_public_facade(folder):
    from namo import issues
    doc = FakeDoc(DOC)
    assert issues.list(doc) == [] and issues.get('RFI-001', doc) is None
    made = issues.create({'title': ''}, doc=doc, template='RFI')
    assert made['id'] == 'RFI-001' and made['title'] == 'RFI 001' and made['type'] == 'RFI'
    assert made['due'] and made['labels'] == ['RFI']
    custom = issues.create({'title': 'Hold the slab pour', 'priority': 'Critical'}, doc=doc,
                           template={'type': 'Hold', 'prefix': 'HOLD', 'priority': 'High',
                                     'due_days': None})
    assert custom['id'] == 'HOLD-001' and custom['priority'] == 'Critical' and custom['due'] == ''
    raises(ValueError, issues.create, {'title': 'x'}, doc, 'No such template')
    updated = issues.update('rfi-001', {'status': 'Resolved'}, doc=doc, note='Answered')
    assert updated['status'] == 'Resolved'
    commented = issues.add_comment(made['id'], 'Thanks', doc=doc)
    assert commented['comments'][-1]['text'] == 'Thanks'
    assert [i['id'] for i in issues.filter(issues.list(doc), status='open')] == ['HOLD-001']
    assert issues.get(made['guid'], doc)['id'] == 'RFI-001'
    assert issues.image_paths(made, doc) == []
    assert issues.list(FakeDoc('')) == []
    raises(issuestore.NotSaved, issues.create, {'title': 'x'}, FakeDoc(''))


@isolated
def test_media_folder_stays_under_the_media_root_whatever_the_guid(folder):
    # A hand-edited shared register must not steer a delete outside _media.
    s = issuestore.for_doc(FakeDoc(DOC))
    root = os.path.normcase(os.path.abspath(s.media_root()))
    for guid in ('..', '../..', '..' + os.sep + 'x', 'a/b', 'C:' + os.sep + 'Windows', '.', ' '):
        media = os.path.normcase(os.path.abspath(s.media_folder({'guid': guid})))
        assert os.path.dirname(media) == root, (guid, media)
    good = issues.new_guid()
    assert s.media_folder({'guid': good}) == os.path.join(s.media_root(), good)
