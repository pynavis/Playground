# -*- coding: utf-8 -*-
"""The Navisworks half of the issue tools: capture a view as issue material, go back to
it, draw issue pins, pick stamp points, and find BCF components in the model.

Every function takes doc=None (the active document) and lazy-imports pynavis, so
`import namo.issueapi` works anywhere; only calling needs Navisworks. Pure decisions
(sizes, labels, segments, filters) live in namo.issues and are unit tested there.

API members used (all grepped in the 2026 dump, see dev/notes/issues_bcf.md):
Document.ActiveView.Width/Height, Document.Units, Document.Grids.ActiveSystem
.ClosestIntersection(Point3D) -> GridIntersection.DisplayName/.Level.DisplayName,
Document.CurrentSelection, ModelItem.BoundingBox(), Document.GenerateImage (through
namo.images), Viewpoint (through namo.camera), Search (through pynavis.sets).
"""

import os
import tempfile
import time

TAG_PREFIX = 'playground-issues:'
PINS = 'issuepins'
ELEMENT_LIMIT = 200
SCAN_LIMIT = 5000
SNAPSHOT_LONG_SIDE = 1280
SNAPSHOT_QUALITY = 88
ELEMENT_CATEGORY = 'LcRevitData_Element'


def _doc(doc):
    if doc is not None:
        return doc
    from pynavis._api import Application
    return Application.ActiveDocument


def doc_units(doc=None):
    """str(doc.Units): 'Feet', 'Millimeters'... ('' when unreadable)."""
    try:
        return str(_doc(doc).Units)
    except Exception:
        return ''


def unit_to_m(doc=None, units_name=None):
    """Metres per document unit (1.0 when unknown)."""
    from namo import units
    try:
        return units.to_meters(1.0, units_name or doc_units(doc))
    except Exception:
        return 1.0


def has_model(doc=None):
    """True when the document has at least one model appended."""
    try:
        return _doc(doc).Models.Count > 0
    except Exception:
        return False


def temp_path(ext='.jpg', stem='issue'):
    """A fresh file path under %TEMP%\\Playground (folder created)."""
    folder = os.path.join(tempfile.gettempdir(), 'Playground')
    if not os.path.isdir(folder):
        os.makedirs(folder)
    return os.path.join(folder, '%s-%d-%d%s' % (stem, int(time.time() * 1000), os.getpid(), ext))


# ---- elements and locations ------------------------------------------------------------


def element_record(item, doc=None):
    """One issue element: {'entry', 'name', 'model', 'category', 'element_id',
    'unique_id', 'ifc_guid', 'ifc_guid_derived'}."""
    from namo import items
    document = _doc(doc)
    entries = items.entries([item], document)
    try:
        ids = items.revit_ids(item) or {}
    except Exception:
        ids = {}
    try:
        name = item.DisplayName or item.ClassDisplayName or ''
    except Exception:
        name = ''
    return {'entry': entries[0] if entries else None, 'name': name,
            'model': items.model_name(item), 'category': items.category(item),
            'element_id': ids.get('element_id'), 'unique_id': ids.get('unique_id'),
            'ifc_guid': ids.get('ifc_guid'), 'ifc_guid_derived': bool(ids.get('ifc_guid_derived'))}


def elements_of(model_items, doc=None, limit=ELEMENT_LIMIT, scan=SCAN_LIMIT):
    """(element records, objects, total) for items: each item becomes its element
    (object ancestor), duplicates dropped, at most `limit` recorded. Only the first
    `scan` items are looked at (a selection of a whole model stays quick); total is then
    the number of selected items rather than of distinct elements."""
    from namo import items
    chosen = items.as_list(model_items)
    objects = []
    seen = set()
    for item in chosen[:scan]:
        element = items.object_of(item)
        if element in seen:
            continue
        seen.add(element)
        objects.append(element)
        if len(objects) >= limit and len(chosen) > scan:
            break
    total = len(objects) if len(chosen) <= scan else len(chosen)
    kept = objects[:limit]
    return [element_record(o, doc) for o in kept], kept, total


def location_labels(point, doc=None):
    """(level, grid) at a point from the active grid system; ('', '') without one."""
    try:
        from pynavis._api import Api
        system = _doc(doc).Grids.ActiveSystem
        if system is None:
            return '', ''
        hit = system.ClosestIntersection(Api.Point3D(float(point[0]), float(point[1]),
                                                     float(point[2])))
        if hit is None:
            return '', ''
        level = ''
        try:
            level = str(hit.Level.DisplayName) if hit.Level is not None else ''
        except Exception:
            level = ''
        return level, str(hit.DisplayName or '')
    except Exception:
        return '', ''


def location_of(point, doc=None):
    """{'point', 'units', 'level', 'grid'} for a point in document units."""
    level, grid = location_labels(point, doc)
    return {'point': [float(point[0]), float(point[1]), float(point[2])],
            'units': doc_units(doc), 'level': level, 'grid': grid}


def centre_of(model_items):
    """Centre of the items' joint box (document units), or None."""
    from namo import items
    box = items.bbox(model_items)
    return items.box_center(box) if box is not None else None


def trade_of_item(item):
    """The trade of the item's model (namo.trades with the configured rules)."""
    from namo import config, items, trades
    try:
        return trades.trade_of(items.model_name(item), trades.rules_from_config(config.load()))
    except Exception:
        return trades.UNASSIGNED


# ---- capture and go to ---------------------------------------------------------------------


def snapshot(doc=None, path=None, long_side=SNAPSHOT_LONG_SIDE):
    """Renders the current view (aspect of the active view) to a JPEG; returns its path."""
    from namo import images, issues
    document = _doc(doc)
    try:
        view = document.ActiveView
        width, height = issues.snapshot_size(view.Width, view.Height, long_side)
    except Exception:
        width, height = issues.snapshot_size(16, 9, long_side)
    target = path or temp_path('.jpg', 'snapshot')
    return images.capture(target, width, height, doc=document, quality=SNAPSHOT_QUALITY)


def capture(doc=None, image=True, model_items=None, point=None):
    """The current view as issue material:

    {'camera', 'camera_units', 'elements' (records), 'element_total', 'location' (from
     point, else the centre of the items) or None, 'image' (temp JPEG path or None),
     'image_error' (text or None)}.

    model_items: what to record (default: the current selection)."""
    from namo import camera, items
    document = _doc(doc)
    chosen = items.selected(document) if model_items is None else items.as_list(model_items)
    records, objects, total = elements_of(chosen, document)
    where = point if point is not None else (centre_of(objects) if objects else None)
    shot = None
    error = None
    if image:
        try:
            shot = snapshot(document)
        except Exception as problem:
            error = str(problem)
    return {'camera': camera.capture(document), 'camera_units': doc_units(document),
            'elements': records, 'element_total': total,
            'location': location_of(where, document) if where is not None else None,
            'image': shot, 'image_error': error}


def go_to(issue, doc=None, select=True):
    """Restores the issue's camera (converted to the document's units) and selects its
    elements. {'moved', 'selected', 'missing'}. With no camera the elements are framed;
    with neither, the view frames a small box around the pin."""
    from namo import camera, issues, items
    document = _doc(doc)
    units_name = doc_units(document)
    moved = False
    cam = issues.camera_in(issue, units_name)
    if cam:
        try:
            camera.apply(cam, document)
            moved = True
        except Exception:
            moved = False
    found = []
    missing = 0
    entries = [e.get('entry') for e in issue.get('elements') or [] if e.get('entry')]
    if entries:
        found, missing = items.resolve(entries, document)
    if select:
        if found:
            items.select(found, doc=document)
        else:
            try:
                document.CurrentSelection.Clear()
            except Exception:
                pass
    if not moved and found:
        moved = bool(items.zoom(found, doc=document, margin=0.25))
    if not moved:
        point = issues.point_in(issue, units_name)
        if point is not None:
            half = 1.5 / (unit_to_m(document, units_name) or 1.0)
            box = ((point[0] - half, point[1] - half, point[2] - half),
                   (point[0] + half, point[1] + half, point[2] + half))
            try:
                moved = bool(camera.zoom_to(box, document))
            except Exception:
                moved = False
    return {'moved': moved, 'selected': len(found), 'missing': missing}


def select_elements(issue, doc=None):
    """Selects the issue's elements without moving the view. {'moved': False,
    'selected', 'missing'}."""
    from namo import items
    document = _doc(doc)
    entries = [e.get('entry') for e in issue.get('elements') or [] if e.get('entry')]
    found, missing = items.resolve(entries, document) if entries else ([], 0)
    if found:
        items.select(found, doc=document)
    return {'moved': False, 'selected': len(found), 'missing': missing}


def go_to_note(result):
    """A toast detail for go_to's result ('' when everything was found)."""
    if result['missing']:
        return '%d element%s not found in this model.' % (result['missing'],
                                                          '' if result['missing'] == 1 else 's')
    if not result['moved'] and not result['selected']:
        return 'The issue has no saved view, elements or pin.'
    return ''


# ---- pins -------------------------------------------------------------------------------------


def _pins():
    from namo import session
    holder = session.holder(PINS)
    if getattr(holder, 'drawn', None) is None:
        holder.drawn = []
        holder.on = False
    return holder


def pins_on():
    """True while Issue Pins is switched on this session."""
    return bool(_pins().on)


def set_pins_on(on):
    _pins().on = bool(on)


def stray_pin_tags(tags, remembered=()):
    """The overlay tags that are issue pins but not in `remembered` (pure). The overlay
    outlives everything on the Python side, so pins can be on screen that this session's
    holder no longer lists; they are found by their tag prefix."""
    known = set(remembered or ())
    out = []
    for tag in tags or []:
        text = '' if tag is None else str(tag)
        if text.startswith(TAG_PREFIX) and text not in known and text not in out:
            out.append(text)
    return out


def _overlay_tags():
    """Every tag the overlay holds right now ([] when it cannot be read)."""
    try:
        import clr
        clr.AddReference('PyNavis.Runtime')
        from PyNavis.Runtime.Overlay import OverlayRegistry
        return [item.Tag for item in OverlayRegistry.Items]
    except Exception:
        return []


def _wipe(overlay, holder):
    remembered = list(holder.drawn or [])
    for tag in remembered + stray_pin_tags(_overlay_tags(), remembered):
        overlay.clear(tag)
    holder.drawn = []


def clear_pins():
    """Removes every issue pin from the view: the ones this session drew and any other
    left under the issue pin tag prefix."""
    from pynavis import overlay
    _wipe(overlay, _pins())
    _overlay_redraw()


def draw_pins(rows, doc=None, statuses=None):
    """Draws a pin for every issue in rows whose status is in statuses (default: open)
    and that has a location, replacing the pins drawn before. Returns how many were
    drawn (0 when the overlay plug-in is not loaded)."""
    from pynavis import overlay
    from namo import issues
    document = _doc(doc)
    holder = _pins()
    _wipe(overlay, holder)
    wanted = statuses or issues.OPEN_STATUSES
    units_name = doc_units(document)
    height = issues.pin_height(unit_to_m(document, units_name))
    count = 0
    for issue in rows:
        if issue.get('status') not in wanted:
            continue
        point = issues.point_in(issue, units_name)
        if point is None:
            continue
        tag = TAG_PREFIX + issue['id']
        if overlay.add(tag, issues.pin_segments(point, height), label=issues.pin_label(issue),
                       label_at=issues.pin_label_point(point, height)):
            count += 1
        holder.drawn.append(tag)
    _overlay_redraw()
    return count


def redraw_pins(doc=None):
    """Redraws the pins of the document's register when pins are on. Returns the count
    drawn, or None when pins are off. Never raises (logged)."""
    from namo import issuestore, session
    if not pins_on():
        return None
    try:
        document = _doc(doc)
        rows = issuestore.for_doc(document).list()
        if not rows:
            clear_pins()
            return 0
        return draw_pins(rows, document)
    except Exception as error:
        session.log('warning', 'issue pins not redrawn: %s' % error)
        return None


def watch_pins():
    """Keeps pins in step with issue edits made anywhere in this session: one listener,
    debounced (300 ms) so a batch of edits redraws once."""
    from namo import issuestore
    holder = _pins()
    old = getattr(holder, 'debouncer', None)
    if old is not None:
        try:
            old.cancel()
        except Exception:
            pass
    try:
        from namo import ui
        holder.debouncer = ui.Debouncer(300, redraw_pins)
    except Exception:
        holder.debouncer = None

    def changed(kind, ids, key):
        debouncer = getattr(holder, 'debouncer', None)
        if debouncer is not None:
            debouncer.trigger()
        else:
            redraw_pins()
    issuestore.subscribe('issue-pins', changed)


def unwatch_pins():
    from namo import issuestore
    holder = _pins()
    debouncer = getattr(holder, 'debouncer', None)
    if debouncer is not None:
        try:
            debouncer.cancel()
        except Exception:
            pass
    holder.debouncer = None
    issuestore.unsubscribe('issue-pins')


# ---- BCF components -------------------------------------------------------------------------


def _query(conditions):
    return {'or': [{'and': conditions}]}


def _exists(category, prop):
    return _query([{'category': category, 'prop': prop, 'op': 'has_property'}])


def component_finder(doc=None, progress=None):
    """A function find(component) -> ModelItem or None for BCF components, set up once
    per model: it probes which IFC GUID property this model carries and whether it
    marks Revit elements, so each lookup costs at most two searches (each a model walk
    that stops at the first hit; pynavis.sets.find_first). The probes themselves are a
    few walks once (a property no item has costs one full walk to rule out);
    progress(fraction, label) is told, and False from it raises items.Cancelled."""
    from pynavis import sets
    from namo import items
    document = _doc(doc)
    candidates = list(items.REVIT_PROPERTIES['ifc_guid'])
    steps = 2 + len(candidates)

    def tell(done):
        if progress is not None and progress(float(done) / steps,
                                             'Checking which ID properties the model has') == False:  # noqa: E712
            raise items.Cancelled()
    tell(0)
    try:
        has_element_id = sets.find_first(_exists('Element ID', 'Value'), document) is not None
    except Exception:
        has_element_id = False
    tell(1)
    try:
        elements_marked = sets.find_first(
            _query([{'category': ELEMENT_CATEGORY, 'op': 'has_category', 'by_display': False}]),
            document) is not None
    except Exception:
        elements_marked = False
    guid_props = []
    for index, (category, prop) in enumerate(candidates):
        tell(2 + index)
        try:
            if sets.find_first(_exists(category, prop), document) is not None:
                guid_props.append((category, prop))
        except Exception:
            continue

    def find(component):
        tool_id = str(component.get('authoring_tool_id') or '').strip()
        ifc = str(component.get('ifc_guid') or '').strip()
        for category, prop in guid_props:
            if not ifc:
                break
            try:
                hit = sets.find_first(_query([{'category': category, 'prop': prop,
                                               'op': 'equals', 'value': ifc}]), document)
            except Exception:
                hit = None
            if hit is not None:
                return items.object_of(hit)
        if has_element_id and tool_id.isdigit():
            conditions = [{'category': 'Element ID', 'prop': 'Value', 'op': 'equals',
                           'value': tool_id}]
            if elements_marked:
                conditions.append({'category': ELEMENT_CATEGORY, 'op': 'has_category',
                                   'by_display': False})
            try:
                hit = sets.find_first(_query(conditions), document)
            except Exception:
                hit = None
            if hit is not None:
                return items.object_of(hit)
        return None

    find.searchable = bool(guid_props or has_element_id)
    find.ifc_properties = guid_props
    return find


def resolve_components(components, doc=None, progress=None, budget_s=180.0, finder=None):
    """(found ModelItems, missing count, skipped count) for BCF components: IFC GlobalId
    first (through whichever IFC GUID property the model has), then AuthoringToolId as a
    Revit Element ID. progress(fraction, label) returning False raises items.Cancelled.
    After budget_s seconds the rest are skipped (counted, not searched)."""
    from namo import items
    finder = finder or component_finder(doc)
    unique = []
    seen = set()
    for component in components or []:
        key = (str(component.get('ifc_guid') or ''), str(component.get('authoring_tool_id') or ''))
        if key in seen or key == ('', ''):
            continue
        seen.add(key)
        unique.append(component)
    found = []
    missing = 0
    skipped = 0
    started = time.time()
    total = len(unique) or 1
    for index, component in enumerate(unique):
        if progress is not None and progress(float(index) / total, 'Finding elements %d of %d'
                                             % (index + 1, len(unique))) == False:  # noqa: E712
            raise items.Cancelled()
        if time.time() - started > budget_s:
            skipped += 1
            continue
        hit = finder(component)
        if hit is None:
            missing += 1
        elif hit not in found:
            found.append(hit)
    return found, missing, skipped


def _overlay_redraw():
    """Redraws the overlay through namo.overlayfix, so labels land on their points."""
    from namo import overlayfix
    return overlayfix.redraw()
