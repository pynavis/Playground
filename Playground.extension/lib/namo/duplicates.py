# -*- coding: utf-8 -*-
"""Duplicate Finder: element-level objects that are the same thing in the same place.

Pure half (unit tested): group_duplicates() finds groups of entries whose class and
primitive count are equal and whose six bounding-box coordinates are all within a
tolerance of each other, with a spatial hash that is exact even when a pair straddles
a cell boundary; classify() tells same-model from across-model groups; refine() splits
groups by mesh volume and centroid (the optional deep check); extras() picks every
copy but the first.

Why the hash is exact: entries are bucketed by (class, primitives, floor(centre /
cell)) with cell = 4 x tolerance. Two duplicates have centres within tolerance on
every axis, so where their cells differ on an axis, the later one sits within
tolerance of that cell boundary. Each entry is compared against the earlier entries
in its own cell AND, on every axis where it is that close to a boundary, the
neighbouring cell. Usually that is one bucket lookup per entry.

API half: collect() walks the geometry leaves under the scope once, sums each
object's PrimitiveCount and reads each object's box; deep_props() reads triangles
through namo.mesh (IronPython only, slow, budgeted).
"""

import math

import struct

DEFAULTS = {'tolerance_m': 0.001, 'scope': 'selection', 'deep': False, 'select': True,
            'make_set': True}
OBJECT_BUDGET = 200000
DEEP_GROUP_BUDGET = 300
SET_FOLDER = 'Playground'
FLOAT32_STEP = 2.0 ** -23       # one float32 step per unit of coordinate size
FLOAT64_STEP = 2.0 ** -52
PRECISION_SAMPLE = 400


# ---- pure: how precise the boxes are ----------------------------------------------------
#
# A federated model can sit a long way from the origin (shared coordinates: 1.37
# million feet in the field). Nothing here assumes coordinates are small: the smallest
# tolerance that means anything is worked out from the boxes themselves.


def _is_single(value):
    """True when a double is exactly a float32 value (it survives the round trip)."""
    try:
        return struct.unpack('f', struct.pack('f', value))[0] == value
    except (OverflowError, struct.error):
        return False


def box_precision(entries, sample=PRECISION_SAMPLE):
    """{'reach', 'single', 'noise'} for entries [(id, class, primitives, box, model)].

    reach: the largest coordinate. single: True when the boxes are float32 values (every
    sampled coordinate that is not a whole number survives a float32 round trip), which
    far from the origin makes them coarse: 1/8 ft at 1.37 million feet. noise: how far
    apart the boxes of two objects in exactly the same place can then read, two float32
    steps at that reach; for double precision boxes, a few float64 steps (nothing)."""
    reach = 0.0
    usable = [e[3] for e in entries if e[3] is not None]
    for box in usable:
        for corner in box:
            for value in corner:
                if abs(value) > reach:
                    reach = abs(value)
    step = max(1, len(usable) // max(1, int(sample)))
    checked = 0
    single = True
    for box in usable[::step]:
        for corner in box:
            for value in corner:
                if value == int(value):
                    continue                    # whole numbers prove nothing
                checked += 1
                if not _is_single(value):
                    single = False
                    break
            if not single:
                break
        if not single:
            break
    single = single and checked >= 12
    scale = max(reach, 1.0)
    noise = scale * (2.0 * FLOAT32_STEP if single else 8.0 * FLOAT64_STEP)
    return {'reach': reach, 'single': single, 'noise': noise}


def effective_tolerance(tol, precision):
    """(tolerance to search with, widened): the asked tolerance, raised to the boxes'
    own noise when that is larger (asking for 1 mm of boxes stored to 1/8 ft)."""
    noise = float((precision or {}).get('noise') or 0.0)
    tol = abs(float(tol))
    if noise > tol:
        return noise, True
    return tol, False


def default_tolerance(tolerance_m, doc_units, denominator=16):
    """The tolerance the form opens with, in document units. In a feet-and-inches
    document the box shows lengths to the nearest 1/16 in, so the saved tolerance is
    rounded UP to that grid (1 mm becomes 1/16 in): a prefill that reads back as zero
    would be refused by the form's own check."""
    from namo import units
    value = units.from_meters(abs(float(tolerance_m)), doc_units)
    if not units.is_imperial(doc_units):
        return value
    tick = units.from_meters(0.0254, doc_units) / float(denominator)
    ticks = int(math.ceil(value / tick - 1e-9))
    return max(1, ticks) * tick


def kept_tolerance_m(answer, prefill, saved_m, doc_units):
    """The tolerance to remember, in metres: the saved one when the prefill was left
    alone (so 1 mm does not drift to 1/16 in by passing through a feet document), else
    what was typed."""
    from namo import units
    if abs(float(answer) - float(prefill)) <= abs(float(prefill)) * 1e-6:
        return float(saved_m)
    return units.to_meters(float(answer), doc_units)


class UnionFind(object):
    """Disjoint sets over 0..n-1 with path halving and union by size."""

    def __init__(self, count):
        self.parent = list(range(count))
        self.size = [1] * count

    def find(self, index):
        parent = self.parent
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return ra
        if self.size[ra] < self.size[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        self.size[ra] += self.size[rb]
        return ra


def boxes_match(a, b, tol):
    """True when all six coordinates of two boxes are within tol."""
    for corner in (0, 1):
        pa, pb = a[corner], b[corner]
        if abs(pa[0] - pb[0]) > tol or abs(pa[1] - pb[1]) > tol or abs(pa[2] - pb[2]) > tol:
            return False
    return True


def _axis_options(value, cell, tol):
    base = int(math.floor(value / cell))
    options = [base]
    if value - base * cell <= tol:
        options.append(base - 1)
    if (base + 1) * cell - value <= tol:
        options.append(base + 1)
    return base, options


def group_duplicates(entries, tol):
    """Groups of duplicate entries, as lists of entry ids.

    entries: [(id, class_name, primitives, ((x0, y0, z0), (x1, y1, z1)), model), ...];
    entries without a box are ignored. A pair is a duplicate when the class and the
    primitive count are equal and every box coordinate is within tol. Matches chain
    (union-find), so a group holds everything connected by matches. Groups keep entry
    order inside and are ordered by their first entry; only groups of two or more."""
    usable = [e for e in entries if e[3] is not None]
    reach = 1.0
    for entry in usable:
        for corner in entry[3]:
            for value in corner:
                if abs(value) > reach:
                    reach = abs(value)
    # Rounding slack: a few float64 steps at the largest coordinate, so two boxes
    # exactly tol apart far from the origin are not split by the subtraction itself.
    eps = reach * 8.0 * FLOAT64_STEP
    tol = max(abs(float(tol)), eps)
    cell = 4.0 * tol
    finder = UnionFind(len(usable))
    buckets = {}
    for index, entry in enumerate(usable):
        box = entry[3]
        center = [(box[0][a] + box[1][a]) / 2.0 for a in range(3)]
        bx, ox = _axis_options(center[0], cell, tol + eps)
        by, oy = _axis_options(center[1], cell, tol + eps)
        bz, oz = _axis_options(center[2], cell, tol + eps)
        head = (entry[1], entry[2])
        for cx in ox:
            for cy in oy:
                for cz in oz:
                    found = buckets.get(head + (cx, cy, cz))
                    if not found:
                        continue
                    for other in found:
                        if boxes_match(box, usable[other][3], tol + eps):
                            finder.union(index, other)
        buckets.setdefault(head + (bx, by, bz), []).append(index)
    members = {}
    order = []
    for index in range(len(usable)):
        root = finder.find(index)
        if root not in members:
            members[root] = []
            order.append(root)
        members[root].append(index)
    groups = []
    for root in order:
        group = members[root]
        if len(group) > 1:
            groups.append([usable[i][0] for i in group])
    return groups


def classify(group, model_of):
    """'Same model' when every id in the group is in one model, else 'Across models'.
    model_of(id) -> model index."""
    models = set(model_of(i) for i in group)
    return 'Same model' if len(models) <= 1 else 'Across models'


def extras(groups):
    """Every id except the first of each group, in group order."""
    out = []
    for group in groups:
        out.extend(group[1:])
    return out


def _close(a, b, tol):
    return abs(float(a) - float(b)) <= tol


def refine(groups, props, tol, volume_tol=0.02):
    """Splits groups whose members differ in mesh volume or centroid.

    props: {id: (volume or None, centroid (x, y, z) or None)}; a member with unknown
    props cannot be told apart and stays with the first member. Two members agree
    when their volumes are within volume_tol (2 %) of the larger and their centroids
    within tol on every axis. Returns the new groups (two or more members only)."""
    out = []
    for group in groups:
        clusters = []
        for member in group:
            volume, centroid = props.get(member, (None, None))
            placed = False
            for cluster in clusters:
                ref_volume, ref_centroid = props.get(cluster[0], (None, None))
                if volume is None or ref_volume is None:
                    same_volume = True
                else:
                    big = max(abs(volume), abs(ref_volume), 1e-30)
                    same_volume = abs(volume - ref_volume) <= volume_tol * big
                if centroid is None or ref_centroid is None:
                    same_centroid = True
                else:
                    same_centroid = all(_close(centroid[a], ref_centroid[a], tol) for a in range(3))
                if same_volume and same_centroid:
                    cluster.append(member)
                    placed = True
                    break
            if not placed:
                clusters.append([member])
        out.extend(c for c in clusters if len(c) > 1)
    return out


def summary(groups, objects_checked, tol_text, sampled=False):
    """(level, message, detail) for the toast."""
    copies = sum(len(g) - 1 for g in groups)
    checked = '{:,}'.format(objects_checked)
    if not groups:
        detail = 'Checked %s objects at %s.' % (checked, tol_text)
        if sampled:
            detail = 'Checked the first %s objects at %s (the budget stopped the search).' % (
                checked, tol_text)
        return ('info', 'No duplicates found', detail)
    message = 'Found %s duplicate%s in %s group%s' % (
        '{:,}'.format(copies), '' if copies == 1 else 's',
        '{:,}'.format(len(groups)), '' if len(groups) == 1 else 's')
    detail = '%s objects checked at %s.' % (checked, tol_text)
    if sampled:
        detail = 'Sampled: only the first %s objects were checked, at %s.' % (checked, tol_text)
    return ('warning', message, detail)


def tolerance_text(meters, imperial=False):
    """'1 mm', '0.5 mm', '2.5 cm' (metric), or '1/16 in', '1 1/2 in', '0.039 in'
    (imperial: a fraction when it is one to the 1/64 in) for a tolerance."""
    meters = abs(float(meters))
    if imperial:
        inches = meters / 0.0254
        ticks = int(round(inches * 64.0))
        if ticks > 0 and abs(inches * 64.0 - ticks) < 1e-6:
            whole, rest = ticks // 64, ticks % 64
            den = 64
            while rest and rest % 2 == 0:
                rest, den = rest // 2, den // 2
            parts = ([str(whole)] if whole else []) + (['%d/%d' % (rest, den)] if rest else [])
            return '%s in' % ' '.join(parts)
        return '%s in' % ('%.3g' % inches)
    if meters < 0.01:
        return '%s mm' % ('%.3g' % (meters * 1000.0))
    if meters < 1.0:
        return '%s cm' % ('%.3g' % (meters * 100.0))
    return '%s m' % ('%.3g' % meters)


def set_name(now):
    """'Duplicates 2026-10-05 1430' for a datetime."""
    return 'Duplicates %s' % now.strftime('%Y-%m-%d %H%M')


# ---- API half ---------------------------------------------------------------------------


def _doc(doc):
    if doc is not None:
        return doc
    from pynavis._api import Application
    return Application.ActiveDocument


def _model_index(document, item):
    try:
        return int(document.Models.CreatePathId(item).ModelIndex)
    except Exception:
        return -1


def collect(scope_roots, doc=None, budget=OBJECT_BUDGET, progress=None):
    """Element-level objects under the scope roots.

    Returns {'entries': [(id, class, primitives, box, model)], 'objects': [ModelItem]
    (entry id = index), 'sampled': bool, 'leaves': int}. progress(fraction, label) may
    raise a Cancelled. Geometry leaves reached from two overlapping roots count once."""
    from namo import items as _items
    document = _doc(doc)
    roots = _items.as_list(scope_roots)
    prims = {}
    order = []
    model_of = {}
    seen_leaves = set() if len(roots) > 1 else None
    leaves = 0
    sampled = False
    total = max(1, len(roots))
    for number, root in enumerate(roots):
        root_model = _model_index(document, root)
        if progress is not None:
            progress(0.8 * number / total, 'Reading %s objects' % '{:,}'.format(len(order)))
        for leaf in root.DescendantsAndSelf:
            if not leaf.HasGeometry:
                continue
            if seen_leaves is not None:
                if leaf in seen_leaves:
                    continue
                seen_leaves.add(leaf)
            leaves += 1
            obj = _items.object_of(leaf)
            try:
                count = int(leaf.Geometry.PrimitiveCount)
            except Exception:
                count = 0
            if obj in prims:
                prims[obj] += count
            else:
                if len(order) >= budget:
                    sampled = True
                    break
                prims[obj] = count
                order.append(obj)
                model_of[obj] = root_model
            if progress is not None and leaves % 2000 == 0:
                progress(0.8 * (number + 0.5) / total, 'Reading %s objects' % '{:,}'.format(len(order)))
        if sampled:
            break
    entries = []
    for index, obj in enumerate(order):
        if progress is not None and index % 2000 == 0:
            progress(0.8 + 0.2 * index / max(1, len(order)),
                     'Measuring %s of %s objects' % ('{:,}'.format(index), '{:,}'.format(len(order))))
        try:
            box = _items.bbox(obj)
        except Exception:
            box = None
        try:
            name = obj.ClassDisplayName or obj.ClassName or ''
        except Exception:
            name = ''
        entries.append((index, name, prims[obj], box, model_of[obj]))
    return {'entries': entries, 'objects': order, 'sampled': sampled, 'leaves': leaves}


def weld_tolerance(tris, noise):
    """The tolerance for welding one object's triangles: four times the float32 noise
    the triangle walk measured (pynavis.geometry.float_noise), never less than a ten
    millionth of the object's own size (for a walk that reported no noise)."""
    from namo import mesh
    return mesh.weld_tolerance(tris, noise)


def deep_props(groups, objects, progress=None, budget=DEEP_GROUP_BUDGET, stats=None):
    """{id: (volume or None, centroid or None)} from each member's triangles
    (namo.mesh.item_triangles: IronPython only). Only the first `budget` groups are
    read; the rest keep their box match. Returns (props, groups_read). stats, a dict,
    gets 'noise': the largest float32 noise of any member's triangles, which the
    centroid comparison must allow for."""
    from namo import mesh
    props = {}
    worst = 0.0
    read = groups[:budget]
    for number, group in enumerate(read):
        if progress is not None:
            progress(float(number) / max(1, len(read)),
                     'Comparing shapes in group %d of %d' % (number + 1, len(read)))
        for member in group:
            data = mesh.item_triangles(objects[member])
            tris = data['tris']
            if not tris:
                props[member] = (None, None)
                continue
            noise = float(data.get('noise') or 0.0)
            worst = max(worst, noise)
            info = mesh.summary(tris, weld_tolerance(tris, noise))
            props[member] = (info['volume'], info['centroid'])
    if stats is not None:
        stats['noise'] = worst
    return props, len(read)


def make_set(item_list, name, doc=None):
    """A static selection set `name` in the Playground folder holding item_list. Returns
    the path shown to users ('Playground/<final name>')."""
    from pynavis import sets
    created = sets.create(name, item_list, folder=SET_FOLDER, doc=_doc(doc))
    try:
        final = created.DisplayName
    except Exception:
        final = name
    return '%s/%s' % (SET_FOLDER, final)
