# -*- coding: utf-8 -*-
"""Auto Attach rules, and the one-walk object index both Auto Attach and TimeLiner
from Excel use to turn conditions into model items.

A rule is one line of text:

    Name ~ L(?P<level>\\d+) (?P<trade>\\w+)  =>  Element > Level = Level {level} & Item > Layer contains {trade}
    Name contains Slab                      =>  set Structure/Slabs
    User1 = MEP                             =>  set Services/{name}
    # a comment

Left of '=>': a task field (Name, Task ID, Type, User1..User10), an operator (~ or
'matches' for a regular expression with named groups, contains, =, is, starts with,
ends with, like for wildcards) and a pattern. Right of '=>': targets joined by ' & ':
'set <path>' attaches a selection set (by reference); anything else is a condition
(namo.rules.parse_cell) and all conditions must hold (AND). {group} tokens take the
regex groups; {name}, {id}, {type} and {user1}..{user10} are always available. The
first rule that matches a task wins.

ObjectIndex evaluates many conditions with ONE pass over the model's objects: it reads
each distinct (category, property) once per object, keeps a value index for 'equals'
conditions (so a hundred "Level = Level N" rules cost one lookup each) and caches every
condition's result.

Pure except read_pairs() and model_objects(), which lazy-import the API.
"""

import re

from namo import naming, rules

FIELDS = [('name', 'Name'), ('id', 'Task ID'), ('type', 'Type')] + \
    [('user%d' % n, 'User%d' % n) for n in range(1, 11)]
_FIELD_WORDS = {'name': 'name', 'task name': 'name', 'task id': 'id', 'id': 'id',
                'display id': 'id', 'type': 'type', 'task type': 'type'}
for _n in range(1, 11):
    _FIELD_WORDS['user%d' % _n] = 'user%d' % _n
    _FIELD_WORDS['user %d' % _n] = 'user%d' % _n

_OPS = [('starts with', 'starts_with'), ('ends with', 'ends_with'), ('contains', 'contains'),
        ('matches', 'regex'), ('like', 'wildcard'), ('equals', 'equals'), ('is', 'equals'),
        ('~', 'regex'), ('=', 'equals')]
OP_LABELS = {'regex': '~', 'contains': 'contains', 'equals': '=', 'starts_with': 'starts with',
             'ends_with': 'ends with', 'wildcard': 'like'}

EXAMPLE = ('# One rule per line: <task field> <operator> <pattern> => <targets>\n'
           '# Name ~ L(?P<level>\\d+) (?P<trade>\\w+) => Element > Level = Level {level} & Item > Layer contains {trade}\n'
           '# Name contains Slab => set Structure/Slabs\n')


def _strip_quotes(text):
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in '"\'':
        return text[1:-1]
    return text


def parse_rule(line):
    """A rule dict from one line, or None for a blank/comment line. Raises ValueError
    with a sentence when it does not read."""
    text = str(line or '').strip()
    if not text or text.startswith('#'):
        return None
    if '=>' not in text:
        raise ValueError('A rule needs "=>" between the task test and what to attach.')
    left, right = text.split('=>', 1)
    left = left.strip()
    right = right.strip()
    if not right:
        raise ValueError('Nothing to attach after "=>".')
    lowered = left.lower()
    field = None
    rest = ''
    for word in sorted(_FIELD_WORDS, key=lambda w: -len(w)):
        if lowered.startswith(word) and (len(lowered) == len(word) or not lowered[len(word)].isalnum()):
            field = _FIELD_WORDS[word]
            rest = left[len(word):].strip()
            break
    if field is None:
        raise ValueError('Start with a task field: Name, Task ID, Type or User1 to User10.')
    op = None
    pattern = ''
    lowered_rest = rest.lower()
    for word, name in _OPS:
        if lowered_rest.startswith(word):
            boundary = len(word)
            if word[0].isalpha() and len(lowered_rest) > boundary and lowered_rest[boundary].isalnum():
                continue
            op = name
            pattern = _strip_quotes(rest[boundary:])
            break
    if op is None:
        raise ValueError('Use an operator after the field: ~, contains, =, starts with, ends with or like.')
    if not pattern:
        raise ValueError('The rule has no pattern to look for.')
    compiled = None
    if op == 'regex':
        try:
            compiled = re.compile(pattern, re.IGNORECASE)
        except re.error as error:
            raise ValueError('The pattern does not read: %s.' % error)
    targets = [t.strip() for t in re.split(r'\s+&\s+', right) if t.strip()]
    sets = []
    conditions = []
    for target in targets:
        if target.lower().startswith('set ') or target.lower().startswith('sets '):
            sets.append(_strip_quotes(target.split(None, 1)[1]))
        else:
            conditions.append(target)
    tokens = set()
    for template in sets + conditions:
        tokens.update(naming.tokens(template))
    available = set(['name', 'id', 'type'] + ['user%d' % n for n in range(1, 11)])
    if compiled is not None:
        available.update(compiled.groupindex)
    missing = sorted(t for t in tokens if t.lower() not in set(a.lower() for a in available))
    if missing:
        raise ValueError('{%s} is not a group in the pattern.' % missing[0])
    for condition in conditions:
        if not naming.tokens(condition):
            rules.parse_cell(condition)       # raises a readable ValueError
    return {'field': field, 'op': op, 'pattern': pattern, 'regex': compiled, 'sets': sets,
            'conditions': conditions, 'text': text}


def parse_rules(text):
    """(rules, errors): errors are (line number, sentence)."""
    out = []
    errors = []
    for number, line in enumerate(str(text or '').replace('\r', '').split('\n')):
        try:
            rule = parse_rule(line)
        except ValueError as error:
            errors.append((number + 1, str(error)))
            continue
        if rule is not None:
            rule['line'] = number + 1
            out.append(rule)
    return out, errors


def task_values(row):
    """The fields a rule can test, from a timeliner.snapshot row."""
    values = {'name': row.get('name') or '', 'id': row.get('id') or '', 'type': row.get('type') or ''}
    users = row.get('user') or [''] * 10
    for n in range(1, 11):
        values['user%d' % n] = users[n - 1] if n - 1 < len(users) else ''
    return values


def match(rule, values):
    """The captures dict when the rule matches the task values, else None."""
    subject = str(values.get(rule['field']) or '')
    pattern = rule['pattern']
    op = rule['op']
    found = None
    if op == 'regex':
        m = rule['regex'].search(subject)
        if m:
            found = dict((k, v or '') for k, v in m.groupdict().items())
    elif op == 'contains':
        found = {} if pattern.lower() in subject.lower() else None
    elif op == 'equals':
        found = {} if subject.strip().lower() == pattern.strip().lower() else None
    elif op == 'starts_with':
        found = {} if subject.lower().startswith(pattern.lower()) else None
    elif op == 'ends_with':
        found = {} if subject.lower().endswith(pattern.lower()) else None
    elif op == 'wildcard':
        found = {} if rules.evaluate({'category': '', 'property': 'x', 'op': 'wildcard',
                                      'value': pattern}, True, subject) else None
    if found is None:
        return None
    merged = dict(values)
    merged.update(found)
    return merged


def render(rule, captures):
    """{'sets': [paths], 'conditions': [condition dicts]} with {tokens} filled.
    Raises ValueError when a rendered condition does not read."""
    sets = [naming.render(path, captures)[0].strip() for path in rule['sets']]
    conditions = [rules.parse_cell(naming.render(text, captures)[0]) for text in rule['conditions']]
    return {'sets': [s for s in sets if s], 'conditions': conditions}


def plan(rows, rule_list, leaf_only=True):
    """One entry per task considered: {'index' (row index), 'rule' (rule or None),
    'targets' (render result or None), 'error' (sentence or None)}."""
    out = []
    for index, row in enumerate(rows):
        if leaf_only and row.get('has_children'):
            continue
        values = task_values(row)
        entry = {'index': index, 'rule': None, 'targets': None, 'error': None}
        for rule in rule_list:
            captures = match(rule, values)
            if captures is None:
                continue
            entry['rule'] = rule
            try:
                entry['targets'] = render(rule, captures)
            except ValueError as error:
                entry['error'] = str(error)
            break
        out.append(entry)
    return out


def condition_key(cond):
    """A hashable identity for a condition (for caches)."""
    value = cond.get('value')
    if isinstance(value, list):
        value = tuple(str(v) for v in value)
    return (cond.get('category') or '', cond.get('property') or '', cond.get('op'), value,
            bool(cond.get('ignore_case', True)))


_BOOL_WORDS = ('yes', 'no', 'true', 'false', '1', '0', 'y', 'n', 'on', 'off')


def _index_key(value):
    text = rules.text_of(value).strip()
    try:
        return ('n', float(text))
    except ValueError:
        return ('t', text.lower())


class ObjectIndex(object):
    """Conditions over a fixed list of objects, one property read per (object, pair).

    objects: any list (ModelItems in Navisworks, dicts in tests).
    reader(obj, pairs) -> {(category, property): (exists, value)} for the pairs asked.
    """

    def __init__(self, objects, reader):
        self.objects = list(objects)
        self.reader = reader
        self.values = {}            # pair -> [ (exists, value) per object ]
        self.lookup = {}            # pair -> {index key: [object index]}
        self.cache = {}

    def prepare(self, condition_lists, tick=None):
        """Reads every pair the conditions use, in one pass. tick(done, total) every
        200 objects; a tick returning exactly False stops (raises Cancelled)."""
        pairs = set()
        for conds in condition_lists:
            for cond in conds:
                pairs.add(((cond.get('category') or '').strip(), (cond.get('property') or '').strip()))
        pairs = sorted(p for p in pairs if p not in self.values)
        if not pairs:
            return
        columns = dict((p, []) for p in pairs)
        total = len(self.objects)
        for index, obj in enumerate(self.objects):
            try:
                found = self.reader(obj, pairs) or {}
            except Exception:
                found = {}
            for pair in pairs:
                columns[pair].append(found.get(pair, (False, None)))
            if tick is not None and index % 200 == 199:
                if tick(index + 1, total) == False:   # noqa: E712 (interop bools)
                    from namo.items import Cancelled
                    raise Cancelled()
        for pair in pairs:
            self.values[pair] = columns[pair]
            index = {}
            for position, (exists, value) in enumerate(columns[pair]):
                if exists:
                    index.setdefault(_index_key(value), []).append(position)
            self.lookup[pair] = index

    def _candidates(self, cond):
        pair = ((cond.get('category') or '').strip(), (cond.get('property') or '').strip())
        if (cond.get('op') == 'equals' and cond.get('ignore_case', True)
                and str(cond.get('value', '')).strip().lower() not in _BOOL_WORDS
                and pair in self.lookup):
            return set(self.lookup[pair].get(_index_key(cond.get('value')), []))
        return None

    def matching(self, cond):
        """Object indexes satisfying one condition (cached)."""
        key = condition_key(cond)
        if key in self.cache:
            return self.cache[key]
        pair = ((cond.get('category') or '').strip(), (cond.get('property') or '').strip())
        if pair not in self.values:
            self.prepare([[cond]])
        column = self.values[pair]
        candidates = self._candidates(cond)
        positions = candidates if candidates is not None else range(len(column))
        found = set()
        for position in positions:
            exists, value = column[position]
            if rules.evaluate(cond, exists, value):
                found.add(position)
        self.cache[key] = found
        return found

    def find(self, conditions):
        """Objects matching every condition (AND), in walk order."""
        if not conditions:
            return []
        groups = sorted((self.matching(c) for c in conditions), key=len)
        result = set(groups[0])
        for group in groups[1:]:
            result &= group
            if not result:
                break
        return [self.objects[i] for i in sorted(result)]


# ---- API half -------------------------------------------------------------------------------


def read_pairs(item, pairs):
    """{(category, property): (exists, value)} for one ModelItem by DISPLAY names; an
    empty category means "any category" (the first property with that name)."""
    from namo import variants
    out = {}
    anywhere = [p for p in pairs if not p[0]]
    for pair in pairs:
        if not pair[0]:
            continue
        try:
            value = variants.get(item, pair[0], pair[1])
        except Exception:
            value = None
        out[pair] = (value is not None, value)
    if anywhere:
        wanted = dict((p[1].lower(), p) for p in anywhere)
        try:
            for category in item.PropertyCategories:
                for prop in category.Properties:
                    pair = wanted.get(str(prop.DisplayName).lower())
                    if pair is not None and pair not in out:
                        value = variants.get(item, str(category.DisplayName), str(prop.DisplayName))
                        out[pair] = (value is not None, value)
        except Exception:
            pass
        for pair in anywhere:
            out.setdefault(pair, (False, None))
    return out


def model_objects(doc=None, tick=None):
    """Every element-level object in the document (namo.items.objects of every root)."""
    from namo import items
    return items.objects(items.roots(doc), tick=tick)
