# -*- coding: utf-8 -*-
"""Properties Plus: a modeless window that follows the selection live.

Top: the pinned properties ('Category > Property', kept in the button's config) over
the whole selection: the value when every selected item agrees, otherwise
'Varies (N values)'; picking a row shows its most common values underneath (no
hover-only tooltips). Bottom: 'This item', every tab and property of the first
selected item, filterable. Actions: copy a value, select every item in the model with
that value (native search where Navisworks matches exactly, confirmed in Python),
pin and unpin.

Live wiring (all on the session holder 'properties-plus', all handlers guarded):
doc.CurrentSelection.Changed with a 200 ms debounce, re-subscribed on
Application.ActiveDocumentChanged, everything removed when the window closes.
"""

from namo import inspect, propindex

KEY = 'properties-plus'
TITLE = 'Properties Plus'
HOLDER = 'properties-plus'
DEBOUNCE_MS = 200
READ_BUDGET = 2000          # selected items read per refresh (the status line says when it is fewer)
DEFAULTS = {'pins': ['Element > Category', 'Element > Family', 'Element > Type', 'Element > Mark',
                     'Item > Source File']}


# =============================================================================
# Pure half
# =============================================================================


def pinned_rows(pins, summaries):
    """Table rows for the pinned list: [{'cells': [pin, value], 'value': pin}]."""
    rows = []
    for pin in pins:
        summary = summaries.get(pin) or {'value': ''}
        rows.append({'cells': [pin, summary.get('value', '')], 'value': pin})
    return rows


def item_rows(readings):
    """'This item' rows from Reader.all(): value = (category, property, text, vtype)."""
    return [{'cells': [category, prop, text], 'value': (category, prop, text, vtype)}
            for category, prop, _kind, vtype, text in readings]


def status_line(count, read):
    if not count:
        return 'Nothing selected. Select something in the model.'
    text = '%s %s selected' % ('{:,}'.format(count), 'item' if count == 1 else 'items')
    if read < count:
        text += ' (values from the first %s)' % '{:,}'.format(read)
    return text


def detail_line(pin, summary):
    """The line under the pinned list for the picked row."""
    if not summary:
        return ''
    state = summary.get('state')
    if state == 'same':
        return '%s: %s on all %s' % (pin, summary['value'], '{:,}'.format(summary['present']))
    if state == 'missing':
        return '%s is not on the selected items.' % pin
    if state == 'varies':
        shown = ', '.join('%s (%s)' % (text, '{:,}'.format(n)) for text, n in summary['counts'][:inspect.VARIES_SHOWN])
        more = summary['distinct'] - inspect.VARIES_SHOWN
        if more > 0:
            shown += ' and %s more' % '{:,}'.format(more)
        return 'Most common: ' + shown
    return ''


def add_pins(pins, new):
    """pins with new ones appended (no duplicates, case-insensitive)."""
    return inspect.clean_pins(list(pins) + list(new))


def remove_pins(pins, gone):
    lowered = set(p.lower() for p in gone)
    return [p for p in pins if p.lower() not in lowered]


# =============================================================================
# Reading
# =============================================================================


def summarize_selection(doc, pins, reader, budget=READ_BUDGET):
    """(count, read, {pin: summary}, first item or None) for the document's selection."""
    selected = doc.CurrentSelection.SelectedItems
    count = int(selected.Count)
    picked = []
    for item in selected:
        if len(picked) >= budget:
            break
        picked.append(item)
    summaries = {}
    for pin in pins:
        pair = inspect.parse_pin(pin)
        if pair is None:
            continue
        texts = [reader.text(item, pair[0], pair[1]) for item in picked]
        summaries[pin] = inspect.summarize(texts, propindex.MISSING)
    return count, len(picked), summaries, (picked[0] if picked else None)


# =============================================================================
# Window
# =============================================================================


class PlusState(object):
    """window.Tag of the Properties Plus window."""

    def __init__(self, win, me, logger, pins):
        self.window = win
        self.me = me
        self.logger = logger
        self.pins = list(pins)
        self.summaries = {}
        self.first = None
        self.pinned = None
        self.this_item = None
        self.status = None
        self.detail = None
        self.item_title = None
        self.item_panel = None
        self.toggle = None

    # -- painting --

    def paint(self, doc=None):
        from pynavis._api import Application
        document = doc or Application.ActiveDocument
        if document is None:
            return
        reader = propindex.Reader(document)
        count, read, self.summaries, self.first = summarize_selection(document, self.pins, reader)
        self.status.Text = status_line(count, read)
        keep = self.pinned.selected_values()
        self.pinned.update(pinned_rows(self.pins, self.summaries))
        if keep:
            self.pinned.select_values(keep[:1])
        self.on_pin()
        if self.first is None:
            self.item_title.Text = 'This item'
            self.this_item.update([])
            return
        name = self.first.DisplayName or self.first.ClassDisplayName or 'Item'
        self.item_title.Text = 'This item: %s' % name
        self.this_item.update(item_rows(reader.all(self.first)))

    def on_pin(self):
        picked = self.pinned.selected_values()
        if not picked:
            self.detail.Text = 'Pick a pinned property to see its values.' if self.pins else \
                'Pin properties to compare them across the selection.'
            return
        self.detail.Text = detail_line(picked[0], self.summaries.get(picked[0]))

    def save_pins(self):
        if self.me is not None:
            values = self.me.get_config(DEFAULTS)
            values['pins'] = list(self.pins)
            self.me.save_config(values)

    # -- actions --

    def pin_dialog(self):
        from namo import ui
        from pynavis import toast
        choices = []
        if self.first is not None:
            for category, prop, _kind, _vtype, _text in propindex.Reader().all(self.first):
                key = inspect.pin_key(category, prop)
                if key not in [c[0] for c in choices]:
                    choices.append((key, category, prop))
        for pin in self.pins:
            pair = inspect.parse_pin(pin)
            if pair is not None and pin not in [c[0] for c in choices]:
                choices.append((pin, pair[0], pair[1]))
        if not choices:
            toast.info('Nothing to pin yet', 'Select an item: its properties become the choices.')
            return
        rows = [{'cells': [category, prop], 'value': key} for key, category, prop in choices]
        picked = ui.choose('Pin properties', rows, ['Tab', 'Property'], multiselect=True, checked=self.pins,
                           prompt='Tick the properties to compare across the selection.', ok='Pin')
        if picked is None:
            return
        kept = [p for p in self.pins if p in picked]
        self.pins = add_pins(kept, [p for p in picked if p not in kept])
        self.save_pins()
        self.paint()

    def pin_from_item(self):
        picked = self.this_item.selected_values()
        if not picked:
            return
        self.pins = add_pins(self.pins, [inspect.pin_key(v[0], v[1]) for v in picked])
        self.save_pins()
        self.paint()

    def unpin(self):
        picked = self.pinned.selected_values()
        if not picked:
            return
        self.pins = remove_pins(self.pins, picked)
        self.save_pins()
        self.paint()

    def _pinned_value(self):
        """(category, property, text, vtype) of the picked pinned row when every
        selected item agrees, else None (toasted)."""
        from pynavis import toast
        picked = self.pinned.selected_values()
        if not picked:
            return None
        summary = self.summaries.get(picked[0]) or {}
        if summary.get('state') != 'same':
            toast.info('The selection holds several values', 'Pick a row with one value, or use This item below.')
            return None
        pair = inspect.parse_pin(picked[0])
        vtype = None
        if self.first is not None:
            for category, prop, _kind, vt, _text in propindex.Reader().all(self.first):
                if category == pair[0] and prop == pair[1]:
                    vtype = vt
                    break
        return (pair[0], pair[1], summary['value'], vtype)

    def copy_pinned(self):
        value = self._pinned_value()
        if value is not None:
            self._copy(value[2])

    def copy_item_value(self):
        picked = self.this_item.selected_values()
        if picked:
            self._copy('\r\n'.join(v[2] for v in picked) if len(picked) > 1 else picked[0][2])

    def _copy(self, text):
        from pynavis import toast
        from namo import ui
        if ui.copy(text):
            toast.success('Value copied', text if len(text) <= 80 else text[:77] + '...')
        else:
            toast.error('Could not copy', 'Another program is holding the clipboard; try again.')

    def select_pinned(self):
        value = self._pinned_value()
        if value is not None:
            self._select(*value)

    def select_item_value(self):
        picked = self.this_item.selected_values()
        if picked:
            self._select(*picked[0])

    def _select(self, category, prop, text, vtype):
        from pynavis import toast
        from namo import items, progress
        if text in (propindex.NO_VALUE, propindex.MISSING):
            toast.info('Pick a property that has a value', '%s > %s is empty here.' % (category, prop))
            return

        def work(report):
            from namo import data_common
            return propindex.find_in_model(category, prop, text, vtype,
                                           tick=data_common.stage(report, 0.0, 1.0, 'Reading %s'))
        outcome = progress.run('Finding items', work)
        if outcome is progress.CANCELLED:
            return
        found, how = outcome
        if not found:
            toast.info('No items have that value', '%s > %s = %s' % (category, prop, text))
            return
        items.select(found)
        detail = '%s > %s = %s' % (category, prop, text)
        if how == 'scan-sampled':
            toast.warning('Selected %s items (sampled)' % '{:,}'.format(len(found)),
                          detail + '. The model is large: only part of it was read.')
            return
        toast.success('Selected %s %s' % ('{:,}'.format(len(found)), 'item' if len(found) == 1 else 'items'),
                      detail)

    def toggle_item(self):
        from System.Windows import Visibility
        shown = self.item_panel.Visibility == Visibility.Visible
        self.item_panel.Visibility = Visibility.Collapsed if shown else Visibility.Visible
        self.toggle.Content = 'Show' if shown else 'Hide'


def build_window(me=None, pins=None, logger=None):
    """The window (unshown); window.Tag is its PlusState. Not wired to Navisworks yet
    (start() does that)."""
    from namo import ui
    ui._wpf()
    from System.Windows import GridLength, GridUnitType, Thickness, VerticalAlignment
    from System.Windows.Controls import Dock, DockPanel, Grid, Orientation, RowDefinition, StackPanel
    logger = logger or ui.pinned_logger()
    win = ui.window(TITLE, width=560, height=720, resizable=True, min_width=420, min_height=420)
    state = PlusState(win, me, logger, inspect.clean_pins(pins if pins is not None else DEFAULTS['pins']))
    win.Tag = state

    def guarded(fn, label):
        return ui.safe(fn, label, logger)

    state.pinned = ui.Table(['Pinned property', 'Value'], [], multiselect=True,
                            on_change=guarded(state.on_pin, 'pinned'), logger=logger)
    state.this_item = ui.Table(['Tab', 'Property', 'Value'], [], multiselect=True,
                               on_open=lambda value: guarded(state.copy_item_value, 'open')(), logger=logger)

    grid = Grid()
    grid.Margin = Thickness(16, 14, 16, 12)
    for size in ('auto', 'star', 'auto', 'auto', 'auto', 'auto', 'star1.4', 'auto'):
        row = RowDefinition()
        if size.startswith('star'):
            row.Height = GridLength(float(size[4:] or 1), GridUnitType.Star)
        else:
            row.Height = GridLength.Auto
        grid.RowDefinitions.Add(row)

    def place(element, row):
        Grid.SetRow(element, row)
        grid.Children.Add(element)

    head = DockPanel()
    head.Margin = Thickness(0, 0, 0, 8)
    pin_button = ui.button('Pin properties', state.pin_dialog, 'secondary', logger)
    DockPanel.SetDock(pin_button, Dock.Right)
    head.Children.Add(pin_button)
    state.status = ui.text('', 13, wrap=True)
    state.status.VerticalAlignment = VerticalAlignment.Center
    head.Children.Add(state.status)
    place(head, 0)
    place(state.pinned.element, 1)
    state.detail = ui.hint('')
    state.detail.Margin = Thickness(0, 6, 0, 6)
    place(state.detail, 2)
    actions = StackPanel()
    actions.Orientation = Orientation.Horizontal
    for index, (label, fn) in enumerate((('Copy value', state.copy_pinned),
                                         ('Select items with this value', state.select_pinned),
                                         ('Unpin', state.unpin))):
        control = ui.button(label, fn, 'secondary', logger)
        control.Margin = Thickness(0 if index == 0 else 8, 0, 0, 0)
        actions.Children.Add(control)
    place(actions, 3)
    place(ui.separator((0, 14, 0, 10)), 4)

    item_head = DockPanel()
    item_head.Margin = Thickness(0, 0, 0, 6)
    state.toggle = ui.button('Hide', state.toggle_item, 'quiet', logger)
    DockPanel.SetDock(state.toggle, Dock.Right)
    item_head.Children.Add(state.toggle)
    state.item_title = ui.text('This item', 13, bold=True, wrap=False)
    state.item_title.VerticalAlignment = VerticalAlignment.Center
    item_head.Children.Add(state.item_title)
    place(item_head, 5)

    panel = Grid()
    for size in ('auto', 'star', 'auto'):
        row = RowDefinition()
        row.Height = GridLength(1, GridUnitType.Star) if size == 'star' else GridLength.Auto
        panel.RowDefinitions.Add(row)
    search, _box = ui.search_box('Filter properties', lambda query: state.this_item.set_filter(query))
    search.Margin = Thickness(0, 0, 0, 8)
    Grid.SetRow(search, 0)
    panel.Children.Add(search)
    Grid.SetRow(state.this_item.element, 1)
    panel.Children.Add(state.this_item.element)
    item_actions = StackPanel()
    item_actions.Orientation = Orientation.Horizontal
    item_actions.Margin = Thickness(0, 8, 0, 0)
    for index, (label, fn) in enumerate((('Pin', state.pin_from_item), ('Copy value', state.copy_item_value),
                                         ('Select items with this value', state.select_item_value))):
        control = ui.button(label, fn, 'secondary', logger)
        control.Margin = Thickness(0 if index == 0 else 8, 0, 0, 0)
        item_actions.Children.Add(control)
    Grid.SetRow(item_actions, 2)
    panel.Children.Add(item_actions)
    state.item_panel = panel
    place(panel, 6)

    close = ui.button('Close', lambda: win.Close(), 'secondary', logger)
    close.IsCancel = True
    bar = ui.footer([close], left=ui.hint('Follows the selection while open.'), padding=16)
    layout = DockPanel()
    DockPanel.SetDock(bar, Dock.Bottom)
    layout.Children.Add(bar)
    layout.Children.Add(grid)
    win.Content = layout
    state.pinned.update(pinned_rows(state.pins, {}))
    state.on_pin()
    return win


def _holder():
    from namo import session
    return session.holder(HOLDER)


def _unwire(holder):
    """Removes every subscription the open window made. Never raises."""
    from pynavis._api import Application
    document = getattr(holder, 'doc', None)
    handler = getattr(holder, 'on_selection', None)
    if document is not None and handler is not None:
        try:
            document.CurrentSelection.Changed -= handler
        except Exception:
            pass
    on_document = getattr(holder, 'on_document', None)
    if on_document is not None:
        try:
            Application.ActiveDocumentChanged -= on_document
        except Exception:
            pass
    debounce = getattr(holder, 'debounce', None)
    if debounce is not None:
        try:
            debounce.cancel()
        except Exception:
            pass
    for name in ('doc', 'on_selection', 'on_document', 'debounce'):
        setattr(holder, name, None)


def show(me, logger=None):
    """Opens the window (or brings the open one forward) and wires it to the
    selection. Returns the window."""
    from namo import ui
    existing = ui.Modeless.get(KEY)
    if existing is not None:
        existing.Activate()
        return existing
    from pynavis._api import Application
    logger = logger or ui.pinned_logger()
    pins = me.get_config(DEFAULTS).get('pins') if me is not None else None
    win = ui.Modeless(KEY, TITLE, window_factory=lambda: build_window(me, pins, logger)).show()
    state = win.Tag
    holder = _holder()
    _unwire(holder)
    debounce = ui.Debouncer(DEBOUNCE_MS, lambda: state.paint())
    holder.debounce = debounce

    def on_selection(sender, args):
        try:
            debounce.trigger()
        except Exception:
            ui.log_error('Properties Plus selection handler failed', logger)

    def subscribe(document):
        previous = getattr(holder, 'doc', None)
        if previous is document:
            return
        if previous is not None:
            try:
                previous.CurrentSelection.Changed -= on_selection
            except Exception:
                pass
        holder.doc = document
        if document is not None:
            document.CurrentSelection.Changed += on_selection

    def on_document(sender, args):
        try:
            subscribe(Application.ActiveDocument)
            debounce.trigger()
        except Exception:
            ui.log_error('Properties Plus document switch failed', logger)

    def on_closed(sender, args):
        _unwire(holder)

    holder.on_selection = on_selection
    holder.on_document = on_document
    try:
        Application.ActiveDocumentChanged += on_document
        subscribe(Application.ActiveDocument)
        win.Closed += ui.safe(on_closed, 'Properties Plus closed', logger)
        state.paint()
    except Exception:
        _unwire(holder)
        try:
            win.Close()
        except Exception:
            pass
        raise
    return win
