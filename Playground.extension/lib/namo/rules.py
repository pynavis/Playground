# -*- coding: utf-8 -*-
"""One condition engine for every rule-driven Playground tool.

A condition is a plain dict:

    {'category': 'Element', 'property': 'Category', 'op': 'equals', 'value': 'Ducts',
     'ignore_case': True}

    rules.evaluate(cond, exists, value)       # one already-read property value
    rules.matches(conds, getter, mode='all')  # getter(category, property) -> (exists, value)
    rules.parse_cell('Element > Category = Ducts')   # Excel / text driven rules
    rules.describe(cond)                      # 'Element > Category = Ducts'
    rules.native_query(conds)                 # pynavis sets Builder, or None (needs Python)

Semantics, the same in evaluate() and wherever a rule is shown:
  * ignore_case defaults to True. Text compares trimmed values.
  * every value operator is False when the property does not exist (like Navisworks'
    Find Items); 'missing' finds those. 'empty' is True for a missing property OR a
    blank value; 'not_empty' needs a present, non-blank value.
  * equals / not_equals / in_list compare as numbers when both sides read entirely as
    numbers ('3' equals 3.0 and '3.000'), otherwise as text. Yes/No values match
    yes/no/true/false/1/0.
  * gt, ge, lt, le, between use to_number() of both sides (the number at the start:
    '12.5 m' is 12.5); a side without a number makes the condition False.
  * wildcard: '*' any run, '?' one character, whole value. regex: re.search.
category '' means "any category" for getters that support it; native_query needs one.

Pure except native_query(), which lazy-imports pynavis.sets.
"""
import re

from namo import units

OPS = [
    ('equals', 'equals', True),
    ('not_equals', 'does not equal', True),
    ('contains', 'contains', True),
    ('not_contains', 'does not contain', True),
    ('starts_with', 'starts with', True),
    ('ends_with', 'ends with', True),
    ('wildcard', 'matches wildcard', True),
    ('regex', 'matches pattern', True),
    ('gt', 'greater than', True),
    ('ge', 'at least', True),
    ('lt', 'less than', True),
    ('le', 'at most', True),
    ('between', 'between', True),
    ('in_list', 'is one of', True),
    ('exists', 'exists', False),
    ('missing', 'is missing', False),
    ('empty', 'is empty', False),
    ('not_empty', 'is not empty', False),
]
OP_NAMES = [op for op, _label, _needs in OPS]
LABELS = dict((op, label) for op, label, _needs in OPS)
NEEDS_VALUE = dict((op, needs) for op, _label, needs in OPS)
NUMERIC_OPS = ('gt', 'ge', 'lt', 'le', 'between')
TEXT_OPS = ('equals', 'not_equals', 'contains', 'not_contains', 'starts_with', 'ends_with',
            'wildcard', 'regex', 'in_list')

# How describe() writes each operator (parse_cell reads these back).
SYMBOLS = {
    'equals': '=', 'not_equals': '!=', 'contains': 'contains', 'not_contains': 'does not contain',
    'starts_with': 'starts with', 'ends_with': 'ends with', 'wildcard': 'like',
    'regex': 'matches', 'gt': '>', 'ge': '>=', 'lt': '<', 'le': '<=', 'between': 'between',
    'in_list': 'is one of', 'exists': 'exists', 'missing': 'is missing', 'empty': 'is empty',
    'not_empty': 'is not empty',
}

_GE, _LE, _NE = chr(0x2265), chr(0x2264), chr(0x2260)

# Operator spellings accepted by normalise() and parse_cell().
OP_ALIASES = {
    '=': 'equals', '==': 'equals', 'is': 'equals', 'eq': 'equals', 'equal': 'equals',
    '!=': 'not_equals', '<>': 'not_equals', _NE: 'not_equals', 'is not': 'not_equals',
    'not equals': 'not_equals', 'ne': 'not_equals', 'not_equal': 'not_equals',
    'not contains': 'not_contains', 'begins with': 'starts_with', 'startswith': 'starts_with',
    'endswith': 'ends_with', 'like': 'wildcard', 'matches': 'regex', 'regexp': 'regex',
    '>': 'gt', '>=': 'ge', _GE: 'ge', '<': 'lt', '<=': 'le', _LE: 'le',
    'greater': 'gt', 'less': 'lt', 'in': 'in_list', 'one of': 'in_list', 'in list': 'in_list',
    'missing': 'missing', 'does not exist': 'missing', 'empty': 'empty', 'not empty': 'not_empty',
    'is blank': 'empty', 'is not blank': 'not_empty',
}
for _op, _label, _needs in OPS:
    OP_ALIASES[_label] = _op
    OP_ALIASES[_op] = _op
    OP_ALIASES[_op.replace('_', ' ')] = _op
for _op, _sym in SYMBOLS.items():
    OP_ALIASES[_sym] = _op

_TRUE_WORDS = ('yes', 'true', '1', 'y', 'on')
_FALSE_WORDS = ('no', 'false', '0', 'n', 'off')
_PATTERNS = {}


# ---- values ------------------------------------------------------------------------


def to_number(value):
    """The number a value carries: ints/floats as float, text by the number at its start
    ('12.5', '1,234', '12.5 m', '3.2 ft', '-4', '1e3'). bool and None give None."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    number, _rest = units.split_number(str(value))
    return number


def _exact_number(value):
    """A number only when the whole value is one ('3', '3.000', 3.0); else None."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return units.parse_number(str(value))


def text_of(value):
    """How a property value reads as text: None '', True 'Yes', 3.0 '3', 2.5 '2.5'."""
    if value is None:
        return ''
    if isinstance(value, bool):
        return 'Yes' if value else 'No'
    if isinstance(value, float):
        if value == int(value) and abs(value) < 1e15:
            return str(int(value))
        return '%.10g' % value
    return str(value).strip()


def _blank(value):
    return value is None or text_of(value) == ''


def _fold(text, ignore_case):
    return text.lower() if ignore_case else text


def _equal(value, target, ignore_case):
    if isinstance(value, bool):
        word = text_of(target).lower()
        if word in _TRUE_WORDS:
            return value is True
        if word in _FALSE_WORDS:
            return value is False
    a, b = _exact_number(value), _exact_number(target)
    if a is not None and b is not None:
        return abs(a - b) <= 1e-9 * max(1.0, abs(a), abs(b))
    return _fold(text_of(value), ignore_case) == _fold(text_of(target), ignore_case)


def as_list(value):
    """An in_list value as a list: lists/tuples as they are, text split on ';' when it has
    one, else on ','; items trimmed, empties dropped."""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [v for v in value if text_of(v) != '']
    text = str(value)
    parts = text.split(';') if ';' in text else text.split(',')
    return [p.strip() for p in parts if p.strip()]


def bounds(value):
    """(lo, hi) numbers of a between value ([lo, hi], (lo, hi) or 'lo and hi' / 'lo, hi' /
    'lo..hi'), low first; (None, None) when it does not read."""
    if isinstance(value, (list, tuple)) and len(value) == 2:
        lo, hi = to_number(value[0]), to_number(value[1])
    elif isinstance(value, str):
        parts = re.split(r'\s+and\s+|\s*\.\.\s*|\s*;\s*|\s*,\s+', value.strip(), flags=re.IGNORECASE)
        if len(parts) != 2:
            return None, None
        lo, hi = to_number(parts[0]), to_number(parts[1])
    else:
        return None, None
    if lo is None or hi is None:
        return None, None
    return (lo, hi) if lo <= hi else (hi, lo)


def wildcard_regex(pattern, ignore_case=True):
    """Compiled whole-value regex for a '*'/'?' wildcard pattern (cached)."""
    key = ('w', pattern, bool(ignore_case))
    compiled = _PATTERNS.get(key)
    if compiled is None:
        parts = []
        for ch in str(pattern):
            if ch == '*':
                parts.append('.*')
            elif ch == '?':
                parts.append('.')
            else:
                parts.append(re.escape(ch))
        flags = re.DOTALL | (re.IGNORECASE if ignore_case else 0)
        compiled = re.compile('^' + ''.join(parts) + '$', flags)
        _PATTERNS[key] = compiled
    return compiled


def _regex(pattern, ignore_case):
    key = ('r', pattern, bool(ignore_case))
    if key not in _PATTERNS:
        try:
            _PATTERNS[key] = re.compile(str(pattern), re.IGNORECASE if ignore_case else 0)
        except Exception:
            _PATTERNS[key] = None
    return _PATTERNS[key]


# ---- conditions ----------------------------------------------------------------------


def op_of(text):
    """The op name for an operator spelling ('=', '>=', 'does not contain', 'Contains',
    'is one of', 'in_list' ...), or None."""
    if text is None:
        return None
    key = ' '.join(str(text).strip().lower().split())
    return OP_ALIASES.get(key)


def normalise(cond):
    """A clean copy: keys category, property ('prop' is accepted too), op (aliases
    resolved; '' when unknown), value (None for ops without one), ignore_case (default True)."""
    cond = cond or {}
    op = op_of(cond.get('op')) or ''
    prop = cond.get('property')
    if prop is None:
        prop = cond.get('prop')
    out = {
        'category': text_of(cond.get('category')),
        'property': text_of(prop),
        'op': op,
        'value': cond.get('value') if NEEDS_VALUE.get(op, True) else None,
        'ignore_case': bool(cond.get('ignore_case', True)),
    }
    return out


def evaluate(cond, exists, value):
    """True when one property reading satisfies the condition (see the module docstring
    for the exact semantics). exists: whether the item has the property at all; value:
    what it holds (str, number, bool or None)."""
    op = cond.get('op') or 'equals'
    if op not in NEEDS_VALUE:
        op = op_of(op) or op
    if op == 'exists':
        return bool(exists)
    if op == 'missing':
        return not exists
    if op == 'empty':
        return (not exists) or _blank(value)
    if op == 'not_empty':
        return bool(exists) and not _blank(value)
    if not exists:
        return False
    target = cond.get('value')
    ignore_case = cond.get('ignore_case', True)
    if op in ('gt', 'ge', 'lt', 'le'):
        a, b = to_number(value), to_number(target)
        if a is None or b is None:
            return False
        if op == 'gt':
            return a > b
        if op == 'ge':
            return a >= b
        if op == 'lt':
            return a < b
        return a <= b
    if op == 'between':
        lo, hi = bounds(target)
        a = to_number(value)
        if lo is None or a is None:
            return False
        return lo <= a <= hi
    if op == 'equals':
        return _equal(value, target, ignore_case)
    if op == 'not_equals':
        return not _equal(value, target, ignore_case)
    if op == 'in_list':
        for item in as_list(target):
            if _equal(value, item, ignore_case):
                return True
        return False
    text = _fold(text_of(value), ignore_case)
    pattern = _fold(text_of(target), ignore_case)
    if op == 'contains':
        return pattern in text
    if op == 'not_contains':
        return pattern not in text
    if op == 'starts_with':
        return text.startswith(pattern)
    if op == 'ends_with':
        return text.endswith(pattern)
    if op == 'wildcard':
        return wildcard_regex(text_of(target), ignore_case).match(text_of(value)) is not None
    if op == 'regex':
        compiled = _regex(target, ignore_case)
        return compiled is not None and compiled.search(text_of(value)) is not None
    return False


def matches(conds, getter, mode='all'):
    """True when the conditions hold for one item. getter(category, property) returns
    (exists, value); it is called at most once per distinct (category, property), and a
    getter that raises counts as a missing property. mode 'all' (every condition; True
    for no conditions) or 'any' (at least one; False for none)."""
    if mode not in ('all', 'any'):
        raise ValueError("mode must be 'all' or 'any'")
    cache = {}
    for cond in conds:
        key = (cond.get('category') or '', cond.get('property') or cond.get('prop') or '')
        if key not in cache:
            try:
                cache[key] = getter(key[0], key[1])
            except Exception:
                cache[key] = (False, None)
        exists, value = cache[key]
        ok = evaluate(cond, exists, value)
        if mode == 'any' and ok:
            return True
        if mode == 'all' and not ok:
            return False
    return mode == 'all'


def _value_text(value):
    text = text_of(value)
    if text == '' or (text[0] in ('"', "'") and text[-1] == text[0]):
        return '"%s"' % text
    return text


def describe(cond):
    """One line for lists: 'Element > Category = Ducts', 'Item > Name contains PIPE',
    'Level between 1 and 3', 'Element > Mark is empty'; ' (match case)' when ignore_case
    is False on a text operator. parse_cell() reads it back."""
    c = normalise(cond)
    left = ' > '.join(part for part in (c['category'], c['property']) if part) or '(no property)'
    op = c['op']
    if not op:
        return '%s ? %s' % (left, text_of(cond.get('op') if cond else ''))
    if not NEEDS_VALUE[op]:
        text = '%s %s' % (left, SYMBOLS[op])
    elif op == 'between':
        value = c['value']
        if isinstance(value, (list, tuple)) and len(value) == 2:
            text = '%s between %s and %s' % (left, text_of(value[0]), text_of(value[1]))
        else:
            text = '%s between %s' % (left, text_of(value))
    elif op == 'in_list':
        items = [text_of(v) for v in as_list(c['value'])]
        joiner = '; ' if any(',' in item for item in items) else ', '
        text = '%s is one of %s' % (left, joiner.join(items))
    else:
        text = '%s %s %s' % (left, SYMBOLS[op], _value_text(c['value']))
    if not c['ignore_case'] and op in TEXT_OPS:
        text += ' (match case)'
    return text


def validate(cond):
    """Problems with a condition, as sentences for the user ([] when it is fine)."""
    if not isinstance(cond, dict):
        return ['A rule must be a set of fields.']
    problems = []
    c = normalise(cond)
    if not c['property']:
        problems.append('Choose a property.')
    if not c['op']:
        problems.append('Unknown comparison "%s".' % text_of(cond.get('op')))
        return problems
    if not NEEDS_VALUE[c['op']]:
        return problems
    value = c['value']
    label = LABELS[c['op']]
    if c['op'] == 'in_list':
        if not as_list(value):
            problems.append('Enter at least one value for "%s".' % label)
    elif c['op'] == 'between':
        lo, _hi = bounds(value)
        if lo is None:
            problems.append('Enter two numbers for "between", like 1 and 3.')
    elif value is None or text_of(value) == '':
        problems.append('Enter a value for "%s".' % label)
    elif c['op'] in ('gt', 'ge', 'lt', 'le') and to_number(value) is None:
        problems.append('Enter a number for "%s".' % label)
    elif c['op'] == 'regex':
        try:
            re.compile(str(value))
        except Exception as error:
            problems.append('The pattern does not read: %s.' % error)
    return problems


# ---- native Navisworks searches --------------------------------------------------------

_WILDCARD_UNSAFE = '*?[]#'


def native_ops():
    """Ops native_plan() can compile into a Navisworks search: equals, not_equals,
    contains, wildcard, gt, ge, lt, le, exists, missing always; starts_with/ends_with as a
    wildcard when the value has no * ? [ ] #; between as ge + le; in_list as OR groups.
    regex, not_contains, empty and not_empty always need Python."""
    return ['equals', 'not_equals', 'contains', 'starts_with', 'ends_with', 'wildcard',
            'gt', 'ge', 'lt', 'le', 'between', 'in_list', 'exists', 'missing']


def _native_alternatives(c, numbers_as_text):
    """List of alternatives (each a list of atoms) for one condition, or None."""
    cat, prop, op, value, ic = c['category'], c['property'], c['op'], c['value'], c['ignore_case']
    if not cat or not prop:
        return None

    def atom(nop, v=None):
        return (cat, prop, nop, v, bool(ic) if nop in ('equals', 'not_equals', 'contains', 'wildcard') else False)

    if op in ('equals', 'not_equals'):
        if _blank(value) or (_exact_number(value) is not None and not numbers_as_text):
            return None
        return [[atom(op, text_of(value))]]
    if op == 'contains':
        return None if _blank(value) else [[atom('contains', text_of(value))]]
    if op in ('starts_with', 'ends_with'):
        text = text_of(value)
        if not text or any(ch in text for ch in _WILDCARD_UNSAFE):
            return None
        return [[atom('wildcard', text + '*' if op == 'starts_with' else '*' + text)]]
    if op == 'wildcard':
        return None if _blank(value) else [[atom('wildcard', text_of(value))]]
    if op in ('gt', 'ge', 'lt', 'le'):
        number = to_number(value)
        return None if number is None else [[atom(op, number)]]
    if op == 'between':
        lo, hi = bounds(value)
        return None if lo is None else [[atom('ge', lo), atom('le', hi)]]
    if op == 'in_list':
        items = as_list(value)
        if not items:
            return None
        out = []
        for item in items:
            if _exact_number(item) is not None and not numbers_as_text:
                return None
            out.append([atom('equals', text_of(item))])
        return out
    if op == 'exists':
        return [[atom('exists')]]
    if op == 'missing':
        return [[atom('missing')]]
    return None


def native_plan(conds, mode='all', numbers_as_text=False, max_groups=4):
    """Pure half of native_query: OR groups of AND atoms
    [[(category, property, native_op, value, ignore_case), ...], ...], or None when any
    condition needs Python, a category is blank, there are no conditions, or more than
    max_groups OR groups would be needed (each OR group is one full model walk).

    equals/not_equals/in_list values that read as numbers return None unless
    numbers_as_text=True: a native match compares display strings, which finds text
    properties (Element ID > Value) but misses numeric (Int32/Double) ones that
    evaluate() would match."""
    if mode not in ('all', 'any'):
        raise ValueError("mode must be 'all' or 'any'")
    conds = [normalise(c) for c in conds or []]
    if not conds:
        return None
    if mode == 'all':
        groups = [[]]
        for c in conds:
            alternatives = _native_alternatives(c, numbers_as_text)
            if alternatives is None:
                return None
            groups = [g + alt for g in groups for alt in alternatives]
            if len(groups) > max_groups:
                return None
        return groups
    groups = []
    for c in conds:
        alternatives = _native_alternatives(c, numbers_as_text)
        if alternatives is None:
            return None
        groups.extend(alternatives)
        if len(groups) > max_groups:
            return None
    return groups


def native_query(conds, mode='all', numbers_as_text=False, max_groups=4):
    """A pynavis sets.query() Builder for the conditions (run it with sets.run(builder)
    or sets.find_first), or None when native_plan() says Python must decide. Text
    operators get .ignore_case() when the condition ignores case. Categories and
    properties are matched by DISPLAY name (the Builder's default)."""
    plan = native_plan(conds, mode, numbers_as_text, max_groups)
    if plan is None:
        return None
    from pynavis import sets
    builder = sets.query()
    for index, group in enumerate(plan):
        if index:
            builder.or_group()
        for cat, prop, nop, value, ignore_case in group:
            builder.prop(cat, prop)
            if nop == 'exists':
                builder.exists()
            elif nop == 'missing':
                builder.missing()
            else:
                getattr(builder, nop)(value)
            if ignore_case:
                builder.ignore_case()
    return builder


# ---- rules written as text ----------------------------------------------------------------

_WORD_OPS = [
    ('does not contain', 'not_contains'), ('not contains', 'not_contains'),
    ('does not equal', 'not_equals'), ('not equals', 'not_equals'),
    ('is not empty', 'not_empty'), ('is not blank', 'not_empty'), ('not empty', 'not_empty'),
    ('does not exist', 'missing'), ('is not', 'not_equals'),
    ('starts with', 'starts_with'), ('begins with', 'starts_with'), ('ends with', 'ends_with'),
    ('is one of', 'in_list'), ('one of', 'in_list'), ('is empty', 'empty'),
    ('is blank', 'empty'), ('is missing', 'missing'), ('exists', 'exists'),
    ('missing', 'missing'), ('empty', 'empty'), ('matches', 'regex'), ('like', 'wildcard'),
    ('between', 'between'), ('contains', 'contains'), ('equals', 'equals'),
    ('in', 'in_list'), ('is', 'equals'),
]
_WORD_RE = re.compile(
    r'(?<=\s)(' + '|'.join(r'\s+'.join(re.escape(part) for part in w.split()) for w, _o in
                           sorted(_WORD_OPS, key=lambda p: -len(p[0]))) + r')(?=\s|$)',
    re.IGNORECASE)
_WORD_MAP = dict((w, o) for w, o in _WORD_OPS)
_SYMBOL_RE = re.compile('(>=|<=|!=|<>|==|' + _GE + '|' + _LE + '|' + _NE + '|=|>|<)')
_CASE_RE = re.compile(r'\s*\(\s*match(?:ing)?\s+case\s*\)\s*$', re.IGNORECASE)


def _mask_quotes(text):
    """text with everything inside "..." replaced by NULs (same length), so operators
    inside quotes are not seen."""
    out = []
    inside = False
    for ch in text:
        if ch == '"':
            inside = not inside
            out.append(ch)
        else:
            out.append(chr(0) if inside else ch)
    return ''.join(out)


def _unquote(text):
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in '"\'':
        return text[1:-1]
    return text


def parse_cell(text):
    """A condition from one line of text, for Excel or text driven rules:

        'Element > Category = Ducts'      'Item > Name contains PIPE'
        'Level >= 3'                       'Element > Mark is empty'
        'Item > Name like P-*'             'Element > Level between 1 and 3'
        'Element > Category is one of Ducts, Pipes'   'Item > Name matches ^P\\d+'
        'Element > "Is Mirrored" = Yes'   (quotes hide operator words in names or values)

    The left side is 'Category > Property' or just 'Property' (category '').
    '(match case)' at the end turns ignore_case off. Raises ValueError with a readable
    message when no comparison can be found."""
    raw = str(text or '').strip()
    if not raw:
        raise ValueError('The rule is empty.')
    ignore_case = True
    case = _CASE_RE.search(raw)
    if case:
        ignore_case = False
        raw = raw[:case.start()].rstrip()
    masked = _mask_quotes(raw)
    found = []
    for m in _SYMBOL_RE.finditer(masked):
        found.append((m.start(), m.end(), op_of(m.group(1)), m.group(1)))
    for m in _WORD_RE.finditer(masked):
        found.append((m.start(), m.end(), _WORD_MAP[' '.join(m.group(1).lower().split())], m.group(1)))
    found.sort(key=lambda f: (f[0], -(f[1] - f[0])))
    choice = None
    for index, (start, end, op, token) in enumerate(found):
        before = masked[:start].rstrip()
        if not before or before.endswith('>'):
            continue        # no property yet: 'Element > Is Mirrored = Yes' skips 'Is'
        if token == '>':
            if [f for f in found[index + 1:] if f[0] >= end]:
                continue    # a later comparison exists: this '>' separates category and property
            if to_number(_unquote(raw[end:])) is None:
                continue    # 'Element > Category' is a path, not "greater than Category"
        choice = (start, end, op)
        break
    if choice is None:
        raise ValueError('No comparison found in "%s". Write it like Element > Category = Ducts.'
                         % raw)
    start, end, op = choice
    left = raw[:start].strip()
    right = raw[end:].strip()
    parts = [_unquote(p) for p in _split_left(left)]
    if not parts or not parts[-1]:
        raise ValueError('No property found in "%s".' % raw)
    category = parts[0] if len(parts) > 1 else ''
    prop = ' > '.join(parts[1:]) if len(parts) > 1 else parts[0]
    value = None
    if NEEDS_VALUE[op]:
        if op == 'between':
            pieces = re.split(r'\s+and\s+|\s*\.\.\s*|\s*;\s*|\s*,\s+', right, flags=re.IGNORECASE)
            value = [_unquote(p) for p in pieces if p.strip()]
        elif op == 'in_list':
            value = [_unquote(p) for p in as_list(right)]
        else:
            value = _unquote(right)
            if op == 'regex' and len(value) >= 2 and value[0] == '/' and value[-1] == '/':
                value = value[1:-1]
    return {'category': category, 'property': prop, 'op': op, 'value': value,
            'ignore_case': ignore_case}


def _split_left(left):
    masked = _mask_quotes(left)
    parts = []
    last = 0
    for i, ch in enumerate(masked):
        if ch == '>':
            parts.append(left[last:i].strip())
            last = i + 1
    parts.append(left[last:].strip())
    return [p for p in parts if p]
