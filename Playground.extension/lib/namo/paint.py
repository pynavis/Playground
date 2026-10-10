# -*- coding: utf-8 -*-
"""Colouring model items: permanent colour/transparency overrides, ghosting, reset.

Every write is ONE undo step (pynavis.viewpoints.transaction). Colours are 'RRGGBB'
(see namo.colors); transparency is 0.0 (opaque) to 1.0 (invisible).

ghost(keep) and why it is built the way it is
---------------------------------------------
"Ghost everything except these" could be done as "override the model roots, then
ResetPermanentMaterials on the kept items", but that is wrong twice over: it would
wipe any colour the kept items were just given (colour by property + ghost the rest
is the common case), and whether resetting a child undoes an override set on its
ancestor depends on how Navisworks stores overrides (pushed down to the geometry
nodes, or inherited at draw time), which is not documented. Instead ghost() overrides
the COMPLEMENT: namo.items.complement(keep), the fewest subtrees that hold everything
except the kept items. No kept item and no ancestor of one is ever touched, so the
result is right under either storage rule, and kept items keep their colours. The
cost is the kept items' ancestors plus those ancestors' children (one Parent climb per
kept item, deduplicated), then a single override call: far below a model walk.

Reading a colour back (read_color) uses ModelGeometry.ActiveColor /
ActiveTransparency, which are in the API but UNVERIFIED in-app: older field notes
(pynavis.viewstate) found overrides unreadable through COM. Treat it as best effort.
"""

import datetime

from namo import colors

SCHEME_STORE = 'last-color-scheme'


def nw_color(hex_value):
    """Api.Color for 'RRGGBB' (0..1 channels, which is what Api.Color takes)."""
    from pynavis._api import Api
    r, g, b = colors.rgb01(hex_value)
    return Api.Color(r, g, b)


def _doc(doc):
    if doc is not None:
        return doc
    from pynavis._api import Application
    return Application.ActiveDocument


def _clamp_transparency(value):
    if value is None:
        return None
    value = float(value)
    return 0.0 if value < 0.0 else 1.0 if value > 1.0 else value


def plan_groups(groups):
    """Pure: the groups apply() will write, as [(items_list, hex_or_None,
    transparency_or_None)], with empty groups and do-nothing groups dropped, hexes
    normalised and transparency clamped to 0..1. Raises ValueError for a colour
    that does not parse."""
    out = []
    for group in groups:
        items, hex_value = group[0], group[1] if len(group) > 1 else None
        transparency = group[2] if len(group) > 2 else None
        items = list(items or [])
        if not items:
            continue
        if hex_value is not None:
            parsed = colors.parse_hex(hex_value)
            if parsed is None:
                raise ValueError('not a colour: %r' % (hex_value,))
            hex_value = parsed
        transparency = _clamp_transparency(transparency)
        if hex_value is None and transparency is None:
            continue
        out.append((items, hex_value, transparency))
    return out


def apply(groups, doc=None, name='Color items'):
    """Writes [(items, hex_or_None, transparency_or_None)] as permanent overrides in
    ONE transaction (one undo step, named `name`). Empty groups are skipped.
    Returns how many items were written to (counting each group's items)."""
    from namo import items as _items
    planned = plan_groups(groups)
    if not planned:
        return 0
    from pynavis.viewpoints import transaction
    document = _doc(doc)
    models = document.Models
    count = 0
    with transaction(name, document):
        for item_list, hex_value, transparency in planned:
            coll = _items.collection(item_list)
            if hex_value is not None:
                models.OverridePermanentColor(coll, nw_color(hex_value))
            if transparency is not None:
                models.OverridePermanentTransparency(coll, transparency)
            count += coll.Count
    return count


def ghost(keep_items, transparency=0.85, hex=None, doc=None, name='Ghost other items'):
    """Makes everything EXCEPT keep_items transparent (and grey when hex is given),
    one undo step, leaving the kept items' own colours alone (see the module
    docstring). Returns how many top-level subtrees were ghosted; 0 (and no edit)
    when keep_items is empty, so a tool never ghosts the whole model by accident.
    transparency None with a hex greys without fading."""
    from namo import items as _items
    keep = _items.as_list(keep_items)
    if not keep:
        return 0
    document = _doc(doc)
    others = _items.complement(keep, document)
    if not others:
        return 0
    group = (others, hex, transparency)
    apply([group], document, name)
    return len(others)


def reset(items=None, doc=None, name='Reset appearance'):
    """Removes permanent colour and transparency overrides from items, or from the
    whole model when items is None. One undo step. Returns the item count (or -1
    for the whole model)."""
    from pynavis.viewpoints import transaction
    document = _doc(doc)
    if items is None:
        with transaction(name, document):
            document.Models.ResetAllPermanentMaterials()
        return -1
    from namo import items as _items
    coll = _items.collection(items)
    if not coll.Count:
        return 0
    with transaction(name, document):
        document.Models.ResetPermanentMaterials(coll)
    return coll.Count


def temporary(groups, doc=None):
    """Like apply() but with TEMPORARY overrides (cleared by Navisworks' own Reset
    All > Temporary, not saved in the file, not an undo step): for previews."""
    from namo import items as _items
    models = _doc(doc).Models
    count = 0
    for item_list, hex_value, transparency in plan_groups(groups):
        coll = _items.collection(item_list)
        if hex_value is not None:
            models.OverrideTemporaryColor(coll, nw_color(hex_value))
        if transparency is not None:
            models.OverrideTemporaryTransparency(coll, transparency)
        count += coll.Count
    return count


def reset_temporary(doc=None):
    """Clears every temporary override."""
    _doc(doc).Models.ResetAllTemporaryMaterials()


# ---- remembered scheme --------------------------------------------------------


def normalize_scheme(scheme, now=None):
    """Pure: a scheme dict in the stored shape, 'time' stamped (ISO seconds).
    {'title', 'property': {'category', 'property'}, 'entries': [{'value', 'hex',
    'count'}], 'ghost': transparency or None, 'time'}. Unknown keys are kept."""
    out = dict(scheme or {})
    out.setdefault('title', '')
    prop = out.get('property') or {}
    out['property'] = {'category': prop.get('category', ''), 'property': prop.get('property', '')}
    entries = []
    for entry in out.get('entries') or []:
        hex_value = colors.parse_hex(entry.get('hex'))
        entries.append({'value': entry.get('value'), 'hex': hex_value,
                        'count': int(entry.get('count') or 0)})
    out['entries'] = entries
    ghost_value = out.get('ghost')
    out['ghost'] = None if ghost_value is None else _clamp_transparency(ghost_value)
    stamp = now or datetime.datetime.now()
    out['time'] = stamp.strftime('%Y-%m-%dT%H:%M:%S')
    return out


def _scheme_store():
    from namo import store
    return store.Store(SCHEME_STORE, scope='global')


def remember_scheme(scheme):
    """Saves the scheme (normalize_scheme shape) as the last one used, in the
    global store 'last-color-scheme'. Returns what was stored."""
    value = normalize_scheme(scheme)
    _scheme_store().save(value)
    return value


def last_scheme():
    """The last remembered scheme, or None."""
    try:
        value = _scheme_store().load(None)
    except Exception:
        return None
    return value if isinstance(value, dict) else None


# ---- reading back --------------------------------------------------------------


def read_color(item):
    """(hex, transparency) the item draws with, from its first geometry's
    ActiveColor / ActiveTransparency; (None, None) when it has no geometry or the
    read fails. BEST EFFORT and unverified in-app: see the module docstring."""
    try:
        geometry = item.Geometry if item.HasGeometry else item.FindFirstGeometry()
        if geometry is None:
            return (None, None)
        color = geometry.ActiveColor
        return (colors.from_rgb01(color.R, color.G, color.B),
                float(geometry.ActiveTransparency))
    except Exception:
        return (None, None)
