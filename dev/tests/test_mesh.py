# -*- coding: utf-8 -*-
"""namo.mesh: area, volume, centroid, closure and welding on known shapes."""
import _compat

from namo import mesh


def _box(x0, y0, z0, x1, y1, z1):
    """12 outward-wound triangles of an axis-aligned box."""
    p = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
         (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    quads = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (2, 3, 7, 6), (1, 2, 6, 5), (0, 4, 7, 3)]
    tris = []
    for a, b, c, d in quads:
        tris.append((p[a], p[b], p[c]))
        tris.append((p[a], p[c], p[d]))
    return tris


def test_unit_cube():
    cube = _box(0, 0, 0, 1, 1, 1)
    assert mesh.count(cube) == 12
    assert _compat.approx(mesh.area(cube), 6.0)
    assert _compat.approx(mesh.volume(cube), 1.0)
    assert _compat.approx(mesh.signed_volume(cube), 1.0)
    assert mesh.is_closed(cube)
    assert _compat.approx(mesh.centroid(cube), (0.5, 0.5, 0.5))
    assert mesh.bbox(cube) == ((0, 0, 0), (1, 1, 1))


def test_box_far_from_origin_keeps_precision():
    box = _box(1e6, 2e6, 100, 1e6 + 2, 2e6 + 3, 104)
    assert _compat.approx(mesh.volume(box), 24.0, 1e-9)
    assert _compat.approx(mesh.centroid(box), (1e6 + 1, 2e6 + 1.5, 102), 1e-12)


def test_inward_wound_volume_is_still_positive():
    cube = [(a, c, b) for a, b, c in _box(0, 0, 0, 2, 2, 2)]
    assert _compat.approx(mesh.signed_volume(cube), -8.0)
    assert _compat.approx(mesh.volume(cube), 8.0)


def test_open_box_is_not_closed():
    open_box = _box(0, 0, 0, 1, 1, 1)[2:]          # bottom missing
    assert not mesh.is_closed(open_box)
    assert mesh.open_edges(open_box) == 4
    # open mesh falls back to the area centroid
    c = mesh.centroid(open_box)
    assert c is not None and _compat.approx(c, (0.5, 0.5, 0.6))


def test_weld_counts():
    cube = _box(0, 0, 0, 1, 1, 1)
    vertices, faces = mesh.weld(cube)
    assert len(vertices) == 8
    assert len(faces) == 12


def test_weld_tolerance_merges_noise():
    cube = _box(0, 0, 0, 1, 1, 1)
    noisy = [tuple((x + 1e-9, y, z) for x, y, z in tri) if i % 2 else tri
             for i, tri in enumerate(cube)]
    vertices, faces = mesh.weld(noisy, tol=1e-6)
    assert len(vertices) == 8
    assert mesh.is_closed(noisy, tol=1e-6)


def test_weld_drops_collapsed_triangles():
    degenerate = [((0, 0, 0), (0, 0, 0), (1, 0, 0))]
    vertices, faces = mesh.weld(degenerate)
    assert faces == []


def test_empty_mesh():
    assert mesh.area([]) == 0.0
    assert mesh.volume([]) == 0.0
    assert mesh.bbox([]) is None
    assert mesh.centroid([]) is None
    assert not mesh.is_closed([])


def test_translate_and_summary():
    cube = _box(0, 0, 0, 1, 1, 1)
    moved = mesh.translate(cube, (10, 0, 0))
    assert mesh.bbox(moved) == ((10, 0, 0), (11, 1, 1))
    assert mesh.bbox(cube) == ((0, 0, 0), (1, 1, 1))
    s = mesh.summary(cube)
    assert s['closed'] and _compat.approx(s['volume'], 1.0) and s['triangles'] == 12
    s_open = mesh.summary(cube[2:])
    assert s_open['volume'] is None and not s_open['closed']


def test_two_disjoint_cubes():
    two = _box(0, 0, 0, 1, 1, 1) + _box(5, 0, 0, 6, 1, 1)
    assert mesh.is_closed(two)
    assert _compat.approx(mesh.volume(two), 2.0)
    assert _compat.approx(mesh.centroid(two), (3.0, 0.5, 0.5))


def _unwelded_box():
    """A watertight 2 x 2 x 1 box whose top is split around a middle vertex the side faces
    never use (T-junctions on every top edge): how Navisworks tessellates neighbours."""
    box = [t for i, t in enumerate(_box(0, 0, 0, 2, 2, 1)) if i not in (2, 3)]    # without the top
    m = (1.0, 1.0, 1.0)
    mids = [(1.0, 0.0, 1.0), (2.0, 1.0, 1.0), (1.0, 2.0, 1.0), (0.0, 1.0, 1.0)]
    corners = [(0.0, 0.0, 1.0), (2.0, 0.0, 1.0), (2.0, 2.0, 1.0), (0.0, 2.0, 1.0)]
    top = []
    for i in range(4):
        top.append((m, corners[i], mids[i]))
        top.append((m, mids[i], corners[(i + 1) % 4]))
    return box + top


def test_summary_measures_a_watertight_solid_whose_faces_share_no_vertices():
    # Regression: summary() used the welded-edge test, so such a solid had no volume and
    # callers (Duplicate Finder's deep compare) fell back to guessing.
    tris = _unwelded_box()
    assert not mesh.is_closed(tris)                         # topologically open
    s = mesh.summary(tris)
    assert s['closed'] is True and s['welded'] is False
    assert _compat.approx(s['volume'], 4.0) and _compat.approx(s['centroid'], (1.0, 1.0, 0.5))
    assert _compat.approx(mesh.centroid(tris), (1.0, 1.0, 0.5))
    assert _compat.approx(mesh.solid_measure(tris)['volume'], 4.0)


def test_summary_gives_no_volume_to_an_open_or_miswound_mesh():
    cube = _box(0, 0, 0, 1, 1, 1)
    open_box = cube[2:]
    assert mesh.summary(open_box)['volume'] is None and mesh.summary(open_box)['closed'] is False
    # every edge pairs up, but one face is wound the wrong way: the signed volume is wrong
    a, b, c = cube[0]
    flipped = [(a, c, b)] + cube[1:]
    assert mesh.is_closed(flipped)
    s = mesh.summary(flipped)
    assert s['volume'] is None and s['closed'] is False and s['welded'] is True
    assert mesh.solid_measure([]) is None and mesh.summary([])['volume'] is None


def test_weld_tolerance_follows_the_noise_and_the_size_of_the_mesh():
    big = _box(0, 0, 0, 10, 5, 2)
    assert _compat.approx(mesh.weld_tolerance(big), 1e-6)            # a ten millionth of 10
    assert _compat.approx(mesh.weld_tolerance(big, 0.001), 0.004)    # four times the noise
    assert mesh.weld_tolerance([]) == 0.0


def test_default_tolerance_welds_float32_noise_far_from_the_origin():
    # 1.37 million feet out a float32 coordinate is good to about 0.1 ft. With the old
    # fixed 1e-6 the corners never met; the default now comes from the mesh and the noise.
    far = _box(1370000.0, -1370000.0, 300.0, 1370040.0, -1369960.0, 330.0)
    nudged = []
    for n, tri in enumerate(far):
        nudged.append(tuple((p[0] + (0.03 if n % 2 else -0.03), p[1], p[2]) for p in tri))
    assert not mesh.is_closed(nudged, tol=1e-6)
    tol = mesh.weld_tolerance(nudged, noise=0.1)
    assert _compat.approx(tol, 0.4)
    assert mesh.is_closed(nudged, tol=tol)
    assert mesh.summary(nudged, tol)['welded'] is True
    # a small mesh: the default scales down with it instead of merging real corners
    tiny = _box(0, 0, 0, 1e-5, 1e-5, 1e-5)
    assert mesh.is_closed(tiny) and len(mesh.weld(tiny)[0]) == 8
