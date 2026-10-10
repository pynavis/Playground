# -*- coding: utf-8 -*-
"""namo.pins: the one pin glyph Photo Pins and Issue Pins share."""
import _compat

from namo import pins


def _extent(points, axis):
    return max(p[axis] for p in points) - min(p[axis] for p in points)


def test_marker_is_centred_on_the_point():
    # Field: a head on a stem a metre above the click read as a pin somewhere else.
    pin = pins.segments((0, 0, 0), 1.0)
    assert len(pin) == pins.SEGMENT_COUNT == 15
    assert all(dashed is False for _a, _b, dashed in pin)
    head = [p for a, b, _d in pins.head_segments(pin) for p in (a, b)]
    for axis in range(3):
        assert _compat.approx(max(p[axis] for p in head), 0.2)
        assert _compat.approx(min(p[axis] for p in head), -0.2)
    strokes = [pin[0]] + pin[13:]
    for a, b, _d in strokes:                        # each centre stroke crosses the point
        assert all(_compat.approx((a[i] + b[i]) / 2.0, 0.0) for i in range(3))
    assert pins.top((1, 2, 3), 1.0) == (1.0, 2.0, 3.2)


def test_head_reads_from_every_side_and_in_plan():
    pin = pins.segments((0, 0, 0), 1.0)
    head = pins.head_segments(pin)
    points = [p for a, b, _d in head for p in (a, b)]
    for a, b in ((1, 2), (0, 2), (0, 1)):           # looking along X, along Y, straight down
        assert _extent(points, a) > 0.3 and _extent(points, b) > 0.3
        outline = [s for s in head if abs(s[0][a] - s[1][a]) > 1e-9 and abs(s[0][b] - s[1][b]) > 1e-9]
        assert len(outline) >= 4                    # a closed outline, never a single stroke


def test_far_from_the_origin_it_is_the_same_pin_moved():
    far = (1370000.25, -1370000.75, 312.5)
    near, moved = pins.segments((0, 0, 0), 3.28), pins.segments(far, 3.28)
    for (a0, a1, _), (b0, b1, _) in zip(near, moved):
        for p, q in ((a0, b0), (a1, b1)):
            for axis in range(3):
                assert abs((q[axis] - far[axis]) - p[axis]) < 1e-6


def test_zero_or_negative_height_still_draws():
    assert len(pins.segments((0, 0, 0), 0)) == 15
    assert pins.segments((0, 0, 0), -2.0) == pins.segments((0, 0, 0), 2.0)
    assert pins.top((0, 0, 0), 0) == (0.0, 0.0, 0.2)


def test_photo_and_issue_pins_are_one_family():
    from namo import issues, photopins
    assert photopins.pin_segments((5, 6, 7), 2.0) == pins.segments((5, 6, 7), 2.0)
    assert photopins.pin_label_point((5, 6, 7), 2.0) == pins.top((5, 6, 7), 2.0)
    assert issues.pin_segments((5, 6, 7), 2.0) == pins.segments((5, 6, 7), 2.0 * issues.PIN_HEAD_ABOVE)
