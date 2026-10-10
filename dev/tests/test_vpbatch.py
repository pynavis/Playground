# -*- coding: utf-8 -*-
"""namo.vpbatch: settings and form fields, names, grid sampling and line maths,
cameras, the runner (one transaction, hide-and-capture) and summaries."""
import math

import _compat
from _compat import approx

import test_items as nav
import test_vp_common as vpfake
from namo import levels, ui, vpbatch


def test_settings_are_made_safe():
    cfg = vpbatch.settings({'cut_height_m': '-2', 'zoom_margin': 900, 'generator': 'x', 'policy': 'y',
                            'grid_axis': 'up', 'level_view': 'side', 'slab': 0, 'unknown': 1})
    assert cfg['cut_height_m'] == 2.0 and cfg['zoom_margin'] == 200 and cfg['generator'] == 'level'
    assert cfg['policy'] == 'replace' and cfg['grid_axis'] == 'line1' and cfg['level_view'] == 'plan'
    assert cfg['slab'] is False and 'unknown' not in cfg


def test_fields_are_valid_forms_in_document_units():
    cfg = vpbatch.settings(None)
    for generator, _label in vpbatch.GENERATORS:
        options = [('Level 1 (0 m)', 'Level 1')] if generator == 'grid' else None
        fields = vpbatch.fields_for(generator, cfg, 'Millimeters', options)
        vpfake.check_defaults(fields)
        specs = ui.normalize_fields(fields)
        keys = [f.get('key') for f in specs]
        assert 'folder' in keys and 'name' in keys and 'policy' in keys
    level_fields = vpbatch.fields_for('level', cfg, 'Millimeters')
    cut = [f for f in level_fields if f.get('key') == 'cut_height'][0]
    assert cut['default'] == 1200.0


def test_update_settings_converts_back_to_metres():
    cfg = vpbatch.settings(None)
    values = {'cut_height': 4.0, 'eye_height': None, 'level_view': 'eye', 'folder': 'Plans/{level}',
              'name': '{level} plan', 'policy': 'keep', 'comment': False, 'slab': False}
    out = vpbatch.update_settings(cfg, 'level', values, 'Feet')
    assert approx(out['cut_height_m'], 1.2192) and out['eye_height_m'] == 1.6
    assert out['folder_level'] == 'Plans/{level}' and out['name_level'] == '{level} plan'
    assert out['level_view'] == 'eye' and out['policy'] == 'keep' and out['comment'] is False
    keep = vpbatch.update_settings(cfg, 'set', {'name': ''}, 'Meters')
    assert keep['name_set'] == '{set}'


def test_render_jobs_tokens_numbers_and_slashes():
    entries = [{'level': 'Level 1/2 mezz', 'elevation': '4.200 m'}, {'level': '', 'fallback': 'L9'}]
    jobs = vpbatch.render_jobs(entries, 'Batch/{level}', '{n:00} {level} at {elevation}', {'file': 'Tower'})
    assert jobs[0] == ('Batch/Level 1-2 mezz', '01 Level 1/2 mezz at 4.200 m')
    assert jobs[1] == ('Batch', '02 at {elevation}')
    blank = vpbatch.render_jobs([{'fallback': 'Plan'}], '', '', None)
    assert blank == [('', 'Plan')]
    assert vpbatch.render_jobs([{}], ' / x // y ', '{n}')[0] == ('x/y', '1')


def test_comment_text():
    cfg = vpbatch.settings(None)
    text = vpbatch.comment_text('level', {'level': 'L2', 'elevation_value': 4.2, 'approximate': True}, cfg,
                                'Meters', '2026-10-05', 'Ann')
    assert text.startswith('Plan of L2 (4.200 m), cut 1.200 m above.')
    assert 'estimated' in text and text.endswith('Made by Batch Viewpoints 2026-10-05 by Ann.')
    assert vpbatch.comment_text('grid', {'grid': 'A-1', 'level': 'L1'}, cfg, 'Meters').startswith(
        'Grid intersection A-1 on L1.')
    assert 'set Ducts' in vpbatch.comment_text('set', {'set': 'Ducts'}, cfg, 'Meters')


def test_lattice_covers_the_box_within_budget():
    points, step = vpbatch.lattice(((0, 0, 0), (10, 4, 1)), 1.0)
    assert step == 1.0 and len(points) == 40
    assert points[0] == (0.5, 0.5) and points[-1] == (9.5, 3.5)
    many, big_step = vpbatch.lattice(((0, 0, 0), (1000, 1000, 0)), 1.0, max_points=500)
    assert len(many) <= 500 and big_step > 1.0


def test_lines_crossings_and_candidates():
    found = [{'line1': 'A', 'line2': '1', 'position': (0.0, 0.0, 0.0), 'dir1': (0, 1, 0), 'dir2': (1, 0, 0)},
             {'line1': 'B', 'line2': '2', 'position': (8.0, 6.0, 0.0), 'dir1': (0, 1, 0), 'dir2': (1, 0, 0)},
             {'line1': 'C', 'line2': '', 'position': (5.0, 5.0, 0.0), 'dir1': (0, 0, 1), 'dir2': None}]
    lines = vpbatch.lines_from(found)
    assert sorted(lines) == ['1', '2', 'A', 'B']
    assert approx(vpbatch.crossing(lines['A'], lines['2']), (0.0, 6.0))
    assert vpbatch.crossing(lines['A'], lines['B']) is None
    known = set([vpbatch.pair_key('A', '1'), vpbatch.pair_key('2', 'B')])
    extra = vpbatch.candidates(lines, ((-1, -1, 0), (10, 10, 0)), known)
    assert [(a, b) for a, b, _p in extra] == [('1', 'B'), ('2', 'A')]
    assert vpbatch.pair_key('B', 'A') == ('A', 'B')


def test_sort_and_look_directions():
    found = [{'name': 'B-10', 'position': (0, 0, 0)}, {'name': 'B-2', 'position': (0, 0, 0)},
             {'name': 'A-1', 'position': (0, 0, 0)}]
    assert [r['name'] for r in vpbatch.sort_intersections(found)] == ['A-1', 'B-2', 'B-10']
    assert vpbatch.look_direction('east') == (1.0, 0.0, 0.0)
    assert approx(vpbatch.look_direction('line1', (3, 4, 9)), (0.6, 0.8, 0.0))
    assert vpbatch.look_direction('line2', None, None) == (0.0, 1.0, 0.0)


def test_eye_cameras_and_boxes():
    eye, direction, distance = vpbatch.corner_eye(((0, 0, 0), (100, 50, 9)), 1.6)
    assert approx(eye, (8.0, 4.0, 1.6)) and approx(direction[2], 0.0)
    assert approx(distance, math.hypot(42, 21))
    cam = vpbatch.eye_camera(eye, direction, 60.0, distance)
    assert cam['projection'] == 'persp' and approx(cam['fov'], 60.0) and approx(cam['up'], (0.0, 0.0, 1.0))
    low, high = vpbatch.grown(((0, 0, 0), (10, 20, 0)), 0.1)
    assert approx(low, (-1.0, -2.0, -0.1)) and approx(high, (11.0, 22.0, 0.1))


def test_storey_height():
    lvls = [levels.level('A', 0), levels.level('B', 3), levels.level('C', 7)]
    assert vpbatch.storey_height(lvls, 'Meters') in (3, 4)
    assert approx(vpbatch.storey_height([levels.level('A', 0)], 'Feet'), 4.0 / 0.3048)


def test_summary_sentences():
    base = {'created': 3, 'replaced': 1, 'skipped': 0, 'failed': [], 'stopped': False, 'total': 4,
            'hidden_lost': 0, 'folders': ['Batch/Levels']}
    assert vpbatch.summary(base) == ('success', 'Saved 4 viewpoints (1 replaced)',
                                     'In Batch/Levels. One Ctrl+Z removes them all.')
    stopped = dict(base, stopped=True, total=10)
    assert vpbatch.summary(stopped)[1] == 'Stopped after 4 of 10 viewpoints'
    failed = dict(base, failed=[('L3', 'boom')])
    assert vpbatch.summary(failed) == ('warning', 'Saved 4 viewpoints, 1 failed (1 replaced)', 'L3: boom')
    lost = dict(base, hidden_lost=2)
    assert vpbatch.summary(lost)[0] == 'warning' and 'Save Hide/Required' in vpbatch.summary(lost)[2]
    none = dict(base, created=0, replaced=0, skipped=4)
    assert vpbatch.summary(none)[1] == 'No viewpoints saved'


# ---- API half on the fake ---------------------------------------------------------------


class _Ns(object):
    def __init__(self, **kw):
        self.__dict__.update(kw)


class FakeGridLevel(object):
    """A grid of lines A, B (x = 0, 6) and 1, 2, 3 (y = 0, 5, 10) at elevation 4."""
    Elevation = 4.0

    def __init__(self):
        self.asked = 0

    def ClosestIntersection(self, point):
        self.asked += 1
        xs = [('A', 0.0), ('B', 6.0)]
        ys = [('1', 0.0), ('2', 5.0), ('3', 10.0)]
        lx = min(xs, key=lambda t: abs(t[1] - point.X))
        ly = min(ys, key=lambda t: abs(t[1] - point.Y))
        return _Ns(DisplayName='%s-%s' % (lx[0], ly[0]), Position=nav.Point3D(lx[1], ly[1], 4.0),
                   Line1=_Ns(DisplayName=lx[0]), Line2=_Ns(DisplayName=ly[0]),
                   Line1Direction=nav.Point3D(0, 1, 0), Line2Direction=nav.Point3D(1, 0, 0))


def test_find_intersections_on_a_fake_grid():
    doc = vpfake.make_doc()
    with nav.FakeNav(doc) as fake:
        vpfake.extend(fake.Api)
        level = FakeGridLevel()
        found, step = vpbatch.find_intersections(doc, level, ((-1, -1, 0), (7, 11, 9)), 2.0)
    assert [r['name'] for r in found] == ['A-1', 'A-2', 'A-3', 'B-1', 'B-2', 'B-3']
    assert found[0]['line1'] == 'A' and found[0]['dir1'] == (0.0, 1.0, 0.0)
    assert step == 2.0 and level.asked >= 6


def test_run_files_jobs_in_one_transaction():
    doc = vpfake.make_doc()
    vpfake.tree(doc)
    with nav.FakeNav(doc) as fake:
        vpfake.extend(fake.Api)
        cfg = vpbatch.settings({'policy': 'replace'})
        jobs = [{'folder': 'Batch', 'name': 'One', 'build': lambda: nav.Viewpoint(), 'keep': None,
                 'comment': 'made'},
                {'folder': '', 'name': 'Top', 'build': lambda: nav.Viewpoint(), 'keep': None, 'comment': None},
                {'folder': 'Batch', 'name': 'Bad', 'build': lambda: 1 / 0, 'keep': None, 'comment': None}]
        result = vpbatch.run(doc, jobs, cfg)
    assert result['created'] == 1 and result['replaced'] == 1 and len(result['failed']) == 1
    assert result['folders'] == ['Batch', ''] and doc.transactions[0] == 'Batch viewpoints'
    batch = doc.SavedViewpoints.RootItem.Children[-1]
    assert batch.DisplayName == 'Batch' and [c.Body for c in batch.Children[0].Comments] == ['made']
    level, message, _detail = vpbatch.summary(result)
    assert level == 'warning' and message.startswith('Saved 2 viewpoints, 1 failed')


def test_run_hide_and_capture_restores_hidden_flags():
    doc, named = nav.model_tree()
    doc.SavedViewpoints = vpfake.ViewsSaved(doc)
    doc.Units = 'Meters'
    doc.FileName = ''
    with nav.FakeNav(doc) as fake:
        vpfake.extend(fake.Api)
        cfg = vpbatch.settings({'policy': 'keep'})
        targets = [{'name': 'Walls', 'folder': '', 'items': [named['Wall 1'], named['Wall 2']]}]
        cfg['hide_others'] = True
        jobs = vpbatch.zoom_jobs(doc, targets, 'set', cfg)
        assert jobs[0]['keep'] is not None and jobs[0]['name'] == 'Walls'
        result = vpbatch.run(doc, jobs, cfg)
    assert result['created'] == 1 and result['hidden_lost'] == 0
    hides = [c for c in doc.Models.calls if c[0] == 'hidden']
    assert len(hides) == 2 and hides[0][2] is True and hides[1][2] is False
    assert [i.DisplayName for i in hides[0][1]] == [i.DisplayName for i in hides[1][1]]
    assert 'Wall 1' not in [i.DisplayName for i in hides[0][1]]
    batch = doc.SavedViewpoints.RootItem.Children[0]
    assert batch.DisplayName == 'Batch' and batch.Children[0].DisplayName == 'Sets'
    saved = batch.Children[0].Children[0]
    assert saved.DisplayName == 'Walls' and saved.ContainsVisibilityOverrides
    assert len(doc.CurrentViewpoint.writes) >= 2          # shown, then the view put back


def test_zoom_jobs_frame_the_items():
    doc, named = nav.model_tree()
    doc.SavedViewpoints = vpfake.ViewsSaved(doc)
    doc.Units = 'Meters'
    with nav.FakeNav(doc) as fake:
        vpfake.extend(fake.Api)
        cfg = vpbatch.settings({'zoom_margin': 0, 'keep_section': False})
        jobs = vpbatch.zoom_jobs(doc, [{'name': 'ARCH', 'items': [named['ARCH.nwc']]}], 'model', cfg)
        viewpoint = jobs[0]['build']()
    assert jobs[0]['folder'] == 'Batch/Models' and jobs[0]['name'] == 'ARCH'
    assert viewpoint.zoomed == ((0.0, 0.0, 0.0), (6.0, 5.0, 3.0))
    assert viewpoint.ClipPlanes.Enabled is False


def test_level_jobs_build_plan_viewpoints():
    doc, named = nav.model_tree()
    doc.SavedViewpoints = vpfake.ViewsSaved(doc)
    doc.Units = 'Meters'
    with nav.FakeNav(doc) as fake:
        vpfake.extend(fake.Api)
        lvls = [levels.level('Ground', 0.0), levels.level('First', 2.0)]
        cfg = vpbatch.settings({'level_frame': 'level', 'slab': False})
        jobs, sampled = vpbatch.level_jobs(doc, lvls, lvls, cfg)
        plan = jobs[0]['build']()
        cfg_eye = vpbatch.settings({'level_view': 'eye'})
        eye_jobs, _s = vpbatch.level_jobs(doc, lvls, lvls[1:], cfg_eye)
        eye = eye_jobs[0]['build']()
    assert not sampled and [j['name'] for j in jobs] == ['Ground', 'First']
    assert plan.ClipPlanes.Enabled and plan.ClipPlanes.planes[0].Origin.t()[2] == 1.2
    assert plan.zoomed is not None and plan.zoomed[0][2] == 0.0
    assert [a for a in plan.aligned if a[0] == 'direction'][0][1] == (0.0, 0.0, -1.0)
    assert eye_jobs[0]['name'] == 'First'
    assert eye.Position.t()[2] == 3.6
