# -*- coding: utf-8 -*-
"""Automatic clash snapshot on save (registered for 'doc-saved' in namo.hooks).

Off by default: Shift+Click Snapshot turns it on. When on, each save of a saved model
records one clash history snapshot (namo.clashdata.save_history, the same record the
Snapshot button keeps) for Clash Delta and Clash Trends, but only when all of these
hold, cheapest check first:

  1. the switch is on (one small settings read: the only cost when it is off);
  2. the model has a file name and Playground data is not in 'model' mode (writing into the
     model right after a save would mark it changed again, so the snapshot is skipped
     and the log says why);
  3. the newest snapshot is at least `min_hours` old (default 4);
  4. the chosen tests (default every test with results) hold some results, no more than
     `max_results` (default 50,000) by Clash Detective's own counter, and their counts
     per status differ from the newest snapshot's (nothing to record otherwise).

Only then are the results read (no dialog; the save has already finished). Every failure
is logged and swallowed; a test set over the cap toasts once per session.
"""

import datetime

TOOL = 'playground_clashhistory'
DEFAULTS = {'auto_on_save': False, 'max_results': 50000, 'min_hours': 4.0, 'tests': []}
HOLDER = 'clashhistory'


def load_config(loader=None):
    """The automatic-snapshot settings (pynavis.settings TOOL), normalised. Never raises."""
    try:
        if loader is None:
            from pynavis import settings
            loader = settings.load
        values = loader(TOOL, DEFAULTS)
    except Exception:
        values = dict(DEFAULTS)
    out = dict(DEFAULTS)
    out['auto_on_save'] = bool(values.get('auto_on_save'))
    try:
        out['max_results'] = max(1, int(values.get('max_results')))
    except (TypeError, ValueError):
        pass
    try:
        out['min_hours'] = max(0.0, float(values.get('min_hours')))
    except (TypeError, ValueError):
        pass
    tests = values.get('tests')
    out['tests'] = [str(t) for t in tests] if isinstance(tests, list) else []
    return out


def same_counts(entry, current):
    """True when a snapshot's per-test status counts equal current {test: {status: n}}
    for exactly the same tests."""
    from namo import clashreport as cr
    stored = (entry or {}).get('counts') or {}
    if sorted(stored) != sorted(current):
        return False

    def nonzero(pairs):
        out = {}
        for status, n in pairs:
            if int(n or 0):
                key = cr.status_name(status)
                out[key] = out.get(key, 0) + int(n)
        return out
    for name in current:
        mine = nonzero(current[name].items())
        theirs = nonzero(((stored[name] or {}).get('by_status') or {}).items())
        if mine != theirs:
            return False
    return True


def decide(config, doc_path, data_mode, entries, counts, now):
    """(True, '') when a snapshot should be taken, else (False, reason). PURE.
    counts: {test: {status: n}} of the tests to record (None when not read yet)."""
    from namo import clashrep_history as hist
    if not config.get('auto_on_save'):
        return False, 'off'
    if not doc_path:
        return False, 'the model is not saved to a file'
    if data_mode == 'model':
        return False, 'Playground data is kept in the model, and writing it after a save would mark the model changed'
    if not hist.due_for_auto(entries, now, config.get('min_hours')):
        return False, 'the last snapshot is less than %s hours old' % ('%g' % float(config.get('min_hours') or 0))
    if counts is None:
        return True, ''
    total = sum(sum(int(n) for n in c.values()) for c in counts.values())
    if not total:
        return False, 'no clash results'
    if total > int(config.get('max_results') or DEFAULTS['max_results']):
        return False, '%s results are over the %s cap' % ('{:,}'.format(total),
                                                          '{:,}'.format(int(config.get('max_results'))))
    latest = sorted(entries or [], key=lambda e: (e.get('time') or '', e.get('id') or ''))
    if latest and same_counts(latest[-1], counts):
        return False, 'the clash counts have not changed since the last snapshot'
    return True, ''


def _log(level, message):
    try:
        from namo import session
        session.log(level, 'Clash history: %s' % message)
    except Exception:
        pass


def _warn_once(doc_path, message, detail):
    from namo import session
    held = session.holder(HOLDER)
    warned = getattr(held, 'warned', None)
    if warned is None:
        warned = held.warned = set()
    key = (doc_path or '').lower()
    if key in warned:
        return
    warned.add(key)
    from pynavis import toast
    toast.warning(message, detail)


def take(config, doc=None, now=None):
    """Runs the checks and, when they pass, records the snapshot. Returns (entry or None,
    reason)."""
    import time
    from namo import clashdata, config as namo_config
    from namo import clashreport as cr
    document = cr.active_doc(doc)
    now = now or datetime.datetime.now()
    doc_path, _stem, _title = cr.file_info(document)
    mode = namo_config.get('data_mode')
    entries = clashdata.list_history(doc_path) if doc_path else []
    go, reason = decide(config, doc_path, mode, entries, None, now)
    if not go:
        return None, reason
    from namo import clashset_tests
    if not clashset_tests.available(document):
        return None, 'Clash Detective is not available'
    tests, _missing = cr.resolve_tests(config.get('tests'), document)
    names = clashdata.unique_names([t.DisplayName for t in tests])
    counts = dict((name, cr.status_counts(test)) for name, test in zip(names, tests))
    go, reason = decide(config, doc_path, mode, entries, counts, now)
    if not go:
        if 'cap' in reason:
            _warn_once(doc_path, 'Skipped the automatic clash snapshot',
                       'The tests hold %s. Raise the limit or pick fewer tests with Shift+Click on Snapshot.' % reason)
        return None, reason
    started = time.time()
    rows_by_test = clashdata.snapshot_all(tests, document)
    entry = clashdata.save_history(doc_path, rows_by_test, 'Saved %s' % now.strftime('%Y-%m-%d %H:%M'))
    seconds = time.time() - started
    _log('info', 'snapshot %s of %d tests in %.1f s' % (entry.get('id'), len(tests), seconds))
    return entry, ''


def handle(name, event):
    if name != 'doc-saved':
        return
    config = load_config()
    if not config['auto_on_save']:
        return
    try:
        entry, reason = take(config)
    except Exception:
        import traceback
        _log('error', 'the automatic snapshot failed:\n%s' % traceback.format_exc())
        return
    if entry is None:
        _log('info', 'no automatic snapshot: %s' % reason)
        return
    try:
        from pynavis import toast
        from namo import clashreport as cr
        total = sum(int((c or {}).get('total') or 0) for c in (entry.get('counts') or {}).values())
        toast.info('Clash snapshot saved', '%s and %s, for Clash Delta and Clash Trends.' % (
            cr.plural(len(entry.get('counts') or {}), 'test'), cr.plural(total, 'clash', 'clashes')))
    except Exception:
        pass
