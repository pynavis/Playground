# -*- coding: utf-8 -*-
"""Property Labels: a property's value drawn above each selected object in the 3D view
through pynavis.overlay, with a short leader from the object's top-centre.

Each label is its own overlay item (overlay.add replaces items that share a tag), all
tagged 'playground-labels:<n>'; the tags live on the session holder 'property-labels' so
Clear Labels removes exactly them (with a sweep of the overlay registry for any label
tag as a fallback).

Pure (tested): label_anchor() and leader_length() geometry, label_text().
"""

TAG_PREFIX = 'playground-labels:'
HOLDER = 'property-labels'
MAX_LABELS = 500
LEADER_SHARE = 0.03          # leader length as a share of the selection's box diagonal...
MIN_LEADER_M = 0.15          # ...kept between these real-world lengths (metres), so a leader
MAX_LEADER_M = 1.5           # reads the same in a model drawn in feet or in millimetres
MAX_TEXT = 60


def leader_length(box, meters_per_unit=1.0):
    """How long the leaders are, in model units, for a selection box: 3% of its
    diagonal, kept between MIN_LEADER_M and MAX_LEADER_M of real length so one small
    object still gets a visible stub and a whole building does not get 10 m masts.
    meters_per_unit: metres per model unit (0.3048 for a model in feet)."""
    if box is None:
        return 0.0
    scale = float(meters_per_unit or 1.0)
    dx, dy, dz = [box[1][i] - box[0][i] for i in range(3)]
    diagonal = (dx * dx + dy * dy + dz * dz) ** 0.5
    return min(max(diagonal * LEADER_SHARE, MIN_LEADER_M / scale), MAX_LEADER_M / scale)


def meters_per_unit(doc=None):
    """Metres per model unit of the document (1.0 when its units cannot be read)."""
    try:
        from namo import units
        if doc is None:
            from pynavis._api import Application
            doc = Application.ActiveDocument
        return float(units.to_meters(1.0, str(doc.Units)))
    except Exception:
        return 1.0


def label_anchor(box, leader):
    """(top-centre, label point) for an object's box: the leader rises straight up
    from the centre of the box top."""
    cx = (box[0][0] + box[1][0]) / 2.0
    cy = (box[0][1] + box[1][1]) / 2.0
    top = box[1][2]
    return (cx, cy, top), (cx, cy, top + leader)


def label_text(text):
    """The value as drawn: one line, at most MAX_TEXT characters."""
    flat = ' '.join(str(text or '').split())
    if len(flat) > MAX_TEXT:
        return flat[:MAX_TEXT - 3] + '...'
    return flat


def _holder():
    from namo import session
    return session.holder(HOLDER)


def tags():
    return list(getattr(_holder(), 'tags', None) or [])


def clear():
    """Removes every Property Labels label. Returns how many were removed."""
    from pynavis import overlay
    removed = set(tags())
    try:
        from PyNavis.Runtime.Overlay import OverlayRegistry
        for item in OverlayRegistry.Items:
            tag = str(item.Tag or '')
            if tag.startswith(TAG_PREFIX):
                removed.add(tag)
    except Exception:
        pass
    for tag in sorted(removed):
        overlay.clear(tag)
    _overlay_redraw()
    _holder().tags = []
    return len(removed)


def draw(labels, doc=None):
    """Draws [(box, text)] (boxes in model units), replacing the labels of the last
    run. Returns (drawn, overlay_loaded); nothing is left behind when the overlay
    plugin is not loaded."""
    from pynavis import overlay
    from namo import items
    clear()
    if not labels:
        return 0, True
    leader = leader_length(items.union_boxes(box for box, _text in labels), meters_per_unit(doc))
    drawn = []
    loaded = True
    for index, (box, text) in enumerate(labels):
        start, end = label_anchor(box, leader)
        tag = '%s%d' % (TAG_PREFIX, index + 1)
        ok = overlay.add(tag, [(start, end, False)], label=label_text(text), label_at=end)
        drawn.append(tag)
        if not ok:
            loaded = False
            break
    if not loaded:
        for tag in drawn:
            overlay.clear(tag)
        _holder().tags = []
        return 0, False
    _overlay_redraw()
    _holder().tags = drawn
    return len(drawn), True


def _overlay_redraw():
    """Redraws the overlay through namo.overlayfix, so labels land on their points."""
    from namo import overlayfix
    return overlayfix.redraw()
