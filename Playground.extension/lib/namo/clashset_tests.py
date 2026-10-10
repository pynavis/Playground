# -*- coding: utf-8 -*-
"""Clash test definitions as plain data, and the one place Playground builds tests from them.

Clash Matrix, Clash Templates and Scan vs Model all create tests through here, so a
test made by any of them is made the same way. A definition is JSON-safe:

    {'name': 'Ducts vs Beams',
     'type': 'hard',               # hard | hard_conservative | clearance | duplicate
     'tolerance_m': 0.01,          # ALWAYS metres; the API stores model units
     'merge_composites': False,
     'a': side, 'b': side}

    side   = {'sources': [source, ...], 'self_intersect': False,
              'primitives': ['triangles']}     # triangles lines points snap_points text
    source = {'kind': 'set', 'path': 'MEP/Ducts', 'folder': False, 'search': query or None}
           | {'kind': 'model', 'name': 'MEP.nwc'}
           | {'kind': 'search', 'query': query, 'label': 'Element > Category = Ducts'}
           | {'kind': 'items', 'count': 120, 'entries': [...] or None}

A query is pynavis.sets' dict shape {'or': [{'and': [condition, ...]}]}. Set paths use
pynavis.sets' escaping: a literal '/' inside a name is written '\\/'.

How a side becomes a selection (the API half, resolve_side):
  * every source a set (or folder of sets): the side REFERENCES them through
    DocumentSelectionSets.CreateSelectionSource, so the test follows later edits of the
    sets, exactly like picking sets in Clash Detective's Select tab;
  * anything else (whole models, hand-picked items): explicit items, which is what
    Clash Detective stores when you pick a file in its Standard tree. A side that mixes
    both is made explicit and says so in its notes.
'search' sources have to be turned into sets by the caller first (Clash Matrix keeps
them in a 'Clash Matrix' set folder) so they stay live too.

Existing tests are UPDATED with TestsEditTestFromCopy on a CreateCopy of the live test:
that call is definition-only (pynavis' trap), which is exactly right here, and it keeps
the test's results, statuses and comments until the next run. New tests are added with
TestsAddCopy and re-found by Guid difference, like pynavis.clashtest.create.

Pure first; the API half lazy-imports pynavis inside the functions.
"""

import re

from namo import units

# (key, ClashTestType member, label). 'Custom' tests (plugin tests) cannot be rebuilt.
TYPES = [
    ('hard', 'Hard', 'Hard'),
    ('hard_conservative', 'HardConservative', 'Hard (conservative)'),
    ('clearance', 'Clearance', 'Clearance'),
    ('duplicate', 'Duplicate', 'Duplicates'),
]
TYPE_KEYS = [key for key, _member, _label in TYPES]
TYPE_LABELS = dict((key, label) for key, _member, label in TYPES)
_TYPE_MEMBER = dict((key, member) for key, member, _label in TYPES)
_MEMBER_TYPE = dict((member.lower(), key) for key, member, _label in TYPES)

# (key, PrimitiveTypes member, label as Clash Detective words it)
PRIMITIVES = [
    ('triangles', 'Triangles', 'Surfaces'),
    ('lines', 'Lines', 'Lines'),
    ('points', 'Points', 'Points'),
    ('snap_points', 'SnapPoints', 'Snap points'),
    ('text', 'Text', 'Text'),
]
PRIMITIVE_KEYS = [key for key, _member, _label in PRIMITIVES]
PRIMITIVE_LABELS = dict((key, label) for key, _member, label in PRIMITIVES)

SOURCE_KINDS = ('set', 'model', 'search', 'items')
MAX_ENTRIES = 2000          # explicit items remembered per side (same-document reuse)


# ---- pure: types, primitives, lengths ---------------------------------------------------


def type_member(key):
    """The ClashTestType member name for a type key ('hard' -> 'Hard'); ValueError when
    the key is not one Playground can build."""
    if key not in _TYPE_MEMBER:
        raise ValueError('Unknown clash test type "%s".' % (key,))
    return _TYPE_MEMBER[key]


def type_key(value):
    """The type key for a ClashTestType value or text ('HardConservative' ->
    'hard_conservative'); 'custom' for anything Playground cannot rebuild."""
    text = str(value or '').strip()
    key = _MEMBER_TYPE.get(text.lower().replace(' ', '').replace('_', ''))
    if key is not None:
        return key
    if text.lower() in _TYPE_MEMBER:
        return text.lower()
    return 'custom'


def decode_primitives(value, members):
    """Primitive keys set in a flags value. members: [(key, int_value)] from the live
    enum (pure so it is testable). Order follows PRIMITIVES."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return []
    found = []
    by_key = dict(members)
    for key in PRIMITIVE_KEYS:
        bit = by_key.get(key)
        if bit and number & int(bit) == int(bit):
            found.append(key)
    return found


def normalise_primitives(keys):
    """Known primitive keys in PRIMITIVES order, deduplicated; ['triangles'] when none."""
    wanted = set(str(k).strip().lower() for k in (keys or []))
    out = [key for key in PRIMITIVE_KEYS if key in wanted]
    return out or ['triangles']


def trim_number(value, decimals):
    """'1,250', '2.5', '0.038': thousands separators, at most `decimals` places, no
    trailing zeros, no '-0'."""
    text = ('{:,.%df}' % max(0, int(decimals))).format(float(value))
    if '.' in text:
        text = text.rstrip('0').rstrip('.')
    if text in ('-0', ''):
        text = '0'
    return text


_DECIMALS = {'mm': 1, 'cm': 2, 'm': 3, 'km': 4, 'um': 0}


def length_text(value, doc_units):
    """A length in document units as people read it: 1' 6 1/2" in a feet-and-inches
    document, '25 mm' / '0.038 m' otherwise. Negative values keep their sign (Clash
    Detective shows penetrations that way). None gives ''."""
    if value is None:
        return ''
    value = float(value)
    if units.is_imperial(doc_units):
        return units.format_length_input(value, doc_units)
    symbol = units.doc_unit_symbol(doc_units)
    return '%s %s' % (trim_number(value, _DECIMALS.get(symbol, 3)), symbol)


def tolerance_text(tolerance_m, doc_units):
    """A tolerance in metres shown in document units."""
    if tolerance_m is None:
        return ''
    return length_text(units.from_meters(tolerance_m, doc_units), doc_units)


# ---- pure: set paths -------------------------------------------------------------------


def join_set_path(names):
    """'A/B/Name' from names, escaping a literal '/' as '\\/' (pynavis.sets.find)."""
    return '/'.join(str(n).replace('/', '\\/') for n in names if str(n) != '')


def split_set_path(path):
    """The names in a set path, unescaping '\\/' (the reverse of join_set_path)."""
    parts = []
    current = []
    text = str(path or '')
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == '\\' and i + 1 < len(text) and text[i + 1] == '/':
            current.append('/')
            i += 2
            continue
        if ch == '/':
            parts.append(''.join(current))
            current = []
        else:
            current.append(ch)
        i += 1
    parts.append(''.join(current))
    return [p.strip() for p in parts if p.strip()]


def set_name_of(path):
    """The last name in a set path ('' for an empty path)."""
    parts = split_set_path(path)
    return parts[-1] if parts else ''


# ---- pure: definitions ----------------------------------------------------------------


def new_side(sources=None, primitives=None, self_intersect=False):
    return {'sources': list(sources or []), 'self_intersect': bool(self_intersect),
            'primitives': normalise_primitives(primitives)}


def new_definition(name, test_type='hard', tolerance_m=0.0, a=None, b=None,
                   merge_composites=False):
    return {'name': str(name or '').strip(), 'type': test_type,
            'tolerance_m': float(tolerance_m or 0.0), 'merge_composites': bool(merge_composites),
            'a': a if a is not None else new_side(), 'b': b if b is not None else new_side()}


def _normalise_source(source):
    if not isinstance(source, dict):
        return None
    kind = source.get('kind')
    if kind == 'set':
        path = str(source.get('path') or '').strip()
        if not path:
            return None
        search = source.get('search')
        return {'kind': 'set', 'path': path, 'folder': bool(source.get('folder', False)),
                'search': search if isinstance(search, dict) else None}
    if kind == 'model':
        name = str(source.get('name') or '').strip()
        return {'kind': 'model', 'name': name} if name else None
    if kind == 'search':
        query = source.get('query')
        if not isinstance(query, dict):
            return None
        return {'kind': 'search', 'query': query, 'label': str(source.get('label') or '')}
    if kind == 'items':
        entries = source.get('entries')
        return {'kind': 'items', 'count': int(source.get('count') or 0),
                'entries': entries if isinstance(entries, list) else None}
    return None


def normalise_side(side):
    side = side if isinstance(side, dict) else {}
    sources = [s for s in (_normalise_source(x) for x in side.get('sources') or []) if s]
    return new_side(sources, side.get('primitives'), side.get('self_intersect', False))


def normalise_definition(definition):
    """A clean copy with every key present (unknown keys dropped)."""
    d = definition if isinstance(definition, dict) else {}
    test_type = str(d.get('type') or 'hard').strip().lower()
    try:
        tolerance = float(d.get('tolerance_m') or 0.0)
    except (TypeError, ValueError):
        tolerance = 0.0
    return {'name': str(d.get('name') or '').strip(), 'type': test_type,
            'tolerance_m': tolerance, 'merge_composites': bool(d.get('merge_composites', False)),
            'a': normalise_side(d.get('a')), 'b': normalise_side(d.get('b'))}


def validate_definition(definition):
    """Sentences describing what stops this definition from becoming a test ([] when
    fine)."""
    d = normalise_definition(definition)
    problems = []
    if not d['name']:
        problems.append('The test needs a name.')
    if d['type'] not in _TYPE_MEMBER:
        problems.append('%s is a %s test, which Playground cannot rebuild.'
                        % (d['name'] or 'This', d['type']))
    if d['tolerance_m'] < 0:
        problems.append('The tolerance cannot be negative.')
    for key in ('a', 'b'):
        if not d[key]['sources']:
            problems.append('Selection %s is empty.' % key.upper())
    return problems


def describe_source(source):
    kind = source.get('kind')
    if kind == 'set':
        return ('Folder ' if source.get('folder') else 'Set ') + str(source.get('path', ''))
    if kind == 'model':
        return 'Model ' + str(source.get('name', ''))
    if kind == 'search':
        return 'Search ' + (source.get('label') or 'conditions')
    if kind == 'items':
        return '{:,} picked items'.format(int(source.get('count') or 0))
    return '?'


def describe_side(side):
    sources = (side or {}).get('sources') or []
    if not sources:
        return '(empty)'
    return '; '.join(describe_source(s) for s in sources)


def side_is_portable(side):
    """True when every source can be found again in another model (sets, models,
    searches; not hand-picked items)."""
    return all(s.get('kind') in ('set', 'model', 'search') for s in (side or {}).get('sources') or [])


def query_from_plan(groups):
    """pynavis query dict from rules.native_plan() groups of
    (category, property, op, value, ignore_case) atoms."""
    out = []
    for group in groups or []:
        conditions = []
        for category, prop, op, value, ignore_case in group:
            if op == 'exists':
                conditions.append({'category': category, 'prop': prop, 'op': 'has_property'})
                continue
            if op == 'missing':
                conditions.append({'category': category, 'prop': prop, 'op': 'not_has_property'})
                continue
            condition = {'category': category, 'prop': prop, 'op': op, 'value': value}
            if ignore_case:
                condition['ignore_case'] = True
            conditions.append(condition)
        out.append({'and': conditions})
    return {'or': out}


def query_groups(query):
    """The OR groups of a query dict (each a dict with 'and')."""
    if not isinstance(query, dict):
        return []
    return [g for g in query.get('or') or [] if isinstance(g, dict)]


def query_is_portable(query):
    """True when the query can be rebuilt as a search set: at least one group, every
    group has conditions, and no 'raw' condition (pynavis.sets.to_dict could not
    read it back)."""
    groups = query_groups(query)
    if not groups:
        return False
    for group in groups:
        conditions = group.get('and') or []
        if not conditions:
            return False
        for condition in conditions:
            if not isinstance(condition, dict) or condition.get('op') in (None, '', 'raw'):
                return False
    return True


def single_group_queries(query):
    """[query with one OR group] for each group (a search set holds one group)."""
    return [{'or': [group]} for group in query_groups(query)]


def unique_test_names(names, existing=()):
    """names made unique among themselves and existing (case-insensitive), with
    ' (2)'... appended, order kept."""
    taken = set(str(e).strip().lower() for e in existing)
    out = []
    for name in names:
        base = str(name)
        candidate = base
        n = 2
        while candidate.strip().lower() in taken:
            candidate = '%s (%d)' % (base, n)
            n += 1
        taken.add(candidate.strip().lower())
        out.append(candidate)
    return out


def safe_test_name(text):
    """A test name: control characters and line breaks become spaces, runs collapse,
    trimmed, at most 120 characters."""
    cleaned = re.sub(r'[\x00-\x1f\x7f]+', ' ', str(text or ''))
    cleaned = ' '.join(cleaned.split())
    return cleaned[:120].strip()


# ==== API half (Navisworks only; lazy imports) =========================================


def _doc(doc):
    if doc is not None:
        return doc
    from pynavis._api import Application
    return Application.ActiveDocument


def _clash():
    from pynavis import clash
    return clash


def clash_api():
    """Autodesk.Navisworks.Api.Clash (after pynavis.clash added the reference)."""
    _clash()
    import Autodesk.Navisworks.Api.Clash as ClashApi
    return ClashApi


def available(doc=None):
    """True when Clash Detective can be used in this session (Navisworks Manage with a
    document). Never raises."""
    try:
        return _clash().get_clash(_doc(doc)).TestsData is not None
    except Exception:
        return False


def doc_units(doc=None):
    try:
        return str(_doc(doc).Units)
    except Exception:
        return 'Meters'


def _primitive_members(Api):
    out = []
    for key, member, _label in PRIMITIVES:
        try:
            out.append((key, int(getattr(Api.PrimitiveTypes, member))))
        except Exception:
            continue
    return out


def combine_flags(flags, to_enum=None):
    """Combines flag enum values. `|` first (what a .NET [Flags] enum supports under
    IronPython); when the enum refuses it, the integer values are ORed and turned back
    into the enum with to_enum(int). Pure over the two callables."""
    value = None
    for flag in flags:
        if value is None:
            value = flag
            continue
        try:
            value = value | flag
        except Exception:
            number = int(value) | int(flag)
            value = to_enum(number) if to_enum is not None else number
    return value


def primitive_flags(keys, Api=None):
    """A PrimitiveTypes value with every key in keys set."""
    if Api is None:
        from pynavis._api import Api
    wanted = normalise_primitives(keys)
    enum_type = Api.PrimitiveTypes

    def to_enum(number):
        from System import Enum
        return Enum.ToObject(enum_type, int(number))

    return combine_flags([getattr(enum_type, member) for key, member, _label in PRIMITIVES
                          if key in wanted], to_enum)


def set_path_of(item, doc=None):
    """The '/'-joined, escaped path of a selection set or folder ('' for the root)."""
    document = _doc(doc)
    root = document.SelectionSets.RootItem
    root_guid = str(root.Guid)
    names = []
    node = item
    while node is not None and str(node.Guid) != root_guid:
        if node.DisplayName:
            names.append(node.DisplayName)
        node = node.Parent
    names.reverse()
    return join_set_path(names)


def _model_root_name(item):
    from namo import items as _items
    return _items.model_name(item)


def _read_side(clash_selection, document):
    """A side dict from a live ClashSelection."""
    from pynavis._api import Api
    selection = clash_selection.Selection
    sources = []
    if selection.HasSelectionSources:
        for source in selection.SelectionSources:
            saved = None
            try:
                saved = document.SelectionSets.ResolveSelectionSource(source)
            except Exception:
                saved = None
            if saved is None:
                sources.append({'kind': 'set', 'path': str(source), 'folder': False,
                                'search': None, 'missing': True})
                continue
            entry = {'kind': 'set', 'path': set_path_of(saved, document),
                     'folder': isinstance(saved, Api.FolderItem), 'search': None}
            if not entry['folder'] and getattr(saved, 'HasSearch', False):
                try:
                    from pynavis import sets
                    from namo import find_query
                    # to_dict leaves VariantData's type prefix on text values
                    # ('DisplayString:Ducts'); a set rebuilt with it finds nothing.
                    entry['search'] = find_query.stored_query(sets.to_dict(saved, document))
                except Exception:
                    entry['search'] = None
            sources.append(entry)
    if selection.HasExplicitSelection:
        explicit = list(selection.ExplicitSelection)
        if explicit and all(item.Parent is None for item in explicit):
            for item in explicit:
                name = _model_root_name(item)
                if name:
                    sources.append({'kind': 'model', 'name': name})
        elif explicit:
            entries = None
            if len(explicit) <= MAX_ENTRIES:
                try:
                    from namo import items as _items
                    entries = _items.entries(explicit, document)
                except Exception:
                    entries = None
            sources.append({'kind': 'items', 'count': len(explicit), 'entries': entries})
    try:
        primitives = decode_primitives(clash_selection.PrimitiveTypes,
                                       _primitive_members(Api))
    except Exception:
        primitives = ['triangles']
    try:
        self_intersect = bool(clash_selection.SelfIntersect)
    except Exception:
        self_intersect = False
    side = new_side(sources, primitives, self_intersect)
    return side


def read_definition(test, doc=None):
    """The definition of a live ClashTest (tolerance converted to metres)."""
    document = _doc(doc)
    tolerance_m = units.to_meters(float(test.Tolerance), doc_units(document))
    definition = new_definition(test.DisplayName, type_key(test.TestType), tolerance_m,
                                _read_side(test.SelectionA, document),
                                _read_side(test.SelectionB, document),
                                bool(getattr(test, 'MergeComposites', False)))
    return definition


def find_model_roots(name, doc=None):
    """Root items of the models whose source/file name matches name (case-insensitive,
    by file name; '*' and '?' wildcards allowed)."""
    from namo import items as _items
    from namo import rules
    wanted = str(name or '').strip()
    if not wanted:
        return []
    pattern = rules.wildcard_regex(wanted.lower(), True)
    out = []
    for model in _items.models(doc):
        names = set([model['name'].lower()])
        for text in (model.get('source'), model.get('file')):
            if text:
                names.add(str(text).replace('\\', '/').split('/')[-1].lower())
        if any(pattern.match(n) for n in names):
            out.append(model['root'])
    return out


def find_set(path, doc=None):
    """The selection set or folder at path (then, failing that, the first one named
    like its last segment anywhere), or None."""
    from pynavis import sets
    document = _doc(doc)
    found = None
    try:
        found = sets.find(path, document)
    except Exception:
        found = None
    if found is None:
        name = set_name_of(path)
        if name and len(split_set_path(path)) > 1:
            try:
                found = sets.find(name.replace('/', '\\/'), document)
            except Exception:
                found = None
    return found


def resolve_side(side, doc=None):
    """How one side will be written: {'sources': SelectionSourceCollection or None,
    'items': ModelItemCollection or None, 'missing': [sentences], 'notes': [sentences],
    'labels': [text]}. 'search' sources must already have been turned into sets."""
    from pynavis._api import Api
    from namo import items as _items
    document = _doc(doc)
    side = normalise_side(side)
    missing = []
    notes = []
    labels = []
    saved_items = []
    explicit = []
    for source in side['sources']:
        kind = source['kind']
        labels.append(describe_source(source))
        if kind == 'set':
            found = find_set(source['path'], document)
            if found is None:
                missing.append('Selection set "%s" is not in this model.' % source['path'])
            else:
                saved_items.append(found)
        elif kind == 'model':
            roots = find_model_roots(source['name'], document)
            if not roots:
                missing.append('Model "%s" is not loaded.' % source['name'])
            explicit.extend(roots)
        elif kind == 'items':
            if source.get('entries'):
                found_items, lost = _items.resolve(source['entries'], document)
                if lost:
                    missing.append('{:,} of the picked items are not in this model.'.format(lost))
                explicit.extend(found_items)
            else:
                missing.append('{:,} hand-picked items cannot be found again; use a selection set.'
                               .format(int(source.get('count') or 0)))
        else:
            missing.append('A search must be saved as a selection set first.')
    result = {'sources': None, 'items': None, 'missing': missing, 'notes': notes,
              'labels': labels, 'saved': saved_items, 'explicit': explicit}
    if saved_items and not explicit:
        try:
            collection = Api.SelectionSourceCollection()
            for saved in saved_items:
                collection.Add(document.SelectionSets.CreateSelectionSource(saved))
            result['sources'] = collection
            return result
        except Exception:
            # This Navisworks will not hand out set references: fall back to the sets'
            # items (what the catalog asks for) and say so.
            notes.append(SET_FALLBACK_NOTE)
            result['items'] = explicit_items(result, document)
            return result
    result['items'] = explicit_items(result, document)
    if saved_items:
        notes.append('This side mixes sets with models or items, so it holds today\'s items '
                     'and will not follow later set changes.')
    return result


SET_FALLBACK_NOTE = ('Navisworks did not accept a reference to the selection sets, so this side '
                     'holds today\'s items and will not follow later set changes.')


def explicit_items(resolved, doc=None):
    """A ModelItemCollection of everything a resolved side stands for today: the items
    of its sets (a folder: every set inside it) plus its models and picked items."""
    from pynavis._api import Api
    document = _doc(doc)
    collection = Api.ModelItemCollection()
    seen = set()

    def add_set(saved):
        if isinstance(saved, Api.FolderItem):
            for child in saved.Children:
                add_set(child)
            return
        try:
            for item in saved.GetSelectedItems(document):
                if item not in seen:
                    seen.add(item)
                    collection.Add(item)
        except Exception:
            resolved['missing'].append('Selection set "%s" could not be read.' % saved.DisplayName)

    for saved in resolved.get('saved') or []:
        add_set(saved)
    for item in resolved.get('explicit') or []:
        if item not in seen:
            seen.add(item)
            collection.Add(item)
    return collection


def _note(resolved, sentence):
    if sentence not in resolved['notes']:
        resolved['notes'].append(sentence)


def _set_if_different(target, attribute, value):
    """Writes target.attribute only when it differs (a new ClashTest already holds the
    usual values, so an ordinary test touches nothing pynavis.clashtest.create does
    not). Returns False when Navisworks refused the write."""
    try:
        current = getattr(target, attribute)
        if current == value:
            return True
        if not isinstance(value, bool) and int(current) == int(value):
            return True
    except Exception:
        pass
    try:
        setattr(target, attribute, value)
        return True
    except Exception:
        return False


def configure(test, definition, resolved_a, resolved_b, doc=None):
    """Writes a definition onto a ClashTest object (a new one or a CreateCopy). Name,
    type, tolerance and the two selections are written the way pynavis.clashtest.create
    writes them; geometry types, self-intersect and merge-composites only when they
    differ from what the test already holds. A setting Navisworks refuses becomes a note
    on that side instead of an error."""
    ClashApi = clash_api()
    document = _doc(doc)
    d = normalise_definition(definition)
    test.DisplayName = d['name']
    test.TestType = getattr(ClashApi.ClashTestType, type_member(d['type']))
    test.Tolerance = units.from_meters(d['tolerance_m'], doc_units(document))
    _set_if_different(test, 'MergeComposites', d['merge_composites'])
    for key, clash_selection, resolved in (('a', test.SelectionA, resolved_a),
                                           ('b', test.SelectionB, resolved_b)):
        side = d[key]
        _set_if_different(clash_selection, 'SelfIntersect', side['self_intersect'])
        try:
            flags = primitive_flags(side['primitives'])
        except Exception:
            flags = None
        if flags is None or not _set_if_different(clash_selection, 'PrimitiveTypes', flags):
            _note(resolved, 'The geometry types (%s) could not be set; check them in Clash '
                            'Detective.' % ', '.join(PRIMITIVE_LABELS[k] for k in side['primitives']))
        if resolved['sources'] is not None:
            try:
                clash_selection.Selection.CopyFrom(resolved['sources'])
                continue
            except Exception:
                _note(resolved, SET_FALLBACK_NOTE)
                resolved['sources'] = None
                resolved['items'] = explicit_items(resolved, document)
        clash_selection.Selection.CopyFrom(resolved['items'])
    return test


def _all_tests(document):
    return list(_clash().walk_tests(document))


def find_test(name, doc=None):
    """The live test named name (exact, then ignoring case), or None."""
    wanted = str(name or '').strip()
    tests = _all_tests(_doc(doc))
    for test in tests:
        if test.DisplayName == wanted:
            return test
    lowered = wanted.lower()
    for test in tests:
        if test.DisplayName.strip().lower() == lowered:
            return test
    return None


def test_names(doc=None):
    return [t.DisplayName for t in _all_tests(_doc(doc))]


def _resolve_added(tests, before):
    for item in tests:
        if str(item.Guid) not in before:
            return item
    return None


def write_test(definition, resolved_a, resolved_b, existing='skip', doc=None):
    """Creates the test, or updates the existing test with the same name
    (existing='update', results kept) or leaves it (existing='skip').
    Returns (outcome, live test or None) with outcome 'created' | 'updated' | 'skipped'.
    Call inside one transaction for a batch (one undo step)."""
    ClashApi = clash_api()
    document = _doc(doc)
    data = _clash().get_clash(document).TestsData
    live = find_test(definition['name'], document)
    if live is not None:
        if existing != 'update':
            return 'skipped', live
        copy = live.CreateCopy()
        configure(copy, dict(definition, name=live.DisplayName), resolved_a, resolved_b, document)
        data.TestsEditTestFromCopy(live, copy)
        return 'updated', live
    fresh = ClashApi.ClashTest()
    configure(fresh, definition, resolved_a, resolved_b, document)
    before = set(str(item.Guid) for item in data.Tests)
    data.TestsAddCopy(fresh)
    return 'created', _resolve_added(data.Tests, before)


def references_sets(test):
    """True when side A or B of a live test holds selection-set references (a check
    that CreateSelectionSource survived the copy into the document)."""
    try:
        return bool(test.SelectionA.Selection.HasSelectionSources
                    or test.SelectionB.Selection.HasSelectionSources)
    except Exception:
        return False


def run_tests(tests, doc=None, progress=None):
    """Runs tests one by one (pynavis.clashtest.run). progress(fraction, label) between
    tests; returning False stops (raises items.Cancelled). Returns {guid: result count}."""
    from pynavis import clashtest
    from namo import clashdata
    document = _doc(doc)
    data = _clash().get_clash(document).TestsData
    counts = {}
    total = len(tests) or 1
    for index, test in enumerate(tests):
        name = test.DisplayName
        if progress is not None and progress(float(index) / total, 'Running %s' % name) == False:  # noqa: E712
            raise clashdata.Cancelled()
        guid = str(test.Guid)
        clashtest.run(test, document)
        live = _by_guid(data, guid)
        counts[guid] = result_count(live if live is not None else test)
    if progress is not None:
        progress(1.0, 'Done')
    return counts


def _by_guid(data, guid_text):
    try:
        from System import Guid
        return data.ResolveGuid(Guid(guid_text))
    except Exception:
        return None


def has_results(test):
    """True when a test holds anything at all (a look at its first level only)."""
    children = test.Children
    try:
        return int(children.Count) > 0
    except Exception:
        try:
            return len(children) > 0
        except Exception:
            return True


def result_count(test):
    """How many clash results a test holds: pynavis.clash.count_results, the walk the
    shipped Clash Grouper counts with (groups are not counted, the clashes in them
    are). Roughly a second per few hundred thousand results."""
    return int(_clash().count_results(test)[0])


def test_rows(doc=None, with_counts=True):
    """[{'value': index, 'cells': [path, type, results], 'test': ClashTest}] for every
    test, tree order (for ui.choose)."""
    from namo import clashdata
    rows = []
    for index, test in enumerate(_all_tests(_doc(doc))):
        count = ''
        if with_counts:
            try:
                count = result_count(test)
            except Exception:
                count = ''
        rows.append({'value': index, 'cells': [clashdata.test_path(test),
                                               TYPE_LABELS.get(type_key(test.TestType), 'Custom'),
                                               count],
                     'test': test})
    return rows
