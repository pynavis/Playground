# -*- coding: utf-8 -*-
"""Keeps pynavis.overlay labels on their points, whichever way up the view counts pixels.

pyNavis' overlay places a label by projecting its point (View.ProjectPoint) and then
flipping Y, on the assumption that ProjectPoint counts rows from the top while the
drawing context counts from the bottom (OverlayRegistry.FlipY, a field its own comment
says exists in case a field check finds labels mirrored). In the owner's Navisworks
ProjectPoint counted from the BOTTOM: a pin clicked low in the view got its label the
same distance from the top (measured from a screenshot: point at row 720 of 859, label
at row 140, columns identical).

Rather than hard-code the other answer, calibrate() asks the view: a point a little
above the camera's line of sight must project above the centre of the view. If
ProjectPoint gives it a larger Y than the centre point, rows are counted from the
bottom, the same way the drawing context counts them, and no flip is wanted.

redraw() is overlay.redraw() with that check first; every Playground tool that draws in the
view ends in it. Pure half: rows_from_top().
"""

PROBE_DISTANCE_M = 10.0     # how far along the line of sight the two probe points sit
PROBE_RISE = 0.1            # the upper probe is this share of the distance above the axis


def rows_from_top(centre_y, above_y):
    """True when a point above the line of sight got the SMALLER row number, i.e. rows
    are counted from the top; False when from the bottom; None when the two rows are
    the same (nothing can be told)."""
    try:
        centre, above = float(centre_y), float(above_y)
    except (TypeError, ValueError):
        return None
    if abs(centre - above) < 1.0:
        return None
    return above < centre


def probe_points(position, direction, up, distance):
    """(centre, above): a point on the line of sight and one a little above it."""
    centre = tuple(float(position[i]) + float(direction[i]) * distance for i in range(3))
    above = tuple(centre[i] + float(up[i]) * distance * PROBE_RISE for i in range(3))
    return centre, above


def calibrate(doc=None):
    """Sets pyNavis' OverlayRegistry.FlipY to match the active view. Returns True (rows
    from the top, flip), False (rows from the bottom, no flip) or None when nothing
    could be told, in which case the field is left alone. Never raises."""
    try:
        from pynavis import app, overlay, script
        from pynavis._api import Api
        from namo import camera, units
        document = doc if doc is not None else app.get_doc()
        if document is None or document.IsClear:
            return None         # a document being closed: leave its view alone
        cam = camera.capture(document)
        try:
            distance = PROBE_DISTANCE_M / units.to_meters(1.0, str(document.Units))
        except Exception:
            distance = PROBE_DISTANCE_M
        centre, above = probe_points(cam['position'], cam['direction'], cam['up'], distance)
        view = document.ActiveView
        shot_centre = view.ProjectPoint(Api.Point3D(centre[0], centre[1], centre[2]), False, False)
        shot_above = view.ProjectPoint(Api.Point3D(above[0], above[1], above[2]), False, False)
        answer = rows_from_top(shot_centre.Y, shot_above.Y)
        registry = overlay.OverlayRegistry
        before = bool(registry.FlipY)
        if answer is not None and answer != before:
            registry.FlipY = answer
        try:
            script.get_logger().info('overlay rows: centre y %s, above y %s, flip %s -> %s, %s item(s)' % (
                shot_centre.Y, shot_above.Y, before, registry.FlipY, registry.Count))
        except Exception:
            pass
        return answer
    except Exception:
        return None


def redraw(doc=None):
    """overlay.redraw() after making sure labels will land on their points."""
    from pynavis import overlay
    calibrate(doc)
    return overlay.redraw()
