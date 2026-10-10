# -*- coding: utf-8 -*-
"""namo.camera pure half: quaternion convention, look-at, bearings, lens, BCF, planes."""
import math

import _compat

from namo import camera

S = math.sqrt(0.5)


def _close(a, b, tol=1e-9):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def test_identity_is_plan_view():
    direction, up, right = camera.quat_to_axes(0, 0, 0, 1)
    assert _close(direction, (0, 0, -1))
    assert _close(up, (0, 1, 0))
    assert _close(right, (1, 0, 0))


def test_zero_quaternion_reads_as_identity():
    direction, up, right = camera.quat_to_axes(0, 0, 0, 0)
    assert _close(direction, (0, 0, -1)) and _close(up, (0, 1, 0))


def test_front_view_quaternion():
    # +90 degrees about X: looks along +Y with Z up (the ViewCube Front of a Z-up model)
    direction, up, right = camera.quat_to_axes(S, 0, 0, S)
    assert _close(direction, (0, 1, 0))
    assert _close(up, (0, 0, 1))
    assert _close(right, (1, 0, 0))


def test_unnormalised_quaternion_is_normalised():
    direction, up, right = camera.quat_to_axes(2 * S, 0, 0, 2 * S)
    assert _close(direction, (0, 1, 0))


def test_axes_to_quat_known_values():
    assert _close(camera.axes_to_quat((0, 0, -1), (0, 1, 0)), (0, 0, 0, 1))
    assert _close(camera.axes_to_quat((0, 1, 0), (0, 0, 1)), (S, 0, 0, S))


def test_round_trips_many_directions():
    ups = [(0, 0, 1), (0, 1, 0), (1, 0, 0)]
    for i in range(-6, 7):
        for j in range(0, 12):
            pitch = math.radians(i * 14.0)
            yaw = math.radians(j * 30.0 + 7.0)
            d = (math.cos(pitch) * math.sin(yaw), math.cos(pitch) * math.cos(yaw), math.sin(pitch))
            for up in ups:
                q = camera.axes_to_quat(d, up)
                assert q[3] >= 0.0
                assert _compat.approx(sum(x * x for x in q), 1.0, 1e-12)
                direction, true_up, right = camera.quat_to_axes(*q)
                assert _close(direction, d, 1e-9)
                expect_d, expect_up = camera.orthonormal_up(d, up)
                assert _close(true_up, expect_up, 1e-9)
                # right-handed: right = direction x up
                cross = (direction[1] * true_up[2] - direction[2] * true_up[1],
                         direction[2] * true_up[0] - direction[0] * true_up[2],
                         direction[0] * true_up[1] - direction[1] * true_up[0])
                assert _close(right, cross, 1e-9)


def test_orthonormal_up_degenerate_falls_back_to_north():
    f, u = camera.orthonormal_up((0, 0, -1), (0, 0, 1))
    assert _close(u, (0, 1, 0))
    f, u = camera.orthonormal_up((0, 1, 0), (0, 1, 0))
    assert _close(u, (1, 0, 0))
    _compat.raises(ValueError, camera.orthonormal_up, (0, 0, 0), (0, 0, 1))


def test_look_at_axes():
    d, u, r = camera.look_at_axes((0, 0, 0), (10, 0, 0))
    assert _close(d, (1, 0, 0)) and _close(u, (0, 0, 1)) and _close(r, (0, -1, 0))
    d, u, r = camera.look_at_axes((5, 5, 100), (5, 5, 0))      # straight down
    assert _close(d, (0, 0, -1)) and _close(u, (0, 1, 0))
    _compat.raises(ValueError, camera.look_at_axes, (1, 2, 3), (1, 2, 3))


def test_bearing_pitch():
    assert _close(camera.bearing_pitch((0, 1, 0)), (0.0, 0.0))
    assert _close(camera.bearing_pitch((1, 0, 0)), (90.0, 0.0))
    assert _close(camera.bearing_pitch((0, -1, 0)), (180.0, 0.0))
    assert _close(camera.bearing_pitch((-1, 0, 0)), (270.0, 0.0))
    b, p = camera.bearing_pitch((1, 1, math.sqrt(2)))
    assert _compat.approx(b, 45.0) and _compat.approx(p, 45.0)
    assert _close(camera.bearing_pitch((0, 0, -1)), (0.0, -90.0))
    assert camera.compass_name(44) == 'NE' and camera.compass_name(350) == 'N'


def test_bearing_with_project_north():
    # project north rotated 90 degrees: world +X is "north"
    b, p = camera.bearing_pitch((1, 0, 0), north=(1, 0, 0))
    assert _compat.approx(b, 0.0)


def test_lens_helpers():
    assert camera.projection_name('Orthographic') == 'ortho'
    assert camera.projection_name('Perspective') == 'persp'
    assert camera.fov_degrees(math.radians(60), 'persp') == 60.0 or \
        _compat.approx(camera.fov_degrees(math.radians(60), 'persp'), 60.0)
    assert camera.fov_degrees(12.0, 'ortho') is None
    assert _compat.approx(camera.height_field_for(90), math.pi / 2)
    v = camera.vertical_fov(90, 16.0 / 9.0)
    assert _compat.approx(camera.horizontal_fov(v, 16.0 / 9.0), 90.0)


def test_make_cam_fills_both_ways():
    cam = camera.make_cam((1, 2, 3), rotation=(S, 0, 0, S))
    assert _close(cam['direction'], (0, 1, 0)) and _close(cam['up'], (0, 0, 1))
    assert _compat.approx(cam['fov'], camera.DEFAULT_FOV)
    cam2 = camera.make_cam((1, 2, 3), direction=(0, 2, 0), up=(0, 0.1, 1))
    assert cam2['rotation'] is None
    assert _close(cam2['rotation_computed'], (S, 0, 0, S))
    assert _close(cam2['up'], (0, 0, 1))
    _compat.raises(ValueError, camera.make_cam, (0, 0, 0))


def test_bcf_round_trip_perspective():
    cam = camera.make_cam((10, 20, 5), direction=(1, 1, 0), up=(0, 0, 1),
                          height_field=math.radians(50), aspect=1.5)
    bcf = camera.to_bcf(cam, 0.3048)
    assert bcf['type'] == 'PerspectiveCamera'
    assert _close(bcf['CameraViewPoint'], (3.048, 6.096, 1.524))
    assert _compat.approx(bcf['FieldOfView'], 50.0)
    back = camera.from_bcf(bcf, 1 / 0.3048)
    assert _close(back['position'], (10, 20, 5), 1e-9)
    assert _close(back['direction'], cam['direction'])
    assert _close(back['up'], cam['up'])
    assert back['projection'] == 'persp'
    assert _compat.approx(back['fov'], 50.0)
    assert back['rotation'] is None and back['rotation_computed'] is not None


def test_bcf_round_trip_orthographic():
    cam = camera.make_cam((0, 0, 50), direction=(0, 0, -1), up=(0, 1, 0),
                          projection='ortho', height_field=40.0)
    bcf = camera.to_bcf(cam, 0.001)
    assert bcf['type'] == 'OrthogonalCamera'
    assert _compat.approx(bcf['ViewToWorldScale'], 0.04)
    back = camera.from_bcf(bcf, 1000.0)
    assert back['projection'] == 'ortho'
    assert _compat.approx(back['height_field'], 40.0)


def test_from_bcf_lenient_keys_and_skewed_up():
    back = camera.from_bcf({'position': (1, 1, 1), 'direction': (0, 1, 0),
                            'up': (0, 0.05, 1), 'fov': 45}, 1.0)
    assert _close(back['up'], (0, 0, 1))
    assert _compat.approx(back['fov'], 45.0)
    _compat.raises(ValueError, camera.from_bcf, {'up': (0, 0, 1)}, 1.0)


def test_to_bcf_from_rotation_only_cam():
    cam = camera.make_cam((0, 0, 0), rotation=(0, 0, 0, 1))
    cam['direction'] = None
    bcf = camera.to_bcf(cam, 1.0)
    assert _close(bcf['CameraDirection'], (0, 0, -1))


def test_horizontal_planes_point_into_kept_volume():
    planes = camera.horizontal_planes(10.0, 2.0, center=(5, 6))
    (top_origin, top_normal), (bottom_origin, bottom_normal) = planes
    assert top_origin == (5.0, 6.0, 10.0) and top_normal == (0.0, 0.0, -1.0)
    assert bottom_origin == (5.0, 6.0, 2.0) and bottom_normal == (0.0, 0.0, 1.0)
    assert len(camera.horizontal_planes(3.0)) == 1
    _compat.raises(ValueError, camera.horizontal_planes, 1.0, 5.0)


def test_range_ok_and_names():
    assert camera.range_ok([[0, 0, 0], [1, 1, 1]])
    assert not camera.range_ok([[1, 0, 0], [0, 1, 1]])
    assert not camera.range_ok(None)
    assert camera.unique_name('A', ['A', 'A (2)']) == 'A (3)'
    assert camera.unique_name('B', ['A']) == 'B'
    assert camera.split_path('Coordination/ Level 1 /') == ['Coordination', 'Level 1']
    assert camera.split_path('') == [] and camera.split_path(None) == []


def test_target_of():
    cam = camera.make_cam((0, 0, 0), direction=(0, 1, 0), focal_distance=10)
    assert _close(camera.target_of(cam), (0, 10, 0))


# ---- API half through the fake Navisworks layer (see test_items) -----------------

import test_items as nav  # noqa: E402


def test_api_capture_and_round_trip():
    doc = nav.Document()
    with nav.FakeNav(doc) as fake:
        vp = doc.CurrentViewpoint.vp
        vp.Rotation = nav.Rotation3D(S, 0, 0, S)
        vp.Position = nav.Point3D(1, 2, 3)
        vp.HeightField = math.radians(45)
        cam = camera.capture()
        assert _close(cam['direction'], (0, 1, 0)) and _close(cam['up'], (0, 0, 1))
        assert cam['projection'] == 'persp' and _compat.approx(cam['fov'], 45.0)
        assert cam['json'] == '{"camera": 1}' and cam['focal_distance'] == 10.0
        doc.CurrentViewpoint.vp.Rotation = nav.Rotation3D()
        camera.apply(cam)
        written = doc.CurrentViewpoint.writes[-1]
        assert (written.Rotation.A, written.Rotation.D) == (S, S)
        assert written.Position.t() == (1, 2, 3) and not written.aligned
        assert len(doc.CurrentViewpoint.writes) == 1


def test_api_look_at_uses_align_calls():
    doc = nav.Document()
    with nav.FakeNav(doc) as fake:
        doc.CurrentViewpoint.vp.Projection = fake.Api.ViewpointProjection.Orthographic
        camera.look_at((0, 0, 0), (10, 0, 0))
        written = doc.CurrentViewpoint.writes[-1]
        assert written.aligned == [('direction', (1.0, 0.0, 0.0)), ('up', (0.0, 0.0, 1.0))]
        assert str(written.Projection) == 'Perspective'
        assert _compat.approx(written.HeightField, math.radians(camera.DEFAULT_FOV))
        assert written.FocalDistance == 10.0
        camera.look_at((0, 0, 0), (0, 0, -5), fov_deg=30)
        written = doc.CurrentViewpoint.writes[-1]
        assert written.aligned[-1] == ('up', (0.0, 1.0, 0.0))
        assert _compat.approx(written.HeightField, math.radians(30))


def test_api_ortho_from_persp_takes_vertical_extent():
    doc = nav.Document()
    with nav.FakeNav(doc):
        cam = camera.make_cam((0, 0, 50), direction=(0, 0, -1), up=(0, 1, 0), projection='ortho')
        camera.apply(cam)
        written = doc.CurrentViewpoint.writes[-1]
        assert str(written.Projection) == 'Orthographic' and written.HeightField == 8.0


def test_api_zoom_to():
    doc = nav.Document()
    with nav.FakeNav(doc):
        assert camera.zoom_to(((0, 0, 0), (10, 10, 10)), margin=0.1)
        assert doc.CurrentViewpoint.writes[-1].zoomed == ((-1, -1, -1), (11, 11, 11))
        assert camera.zoom_to([]) is False


def test_api_folders_and_saved_views():
    doc = nav.Document()
    with nav.FakeNav(doc):
        leaf = camera.folder('Coordination/Level 1')
        assert leaf.DisplayName == 'Level 1' and leaf.Parent.DisplayName == 'Coordination'
        again = camera.ensure_folder('Coordination/Level 1')
        assert again is leaf and len(doc.SavedViewpoints.RootItem.Children) == 1
        first = camera.save_view('Clash 1', 'Coordination/Level 1', comments='Check this')
        second = camera.save_view('Clash 1', 'Coordination/Level 1', comments=['a', '', 'b'])
        assert first.DisplayName == 'Clash 1' and second.DisplayName == 'Clash 1 (2)'
        assert first.Parent is leaf and [c.Body for c in second.Comments] == ['a', 'b']
        top = camera.save_view('Overview')
        assert top.Parent is None
        listed = [(path, item.DisplayName) for path, item in camera.saved_views()]
        assert listed == [('Coordination/Level 1', 'Clash 1'), ('Coordination/Level 1', 'Clash 1 (2)'),
                          ('', 'Overview')]
        assert camera.find_view('Coordination/Level 1/Clash 1 (2)') is second
        assert camera.find_view('Overview') is top
        assert camera.find_view('Nope') is None
        camera.recall(top)
        assert doc.SavedViewpoints.CurrentSavedViewpoint is top
        assert 'Save viewpoint' in doc.transactions


def test_api_horizontal_section_and_clear():
    doc = nav.Document()
    with nav.FakeNav(doc) as fake:
        assert camera.horizontal_section(6.0, 1.0) == 2
        assert len(doc.CurrentViewpoint.writes) == 1
        planes = doc.CurrentViewpoint.vp.ClipPlanes
        assert planes.Enabled and str(planes.Mode) == 'Planes' and planes.Linked is False
        top, bottom = planes.planes[0], planes.planes[1]
        assert top.Origin.t() == (10.0, 5.0, 6.0) and top.Normal.t() == (0.0, 0.0, -1.0)
        assert bottom.Origin.t() == (10.0, 5.0, 1.0) and bottom.Normal.t() == (0.0, 0.0, 1.0)
        assert str(top.alignment) == 'Custom' and str(top.State) == 'Enabled'
        assert not any(p.Enabled for p in planes.planes[2:])
        assert planes.Range.Max.t() == (20.0, 10.0, 9.0)
        state = camera.clip_state()
        assert state['enabled'] and state['active'] == 2 and state['mode'] == 'Planes'
        assert state['planes'][0]['normal'] == [0.0, 0.0, -1.0]
        assert camera.clear_section() is True
        assert camera.clear_section() is False
        camera.set_clip_state(state)
        again = doc.CurrentViewpoint.vp.ClipPlanes
        assert again.Enabled and again.planes[1].Origin.t() == (10.0, 5.0, 1.0)
        camera.section_box(((0, 0, 0), (1, 2, 3)))
        assert str(doc.CurrentViewpoint.vp.ClipPlanes.Mode) == 'Box'
        boxed = camera.clip_state()
        assert boxed['box']['max'] == [1.0, 2.0, 3.0] and boxed['box']['rotation'] is None
        assert camera.clip_json() == '{"planes": []}'
        assert camera.set_clip_json('{"planes": []}')
        _compat.raises(ValueError, camera.set_clip_json, 'garbage')


def test_view_path_and_match_view_find_names_that_hold_a_slash():
    views = [('', 'Overview', 1), ('Coordination', 'Level 1/2', 2), ('Coordination/Level 1', 'Clash 1', 3),
             ('', 'North / East', 4), ('A', 'B', 5), ('Deep', 'A/B', 6)]
    assert camera.view_path('', 'Overview') == 'Overview'
    assert camera.view_path('Coordination', 'Level 1/2') == 'Coordination/Level 1/2'
    # the stored path of a name with a slash: the split-on-slash walk could never find it
    assert camera.match_view('Coordination/Level 1/2', views) == 2
    assert camera.match_view('North / East', views) == 4
    # ordinary paths and bare names as before
    assert camera.match_view('Coordination/Level 1/Clash 1', views) == 3
    assert camera.match_view('Clash 1', views) == 3 and camera.match_view('Overview', views) == 1
    # 'A/B' is the view B in folder A (an exact stored path) before the view named 'A/B'
    assert camera.match_view('A/B', views) == 5
    # a bare name with a slash, wherever it lives
    assert camera.match_view('Level 1/2', views) == 2
    assert camera.match_view('Nope', views) is None and camera.match_view('', views) is None
    assert camera.match_view('Coordination/Nope', views) is None


def test_api_find_view_reads_back_a_name_with_a_slash():
    doc = nav.Document()
    with nav.FakeNav(doc):
        plain = camera.save_view('Clash 1', 'Coordination')
        slashed = camera.save_view('Level 1/2', 'Coordination')
        top = camera.save_view('North / East')
        stored = [camera.view_path(path, item.DisplayName) for path, item in camera.saved_views()]
        assert stored == ['Coordination/Clash 1', 'Coordination/Level 1/2', 'North / East']
        assert camera.find_view(stored[1]) is slashed
        assert camera.find_view(stored[2]) is top
        assert camera.find_view('Level 1/2') is slashed
        assert camera.find_view('Coordination/Clash 1') is plain and camera.find_view('Clash 1') is plain
        assert camera.find_view('Coordination/Level 1') is None and camera.find_view(None) is None


def test_api_write_camera_edits_the_viewpoint_it_is_given():
    doc = nav.Document()
    with nav.FakeNav(doc):
        view = doc.CurrentViewpoint.vp
        cam = camera.make_cam((4, 5, 6), rotation=(S, 0, 0, S))
        assert camera.write_camera(view, cam) is view
        assert view.Position.t() == (4, 5, 6) and (view.Rotation.A, view.Rotation.D) == (S, S)
        assert doc.CurrentViewpoint.writes == []           # nothing was recalled on screen
        _compat.raises(ValueError, camera.write_camera, view, {'position': (0, 0, 0)})
