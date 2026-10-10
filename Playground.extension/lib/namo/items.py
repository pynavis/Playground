# -*- coding: utf-8 -*-
"""Model items: walking, collecting, identifying, measuring and showing them.

Pure helpers come first (tree walks over callables, box unions, value tallies, the
"everything except" frontier); the API half lazy-imports pynavis so `import
namo.items` works anywhere. Every API function takes doc=None for the active
document.

Terms used here:
  * geometry item  a ModelItem with HasGeometry (a leaf that draws).
  * object         FindFirstObjectAncestor() of a geometry item: what a user calls
                   an element (a wall, a duct). Falls back to the item itself.
  * key            '<source file name lower>|<PathId>': stable across sessions of
                   the same document while the models keep their source files.

Lists returned by geometry_items/objects are ItemList: a plain list with a
`sampled` attribute that is True when a budget cut the walk short ("sampled" must
then appear in what the tool tells the user).

Traps baked in:
  * ModelItem.HasModel / .Model are documented for the model ROOT item; model_of()
    climbs to the root instead of trusting an element's own HasModel.
  * IsHidden is the item's OWN flag: visible() checks every ancestor.
  * A fresh Api.Search matches nothing (pynavis.sets handles that); nothing here
    builds raw searches.
"""

import os

TICK_EVERY = 500

# What revit_ids() tries, in order, by DISPLAY names (category, property). The
# object-level ancestor is tried when the item itself has none of them.
REVIT_PROPERTIES = {
    'element_id': [('Element ID', 'Value'), ('Element', 'Id'), ('Revit Element', 'Id'),
                   ('Element', 'Element ID'), ('Element', 'ElementId')],
    'unique_id': [('Element', 'UniqueId'), ('Element', 'Unique Id'), ('Element', 'GUID'),
                  ('Revit Element', 'UniqueId'), ('Element ID', 'UniqueId')],
    'ifc_guid': [('Element', 'IfcGUID'), ('Element', 'IFC GUID'), ('Element', 'IfcGuid'),
                 ('Element', 'GlobalId'), ('IFC', 'GlobalId'), ('Element', 'Ifc Guid'),
                 ('Identity Data', 'IfcGUID')],
    'category': [('Element', 'Category'), ('Revit Element', 'Category'),
                 ('Element', 'Category Name')],
    'family': [('Element', 'Family'), ('Revit Type', 'Family'), ('Element', 'Family Name'),
               ('Revit Element', 'Family')],
    'type': [('Element', 'Type'), ('Revit Type', 'Name'), ('Element', 'Type Name'),
             ('Revit Element', 'Type')],
}

NO_VALUE = '(no value)'


class Cancelled(Exception):
    """Raised when a tick callback returns False."""


class ItemList(list):
    """A list of ModelItems; `sampled` is True when a budget stopped the walk."""
    sampled = False


# ---- pure helpers --------------------------------------------------------------


class Ticker(object):
    """Calls tick(done, total) every `every` steps and once at the end; a tick that
    returns exactly False (== False, so interop bools work) raises Cancelled."""

    def __init__(self, tick, total=None, every=TICK_EVERY):
        self.tick = tick
        self.total = total
        self.every = max(1, int(every))
        self.done = 0

    def step(self, count=1):
        before = self.done
        self.done += count
        if self.tick is not None and (self.done // self.every) != (before // self.every):
            self._fire()

    def finish(self):
        if self.tick is not None:
            self._fire()

    def _fire(self):
        if self.tick(self.done, self.total) == False:   # noqa: E712 (interop bools)
            raise Cancelled()


def walk_tree(roots, children_of, max_depth=None):
    """(node, depth) depth-first pre-order with children in their own order.
    Iterative, so deep trees cannot hit the recursion limit."""
    stack = [(node, 0) for node in reversed(list(roots))]
    while stack:
        node, depth = stack.pop()
        yield node, depth
        if max_depth is not None and depth >= max_depth:
            continue
        children = list(children_of(node))
        for child in reversed(children):
            stack.append((child, depth + 1))


def dedupe(values, key=None):
    """values without repeats, first occurrence wins, order kept."""
    seen = set()
    out = []
    for value in values:
        k = value if key is None else key(value)
        if k in seen:
            continue
        seen.add(k)
        out.append(value)
    return out


def union_boxes(boxes):
    """((x0,y0,z0),(x1,y1,z1)) enclosing every box; None entries are skipped and
    no boxes at all gives None."""
    low = [None, None, None]
    high = [None, None, None]
    for box in boxes:
        if box is None:
            continue
        for axis in range(3):
            lo, hi = box[0][axis], box[1][axis]
            if low[axis] is None or lo < low[axis]:
                low[axis] = lo
            if high[axis] is None or hi > high[axis]:
                high[axis] = hi
    if low[0] is None:
        return None
    return (tuple(low), tuple(high))


def box_center(box):
    if box is None:
        return None
    return tuple((box[0][i] + box[1][i]) / 2.0 for i in range(3))


def box_size(box):
    if box is None:
        return None
    return tuple(box[1][i] - box[0][i] for i in range(3))


def value_text(value):
    """How a property value is shown and compared in tallies: None and blank text
    become NO_VALUE, floats lose trailing zeros, booleans read Yes/No, tuples
    (points) are joined with commas."""
    if value is None:
        return NO_VALUE
    if isinstance(value, bool):
        return 'Yes' if value else 'No'
    if isinstance(value, float):
        text = ('%.6f' % value).rstrip('0').rstrip('.')
        return '0' if text in ('', '-0') else text
    if isinstance(value, (tuple, list)):
        return ', '.join(value_text(v) for v in value)
    text = str(value)
    return text if text.strip() else NO_VALUE


def tally(texts):
    """[(text, count)] most common first, ties broken by text (case-insensitive),
    so the order is the same on every engine."""
    counts = {}
    for text in texts:
        counts[text] = counts.get(text, 0) + 1
    return sorted(counts.items(), key=lambda pair: (-pair[1], str(pair[0]).lower(), str(pair[0])))


def key_text(source_name, path_id):
    """The stable item key: '<source file basename lower>|<PathId>'."""
    base = os.path.basename(str(source_name or '').replace('\\', '/').split('/')[-1])
    return '%s|%s' % (base.lower(), path_id)


def join_path(names, sep=' > '):
    return sep.join(str(n) for n in names)


def ancestor_closure(keep, parent_of):
    """Every node that is an ancestor of something in keep (keep itself excluded
    unless it is an ancestor of another kept node). parent_of(node) -> parent or
    None. Climbing stops at a node already seen, so the cost is the number of
    distinct ancestors, not keep x depth."""
    ancestors = set()
    for node in keep:
        parent = parent_of(node)
        while parent is not None and parent not in ancestors:
            ancestors.add(parent)
            parent = parent_of(parent)
    return ancestors


def frontier(roots, children_of, keep, ancestors):
    """The smallest list of subtrees that together hold everything EXCEPT keep
    and its descendants: walk down from the roots only through ancestors of kept
    nodes; any child that is neither kept nor an ancestor is a whole subtree to
    take. keep and ancestors are sets of nodes (anything hashable).

    This is what paint.ghost overrides: correct whether Navisworks pushes an
    override down to descendants or inherits it at draw time, because no taken
    subtree contains a kept node and no kept node's ancestor is ever taken.
    """
    out = []
    stack = list(reversed(list(roots)))
    while stack:
        node = stack.pop()
        if node in keep:
            continue
        if node in ancestors:
            children = list(children_of(node))
            for child in reversed(children):
                stack.append(child)
            continue
        out.append(node)
    return out


# ---- API half ------------------------------------------------------------------


def _doc(doc):
    if doc is not None:
        return doc
    from pynavis._api import Application
    return Application.ActiveDocument


def _api():
    from pynavis._api import Api
    return Api


def _is_item(value):
    try:
        Api = _api()
    except ImportError:
        return False
    return isinstance(value, Api.ModelItem)


def as_list(items_or_item):
    """A python list from a ModelItem, a ModelItemCollection, None or any iterable."""
    if items_or_item is None:
        return []
    if _is_item(items_or_item):
        return [items_or_item]
    return list(items_or_item)


def selected(doc=None):
    """The current selection as a list of ModelItems (a snapshot)."""
    return list(_doc(doc).CurrentSelection.SelectedItems)


def roots(doc=None):
    """The root item of every model in the document, in model order."""
    models = _doc(doc).Models
    return [models[index].RootItem for index in range(models.Count)]


def walk(roots, max_depth=None):
    """(item, depth) depth-first, children in order, starting at depth 0 for each
    root. Python-side recursion over .Children: fine for a branch, slow for a whole
    federation (use geometry_items/objects, which enumerate natively)."""
    return walk_tree(as_list(roots), lambda item: item.Children, max_depth)


def geometry_items(roots, tick=None, budget=None):
    """ItemList of every item with geometry at or under roots, in tree order.

    Enumerates each root's DescendantsAndSelf natively. tick(done, None) is called
    every ~500 items walked; returning False raises Cancelled. budget caps how many
    geometry items are collected (the list's .sampled is then True). Overlapping
    roots (a selection holding a parent and its child) yield each item once."""
    ticker = Ticker(tick)
    out = ItemList()
    starts = as_list(roots)
    seen = set() if len(starts) > 1 else None
    for root in starts:
        for item in root.DescendantsAndSelf:
            ticker.step()
            if item.HasGeometry:
                if seen is not None:
                    if item in seen:
                        continue
                    seen.add(item)
                out.append(item)
                if budget is not None and len(out) >= budget:
                    out.sampled = True
                    ticker.finish()
                    return out
    ticker.finish()
    return out


def object_of(item):
    """The element-level item for any item: FindFirstObjectAncestor(), else the
    item itself."""
    try:
        ancestor = item.FindFirstObjectAncestor()
    except Exception:
        ancestor = None
    return ancestor if ancestor is not None else item


def objects(roots_or_items, tick=None, budget=None):
    """ItemList of distinct element-level items (object_of each geometry item under
    roots_or_items), first-seen order. budget caps the number of objects
    (.sampled True when it did); tick as geometry_items."""
    ticker = Ticker(tick)
    seen = set()
    out = ItemList()
    for root in as_list(roots_or_items):
        for item in root.DescendantsAndSelf:
            ticker.step()
            if not item.HasGeometry:
                continue
            element = object_of(item)
            if element in seen:
                continue
            seen.add(element)
            out.append(element)
            if budget is not None and len(out) >= budget:
                out.sampled = True
                ticker.finish()
                return out
    ticker.finish()
    return out


def visible(item):
    """True when neither the item nor any ancestor is hidden."""
    node = item
    while node is not None:
        if node.IsHidden:
            return False
        node = node.Parent
    return True


def _source_names(models):
    names = {}
    for index in range(models.Count):
        try:
            names[index] = models[index].SourceFileName or models[index].FileName or ''
        except Exception:
            names[index] = ''
    return names


def key(item, doc=None):
    """'<source file lower>|<PathId>' for one item (see module docstring)."""
    models = _doc(doc).Models
    path_id = models.CreatePathId(item)
    index = path_id.ModelIndex
    try:
        source = models[index].SourceFileName or models[index].FileName or ''
    except Exception:
        source = ''
    return key_text(source, path_id.PathId)


def keys(items, doc=None):
    """key() for many items, reading each model's file name once."""
    models = _doc(doc).Models
    names = _source_names(models)
    out = []
    for item in as_list(items):
        path_id = models.CreatePathId(item)
        out.append(key_text(names.get(path_id.ModelIndex, ''), path_id.PathId))
    return out


def entries(items, doc=None):
    """JSON-safe entries ({'m','i','p'}) for items: pynavis.memory's schema, so
    they resolve across sessions and survive appended or reordered models."""
    from pynavis import memory
    return memory.encode_items(as_list(items), _doc(doc))


def resolve(entries, doc=None):
    """(found ModelItems, missing count) for entries from entries()."""
    from pynavis import memory
    found, missing, _models = memory.resolve_entries(list(entries or []), _doc(doc))
    return found, missing


def model_of(item):
    """The Model an item belongs to (climbing to the model root), or None."""
    node = item
    last = None
    while node is not None:
        try:
            if node.HasModel:
                return node.Model
        except Exception:
            pass
        last = node
        node = node.Parent
    try:
        if last is not None and last.HasModel:
            return last.Model
    except Exception:
        pass
    return None


def model_name(item):
    """Source file name (basename, as appended) of the item's model, or ''."""
    model = model_of(item)
    if model is None:
        return ''
    name = model.SourceFileName or model.FileName or ''
    return str(name).replace('\\', '/').split('/')[-1]


def models(doc=None):
    """[{'index', 'model', 'name' (basename), 'file' (Model.FileName),
    'source' (Model.SourceFileName), 'units' (str), 'root' (ModelItem)}]."""
    document = _doc(doc)
    out = []
    collection = document.Models
    for index in range(collection.Count):
        model = collection[index]
        source = model.SourceFileName or ''
        file_name = model.FileName or ''
        name = (source or file_name).replace('\\', '/').split('/')[-1]
        try:
            units = str(model.Units)
        except Exception:
            units = ''
        out.append({'index': index, 'model': model, 'name': name, 'file': file_name,
                    'source': source, 'units': units, 'root': model.RootItem})
    return out


def _name_of(item):
    name = item.DisplayName
    if name:
        return name
    try:
        return item.ClassDisplayName or ''
    except Exception:
        return ''


def tree_path(item, sep=' > '):
    """'file.nwc > Level 1 > Walls > Basic Wall': display names root first (a
    blank name shows the item's class name)."""
    names = []
    node = item
    while node is not None:
        names.append(_name_of(node))
        node = node.Parent
    names.reverse()
    return join_path(names, sep)


def _box_tuple(box):
    if box is None:
        return None
    try:
        if box.IsEmpty:
            return None
    except Exception:
        return None
    return ((box.Min.X, box.Min.Y, box.Min.Z), (box.Max.X, box.Max.Y, box.Max.Z))


def bbox(items_or_item):
    """World bounding box ((x0,y0,z0),(x1,y1,z1)) of one item or many (union,
    empty boxes ignored), or None. A ModelItemCollection is measured natively."""
    Api = _api()
    if items_or_item is None:
        return None
    if isinstance(items_or_item, (Api.ModelItem, Api.ModelItemCollection)):
        return _box_tuple(items_or_item.BoundingBox())
    return union_boxes(_box_tuple(item.BoundingBox()) for item in items_or_item)


def center(item):
    """Bounding-box centre (x, y, z) of an item (or items), or None."""
    return box_center(bbox(item))


def size(item):
    """Bounding-box size (dx, dy, dz) of an item (or items), or None."""
    return box_size(bbox(item))


def _get(item, category, prop):
    from namo import variants
    try:
        return variants.get(item, category, prop)
    except Exception:
        return None


def prop(item, category, prop_name, fallback_to_object=True):
    """A property value (pynavis.props coercion: str/int/float/bool/datetime/
    tuple) by display names, or None. With fallback_to_object the element-level
    ancestor is tried when the item itself does not carry it."""
    value = _get(item, category, prop_name)
    if value is None and fallback_to_object:
        element = object_of(item)
        if element is not item and not element.Equals(item):
            value = _get(element, category, prop_name)
    return value


REVIT_ELEMENT_CATEGORY = 'LcRevitData_Element'


def revit_element(item):
    """The nearest ancestor-or-self carrying Revit's element category (internal name
    LcRevitData_Element), or None for non-Revit items. Use it whenever an Element ID
    must identify the ELEMENT: nested family parts carry their type's id."""
    node = item
    depth = 0
    while node is not None and depth < 64:
        try:
            for category in node.PropertyCategories:
                if category.Name == REVIT_ELEMENT_CATEGORY:
                    return node
        except Exception:
            pass
        try:
            node = node.Parent
        except Exception:
            node = None
        depth += 1
    return None


def revit_ids(item):
    """{'element_id', 'unique_id', 'ifc_guid', 'category', 'family', 'type'} as
    text or None, tried in REVIT_PROPERTIES order on the nearest real Revit element
    (revit_element), then the item, then its object ancestor. When the model carries no IFC GUID but has a Revit UniqueId,
    ifc_guid is derived the way Revit's IFC exporter does (namo.ifcguid) and
    'ifc_guid_derived' is True."""
    # The nearest real Revit element first: nested parts under a family instance carry
    # the TYPE's Element ID (one id on every instance of the type), so reading the
    # picked part itself would report the wrong element. Then the item, then its
    # object ancestor (non-Revit models).
    candidates = []
    revit = revit_element(item)
    if revit is not None:
        candidates.append(revit)
    for node in (item, object_of(item)):
        if not any(node.Equals(c) for c in candidates):
            candidates.append(node)
    out = {}
    for field in sorted(REVIT_PROPERTIES):
        found = None
        for node in candidates:
            for category, name in REVIT_PROPERTIES[field]:
                value = _get(node, category, name)
                if value is not None and str(value).strip():
                    found = value_text(value)
                    break
            if found is not None:
                break
        out[field] = found
    out['ifc_guid_derived'] = False
    if out['ifc_guid'] is None and out['unique_id']:
        try:
            from namo import ifcguid
            out['ifc_guid'] = ifcguid.from_revit_unique_id(out['unique_id'])
            out['ifc_guid_derived'] = True
        except Exception:
            pass
    return out


def category(item):
    """The Revit/IFC category ('Ducts') when the item or its element carries one,
    else Navisworks' class name ('Solid', 'Block')."""
    for node in (item, object_of(item)):
        for cat, name in REVIT_PROPERTIES['category']:
            value = _get(node, cat, name)
            if value is not None and str(value).strip():
                return str(value)
    try:
        return item.ClassDisplayName or ''
    except Exception:
        return ''


def sample_properties(items, limit=200):
    """[(category, property, count)] of the property NAMES on the first `limit`
    items: how many of them carry each one. Sorted by category then property
    (case-insensitive). Reads names only, never values, so it is quick."""
    counts = {}
    for index, item in enumerate(as_list(items)):
        if limit is not None and index >= limit:
            break
        try:
            categories = item.PropertyCategories
        except Exception:
            continue
        for cat in categories:
            for prop_ in cat.Properties:
                pair = (cat.DisplayName, prop_.DisplayName)
                counts[pair] = counts.get(pair, 0) + 1
    rows = [(pair[0], pair[1], n) for pair, n in counts.items()]
    rows.sort(key=lambda r: (r[0].lower(), r[1].lower(), r[0], r[1]))
    return rows


def distinct_values(items, category_name, prop_name, tick=None, fallback_to_object=False):
    """[(value_text, count)] most common first, over every item (missing values
    count as NO_VALUE). tick(done, total) every ~500 items; False cancels."""
    data = as_list(items)
    ticker = Ticker(tick, total=len(data))
    texts = []
    for item in data:
        texts.append(value_text(prop(item, category_name, prop_name, fallback_to_object)))
        ticker.step()
    ticker.finish()
    return tally(texts)


def collection(items):
    """A ModelItemCollection of items (a collection passes straight through)."""
    Api = _api()
    if isinstance(items, Api.ModelItemCollection):
        return items
    out = Api.ModelItemCollection()
    for item in as_list(items):
        out.Add(item)
    return out


def select(items, zoom=False, doc=None):
    """Replaces the selection with items; zoom=True then frames it (COM zoom to
    selection, best effort). Returns how many items were selected."""
    document = _doc(doc)
    coll = collection(items)
    document.CurrentSelection.CopyFrom(coll)
    if zoom and coll.Count:
        from pynavis import view
        view.zoom_selected(document)
    return coll.Count


def zoom(items, doc=None, margin=0.0):
    """Frames items along the current view direction without touching the
    selection (namo.camera.zoom_to). False when they have no extent."""
    from namo import camera
    return camera.zoom_to(bbox(collection(items)), doc=doc, margin=margin)


def isolate(items, doc=None):
    """Hides everything but items, one undo step (pynavis.view.isolate). Returns
    how many were kept; empty items is a no-op."""
    from pynavis import view
    return view.isolate(as_list(items), _doc(doc))


def hide(items, hidden=True, doc=None):
    """Hides (or unhides) items, one undo step. Returns the count."""
    from pynavis.viewpoints import transaction
    document = _doc(doc)
    coll = collection(items)
    if not coll.Count:
        return 0
    with transaction('Hide items' if hidden else 'Unhide items', document):
        document.Models.SetHidden(coll, bool(hidden))
    return coll.Count


def unhide_all(doc=None):
    """Unhides everything, one undo step."""
    from pynavis import view
    view.unhide_all(_doc(doc))


def complement(keep, doc=None):
    """The fewest items that together cover the whole model EXCEPT keep (and what
    is under keep): see frontier(). Cost is the kept items' ancestors and their
    children, not the model size."""
    keep_list = as_list(keep)
    keep_set = set(keep_list)
    ancestors = ancestor_closure(keep_list, lambda node: node.Parent)
    return frontier(roots(doc), lambda node: node.Children, keep_set, ancestors)
