# -*- coding: utf-8 -*-
"""Pick Order: an ordered list of items the user clicks, and what to do with it.

While the Pick Order toggle is on, namo.hk_pickorder appends each newly selected item
(a click, or each item of a small Ctrl/Shift-added set, in selection order) to the
document's pick list, ignoring repeats. The list lives in the session holder and in the
per-document store 'pick-order' (always local: it is personal, and a hook must never
wait on a network share or write into the model on every click), so it survives the
session. Select / Number / Export / Color / Clear Picked act on it.

Entries use pynavis.memory's schema plus a display name: {'m', 'i', 'p', 'name'}.
"""

import datetime

HOLDER = 'pickorder'
STORE = 'pick-order'
SMALL_SET = 20          # an added set larger than this is a box/search selection, not picks
TRACK_LIMIT = 500       # selections larger than this are not tracked item by item
CONFIRM_CLEAR_OVER = 20
TAB = 'Playground'
NUMBER_DEFAULTS = {'start': 1, 'step': 1, 'prefix': '', 'digits': 0, 'property': 'Sequence'}
EXPORT_HEADERS = ['Order', 'Name', 'Category', 'Element ID', 'GUID', 'Source file']


# ---- pure half -----------------------------------------------------------------------


def entry_key(entry):
    """(model file lower, PathId): one item, whatever model index it has today."""
    return (str(entry.get('m', '')).lower(), str(entry.get('p', '')))


def added(previous_keys, current_keys):
    """Keys in the current selection that were not in the previous one, in the current
    selection's order. previous_keys None means unknown: everything is new."""
    if previous_keys is None:
        return list(current_keys)
    before = set(previous_keys)
    return [k for k in current_keys if k not in before]


def picks_from_change(previous_keys, current_entries, small=SMALL_SET):
    """The entries a selection change contributes as picks: the newly added items when
    there are 1..small of them, else none (a box or search selection is not a pick)."""
    keys = [entry_key(e) for e in current_entries]
    new = set(added(previous_keys, keys))
    fresh = [e for e, k in zip(current_entries, keys) if k in new]
    if not fresh or len(fresh) > small:
        return []
    return fresh


def append(picks, entries):
    """picks plus entries not already in it (by entry_key). Returns (new list, count
    appended)."""
    seen = set(entry_key(e) for e in picks)
    out = list(picks)
    count = 0
    for entry in entries:
        key = entry_key(entry)
        if key in seen:
            continue
        seen.add(key)
        out.append(dict(entry))
        count += 1
    return out, count


def status_text(count, last_name=''):
    """(message, detail) for the banner while Pick Order is on."""
    if not count:
        return ('Pick order on: click items in order',
                'Each item you click is added to the list. Click Stop Picking when done.')
    noun = 'item' if count == 1 else 'items'
    detail = 'Click the next item, or Stop Picking when done.'
    if last_name:
        detail = 'Last: %s. %s' % (last_name, detail)
    return ('Pick order on: %s %s picked' % ('{:,}'.format(count), noun), detail)


def sequence_values(count, start=1, step=1, prefix='', digits=0):
    """The values Number Picked writes: ints, or text 'P-001' when there is a prefix or
    zero padding."""
    out = []
    for index in range(count):
        number = int(start) + index * int(step)
        if prefix or digits:
            text = str(abs(number)).zfill(int(digits or 0))
            out.append('%s%s%s' % (prefix, '-' if number < 0 else '', text))
        else:
            out.append(number)
    return out


def merged_tab(existing, prop, value):
    """A custom tab's values with one property set (pynavis props.set_custom replaces the
    whole tab, so the rest must be carried over). Values set_custom cannot write (dates,
    points) are kept as text."""
    out = {}
    for key, old in (existing or {}).items():
        if old is None:
            continue
        if isinstance(old, (bool, int, float, str)):
            out[key] = old
        else:
            out[key] = str(old)
    out[prop] = value
    return out


def gradient(count):
    """Hex colours along the order: light to strong (namo.colors.sequential)."""
    from namo import colors
    if count <= 0:
        return []
    if count == 1:
        return [colors.sequential(1.0)]
    return [colors.sequential(0.15 + 0.85 * float(i) / (count - 1)) for i in range(count)]


def csv_text(headers, rows):
    """RFC 4180 CSV text (CRLF line ends): quotes fields with commas, quotes or breaks."""
    def cell(value):
        if value is None:
            return ''
        if isinstance(value, float):
            text = ('%.6f' % value).rstrip('0').rstrip('.')
        else:
            text = str(value)
        if any(ch in text for ch in ',"\r\n'):
            text = '"%s"' % text.replace('"', '""')
        return text
    lines = [','.join(cell(h) for h in headers)]
    for row in rows:
        lines.append(','.join(cell(v) for v in row))
    return '\r\n'.join(lines) + '\r\n'


def export_headers(unit_symbol):
    suffix = ' (%s)' % unit_symbol if unit_symbol else ''
    return EXPORT_HEADERS + ['Centre X' + suffix, 'Centre Y' + suffix, 'Centre Z' + suffix]


def export_row(order, record):
    """One table row from a record {'name', 'category', 'element_id', 'guid', 'source',
    'center'}; centre values rounded to 4 decimals (blank when unknown)."""
    center = record.get('center') or (None, None, None)
    return [order, record.get('name') or '', record.get('category') or '',
            record.get('element_id') or '', record.get('guid') or '', record.get('source') or '',
            None if center[0] is None else round(center[0], 4),
            None if center[1] is None else round(center[1], 4),
            None if center[2] is None else round(center[2], 4)]


# ---- session + store ---------------------------------------------------------------------


def _doc(doc=None):
    if doc is not None:
        return doc
    from pynavis._api import Application
    return Application.ActiveDocument


def _doc_path(doc=None):
    try:
        return _doc(doc).FileName or ''
    except Exception:
        return ''


def _store(doc=None):
    from namo import store
    return store.Store(STORE, doc_path=_doc_path(doc), mode='local')


def _holder():
    from namo import session
    return session.holder(HOLDER)


def _cache(doc=None):
    """{'key', 'picks'} for the active document, loaded from the store once."""
    from namo import paths
    holder = _holder()
    key = paths.doc_key(_doc_path(doc))
    cache = getattr(holder, 'cache', None)
    if cache is None or cache.get('key') != key:
        data = _store(doc).load({}) or {}
        picks = [e for e in (data.get('items') or []) if isinstance(e, dict) and 'p' in e]
        cache = {'key': key, 'picks': picks}
        holder.cache = cache
    return cache


def load(doc=None):
    """The pick list of the active document (entries, in order)."""
    return list(_cache(doc)['picks'])


def save(picks, doc=None):
    """Stores the pick list (session + local store). IOError when the file is refused."""
    cache = _cache(doc)
    cache['picks'] = list(picks)
    _store(doc).save({'version': 1, 'items': cache['picks'],
                      'updated': datetime.datetime.now().replace(microsecond=0).isoformat()})


def is_on():
    return bool(getattr(_holder(), 'on', False))


def selection_entries(doc=None, limit=TRACK_LIMIT):
    """(entries with names, total count) for the current selection; entries is None when
    the selection is larger than limit (not tracked)."""
    from pynavis import memory
    document = _doc(doc)
    selected = document.CurrentSelection.SelectedItems
    count = selected.Count
    if count > limit:
        return None, count
    items_ = list(selected)
    entries = memory.encode_items(items_, document)
    for entry, item in zip(entries, items_):
        entry['name'] = item.DisplayName or item.ClassDisplayName or ''
    return entries, count


def announce(count, last_name=''):
    """Puts the running pick count on the banner along the bottom of the window, where
    shipped pyNavis tools keep the prompt while the user works in the view. It stays
    until Stop Picking clears it. Never raises (the banner is a courtesy: a pick is
    recorded whether or not it can be shown). Returns True when it was shown."""
    try:
        from pynavis import banner
        message, detail = status_text(count, last_name)
        banner.prompt(message, detail)
        return True
    except Exception:
        return False


def start(doc=None):
    """Turns recording on; the selection as it is now is not a pick. Returns True when
    the prompt went on the banner (the caller toasts it otherwise)."""
    holder = _holder()
    entries, _count = selection_entries(doc)
    holder.last = None if entries is None else [entry_key(e) for e in entries]
    holder.on = True
    return announce(len(_cache(doc)['picks']))


def stop():
    """Turns recording off. Returns how many items are in the list."""
    holder = _holder()
    holder.on = False
    holder.last = None
    try:
        from pynavis import banner
        banner.clear()
    except Exception:
        pass
    try:
        return len(load())
    except Exception:
        return 0


def on_selection(doc=None):
    """The hook's work: appends new picks. Returns how many were appended."""
    holder = _holder()
    entries, _count = selection_entries(doc)
    if entries is None:
        holder.last = None
        return 0
    fresh = picks_from_change(getattr(holder, 'last', None), entries)
    holder.last = [entry_key(e) for e in entries]
    if not fresh:
        return 0
    picks, count = append(load(doc), fresh)
    if count:
        save(picks, doc)
        announce(len(picks), picks[-1].get('name') or '')
    return count


def clear(doc=None):
    """Empties the list. Returns how many items it held."""
    count = len(load(doc))
    save([], doc)
    holder = _holder()
    if getattr(holder, 'on', False):
        start(doc)
    return count


def resolve(doc=None):
    """(items in pick order, missing count)."""
    from namo import items
    return items.resolve(load(doc), _doc(doc))


# ---- actions --------------------------------------------------------------------------------


def number(found, values, prop='Sequence', report=None, doc=None):
    """Writes Playground > prop = values[i] on found[i], merging into each item's existing
    Playground tab, in ONE undo step. Returns (written, errors)."""
    from pynavis import props
    from pynavis.viewpoints import transaction
    document = _doc(doc)
    written = 0
    errors = []
    try:
        with transaction('Number picked items', document):
            for index, (item, value) in enumerate(zip(found, values)):
                try:
                    existing = props.get_custom(item, TAB)
                except Exception:
                    existing = None
                tab = merged_tab(existing, prop, value)
                try:
                    count, errs = props.set_custom([item], TAB, tab, doc=document)
                except ValueError as error:
                    count, errs = 0, ['%s: %s' % (item.DisplayName, error)]
                written += count
                errors.extend(errs)
                if report is not None:
                    report(float(index + 1) / max(1, len(found)),
                           'Numbering %d of %d' % (index + 1, len(found)))
    finally:
        # README convention: a tool that writes custom tabs drops Property Explorer's
        # cached scan (also after a cancel: some items may already carry the tab).
        try:
            from namo import propindex
            propindex.invalidate()
        except Exception:
            pass
    return written, errors


def record_for(item, doc=None):
    """The export record of one picked item."""
    from namo import items
    ids = items.revit_ids(item) or {}
    guid = ids.get('unique_id') or ids.get('ifc_guid') or ''
    if not guid:
        try:
            text = str(item.InstanceGuid)
            if text and text.strip('0-') != '':
                guid = text
        except Exception:
            guid = ''
    element = items.object_of(item)
    return {'name': element.DisplayName or item.DisplayName or '',
            'category': items.category(item),
            'element_id': ids.get('element_id') or '',
            'guid': guid,
            'source': items.model_name(item),
            'center': items.center(item)}


def color(found, doc=None):
    """Colours the picked items light to strong along the order, one undo step."""
    from namo import paint
    hexes = gradient(len(found))
    groups = [([item], hex_value, None) for item, hex_value in zip(found, hexes)]
    return paint.apply(groups, doc=_doc(doc), name='Color picked items')
