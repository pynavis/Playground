# -*- coding: utf-8 -*-
"""Quick Find: type-ahead search over every element of the model.

The first search in a document builds an INDEX: one row per element-level item (the
object a user clicks: FindFirstObjectAncestor of each geometry item) holding its
PathId and the text of a few key fields (name, class, Element ID, category, family,
type, mark, comments, IFC GlobalId and name, system, level; configurable). The index is
kept for the session and written to %APPDATA%\\pyNavis\\playground\\index\\<doc_key>.json, keyed by
the appended files' names, sizes and dates, so the next session opens instantly and a
re-exported model rebuilds it automatically.

File format (measured: JSON lists of 100,000 rows take 3.6 s to parse on IronPython 3.4;
one string field split on separators takes 0.6 s): the rows travel as ONE string, rows
joined by U+E001 and fields by U+E000 (private-use characters no model text contains;
they are scrubbed from values anyway), written with ensure_ascii off so nothing in it
needs a JSON escape.

Searching ranks rows with namo.textmatch (fuzzy, word starts, acronyms) over each row's
combined text, except that a query word made of 3 or more digits is an id and must
appear as written ('312045' never matches '312 ... 0 ... 45'). Typing more characters
only ever narrows the matches, so a query that extends the previous one is ranked over
the previous matches only: after the first couple of characters every keystroke touches
a few hundred rows, not the whole model.

Pure half (fields, signature, encode/decode, QuickIndex, display) first, then the API
half (build, load, resolve) and the window.
"""

import datetime

from namo import textmatch

FORMAT = 'playground-quickfind'
VERSION = 2                     # 2: type ids left out, numeric values without a type prefix
FIELD_SEP = u''
ROW_SEP = u''
JOIN = '  |  '

# Every field the index can hold. 'sources' are tried in order: '@name' is the item's
# display name, '@class' its class name, pairs are (category, property) display names.
FIELDS = [
    {'key': 'name', 'label': 'Name', 'sources': ['@name']},
    {'key': 'class', 'label': 'Class', 'sources': ['@class']},
    {'key': 'element_id', 'label': 'Element ID',
     'sources': [('Element ID', 'Value'), ('Element', 'Id'), ('Revit Element', 'Id')]},
    {'key': 'category', 'label': 'Category',
     'sources': [('Element', 'Category'), ('Revit Element', 'Category')]},
    {'key': 'family', 'label': 'Family', 'sources': [('Element', 'Family'), ('Revit Type', 'Family')]},
    {'key': 'type', 'label': 'Type', 'sources': [('Element', 'Type'), ('Revit Type', 'Name')]},
    {'key': 'mark', 'label': 'Mark', 'sources': [('Element', 'Mark')]},
    {'key': 'comments', 'label': 'Comments', 'sources': [('Element', 'Comments')]},
    {'key': 'ifc_guid', 'label': 'IFC GlobalId',
     'sources': [('Element', 'IfcGUID'), ('Element', 'IFC GUID'), ('IFC', 'GlobalId'),
                 ('Element', 'GlobalId')]},
    {'key': 'ifc_name', 'label': 'IFC Name', 'sources': [('IFC', 'Name'), ('Element', 'IfcName')]},
    {'key': 'system', 'label': 'System Name',
     'sources': [('Element', 'System Name'), ('Element', 'System Classification')]},
    {'key': 'level', 'label': 'Level',
     'sources': [('Element', 'Level'), ('Element', 'Reference Level'), ('Element', 'Base Constraint'),
                 ('Element', 'Schedule Level')]},
]
FIELD_KEYS = [f['key'] for f in FIELDS]
DEFAULTS = {'fields': list(FIELD_KEYS), 'cap': 200, 'budget': 500000}
HOLDER = 'quickfind'


# ---- pure half ----------------------------------------------------------------------


def field_specs(keys):
    """Field specs for the configured keys, in FIELDS order; 'name' is always first (the
    result list shows it)."""
    wanted = set(keys or []) | set(['name'])
    return [dict(f) for f in FIELDS if f['key'] in wanted]


def clean(value):
    """One line of index text: separators and line breaks become spaces, ends trimmed."""
    if value is None:
        return ''
    text = value if isinstance(value, str) else str(value)
    for ch in (FIELD_SEP, ROW_SEP, '\t', '\r', '\n'):
        if ch in text:
            text = text.replace(ch, ' ')
    return text.strip()


def signature(models, field_keys):
    """What an index depends on: its format version, the fields and every appended file
    (name lower, size, modified time; -1 when the file cannot be read here)."""
    return {'version': VERSION, 'fields': list(field_keys),
            'models': [[str(m.get('name', '')).lower(), int(m.get('size', -1)),
                        int(m.get('mtime', -1))] for m in models]}


def same_signature(a, b):
    return a is not None and b is not None and a == b


def encode(sig, model_names, rows, sampled=False, built=None):
    """The JSON-ready index. rows: [(model_index, path_id, [field texts])]."""
    lines = []
    for model_index, path, values in rows:
        lines.append(FIELD_SEP.join([str(int(model_index)), clean(path)] + [clean(v) for v in values]))
    return {'format': FORMAT, 'version': VERSION, 'signature': sig, 'models': list(model_names),
            'fields': list(sig.get('fields') or []), 'sampled': bool(sampled),
            'built': built or datetime.datetime.now().replace(microsecond=0).isoformat(),
            'count': len(rows), 'rows': ROW_SEP.join(lines)}


def decode(data):
    """{'signature', 'models', 'fields', 'rows', 'sampled', 'built'} from encode()'s
    output, or None when it is not a readable index of this version."""
    if not isinstance(data, dict) or data.get('format') != FORMAT or data.get('version') != VERSION:
        return None
    fields = list(data.get('fields') or [])
    width = len(fields)
    rows = []
    text = data.get('rows') or ''
    if text:
        for line in text.split(ROW_SEP):
            parts = line.split(FIELD_SEP)
            if len(parts) < 2:
                continue
            try:
                model_index = int(parts[0])
            except ValueError:
                continue
            values = parts[2:2 + width]
            if len(values) < width:
                values = values + [''] * (width - len(values))
            rows.append((model_index, parts[1], values))
    return {'signature': data.get('signature'), 'models': list(data.get('models') or []),
            'fields': fields, 'rows': rows, 'sampled': bool(data.get('sampled')),
            'built': data.get('built') or ''}


def drop_type_ids(rows, is_element, id_at):
    """Blanks the Element ID of rows that are not real Revit elements, in models that
    mark their elements. rows: [(model_index, path, [values])]; is_element: one bool per
    row (the item carries the exporter's Element category); id_at: position of the
    Element ID in values (None: nothing to do).

    The nested parts under a Revit family instance carry an Element ID tab too, holding
    the TYPE's id: the same number on every instance of that type (field-verified, see
    pyNavis' Select by IDs). Left in the index, typing a type id would list parts of
    unrelated fixtures as if they were that element. A model whose exporter never wrote
    the category (no row of it is an element) keeps every id."""
    if id_at is None:
        return rows
    marked = set()
    for row, flag in zip(rows, is_element):
        if flag:
            marked.add(row[0])
    out = []
    for row, flag in zip(rows, is_element):
        values = row[2]
        if not flag and row[0] in marked and id_at < len(values) and values[id_at]:
            values = list(values)
            values[id_at] = ''
            row = (row[0], row[1], values)
        out.append(row)
    return out


def row_text(values):
    """The combined text a row is ranked on."""
    return JOIN.join(v for v in values if v)


def exact_words(words):
    """Query words that must match as written, not as a scattered subsequence: digit runs
    of 3 or more characters are ids ('312045' must not match '312 ... 0 ... 45')."""
    return [w for w in words if len(w) >= 3 and w.isdigit()]


def extends(previous, query):
    """True when every match of `query` is also a match of `previous`: the new query is
    the old one with characters added (subsequence matching only narrows)."""
    if previous is None:
        return False
    old = previous.lower()
    new = (query or '').lower()
    return bool(old.strip()) and new.startswith(old)


class QuickIndex(object):
    """Rows plus their lowered texts, ranked per keystroke with narrowing."""

    def __init__(self, fields, models, rows, sampled=False, built=''):
        self.fields = list(fields)
        self.labels = [_label(k) for k in self.fields]
        self.models = list(models)
        self.rows = list(rows)
        self.sampled = bool(sampled)
        self.built = built
        self.texts = [row_text(r[2]) for r in self.rows]
        self.lows = [t.lower() for t in self.texts]
        self.name_at = self.fields.index('name') if 'name' in self.fields else 0
        self._last_query = None
        self._last_matches = None

    def __len__(self):
        return len(self.rows)

    def search(self, query, limit=200):
        """(total matches, [(score, row index)] best first, at most limit)."""
        words = (query or '').lower().split()
        if not words:
            self._last_query, self._last_matches = None, None
            return 0, []
        sub = textmatch.Index([])
        if extends(self._last_query, query) and self._last_matches is not None:
            sub.items = list(self._last_matches)
            sub.texts = [self.texts[i] for i in sub.items]
            sub.lows = [self.lows[i] for i in sub.items]
        else:
            sub.items = list(range(len(self.rows)))
            sub.texts = self.texts
            sub.lows = self.lows
        ranked = sub.rank(query, limit=None)
        exact = exact_words(words)
        if exact:
            lows = self.lows
            ranked = [(s, i) for s, i in ranked if all(w in lows[i] for w in exact)]
        self._last_query = query
        self._last_matches = [i for _score, i in ranked]
        return len(ranked), ranked[:limit] if limit else ranked

    def all_matches(self):
        """Every row index the last search matched (best first)."""
        return list(self._last_matches or [])

    def entry(self, row_index):
        """pynavis.memory entry for a row."""
        model_index, path, _values = self.rows[row_index]
        name = self.models[model_index] if 0 <= model_index < len(self.models) else ''
        return {'m': name, 'i': model_index, 'p': path}

    def display(self, row_index, query):
        """What the results list shows for a row (see display_row)."""
        model_index, _path, values = self.rows[row_index]
        model = self.models[model_index] if 0 <= model_index < len(self.models) else ''
        return display_row(self.fields, self.labels, values, query, model)


def _label(key):
    for field in FIELDS:
        if field['key'] == key:
            return field['label']
    return key


def best_field(fields, values, query):
    """(field position, matched words) of the field that explains the match best: the
    most query words matched, then the highest score; (None, []) when none matches."""
    words = (query or '').lower().split()
    best = None
    for pos, value in enumerate(values):
        if not value:
            continue
        hit = []
        total = 0.0
        for word in words:
            s = textmatch.score(word, value)
            if s > 0:
                hit.append(word)
                total += s
        if not hit:
            continue
        key = (len(hit), total, -pos)
        if best is None or key > best[0]:
            best = (key, pos, hit)
    if best is None:
        return None, []
    return best[1], best[2]


def display_row(fields, labels, values, query, model=''):
    """{'name', 'name_spans', 'detail', 'detail_spans', 'model'} for one result: the name
    (highlighted when it matched) and a second line naming the field that matched
    ('Element ID: 312045', highlighted), or Category and Type when the name matched."""
    name_at = fields.index('name') if 'name' in fields else 0
    name = values[name_at] if name_at < len(values) else ''
    pos, hit = best_field(fields, values, query)
    name_spans = textmatch.spans(' '.join(hit), name) if pos == name_at and hit else []
    if pos is not None and pos != name_at:
        label = labels[pos]
        prefix = '%s: ' % label
        value = values[pos]
        spans = [(a + len(prefix), b + len(prefix)) for a, b in textmatch.spans(' '.join(hit), value)]
        detail, detail_spans = prefix + value, spans
    else:
        summary = []
        for key in ('category', 'type', 'class'):
            if key in fields:
                value = values[fields.index(key)]
                if value and value not in summary:
                    summary.append(value)
            if len(summary) >= 2:
                break
        detail, detail_spans = ', '.join(summary), []
    return {'name': name or '(unnamed)', 'name_spans': name_spans, 'detail': detail,
            'detail_spans': detail_spans, 'model': model}


def pieces(text, spans):
    """[(text, highlighted)] runs of text cut at the spans."""
    out = []
    at = 0
    for start, end in sorted(spans or []):
        start, end = max(start, at), min(end, len(text))
        if start >= end:
            continue
        if start > at:
            out.append((text[at:start], False))
        out.append((text[start:end], True))
        at = end
    if at < len(text):
        out.append((text[at:], False))
    return out or [(text, False)]


def status_text(total_rows, matches, shown, query, sampled=False):
    """The line under the search box."""
    if not (query or '').strip():
        text = 'Type to search %s elements' % '{:,}'.format(total_rows)
    elif not matches:
        text = 'No matches'
    elif matches > shown:
        text = '%s matches, showing the best %s' % ('{:,}'.format(matches), '{:,}'.format(shown))
    else:
        text = '%s %s' % ('{:,}'.format(matches), 'match' if matches == 1 else 'matches')
    if sampled:
        text += ' (index sampled: the first %s elements)' % '{:,}'.format(total_rows)
    return text


# ---- API half -----------------------------------------------------------------------------


def _doc(doc=None):
    if doc is not None:
        return doc
    from pynavis._api import Application
    return Application.ActiveDocument


def model_infos(doc=None):
    """[{'name', 'size', 'mtime'}] for each appended model (the loaded file, else its
    source), for the signature."""
    import os
    from namo import items
    out = []
    for model in items.models(_doc(doc)):
        path = model.get('file') or model.get('source') or ''
        size = mtime = -1
        try:
            if path and os.path.exists(path):
                size = int(os.path.getsize(path))
                mtime = int(os.path.getmtime(path))
        except Exception:
            pass
        out.append({'name': os.path.basename(str(path).replace('\\', '/')) or model['name'],
                    'size': size, 'mtime': mtime})
    return out


def index_path(doc=None):
    import os
    from namo import paths
    try:
        name = _doc(doc).FileName or ''
    except Exception:
        name = ''
    return os.path.join(paths.data_root(), 'index', paths.doc_key(name) + '.json')


def read_fields(item, specs):
    """The text of each field on one element ('' when absent)."""
    try:
        cats = item.PropertyCategories
    except Exception:
        cats = None
    found_cats = {}
    values = []
    for spec in specs:
        text = ''
        for source in spec['sources']:
            if source == '@name':
                text = item.DisplayName or ''
            elif source == '@class':
                text = item.ClassDisplayName or ''
            elif cats is not None:
                cat_name, prop_name = source
                if cat_name not in found_cats:
                    try:
                        found_cats[cat_name] = cats.FindCategoryByDisplayName(cat_name)
                    except Exception:
                        found_cats[cat_name] = None
                category = found_cats[cat_name]
                if category is None:
                    continue
                try:
                    prop = category.Properties.FindPropertyByDisplayName(prop_name)
                except Exception:
                    prop = None
                if prop is None:
                    continue
                text = _value_text(prop.Value)
            if text and str(text).strip():
                break
        values.append(clean(text))
    return values


def _value_text(variant):
    """Index text of a property value. VariantData.ToDisplayString() raises on anything
    that is not a display string (an Int32 Element > Id, a length), and str() of a
    variant carries its data type ('Int32:312045'), so the value goes through pynavis'
    own conversion first."""
    try:
        if variant.IsDisplayString:                 # nearly every indexed field
            return variant.ToDisplayString()
    except Exception:
        pass
    from namo import find_query, variants
    try:
        value = variants.to_python(variant)
    except Exception:
        return ''
    if find_query.kind_of(value) is None:
        return ''
    text = find_query.value_text(value)
    return '' if text == find_query.NO_VALUE else text


ELEMENT_CATEGORY = 'LcRevitData_Element'    # internal name: only real Revit elements carry it


def _is_element(item):
    try:
        return item.PropertyCategories.FindCategoryByName(ELEMENT_CATEGORY) is not None
    except Exception:
        return False


def build(doc=None, config=None, report=None):
    """Walks the model and returns a fresh QuickIndex (also cached and saved). report is
    a progress(fraction, label) callback that raises to cancel."""
    from namo import items, session
    document = _doc(doc)
    cfg = dict(DEFAULTS)
    cfg.update(config or {})
    specs = field_specs(cfg.get('fields'))
    keys = [s['key'] for s in specs]
    budget = int(cfg.get('budget') or DEFAULTS['budget'])

    def walk_tick(done, total=None):
        if report is not None:
            report(0.0, 'Finding elements: %s items walked' % '{:,}'.format(done))
        return True
    objects = items.objects(items.roots(document), tick=walk_tick, budget=budget)
    models = document.Models
    names = [m['name'] for m in items.models(document)]
    rows = []
    flags = []
    id_at = keys.index('element_id') if 'element_id' in keys else None
    total = len(objects)
    for index, obj in enumerate(objects):
        try:
            path_id = models.CreatePathId(obj)
            rows.append((path_id.ModelIndex, path_id.PathId, read_fields(obj, specs)))
            flags.append(id_at is not None and _is_element(obj))
        except Exception:
            continue
        if report is not None and index % 250 == 0:
            report(float(index) / max(1, total), 'Reading %s of %s elements' % (
                '{:,}'.format(index), '{:,}'.format(total)))
    rows = drop_type_ids(rows, flags, id_at)
    sig = signature(model_infos(document), keys)
    data = encode(sig, names, rows, sampled=objects.sampled)
    try:
        from namo import paths
        paths.write_json(index_path(document), data)
    except Exception as error:
        session.log('warning', 'Quick Find could not save its index: %s' % error)
    index = QuickIndex(keys, names, rows, sampled=objects.sampled, built=data['built'])
    _remember(document, sig, index)
    return index


def _remember(document, sig, index):
    from namo import session
    holder = session.holder(HOLDER)
    holder.index = index
    holder.key = (index_path(document), sig)


def cached(doc=None, config=None):
    """The index for the document when one is current (session first, then the file);
    None when there is none or the model changed (then build())."""
    from namo import paths, session
    document = _doc(doc)
    cfg = dict(DEFAULTS)
    cfg.update(config or {})
    keys = [s['key'] for s in field_specs(cfg.get('fields'))]
    sig = signature(model_infos(document), keys)
    path = index_path(document)
    holder = session.holder(HOLDER)
    if getattr(holder, 'key', None) == (path, sig) and getattr(holder, 'index', None) is not None:
        return holder.index
    data = decode(paths.load_json(path, None))
    if data is None or not same_signature(data['signature'], sig):
        return None
    index = QuickIndex(data['fields'], data['models'], data['rows'], data['sampled'], data['built'])
    _remember(document, sig, index)
    return index


def forget(doc=None):
    """Drops the session copy and the file (Rebuild). True when a file was removed."""
    import os
    from namo import session
    holder = session.holder(HOLDER)
    holder.index = None
    holder.key = None
    path = index_path(doc)
    if os.path.exists(path):
        try:
            os.remove(path)
            return True
        except OSError:
            return False
    return False


def resolve(index, row_indices, doc=None):
    """(ModelItems, missing count) for rows."""
    import os
    from namo import items
    document = _doc(doc)
    # The index names models as items.models does (source file, else the loaded file),
    # but pynavis.memory matches an entry's 'm' against the basename of
    # Model.SourceFileName only: translate, so a model without a source name resolves.
    memory_name = {}
    for model in items.models(document):
        memory_name.setdefault(model['name'], os.path.basename(model['source'] or ''))
    entries = []
    for i in row_indices:
        entry = index.entry(i)
        entry['m'] = memory_name.get(entry['m'], entry['m'])
        entries.append(entry)
    return items.resolve(entries, document)


# ---- window ----------------------------------------------------------------------------------


_ITEM_STYLE = r'''
<Style xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
       xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml" TargetType="ListBoxItem">
  <Setter Property="FocusVisualStyle" Value="{x:Null}"/>
  <Setter Property="Template">
    <Setter.Value>
      <ControlTemplate TargetType="ListBoxItem">
        <Grid Background="Transparent">
          <Border x:Name="Wash" Background="Transparent"/>
          <Border x:Name="Rail" Width="3" HorizontalAlignment="Left" Background="Transparent"/>
          <ContentPresenter Margin="12,6,12,6"/>
        </Grid>
        <ControlTemplate.Triggers>
          <Trigger Property="IsMouseOver" Value="True">
            <Setter TargetName="Wash" Property="Background" Value="%(surface)s"/>
          </Trigger>
          <Trigger Property="IsSelected" Value="True">
            <Setter TargetName="Wash" Property="Background" Value="%(selection)s"/>
            <Setter TargetName="Rail" Property="Background" Value="%(accent)s"/>
          </Trigger>
        </ControlTemplate.Triggers>
      </ControlTemplate>
    </Setter.Value>
  </Setter>
</Style>
'''


def _item_style(colors):
    from System.Windows.Markup import XamlReader
    return XamlReader.Parse(_ITEM_STYLE % colors)


def _rich(text, spans, size, muted, colors):
    """A TextBlock whose matched characters are SemiBold in ink."""
    from namo import ui
    from System.Windows import FontWeights, TextTrimming, TextWrapping
    from System.Windows.Documents import Run
    block = ui.text('', size=size, muted=muted, wrap=False)
    block.TextWrapping = TextWrapping.NoWrap
    block.TextTrimming = TextTrimming.CharacterEllipsis
    for piece, hit in pieces(text, spans):
        run = Run(piece)
        if hit:
            run.FontWeight = FontWeights.SemiBold
            run.Foreground = ui.brush(colors['ink'])
        block.Inlines.Add(run)
    return block


def _result_visual(shown, colors):
    from namo import ui
    from System.Windows import GridLength, GridUnitType, VerticalAlignment
    from System.Windows.Controls import ColumnDefinition, Grid, StackPanel
    grid = Grid()
    for width in ('star', 'auto'):
        column = ColumnDefinition()
        column.Width = GridLength(1, GridUnitType.Star) if width == 'star' else GridLength.Auto
        grid.ColumnDefinitions.Add(column)
    stack = StackPanel()
    stack.Children.Add(_rich(shown['name'], shown['name_spans'], 13, False, colors))
    if shown['detail']:
        stack.Children.Add(_rich(shown['detail'], shown['detail_spans'], 12, True, colors))
    Grid.SetColumn(stack, 0)
    grid.Children.Add(stack)
    model = ui.text(shown['model'], size=12, muted=True, wrap=False)
    model.Margin = ui._thickness(16, 0, 0, 0)
    model.VerticalAlignment = VerticalAlignment.Top
    Grid.SetColumn(model, 1)
    grid.Children.Add(model)
    return grid


class FindState(object):
    """window.Tag of the Quick Find window: result {'action': 'select'|'all'|'add',
    'rows': [row indices], 'query'} once a choice was made."""

    def __init__(self, win, index, cap):
        self.window = win
        self.index = index
        self.cap = cap
        self.shown = []           # row indices in the list, in order
        self.result = None
        self.query = ''

    def run(self, query):
        self.query = query or ''
        total, ranked = self.index.search(self.query, self.cap)
        self.shown = [i for _score, i in ranked]
        return total

    def finish(self, action, rows):
        if not rows:
            return False
        self.result = {'action': action, 'rows': list(rows), 'query': self.query}
        try:
            self.window.DialogResult = True
        except Exception:
            self.window.Close()
        return True


def build_window(index, cap=200, query=''):
    """The Quick Find window, unshown (window.Tag is a FindState)."""
    from namo import ui
    ui._wpf()
    from System.Windows import GridLength, GridUnitType
    from System.Windows.Controls import (Dock, DockPanel, Grid, ListBox, RowDefinition,
                                         ScrollBarVisibility)
    from System.Windows.Input import Key, Keyboard, ModifierKeys
    logger = ui.pinned_logger()
    colors = ui.palette()
    win = ui.window('Quick Find', width=640, height=560, resizable=True, min_width=460,
                    min_height=320)
    state = FindState(win, index, max(10, int(cap or 200)))
    win.Tag = state

    listing = ListBox()
    listing.BorderThickness = ui._thickness(0)
    listing.Background = ui.brush(colors['paper'])
    listing.ItemContainerStyle = _item_style(colors)
    listing.Focusable = True
    from System.Windows.Controls import ScrollViewer
    ScrollViewer.SetHorizontalScrollBarVisibility(listing, ScrollBarVisibility.Disabled)
    status = ui.hint('')

    def refresh(text):
        total = state.run(text)
        listing.Items.Clear()
        for row in state.shown:
            listing.Items.Add(_result_visual(index.display(row, state.query), colors))
        if listing.Items.Count:
            listing.SelectedIndex = 0
            listing.ScrollIntoView(listing.Items[0])
        status.Text = status_text(len(index), total, len(state.shown), state.query, index.sampled)
        select_button.IsEnabled = bool(state.shown)

    search, box = ui.search_box('Name, Element ID, type, mark, level...',
                                lambda text: refresh(text), delay_ms=120)

    def chosen_rows():
        position = listing.SelectedIndex
        if 0 <= position < len(state.shown):
            return [state.shown[position]]
        return []

    def act(action):
        if action == 'all':
            state.query = box.Text
            return state.finish('all', index.all_matches())
        return state.finish(action, chosen_rows())

    def move(delta):
        count = listing.Items.Count
        if not count:
            return
        position = max(0, min(count - 1, listing.SelectedIndex + delta))
        listing.SelectedIndex = position
        listing.ScrollIntoView(listing.Items[position])

    def keys(sender, args):
        mods = Keyboard.Modifiers
        if args.Key == Key.Down:
            move(1)
            args.Handled = True
        elif args.Key == Key.Up:
            move(-1)
            args.Handled = True
        elif args.Key == Key.PageDown:
            move(8)
            args.Handled = True
        elif args.Key == Key.PageUp:
            move(-8)
            args.Handled = True
        elif args.Key in (Key.Enter, Key.Return):
            if state.query != box.Text:
                refresh(box.Text)          # Enter before the debounce fired
            if mods == ModifierKeys.Shift:
                act('all')
            elif mods == ModifierKeys.Control:
                act('add')
            else:
                act('select')
            args.Handled = True
        elif args.Key == Key.Escape:
            ui._close_with(win, False)
            args.Handled = True
    win.PreviewKeyDown += ui.safe(keys, 'quick find keys', logger)
    listing.MouseDoubleClick += ui.safe(lambda s, e: act('select'), 'quick find open', logger)

    root = Grid()
    root.Margin = ui._thickness(16, 16, 16, 8)
    for size in ('auto', 'auto', 'star'):
        definition = RowDefinition()
        definition.Height = GridLength(1, GridUnitType.Star) if size == 'star' else GridLength.Auto
        root.RowDefinitions.Add(definition)
    Grid.SetRow(search, 0)
    root.Children.Add(search)
    status.Margin = ui._thickness(2, 6, 0, 8)
    Grid.SetRow(status, 1)
    root.Children.Add(status)
    Grid.SetRow(listing, 2)
    root.Children.Add(listing)

    keys_hint = ui.hint('Enter selects and zooms, Shift+Enter selects every match, '
                        'Ctrl+Enter adds to the selection')
    select_button = ui.button('Select', lambda: act('select'), 'primary', logger)
    close_button = ui.button('Close', lambda: ui._close_with(win, False), 'secondary', logger)
    close_button.IsCancel = True
    bottom = ui.footer([select_button, close_button], left=keys_hint, padding=16)
    layout = DockPanel()
    DockPanel.SetDock(bottom, Dock.Bottom)
    layout.Children.Add(bottom)
    layout.Children.Add(root)
    win.Content = layout

    def first_focus(sender, args):
        box.Focus()
        box.SelectAll()
    win.ContentRendered += ui.safe(first_focus, 'quick find focus', logger)
    if query:
        box.Text = query
    refresh(query)
    state.refresh = refresh
    state.box = box
    state.listing = listing
    state.status = status
    return win


def dialog(index, cap=200, query=''):
    """Shows Quick Find; returns FindState.result or None (closed)."""
    from namo import ui
    win = build_window(index, cap, query)
    ui.show_modal(win)
    return win.Tag.result
