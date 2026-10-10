# -*- coding: utf-8 -*-
"""Property scanning shared by Property Explorer, Count by Property, Data Validator and
the Write Data tools: scopes, fast value reading, the category > property > value index.

Pure half (unit tested on both engines):
  * scope choices and labels (SCOPES, LEVELS, default_scope, scope_text)
  * value display: display_text(kind, value, ctx) turns one property reading into the
    text people see and group by ('3,000 mm', 'Yes', '2026-10-05'), plain_value() the
    value rules compare against (numbers in report units)
  * PropIndex: category -> property -> value -> count, with item counts, distinct
    counts, value kinds and a cap on distinct values per property (memory stays bounded
    on 200,000-item scans; a capped property says so)
  * pivot(): one- or two-level counts for Count by Property

API half (lazy pynavis imports):
  * kind_table(), coerce(variant): one VariantData read by its DataType (two .NET calls
    per value instead of pynavis.props' probe chain, which scans dir() on every value)
  * read_all(item), read_one(item, category, property), getter(item) for namo.rules
  * scope_items(scope, level): the items a tool works on, with budget + tick
  * scan(items): a PropIndex over items; the last scan per document is cached in the
    session (holder 'propindex') and invalidated when Playground writes properties
  * find_matching(items, category, property, text): items whose value shows as text

Quantities: a DoubleLength / DoubleArea / DoubleVolume value is taken to be in the
units of the item's own source model (Model.Units; a Revit export stores feet, square
feet and cubic feet), the same reading namo.takeoff uses, and angles in radians. The
Reader converts them to SI the moment it reads them (Reader.si), so everything
downstream (display_text, plain_value, the index) works in SI and shows report units.
Nobody has confirmed the stored units in Navisworks yet: QUANTITY_SOURCE below is the
one switch ('si' if lengths turn out to arrive in metres), and every shown quantity
carries its unit symbol so a wrong reading is visible, never silent.
"""

import time

from namo import naming, units

NO_VALUE = '(no value)'          # same text as namo.items.NO_VALUE
MISSING = '(missing)'            # the property is not on the item at all
MAX_VALUES = 10000               # distinct values kept per property before capping
DEFAULT_BUDGET = 200000
TICK_EVERY = 200

SCOPES = [('selection', 'Current selection'), ('visible', 'Visible items'),
          ('model', 'Whole model')]
LEVELS = [('objects', 'Objects (elements)'), ('geometry', 'Every geometry item')]
SCOPE_NAMES = dict(SCOPES)
LEVEL_NAMES = dict(LEVELS)

QUANTITY_KINDS = ('length', 'area', 'volume', 'angle')
QUANTITY_SOURCE = 'model'        # 'model': values are in the item's Model.Units; 'si': metres
_QUANTITY_POWER = {'length': 1, 'area': 2, 'volume': 3}
NUMBER_KINDS = ('int', 'float') + QUANTITY_KINDS

# VariantDataType member name -> kind. Kinds are what the tools reason about.
TYPE_KINDS = [
    ('DisplayString', 'text'), ('IdentifierString', 'text'), ('NamedConstant', 'text'),
    ('Boolean', 'bool'), ('Int32', 'int'), ('Int64', 'int'), ('Nat32', 'int'), ('Nat64', 'int'),
    ('Double', 'float'), ('DoubleLength', 'length'), ('DoubleArea', 'area'),
    ('DoubleVolume', 'volume'), ('DoubleAngle', 'angle'), ('DateTime', 'date'),
    ('Point3D', 'point'), ('Point2D', 'point'), ('None', 'none'),
]

# Value types a native search compares exactly against what pynavis.sets compiles
# (FromDisplayString / FromInt32 / FromBoolean). Anything else gets a fixed set.
SEARCHABLE_TYPES = ('DisplayString', 'Int32', 'Boolean')


# =============================================================================
# Pure half
# =============================================================================


def default_scope(has_selection, remembered=None):
    """The scope a dialog opens on: the selection when one exists, otherwise the
    remembered choice (unless that was the selection), else the whole model."""
    if has_selection:
        return 'selection'
    if remembered in ('visible', 'model'):
        return remembered
    return 'model'


def scope_options(has_selection):
    """(label, value) pairs for a scope radio; the selection is offered only when
    something is selected."""
    return [(label, value) for value, label in SCOPES
            if value != 'selection' or has_selection]


def noun(level, count):
    """'object' / 'objects' / 'geometry item' / 'geometry items' for a count."""
    if level == 'geometry':
        return 'geometry item' if count == 1 else 'geometry items'
    return 'object' if count == 1 else 'objects'


def scope_text(scope, level, count, sampled=False):
    """'4,210 objects in the current selection' (+ ', sampled' when a budget cut it)."""
    where = {'selection': 'in the current selection', 'visible': 'among visible items',
             'model': 'in the whole model'}.get(scope, '')
    text = '%s %s' % ('{:,}'.format(count), noun(level, count))
    if where:
        text += ' ' + where
    if sampled:
        text += ' (sampled: the scan stopped at the budget)'
    return text


def pair_text(category, prop):
    """'Element > Category'."""
    return '%s > %s' % (category, prop)


def split_pair(text):
    """('Element', 'Category') from 'Element > Category' (also '>' without spaces);
    a bare name is ('', name). None for blank text."""
    text = (text or '').strip()
    if not text:
        return None
    if '>' not in text:
        return ('', text)
    left, right = text.split('>', 1)
    return (left.strip(), right.strip())


def context_for(doc_units, report_units='auto'):
    """The display context for values: {'doc_units', 'length', 'area', 'volume',
    'imperial'}. Quantities are shown in config report units ('auto' = document)."""
    chosen = units.report_units_for(report_units, doc_units)
    ctx = dict(chosen)
    ctx['doc_units'] = doc_units
    ctx['imperial'] = chosen['length'] in ('ft', 'in')
    return ctx


def _trim_number(text):
    """'3,000.000' -> '3,000'; '2.500' -> '2.5'; '-0' -> '0'."""
    if '.' in text:
        text = text.rstrip('0').rstrip('.')
    if text in ('-0', ''):
        return '0'
    return text


def _number(value, decimals):
    return _trim_number(('{:,.%df}' % decimals).format(float(value)))


_LENGTH_DECIMALS = {'mm': 1, 'cm': 2, 'm': 3, 'in': 2, 'ft': 3}


def quantity_value(kind, value, ctx):
    """An SI quantity converted to the context's unit (float), and that unit symbol."""
    if kind == 'length':
        unit = ctx.get('length') or 'm'
        return units.convert(value, 'm', unit), unit
    if kind == 'area':
        unit = ctx.get('area') or 'm2'
        return units.convert(value, 'm2', unit), unit
    if kind == 'volume':
        unit = ctx.get('volume') or 'm3'
        return units.convert(value, 'm3', unit), unit
    if kind == 'angle':
        import math
        return math.degrees(value), 'deg'
    return value, None


def source_factor_for(model_units, default=1.0):
    """Metres per unit for a model's units text ('Feet' -> 0.3048); default when the
    text names no length unit."""
    try:
        return float(units.to_meters(1.0, model_units))
    except (ValueError, TypeError):
        return default


def to_si(kind, value, factor):
    """A length / area / volume stored in a model whose unit is `factor` metres long,
    as metres / square metres / cubic metres. Other kinds pass through."""
    power = _QUANTITY_POWER.get(kind)
    if power is None or value is None or factor == 1.0:
        return value
    return float(value) * factor ** power


def display_text(kind, value, ctx=None):
    """The text a value shows as (and is grouped by): NO_VALUE for None or blank text,
    Yes/No, integers without separators (ids), floats trimmed, quantities converted to
    the context units with their symbol (feet and inches in imperial documents), dates
    as ISO, points as 'x, y, z'."""
    ctx = ctx or context_for('Meters')
    if value is None or kind == 'none':
        return NO_VALUE
    if kind == 'bool' or isinstance(value, bool):
        return 'Yes' if value else 'No'
    if kind in QUANTITY_KINDS:
        try:
            number, unit = quantity_value(kind, float(value), ctx)
        except (TypeError, ValueError):
            return str(value)
        if kind == 'angle':
            return _number(number, 2) + u'°'
        if kind == 'length' and unit == 'ft' and ctx.get('imperial'):
            return units.format_feet_inches(number)
        decimals = _LENGTH_DECIMALS.get(unit, 2) if kind == 'length' else (2 if kind == 'area' else 3)
        return '%s %s' % (_number(number, decimals), units.symbol(unit))
    if kind == 'int' or (isinstance(value, int) and not isinstance(value, bool)):
        return str(int(value))
    if kind == 'float' or isinstance(value, float):
        text = ('%.6f' % float(value)).rstrip('0').rstrip('.')
        return '0' if text in ('', '-0') else text
    if kind == 'date':
        return date_text(value)
    if kind == 'point' or isinstance(value, (tuple, list)):
        try:
            return ', '.join(_number(v, 3).replace(',', '') for v in value)
        except (TypeError, ValueError):
            return str(value)
    text = str(value)
    return text.strip() if text.strip() else NO_VALUE


def date_text(value):
    """'2026-10-05' or '2026-10-05 14:30' (time only when it is not midnight)."""
    try:
        if value.hour or value.minute or value.second:
            return '%04d-%02d-%02d %02d:%02d' % (value.year, value.month, value.day,
                                                 value.hour, value.minute)
        return '%04d-%02d-%02d' % (value.year, value.month, value.day)
    except AttributeError:
        return str(value)


def plain_value(kind, value, ctx=None):
    """The value rules and writers compare against: quantities as floats in the
    context units, dates as ISO text, points as text, everything else unchanged."""
    ctx = ctx or context_for('Meters')
    if value is None:
        return None
    if kind in QUANTITY_KINDS:
        try:
            return quantity_value(kind, float(value), ctx)[0]
        except (TypeError, ValueError):
            return value
    if kind == 'date':
        return date_text(value)
    if kind == 'point':
        return display_text(kind, value, ctx)
    return value


class PropIndex(object):
    """category -> property -> value -> count over a set of items.

    add(rows) takes one item's readings [(category, property, kind, vtype, text)];
    counts are per item (a property listed twice on one item counts once). Every
    query returns sorted lists, never dict order."""

    def __init__(self, max_values=MAX_VALUES):
        self.max_values = int(max_values)
        self.total = 0
        self.cats = {}

    def add(self, rows):
        self.total += 1
        seen_cats = set()
        seen_props = set()
        for category, prop, kind, vtype, text in rows:
            entry = self.cats.get(category)
            if entry is None:
                entry = {'items': 0, 'props': {}}
                self.cats[category] = entry
            if category not in seen_cats:
                seen_cats.add(category)
                entry['items'] += 1
            pair = (category, prop)
            if pair in seen_props:
                continue
            seen_props.add(pair)
            stats = entry['props'].get(prop)
            if stats is None:
                stats = {'items': 0, 'values': {}, 'kind': None, 'vtype': None,
                         'capped': False, 'other': 0}
                entry['props'][prop] = stats
            stats['items'] += 1
            if kind != 'none':
                if stats['kind'] is None:
                    stats['kind'] = kind
                    stats['vtype'] = vtype
                elif stats['kind'] != kind:
                    stats['kind'] = 'mixed'
            values = stats['values']
            if text in values:
                values[text] += 1
            elif len(values) < self.max_values:
                values[text] = 1
            else:
                stats['capped'] = True
                stats['other'] += 1

    def categories(self):
        """[(category, items, property count)] in natural order."""
        rows = [(cat, entry['items'], len(entry['props'])) for cat, entry in self.cats.items()]
        rows.sort(key=lambda r: (naming.natural_key(r[0]), r[0]))
        return rows

    def properties(self, category):
        """[(property, items, distinct values, kind, capped)] in natural order."""
        entry = self.cats.get(category)
        if entry is None:
            return []
        rows = []
        for prop, stats in entry['props'].items():
            rows.append((prop, stats['items'], len(stats['values']), stats['kind'] or 'none',
                         stats['capped']))
        rows.sort(key=lambda r: (naming.natural_key(r[0]), r[0]))
        return rows

    def stats(self, category, prop):
        entry = self.cats.get(category)
        if entry is None:
            return None
        return entry['props'].get(prop)

    def kind_of(self, category, prop):
        stats = self.stats(category, prop)
        return (stats or {}).get('kind') or 'none'

    def vtype_of(self, category, prop):
        stats = self.stats(category, prop)
        return (stats or {}).get('vtype')

    def values(self, category, prop, include_missing=True):
        """[(value text, count)] most common first, ties in natural order; then
        '(other values)' when capped and MISSING for items without the property."""
        stats = self.stats(category, prop)
        if stats is None:
            return [(MISSING, self.total)] if include_missing and self.total else []
        rows = sort_counts(stats['values'].items())
        if stats['capped'] and stats['other']:
            rows.append(('(other values)', stats['other']))
        missing = self.total - stats['items']
        if include_missing and missing > 0:
            rows.append((MISSING, missing))
        return rows

    def pairs(self):
        """[(category, property)] in natural order: every property seen."""
        out = []
        for cat, _items, _n in self.categories():
            for prop, _i, _d, _k, _c in self.properties(cat):
                out.append((cat, prop))
        return out

    def rows(self):
        """Flat rows for export: [category, property, value, count, share of items]."""
        out = []
        for cat, _items, _n in self.categories():
            for prop, _i, _d, _k, _c in self.properties(cat):
                for text, count in self.values(cat, prop):
                    share = float(count) / self.total if self.total else 0.0
                    out.append([cat, prop, text, count, share])
        return out


def sort_counts(pairs):
    """[(text, count)] most common first, ties in natural text order (stable on every
    engine)."""
    rows = list(pairs)
    rows.sort(key=lambda p: (-p[1], naming.natural_key(p[0]), p[0]))
    return rows


def share_text(count, total, decimals=1):
    """'12.5%' of total ('0%' when total is 0)."""
    if not total:
        return '0%'
    return _trim_number(('%.' + str(decimals) + 'f') % (100.0 * count / total)) + '%'


def pivot(readings):
    """Counts for Count by Property. readings: [(text1,)] or [(text1, text2)] per item.
    Returns {'total', 'levels' (1 or 2), 'groups': [{'key': (v1,) or (v1, v2),
    'count', 'indices': [reading indexes]}]} ordered by count (two levels: by the
    first value's total, then count)."""
    total = len(readings)
    levels = 2 if readings and len(readings[0]) > 1 else 1
    groups = {}
    for index, reading in enumerate(readings):
        key = tuple(reading[:levels])
        entry = groups.get(key)
        if entry is None:
            entry = {'key': key, 'count': 0, 'indices': []}
            groups[key] = entry
        entry['count'] += 1
        entry['indices'].append(index)
    entries = list(groups.values())
    if levels == 1:
        entries.sort(key=lambda e: (-e['count'], naming.natural_key(e['key'][0]), e['key'][0]))
    else:
        firsts = {}
        for e in entries:
            firsts[e['key'][0]] = firsts.get(e['key'][0], 0) + e['count']
        entries.sort(key=lambda e: (-firsts[e['key'][0]], naming.natural_key(e['key'][0]),
                                    e['key'][0], -e['count'], naming.natural_key(e['key'][1]),
                                    e['key'][1]))
    return {'total': total, 'levels': levels, 'groups': entries}


def first_totals(groups):
    """[(value1, total)] for a two-level pivot, in the order the groups come."""
    out = []
    seen = {}
    for e in groups:
        first = e['key'][0]
        if first not in seen:
            seen[first] = len(out)
            out.append([first, 0])
        out[seen[first]][1] += e['count']
    return [tuple(pair) for pair in out]


def tsv(rows, headers=None):
    """Tab-separated text for the clipboard: tabs and line breaks inside cells become
    spaces so Excel pastes one cell per value."""
    def clean(value):
        text = '' if value is None else str(value)
        return text.replace('\t', ' ').replace('\r\n', ' ').replace('\n', ' ').replace('\r', ' ')
    lines = []
    if headers:
        lines.append('\t'.join(clean(h) for h in headers))
    for row in rows:
        lines.append('\t'.join(clean(c) for c in row))
    return '\r\n'.join(lines)


# =============================================================================
# API half
# =============================================================================

_HOLDER = 'propindex'


def kind_table():
    """{int(VariantDataType member): (kind, member name)} for the live API."""
    from pynavis._api import Api
    enum = Api.VariantDataType
    table = {}
    for name, kind in TYPE_KINDS:
        member = getattr(enum, name, None)
        if member is not None:
            try:
                table[int(member)] = (kind, name)
            except Exception:
                pass
    return table


def coerce(variant, table):
    """(kind, vtype, value) for one VariantData: one DataType read and one To* call."""
    if variant is None:
        return ('none', 'None', None)
    try:
        entry = table.get(int(variant.DataType))
    except Exception:
        entry = None
    if entry is None:
        try:
            return ('text', None, variant.ToString())
        except Exception:
            return ('none', None, None)
    kind, name = entry
    try:
        if name == 'DisplayString':
            return (kind, name, variant.ToDisplayString())
        if kind in ('float',) + QUANTITY_KINDS:
            return (kind, name, float(variant.ToAnyDouble()))
        if name == 'Int32':
            return (kind, name, int(variant.ToInt32()))
        if name == 'Boolean':
            return (kind, name, bool(variant.ToBoolean()))
        if name == 'IdentifierString':
            return (kind, name, variant.ToIdentifierString())
        if name == 'NamedConstant':
            constant = variant.ToNamedConstant()
            return (kind, name, constant.DisplayName or constant.Name)
        if name == 'Int64':
            return (kind, name, int(variant.ToInt64()))
        if name == 'Nat32':
            return (kind, name, int(variant.ToNat32()))
        if name == 'Nat64':
            return (kind, name, int(variant.ToNat64()))
        if name == 'DateTime':
            from namo import dates
            return (kind, name, dates.from_net(variant.ToDateTime()))
        if name == 'Point3D':
            p = variant.ToPoint3D()
            return (kind, name, (p.X, p.Y, p.Z))
        if name == 'Point2D':
            p = variant.ToPoint2D()
            return (kind, name, (p.X, p.Y))
    except Exception:
        try:
            return ('text', name, variant.ToString())
        except Exception:
            return ('none', name, None)
    return ('none', name, None)


class Reader(object):
    """Reads properties with one kind table and display context (build once per run)."""

    def __init__(self, doc=None, report_units=None):
        self.table = kind_table()
        doc_units = 'Meters'
        try:
            d = _doc(doc)
            doc_units = str(d.Units)
        except Exception:
            pass
        if report_units is None:
            try:
                from namo import config
                report_units = config.get('report_units') or 'auto'
            except Exception:
                report_units = 'auto'
        self.ctx = context_for(doc_units, report_units)
        self.doc = doc
        self._doc_factor = source_factor_for(doc_units, 1.0)
        self._factors = {}

    def source_factor(self, item):
        """Metres per unit of the item's source model (cached per model); the
        document's own units when the model cannot be read; 1.0 in 'si' mode."""
        if QUANTITY_SOURCE != 'model':
            return 1.0
        try:
            models = _doc(self.doc).Models
            index = int(models.CreatePathId(item).ModelIndex)
        except Exception:
            return self._doc_factor
        factor = self._factors.get(index)
        if factor is None:
            try:
                factor = source_factor_for(str(models[index].Units), self._doc_factor)
            except Exception:
                factor = self._doc_factor
            self._factors[index] = factor
        return factor

    def si(self, item, kind, value, factor=None):
        """A length / area / volume as read from item, in SI (see QUANTITY_SOURCE)."""
        if value is None or kind not in _QUANTITY_POWER:
            return value
        if factor is None:
            factor = self.source_factor(item)
        return to_si(kind, value, factor)

    def all(self, item):
        """[(category, property, kind, vtype, display text)] for every property."""
        out = []
        table = self.table
        ctx = self.ctx
        try:
            categories = item.PropertyCategories
        except Exception:
            return out
        factor = None
        for cat in categories:
            cname = cat.DisplayName
            for prop in cat.Properties:
                kind, vtype, value = coerce(prop.Value, table)
                if kind in _QUANTITY_POWER and value is not None:
                    if factor is None:
                        factor = self.source_factor(item)     # one model lookup per item
                    value = to_si(kind, value, factor)
                out.append((cname, prop.DisplayName, kind, vtype, display_text(kind, value, ctx)))
        return out

    def one(self, item, category, prop):
        """(exists, kind, value) for one property by display names; category '' means
        the first category that carries a property with that name."""
        if category:
            try:
                found = item.PropertyCategories.FindPropertyByDisplayName(category, prop)
            except Exception:
                found = None
            if found is None:
                return (False, 'none', None)
            kind, _vtype, value = coerce(found.Value, self.table)
            return (True, kind, self.si(item, kind, value))
        try:
            for cat in item.PropertyCategories:
                for candidate in cat.Properties:
                    if candidate.DisplayName == prop:
                        kind, _vtype, value = coerce(candidate.Value, self.table)
                        return (True, kind, self.si(item, kind, value))
        except Exception:
            pass
        return (False, 'none', None)

    def text(self, item, category, prop):
        """The display text of one property, or MISSING."""
        exists, kind, value = self.one(item, category, prop)
        if not exists:
            return MISSING
        return display_text(kind, value, self.ctx)

    def getter(self, item, fallback_to_object=False):
        """getter(category, property) -> (exists, plain value) for namo.rules."""
        def get(category, prop):
            exists, kind, value = self.one(item, category, prop)
            if not exists and fallback_to_object:
                from namo import items as _items
                element = _items.object_of(item)
                if element is not item and not element.Equals(item):
                    exists, kind, value = self.one(element, category, prop)
            return (exists, plain_value(kind, value, self.ctx) if exists else None)
        return get


def _doc(doc):
    if doc is not None:
        return doc
    from pynavis._api import Application
    return Application.ActiveDocument


def _visible_filter():
    """A memoised 'neither the item nor an ancestor is hidden' test."""
    memo = {}

    def visible(item):
        chain = []
        node = item
        result = True
        while node is not None:
            known = memo.get(node)
            if known is not None:
                result = known
                break
            chain.append(node)
            if node.IsHidden:
                result = False
                break
            node = node.Parent
        for visited in chain:
            memo[visited] = result
        return result
    return visible


def scope_items(scope, level='objects', doc=None, tick=None, budget=None):
    """The items a tool works on: scope 'selection' | 'visible' | 'model', level
    'objects' (element-level, namo.items.objects) | 'geometry'. Returns a namo.items
    ItemList (`.sampled` when the budget cut it). tick(done, total) as namo.items."""
    from namo import items
    document = _doc(doc)
    if scope == 'selection':
        roots = items.selected(document)
    else:
        roots = items.roots(document)
    if not roots:
        return items.ItemList()
    if scope != 'visible':
        if level == 'geometry':
            return items.geometry_items(roots, tick=tick, budget=budget)
        return items.objects(roots, tick=tick, budget=budget)
    visible = _visible_filter()
    ticker = items.Ticker(tick)
    out = items.ItemList()
    seen = set()
    for root in roots:
        for item in root.DescendantsAndSelf:
            ticker.step()
            if not item.HasGeometry or not visible(item):
                continue
            target = item if level == 'geometry' else items.object_of(item)
            if target in seen:
                continue
            seen.add(target)
            out.append(target)
            if budget is not None and len(out) >= budget:
                out.sampled = True
                ticker.finish()
                return out
    ticker.finish()
    return out


def scan(item_list, doc=None, tick=None, max_values=MAX_VALUES, reader=None):
    """A PropIndex over item_list. tick(done, total) every TICK_EVERY items; returning
    False raises namo.items.Cancelled."""
    from namo import items
    reader = reader or Reader(doc)
    index = PropIndex(max_values)
    data = list(item_list)
    ticker = items.Ticker(tick, total=len(data), every=TICK_EVERY)
    for item in data:
        index.add(reader.all(item))
        ticker.step()
    ticker.finish()
    return index


def find_matching(item_list, category, prop, text, doc=None, tick=None, reader=None):
    """Items of item_list whose property shows as `text` (MISSING finds items without
    it). The same reading and formatting the index used, so a value picked in a list
    always finds its items."""
    from namo import items
    reader = reader or Reader(doc)
    data = list(item_list)
    ticker = items.Ticker(tick, total=len(data), every=TICK_EVERY)
    out = []
    for item in data:
        if reader.text(item, category, prop) == text:
            out.append(item)
        ticker.step()
    ticker.finish()
    return out


def read_pairs(item_list, specs, doc=None, tick=None, reader=None, fallback_to_object=False):
    """[(text, ...)] per item for specs [(category, property)], MISSING when absent
    (Count by Property)."""
    from namo import items
    reader = reader or Reader(doc)
    data = list(item_list)
    ticker = items.Ticker(tick, total=len(data), every=TICK_EVERY)
    out = []
    for item in data:
        texts = []
        for category, prop in specs:
            text = reader.text(item, category, prop)
            if text == MISSING and fallback_to_object:
                element = items.object_of(item)
                if element is not item and not element.Equals(item):
                    text = reader.text(element, category, prop)
            texts.append(text)
        out.append(tuple(texts))
        ticker.step()
    ticker.finish()
    return out


# ---- session cache -----------------------------------------------------------------


def doc_signature(doc=None):
    """What identifies a document for the cache: file, title and its model files."""
    document = _doc(doc)
    try:
        models = document.Models
        files = tuple(str(models[i].SourceFileName or models[i].FileName or '')
                      for i in range(models.Count))
    except Exception:
        files = ()
    return (str(getattr(document, 'FileName', '') or ''), str(getattr(document, 'Title', '') or ''),
            files)


def selection_signature(doc=None):
    """(count, first key, last key) of the current selection: cheap and good enough
    to notice that the selection changed."""
    from namo import items
    document = _doc(doc)
    try:
        selected = items.selected(document)
    except Exception:
        return (0, '', '')
    if not selected:
        return (0, '', '')
    try:
        return (len(selected), items.key(selected[0], document), items.key(selected[-1], document))
    except Exception:
        return (len(selected), '', '')


def generation():
    """Bumped whenever Playground writes properties (invalidates cached scans)."""
    from namo import session
    return session.get(_HOLDER, 'generation', 0)


def invalidate():
    """Forget cached scans (call after writing properties)."""
    from namo import session
    session.set(_HOLDER, 'generation', generation() + 1)
    session.set(_HOLDER, 'last', None)


def remember(index, item_list, scope, level, budget, doc=None):
    """Caches a scan for the document (one entry: the last scan)."""
    from namo import session
    entry = {'index': index, 'items': item_list, 'scope': scope, 'level': level,
             'budget': budget, 'time': time.time(), 'doc': doc_signature(doc),
             'selection': selection_signature(doc) if scope == 'selection' else None,
             'generation': generation(), 'sampled': bool(getattr(item_list, 'sampled', False))}
    session.set(_HOLDER, 'last', entry)
    return entry


def cached(doc=None, scope=None, level=None):
    """The cached scan for the active document (optionally only for that scope and
    level), or None when there is none or it no longer applies."""
    from namo import session
    entry = session.get(_HOLDER, 'last')
    if not entry:
        return None
    if entry.get('generation') != generation():
        return None
    try:
        if entry.get('doc') != doc_signature(doc):
            return None
        if scope is not None and entry.get('scope') != scope:
            return None
        if level is not None and entry.get('level') != level:
            return None
        if entry.get('scope') == 'selection' and entry.get('selection') != selection_signature(doc):
            return None
    except Exception:
        return None
    return entry


def property_choices(doc=None, scope='model', limit=300):
    """[(category, property, items)] to offer in a property picker: the cached scan
    when there is one, else the property names on the first `limit` objects of the
    scope (namo.items.sample_properties: names only, quick)."""
    from namo import items
    entry = cached(doc)
    if entry is not None:
        index = entry['index']
        out = []
        for cat, _i, _n in index.categories():
            for prop, count, _d, _k, _c in index.properties(cat):
                out.append((cat, prop, count))
        return out
    sample = scope_items(scope, 'objects', doc=doc, budget=limit)
    if not sample and scope == 'selection':
        sample = scope_items('model', 'objects', doc=doc, budget=limit)
    return items.sample_properties(sample, limit=limit)


# ---- finding items by a value -------------------------------------------------------


def native_value(vtype, text):
    """The value a native search can match exactly for a shown text, or None when
    the property type (or the text) cannot be searched natively: DisplayString text,
    Int32 numbers, Boolean Yes/No."""
    if text in (MISSING, NO_VALUE, '(other values)') or text is None:
        return None
    if vtype == 'DisplayString':
        return text
    if vtype == 'Int32':
        try:
            return int(text)
        except ValueError:
            return None
    if vtype == 'Boolean':
        if text in ('Yes', 'No'):
            return text == 'Yes'
    return None


def search_builder(category, prop, vtype, text):
    """A pynavis.sets Builder matching items whose property equals the shown text, or
    None (see native_value). MISSING builds a 'property missing' search."""
    from pynavis import sets
    if text == MISSING:
        return sets.query().prop(category, prop).missing()
    value = native_value(vtype, text)
    if value is None:
        return None
    return sets.query().prop(category, prop).equals(value)


def find_in_model(category, prop, text, vtype=None, doc=None, tick=None, reader=None,
                  budget=DEFAULT_BUDGET):
    """(items, how) for every item in the model whose property shows as text.

    Native first (pynavis.sets, exact for DisplayString / Int32 / Boolean), every hit
    then confirmed in Python with the same reading the tools show; when the type
    cannot be searched natively (lengths, doubles, dates...) or the search finds
    nothing, the model's objects are read in Python instead (budgeted, so the answer
    may be 'sampled'). how: 'search' | 'scan' | 'scan-sampled'."""
    reader = reader or Reader(doc)
    builder = None
    if text != MISSING:
        try:
            builder = search_builder(category, prop, vtype, text)
        except Exception:
            builder = None
    if builder is not None:
        from pynavis import sets
        try:
            found = list(sets.run(builder, doc=doc))
        except Exception:
            found = []
        confirmed = [item for item in found if reader.text(item, category, prop) == text]
        if confirmed:
            return confirmed, 'search'
    item_list = scope_items('model', 'objects', doc=doc, tick=tick, budget=budget)
    matched = [item for item in item_list if reader.text(item, category, prop) == text]
    if not matched:
        geometry = scope_items('model', 'geometry', doc=doc, tick=tick, budget=budget)
        matched = [item for item in geometry if reader.text(item, category, prop) == text]
        return matched, 'scan-sampled' if geometry.sampled else 'scan'
    return matched, 'scan-sampled' if item_list.sampled else 'scan'
