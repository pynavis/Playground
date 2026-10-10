# -*- coding: utf-8 -*-
"""Unit Converter: a small calculator window that converts as you type.

Reads "12' 6\\" to mm", "250 sqft in m2", "3.5 m3 cuyd", "1200 kg lb" (the target
can follow the quantity without a word between), or a bare value with the From and To
lists. Enter copies the result; the last 10 conversions are kept (local store
'converter-history'); "Document units" (Ctrl+D) points the target at the active
model's units, squared or cubed for areas and volumes.

Pure half: parse(), format_number(), result_text(), push_history(), with_target(),
UNIT_CHOICES. API half: the modeless window (one per session, survives Reload).
"""
import math

from namo import store, ui, units

HISTORY_STORE = 'converter-history'
HISTORY_LIMIT = 10
UNIT_CHOICES = [
    ('Length', ['mm', 'cm', 'm', 'km', 'in', 'ft', 'yd', 'mi']),
    ('Area', ['mm2', 'cm2', 'm2', 'ha', 'km2', 'in2', 'ft2', 'yd2', 'ac']),
    ('Volume', ['cm3', 'l', 'm3', 'in3', 'ft3', 'yd3', 'gal', 'gal_uk']),
    ('Mass', ['g', 'kg', 't', 'oz', 'lb', 'ton']),
]
HINT = 'Type a conversion like 12\' 6" to mm, 250 sqft in m2 or 1200 kg lb.'

# ---- pure -------------------------------------------------------------------------------


def all_units():
    out = []
    for _kind, symbols in UNIT_CHOICES:
        out.extend(symbols)
    return out


def format_number(value, significant=8):
    """Thousands separators, up to `significant` significant digits, no trailing zeros."""
    if value is None:
        return ''
    if value == 0 or math.isinf(value) or math.isnan(value):
        return '0' if value == 0 else str(value)
    magnitude = int(math.floor(math.log10(abs(value))))
    decimals = max(0, min(10, significant - 1 - magnitude))
    text = ('{:,.%df}' % decimals).format(value)
    if '.' in text:
        text = text.rstrip('0').rstrip('.')
    if text in ('-0', ''):
        text = '0'
    return text


def _implicit(text):
    """(value, from, to) for 'quantity unit target' with no separator word, else None."""
    words = text.split()
    for cut in (1, 2):
        if len(words) <= cut:
            continue
        target = units.resolve(' '.join(words[-cut:]))
        if target is None:
            continue
        quantity = units.parse_quantity(' '.join(words[:-cut]))
        if quantity is not None and quantity[1] is not None:
            return quantity[0], quantity[1], target
    return None


def parse(text, from_unit=None, to_unit=None):
    """{'ok', 'value', 'from', 'to', 'result', 'error', 'kind'} for the input.

    A sentence with its own units wins; a quantity with a unit converts to to_unit; a
    bare number converts from_unit to to_unit."""
    text = (text or '').strip()
    out = {'ok': False, 'value': None, 'from': None, 'to': None, 'result': None, 'error': None,
           'kind': None}
    if not text:
        return out
    parsed = units.parse_conversion(text) or _implicit(text)
    if parsed is None:
        quantity = units.parse_quantity(text)
        if quantity is None:
            out['error'] = HINT
            return out
        value, unit, _kind = quantity
        source = unit or units.resolve(from_unit)
        target = units.resolve(to_unit)
        if source is None or target is None:
            out['error'] = 'Pick the units to convert between.'
            return out
        parsed = (value, source, target)
    value, source, target = parsed
    out.update({'value': value, 'from': source, 'to': target, 'kind': units.kind_of(source)})
    try:
        out['result'] = units.convert(value, source, target)
    except ValueError:
        out['error'] = 'Cannot convert %s (%s) to %s (%s).' % (
            units.symbol(source), units.kind_of(source), units.symbol(target), units.kind_of(target))
        return out
    out['ok'] = True
    return out


def result_text(parsed):
    """('1,250 mm', secondary line) for a parsed result; secondary shows feet and inches
    for lengths in ft or in."""
    if not parsed.get('ok'):
        return '', parsed.get('error') or ''
    main = '%s %s' % (format_number(parsed['result']), units.symbol(parsed['to']))
    secondary = '%s %s = %s' % (format_number(parsed['value']), units.symbol(parsed['from']), main)
    if parsed['to'] in ('ft', 'in') and parsed['kind'] == 'length':
        feet = parsed['result'] if parsed['to'] == 'ft' else parsed['result'] / 12.0
        secondary += ', or %s' % units.format_feet_inches(feet)
    return main, secondary


def copy_text(parsed):
    """What Enter puts on the clipboard: the number and unit, ASCII symbol."""
    if not parsed.get('ok'):
        return ''
    return '%s %s' % (format_number(parsed['result']).replace(',', ''), units.symbol(parsed['to'], ascii=True))


def push_history(history, entry, limit=HISTORY_LIMIT):
    """Most recent first, deduped, capped."""
    out = [entry]
    for item in history or []:
        if isinstance(item, str) and item != entry:
            out.append(item)
    return out[:limit]


def history_entry(text, parsed):
    main, _secondary = result_text(parsed)
    return '%s = %s' % (' '.join((text or '').split()), main)


def doc_target(doc_units, kind):
    """The document's unit for a kind: 'ft' -> 'ft2' for an area; None when unknown."""
    base = units.doc_unit_symbol(doc_units) if doc_units else None
    if not base:
        return None
    if kind == 'area':
        return units.resolve(base + '2')
    if kind == 'volume':
        return units.resolve(base + '3')
    if kind == 'mass':
        return None
    return base


def with_target(text, target):
    """The input with its target unit replaced by target (or ' to target' added)."""
    text = (text or '').strip()
    parsed = units.parse_conversion(text)
    if parsed is not None:
        for word in (' to ', ' in ', ' into ', ' as ', '->', '=>', '='):
            index = text.lower().rfind(word)
            if index > 0 and units.resolve(text[index + len(word):].strip().lstrip('?').strip()):
                return '%s to %s' % (text[:index].rstrip(), target)
    implicit = _implicit(text)
    if implicit is not None:
        words = text.split()
        for cut in (1, 2):
            if len(words) > cut and units.resolve(' '.join(words[-cut:])) == implicit[2]:
                return '%s to %s' % (' '.join(words[:-cut]), target)
    return '%s to %s' % (text, target) if text else ''


# ---- API half: the window --------------------------------------------------------------------


def history_store():
    return store.Store(HISTORY_STORE, scope='global', mode='local')


def load_history():
    value = history_store().load([])
    return [h for h in value if isinstance(h, str)] if isinstance(value, list) else []


def save_history(history):
    try:
        history_store().save(history)
    except Exception:
        pass


KEY = 'playground-unit-converter'


def build(win, doc_units=None, history=None, logger=None):
    """Fills the converter window; returns its content (window.Tag gets the parts)."""
    ui.load_wpf()
    from System.Windows import GridLength, GridUnitType, HorizontalAlignment, VerticalAlignment
    from System.Windows.Controls import (ColumnDefinition, Dock, DockPanel, Grid, ListBox,
                                         Orientation, StackPanel)
    from System.Windows.Input import Key, Keyboard, ModifierKeys
    logger = logger or ui.pinned_logger()
    colors = ui.palette()
    parts = ui.Bag(doc_units=doc_units, history=list(history or []), parsed=parse(''))
    win.Tag = parts

    field, box = ui.text_box('', placeholder='12\' 6" to mm')
    unit_labels = []
    for kind, symbols in UNIT_CHOICES:
        for symbol in symbols:
            unit_labels.append(('%s  (%s)' % (units.symbol(symbol), kind.lower()), symbol))
    from_combo = ui.combo(unit_labels, 'ft', width=150)
    to_combo = ui.combo(unit_labels, 'mm', width=150)
    result = ui.text('', size=22, wrap=True)
    result.Margin = ui.thickness(0, 16, 0, 0)
    secondary = ui.hint(HINT)
    history_list = ListBox()
    history_list.BorderThickness = ui.thickness(1)
    history_list.BorderBrush = ui.brush(colors['line'])
    history_list.Background = ui.brush(colors['paper'])
    history_list.Height = 150.0

    def refresh(*args):
        parts.parsed = parse(box.Text, ui.combo_value(from_combo), ui.combo_value(to_combo))
        main, second = result_text(parts.parsed)
        result.Text = main
        secondary.Text = second or (HINT if not box.Text.strip() else '')
        secondary.Foreground = ui.brush(colors['error'] if parts.parsed.get('error') and box.Text.strip()
                                        else colors['muted'])
        copy_button.IsEnabled = bool(parts.parsed.get('ok'))

    def fill_history():
        history_list.Items.Clear()
        for item in parts.history:
            history_list.Items.Add(item)

    def copy_result():
        if not parts.parsed.get('ok'):
            return
        ui.copy(copy_text(parts.parsed))
        parts.history = push_history(parts.history, history_entry(box.Text, parts.parsed))
        save_history(parts.history)
        fill_history()
        secondary.Text = 'Copied %s' % copy_text(parts.parsed)

    def use_doc_units():
        kind = parts.parsed.get('kind') or 'length'
        target = doc_target(parts.doc_units, kind)
        if target is None:
            secondary.Text = 'Open a model to use its units.' if not parts.doc_units else \
                'The document units do not apply to %s.' % kind
            return
        quantity = units.parse_quantity(box.Text)
        has_unit = quantity is not None and quantity[1] is not None
        if has_unit or units.parse_conversion(box.Text) or _implicit(box.Text):
            box.Text = with_target(box.Text, target)
        else:
            index = [v for _l, v in unit_labels].index(target) if target in [v for _l, v in unit_labels] else -1
            if index >= 0:
                to_combo.SelectedIndex = index
        box.CaretIndex = len(box.Text)
        refresh()

    def history_pick(*args):
        item = history_list.SelectedItem
        if item is None:
            return
        box.Text = str(item).split(' = ')[0]
        box.Focus()
        box.CaretIndex = len(box.Text)

    copy_button = ui.button('Copy', copy_result, 'primary', logger)
    doc_button = ui.button('Document units', use_doc_units, 'secondary', logger)
    box.TextChanged += ui.safe(refresh, 'converter typing', logger)
    from_combo.SelectionChanged += ui.safe(refresh, 'converter from', logger)
    to_combo.SelectionChanged += ui.safe(refresh, 'converter to', logger)
    history_list.MouseDoubleClick += ui.safe(history_pick, 'converter history', logger)

    def keys(sender, args):
        ctrl = Keyboard.Modifiers == ModifierKeys.Control
        if args.Key in (Key.Enter, Key.Return):
            if history_list.IsKeyboardFocusWithin:
                history_pick()
            else:
                copy_result()
        elif args.Key == Key.D and ctrl:
            use_doc_units()
        elif args.Key == Key.Escape:
            win.Close()
        elif args.Key == Key.Down and box.IsKeyboardFocusWithin and history_list.Items.Count:
            history_list.SelectedIndex = 0
            history_list.Focus()
        else:
            return
        args.Handled = True
    win.PreviewKeyDown += ui.safe(keys, 'converter keys', logger)

    units_row = StackPanel()
    units_row.Orientation = Orientation.Horizontal
    units_row.Margin = ui.thickness(0, 8, 0, 0)
    arrow = ui.text('to', muted=True, wrap=False)
    arrow.VerticalAlignment = VerticalAlignment.Center
    arrow.Margin = ui.thickness(8, 0, 8, 0)
    for control in (from_combo, arrow, to_combo):
        units_row.Children.Add(control)
    units_hint = ui.hint('The lists apply when you type a bare number.')
    units_hint.Margin = ui.thickness(0, 4, 0, 0)

    result_row = Grid()
    for width in ('star', 'auto'):
        column = ColumnDefinition()
        column.Width = GridLength(1, GridUnitType.Star) if width == 'star' else GridLength.Auto
        result_row.ColumnDefinitions.Add(column)
    Grid.SetColumn(result, 0)
    result_row.Children.Add(result)
    copy_button.VerticalAlignment = VerticalAlignment.Bottom
    copy_button.HorizontalAlignment = HorizontalAlignment.Right
    Grid.SetColumn(copy_button, 1)
    result_row.Children.Add(copy_button)

    body = StackPanel()
    body.Margin = ui.thickness(24, 20, 24, 16)
    body.Children.Add(field)
    body.Children.Add(units_row)
    body.Children.Add(units_hint)
    body.Children.Add(result_row)
    secondary.Margin = ui.thickness(0, 4, 0, 16)
    body.Children.Add(secondary)
    body.Children.Add(ui.text('Recent', size=12, bold=True))
    history_list.Margin = ui.thickness(0, 6, 0, 0)
    body.Children.Add(history_list)

    footer_hint = ui.hint('Enter copies, Ctrl+D uses the document units')
    close_button = ui.button('Close', lambda: win.Close(), 'secondary', logger)
    footer = ui.footer([doc_button, close_button], left=footer_hint, padding=24)
    layout = DockPanel()
    DockPanel.SetDock(footer, Dock.Bottom)
    layout.Children.Add(footer)
    layout.Children.Add(body)

    def first_focus(sender, args):
        box.Focus()
    win.ContentRendered += ui.safe(first_focus, 'converter focus', logger)
    fill_history()
    parts.box = box
    parts.result = result
    parts.secondary = secondary
    parts.copy = copy_result
    parts.use_doc_units = use_doc_units
    parts.from_combo = from_combo
    parts.to_combo = to_combo
    parts.history_list = history_list
    parts.refresh = refresh
    refresh()
    return layout


def show(doc_units=None):
    """Opens the converter (or brings the open one forward, updating its units)."""
    existing = ui.Modeless.get(KEY)
    if existing is not None:
        try:
            existing.Tag.doc_units = doc_units
        except Exception:
            pass
    history = load_history()
    logger = ui.pinned_logger()
    win = ui.Modeless(KEY, 'Unit Converter', lambda w: build(w, doc_units, history, logger),
                      width=460).show()
    return win
