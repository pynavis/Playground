# -*- coding: utf-8 -*-
"""The one way a Playground tool asks for a click in the 3D view.

    from namo import picking

    hit = picking.point('Click where the photos were taken', want_item=True)
    if hit is None:
        return                      # Esc, right-click or another tool: say nothing
    x, y, z = hit.point             # floats, model units
    hit.item                        # the ModelItem under the point, or None

The click runs on the host's own Measure tool (pynavis.pick.measure_point), the
way every shipped pyNavis tool that picks does (Get Coordinates, True Distance,
Clear Clash): the marker under the pointer, the snapping and the cursors are
Navisworks' own, so the point that comes back is the one the user saw
highlighted. pynavis.pick.point (the custom pick tool) is not used anywhere in
Playground: its hover marker and its hit can disagree in the field.

The prompt sits on the banner along the bottom of the window for as long as the
pick runs and is cleared when it ends, whatever the outcome; the caller reports
the result its own way (a toast, or the banner again).

A measurement carries only a point, so with want_item the object is found the
way True Distance finds its faces: the point is projected back to its pixel and
the front-most item there is taken (pynavis.faces.candidates_at). hit.normal and
hit.snap are always None.
"""


class Hit(object):
    """One picked point. point is a 3-tuple of floats in model units."""

    def __init__(self, point, item=None):
        self.point = point
        self.item = item
        self.normal = None
        self.snap = None

    def __repr__(self):
        return 'Hit(point=%r, item=%s)' % (self.point, 'yes' if self.item is not None else 'no')


def _refuse_under_runner():
    """A pick needs the Navisworks window. pynavis.pick.measure_point has no runner check:
    under `pynavis run` it would switch to the Measure tool and wait for a click in a
    hidden window until the run timed out. Raise the runner's dialog refusal instead."""
    from namo import ui
    if ui.is_runner():
        raise RuntimeError(ui.RUNNER_MESSAGE)


def point(prompt, want_item=False, doc=None):
    """Blocks until the user clicks a point; returns a Hit, or None on cancel. Raises
    RuntimeError under `pynavis run`."""
    _refuse_under_runner()
    from pynavis import banner, pick
    banner.clear()
    try:
        measured = pick.measure_point(prompt, notify=banner.prompt)
    finally:
        banner.clear()
    if measured is None:
        return None
    xyz = measured.point
    return Hit(xyz, item_at(xyz, doc) if want_item else None)


def points(prompt, second_prompt, doc=None):
    """Blocks until the user clicks two points (a from/to pair); returns
    (first, second) as 3-tuples, or None on cancel. Nothing is left on screen. Raises
    RuntimeError under `pynavis run`."""
    _refuse_under_runner()
    from pynavis import banner, pick
    banner.clear()
    try:
        measured = pick.measure_points(prompt, second_prompt, notify=banner.prompt, keep=False)
    finally:
        banner.clear()
    return measured


def item_at(xyz, doc=None):
    """The front-most ModelItem at a world point, or None. Never raises."""
    try:
        from pynavis import app, faces, script
        from pynavis._api import Api
        document = doc if doc is not None else app.get_doc()
        found = faces.candidates_at(document.ActiveView,
                                    Api.Point3D(float(xyz[0]), float(xyz[1]), float(xyz[2])),
                                    script.get_logger(), 'pick')
        return found[0] if found else None
    except Exception:
        return None
