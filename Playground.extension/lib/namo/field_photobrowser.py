# -*- coding: utf-8 -*-
"""Photo Browser: a modeless window of photo-pin thumbnails grouped by level, grid or
linked object, with a filter, Go to, Open photo, Delete pin and an HTML photo report.

One card per photo (a pin with three photos shows three cards). Click selects (neutral
wash plus the accent selection rail), double-click or Enter goes to the pin, Left and
Right move between cards, Delete removes the pin after a confirmation, Ctrl+F filters.
Thumbnails are JPEGs cached beside the photo copies (photopins.thumbnail) and loaded
with BitmapCacheOption.OnLoad so no file stays locked.
"""

import os

KEY = 'playground-photo-browser'
MAX_CARDS = 400
CARD_WIDTH = 184.0
THUMB_W = 168.0
THUMB_H = 112.0


def _wpf():
    """Loads the WPF assemblies so System.Windows names import (namo.ui does the same)."""
    import clr
    for name in ('PresentationFramework', 'PresentationCore', 'WindowsBase'):
        clr.AddReference(name)


def card_entries(pins, group_by, query, limit=MAX_CARDS):
    """Pure: ([(group label, [(pin, photo)])], shown, total) after filtering."""
    from namo import photopins
    groups = photopins.group_pins(photopins.filter_pins(pins, query), group_by)
    out = []
    shown = total = 0
    for label, members in groups:
        cards = []
        for pin in members:
            for photo in pin.get('photos') or [{'file': '', 'taken': ''}]:
                total += 1
                if shown < limit:
                    cards.append((pin, photo))
                    shown += 1
        if cards:
            out.append((label, cards))
    return out, shown, total


def status_text(pins, shown, total):
    from namo import fourd_common
    if not pins:
        return 'No photo pins yet. Use Photo Pins to add some.'
    text = '%s, %s' % (fourd_common.plural(len(pins), 'pin'), fourd_common.plural(total, 'photo'))
    if shown < total:
        text += '; showing the first %s, filter to narrow' % '{:,}'.format(shown)
    return text + '.'


class Browser(object):
    """The window's state and handlers (window.Tag)."""

    def __init__(self, doc, records, pins, logger=None):
        from namo import ui
        self.ui = ui
        self.doc = doc
        self.records = records
        self.doc_path = _doc_path(doc)    # the model these pins belong to
        self.pins = list(pins)
        self.group_by = 'level'
        self.query = ''
        self.selected = None          # (pin id, file)
        self.cards = []               # [(key, rail, border)] in display order
        self.logger = logger or ui.pinned_logger()
        self.palette = ui.palette()
        self.window = None
        self.body = None
        self.status = None

    # ---- building ----

    def build(self):
        ui = self.ui
        _wpf()
        from System.Windows import Thickness, VerticalAlignment
        from System.Windows.Controls import Dock, DockPanel, ScrollViewer, ScrollBarVisibility, StackPanel
        from namo import photopins
        win = ui.window('Photo browser', width=920, height=680, min_width=520, min_height=360)
        top = DockPanel()
        top.Margin = Thickness(16, 16, 16, 8)
        group = ui.combo([(label, value) for value, label in photopins.GROUPS], selected=self.group_by,
                         width=170)
        group.Margin = Thickness(8, 0, 0, 0)
        DockPanel.SetDock(group, Dock.Right)
        top.Children.Add(group)
        label = ui.text('Group by', muted=True, wrap=False)
        label.Margin = Thickness(12, 0, 0, 0)
        label.VerticalAlignment = VerticalAlignment.Center
        DockPanel.SetDock(label, Dock.Right)
        top.Children.Add(label)
        search, self.search_box = ui.search_box('Filter by caption, pin, level, grid or file', self.on_filter)
        top.Children.Add(search)
        group.SelectionChanged += ui.safe(lambda s, e: self.on_group(ui.combo_value(group)), 'group', self.logger)
        self.body = StackPanel()
        self.body.Margin = Thickness(16, 0, 8, 8)
        viewer = ScrollViewer()
        viewer.Content = self.body
        viewer.VerticalScrollBarVisibility = ScrollBarVisibility.Auto
        viewer.HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled
        self.viewer = viewer
        self.status = ui.hint('')
        self.go_button = ui.button('Go to', self.go_to, 'primary', self.logger)
        self.open_button = ui.button('Open photo', self.open_photo, 'secondary', self.logger)
        self.delete_button = ui.button('Delete pin', self.delete_pin, 'secondary', self.logger)
        report = ui.button('Export report', self.export_report, 'secondary', self.logger)
        close = ui.button('Close', lambda: win.Close(), 'secondary', self.logger)
        close.IsCancel = True
        bar = ui.footer([self.go_button, self.open_button, self.delete_button, report, close], left=self.status,
                        padding=16)
        layout = DockPanel()
        DockPanel.SetDock(bar, Dock.Bottom)
        layout.Children.Add(bar)
        DockPanel.SetDock(top, Dock.Top)
        layout.Children.Add(top)
        layout.Children.Add(viewer)
        win.Content = layout
        win.Tag = self
        win.PreviewKeyDown += ui.safe(self.on_key, 'keys', self.logger)
        self.window = win
        self.refresh()
        return win

    def refresh(self):
        ui = self.ui
        from System.Windows import Thickness
        from System.Windows.Controls import WrapPanel
        self.body.Children.Clear()
        self.cards = []
        groups, shown, total = card_entries(self.pins, self.group_by, self.query)
        for label, cards in groups:
            heading = ui.heading('%s  (%d)' % (label, len(cards)))
            heading.Margin = Thickness(0, 12, 0, 8)
            self.body.Children.Add(heading)
            wrap = WrapPanel()
            for pin, photo in cards:
                wrap.Children.Add(self._card(pin, photo))
            self.body.Children.Add(wrap)
        if not groups:
            empty = ui.text('No photo matches the filter.' if self.pins else
                            'No photo pins yet. Use Photo Pins to pin site photos to the model.', muted=True)
            empty.Margin = Thickness(0, 24, 0, 0)
            self.body.Children.Add(empty)
        self.status.Text = status_text(self.pins, shown, total)
        keys = [c[0] for c in self.cards]
        if self.selected not in keys:
            self.selected = keys[0] if keys else None
        self._paint_selection()

    def _card(self, pin, photo):
        ui = self.ui
        from System.Windows import (CornerRadius, GridLength, GridUnitType, HorizontalAlignment,
                                    TextTrimming, Thickness, VerticalAlignment)
        from System.Windows.Controls import Border, ColumnDefinition, Grid, Image, StackPanel
        from System.Windows.Media import Stretch
        from namo import photopins
        key = (pin['id'], photo.get('file', ''))
        outer = Grid()
        outer.Width = CARD_WIDTH
        outer.Margin = Thickness(0, 0, 8, 8)
        for width in (3.0, None):
            column = ColumnDefinition()
            column.Width = GridLength(width) if width else GridLength(1, GridUnitType.Star)
            outer.ColumnDefinitions.Add(column)
        rail = Border()
        rail.CornerRadius = CornerRadius(2)
        Grid.SetColumn(rail, 0)
        outer.Children.Add(rail)
        border = Border()
        border.CornerRadius = CornerRadius(4)
        border.BorderThickness = Thickness(1)
        border.Padding = Thickness(6)
        border.Margin = Thickness(2, 0, 0, 0)
        Grid.SetColumn(border, 1)
        stack = StackPanel()
        image_path = None
        if photo.get('file'):
            image_path = photopins.thumbnail(self.records, pin, photo, self.doc)
        source = _bitmap(image_path) if image_path else None
        if source is not None:
            image = Image()
            image.Source = source
            image.Width = THUMB_W
            image.Height = THUMB_H
            image.Stretch = Stretch.UniformToFill
            stack.Children.Add(image)
        else:
            holder = Border()
            holder.Width = THUMB_W
            holder.Height = THUMB_H
            holder.Background = ui.brush(self.palette['surface'])
            note = ui.text('No preview', 12, muted=True, wrap=False)
            note.HorizontalAlignment = HorizontalAlignment.Center
            note.VerticalAlignment = VerticalAlignment.Center
            holder.Child = note
            stack.Children.Add(holder)
        caption = ui.text(pin.get('caption') or pin['id'], bold=True, wrap=False)
        caption.TextTrimming = TextTrimming.CharacterEllipsis
        caption.Margin = Thickness(0, 6, 0, 0)
        stack.Children.Add(caption)
        stack.Children.Add(ui.text('%s  %s' % (pin['id'], photopins.taken_text(photo)), 12, muted=True, wrap=False))
        border.Child = stack
        outer.Children.Add(border)
        outer.ToolTip = '%s\n%s' % (photo.get('file', ''), ', '.join(p for p in (pin.get('level'), pin.get('grid'),
                                                                                pin.get('item_name')) if p))

        def down(sender, args):
            self.select(key)
            if args.ClickCount == 2:
                self.go_to()
            args.Handled = True
        outer.MouseLeftButtonDown += ui.safe(down, 'card click', self.logger)
        self.cards.append((key, rail, border))
        return outer

    # ---- selection ----

    def _paint_selection(self):
        ui = self.ui
        for key, rail, border in self.cards:
            chosen = key == self.selected
            rail.Background = ui.brush(self.palette['accent'] if chosen else self.palette['paper'])
            border.Background = ui.brush(self.palette['selection'] if chosen else self.palette['paper'])
            border.BorderBrush = ui.brush(self.palette['line_strong'] if chosen else self.palette['line'])
        has = self.selected is not None
        for control in (self.go_button, self.open_button, self.delete_button):
            control.IsEnabled = has

    def select(self, key):
        self.selected = key
        self._paint_selection()

    def move(self, step):
        keys = [c[0] for c in self.cards]
        if not keys:
            return
        index = keys.index(self.selected) if self.selected in keys else 0
        self.select(keys[max(0, min(len(keys) - 1, index + step))])

    def current(self):
        """(pin, photo) of the selected card, or (None, None)."""
        if self.selected is None:
            return None, None
        for pin in self.pins:
            if pin['id'] == self.selected[0]:
                for photo in pin.get('photos') or []:
                    if photo.get('file') == self.selected[1]:
                        return pin, photo
                return pin, None
        return None, None

    # ---- handlers ----

    def on_filter(self, text):
        self.query = text or ''
        self.refresh()

    def on_group(self, value):
        self.group_by = value or 'level'
        self.refresh()

    def on_key(self, sender, args):
        from System.Windows.Input import Key, Keyboard, ModifierKeys
        if args.Key == Key.F and Keyboard.Modifiers == ModifierKeys.Control:
            self.search_box.Focus()
            self.search_box.SelectAll()
            args.Handled = True
        elif self.search_box.IsKeyboardFocused:
            return
        elif args.Key == Key.Enter:
            self.go_to()
            args.Handled = True
        elif args.Key == Key.Delete:
            self.delete_pin()
            args.Handled = True
        elif args.Key in (Key.Right, Key.Down):
            self.move(1)
            args.Handled = True
        elif args.Key in (Key.Left, Key.Up):
            self.move(-1)
            args.Handled = True

    def same_model(self):
        """False (with a toast) when another model was opened since the browser was."""
        from pynavis import toast
        if _doc_path(self.doc) == self.doc_path:
            return True
        toast.info('These photos belong to another model', 'Close this window and open Photo Browser again.')
        return False

    def go_to(self):
        from pynavis import toast
        from namo import photopins
        pin, _photo = self.current()
        if pin is None or not self.same_model():
            return
        if photopins.go_to(pin, self.doc):
            toast.success('Went to %s' % pin['id'], pin.get('caption') or '')
        else:
            toast.warning('Could not move the view to %s' % pin['id'],
                          'The pin has no saved camera and its point could not be framed.')

    def open_photo(self):
        from pynavis import toast
        from namo import fourd_common, photopins
        pin, photo = self.current()
        if photo is None:
            return
        path = photopins.photo_path(self.records, pin, photo, self.doc)
        if not os.path.exists(path):
            toast.error('The photo is missing', path)
            return
        if not fourd_common.open_file(path):
            toast.error('Windows could not open the photo', path)

    def delete_pin(self):
        from pynavis import forms, toast
        from namo import photopins
        pin, _photo = self.current()
        if pin is None or not self.same_model():
            return
        count = len(pin.get('photos') or [])
        if not forms.confirm('Delete pin %s and its %d photo %s? The original files are not touched.'
                             % (pin['id'], count, 'copy' if count == 1 else 'copies'), title='Photo browser'):
            return
        try:
            photopins.delete_pin(self.records, pin, self.doc)
        except (IOError, OSError) as error:
            toast.error('Could not delete pin %s' % pin['id'], str(error))
            return
        self.pins = [p for p in self.pins if p['id'] != pin['id']]
        photopins.refresh(self.doc)
        self.selected = None
        self.refresh()
        toast.success('Deleted pin %s' % pin['id'])

    def export_report(self):
        from pynavis import toast
        from namo import config as namo_config, fourd_common, photopins
        pins = photopins.filter_pins(self.pins, self.query)
        if not pins:
            toast.info('No photos to report', 'Clear the filter or pin some photos first.')
            return
        path = fourd_common.ask_save(self.doc, 'Photo report', 'html', 'Export the photo report')
        if path is None:
            return
        thumbs = {}
        for pin in pins:
            for photo in pin.get('photos') or []:
                image = photopins.thumbnail(self.records, pin, photo, self.doc)
                if image:
                    thumbs[(pin['id'], photo['file'])] = image
        report = photopins.report_html(pins, 'Site photos', self.group_by, thumbs,
                                       fourd_common.doc_title(self.doc), namo_config.user_name())
        try:
            report.save(path)
        except (IOError, OSError) as error:
            toast.error('Could not write the report', str(error))
            return
        toast.success('Exported the photo report', path)
        fourd_common.open_file(path)


def _doc_path(doc):
    from namo import fourd_common
    return fourd_common.doc_path(doc)


def _bitmap(path):
    """A frozen BitmapImage read fully into memory (no file lock), or None."""
    try:
        _wpf()
        from System import Uri, UriKind
        from System.Windows.Media.Imaging import BitmapCacheOption, BitmapImage
        image = BitmapImage()
        image.BeginInit()
        image.CacheOption = BitmapCacheOption.OnLoad
        image.DecodePixelWidth = int(THUMB_W * 2)
        image.UriSource = Uri(os.path.abspath(path), UriKind.Absolute)
        image.EndInit()
        image.Freeze()
        return image
    except Exception:
        return None


def build(doc, records, pins):
    """The unshown window (smoke tests build this)."""
    return Browser(doc, records, pins).build()


def show(doc, records, pins):
    from namo import ui
    ui.Modeless.close(KEY)
    return ui.Modeless(KEY, 'Photo browser', None, window_factory=lambda: build(doc, records, pins)).show()


def refresh_open(pins):
    """Shows a new list of pins in the browser when it is open (Photo Pins calls this
    after adding one). Never raises; False when no browser is open."""
    try:
        from namo import ui
        win = ui.Modeless.get(KEY)
        browser = win.Tag if win is not None else None
        if not isinstance(browser, Browser):
            return False
        browser.pins = list(pins)
        browser.refresh()
        return True
    except Exception:
        return False
