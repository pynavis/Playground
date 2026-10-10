# -*- coding: utf-8 -*-
"""Trade Ghost: one or more trades stay solid, every other model fades.

Models are grouped into trades by their file names (namo.trades with the
user's rules first). The focus is the chosen trades' models, or the current
selection. Everything else is ghosted through namo.items.complement (the
fewest subtrees outside the focus), so the focus keeps whatever colours it
has, in ONE undo step.

What was ghosted is recorded (the session, plus the document's store so a
later session still knows): changing the focus resets exactly those items
before ghosting the new complement, and Clear resets exactly those items,
never colours Playground did not put there. Without a record Clear offers a full
reset of colours and transparency, after asking.

The pure half is tested on both engines; the API half lazy-imports pynavis.
"""

import datetime

from namo import colorize, colors, items, naming, trades

STORE = 'trade-ghost'
HOLDER = 'look_ghost'
SELECTION = '__selection__'
DEFAULTS = {'transparency': 85, 'grey': True, 'trades': []}

CHANGE = 'Change focus'
CLEAR = 'Clear ghost'


# =============================================================================
# Pure half
# =============================================================================


def normalize_config(cfg):
    """{'transparency': 10..95 percent, 'grey': bool, 'trades': [names]}."""
    cfg = cfg or {}
    try:
        percent = int(round(float(cfg.get('transparency', DEFAULTS['transparency']))))
    except (TypeError, ValueError):
        percent = DEFAULTS['transparency']
    percent = max(10, min(95, percent))
    chosen = [str(t) for t in (cfg.get('trades') or []) if str(t).strip()]
    return {'transparency': percent, 'grey': bool(cfg.get('grey', DEFAULTS['grey'])),
            'trades': chosen}


def trade_groups(model_names, rules=None, order=None):
    """[(trade, [model names])] for model file names: trades in `order` (the
    configured trade list) first, then any other trade in natural order;
    'Unassigned' last; models in natural order inside a trade."""
    groups = {}
    for name in model_names:
        groups.setdefault(trades.trade_of(name, rules), []).append(name)
    order = list(order or [])

    def key(trade):
        if trade == trades.UNASSIGNED:
            return (2, 0, '')
        if trade in order:
            return (0, order.index(trade), '')
        return (1, 0, naming.natural_key(trade))
    return [(trade, sorted(groups[trade], key=naming.natural_key)) for trade in sorted(groups, key=key)]


def names_text(names, limit=3):
    """'A.nwc, B.nwc and 4 more'."""
    shown = ', '.join(names[:limit])
    if len(names) > limit:
        shown += ' and %s more' % colorize.count_text(len(names) - limit)
    return shown


def chooser_rows(groups, selection_count):
    """ui.choose rows: the selection first (when there is one), then a row per
    trade with its model count and names."""
    rows = []
    if selection_count:
        rows.append({'value': SELECTION,
                     'cells': ['Current selection', colorize.plural(selection_count, 'item'), '']})
    for trade, names in groups:
        rows.append({'value': trade, 'cells': [trade, colorize.plural(len(names), 'model'),
                                               names_text(names)]})
    return rows


def focus_label(chosen):
    """'Mechanical and Plumbing', 'the selection', 'Mechanical, Plumbing and the selection'."""
    parts = [c for c in chosen if c != SELECTION]
    if SELECTION in chosen:
        parts.append('the selection')
    if not parts:
        return 'nothing'
    if len(parts) == 1:
        return parts[0]
    return '%s and %s' % (', '.join(parts[:-1]), parts[-1])


def make_record(entries, label, cfg, now=None):
    return {'version': 1, 'entries': list(entries), 'focus': label,
            'transparency': cfg['transparency'], 'grey': cfg['grey'],
            'time': (now or datetime.datetime.now()).strftime('%Y-%m-%dT%H:%M:%S')}


def valid_record(record):
    return isinstance(record, dict) and isinstance(record.get('entries'), list) and bool(record['entries'])


def config_fields(cfg):
    return [
        {'kind': 'int', 'key': 'transparency', 'label': 'Transparency of everything else',
         'min': 10, 'max': 95, 'suffix': '%', 'default': cfg['transparency'],
         'hint': '85% keeps the context readable without hiding the focus.'},
        {'kind': 'check', 'key': 'grey', 'label': 'Also turn it neutral grey', 'default': cfg['grey']},
    ]


# =============================================================================
# API half
# =============================================================================


def _doc(doc):
    if doc is not None:
        return doc
    from pynavis._api import Application
    return Application.ActiveDocument


def _doc_path(document):
    try:
        return str(document.FileName or '')
    except Exception:
        return ''


def model_groups(doc=None):
    """([(trade, [model dicts])], models) for the document's models."""
    from namo import config
    models = items.models(_doc(doc))
    rules = trades.rules_from_config()
    order = config.get('trades') or []
    by_name = {}
    for model in models:
        by_name.setdefault(model['name'] or model['file'] or 'Model %d' % (model['index'] + 1), []).append(model)
    groups = trade_groups(sorted(by_name), rules, order)
    return [(trade, [m for name in names for m in by_name[name]]) for trade, names in groups], models


def focus_items(chosen, groups, doc=None):
    """The items to keep solid: chosen trades' model roots plus, with SELECTION
    chosen, the selected items."""
    out = []
    by_trade = dict(groups)
    for value in chosen:
        if value == SELECTION:
            out.extend(items.selected(_doc(doc)))
        else:
            out.extend(m['root'] for m in by_trade.get(value, []))
    return items.dedupe(out)


def _holder():
    from namo import session
    return session.holder(HOLDER)


def load_record(doc=None):
    """The ghost record for the active document (session first, then the
    document's store), or None."""
    from namo import store
    document = _doc(doc)
    key = _doc_path(document).lower()
    records = getattr(_holder(), 'records', None) or {}
    if valid_record(records.get(key)):
        return records[key]
    try:
        record = store.for_active_doc(STORE, doc=document).load(None)
    except Exception:
        record = None
    return record if valid_record(record) else None


def save_record(record, doc=None):
    """Keeps the record in the session and the document's store (a store
    failure is logged; the session copy still works)."""
    from namo import session, store
    document = _doc(doc)
    key = _doc_path(document).lower()
    holder = _holder()
    records = getattr(holder, 'records', None)
    if records is None:
        records = {}
        holder.records = records
    if record is None:
        records.pop(key, None)
    else:
        records[key] = record
    try:
        target = store.for_active_doc(STORE, doc=document)
        if record is None:
            target.delete()
        else:
            target.save(record)
    except Exception as error:
        session.log('warning', 'trade ghost record not stored: %s' % error)


def ghost(keep, cfg, previous=None, doc=None):
    """Ghosts everything outside keep (transparency, grey when cfg says so),
    first resetting the items a previous ghost touched. ONE undo step.
    Returns the items ghosted."""
    from namo import paint
    from pynavis.viewpoints import transaction
    document = _doc(doc)
    others = items.complement(keep, document)
    with transaction('Trade ghost', document):
        if previous:
            paint.reset(previous, document, 'Trade ghost')
        if others:
            paint.apply([(others, colors.GHOST if cfg['grey'] else None,
                          cfg['transparency'] / 100.0)], document, 'Trade ghost')
    return others


def clear(record, doc=None):
    """Resets the items a recorded ghost touched. Returns (reset, missing)."""
    from namo import paint
    document = _doc(doc)
    found, missing = items.resolve(record.get('entries') or [], document)
    count = paint.reset(found, document, 'Clear ghost') if found else 0
    return count, missing
