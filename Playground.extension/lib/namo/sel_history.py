# -*- coding: utf-8 -*-
"""Selection History: every selection recorded per document, Back / Forward / History.

The hook (namo.hk_selhistory) records each selection change as a STATE; Back, Forward
and History move a cursor through them and restore the selection. States live in a
session holder (they outlive runs, not Navisworks), one history per document.

A state is compact on purpose (50 states of 5,000 items must not cost much memory):

    {'sig': text, 'count': int (items selected), 'stored': int (refs kept),
     'time': 'HH:MM:SS', 'category': text, 'models': [file names], 'refs': [(model slot,
     model index, PathId)]}

Back/Forward restore a selection themselves, which fires selection-changed after their
command ends. They store the restored selection's signature as EXPECTED, and the hook
skips the one change that matches it, so moving through history never records itself.

Pure half first (history dicts), API half below (lazy pynavis imports).
"""

import hashlib
import time

MAX_STATES = 50
MAX_ITEMS = 5000
EXPECT_SECONDS = 10.0
CATEGORY_SAMPLE = 20

TOOL = 'playground_selhistory'          # pynavis.settings key (the hook cannot use script config)
DEFAULTS = {'enabled': True, 'record_empty': False}
HOLDER = 'selhistory'


# ---- pure half ----------------------------------------------------------------------


def new_history():
    return {'states': [], 'cursor': -1, 'expected': None, 'expected_at': 0.0, 'alias': None}


def compact(entries):
    """(models, refs) from pynavis.memory entries: model names stored once."""
    models = []
    slots = {}
    refs = []
    for entry in entries:
        name = str(entry.get('m', ''))
        slot = slots.get(name)
        if slot is None:
            slot = len(models)
            slots[name] = slot
            models.append(name)
        refs.append((slot, int(entry.get('i', -1)), str(entry.get('p', ''))))
    return models, refs


def expand(state):
    """pynavis.memory entries back from a state."""
    models = state.get('models') or []
    out = []
    for slot, index, path in state.get('refs') or []:
        name = models[slot] if 0 <= slot < len(models) else ''
        out.append({'m': name, 'i': index, 'p': path})
    return out


def signature(entries, count):
    """Order-independent identity of a selection: its item keys (model file lower +
    PathId) sorted, plus the total count."""
    keys = sorted('%s|%s' % (str(e.get('m', '')).lower(), e.get('p', '')) for e in entries)
    digest = hashlib.sha1()
    digest.update(('%d\n' % int(count)).encode('utf-8'))
    for key in keys:
        digest.update((key + '\n').encode('utf-8'))
    return digest.hexdigest()


def make_state(entries, count, clock_text='', category=''):
    """A state from (at most MAX_ITEMS) entries and the full selection count."""
    entries = list(entries)[:MAX_ITEMS]
    models, refs = compact(entries)
    return {'sig': signature(entries, count), 'count': int(count), 'stored': len(refs),
            'time': clock_text, 'category': category or '', 'models': models, 'refs': refs}


def record(history, state, now=None):
    """Adds a state at the cursor (dropping any forward states). Returns True when it was
    recorded; False when it was the expected restore of Back/Forward/History, or the
    same selection as the current state."""
    now = time.time() if now is None else now
    expected = history.get('expected')
    history['expected'] = None
    if expected is not None and expected == state['sig'] and \
            now - history.get('expected_at', 0.0) <= EXPECT_SECONDS:
        return False
    if is_current(history, state['sig']):
        return False
    states = history['states']
    del states[history['cursor'] + 1:]
    states.append(state)
    if len(states) > MAX_STATES:
        del states[:len(states) - MAX_STATES]
    history['cursor'] = len(states) - 1
    history['alias'] = None
    return True


def is_current(history, sig):
    """True when sig is the state at the cursor, or the selection that restoring it
    actually produced (fewer items when some are gone from the model)."""
    states = history['states']
    cursor = history['cursor']
    if 0 <= cursor < len(states) and states[cursor]['sig'] == sig:
        return True
    alias = history.get('alias')
    return alias is not None and alias[0] == cursor and alias[1] == sig


def expect(history, sig, now=None):
    """Remembers the signature of a selection this tool is about to restore."""
    history['expected'] = sig
    history['expected_at'] = time.time() if now is None else now


def target(history, delta, at_cursor=True):
    """The state index delta steps from the cursor, or None at either end.

    at_cursor=False says the selection on screen is NOT the state at the cursor (it was
    cleared, and clearing is not recorded): Back then returns to the cursor's own state,
    the last selection the user had, instead of skipping over it."""
    index = history['cursor'] + delta
    if not at_cursor and delta < 0:
        index = history['cursor']
    if 0 <= index < len(history['states']):
        return index
    return None


def describe(history, index, resolved=None, missing=0):
    """(message, detail) for a state: 'Selection 3 of 12', '1,204 items, 10:42:05'."""
    state = history['states'][index]
    count = state['count'] if resolved is None else resolved
    noun = 'item' if count == 1 else 'items'
    detail = '%s %s' % ('{:,}'.format(count), noun)
    if state.get('category'):
        detail += ', mostly %s' % state['category']
    if state.get('time'):
        detail += ', selected %s' % state['time']
    if missing:
        detail += ' (%s no longer in the model)' % '{:,}'.format(missing)
    if state['stored'] < state['count']:
        detail += ' (first %s kept)' % '{:,}'.format(state['stored'])
    return 'Selection %d of %d' % (index + 1, len(history['states'])), detail


def list_rows(history):
    """ui.choose rows, newest first: value = state index."""
    rows = []
    states = history['states']
    for index in range(len(states) - 1, -1, -1):
        state = states[index]
        marker = 'Current' if index == history['cursor'] else ''
        rows.append({'value': index,
                     'cells': [index + 1, state.get('time', ''), state['count'],
                               state.get('category', ''), marker]})
    return rows


# ---- settings (read by the hook on every change: cached in the holder) ----------------


def settings(refresh=False):
    """{'enabled', 'record_empty'}: pynavis.settings, cached for the session."""
    from namo import session
    holder = session.holder(HOLDER)
    cached = getattr(holder, 'settings', None)
    if cached is None or refresh:
        try:
            from pynavis import settings as _settings
            cached = _settings.load(TOOL, DEFAULTS)
        except Exception:
            cached = dict(DEFAULTS)
        holder.settings = cached
    return cached


def save_settings(values):
    from namo import session
    from pynavis import settings as _settings
    merged = dict(DEFAULTS)
    merged.update(dict((k, bool(values.get(k, DEFAULTS[k]))) for k in DEFAULTS))
    _settings.save(TOOL, merged)
    session.holder(HOLDER).settings = merged
    return merged


# ---- API half --------------------------------------------------------------------------


def _doc(doc=None):
    if doc is not None:
        return doc
    from pynavis._api import Application
    return Application.ActiveDocument


def doc_key(doc=None):
    """What one document's history is filed under for this session: its file path,
    lowercased ('' for an unsaved one). The history never leaves the session, so no
    folder-safe key is needed, and the hook saves importing namo.paths on every
    selection change."""
    document = _doc(doc)
    try:
        name = document.FileName or ''
    except Exception:
        name = ''
    return str(name).lower()


def history_for(doc=None):
    """The (mutable) history of a document, created on first use."""
    from namo import session
    holder = session.holder(HOLDER)
    docs = getattr(holder, 'docs', None)
    if docs is None:
        docs = {}
        holder.docs = docs
    key = doc_key(doc)
    if key not in docs:
        docs[key] = new_history()
    return docs[key]


def clear(doc=None):
    """Forgets this document's history. Returns how many states were dropped."""
    history = history_for(doc)
    count = len(history['states'])
    history.update(new_history())
    return count


def _top_category(items_):
    from namo import items
    texts = []
    for item in items_[:CATEGORY_SAMPLE]:
        try:
            texts.append(items.category(item))
        except Exception:
            pass
    rows = items.tally([t for t in texts if t])
    return rows[0][0] if rows else ''


def encode(items_, document):
    """pynavis.memory entries ({'m', 'i', 'p'}) for items, reading each model's file name
    once. memory.encode_items asks the model for its name again for every item, which
    is three more interop calls per item: too slow for a hook that runs on every
    selection change with up to MAX_ITEMS items."""
    from pynavis import memory
    models = document.Models
    names = {}
    out = []
    for item in items_:
        path_id = models.CreatePathId(item)
        index = path_id.ModelIndex
        name = names.get(index)
        if name is None:
            name = memory._source_name(models, index)
            names[index] = name
        out.append({'m': name, 'i': index, 'p': path_id.PathId})
    return out


def capture(doc=None):
    """A state for the current selection (None when it cannot be read)."""
    import datetime
    document = _doc(doc)
    selected = document.CurrentSelection.SelectedItems
    count = selected.Count
    first = []
    for item in selected:
        first.append(item)
        if len(first) >= MAX_ITEMS:
            break
    entries = encode(first, document)
    clock = datetime.datetime.now().strftime('%H:%M:%S')
    return make_state(entries, count, clock, _top_category(first))


def restore(history, index, doc=None):
    """Selects state `index`, moves the cursor there and tells the hook to expect it.
    Returns (resolved_count, missing_count)."""
    from namo import items
    document = _doc(doc)
    state = history['states'][index]
    found, missing = items.resolve(expand(state), document)
    restored = signature(encode(found, document), len(found))
    expect(history, restored)
    history['cursor'] = index
    history['alias'] = (index, restored)
    items.select(found, doc=document)
    return len(found), missing


OFF = ('info', 'Selection History is off', 'Shift+Click History to turn recording on.')
EMPTY = ('info', 'No selection history yet', 'Selections are recorded as you make them.')


def sync(doc=None):
    """Records the current selection when the hook missed it (it was made while another
    command ran, when hooks are skipped), so Back always returns to the one before it.
    Returns the history; history['at_cursor'] then says whether the selection on screen
    is the state at the cursor (False after the selection was cleared, which is not
    recorded unless the user asked for it)."""
    document = _doc(doc)
    history = history_for(document)
    current = capture(document)
    if current['count'] or settings().get('record_empty'):
        record(history, current)
    history['at_cursor'] = is_current(history, current['sig'])
    return history


def go(delta, doc=None):
    """Back (-1) or Forward (+1). Returns (level, message, detail) for the toast."""
    if not settings().get('enabled', True):
        return OFF
    document = _doc(doc)
    history = sync(document)
    if not history['states']:
        return EMPTY
    index = target(history, delta, history.get('at_cursor', True))
    if index is None:
        if delta < 0:
            return ('info', 'No earlier selection',
                    'This is the oldest of %d recorded selections.' % len(history['states']))
        return ('info', 'No later selection',
                'This is the newest of %d recorded selections.' % len(history['states']))
    resolved, missing = restore(history, index, document)
    message, detail = describe(history, index, resolved, missing)
    if history['states'][index]['count'] and not resolved:
        return ('warning', message, 'None of its items are in the model any more.')
    return ('warning' if missing else 'success', message, detail)
