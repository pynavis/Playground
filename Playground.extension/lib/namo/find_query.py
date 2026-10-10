# -*- coding: utf-8 -*-
"""Native search conditions built from property values, shared by the Select and Find tools.

Select Similar, Filter Selection, the Search Set Wizard, Batch Sets and Set Exchange all
turn "this property has this value" into a pynavis query dict
({'or': [{'and': [condition, ...]}]}, the shape sets.run / sets.create accept). The rules
that decide whether such a search matches what the user sees live here, once:

  * A value keeps its KIND. pynavis compiles an int with VariantData.FromInt32, a float
    with FromDouble, a bool with FromBoolean and text with FromDisplayString, and a
    native EqualValue only matches a property stored the same way. So a value read from
    a property (pynavis.props coerces Int32 -> int, Double* -> float, Boolean -> bool,
    text -> str) is sent back as the same Python type, and text typed by a user is
    coerced to the kind observed on that property.
  * Floats never use equality. A length or area is a DoubleLength/DoubleArea variant
    and FromDouble may not compare equal to it; float noise does the rest. A float
    "equals" becomes NumericGreaterThanOrEqual + NumericLessThanOrEqual around the
    value (relative tolerance FLOAT_TOLERANCE), which compares numbers whatever the
    double's subtype.
  * Text equality ignores case unless asked not to (users type 'ducts').

Pure half first (unit tested on both engines); the sampling helpers at the bottom need
Navisworks and lazy-import it.
"""

import datetime

FLOAT_TOLERANCE = 1e-6          # relative, with an absolute floor of FLOAT_FLOOR
FLOAT_FLOOR = 1e-9

KINDS = ('text', 'int', 'float', 'bool')
BRANCHES = 48                   # how many tree branches a property sample is spread over

# The native search operators the Find tools offer, in menu order:
# (op, label, needs_value). Values are pynavis _query op names.
NATIVE_OPS = [
    ('equals', 'equals', True),
    ('not_equals', 'does not equal', True),
    ('contains', 'contains', True),
    ('wildcard', 'matches wildcard', True),
    ('gt', 'greater than', True),
    ('ge', 'at least', True),
    ('lt', 'less than', True),
    ('le', 'at most', True),
    ('has_property', 'exists', False),
    ('not_has_property', 'is missing', False),
]
OP_LABELS = dict((op, label) for op, label, _needs in NATIVE_OPS)
OP_NEEDS_VALUE = dict((op, needs) for op, _label, needs in NATIVE_OPS)
NUMERIC_OPS = ('gt', 'ge', 'lt', 'le')
TEXT_OPS = ('contains', 'wildcard')
SYMBOLS = {'equals': '=', 'not_equals': '!=', 'gt': '>', 'ge': '>=', 'lt': '<', 'le': '<=',
           'contains': 'contains', 'wildcard': 'like', 'has_property': 'exists',
           'not_has_property': 'is missing', 'has_category': 'has category'}

NO_VALUE = '(no value)'

# pynavis.props hands back VariantData.ToString() for the kinds it does not convert, and
# that text starts with the data type ('NamedConstant:...'). A search built from such
# text compares it as a display string and finds nothing, so these values are not
# offered for matching at all.
_UNSEARCHABLE = ('NamedConstant', 'Point2D', 'Point3D', 'DateTime')


# ---- values -------------------------------------------------------------------------


def kind_of(value):
    """'bool' | 'int' | 'float' | 'text' for a value pynavis.props returned, or None
    when a native search cannot compare it (dates, points, None)."""
    if value is None:
        return None
    if isinstance(value, bool):
        return 'bool'
    if isinstance(value, int):
        return 'int'
    if isinstance(value, float):
        return 'float'
    if isinstance(value, (datetime.datetime, datetime.date, tuple, list)):
        return None
    if isinstance(value, str) and ':' in value and value.split(':', 1)[0] in _UNSEARCHABLE:
        return None
    return 'text'


def value_text(value):
    """How a value reads in lists and names: Yes/No, floats without trailing zeros,
    blank as NO_VALUE."""
    if value is None:
        return NO_VALUE
    if isinstance(value, bool):
        return 'Yes' if value else 'No'
    if isinstance(value, float):
        text = ('%.6f' % value).rstrip('0').rstrip('.')
        return '0' if text in ('', '-0') else text
    text = str(value)
    return text if text.strip() else NO_VALUE


def parse_number(text):
    """A number from user text ('1,234.5', '12,5', '-3'), or None."""
    from namo import units
    if text is None:
        return None
    if isinstance(text, bool):
        return None
    if isinstance(text, (int, float)):
        return float(text)
    return units.parse_number(str(text).strip())


def coerce(text, kind):
    """User text as a value of `kind` for a native search. Raises ValueError with a
    sentence when it does not read (shown under the field)."""
    if kind == 'bool':
        word = str(text).strip().lower()
        if word in ('yes', 'true', '1', 'y', 'on'):
            return True
        if word in ('no', 'false', '0', 'n', 'off'):
            return False
        raise ValueError('Type Yes or No.')
    if kind in ('int', 'float'):
        number = parse_number(text)
        if number is None:
            raise ValueError('Type a number.')
        if kind == 'int' and number == int(number) and abs(number) < 2147483648:
            return int(number)
        return float(number)
    return str(text)


def majority_kind(values):
    """The kind most values share (ties: text, then float, then int, then bool), or
    'text' when nothing is comparable. int and float together read as float."""
    counts = {}
    for value in values:
        kind = kind_of(value)
        if kind is not None:
            counts[kind] = counts.get(kind, 0) + 1
    if not counts:
        return 'text'
    if 'int' in counts and 'float' in counts:
        counts['float'] = counts['float'] + counts.pop('int')
    order = ['text', 'float', 'int', 'bool']
    return sorted(counts, key=lambda k: (-counts[k], order.index(k)))[0]


def tolerance(value):
    """Half-width of the window a float 'equals' searches."""
    return max(FLOAT_FLOOR, abs(float(value)) * FLOAT_TOLERANCE)


# pynavis.sets reads a saved condition's value with VariantData.ToString() for every kind
# it does not convert itself (it converts Boolean, Int32, Double, DoubleLength), and
# Navisworks puts the data type in front of that text: 'DisplayString:Ducts'. A condition
# written back with that text finds nothing, so values read from saved sets are cleaned.
_STORED_TEXT = ('DisplayString', 'IdentifierString')
_STORED_FLOAT = ('Double', 'DoubleLength', 'DoubleArea', 'DoubleVolume', 'DoubleAngle')
_STORED_INT = ('Int32', 'Int64', 'Nat32', 'Nat64')


def stored_value(value):
    """A condition value read from a saved search set (pynavis.sets.to_dict / export_all)
    without the data-type prefix VariantData.ToString() writes: 'DisplayString:Ducts'
    gives 'Ducts', 'DoubleArea:12.5' gives 12.5. Anything else comes back unchanged."""
    if not isinstance(value, str) or ':' not in value:
        return value
    kind, rest = value.split(':', 1)
    if kind in _STORED_TEXT:
        return rest
    if kind in _STORED_FLOAT or kind in _STORED_INT:
        number = parse_number(rest)
        if number is None:
            return value
        if kind in _STORED_INT and number == int(number) and abs(number) < 2147483648:
            return int(number)
        return float(number)
    return value


def stored_conditions(conds):
    """Copies of condition dicts with stored_value applied to each value."""
    out = []
    for cond in conds or []:
        if isinstance(cond, dict) and 'value' in cond:
            cond = dict(cond)
            cond['value'] = stored_value(cond['value'])
        out.append(cond)
    return out


def stored_query(query):
    """A {'or': [{'and': [...]}]} query with stored_value applied to every condition
    (other keys kept)."""
    if not isinstance(query, dict):
        return query
    out = dict(query)
    groups = []
    for group in query.get('or') or []:
        if isinstance(group, dict):
            group = dict(group)
            group['and'] = stored_conditions(group.get('and'))
        groups.append(group)
    out['or'] = groups
    return out


# ---- conditions -----------------------------------------------------------------------


def _cond(category, prop, op, value=None, ignore_case=False):
    out = {'category': category, 'prop': prop, 'op': op}
    if value is not None:
        out['value'] = value
    if ignore_case:
        out['ignore_case'] = True
    return out


def conditions(category, prop, op, value=None, kind='text', ignore_case=True):
    """pynavis condition dicts (one, or two for a float equals) for one rule.

    `value` is already typed (see coerce); `kind` says how it is compared. ignore_case
    only applies to text equals / not equals / contains / wildcard. Raises ValueError
    for an unknown op or a value the op cannot use."""
    if op not in OP_NEEDS_VALUE:
        raise ValueError('Unknown operator %r.' % (op,))
    if not OP_NEEDS_VALUE[op]:
        return [_cond(category, prop, op)]
    if value is None:
        raise ValueError('This operator needs a value.')
    if op in NUMERIC_OPS:
        number = parse_number(value)
        if number is None:
            raise ValueError('Type a number.')
        return [_cond(category, prop, op, float(number))]
    if op in TEXT_OPS:
        return [_cond(category, prop, op, str(value), bool(ignore_case))]
    # equals / not_equals keep the kind
    if kind == 'float':
        number = parse_number(value)
        if number is None:
            raise ValueError('Type a number.')
        if op == 'equals':
            half = tolerance(number)
            return [_cond(category, prop, 'ge', float(number) - half),
                    _cond(category, prop, 'le', float(number) + half)]
        return [_cond(category, prop, op, float(number))]
    if kind == 'int':
        typed = coerce(value, 'int')
        return [_cond(category, prop, op, typed)]
    if kind == 'bool':
        return [_cond(category, prop, op, coerce(value, 'bool'))]
    return [_cond(category, prop, op, str(value), bool(ignore_case))]


def query_dict(groups):
    """{'or': [{'and': conds}, ...]} from a list of condition lists (empty groups
    dropped)."""
    return {'or': [{'and': list(group)} for group in groups if group]}


def describe(category, prop, op, value=None):
    """'Element > Category = Ducts' for one rule (as the user set it)."""
    left = '%s > %s' % (category, prop) if category else str(prop)
    if not OP_NEEDS_VALUE.get(op, True):
        return '%s %s' % (left, SYMBOLS.get(op, op))
    shown = value_text(value) if not isinstance(value, str) else value
    return '%s %s %s' % (left, SYMBOLS.get(op, op), shown)


def describe_condition(cond):
    """Text for a pynavis condition dict (from sets.to_dict or conditions())."""
    op = cond.get('op', '')
    if op == 'raw':
        return cond.get('text', '') or '(unreadable condition)'
    if op == 'has_category':
        return 'has category %s' % cond.get('category', '')
    return describe(cond.get('category', ''), cond.get('prop', ''), op, stored_value(cond.get('value')))


def join_descriptions(texts, limit=3):
    """'A; B; C and 2 more' for a toast detail."""
    texts = [t for t in texts if t]
    if len(texts) <= limit:
        return '; '.join(texts)
    return '%s and %d more' % ('; '.join(texts[:limit]), len(texts) - limit)


# ---- sampled values ---------------------------------------------------------------------


def tally_values(values):
    """[(text, count, raw_value)] most common first (ties by natural text order): every
    value counted by its value_text, the first raw value seen kept so a native search
    can be typed from it."""
    from namo import naming
    counts = {}
    raw = {}
    for value in values:
        text = value_text(value)
        counts[text] = counts.get(text, 0) + 1
        if text not in raw:
            raw[text] = value
    rows = [(text, counts[text], raw[text]) for text in counts]
    rows.sort(key=lambda r: (-r[1], naming.natural_key(r[0]), r[0]))
    return rows


def spread(total, buckets):
    """How many of `total` samples each of `buckets` sources gets (as even as possible,
    earlier buckets get the remainder)."""
    if buckets <= 0:
        return []
    base, extra = divmod(max(0, int(total)), buckets)
    return [base + (1 if i < extra else 0) for i in range(buckets)]


# ---- API half -------------------------------------------------------------------------------


def branches(roots, children_of, want=BRANCHES, max_depth=4):
    """The roots opened up, level by level, until there are at least `want` branches (or
    max_depth levels were opened). Pure: children_of(node) -> iterable.

    A sample that takes the first N elements of each file sees only the start of the
    tree: the first level, the first category. Sampling a share from each branch instead
    reaches every level and category of a model, at the cost of listing a few dozen
    nodes. A node without children stays a branch of its own."""
    current = list(roots)
    for _depth in range(max_depth):
        if len(current) >= want:
            break
        opened = []
        grew = False
        for node in current:
            children = list(children_of(node))
            if children:
                opened.extend(children)
                grew = True
            else:
                opened.append(node)
        if not grew:
            break
        current = opened
    return current


def sample_objects(roots, total=2000, tick=None):
    """Up to `total` element-level items spread over the branches of the roots (see
    branches(): every model, level and category gets a share, so the start of the first
    file does not take the whole sample). Returns an ItemList (namo.items) whose
    .sampled is True when the budget cut a branch short."""
    from namo import items
    parts = branches(items.as_list(roots), lambda node: node.Children)
    if len(parts) > total > 0:
        step = len(parts) / float(total)        # more branches than budget: every nth
        parts = [parts[int(i * step)] for i in range(int(total))]
    out = items.ItemList()
    shares = spread(total, len(parts))
    seen = set()
    sampled = False
    spare = 0
    for part, share in zip(parts, shares):
        share += spare                          # a small branch passes its share on
        spare = 0
        if share <= 0:
            sampled = True
            continue
        found = items.objects([part], tick=tick, budget=share)
        if found.sampled:
            sampled = True
        else:
            spare = share - len(found)
        for element in found:
            if element not in seen:
                seen.add(element)
                out.append(element)
    out.sampled = sampled
    return out


def read(item, category, prop, fallback_to_object=False):
    """(exists, value) for one property by display names; value is pynavis-coerced."""
    from namo import variants
    try:
        value = variants.get(item, category, prop)
    except Exception:
        value = None
    if value is None and fallback_to_object:
        from namo import items
        element = items.object_of(item)
        if element is not item:
            try:
                same = element.Equals(item)
            except Exception:
                same = False
            if not same:
                try:
                    value = variants.get(element, category, prop)
                except Exception:
                    value = None
    return value is not None, value
