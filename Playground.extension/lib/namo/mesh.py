# -*- coding: utf-8 -*-
"""Triangle-mesh maths on plain tuples, plus the one call that reads an item's mesh.

A mesh here is a list of triangles, each ((x, y, z), (x, y, z), (x, y, z)) in world
coordinates, exactly what pynavis.geometry.world_triangles returns. Everything except
item_triangles() is pure and runs under CPython and IronPython alike.

Volume and solid centroid are only meaningful for a CLOSED, consistently wound mesh
(Revit solids exported to Navisworks usually are; sheet geometry, imported meshes and
items clipped by the exporter often are not). volume() always returns the absolute
signed-tetrahedra sum, so ask solid_measure() (or summary()) before trusting it, and
say "geometric" or "approximate" in reports.

Two closure tests, for two different questions:

  * solid_measure(tris) is GEOMETRIC: do these faces enclose a volume? It does not care
    whether the exporter welded its faces. Curved faces are tessellated on their own and
    rarely share vertices with their neighbours, so a watertight pipe fails the
    topological test. This is the test for volumes and centroids; summary() and
    centroid() use it.
  * is_closed(tris, tol) is TOPOLOGICAL: is every welded edge shared by exactly two
    triangles? Right for an exporter that needs a manifold; too strict for takeoff.

Coordinates are float32 underneath (COM vertices). A fixed weld epsilon is wrong far
from the origin (the owner's model sits 1.37 million feet out, where the noise is about
0.1 ft), so tol defaults to weld_tolerance(tris): pass the 'noise' item_triangles()
reports through weld_tolerance(tris, noise) whenever you have it.
"""

import math


# ---- small vector helpers ------------------------------------------------------


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _norm(v):
    return math.sqrt(_dot(v, v))


# ---- measures -----------------------------------------------------------------


def count(tris):
    """How many triangles."""
    return len(tris)


def triangle_area(tri):
    a, b, c = tri
    return 0.5 * _norm(_cross(_sub(b, a), _sub(c, a)))


def area(tris):
    """Total surface area, in model units squared."""
    total = 0.0
    for tri in tris:
        total += triangle_area(tri)
    return total


def signed_volume(tris):
    """Sum of signed tetrahedra against the origin. Positive for an outward-wound
    closed mesh, negative for an inward-wound one; meaningless for an open one."""
    total = 0.0
    for a, b, c in tris:
        total += _dot(a, _cross(b, c))
    return total / 6.0


def volume(tris):
    """Enclosed volume (absolute signed-tetrahedra sum), model units cubed.

    Large coordinates far from the origin lose precision in the sum, so the mesh
    is shifted to its own bounding-box corner first.
    """
    if not tris:
        return 0.0
    box = bbox(tris)
    return abs(signed_volume(translate(tris, (-box[0][0], -box[0][1], -box[0][2]))))


def bbox(tris):
    """((xmin, ymin, zmin), (xmax, ymax, zmax)) or None for an empty mesh."""
    low = [None, None, None]
    high = [None, None, None]
    for tri in tris:
        for point in tri:
            for axis in range(3):
                value = point[axis]
                if low[axis] is None or value < low[axis]:
                    low[axis] = value
                if high[axis] is None or value > high[axis]:
                    high[axis] = value
    if low[0] is None:
        return None
    return (tuple(low), tuple(high))


def area_centroid(tris):
    """Area-weighted centre of the surface, or None for a mesh with no area."""
    total = 0.0
    acc = [0.0, 0.0, 0.0]
    for tri in tris:
        weight = triangle_area(tri)
        if weight <= 0.0:
            continue
        total += weight
        for axis in range(3):
            acc[axis] += weight * (tri[0][axis] + tri[1][axis] + tri[2][axis]) / 3.0
    if total <= 0.0:
        return None
    return (acc[0] / total, acc[1] / total, acc[2] / total)


def solid_centroid(tris):
    """Centre of mass of the enclosed solid, or None when the volume is ~zero."""
    if not tris:
        return None
    box = bbox(tris)
    origin = box[0]
    shifted = translate(tris, (-origin[0], -origin[1], -origin[2]))
    total = 0.0
    acc = [0.0, 0.0, 0.0]
    for a, b, c in shifted:
        v = _dot(a, _cross(b, c)) / 6.0
        total += v
        for axis in range(3):
            acc[axis] += v * (a[axis] + b[axis] + c[axis]) / 4.0
    if abs(total) <= _volume_floor(box):
        return None
    return (acc[0] / total + origin[0], acc[1] / total + origin[1], acc[2] / total + origin[2])


def _volume_floor(box):
    """A volume this small relative to the bounding box is numerical noise."""
    size = [box[1][i] - box[0][i] for i in range(3)]
    biggest = max(size) if size else 0.0
    return max(1e-12, (biggest ** 3) * 1e-9)


def centroid(tris):
    """The solid centroid when the mesh encloses a real volume (solid_measure, the
    geometric test), else the area centroid (sheets, open meshes), else None for an
    empty mesh."""
    solid = solid_measure(tris)
    if solid is not None:
        return solid['centroid']
    return area_centroid(tris)


AREA_CLOSURE = 1e-4      # |sum of area vectors| / total area a closed surface may show
AXIS_AGREEMENT = 1e-3    # how far the three per-axis volumes of a closed surface may differ


def solid_measure(tris):
    """{'volume', 'centroid'} of the solid a triangle mesh encloses (model units), or None
    when the mesh does not enclose one.

    The test is geometric, not topological, so it does not care whether the exporter
    welded its faces (curved faces are tessellated on their own and rarely share
    vertices with their neighbours, which made a watertight pipe look open): by the
    divergence theorem a closed, consistently wound surface has area vectors that sum to
    nothing, and the three integrals of x.nx, y.ny and z.nz over it each equal its
    volume. An open tube passes the first check and fails the second; a face wound the
    wrong way fails both. Everything is summed about the mesh's own centre, so a model
    1.37 million feet from the origin loses nothing."""
    if not tris:
        return None
    box = bbox(tris)
    ox, oy, oz = [(box[0][i] + box[1][i]) / 2.0 for i in range(3)]
    sx = sy = sz = 0.0
    vx = vy = vz = 0.0
    total_area = 0.0
    for a, b, c in tris:
        ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
        wx, wy, wz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
        nx = 0.5 * (uy * wz - uz * wy)
        ny = 0.5 * (uz * wx - ux * wz)
        nz = 0.5 * (ux * wy - uy * wx)
        total_area += math.sqrt(nx * nx + ny * ny + nz * nz)
        sx += nx
        sy += ny
        sz += nz
        vx += nx * ((a[0] + b[0] + c[0]) / 3.0 - ox)
        vy += ny * ((a[1] + b[1] + c[1]) / 3.0 - oy)
        vz += nz * ((a[2] + b[2] + c[2]) / 3.0 - oz)
    if total_area <= 0.0:
        return None
    if math.sqrt(sx * sx + sy * sy + sz * sz) > AREA_CLOSURE * total_area:
        return None
    enclosed = (vx + vy + vz) / 3.0
    size = max(box[1][i] - box[0][i] for i in range(3))
    if abs(enclosed) <= max(1e-12, 1e-9 * size ** 3):
        return None
    if max(vx, vy, vz) - min(vx, vy, vz) > AXIS_AGREEMENT * abs(enclosed):
        return None
    centre = solid_centroid(tris)
    if centre is None:
        return None
    return {'volume': abs(enclosed), 'centroid': centre}


# ---- topology -----------------------------------------------------------------


def _key(point, tol):
    if tol <= 0:
        return (point[0], point[1], point[2])
    return (int(round(point[0] / tol)), int(round(point[1] / tol)), int(round(point[2] / tol)))


def weld_tolerance(tris, noise=0.0):
    """The tolerance for welding one mesh's corners: four times the float32 noise the
    triangle walk measured (item_triangles()['noise']), never less than a ten millionth
    of the mesh's own size (for a walk that reported no noise). 0.0 for an empty mesh.
    It scales with the mesh, where a fixed epsilon is too tight far from the origin and
    too loose for a millimetre model."""
    box = bbox(tris)
    size = max(box[1][a] - box[0][a] for a in range(3)) if box else 0.0
    return max(4.0 * float(noise or 0.0), size * 1e-7)


def _tol(tris, tol):
    return weld_tolerance(tris) if tol is None else tol


def weld(tris, tol=None):
    """(vertices, faces): shared corners merged by rounding to a tol grid.

    vertices is a list of (x, y, z) (the first point seen for each grid cell),
    faces a list of (i, j, k) indices. Triangles that collapse when welded (two
    corners in the same cell) are dropped. Points straddling a cell boundary can
    stay apart, so pick tol well above the coordinate noise. tol None (the default)
    is weld_tolerance(tris): give weld_tolerance(tris, noise) when the walk's noise
    is known.
    """
    tol = _tol(tris, tol)
    index_of = {}
    vertices = []
    faces = []
    for tri in tris:
        ids = []
        for point in tri:
            key = _key(point, tol)
            index = index_of.get(key)
            if index is None:
                index = len(vertices)
                index_of[key] = index
                vertices.append((float(point[0]), float(point[1]), float(point[2])))
            ids.append(index)
        if ids[0] != ids[1] and ids[1] != ids[2] and ids[0] != ids[2]:
            faces.append((ids[0], ids[1], ids[2]))
    return vertices, faces


def edge_counts(tris, tol=None):
    """{(i, j): uses} for every undirected welded edge (i < j)."""
    _vertices, faces = weld(tris, tol)
    counts = {}
    for i, j, k in faces:
        for a, b in ((i, j), (j, k), (k, i)):
            edge = (a, b) if a < b else (b, a)
            counts[edge] = counts.get(edge, 0) + 1
    return counts


def is_closed(tris, tol=None):
    """True when every welded edge is shared by exactly two triangles (a watertight,
    manifold surface). An empty mesh is not closed. The TOPOLOGICAL test: a solid whose
    faces do not share vertices fails it; for "does this enclose a volume" use
    solid_measure()."""
    counts = edge_counts(tris, tol)
    if not counts:
        return False
    for uses in counts.values():
        if uses != 2:
            return False
    return True


def open_edges(tris, tol=None):
    """How many welded edges are NOT shared by exactly two triangles."""
    return len([1 for uses in edge_counts(tris, tol).values() if uses != 2])


# ---- transforms ---------------------------------------------------------------


def translate(tris, v):
    """The mesh moved by vector v (a new list; the input is untouched)."""
    dx, dy, dz = float(v[0]), float(v[1]), float(v[2])
    return [tuple((p[0] + dx, p[1] + dy, p[2] + dz) for p in tri) for tri in tris]


def summary(tris, tol=None):
    """{'triangles', 'area', 'volume', 'closed', 'centroid', 'bbox', 'welded'} in one
    go: what a takeoff row needs.

    'closed' and 'volume' follow the GEOMETRIC test (solid_measure): a watertight solid
    counts whether or not its faces share vertices, and a mesh with a face wound the
    wrong way does not, even when its edges all pair up (its signed volume would be
    wrong). volume is None for anything else, so nobody reports a number that means
    nothing. 'welded' is the topological is_closed(tris, tol) for callers that need a
    manifold; tol None is weld_tolerance(tris)."""
    solid = solid_measure(tris)
    return {
        'triangles': len(tris),
        'area': area(tris),
        'volume': solid['volume'] if solid is not None else None,
        'closed': solid is not None,
        'centroid': solid['centroid'] if solid is not None else area_centroid(tris),
        'bbox': bbox(tris),
        'welded': is_closed(tris, tol),
    }


# ---- API half -----------------------------------------------------------------


def item_triangles(item, budget=200000):
    """{'tris': [...], 'note': str or None, 'noise': float} for one ModelItem.

    Wraps pynavis.geometry.world_triangles: the item and its geometry-carrying
    descendants in world coordinates. IronPython only (the COM callback subclasses
    a COM interface). An empty 'tris' means UNKNOWN, never "no faces": 'note' then
    says why (over budget, no geometry, COM walk produced nothing, no matrix layout
    fits). 'noise' is how far the float32 coordinates can be off, in model units:
    use it (times a few) as the weld/closure tolerance.
    """
    notes = []
    stats = {}
    try:
        from pynavis import geometry
        tris = geometry.world_triangles(item, budget=budget, note=notes.append, stats=stats)
    except Exception as error:
        return {'tris': [], 'note': 'triangle walk failed: %s' % error, 'noise': 0.0}
    note = '; '.join(notes) if notes else None
    if not tris and note is None:
        note = 'no triangles'
    return {'tris': list(tris), 'note': note, 'noise': float(stats.get('noise', 0.0))}
