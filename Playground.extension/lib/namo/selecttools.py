# -*- coding: utf-8 -*-
"""Select panel logic: Select Similar, Filter Selection, Invert, Select by File, Save as Set.

Each tool has a pure planner here (plain dicts and lists, unit tested on both engines)
and a thin API half that lazy-imports pynavis. The bundle scripts gather input, call
these, and toast.

Select Similar
  similar_rows(prop_rows)        the reference element's properties as choosable rows,
                                 identity ones (GUIDs, ids, unique names) flagged
  similar_query(rows)            AND query of "same value" conditions (find_query rules)
  run_similar(element, rows, scope)
                                 preflight (each condition must match the element itself,
                                 natively) then one native search, pruned below matches

Filter Selection
  filter_indices(readings, cond, keep)   pure decision per item (namo.rules semantics)

Invert
  visible_frontier(nodes, ...)   pure: refine an inverted selection so hidden branches
                                 are left out without walking the whole model
  invert(doc, include_hidden)    ModelItemCollection.Invert + the hidden refinement

Select by File / Save as Set: model rows, name templates.
"""

import os
import re

from namo import find_query

# ---- Select Similar -------------------------------------------------------------------

SCOPES = [('model', 'Whole model'), ('same_model', 'Same model as the item'),
          ('selection', 'Current selection')]
SCOPE_LABELS = dict(SCOPES)
SCOPE_OPTIONS = [(label, value) for value, label in SCOPES]     # ui radio order: (label, value)

SIMILAR_DEFAULTS = {'checked': [], 'scope': 'model', 'show_identity': False}

# Default ticks when nothing was remembered: what "similar" usually means.
DEFAULT_KEYS = ['Element > Category', 'Element > Family', 'Element > Type',
                'Element > Family and Type']

_GUID_RE = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', re.I)
_IFC_RE = re.compile(r'^[0-3][0-9A-Za-z_$]{21}$')
_LONG_NUMBER_RE = re.compile(r'\d{5,}')
_BRACKET_ID_RE = re.compile(r'\[\d+\]')

# Property names (lower case) that identify one element rather than describe it.
_IDENTITY_NAMES = set([
    'guid', 'instance guid', 'uniqueid', 'unique id', 'globalid', 'global id', 'ifcguid',
    'ifc guid', 'ifcglobalid', 'id', 'element id', 'elementid', 'handle', 'mark',
    'tag', 'object id', 'objectid', 'entity handle', 'source id', 'item id',
    'unique identifier', 'export guid', 'internal id',
])
# Item state flags: they describe the view, not the element.
_VOLATILE = set([('item', 'hidden'), ('item', 'required'), ('item', 'frozen')])


def row_key(category, prop):
    """'Category > Property', the name a remembered choice is stored under."""
    return '%s > %s' % (category, prop)


def looks_unique(text):
    """True for values that name one thing: GUIDs, IFC GlobalIds, long digit runs,
    '[123456]' style ids."""
    text = str(text or '').strip()
    if not text:
        return False
    if _GUID_RE.search(text) or _IFC_RE.match(text):
        return True
    return bool(_LONG_NUMBER_RE.search(text) or _BRACKET_ID_RE.search(text))


def is_identity(category, prop, text):
    """True when a property identifies an element (or describes view state) rather than
    what kind of thing it is: matching on it finds the element itself, never 'similar'
    ones. Item > Name counts only when it reads like a unique name."""
    cat = str(category or '').strip().lower()
    name = str(prop or '').strip().lower()
    if (cat, name) in _VOLATILE:
        return True
    if cat == 'element id':
        return True
    if name in _IDENTITY_NAMES or name.endswith(' guid') or name.endswith(' uniqueid'):
        return True
    if cat == 'item' and name == 'name':
        return looks_unique(text)
    if _GUID_RE.search(str(text or '')) or _IFC_RE.match(str(text or '').strip()):
        return True
    return False


def similar_rows(prop_rows):
    """Choosable rows from pynavis.props.all_of(element): [{'key', 'category',
    'property', 'value', 'text', 'kind', 'identity'}] in the element's own order.
    Values a native search cannot compare (dates, points) and blank values are left
    out; a repeated Category > Property keeps its first value."""
    out = []
    seen = set()
    for row in prop_rows:
        category = row.get('category', '')
        prop = row.get('property', '')
        value = row.get('value')
        kind = find_query.kind_of(value)
        if kind is None:
            continue
        text = find_query.value_text(value)
        if text == find_query.NO_VALUE:
            continue
        key = row_key(category, prop)
        if key in seen:
            continue
        seen.add(key)
        out.append({'key': key, 'category': category, 'property': prop, 'value': value,
                    'text': text, 'kind': kind, 'identity': is_identity(category, prop, text)})
    return out


def default_checked(rows, remembered):
    """Keys to tick when the window opens: the remembered property names that this
    element has; else the usual Category/Family/Type; never identity rows."""
    available = dict((r['key'], r) for r in rows)
    picked = [k for k in (remembered or []) if k in available]
    if picked:
        return picked
    return [k for k in DEFAULT_KEYS if k in available and not available[k]['identity']]


def similar_conditions(row):
    """pynavis conditions for 'same value as the reference' on one row."""
    return find_query.conditions(row['category'], row['property'], 'equals', row['value'],
                                 kind=row['kind'], ignore_case=(row['kind'] == 'text'))


def similar_query(rows):
    """The AND query dict for the chosen rows (None when nothing is chosen)."""
    group = []
    for row in rows:
        group.extend(similar_conditions(row))
    if not group:
        return None
    return find_query.query_dict([group])


def similar_summary(count, rows, scope, dropped=()):
    """(level, message, detail) for the toast."""
    if dropped and not rows:
        return ('warning', 'These properties cannot be searched',
                'A Navisworks search does not find the item itself by %s. Choose other properties.'
                % ', '.join(r['key'] for r in dropped))
    texts = [find_query.describe(r['category'], r['property'], 'equals', r['text']) for r in rows]
    detail = find_query.join_descriptions(texts)
    if scope != 'model':
        detail = '%s. Scope: %s' % (detail, SCOPE_LABELS.get(scope, scope).lower())
    if dropped:
        detail = '%s. Left out (no native match): %s' % (
            detail, ', '.join(r['key'] for r in dropped))
    if not count:
        return ('info', 'No similar items found', detail)
    noun = 'item' if count == 1 else 'items'
    level = 'warning' if dropped else 'success'
    return (level, 'Selected %s similar %s' % ('{:,}'.format(count), noun), detail)


def scope_items(scope, element, doc=None):
    """What a Select Similar search walks: None (whole model), [the element's model
    root] or the current selection."""
    from namo import items
    if scope == 'same_model':
        model = items.model_of(element)
        return [model.RootItem] if model is not None else None
    if scope == 'selection':
        # The elements of the selected items: a selection of geometry parts would
        # otherwise hide the element-level properties being matched.
        return items.dedupe([items.object_of(item) for item in items.selected(doc)])
    return None


def _matches_itself(query, element, document):
    """True when the native search finds the element itself (scoped to its own branch,
    so it costs next to nothing)."""
    from pynavis import sets
    try:
        found = sets.run(query, document, scope=[element])
    except Exception:
        return False
    try:
        return bool(found.Contains(element))
    except Exception:
        return any(item.Equals(element) for item in found)


def run_similar(element, rows, scope='model', doc=None):
    """(ModelItemCollection of matches, dropped rows).

    Preflight: the AND query must find the reference element itself. When it does not,
    each row is tested alone and the rows the element fails natively (a property stored
    in a way the typed value cannot equal) are dropped and reported, instead of the
    search silently finding nothing. Then ONE native search over the scope, pruned below
    matches so an element's own sub-parts are not counted twice."""
    from pynavis import sets
    from namo import items
    document = items._doc(doc)
    query = similar_query(rows)
    if query is None:
        return items.collection([]), []
    if _matches_itself(query, element, document):
        kept, dropped = list(rows), []
    else:
        kept, dropped = [], []
        for row in rows:
            (kept if _matches_itself(similar_query([row]), element, document) else dropped).append(row)
        query = similar_query(kept)
        if query is None:
            return items.collection([]), dropped
    found = sets.run(query, document, prune=True, scope=scope_items(scope, element, document))
    return found, dropped


def merge_property_counts(*lists):
    """[(category, property, count)] merged from several sample_properties() results
    (the larger count wins), sorted like namo.items.sample_properties."""
    counts = {}
    for rows in lists:
        for category, prop, count in rows:
            key = (category, prop)
            counts[key] = max(counts.get(key, 0), count)
    out = [(k[0], k[1], n) for k, n in counts.items()]
    out.sort(key=lambda r: (r[0].lower(), r[1].lower(), r[0], r[1]))
    return out


def property_rows(selected, limit=200):
    """Properties carried by the first `limit` selected items or their elements, for a
    property picker: [(category, property, count)]."""
    from namo import items
    sample = list(selected[:limit])
    elements = items.dedupe([items.object_of(item) for item in sample])
    return merge_property_counts(items.sample_properties(sample, limit),
                                 items.sample_properties(elements, limit))


def visible_similar_rows(rows, show_identity):
    """The rows the table shows: identity rows only when asked for."""
    return [r for r in rows if show_identity or not r['identity']]


def table_rows(rows, checked):
    """namo.ui Table rows (value = key) with ticks."""
    wanted = set(checked or [])
    return [{'value': r['key'], 'cells': [r['category'], r['property'], r['text']],
             'checked': r['key'] in wanted} for r in rows]


class SimilarState(object):
    """window.Tag of the Select Similar window: result {'keys', 'scope', 'show_identity'}
    and accepted once Select was pressed."""

    def __init__(self, win, table, rows, scope_buttons, identity_check):
        self.window = win
        self.table = table
        self.rows = rows
        self.scope_buttons = scope_buttons
        self.identity_check = identity_check
        self.result = None
        self.accepted = False

    def scope(self):
        from namo import ui
        return ui.radio_value(self.scope_buttons, SCOPE_OPTIONS) or 'model'

    def show_identity(self):
        return bool(self.identity_check.IsChecked)

    def refilter(self):
        ticked = self.table.checked_values()
        shown = visible_similar_rows(self.rows, self.show_identity())
        self.table.update(table_rows(shown, ticked))

    def accept(self):
        keys = self.table.checked_values()
        if not keys:
            return False
        self.result = {'keys': keys, 'scope': self.scope(), 'show_identity': self.show_identity()}
        self.accepted = True
        try:
            self.window.DialogResult = True
        except Exception:
            self.window.Close()
        return True


def build_similar_window(rows, checked, scope='model', show_identity=False, element_name=''):
    """The Select Similar picker, unshown (window.Tag is a SimilarState): a filterable
    tick list of the element's properties, a 'Show identity properties' switch and the
    search scope."""
    from namo import ui
    ui._wpf()
    from System.Windows import GridLength, GridUnitType, VerticalAlignment
    from System.Windows.Controls import Dock, DockPanel, Grid, RowDefinition, StackPanel, Orientation
    from System.Windows.Input import Key, Keyboard, ModifierKeys
    logger = ui.pinned_logger()
    win = ui.window('Select Similar', width=720, height=600, resizable=True, min_width=480,
                    min_height=400)
    by_key = dict((r['key'], r) for r in rows)
    if any(by_key[k]['identity'] for k in (checked or []) if k in by_key):
        show_identity = True
    holder = {}

    def changed():
        if 'refresh' in holder:
            holder['refresh']()

    table = ui.Table(['Category', 'Property', 'Value'],
                     table_rows(visible_similar_rows(rows, show_identity), checked),
                     checkboxes=True, multiselect=True, on_change=changed, logger=logger)
    identity = ui.check('Show identity properties', show_identity)
    scope_panel, scope_buttons = ui.radio_group(SCOPE_OPTIONS, scope if scope in SCOPE_LABELS else 'model',
                                                inline=True, group='namo_similar_scope')
    state = SimilarState(win, table, rows, scope_buttons, identity)
    win.Tag = state

    root = Grid()
    root.Margin = ui._thickness(16, 16, 16, 12)
    for size in ('auto', 'auto', 'star', 'auto'):
        definition = RowDefinition()
        definition.Height = GridLength(1, GridUnitType.Star) if size == 'star' else GridLength.Auto
        root.RowDefinitions.Add(definition)
    lead = ui.text('Tick the properties a match must share with %s. Text compares without case; '
                   'numbers compare as numbers.' % (element_name or 'the first selected item'))
    lead.Margin = ui._thickness(0, 0, 0, 12)
    Grid.SetRow(lead, 0)
    root.Children.Add(lead)

    bar = DockPanel()
    bar.Margin = ui._thickness(0, 0, 0, 8)
    identity.Margin = ui._thickness(12, 0, 0, 0)
    identity.VerticalAlignment = VerticalAlignment.Center
    DockPanel.SetDock(identity, Dock.Right)
    bar.Children.Add(identity)
    search, search_input = ui.search_box('Filter properties', lambda q: table.set_filter(q))
    bar.Children.Add(search)
    Grid.SetRow(bar, 1)
    root.Children.Add(bar)
    Grid.SetRow(table.element, 2)
    root.Children.Add(table.element)

    scope_row = StackPanel()
    scope_row.Orientation = Orientation.Horizontal
    scope_row.Margin = ui._thickness(0, 12, 0, 0)
    label = ui.text('Search in', bold=True, wrap=False)
    label.Margin = ui._thickness(0, 0, 16, 0)
    label.VerticalAlignment = VerticalAlignment.Top
    scope_row.Children.Add(label)
    scope_row.Children.Add(scope_panel)
    Grid.SetRow(scope_row, 3)
    root.Children.Add(scope_row)

    counter = ui.hint('')
    ok = ui.button('Select', lambda: state.accept(), 'primary', logger)
    ok.IsDefault = True
    cancel = ui.button('Cancel', lambda: ui._close_with(win, False), 'secondary', logger)
    cancel.IsCancel = True
    bottom = ui.footer([ok, cancel], left=counter, padding=16)

    def refresh():
        ticked = len(table.checked_values())
        counter.Text = ui.count_text(ticked, table.total(), table.visible_count(), 'ticked')
        ok.IsEnabled = ticked > 0
    holder['refresh'] = refresh
    identity.Checked += ui.safe(lambda s, e: state.refilter(), 'identity filter', logger)
    identity.Unchecked += ui.safe(lambda s, e: state.refilter(), 'identity filter', logger)

    layout = DockPanel()
    DockPanel.SetDock(bottom, Dock.Bottom)
    layout.Children.Add(bottom)
    layout.Children.Add(root)
    win.Content = layout

    def keys(sender, args):
        if args.Key == Key.F and Keyboard.Modifiers == ModifierKeys.Control:
            search_input.Focus()
            search_input.SelectAll()
            args.Handled = True
        elif args.Key == Key.Down and search_input.IsKeyboardFocused:
            table.focus_first()
            args.Handled = True
    win.PreviewKeyDown += ui.safe(keys, 'similar keys', logger)
    win.ContentRendered += ui.safe(lambda s, e: search_input.Focus(), 'similar focus', logger)
    refresh()
    return win


def similar_dialog(rows, checked, scope='model', show_identity=False, element_name=''):
    """Shows the picker; returns {'keys', 'scope', 'show_identity'} or None (cancelled)."""
    from namo import ui
    win = build_similar_window(rows, checked, scope, show_identity, element_name)
    ui.show_modal(win)
    state = win.Tag
    return state.result if state.accepted else None


# ---- Filter Selection -------------------------------------------------------------------

FILTER_DEFAULTS = {'category': '', 'property': '', 'op': 'equals', 'mode': 'keep',
                   'use_object': True}
FILTER_PROGRESS_OVER = 2000
OTHER = '__other__'


def filter_ops():
    """[(op, label)] from namo.rules, in its order."""
    from namo import rules
    return [(op, label) for op, label, _needs in rules.OPS]


def picked_condition(category, prop, op, chosen, typed, tally):
    """The namo.rules condition for the Filter Selection form's answer.

    chosen is the value picked from the observed list (its text) or OTHER, typed the
    free text. A number or Yes/No picked from the list is matched by how it reads in
    that list ('shown'), not by its text as a number: the list shows 12.333333 for
    every length that rounds to it, and comparing the rounded text with the stored
    12.3333333333 as numbers would keep none of the items the count promised."""
    if chosen == OTHER:
        return {'category': category, 'property': prop, 'op': op, 'value': typed,
                'ignore_case': True}
    cond = {'category': category, 'property': prop, 'op': op, 'value': chosen, 'ignore_case': True}
    raw_of = dict((text, raw) for text, _count, raw in tally)
    if op in ('equals', 'not_equals') and chosen in raw_of and not isinstance(raw_of[chosen], str):
        cond['shown'] = chosen
    return cond


def filter_indices(readings, cond, keep=True):
    """Indices of the items that stay. readings[i] = (exists, value) for item i; cond is
    a namo.rules condition (see picked_condition for 'shown'). keep=True keeps matches,
    False removes them."""
    from namo import rules
    shown = cond.get('shown')
    negate = cond.get('op') == 'not_equals'
    out = []
    for index, (exists, value) in enumerate(readings):
        if shown is not None:
            hit = bool(exists) and (find_query.value_text(value) == shown) != negate
        else:
            hit = rules.evaluate(cond, exists, value)
        if bool(hit) == bool(keep):
            out.append(index)
    return out


def filter_summary(kept, total, keep, cond_text):
    """(level, message, detail) for the toast; kept == 0 leaves the selection alone."""
    if kept == 0:
        return ('info', 'No item would stay selected',
                '%s. The selection is unchanged.' % cond_text)
    if kept == total:
        return ('info', 'Every item stays selected', '%s matched all %s.' % (
            cond_text, '{:,}'.format(total)) if keep else '%s matched none of them.' % cond_text)
    if keep:
        return ('success', 'Kept %s of %s' % ('{:,}'.format(kept), '{:,}'.format(total)),
                'Kept items where %s.' % cond_text)
    return ('success', 'Removed %s of %s' % ('{:,}'.format(total - kept), '{:,}'.format(total)),
            '%s left; removed items where %s.' % ('{:,}'.format(kept), cond_text))


def value_options(tally, limit=60):
    """[(label, value)] for the value choice: observed values with counts, then 'Type a
    value' (OTHER)."""
    options = []
    for text, count, _raw in tally[:limit]:
        if text == find_query.NO_VALUE:
            continue
        options.append(('%s  (%s)' % (text, '{:,}'.format(count)), text))
    options.append(('Type a value', OTHER))
    return options


def run_filter(selected, cond, keep, use_object, report=None):
    """Evaluates every selected item (report(fraction, label) every 200 items when
    given; it raises to cancel). Returns the kept items."""
    total = len(selected)
    readings = []
    category = cond.get('category', '')
    prop = cond.get('property', '')
    for index, item in enumerate(selected):
        readings.append(find_query.read(item, category, prop, use_object))
        if report is not None and index % 200 == 0:
            report(float(index) / max(1, total), 'Testing %s of %s items' % (
                '{:,}'.format(index), '{:,}'.format(total)))
    return [selected[i] for i in filter_indices(readings, cond, keep)]


# ---- Invert -----------------------------------------------------------------------------

INVERT_DEFAULTS = {'include_hidden': False}


def visible_frontier(nodes, hidden, hidden_ancestors, children_of, is_hidden):
    """Refines a node list so nothing hidden is in it, cheaply.

    nodes: the inverted selection (any tree nodes). hidden: set of the TOPMOST hidden
    nodes; hidden_ancestors: every ancestor of those (namo.items.ancestor_closure).
    is_hidden(node): True when the node or an ancestor is hidden. A node is dropped when
    hidden; kept whole when no hidden node is below it; otherwise replaced by its
    children, recursively. Cost: the hidden nodes' ancestors and their children only."""
    out = []
    stack = list(reversed(list(nodes)))
    while stack:
        node = stack.pop()
        if node in hidden or is_hidden(node):
            continue
        if node in hidden_ancestors:
            children = list(children_of(node))
            for child in reversed(children):
                stack.append(child)
            continue
        out.append(node)
    return out


def hidden_query(category_name, prop_name):
    """The query dict finding hidden items by Navisworks' internal names (Item > Hidden
    is a Boolean property every item carries)."""
    return {'or': [{'and': [{'category': category_name, 'prop': prop_name, 'op': 'equals',
                             'value': True, 'by_display': False}]}]}


def _hidden_top(document):
    """The topmost hidden items via one native search (Item > Hidden = true, pruned
    below matches), or None when the search is refused."""
    from pynavis import sets
    from pynavis._api import Api
    try:
        query = hidden_query(Api.PropertyCategoryNames.Item, Api.DataPropertyNames.ItemHidden)
        return list(sets.run(query, document, prune=True))
    except Exception as error:
        from namo import session
        session.log('warning', 'Invert: hidden-item search failed (%s)' % error)
        return None


def invert(doc=None, include_hidden=False):
    """Inverts the current selection. Returns (new_items, note): note is None, or a
    sentence when hidden items could only be partly left out."""
    from namo import items
    document = items._doc(doc)
    selected = items.selected(document)
    if selected:
        inverted = items.collection(selected)
        inverted.Invert(document)
        nodes = list(inverted)
    else:
        nodes = items.roots(document)           # nothing selected: everything
    if include_hidden:
        return nodes, None
    top = _hidden_top(document)
    if top is None:
        kept = [n for n in nodes if items.visible(n)]
        return kept, 'Hidden items inside visible branches may still be selected.'
    hidden = set(top)
    ancestors = items.ancestor_closure(top, lambda node: node.Parent)
    kept = visible_frontier(nodes, hidden, ancestors, lambda node: node.Children,
                            lambda node: not items.visible(node))
    return kept, None


# ---- Select by File ---------------------------------------------------------------------

FILE_DEFAULTS = {'files': [], 'zoom': False}
COUNT_BUDGET = 20000


def source_type(name):
    """'RVT', 'NWC', 'IFC'... from a file name's extension ('' when none)."""
    ext = os.path.splitext(str(name or ''))[1]
    return ext[1:].upper() if ext else ''


def count_text(count, budget=COUNT_BUDGET):
    if count is None:
        return ''
    if count >= budget:
        return '%s+' % '{:,}'.format(budget)
    return '{:,}'.format(count)


def file_rows(models, counts):
    """ui.choose rows for the appended models. models: namo.items.models() dicts;
    counts: {index: item count or None}. The value is the model index."""
    rows = []
    for model in models:
        source = model.get('source') or model.get('file') or model.get('name')
        rows.append({'value': model['index'],
                     'cells': [model['name'], source_type(source) or source_type(model.get('file')),
                               model.get('units') or '', count_text(counts.get(model['index']))]})
    return rows


def checked_files(models, remembered):
    """Model indices whose file name was ticked last time (case-insensitive)."""
    wanted = set(str(n).lower() for n in remembered or [])
    return [m['index'] for m in models if str(m['name']).lower() in wanted]


def count_items(root, budget=COUNT_BUDGET):
    """Items under a model root, counted natively up to budget."""
    count = 0
    for _item in root.DescendantsAndSelf:
        count += 1
        if count >= budget:
            break
    return count


def count_models(roots, budget=COUNT_BUDGET, seconds=1.5, clock=None):
    """{position: count} for model roots, each counted up to budget; once `seconds` have
    passed the rest stay uncounted (None) so the chooser never waits long."""
    import time
    clock = clock or time.time
    started = clock()
    out = {}
    for position, root in enumerate(roots):
        if clock() - started > seconds:
            out[position] = None
            continue
        try:
            out[position] = count_items(root, budget)
        except Exception:
            out[position] = None
    return out


# ---- Save as Set --------------------------------------------------------------------------

SAVE_DEFAULTS = {'template': '{category} - {count} items - {date}', 'folder': 'Playground'}
NAME_TOKENS = ('category', 'count', 'date', 'time', 'user', 'file', 'model')


def most_common(texts, fallback=''):
    """The most frequent non-blank text (ties: natural order), else fallback."""
    from namo import items
    rows = items.tally([t for t in texts if t and str(t).strip()])
    return rows[0][0] if rows else fallback


def set_name(template, values):
    """(name, missing_tokens): the template rendered and tidied; an empty result falls
    back to 'Selection'."""
    from namo import naming
    text, missing = naming.render(template or SAVE_DEFAULTS['template'], values)
    name = naming.sanitize(text)
    return (name or 'Selection'), missing


def name_values(categories, models, count, standard):
    """Token values for a set name: standard (naming.standard_values()) plus category
    (most common), model (most common file) and count (formatted)."""
    values = dict(standard or {})
    values['category'] = most_common(categories, 'Items')
    values['model'] = most_common(models, values.get('file') or 'Model')
    values['count'] = '{:,}'.format(count)
    return values
