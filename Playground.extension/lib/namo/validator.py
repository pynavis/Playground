# -*- coding: utf-8 -*-
"""Data Validator: BEP-style property checks from JSON rule files.

A rule file lives in <team_root>\\rules\\validation\\*.json (team-shared when Playground has a
shared folder):

    {"format": "playground-validation", "version": 1, "name": "BEP checks",
     "description": "...",
     "rules": [
       {"name": "Ducts have a system name",
        "description": "Why the rule exists (shown in the report).",
        "applies_to": ["Element > Category = Ducts"],        # namo.rules conditions
        "applies_mode": "all",                               # or "any"; default all
        "require": ["Element > System Name is not empty"],
        "require_mode": "all",                               # or "any"
        "severity": "error",                                 # or "warning"
        "enabled": true}]}

Conditions are text in namo.rules' cell language (rules.parse_cell: '=', 'contains',
'is empty', 'is not empty', 'exists', 'matches <regex>', 'is one of A, B',
'between 1 and 3', '>=' ...) or condition dicts. An empty applies_to checks every item.
Requirements cover: exists, not empty, regex, in list, numeric range. Numbers compare
in Playground report units (document units by default).

Pure (tested): parsing with line-numbered problems (check_text), the starter set,
evaluating one item through a getter, tallies, report rows and HTML. API: run_rules()
over items with a propindex.Reader.
"""

import json
import os
import re

from namo import htmlreport, naming, rules

FORMAT = 'playground-validation'
VERSION = 1
FAILURE_ROWS_SHOWN = 500
RULE_KEYS = ('name', 'description', 'applies_to', 'applies_mode', 'require', 'require_mode',
             'severity', 'enabled')
SEVERITIES = ('error', 'warning')
SET_FOLDER = 'Validation'
STARTER_FILE = 'Playground starter rules.json'

STARTER = {
    'format': FORMAT,
    'version': VERSION,
    'name': 'Playground starter rules',
    'description': ('Example BEP checks for Revit-based models. Copy this file, rename it and '
                    'edit the rules: each rule names the items it applies to and what they '
                    'must carry. Conditions read like "Element > Category = Ducts", '
                    '"Element > Mark is not empty", "Element > Comments matches ^[A-Z]{2}-\\d{3}$", '
                    '"Element > Phase Created is one of Existing, New Construction" or '
                    '"Element > Offset between 0 and 3".'),
    'rules': [
        {'name': 'Ducts have a system name',
         'description': 'Every duct and duct fitting is assigned to a system.',
         'applies_to': ['Element > Category is one of Ducts, Duct Fittings, Flex Ducts'],
         'require': ['Element > System Name is not empty']},
        {'name': 'Pipes have a system name',
         'description': 'Every pipe and pipe fitting is assigned to a system.',
         'applies_to': ['Element > Category is one of Pipes, Pipe Fittings, Flex Pipes'],
         'require': ['Element > System Name is not empty']},
        {'name': 'Elements are hosted on a level',
         'description': ('Every Revit element carries a level; walls use Base Constraint, '
                         'MEP elements Reference Level.'),
         'applies_to': ['Element > Category exists'],
         'require': ['Element > Level is not empty', 'Element > Reference Level is not empty',
                     'Element > Base Constraint is not empty', 'Element > Schedule Level is not empty'],
         'require_mode': 'any', 'severity': 'warning'},
        {'name': 'Doors have a mark',
         'description': 'Door marks are filled in for the door schedule.',
         'applies_to': ['Element > Category = Doors'],
         'require': ['Element > Mark is not empty']},
        {'name': 'Equipment comments follow the asset code',
         'description': 'Mechanical equipment Comments hold an asset code like AHU-001.',
         'applies_to': ['Element > Category = Mechanical Equipment'],
         'require': ['Element > Comments matches ^[A-Z]{2,4}-\\d{3}$'],
         'severity': 'warning'},
    ],
}


# =============================================================================
# Pure half: parsing and checking rule files
# =============================================================================


def _line_of(text, needle, start_line=1):
    """1-based line number of the first line at or after start_line containing
    needle, or None."""
    lines = text.splitlines()
    for index in range(max(0, start_line - 1), len(lines)):
        if needle in lines[index]:
            return index + 1
    return None


def _line_context(text, line):
    lines = text.splitlines()
    if line is None or not 1 <= line <= len(lines):
        return ''
    return lines[line - 1].strip()


def _json_error(text, error):
    """(line, message) for a json syntax error on either engine."""
    message = str(error)
    line = getattr(error, 'lineno', None)
    if line is None:
        found = re.search(r'line (\d+)', message)
        line = int(found.group(1)) if found else None
    short = re.sub(r':\s*line \d+.*$', '', message).strip() or message
    return line, short


def parse_condition(value):
    """(condition dict, problem sentence or None) for one text or dict condition."""
    if isinstance(value, dict):
        cond = rules.normalise(value)
        problems = rules.validate(value)
        return cond, (problems[0] if problems else None)
    if not isinstance(value, str) or not value.strip():
        return None, 'A condition must be text like "Element > Category = Ducts".'
    try:
        cond = rules.parse_cell(value)
    except ValueError as error:
        return None, str(error)
    problems = rules.validate(cond)
    return cond, (problems[0] if problems else None)


def normalise_rule(raw, number):
    """(rule dict or None, [problem sentences]) for the number-th rule (1-based)."""
    problems = []
    if not isinstance(raw, dict):
        return None, ['Rule %d is not a set of fields.' % number]
    name = str(raw.get('name') or '').strip()
    label = 'Rule %d%s' % (number, (' "%s"' % name) if name else '')
    if not name:
        problems.append('%s has no name.' % label)
    for key in sorted(raw):
        if key not in RULE_KEYS:
            problems.append('%s: unknown field "%s" (fields are %s).' % (label, key, ', '.join(RULE_KEYS)))
    rule = {'name': name or ('Rule %d' % number), 'description': str(raw.get('description') or ''),
            'applies_to': [], 'require': [], 'number': number}
    for key, mode_key in (('applies_to', 'applies_mode'), ('require', 'require_mode')):
        values = raw.get(key)
        if values is None:
            values = []
        if not isinstance(values, list):
            values = [values]
        for index, value in enumerate(values):
            cond, problem = parse_condition(value)
            if problem:
                problems.append('%s, %s %d: %s' % (label, 'applies to' if key == 'applies_to' else 'requirement',
                                                  index + 1, problem))
            if cond is not None and not problem:
                rule[key].append(cond)
        mode = str(raw.get(mode_key) or 'all').lower()
        if mode not in ('all', 'any'):
            problems.append('%s: %s must be "all" or "any".' % (label, mode_key))
            mode = 'all'
        rule[mode_key] = mode
    if not raw.get('require'):
        problems.append('%s has no requirements.' % label)
    severity = str(raw.get('severity') or 'error').lower()
    if severity not in SEVERITIES:
        problems.append('%s: severity must be "error" or "warning".' % label)
        severity = 'error'
    rule['severity'] = severity
    rule['enabled'] = raw.get('enabled', True) is not False
    return rule, problems


def check_text(text, file_name=''):
    """(ruleset or None, [(line or None, sentence, line text)]) for a rule file's text.
    The ruleset keeps the rules that read cleanly: {'name', 'description', 'rules',
    'file'}."""
    problems = []
    try:
        data = json.loads(text)
    except ValueError as error:
        line, message = _json_error(text, error)
        return None, [(line, 'The file is not valid JSON: %s.' % message.rstrip('.'),
                       _line_context(text, line))]
    if not isinstance(data, dict):
        return None, [(1, 'The file must hold one set of fields with a "rules" list.', '')]
    if data.get('format') not in (None, FORMAT):
        problems.append((_line_of(text, '"format"'), 'This is not a Playground validation file '
                         '(format "%s").' % data.get('format'), _line_context(text, _line_of(text, '"format"'))))
        return None, problems
    raw_rules = data.get('rules')
    if not isinstance(raw_rules, list) or not raw_rules:
        line = _line_of(text, '"rules"')
        return None, [(line, 'The file needs a "rules" list with at least one rule.', _line_context(text, line))]
    kept = []
    names = {}
    search_from = _line_of(text, '"rules"') or 1
    for number, raw in enumerate(raw_rules, 1):
        name = str(raw.get('name') or '') if isinstance(raw, dict) else ''
        line = _line_of(text, '"%s"' % name.replace('"', '\\"'), search_from) if name else None
        if line:
            search_from = line + 1
        rule, rule_problems = normalise_rule(raw, number)
        for sentence in rule_problems:
            problems.append((line, sentence, _line_context(text, line)))
        if rule is None:
            continue
        key = rule['name'].lower()
        if key in names:
            problems.append((line, 'Rule %d has the same name as rule %d ("%s").'
                             % (number, names[key], rule['name']), _line_context(text, line)))
            continue
        names[key] = number
        if rule_problems:
            continue
        kept.append(rule)
    ruleset = {'name': str(data.get('name') or os.path.splitext(file_name)[0] or 'Rules'),
               'description': str(data.get('description') or ''), 'rules': kept,
               'file': file_name}
    return ruleset, problems


def format_problems(file_name, problems):
    """Readable lines: 'Rules.json, line 12: Rule 3 ... (  "name": "X",)'."""
    out = []
    for line, sentence, context in problems:
        where = '%s, line %d' % (file_name, line) if line else file_name
        text = '%s: %s' % (where, sentence)
        if context:
            text += '  [%s]' % context
        out.append(text)
    return out


def _ordered(value):
    """value with rule-file keys in reading order (format, version, name,
    description, rules; then each rule's fields in RULE_KEYS order), so the starter
    file reads top-down on every engine (IronPython dicts are not insertion ordered)."""
    import collections
    order = ['format', 'version', 'name', 'description', 'rules'] + list(RULE_KEYS)
    if isinstance(value, dict):
        out = collections.OrderedDict()
        for key in sorted(value, key=lambda k: (order.index(k) if k in order else len(order), k)):
            out[key] = _ordered(value[key])
        return out
    if isinstance(value, list):
        return [_ordered(v) for v in value]
    return value


def starter_text():
    """The starter rule file as text (indented JSON, keys in reading order)."""
    return json.dumps(_ordered(STARTER), indent=2) + '\n'


# =============================================================================
# Pure half: evaluating
# =============================================================================


def _value_words(value):
    if value is None:
        return 'empty'
    text = rules.text_of(value)
    if not text:
        return 'empty'
    if len(text) > 60:
        text = text[:57] + '...'
    return '"%s"' % text


def explain(cond, exists, value):
    """One short sentence for a failed requirement: 'System Name is missing',
    'Mark is empty', 'Comments is "x", expected matches ^A'."""
    category = cond.get('category') or ''
    prop = cond.get('property') or cond.get('prop') or ''
    if not exists:
        return '%s is missing' % prop
    op = cond.get('op')
    if op in ('not_empty', 'exists'):
        return '%s is empty' % prop
    described = rules.describe(cond)
    left = ' > '.join(part for part in (category, prop) if part)
    expected = described[len(left):].strip() if described.startswith(left) else described
    return '%s is %s, expected %s' % (prop, _value_words(value), expected)


def caching(getter):
    """getter wrapped so each (category, property) is read once per item."""
    cache = {}

    def get(category, prop):
        key = (category, prop)
        if key not in cache:
            try:
                cache[key] = getter(category, prop)
            except Exception:
                cache[key] = (False, None)
        return cache[key]
    return get


def check_item(rule, getter):
    """(applies, passed, problems) for one item. getter(category, property) ->
    (exists, value) as namo.rules.matches expects; problems are explain() sentences
    for every failed requirement (when the rule fails)."""
    cached = caching(getter)
    if rule['applies_to'] and not rules.matches(rule['applies_to'], cached, rule.get('applies_mode', 'all')):
        return False, True, []
    if rules.matches(rule['require'], cached, rule.get('require_mode', 'all')):
        return True, True, []
    problems = []
    for cond in rule['require']:
        category = cond.get('category') or ''
        prop = cond.get('property') or cond.get('prop') or ''
        exists, value = cached(category, prop)
        if not rules.evaluate(cond, exists, value):
            problems.append(explain(cond, exists, value))
    if rule.get('require_mode') == 'any' and len(problems) > 1:
        problems = ['None of the %d options: %s' % (len(problems), '; '.join(problems))]
    return True, False, problems


def new_result(rule, ruleset_name=''):
    return {'rule': rule['name'], 'set': ruleset_name, 'severity': rule.get('severity', 'error'),
            'description': rule.get('description', ''), 'checked': 0, 'passed': 0, 'failed': 0,
            'failures': []}


def add_outcome(result, item, applies, passed, problems):
    if not applies:
        return
    result['checked'] += 1
    if passed:
        result['passed'] += 1
    else:
        result['failed'] += 1
        result['failures'].append((item, problems))


def pass_rate(result):
    """0..1, or None when nothing was checked."""
    if not result['checked']:
        return None
    return float(result['passed']) / result['checked']


def totals(results):
    """{'rules', 'checked', 'passed', 'failed', 'failing_rules'}."""
    out = {'rules': len(results), 'checked': 0, 'passed': 0, 'failed': 0, 'failing_rules': 0}
    for result in results:
        out['checked'] += result['checked']
        out['passed'] += result['passed']
        out['failed'] += result['failed']
        if result['failed']:
            out['failing_rules'] += 1
    return out


def summary_rows(results):
    """[[rule, set, severity, checked, passed, failed, pass rate 0..1 or None]]."""
    return [[r['rule'], r['set'], r['severity'], r['checked'], r['passed'], r['failed'], pass_rate(r)]
            for r in results]


def set_name(rule_name):
    """The selection set name for a failing rule (no '/', which is a folder there)."""
    text = naming.sanitize(rule_name or 'Rule').replace('/', '-').replace('\\', '-')
    return text.strip() or 'Rule'


_esc = htmlreport.escape

_CSS = ('<style>.playground-val td.bar{width:160px}'
        '.playground-val .track{height:8px;background:var(--line);border-radius:2px;overflow:hidden}'
        '.playground-val .fill{height:8px;background:var(--chart-1)}'
        '.playground-val .muted{color:var(--muted)}'
        '.playground-val td.num,.playground-val th.num{text-align:right;font-variant-numeric:tabular-nums}'
        '</style>')


def summary_html(results):
    """The per-rule summary table with a pass-rate bar (theme CSS variables)."""
    rows = []
    for r in results:
        rate = pass_rate(r)
        if rate is None:
            bar = '<span class="muted">Nothing to check</span>'
            pct = ''
        else:
            bar = ('<div class="track"><div class="fill" style="width:%d%%"></div></div>'
                   % int(round(rate * 100)))
            pct = '100%' if rate >= 1 else '%d%%' % int(rate * 100)
        rows.append('<tr><td>%s<div class="muted">%s</div></td><td>%s</td><td class="num">%s</td>'
                    '<td class="num">%s</td><td class="num">%s</td><td class="num">%s</td>'
                    '<td class="bar">%s</td></tr>'
                    % (_esc(r['rule']), _esc(r['description']), _esc(r['severity'].capitalize()),
                       '{:,}'.format(r['checked']), '{:,}'.format(r['passed']),
                       '{:,}'.format(r['failed']), pct, bar))
    return ('<div class="playground-val">%s<table class="pynavis"><thead><tr><th>Rule</th><th>Severity</th>'
            '<th class="num">Checked</th><th class="num">Passed</th><th class="num">Failed</th>'
            '<th class="num">Pass rate</th><th></th></tr></thead><tbody>%s</tbody></table></div>'
            % (_CSS, ''.join(rows)))


def failure_rows(results, limit=None):
    """[(rule, item, problems text)] in rule order, at most limit (None = all)."""
    out = []
    for r in results:
        for item, problems in r['failures']:
            out.append((r['rule'], item, '; '.join(problems)))
            if limit is not None and len(out) >= limit:
                return out
    return out


def failures_html(rows, link, model_of, total):
    """The failures table: rule, element link (link(item) -> trusted html), model,
    problem; a muted line when it shows only the first rows."""
    body = ''.join('<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>'
                   % (_esc(rule), link(item), _esc(model_of(item)), _esc(problem))
                   for rule, item, problem in rows)
    note = ''
    if total > len(rows):
        note = ('<p class="muted">Showing the first %s of %s failures; the Excel export lists '
                'them all.</p>' % ('{:,}'.format(len(rows)), '{:,}'.format(total)))
    return ('<div class="playground-val">%s<table class="pynavis"><thead><tr><th>Rule</th><th>Element</th>'
            '<th>Model</th><th>Problem</th></tr></thead><tbody>%s</tbody></table>%s</div>'
            % (_CSS, body, note))


# =============================================================================
# Files
# =============================================================================


def rules_folder():
    """<team_root>\\rules\\validation (created)."""
    from namo import paths
    folder = os.path.join(paths.team_root(), 'rules', 'validation')
    paths.ensure_dir(folder)
    return folder


def ensure_starter(folder):
    """Writes the starter rule file when the folder holds no .json file. Returns the
    path written, or None."""
    from namo import paths
    try:
        names = [n for n in os.listdir(folder) if n.lower().endswith('.json')]
    except OSError:
        names = []
    if names:
        return None
    path = os.path.join(folder, STARTER_FILE)
    paths.atomic_write_text(path, starter_text())
    return path


def restore_starter(folder):
    """(Re)writes the starter file, overwriting an edited copy of it."""
    from namo import paths
    path = os.path.join(folder, STARTER_FILE)
    paths.atomic_write_text(path, starter_text())
    return path


def load_folder(folder):
    """[ruleset] for every .json file in the folder, natural file order; each has
    'file', 'path', 'problems' (formatted lines) and the rules that read cleanly."""
    from namo import paths
    try:
        names = [n for n in os.listdir(folder) if n.lower().endswith('.json')]
    except OSError:
        names = []
    names.sort(key=lambda n: (naming.natural_key(n), n))
    out = []
    for name in names:
        path = os.path.join(folder, name)
        text = paths.read_text(path, default=None)
        if text is None:
            out.append({'name': name, 'description': '', 'rules': [], 'file': name, 'path': path,
                        'problems': ['%s: the file could not be read.' % name]})
            continue
        ruleset, problems = check_text(text, name)
        if ruleset is None:
            ruleset = {'name': os.path.splitext(name)[0], 'description': '', 'rules': [], 'file': name}
        ruleset['path'] = path
        ruleset['problems'] = format_problems(name, problems)
        out.append(ruleset)
    return out


# =============================================================================
# API half
# =============================================================================


def run_rules(rulesets, item_list, reader, tick=None):
    """[result] per enabled rule over item_list. tick(done, total) per item (False
    cancels with namo.items.Cancelled)."""
    from namo import items
    active = []
    results = []
    for ruleset in rulesets:
        for rule in ruleset['rules']:
            if rule.get('enabled', True):
                active.append(rule)
                results.append(new_result(rule, ruleset.get('name', '')))
    data = list(item_list)
    ticker = items.Ticker(tick, total=len(data), every=100)
    for item in data:
        getter = caching(reader.getter(item))
        for rule, result in zip(active, results):
            applies, passed, problems = check_item(rule, getter)
            add_outcome(result, item, applies, passed, problems)
        ticker.step()
    ticker.finish()
    return results
