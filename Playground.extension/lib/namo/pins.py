# -*- coding: utf-8 -*-
"""The one pin glyph Playground draws in the view (Photo Pins, Issue Pins).

A pin is overlay line segments for pynavis.overlay.add: an octahedron outline CENTRED
ON the picked point, with a short stroke along each axis crossing at the point itself.
The overlay draws through geometry with no depth cue, so anything standing off the
point (a stem with a head a metre up, as this glyph first was) reads as a pin somewhere
else: in the field the head looked unconnected to the face that was clicked. A marker
whose centre IS the point cannot be misread from any camera angle, and the octahedron
(a diamond in each vertical plane and a square in plan) is never seen edge on.

Sizes are model units and are the caller's business (a real-world size converted with
the document's units, never a share of the model's extents). The shape is built by
adding small offsets to the point, so a pin 1.37 million feet from the origin is the
pin at the origin, moved.

Colour, label text and tags stay with each tool: this module is only the shape, so
the two kinds of pin read as one family. Pure.
"""

HEAD_RATIO = 0.2        # marker radius as a share of the caller's pin size
FOOT_RATIO = 0.5        # centre stroke half-length as a share of the marker radius
SEGMENT_COUNT = 15      # 1 vertical centre stroke, 12 head edges, 2 level centre strokes


def radius(height):
    """The marker's radius for a pin size (a zero size draws a pin of size one)."""
    return (abs(float(height)) or 1.0) * HEAD_RATIO


def segments(point, height):
    """[(start, end, dashed)] for one pin centred on point; `height` is the pin's size
    in model units and the marker's radius is HEAD_RATIO of it. Order: the vertical
    centre stroke, the head's four plan edges, its eight sloping edges, the two level
    centre strokes. The three centre strokes cross exactly on the point."""
    x, y, z = float(point[0]), float(point[1]), float(point[2])
    r = radius(height)
    east, west = (x + r, y, z), (x - r, y, z)
    north, south = (x, y + r, z), (x, y - r, z)
    top_, bottom = (x, y, z + r), (x, y, z - r)
    mark = r * FOOT_RATIO
    out = [((x, y, z - mark), (x, y, z + mark), False)]
    for a, b in ((east, north), (north, west), (west, south), (south, east)):
        out.append((a, b, False))
    for corner in (east, north, west, south):
        out.append((corner, top_, False))
        out.append((corner, bottom, False))
    out.append(((x - mark, y, z), (x + mark, y, z), False))
    out.append(((x, y - mark, z), (x, y + mark, z), False))
    return out


def top(point, height):
    """The top of the marker: where a label is anchored, so it sits on the pin."""
    return (float(point[0]), float(point[1]), float(point[2]) + radius(height))


def head_segments(pin):
    """The twelve head edges of a segments() list (for tests and hit boxes)."""
    return pin[1:13]
