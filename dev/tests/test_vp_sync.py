# -*- coding: utf-8 -*-
"""namo.vp_sync: import planning (targets, policies, duplicates), the report, and the
import itself on the fake (one transaction, units converted, comments kept)."""
import _compat
from _compat import approx

import test_items as nav
import test_vp_common as vpfake
from namo import camera, vp_sync


def rec(folder, name, position=(1.0, 2.0, 3.0), comments=None):
    cam = camera.make_cam(position, rotation=(0.0, 0.0, 0.0, 1.0), projection='persp',
                          height_field=1.0, focal_distance=10.0)
    return {'folder': folder, 'name': name, 'guid': '', 'camera': cam, 'clip': None, 'comments': comments or []}


def test_target_folder():
    assert vp_sync.target_folder('', 'A/B') == 'A/B'
    assert vp_sync.target_folder('From ARCH', 'A') == 'From ARCH/A'
    assert vp_sync.target_folder(' X \\ Y ', '') == 'X/Y'
    assert vp_sync.target_folder('X', 'A/B', keep_paths=False) == 'X'


def test_chosen_by_folder():
    records = [rec('A', '1'), rec('', '2'), rec('A/B', '3')]
    assert [r['name'] for r in vp_sync.chosen(records, ['A', ''])] == ['1', '2']


def test_plan_policies():
    records = [rec('A', 'One'), rec('A', 'Two'), rec('A', 'one')]
    existing = set([('A', 'two')])
    exists = lambda f, n: (f, n.lower()) in existing
    skip = vp_sync.plan(records, '', 'skip', exists)
    assert [s['action'] for s in skip] == ['create', 'skip', 'skip']
    replace = vp_sync.plan(records, '', 'replace', exists)
    assert [s['action'] for s in replace] == ['create', 'replace', 'keep']
    keep = vp_sync.plan(records, 'Imported', 'keep', exists)
    assert [(s['folder'], s['action']) for s in keep] == [('Imported/A', 'create'), ('Imported/A', 'create'),
                                                          ('Imported/A', 'keep')]
    assert vp_sync.plan_counts(replace) == {'create': 1, 'replace': 1, 'skip': 0, 'keep': 1}
    assert vp_sync.plan_sentence(replace) == 'Create 2 viewpoints, replace 1.'
    assert vp_sync.plan_sentence(skip) == 'Create 1 viewpoint, skip 2.'
    assert vp_sync.plan_sentence([]) == 'Nothing to do.'


def test_report_rows_and_summary():
    results = [{'folder': '', 'name': 'a', 'outcome': 'created', 'error': ''},
               {'folder': 'F', 'name': 'b', 'outcome': 'failed', 'error': 'boom'},
               {'folder': 'F', 'name': 'c', 'outcome': 'skipped', 'error': ''}]
    assert vp_sync.report_rows(results) == [['(top level)', 'a', 'Created'], ['F', 'b', 'Failed: boom'],
                                            ['F', 'c', 'Skipped (name taken)']]
    level, message, detail = vp_sync.summary(results, False, 3)
    assert level == 'warning' and message == 'Imported 1 viewpoint, 1 failed (1 skipped)' and detail == 'b: boom'
    assert vp_sync.summary(results[:1], False, 1)[0] == 'success'
    assert vp_sync.summary(results[2:], False, 1)[1] == 'No viewpoints imported'
    assert vp_sync.summary(results[:1], True, 5)[1] == 'Stopped after 1 of 5 viewpoints'
    assert vp_sync.summary(results[1:2], False, 1)[0] == 'error'


def test_default_package_name():
    assert vp_sync.default_package_name(r'C:\J\Tower.nwf', '2026-10-05') == 'Tower - Viewpoints - 2026-10-05.nvp.json'


def test_apply_imports_in_one_transaction_with_units():
    doc = vpfake.make_doc(units='Millimeters')
    vpfake.tree(doc)
    with nav.FakeNav(doc) as fake:
        vpfake.extend(fake.Api)
        records = [rec('C', 'Three', (1.0, 2.0, 3.0), [{'body': 'From the arch model', 'author': 'Ann',
                                                       'status': 'Active'}]),
                   rec('C', 'Four'), rec('', 'Top')]
        steps = vp_sync.plan(records, '', 'replace', vp_sync.existing_lookup(doc))
        assert [s['action'] for s in steps] == ['replace', 'create', 'replace']
        results, stopped = vp_sync.apply(doc, steps, 'Meters', include_clip=True, include_comments=True)
    assert not stopped
    assert [r['outcome'] for r in results] == ['replaced', 'created', 'replaced']
    assert doc.transactions[0] == 'Import viewpoints'     # nested ones are no-ops in pynavis
    c = doc.SavedViewpoints.RootItem.Children[2]
    three = c.Children[0]
    assert three.DisplayName == 'Three'
    assert approx(three.Viewpoint.Position.t(), (1000.0, 2000.0, 3000.0))
    assert [cm.Body for cm in three.Comments] == ['From the arch model']
    assert c.Children[1].DisplayName == 'Four'
    assert three.Viewpoint.ClipPlanes.Enabled is False


def test_apply_skips_and_stops():
    doc = vpfake.make_doc()
    vpfake.tree(doc)
    with nav.FakeNav(doc) as fake:
        vpfake.extend(fake.Api)
        steps = vp_sync.plan([rec('', 'Top'), rec('', 'New')], '', 'skip', vp_sync.existing_lookup(doc))
        results, stopped = vp_sync.apply(doc, steps, 'Meters')
        assert [r['outcome'] for r in results] == ['skipped', 'created']

        class Cancelled(Exception):
            pass

        def cancel(fraction, label):
            raise Cancelled()
        results, stopped = vp_sync.apply(doc, steps, 'Meters', report=cancel)
    assert stopped and results == []


def test_import_fields_defaults_are_option_values():
    from namo import ui
    fields = vp_sync.import_fields({'target': 'From A', 'keep_paths': False, 'policy': 'keep', 'clip': True,
                                    'comments': False})
    vpfake.check_defaults(fields)
    values, errors = ui.collect(ui.normalize_fields(fields), {'target': 'From A', 'keep_paths': False,
                                                              'policy': 'keep', 'clip': True, 'comments': False})
    assert not errors and values['policy'] == 'keep' and values['target'] == 'From A'
