# -*- coding: utf-8 -*-
"""Selection HUD: a small, non-activating readout of the current selection anchored to
the bottom-left corner of the Navisworks window.

    "1,204 items selected (312 objects)"
    "ARCH.rvt, MEP.rvt"
    "Ducts 120, Pipes 80, Walls 12"
    "Length: 124.5 m"                 (only when a property to sum is configured)

Pure half: stats_lines() turns collected stats into the lines shown (tested).
API half: collect() reads the selection (the first READ_BUDGET items for objects,
models, categories and the sum; the count itself is always exact and the HUD says
when it read only part), and start()/stop() own the window, the selection
subscription (doc.CurrentSelection.Changed, 200 ms debounce), the document switch
re-subscription (Application.ActiveDocumentChanged) and a 1 s re-anchor timer.
Everything that outlives the toggle's run lives on the session holder 'selection-hud';
every late callback is wrapped and logs instead of raising.
"""

from namo import naming

HOLDER = 'selection-hud'
READ_BUDGET = 2000          # selected items read for objects / models / categories / sum (every
                            # selection change pays for this read on the UI thread, so it stays small)
DEBOUNCE_MS = 200
ANCHOR_MS = 1000
MARGIN_LEFT = 24            # WPF units from the host window's left edge
MARGIN_BOTTOM = 56          # clears the status bar
TOP_CATEGORIES = 3
MODELS_SHOWN = 3


# =============================================================================
# Pure half
# =============================================================================


def _n(value):
    return '{:,}'.format(int(value))


def top_counts(counts, limit=TOP_CATEGORIES):
    """[(name, count)] largest first, ties in natural order."""
    rows = list(counts.items())
    rows.sort(key=lambda p: (-p[1], naming.natural_key(p[0]), p[0]))
    return rows[:limit]


def models_text(names, limit=MODELS_SHOWN):
    """'ARCH.rvt, MEP.rvt' or 'A.rvt, B.rvt, C.rvt and 2 more' (natural order)."""
    ordered = sorted(set(n for n in names if n), key=lambda n: (naming.natural_key(n), n))
    if not ordered:
        return ''
    shown = ordered[:limit]
    text = ', '.join(shown)
    if len(ordered) > limit:
        text += ' and %d more' % (len(ordered) - limit)
    return text


def sum_text(label, total, unit, counted, present):
    """'Length: 124.5 m' (+ ' on 38 of 40' when some items lack it)."""
    if not present:
        return '%s: not on the selection' % label
    number = ('{:,.2f}'.format(total)).rstrip('0').rstrip('.')
    text = '%s: %s%s' % (label, number, (' ' + unit) if unit else '')
    if present != counted:
        text += ' on %s of %s' % (_n(present), _n(counted))
    return text


def stats_lines(stats):
    """[(text, muted)] for the HUD from collect()'s stats dict:
    {'count', 'read', 'objects', 'models': [names], 'categories': {name: n},
     'sum': None or {'label', 'total', 'unit', 'present'}}."""
    count = stats.get('count') or 0
    if not count:
        return [('Nothing selected', True)]
    read = stats.get('read') or 0
    objects = stats.get('objects') or 0
    noun = 'item' if count == 1 else 'items'
    head = '%s %s selected' % (_n(count), noun)
    if objects:
        partial = read < count
        head += ' (%s%s %s)' % (_n(objects), '+' if partial else '',
                                'object' if objects == 1 and not partial else 'objects')
    lines = [(head, False)]
    models = models_text(stats.get('models') or [])
    if models:
        lines.append((models, True))
    top = top_counts(stats.get('categories') or {})
    if top:
        lines.append((', '.join('%s %s' % (name, _n(n)) for name, n in top), True))
    total = stats.get('sum')
    if total:
        lines.append((sum_text(total['label'], total['total'], total.get('unit'), read,
                               total['present']), False))
    if read < count:
        lines.append(('Details from the first %s items' % _n(read), True))
    return lines


# =============================================================================
# API half
# =============================================================================


def _holder():
    from namo import session
    return session.holder(HOLDER)


def collect(doc, reader, sum_spec=None, budget=READ_BUDGET):
    """Stats for stats_lines() from the document's current selection."""
    from namo import items, propindex
    selected = doc.CurrentSelection.SelectedItems
    count = int(selected.Count)
    stats = {'count': count, 'read': 0, 'objects': 0, 'models': [], 'categories': {}, 'sum': None}
    if not count:
        return stats
    models = doc.Models
    names = {}
    for index in range(models.Count):
        source = models[index].SourceFileName or models[index].FileName or ''
        names[index] = str(source).replace('\\', '/').split('/')[-1]
    seen_objects = set()
    model_names = set()
    categories = {}
    total = 0.0
    present = 0
    unit = None
    read = 0
    for item in selected:
        if read >= budget:
            break
        read += 1
        try:
            model_names.add(names.get(models.CreatePathId(item).ModelIndex, ''))
        except Exception:
            pass
        element = items.object_of(item)
        if element in seen_objects:
            continue
        seen_objects.add(element)
        exists, _kind, value = reader.one(element, 'Element', 'Category')
        if not exists or value is None or not str(value).strip():
            try:
                value = element.ClassDisplayName or 'Other'
            except Exception:
                value = 'Other'
        name = str(value)
        categories[name] = categories.get(name, 0) + 1
        if sum_spec:
            exists, kind, raw = reader.one(element, sum_spec[0], sum_spec[1])
            if exists and raw is not None:
                plain = propindex.plain_value(kind, raw, reader.ctx)
                try:
                    total += float(plain)
                    present += 1
                    if kind in propindex.QUANTITY_KINDS and unit is None:
                        unit = propindex.quantity_value(kind, 1.0, reader.ctx)[1]
                except (TypeError, ValueError):
                    pass
    stats['read'] = read
    stats['objects'] = len(seen_objects)
    stats['models'] = sorted(model_names)
    stats['categories'] = categories
    if sum_spec:
        from namo import units as _units
        stats['sum'] = {'label': sum_spec[1], 'total': total,
                        'unit': _units.symbol(unit) if unit and unit != 'deg' else unit,
                        'present': present}
    return stats


def is_running():
    holder = _holder()
    win = getattr(holder, 'window', None)
    if win is None:
        return False
    try:
        return bool(win.IsVisible)
    except Exception:
        return False


def build_window():
    """The HUD window (unshown) and its update(lines) function."""
    from namo import ui
    ui._wpf()
    from System.Windows import (FontWeights, ResizeMode, SizeToContent, TextWrapping,
                                Thickness, WindowStartupLocation, WindowStyle)
    from System.Windows.Controls import Border, StackPanel, TextBlock
    palette = ui.palette()
    win = ui.window('Selection HUD', width=200, height=None, resizable=False)
    win.WindowStyle = getattr(WindowStyle, 'None')
    win.ResizeMode = ResizeMode.NoResize
    win.SizeToContent = SizeToContent.WidthAndHeight
    win.WindowStartupLocation = WindowStartupLocation.Manual    # placed by _place, never centred first
    win.Topmost = False
    win.ShowInTaskbar = False
    win.ShowActivated = False
    win.Focusable = False
    win.Background = ui.brush(palette['surface'])
    frame = Border()
    frame.Background = ui.brush(palette['surface'])
    frame.BorderBrush = ui.brush(palette['line_strong'])
    frame.BorderThickness = Thickness(1)
    frame.Padding = Thickness(12, 8, 14, 9)
    stack = StackPanel()
    frame.Child = stack
    win.Content = frame
    ink = ui.brush(palette['ink'])
    muted = ui.brush(palette['muted'])

    def update(lines):
        stack.Children.Clear()
        for index, (text, is_muted) in enumerate(lines):
            block = TextBlock()
            block.Text = text
            block.FontSize = 13.0 if index == 0 else 12.0
            block.Foreground = muted if is_muted else ink
            if index == 0 and not is_muted:
                block.FontWeight = FontWeights.Medium
            block.TextWrapping = TextWrapping.NoWrap
            block.MaxWidth = 460.0
            block.Margin = Thickness(0, 0 if index == 0 else 2, 0, 0)
            stack.Children.Add(block)
    win.Tag = update
    return win, update


def _place(win):
    from namo import ui
    host = ui.host_rect()
    scale = ui.dpi_scale(win) or 1.0
    left, top, right, bottom = [float(v) / scale for v in host]
    if right - left < 200 or bottom - top < 150:
        return host
    height = win.ActualHeight or 80.0
    win.Left = left + MARGIN_LEFT
    win.Top = bottom - height - MARGIN_BOTTOM
    return host


def start(config, logger=None):
    """Opens the HUD (or refreshes the open one). config: {'sum_property': 'Cat > Prop'
    or ''}. Returns True when the HUD is showing."""
    from namo import propindex, ui
    holder = _holder()
    holder.config = dict(config or {})
    if is_running():
        refresh()
        return True
    stop()
    from pynavis._api import Application
    from System import TimeSpan
    from System.Windows.Threading import DispatcherPriority, DispatcherTimer
    from PyNavis.Runtime.Forms import FluentChrome
    logger = logger or ui.pinned_logger()
    holder.logger = logger
    win, update = build_window()
    holder.window = win
    holder.update = update
    holder.doc = None
    holder.host = None

    def paint():
        document = Application.ActiveDocument
        if document is None or holder.window is None:
            return
        spec = propindex.split_pair((holder.config or {}).get('sum_property') or '')
        if spec is not None and not spec[0]:
            spec = None
        reader = propindex.Reader(document)
        stats = collect(document, reader, spec)
        holder.update(stats_lines(stats))
    holder.paint = ui.safe(paint, 'Selection HUD update', logger)
    debounce = ui.Debouncer(DEBOUNCE_MS, holder.paint)
    holder.debounce = debounce

    def on_selection(sender, args):
        try:
            debounce.trigger()
        except Exception:
            ui.log_error('Selection HUD selection handler failed', logger)

    def subscribe(document):
        previous = holder.doc
        if previous is document:
            return
        if previous is not None:
            try:
                previous.CurrentSelection.Changed -= holder.on_selection
            except Exception:
                pass
        holder.doc = document
        if document is not None:
            document.CurrentSelection.Changed += holder.on_selection

    def on_document(sender, args):
        try:
            subscribe(Application.ActiveDocument)
            debounce.trigger()
        except Exception:
            ui.log_error('Selection HUD document switch failed', logger)

    def on_tick(sender, args):
        try:
            if holder.window is None:
                return
            host = _place(holder.window)
            holder.host = host
        except Exception:
            ui.log_error('Selection HUD anchor failed', logger)

    def on_size(sender, args):
        on_tick(None, None)

    holder.on_selection = on_selection
    holder.on_document = on_document
    holder.subscribe = subscribe
    timer = DispatcherTimer(DispatcherPriority.Background)
    timer.Interval = TimeSpan.FromMilliseconds(ANCHOR_MS)
    timer.Tick += on_tick
    holder.timer = timer
    holder.on_tick = on_tick

    def on_closed(sender, args):
        # Closed by anything but stop() (Navisworks closing its owned windows, say):
        # drop the subscriptions and the timer too, so no handler outlives the window.
        try:
            if getattr(holder, 'window', None) is win:
                stop()
        except Exception:
            ui.log_error('Selection HUD close failed', logger)
    try:
        Application.ActiveDocumentChanged += on_document
        subscribe(Application.ActiveDocument)
        paint()
        win.SizeChanged += on_size
        win.Closed += on_closed
        FluentChrome.Apply(win)
        ui.non_activating(win)
        _place(win)                 # near its corner before it shows, exact once it has a size
        win.Show()
        _place(win)
        timer.Start()
    except Exception:
        stop()
        raise
    return True


def update_config(changes):
    """Merges changes into the running HUD's settings and repaints it (no-op when the
    HUD is off: the next start reads the saved config)."""
    holder = _holder()
    config = dict(getattr(holder, 'config', None) or {})
    config.update(changes or {})
    holder.config = config
    if is_running():
        refresh()


def refresh():
    """Repaints the open HUD now (after its settings changed)."""
    holder = _holder()
    paint = getattr(holder, 'paint', None)
    if paint is not None:
        paint()


def stop():
    """Closes the HUD and removes every subscription. Safe to call any time."""
    holder = _holder()
    steps = []
    timer = getattr(holder, 'timer', None)
    if timer is not None:
        steps.append(lambda: timer.Stop())
        steps.append(lambda: _unhook_tick(timer, holder))
    debounce = getattr(holder, 'debounce', None)
    if debounce is not None:
        steps.append(lambda: debounce.cancel())
    document = getattr(holder, 'doc', None)
    if document is not None and getattr(holder, 'on_selection', None) is not None:
        steps.append(lambda: _unhook_selection(document, holder))
    if getattr(holder, 'on_document', None) is not None:
        steps.append(lambda: _unhook_document(holder))
    win = getattr(holder, 'window', None)
    holder.window = None        # start()'s Closed handler then knows stop() itself is closing it
    if win is not None:
        steps.append(lambda: win.Close())
    for step in steps:
        try:
            step()
        except Exception:
            pass
    for name in ('timer', 'debounce', 'doc', 'on_selection', 'on_document', 'window', 'update',
                 'paint', 'subscribe', 'on_tick'):
        setattr(holder, name, None)


def _unhook_tick(timer, holder):
    if getattr(holder, 'on_tick', None) is not None:
        timer.Tick -= holder.on_tick


def _unhook_selection(document, holder):
    document.CurrentSelection.Changed -= holder.on_selection


def _unhook_document(holder):
    from pynavis._api import Application
    Application.ActiveDocumentChanged -= holder.on_document
