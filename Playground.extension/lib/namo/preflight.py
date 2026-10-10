# -*- coding: utf-8 -*-
"""Preflight: is this document ready to share? A profile of checks, each pass, warn or fail.

A profile names which checks run, which of them FAIL (block NWD Publisher) and which
only warn, and the parameters some need (expected models, required selection sets,
the New clash limit, the minimum number of saved viewpoints). The built-in 'Standard'
profile ships in code and is always there; saved profiles live in
namo.templates('preflight') (team-shared when a shared folder is set). A saved
profile called 'Standard' replaces the built-in one until it is deleted.

Two halves:
  * pure: DEFAULT_PROFILE, normalize_profile(), evaluate(facts, profile) -> checks,
    summarize(), toast_text(). Everything that decides a result is here and unit
    tested; facts is a plain dict (see gather_facts for its keys).
  * API: gather_facts(doc, profile, progress) reads the document (only what the
    enabled checks need) and run_profile() = gather + evaluate. NWD Publisher calls
    run_profile before it publishes.

A check result is {'id', 'name', 'level' ('pass' | 'info' | 'warn' | 'fail'),
'detail'}. 'info' means "nothing to judge" (not configured, not available here).
"""

import copy
import datetime
import fnmatch

TEMPLATES_TOOL = 'preflight'
DEFAULT_NAME = 'Standard'

# (id, name shown to people, level when it goes wrong), in the order they run.
CHECKS = [
    ('saved', 'Document saved', 'fail'),
    ('units', 'Units consistent', 'warn'),
    ('expected_models', 'Expected models present', 'fail'),
    ('stale', 'Model files current', 'warn'),
    ('sets', 'Required selection sets', 'fail'),
    ('clash_run', 'Clash tests run after the newest models', 'warn'),
    ('new_clashes', 'New clashes within the limit', 'warn'),
    ('viewpoints', 'Saved viewpoints present', 'warn'),
    ('hidden', 'No hidden items', 'warn'),
    ('overrides', 'No leftover appearance overrides', 'warn'),
    ('section', 'Sectioning off', 'warn'),
    ('timeliner', 'TimeLiner tasks attached', 'warn'),
]
CHECK_IDS = [c[0] for c in CHECKS]
CHECK_NAMES = dict((c[0], c[1]) for c in CHECKS)
OFF_BY_DEFAULT = ('timeliner',)

LIMITS = {
    'max_new_clashes': 0,       # -1 turns the limit off; 0 means no New clashes at all
    'min_viewpoints': 1,
    'hidden_budget': 500000,    # items walked looking for a hidden one
    'override_sample': 20000,   # geometry items whose colour is compared (best effort)
    'clash_budget': 200000,     # clash results read when counting New ones
}


def _default_checks():
    out = {}
    for check_id, _name, level in CHECKS:
        out[check_id] = {'enabled': check_id not in OFF_BY_DEFAULT, 'level': level}
    return out


DEFAULT_PROFILE = {
    'name': DEFAULT_NAME,
    'checks': _default_checks(),
    'expected_models': [],
    'required_sets': [],
    'max_new_clashes': LIMITS['max_new_clashes'],
    'min_viewpoints': LIMITS['min_viewpoints'],
    'hidden_budget': LIMITS['hidden_budget'],
    'override_sample': LIMITS['override_sample'],
    'clash_budget': LIMITS['clash_budget'],
}


# ---- pure: profiles -------------------------------------------------------------------


def _lines(value):
    """A list of non-blank stripped strings from a list or from text (one per line)."""
    if value is None:
        return []
    if isinstance(value, str):
        value = value.replace('\r', '\n').split('\n')
    out = []
    for item in value:
        text = str(item or '').strip()
        if text and text not in out:
            out.append(text)
    return out


parse_lines = _lines


def _int(value, default, low=None):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    if low is not None and number < low:
        return low
    return number


def normalize_profile(profile):
    """A complete, valid profile from any partial dict: every check present with
    'enabled' (bool) and 'level' ('fail' or 'warn'), lists of patterns cleaned,
    numbers made ints in range. Unknown check ids are dropped."""
    source = profile if isinstance(profile, dict) else {}
    out = copy.deepcopy(DEFAULT_PROFILE)
    name = str(source.get('name') or '').strip()
    out['name'] = name or 'Untitled'
    checks = source.get('checks') if isinstance(source.get('checks'), dict) else {}
    for check_id in CHECK_IDS:
        given = checks.get(check_id)
        if not isinstance(given, dict):
            continue
        if 'enabled' in given:
            out['checks'][check_id]['enabled'] = bool(given['enabled'])
        level = str(given.get('level') or '').lower()
        if level in ('fail', 'warn'):
            out['checks'][check_id]['level'] = level
    out['expected_models'] = _lines(source.get('expected_models'))
    out['required_sets'] = _lines(source.get('required_sets'))
    out['max_new_clashes'] = _int(source.get('max_new_clashes'), LIMITS['max_new_clashes'], -1)
    out['min_viewpoints'] = _int(source.get('min_viewpoints'), LIMITS['min_viewpoints'], 0)
    out['hidden_budget'] = _int(source.get('hidden_budget'), LIMITS['hidden_budget'], 1000)
    out['override_sample'] = _int(source.get('override_sample'), LIMITS['override_sample'], 0)
    out['clash_budget'] = _int(source.get('clash_budget'), LIMITS['clash_budget'], 1000)
    return out


def enabled_checks(profile):
    """Ids of the checks the profile runs, in run order."""
    checks = normalize_profile(profile)['checks']
    return [c for c in CHECK_IDS if checks[c]['enabled']]


def blocking_checks(profile):
    """Ids of the enabled checks that fail (rather than warn), in run order."""
    checks = normalize_profile(profile)['checks']
    return [c for c in CHECK_IDS if checks[c]['enabled'] and checks[c]['level'] == 'fail']


def profile_from_choices(name, enabled, blocking, expected_models, required_sets,
                         max_new_clashes, min_viewpoints, base=None):
    """The profile a settings form describes: `enabled` and `blocking` are lists of check
    ids (blocking ones fail, the rest warn); the rest as in normalize_profile."""
    profile = normalize_profile(base or DEFAULT_PROFILE)
    profile['name'] = name
    for check_id in CHECK_IDS:
        profile['checks'][check_id] = {'enabled': check_id in (enabled or []),
                                       'level': 'fail' if check_id in (blocking or []) else 'warn'}
    profile['expected_models'] = expected_models
    profile['required_sets'] = required_sets
    profile['max_new_clashes'] = max_new_clashes
    profile['min_viewpoints'] = min_viewpoints
    return normalize_profile(profile)


def profile_form_fields(base, deletable=False, delete_label='Delete this profile'):
    """The profile editor form (namo.ui.form fields) pre-filled from a profile. Keys:
    name, enabled, blocking, expected, sets, max_new, min_views (and delete when
    deletable)."""
    base = normalize_profile(base)
    options = [(name, check_id) for check_id, name, _level in CHECKS]
    fields = [
        {'kind': 'text', 'key': 'name', 'label': 'Profile name', 'default': base['name'],
         'required': True},
        {'kind': 'multi', 'key': 'enabled', 'label': 'Checks to run', 'options': options,
         'default': enabled_checks(base)},
        {'kind': 'multi', 'key': 'blocking', 'label': 'Checks that fail and block publishing',
         'options': options, 'default': blocking_checks(base),
         'hint': 'The other checks only warn.'},
        {'kind': 'textarea', 'key': 'expected', 'label': 'Expected models', 'rows': 4,
         'default': '\n'.join(base['expected_models']),
         'hint': 'One file name per line; * and ? match any text, and ARCH finds ARCH.nwc.'},
        {'kind': 'textarea', 'key': 'sets', 'label': 'Required selection sets', 'rows': 3,
         'default': '\n'.join(base['required_sets']),
         'hint': 'One per line, as Folder/Set name.'},
        {'kind': 'int', 'key': 'max_new', 'label': 'Most New clashes allowed', 'min': -1,
         'default': base['max_new_clashes'],
         'hint': '0 means none may be New; -1 turns the limit off.'},
        {'kind': 'int', 'key': 'min_views', 'label': 'Fewest saved viewpoints', 'min': 0,
         'default': base['min_viewpoints']},
    ]
    if deletable:
        fields.append({'kind': 'check', 'key': 'delete', 'label': delete_label, 'default': False})
    return fields


def profile_from_form(values, base=None):
    """The profile a filled profile_form_fields form describes."""
    return profile_from_choices(
        str(values.get('name') or '').strip(), values.get('enabled') or [],
        values.get('blocking') or [], parse_lines(values.get('expected')),
        parse_lines(values.get('sets')),
        values.get('max_new') if values.get('max_new') is not None else 0,
        values.get('min_views') if values.get('min_views') is not None else 0, base)


def describe_profile(profile):
    """'12 checks, 4 block publishing' for lists and toasts."""
    on = len(enabled_checks(profile))
    blocking = len(blocking_checks(profile))
    return '%d check%s, %d block%s publishing' % (on, '' if on == 1 else 's', blocking,
                                                  's' if blocking == 1 else '')


# ---- pure: helpers ----------------------------------------------------------------------


def _plural(count, noun, plural_form=None):
    word = noun if count == 1 else (plural_form or noun + 's')
    return '%s %s' % ('{:,}'.format(count), word)


def _names(names, limit=3):
    names = [str(n) for n in names]
    if len(names) <= 1:
        return ''.join(names)
    if len(names) <= limit:
        return '%s and %s' % (', '.join(names[:-1]), names[-1])
    return '%s and %d more' % (', '.join(names[:limit]), len(names) - limit)


def _when(value):
    if value is None:
        return ''
    try:
        return value.strftime('%Y-%m-%d %H:%M')
    except Exception:
        return str(value)


def pattern_matches(pattern, name):
    """True when a model name matches an expected-model pattern: * and ? wildcards,
    case-insensitive, against the whole name or the name without its extension
    ('ARCH' and 'ARCH*' both find 'ARCH.nwc')."""
    wanted = str(pattern or '').strip().lower()
    text = str(name or '').strip().lower()
    if not wanted or not text:
        return False
    stem = text.rsplit('.', 1)[0] if '.' in text else text
    return fnmatch.fnmatchcase(text, wanted) or fnmatch.fnmatchcase(stem, wanted)


def missing_patterns(patterns, names):
    """The patterns no model name matches, in pattern order."""
    return [p for p in patterns if not any(pattern_matches(p, n) for n in names)]


def _soft(level):
    """A sub-condition that is never worse than a warning."""
    return 'warn'


def _result(check_id, level, detail):
    return {'id': check_id, 'name': CHECK_NAMES[check_id], 'level': level, 'detail': detail}


# ---- pure: evaluators (facts, profile, level) -> (level, detail) ---------------------------


def _check_saved(facts, profile, level):
    if 'doc_file' not in facts:
        return 'info', 'Not checked.'
    path = facts.get('doc_file') or ''
    if not path:
        return level, 'The document has never been saved. Save it as an NWF first.'
    name = path.replace('\\', '/').split('/')[-1]
    if facts.get('modified'):
        return _soft(level), '%s has unsaved changes.' % name
    return 'pass', '%s is saved.' % name


def _check_units(facts, profile, level):
    models = facts.get('models')
    if models is None:
        return 'info', 'Not checked.'
    if not models:
        return 'info', 'No models are appended.'
    groups = {}
    for model in models:
        groups.setdefault(model.get('units') or 'Unknown units', []).append(model.get('name', ''))
    ordered = sorted(groups.items(), key=lambda pair: (-len(pair[1]), pair[0]))
    if len(ordered) == 1:
        if len(models) == 1:
            return 'pass', 'The model is in %s.' % ordered[0][0]
        return 'pass', 'All %d models are in %s.' % (len(models), ordered[0][0])
    parts = []
    for index, (units, names) in enumerate(ordered):
        if index == 0:
            parts.append('%d in %s' % (len(names), units))
        else:
            parts.append('%d in %s (%s)' % (len(names), units, _names(names)))
    return level, 'Mixed units: %s.' % ', '.join(parts)


def _check_expected(facts, profile, level):
    patterns = profile['expected_models']
    if not patterns:
        return 'info', 'This profile lists no expected models.'
    models = facts.get('models')
    if models is None:
        return 'info', 'Not checked.'
    missing = missing_patterns(patterns, [m.get('name', '') for m in models])
    if missing:
        return level, 'Missing: %s.' % _names(missing, 5)
    if len(patterns) == 1:
        return 'pass', 'The expected model is appended.'
    return 'pass', 'All %d expected models are appended.' % len(patterns)


def _check_stale(facts, profile, level):
    rows = facts.get('stale')
    if rows is None:
        return 'info', 'Not checked.'
    if not rows:
        return 'info', 'No models are appended.'
    late = [r['name'] for r in rows if r.get('status') == 'Out of date']
    lost = [r['name'] for r in rows if r.get('status') in ('File not found', 'Folder offline')]
    if late or lost:
        parts = []
        if late:
            parts.append('%s out of date (%s)' % (_plural(len(late), 'model'), _names(late)))
        if lost:
            parts.append('%s not found (%s)' % (_plural(len(lost), 'file'), _names(lost)))
        return level, '%s. Refresh, or re-export the models.' % '; '.join(parts)
    unknown = [r for r in rows if r.get('status') in ('Source not found', 'Source folder offline')]
    detail = 'All %s are current.' % _plural(len(rows), 'model file')
    if unknown:
        detail += ' %d have no source file on this computer to compare with.' % len(unknown)
    return 'pass', detail


def _check_sets(facts, profile, level):
    wanted = profile['required_sets']
    if not wanted:
        return 'info', 'This profile lists no required selection sets.'
    found = facts.get('sets_found')
    if found is None:
        return 'info', 'Not checked.'
    missing = [path for path in wanted if not found.get(path)]
    if missing:
        return level, 'Missing: %s.' % _names(missing, 5)
    if len(wanted) == 1:
        return 'pass', 'The required set exists.'
    return 'pass', 'All %d required sets exist.' % len(wanted)


def _check_clash_run(facts, profile, level):
    clash = facts.get('clash')
    if clash is None:
        return 'info', 'Not checked.'
    if not clash.get('available'):
        return 'info', 'Clash Detective is not available here.'
    tests = clash.get('tests') or []
    if not tests:
        return level, 'There are no clash tests. Set up and run them in Clash Detective.'
    newest = facts.get('newest_model_time')
    never = [t['name'] for t in tests if t.get('last_run') is None]
    old = []
    if newest is not None:
        limit = newest - datetime.timedelta(seconds=1)
        old = [t['name'] for t in tests if t.get('last_run') is not None and t['last_run'] < limit]
    if never or old:
        parts = []
        if never:
            parts.append('%s never run (%s)' % (_plural(len(never), 'test'), _names(never)))
        if old:
            parts.append('%s run before the newest model data of %s (%s)'
                         % (_plural(len(old), 'test'), _when(newest), _names(old)))
        return level, '%s. Run all tests again.' % '; '.join(parts)
    if newest is None:
        return 'pass', 'All %s have been run (the model file times are unknown).' % _plural(len(tests), 'test')
    return 'pass', 'All %s ran after the newest model data of %s.' % (_plural(len(tests), 'test'), _when(newest))


def _check_new_clashes(facts, profile, level):
    limit = profile['max_new_clashes']
    if limit < 0:
        return 'info', 'This profile sets no limit.'
    data = facts.get('new_clashes')
    if data is None:
        return 'info', 'Not checked.'
    if not data.get('available'):
        return 'info', 'Clash Detective is not available here.'
    count = int(data.get('count') or 0)
    sampled = bool(data.get('sampled'))
    if count > limit:
        if sampled:
            text = 'At least %s in the first %s results' % (
                _plural(count, 'New clash', 'New clashes'), '{:,}'.format(int(data.get('checked') or 0)))
        else:
            text = _plural(count, 'New clash', 'New clashes')
        if limit == 0:
            return level, '%s; review them before publishing.' % text
        return level, '%s; the limit is %s.' % (text, '{:,}'.format(limit))
    if count == 0:
        detail = 'No New clashes.'
    else:
        detail = '%s, within the limit of %s.' % (_plural(count, 'New clash', 'New clashes'),
                                                 '{:,}'.format(limit))
    if sampled:
        detail += ' Only the first %s results were read.' % '{:,}'.format(int(data.get('checked') or 0))
    return 'pass', detail


def _check_viewpoints(facts, profile, level):
    count = facts.get('viewpoints')
    if count is None:
        return 'info', 'Not checked.'
    wanted = profile['min_viewpoints']
    if count < wanted:
        if count == 0:
            return level, 'There are no saved viewpoints.'
        return level, '%s; this profile asks for at least %s.' % (
            _plural(count, 'saved viewpoint'), '{:,}'.format(wanted))
    if count == 0:
        return 'pass', 'No saved viewpoints, and none are required.'
    return 'pass', '%s.' % _plural(count, 'saved viewpoint')


def _check_hidden(facts, profile, level):
    data = facts.get('hidden')
    if data is None:
        return 'info', 'Not checked.'
    if data.get('found'):
        example = data.get('example')
        where = (" (for example '%s')" % example) if example else ''
        return level, 'Hidden items%s. Unhide them, or publish with hidden items left out.' % where
    checked = int(data.get('checked') or 0)
    if data.get('sampled'):
        return 'pass', 'No hidden items in the first %s items checked.' % '{:,}'.format(checked)
    return 'pass', 'No hidden items (%s checked).' % _plural(checked, 'item')


def _check_overrides(facts, profile, level):
    data = facts.get('overrides')
    if data is None:
        return 'info', 'Not checked.'
    if not data.get('readable'):
        return 'info', 'Item colours could not be read here (best effort).'
    checked = int(data.get('checked') or 0)
    found = int(data.get('found') or 0)
    if not checked:
        return 'info', 'No geometry to sample.'
    scope = ('%s sampled' if data.get('sampled') else '%s') % _plural(checked, 'geometry item')
    if found:
        return level, 'Colour or transparency overrides on %s of %s (best effort). Reset appearance before publishing if they are not meant to stay.' % (
            '{:,}'.format(found), scope)
    return 'pass', 'No overrides found in %s (best effort).' % scope


def _check_section(facts, profile, level):
    state = facts.get('section_on')
    if state is None:
        return 'info', 'Not checked.'
    if state:
        return level, 'Sectioning is on in the current view.'
    return 'pass', 'Sectioning is off.'


def _check_timeliner(facts, profile, level):
    data = facts.get('timeliner')
    if data is None:
        return 'info', 'Not checked.'
    if not data.get('available'):
        return 'info', 'TimeLiner is not available here.'
    tasks = int(data.get('tasks') or 0)
    if not tasks:
        return 'info', 'There are no TimeLiner tasks.'
    unattached = int(data.get('unattached') or 0)
    if unattached:
        examples = data.get('examples') or []
        where = (': %s' % _names(examples)) if examples else ''
        return level, '%s of %s have nothing attached%s.' % (
            '{:,}'.format(unattached), _plural(tasks, 'task'), where)
    return 'pass', 'All %s have items attached.' % _plural(tasks, 'task')


_EVALUATORS = {
    'saved': _check_saved, 'units': _check_units, 'expected_models': _check_expected,
    'stale': _check_stale, 'sets': _check_sets, 'clash_run': _check_clash_run,
    'new_clashes': _check_new_clashes, 'viewpoints': _check_viewpoints,
    'hidden': _check_hidden, 'overrides': _check_overrides, 'section': _check_section,
    'timeliner': _check_timeliner,
}


def evaluate(facts, profile):
    """Check results for every enabled check, in run order, from a facts dict. A
    check whose facts are missing reports 'info' ('Not checked.'); one that raises
    reports 'info' with the reason, so a bad fact never hides the other results."""
    profile = normalize_profile(profile)
    facts = facts or {}
    out = []
    for check_id in CHECK_IDS:
        setting = profile['checks'][check_id]
        if not setting['enabled']:
            continue
        try:
            level, detail = _EVALUATORS[check_id](facts, profile, setting['level'])
        except Exception as error:
            level, detail = 'info', 'Could not be checked: %s' % (str(error) or type(error).__name__)
        out.append(_result(check_id, level, detail))
    return out


def summarize(checks):
    """{'total', 'passed', 'warnings', 'failures', 'infos', 'level'} where level is the
    worst result ('fail', 'warn', 'pass'; 'info' when nothing was judged)."""
    counts = {'pass': 0, 'warn': 0, 'fail': 0, 'info': 0}
    for check in checks:
        counts[check.get('level', 'info')] = counts.get(check.get('level', 'info'), 0) + 1
    if counts['fail']:
        level = 'fail'
    elif counts['warn']:
        level = 'warn'
    elif counts['pass']:
        level = 'pass'
    else:
        level = 'info'
    return {'total': len(checks), 'passed': counts['pass'], 'warnings': counts['warn'],
            'failures': counts['fail'], 'infos': counts['info'], 'level': level}


def summary_text(checks):
    """'passed' / '2 failed, 1 warning' (for history records and confirms)."""
    s = summarize(checks)
    if not s['failures'] and not s['warnings']:
        return 'passed'
    parts = []
    if s['failures']:
        parts.append('%d failed' % s['failures'])
    if s['warnings']:
        parts.append(_plural(s['warnings'], 'warning'))
    return ', '.join(parts)


def toast_text(checks):
    """(toast level, message, detail) for a finished preflight."""
    s = summarize(checks)
    failed = [c['name'] for c in checks if c['level'] == 'fail']
    warned = [c['name'] for c in checks if c['level'] == 'warn']
    if not checks:
        return ('info', 'Preflight ran no checks', 'Turn checks on with Shift+Click.')
    if failed:
        message = 'Preflight: %s failed' % _plural(len(failed), 'check')
        detail = _names(failed)
        if warned:
            detail += '; %s.' % _plural(len(warned), 'warning')
        return ('error', message, detail)
    if warned:
        return ('warning', 'Preflight: %s' % _plural(len(warned), 'warning'), _names(warned))
    if not s['passed']:
        return ('info', 'Preflight had nothing to judge', 'Every check was skipped or not configured.')
    return ('success', 'Preflight passed: %s' % _plural(s['passed'], 'check'),
            ('%d not configured.' % s['infos']) if s['infos'] else None)


def failures_text(checks):
    """'Document saved, Expected models present' for the publish-anyway question."""
    return _names([c['name'] for c in checks if c['level'] == 'fail'], 4)


def output_html(checks, profile_name, doc_name=''):
    """Output-window markup: heading, KPI row and the checklist."""
    from namo import mdl_output
    s = summarize(checks)
    title = 'Preflight: %s' % (doc_name or 'untitled document')
    parts = [mdl_output.heading(title),
             mdl_output.note('Profile %s, %s.' % (profile_name, _when(datetime.datetime.now()))),
             mdl_output.kpis([('Passed', s['passed'], 'pass' if s['passed'] else None),
                              ('Warnings', s['warnings'], 'warn' if s['warnings'] else None),
                              ('Failures', s['failures'], 'fail' if s['failures'] else None)]),
             mdl_output.checklist(checks)]
    return ''.join(parts)


# ---- profiles in templates -------------------------------------------------------------------


def _templates():
    from namo import templates
    return templates.Templates(TEMPLATES_TOOL)


def profile_names():
    """'Standard' first (built in, or a saved profile of that name), then the saved
    profiles in natural order."""
    try:
        saved = _templates().names()
    except Exception:
        saved = []
    others = [n for n in saved if n.strip().lower() != DEFAULT_NAME.lower()]
    return [DEFAULT_NAME] + others


def load_profile(name):
    """The normalized profile called name (a saved one first, else the built-in
    Standard), or None when there is no such profile."""
    try:
        stored = _templates().get(name)
    except Exception:
        stored = None
    if stored is not None:
        stored['name'] = stored.get('name') or name
        profile = normalize_profile(stored)
        profile['name'] = name if str(name).strip().lower() != DEFAULT_NAME.lower() else DEFAULT_NAME
        return profile
    if str(name or '').strip().lower() == DEFAULT_NAME.lower():
        return normalize_profile(DEFAULT_PROFILE)
    return None


def is_saved(name):
    """True when a saved (template) profile of that name exists."""
    try:
        return _templates().get(name) is not None
    except Exception:
        return False


def save_profile(profile):
    """Saves a profile under its name; returns the stored name. IOError on failure."""
    profile = normalize_profile(profile)
    return _templates().save(profile['name'], profile)


def delete_profile(name):
    return _templates().delete(name)


# ---- API half ------------------------------------------------------------------------------------


def _doc(doc):
    if doc is not None:
        return doc
    from pynavis._api import Application
    return Application.ActiveDocument


class _Stages(object):
    """Maps per-stage progress onto one 0..1 bar: stage k of n."""

    def __init__(self, report, count):
        self.report = report
        self.count = max(1, count)
        self.index = 0

    def start(self, label):
        if self.report is not None:
            self.report(float(self.index) / self.count, label)
        self.index += 1

    def inside(self, fraction, label):
        if self.report is not None:
            base = float(max(0, self.index - 1)) / self.count
            self.report(base + max(0.0, min(1.0, fraction)) / self.count, label)


def _model_facts(doc):
    from namo import modelmgmt
    infos = modelmgmt.models_info(doc)
    return infos, [{'name': i['name'], 'units': i['units']} for i in infos]


def _clash_facts(doc):
    try:
        from namo import clashdata
        tests = clashdata.tests(doc)
    except Exception:
        return {'available': False, 'tests': []}, []
    from namo import clashdata, dates
    rows = []
    for test in tests:
        try:
            last = test.LastRun
        except Exception:
            last = None
        rows.append({'name': clashdata.test_path(test), 'last_run': dates.from_net(last)})
    return {'available': True, 'tests': rows}, tests


def _new_clash_facts(tests, budget, stages):
    try:
        from pynavis import clash
    except Exception:
        return {'available': False, 'count': 0, 'checked': 0, 'sampled': False}
    count = checked = 0
    sampled = False
    for test in tests:
        for result in clash.walk_results(test):
            checked += 1
            try:
                if str(result.Status) == 'New':
                    count += 1
            except Exception:
                pass
            if checked % 5000 == 0:
                stages.inside(float(checked) / budget, 'Counting New clashes (%s)' % '{:,}'.format(checked))
            if checked >= budget:
                sampled = True
                break
        if sampled:
            break
    return {'available': True, 'count': count, 'checked': checked, 'sampled': sampled}


def _viewpoint_count(doc):
    from pynavis import doc as _pdoc
    return sum(1 for _pair in _pdoc.walk_saved_viewpoints(doc))


def _colors_differ(a, b, tol=1e-3):
    return abs(a.R - b.R) > tol or abs(a.G - b.G) > tol or abs(a.B - b.B) > tol


def _item_path(item, depth=3):
    names = []
    node = item
    while node is not None and len(names) < depth:
        try:
            names.append(node.DisplayName or node.ClassDisplayName or '')
        except Exception:
            break
        node = node.Parent
    names.reverse()
    return ' > '.join(n for n in names if n)


def _walk_hidden_overrides(infos, want_hidden, want_overrides, budget, sample, stages):
    """One pass over every model: the first hidden item (own IsHidden flag) and how many
    of the first `sample` geometry items carry a colour or transparency override."""
    hidden = {'found': False, 'example': None, 'checked': 0, 'sampled': False}
    overrides = {'readable': True, 'found': 0, 'checked': 0, 'sampled': False}
    walked = 0
    hidden_done = not want_hidden
    overrides_done = not want_overrides or sample <= 0
    stopped = False
    for info in infos:
        if stopped:
            break
        for item in info['root'].DescendantsAndSelf:
            walked += 1
            if not hidden_done:
                try:
                    if item.IsHidden:
                        hidden['found'] = True
                        hidden['example'] = _item_path(item)
                        hidden_done = True
                except Exception:
                    pass
            if not overrides_done and overrides['readable']:
                try:
                    if item.HasGeometry:
                        geometry = item.Geometry
                        overrides['checked'] += 1
                        if (_colors_differ(geometry.PermanentColor, geometry.OriginalColor) or
                                abs(geometry.PermanentTransparency - geometry.OriginalTransparency) > 1e-3):
                            overrides['found'] += 1
                        if overrides['checked'] >= sample:
                            overrides['sampled'] = True
                            overrides_done = True
                except Exception:
                    overrides['readable'] = False
                    overrides_done = True
            if walked % 5000 == 0:
                stages.inside(float(walked) / budget, 'Checking items (%s)' % '{:,}'.format(walked))
            if hidden_done and overrides_done:
                stopped = True
                break
            if walked >= budget:
                hidden['sampled'] = not hidden_done
                if not overrides_done:
                    overrides['sampled'] = True
                stopped = True
                break
    hidden['checked'] = walked
    return hidden, overrides


def timeliner_of(doc):
    """The document's DocumentTimeliner, or None when TimeLiner is not available."""
    try:
        from pynavis import _api
        _api.add_reference('Autodesk.Navisworks.Timeliner')
        from Autodesk.Navisworks.Api.Timeliner import DocumentTimeliner
        return DocumentTimeliner.TimelinerInstance(doc)
    except Exception:
        return None


def _timeliner_facts(doc):
    timeliner = timeliner_of(doc)
    if timeliner is None:
        return {'available': False}
    tasks = 0
    unattached = 0
    examples = []
    stack = list(timeliner.TasksRoot.Children)
    stack.reverse()
    while stack:
        task = stack.pop()
        try:
            children = list(task.Children)
        except Exception:
            children = []
        if children:
            children.reverse()
            stack.extend(children)
            continue
        tasks += 1
        try:
            empty = bool(task.Selection.IsClear)
        except Exception:
            empty = False
        if empty:
            unattached += 1
            if len(examples) < 3:
                examples.append(task.DisplayName)
    return {'available': True, 'tasks': tasks, 'unattached': unattached, 'examples': examples}


def gather_facts(doc=None, profile=None, progress=None):
    """The facts evaluate() needs for the profile's enabled checks, read from the
    document. progress(fraction, label) may raise a Cancelled to stop."""
    from namo import modelmgmt
    document = _doc(doc)
    profile = normalize_profile(profile or DEFAULT_PROFILE)
    wanted = set(enabled_checks(profile))
    stages = _Stages(progress, 6)
    facts = {}

    stages.start('Reading the models')
    infos, models = _model_facts(document)
    if 'saved' in wanted:
        try:
            from pynavis import doc as _pdoc
            facts['doc_file'] = _pdoc.get_filename(document) or ''
        except Exception:
            facts['doc_file'] = ''
        try:
            facts['modified'] = bool(document.IsModified)
        except Exception:
            facts['modified'] = False
    facts['models'] = models

    stages.start('Checking model files')
    stale = None
    if wanted & set(['stale', 'clash_run']):
        stale = modelmgmt.stale_rows(document, infos)
        facts['stale'] = stale
        newest = modelmgmt.newest_file_time(stale)
        facts['newest_model_time'] = (datetime.datetime.fromtimestamp(newest)
                                      if newest is not None else None)
    if 'sets' in wanted:
        from pynavis import sets
        found = {}
        for path in profile['required_sets']:
            try:
                found[path] = sets.find(path, document) is not None
            except Exception:
                found[path] = False
        facts['sets_found'] = found
    if 'viewpoints' in wanted:
        try:
            facts['viewpoints'] = _viewpoint_count(document)
        except Exception:
            facts['viewpoints'] = None
    if 'section' in wanted:
        try:
            facts['section_on'] = bool(document.CurrentViewpoint.CreateCopy().ClipPlanes.Enabled)
        except Exception:
            facts['section_on'] = None

    stages.start('Reading clash tests')
    tests = []
    if wanted & set(['clash_run', 'new_clashes']):
        facts['clash'], tests = _clash_facts(document)

    stages.start('Counting New clashes')
    if 'new_clashes' in wanted and profile['max_new_clashes'] >= 0:
        if facts['clash']['available']:
            facts['new_clashes'] = _new_clash_facts(tests, profile['clash_budget'], stages)
        else:
            facts['new_clashes'] = {'available': False}

    stages.start('Checking items')
    if wanted & set(['hidden', 'overrides']):
        hidden, overrides = _walk_hidden_overrides(
            infos, 'hidden' in wanted, 'overrides' in wanted, profile['hidden_budget'],
            profile['override_sample'], stages)
        if 'hidden' in wanted:
            facts['hidden'] = hidden
        if 'overrides' in wanted:
            facts['overrides'] = overrides

    stages.start('Reading TimeLiner')
    if 'timeliner' in wanted:
        facts['timeliner'] = _timeliner_facts(document)
    if progress is not None:
        progress(1.0, 'Done')
    return facts


def run_profile(profile, doc=None, progress=None):
    """gather_facts + evaluate: the check results for a profile on the document."""
    profile = normalize_profile(profile or DEFAULT_PROFILE)
    return evaluate(gather_facts(doc, profile, progress), profile)


def document_name(doc=None):
    """The document's file name, or 'Untitled'."""
    try:
        from pynavis import doc as _pdoc
        path = _pdoc.get_filename(_doc(doc)) or ''
    except Exception:
        path = ''
    return path.replace('\\', '/').split('/')[-1] if path else 'Untitled'
