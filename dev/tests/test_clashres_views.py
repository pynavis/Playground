# -*- coding: utf-8 -*-
"""namo.clashres_views: folder templates, candidates by mode and status, plans with
unique names, comments, and create() through the fakes (folders, skip, replace)."""
import _compat
import test_clashset_tests as cf

from namo import clashassign as ca
from namo import clashname as cn
from namo import clashres_views as cv
from namo import paths


def _row(i, name, status='New', group=None, grid='C-4', distance=-0.02):
    return {'id': i, 'name': name, 'status': status, 'group': group, 'grid': grid, 'level': 'L2',
            'distance': distance, 'model_a': 'MEP.nwc', 'model_b': 'STR.nwc', 'trade_a': 'Mechanical',
            'trade_b': 'Structure', 'item_a_name': 'Duct', 'item_b_name': 'Beam', 'assigned': ''}


def _units():
    return [{'kind': 'clash', 'name': 'Clash1', 'test': 'T', 'guid': 'c1', 'rows': [_row(0, 'Clash1')]},
            {'kind': 'group', 'name': 'Level 2/East', 'test': 'T', 'guid': 'g1',
             'rows': [_row(1, 'Clash2', 'Active', 'Level 2/East'),
                      _row(2, 'Clash3', 'Resolved', 'Level 2/East', distance=-0.05)]},
            {'kind': 'clash', 'name': 'Clash4', 'test': 'T', 'guid': 'c4',
             'rows': [_row(3, 'Clash4', 'Approved')]}]


def test_render_folder_keeps_values_slash_free():
    assert cv.render_folder('Clashes/{test}/{group}', {'test': 'A/B', 'group': ''}) == 'Clashes/A-B'
    assert cv.render_folder('Clashes/{test}/{group}', {'test': 'T', 'group': 'G 1'}) == 'Clashes/T/G 1'
    assert cv.render_folder('', {}) == ''
    assert cv.split_folder(' A // B ') == ['A', 'B']


def test_candidates_by_mode_and_status():
    units = _units()
    groups = cv.candidates(units, 'group', ['New', 'Active'])
    assert [(u['kind'], u['name'], u['ref']) for u in groups] == [
        ('clash', 'Clash1', ('clash', 0)), ('group', 'Level 2/East', ('group', 'g1'))]
    clashes = cv.candidates(units, 'clash', ['Active', 'Approved'])
    assert [(u['name'], u['ref']) for u in clashes] == [('Clash2', ('clash', 1)), ('Clash4', ('clash', 3))]
    assert cv.candidates(units, 'group', []) == []


def test_plan_names_folders_and_existing():
    existing = {'clashes/t': set(['clash1'])}
    planned = cv.plan([(0, 'T', _units()), (1, 'T', _units())], 'clash', ['New', 'Active', 'Resolved'],
                      cv.DEFAULT_FOLDER, '{name} {status}', 'Meters',
                      existing=lambda folder: existing.get(folder.lower(), set()))
    folders = [(p['test'], p['folder'], p['name'], p['exists']) for p in planned]
    assert folders[:3] == [(0, 'Clashes/T', 'Clash1 New', False),
                           (0, 'Clashes/T/Level 2-East', 'Clash2 Active', False),
                           (0, 'Clashes/T/Level 2-East', 'Clash3 Resolved', False)]
    assert folders[3] == (1, 'Clashes/T', 'Clash1 New (2)', False)
    plain = cv.plan([(0, 'T', _units())], 'group', ['New'], cv.DEFAULT_FOLDER, cv.DEFAULT_NAME,
                    'Meters', existing=lambda folder: existing.get(folder.lower(), set()))
    assert [(p['name'], p['exists']) for p in plain] == [('Clash1', True)]
    assert cv.counts(plain, False) == {'create': 0, 'replace': 0, 'skip': 1}
    assert cv.counts(plain, True) == {'create': 0, 'replace': 1, 'skip': 0}
    assert cv.top_folder(planned) == 'Clashes'


def test_comment_text_for_clash_and_group():
    units = _units()
    text = cv.comment_text(units[0], 'Meters')
    assert text.split('\n') == ['Status: New', 'Distance: -0.02 m', 'A: Duct (MEP.nwc)',
                                'B: Beam (STR.nwc)', 'Grid C-4, Level L2', 'Test: T']
    group = cv.comment_text(units[1], 'Meters').split('\n')
    assert group[0] == 'Group of 2 clashes: 1 Active, 1 Resolved'
    assert group[1] == 'Deepest: -0.05 m'


def test_create_through_fakes_skips_and_replaces():
    folder = _compat.tmpdir('clashviews')
    previous = paths.redirect(folder)
    try:
        doc, test = cf.clash_doc()
        removed = []
        doc.SavedViewpoints.Remove = lambda *args: removed.append(args[-1].DisplayName) or \
            (args[0].Children.remove(args[-1]) if len(args) == 2 else
             doc.SavedViewpoints.RootItem.Children.remove(args[-1]))
        with cf.ClashNav(doc):
            entry = cn.read_test(test, doc)
            units = ca.units_of(entry)
            refs = cv.items_by_ref([entry])
            planned = cv.plan([(0, entry['name'], units)], 'group', ['New'], cv.DEFAULT_FOLDER,
                              cv.DEFAULT_NAME, 'Meters', existing=cv.existing_names(doc))
            assert [(p['folder'], p['name']) for p in planned] == [
                ('Clashes/Ducts vs Walls', 'Clash1'), ('Clashes/Ducts vs Walls', 'Group 1')]
            totals = cv.create(planned, refs, False, doc)
            assert totals == {'created': 2, 'replaced': 0, 'skipped': 0, 'failed': 0}
            assert doc.transactions[0] == 'Clash viewpoints'
            root = doc.SavedViewpoints.RootItem
            clashes = root.Children[0]
            assert clashes.DisplayName == 'Clashes'
            inner = clashes.Children[0]
            assert [c.DisplayName for c in inner.Children] == ['Clash1', 'Group 1']
            assert inner.Children[0].Comments[0].Body.startswith('Status: New')
            again = cv.create(planned, refs, False, doc)
            assert again == {'created': 0, 'replaced': 0, 'skipped': 2, 'failed': 0}
            replaced = cv.create(planned[:1], refs, True, doc)
            assert replaced == {'created': 0, 'replaced': 1, 'skipped': 0, 'failed': 0}
            assert removed == ['Clash1']
            assert [c.DisplayName for c in inner.Children] == ['Group 1', 'Clash1']
    finally:
        paths.redirect(previous)


def test_create_comments_the_detached_viewpoint_and_survives_a_bad_folder():
    # The comment is added to the viewpoint before AddCopy (the shipped Clash Grouper's
    # way with new groups); a folder that cannot be made fails its views, not the run.
    folder = _compat.tmpdir('clashviews-comment')
    previous = paths.redirect(folder)
    try:
        doc, test = cf.clash_doc()
        seen = []
        saved_views = doc.SavedViewpoints
        plain_add = saved_views.AddCopy

        def add_copy(*args):
            seen.append([c.Body for c in args[-1].Comments])
            plain_add(*args)

        def no_add_comment(item, comment):
            raise RuntimeError('AddComment must not be needed')

        with cf.ClashNav(doc) as fake:
            class Commentable(cf.nav.SavedViewpoint):
                def __init__(self, viewpoint=None):
                    cf.nav.SavedViewpoint.__init__(self, viewpoint)
                    self.Comments = cf.nav.CommentCollection()

            fake.Api.SavedViewpoint = Commentable
            saved_views.AddCopy = add_copy
            saved_views.AddComment = no_add_comment
            entry = cn.read_test(test, doc)
            units = ca.units_of(entry)
            refs = cv.items_by_ref([entry])
            planned = cv.plan([(0, entry['name'], units)], 'group', ['New'], 'Clashes', '{name}',
                              'Meters', existing=cv.existing_names(doc))
            totals = cv.create(planned, refs, False, doc)
            assert totals == {'created': 2, 'replaced': 0, 'skipped': 0, 'failed': 0}
            views = [c for c in seen if c]
            assert len(views) == 2 and views[0][0].startswith('Status: New')

            from namo import camera
            real = camera.ensure_folder

            def broken(path, document=None):
                raise RuntimeError('could not create the viewpoint folder')
            camera.ensure_folder = broken
            try:
                other = cv.plan([(0, entry['name'], units)], 'group', ['New'], 'Elsewhere', '{name}',
                                'Meters', existing=cv.existing_names(doc))
                assert cv.create(other, refs, False, doc) == {
                    'created': 0, 'replaced': 0, 'skipped': 0, 'failed': 2}
            finally:
                camera.ensure_folder = real
    finally:
        paths.redirect(previous)
