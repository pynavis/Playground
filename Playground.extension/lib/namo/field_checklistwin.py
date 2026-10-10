# -*- coding: utf-8 -*-
"""Field Checklists window: the checklist of one saved viewpoint at a time.

Top: the viewpoint (every saved viewpoint, with its checklist progress), Previous and
Next (which also move the model view there). Middle: the items by section, each with a
Pass / Fail / N/A choice and a note; a viewpoint without a checklist offers the
templates and an Attach button instead. Bottom: inspector, date, Sign off, Report, Save.
Changes are saved when you press Save, move to another viewpoint or close the window.
Modeless; every handler is wrapped with ui.safe and uses the objects pinned at open.
"""

import datetime
import os

KEY = 'playground-field-checklists'


def _wpf():
    """Loads the WPF assemblies so System.Windows names import (namo.ui does the same)."""
    import clr
    for name in ('PresentationFramework', 'PresentationCore', 'WindowsBase'):
        clr.AddReference(name)


def viewpoint_label(view, record):
    from namo import checklists
    if record is None:
        return view['path']
    p = checklists.progress(record)
    mark = ', signed' if p['signed'] else ''
    return '%s  (%d/%d%s)' % (view['path'], p['answered'], p['total'], mark)


def start_index(views, current_guid, records_by_id):
    """The viewpoint to open on: the current one, else the first with a checklist, else 0."""
    guids = [v['guid'] for v in views]
    if current_guid in guids:
        return guids.index(current_guid)
    for index, view in enumerate(views):
        if view['guid'] in records_by_id:
            return index
    return 0


class ChecklistWindow(object):

    def __init__(self, doc, records, views, templates, current_guid=None, user=''):
        from namo import ui
        self.ui = ui
        self.doc = doc
        self.records = records
        self.views = list(views)
        self.templates = templates
        self.user = user
        self.by_id = dict((r['id'], r) for r in records.list())
        self.index = start_index(self.views, current_guid, self.by_id)
        self.record = None
        self.dirty = False
        self.loading = False
        self.logger = ui.pinned_logger()
        self.window = None

    # ---- building ----

    def build(self):
        ui = self.ui
        _wpf()
        from System.Windows import Thickness, VerticalAlignment
        from System.Windows.Controls import (ColumnDefinition, Dock, DockPanel, Grid, Orientation,
                                             ScrollBarVisibility, ScrollViewer, StackPanel)
        from System.Windows import GridLength, GridUnitType
        win = ui.window('Field checklists', width=780, height=720, min_width=560, min_height=420)
        top = Grid()
        top.Margin = Thickness(24, 20, 24, 4)
        for width in ('star', 8.0, 'auto', 8.0, 'auto'):
            column = ColumnDefinition()
            column.Width = _length(width, GridLength, GridUnitType)
            top.ColumnDefinitions.Add(column)
        self.combo = ui.combo([(viewpoint_label(v, self.by_id.get(v['guid'])), i) for i, v in enumerate(self.views)],
                              selected=self.index)
        Grid.SetColumn(self.combo, 0)
        top.Children.Add(self.combo)
        previous = ui.button('Previous', lambda: self.step(-1), 'secondary', self.logger)
        Grid.SetColumn(previous, 2)
        top.Children.Add(previous)
        following = ui.button('Next', lambda: self.step(1), 'secondary', self.logger)
        Grid.SetColumn(following, 4)
        top.Children.Add(following)
        self.combo.SelectionChanged += ui.safe(lambda s, e: self.on_pick(), 'viewpoint', self.logger)
        self.info = ui.text('', 12, muted=True)
        self.info.Margin = Thickness(24, 4, 24, 8)
        self.body = StackPanel()
        self.body.Margin = Thickness(24, 4, 24, 16)
        viewer = ScrollViewer()
        viewer.Content = self.body
        viewer.VerticalScrollBarVisibility = ScrollBarVisibility.Auto
        viewer.HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled
        left = StackPanel()
        left.Orientation = Orientation.Horizontal
        inspector_shell, self.inspector = ui.text_box('', placeholder='Inspector')
        inspector_shell.Width = 150.0
        date_shell, self.date = ui.text_box('', placeholder='YYYY-MM-DD')
        date_shell.Width = 110.0
        date_shell.Margin = Thickness(8, 0, 0, 0)
        self.signed = ui.check('Signed off')
        self.signed.Margin = Thickness(12, 0, 0, 0)
        self.signed.VerticalAlignment = VerticalAlignment.Center
        for element in (inspector_shell, date_shell, self.signed):
            left.Children.Add(element)
        self.inspector.TextChanged += ui.safe(lambda s, e: self.touch(), 'inspector', self.logger)
        self.date.TextChanged += ui.safe(lambda s, e: self.touch(), 'date', self.logger)
        self.signed.Click += ui.safe(lambda s, e: self.touch(), 'sign', self.logger)
        report = ui.button('Report', self.report, 'secondary', self.logger)
        save = ui.button('Save', self.save, 'primary', self.logger)
        close = ui.button('Close', lambda: win.Close(), 'secondary', self.logger)
        close.IsCancel = True
        bar = ui.footer([report, save, close], left=left, padding=16)
        layout = DockPanel()
        DockPanel.SetDock(bar, Dock.Bottom)
        layout.Children.Add(bar)
        header = StackPanel()
        header.Children.Add(top)
        header.Children.Add(self.info)
        header.Children.Add(ui.separator((24, 0, 24, 0)))
        DockPanel.SetDock(header, Dock.Top)
        layout.Children.Add(header)
        layout.Children.Add(viewer)
        win.Content = layout
        win.Tag = self
        win.Closing += ui.safe(lambda s, e: self.save(quiet=True), 'closing', self.logger)
        self.window = win
        self.load(self.index, recall=False)
        return win

    # ---- loading ----

    def load(self, index, recall=True):
        from namo import camera, checklists
        self.loading = True
        try:
            self.index = index
            view = self.views[index] if self.views else None
            stored = self.by_id.get(view['guid']) if view else None
            self.record = None if stored is None else _copy(stored)
            grown = 0
            if self.record is not None and view is not None:
                self.record['viewpoint'], self.record['folder'] = view['name'], view['folder']
                template = self.templates.get(self.record.get('template'))
                if template is not None:
                    try:
                        grown = checklists.merge_template(self.record, template)
                    except ValueError:
                        grown = 0
            self.body.Children.Clear()
            if view is None:
                self.body.Children.Add(self.ui.text('This model has no saved viewpoints.', muted=True))
            elif self.record is None:
                self._attach_panel(view)
            else:
                self._items_panel()
            self.inspector.Text = (self.record or {}).get('inspector') or (self.user if self.record else '')
            self.date.Text = (self.record or {}).get('date') or (
                datetime.date.today().strftime('%Y-%m-%d') if self.record else '')
            self.signed.IsChecked = bool((self.record or {}).get('signed_off'))
            for control in (self.inspector, self.date, self.signed):
                control.IsEnabled = self.record is not None
            self.dirty = bool(grown)            # template items added since: save them with the rest
            self._update_info()
            if recall and view is not None:
                try:
                    camera.recall(view['saved'], self.doc)
                except Exception as error:
                    self.ui.log_error('could not recall %s: %s' % (view['path'], error), self.logger)
                    from pynavis import toast
                    toast.warning('Could not move the view to %s' % view['name'],
                                  'The viewpoint may have been deleted or moved. Close this window and '
                                  'open Field Checklists again.')
        finally:
            self.loading = False

    def _attach_panel(self, view):
        ui = self.ui
        from System.Windows import Thickness
        from System.Windows.Controls import Orientation, StackPanel
        self.body.Children.Add(ui.text('No checklist on %s yet.' % view['path'], 15, bold=True))
        hint = ui.hint('Pick a template to attach. Teams add their own with Shift+Click on Field Checklists.')
        hint.Margin = Thickness(0, 4, 0, 12)
        self.body.Children.Add(hint)
        row = StackPanel()
        row.Orientation = Orientation.Horizontal
        names = sorted(self.templates)
        picker = ui.combo(names, selected=names[0] if names else None, width=260)
        attach = ui.button('Attach checklist', lambda: self.attach(ui.combo_value(picker)), 'secondary', self.logger)
        attach.Margin = Thickness(8, 0, 0, 0)
        row.Children.Add(picker)
        row.Children.Add(attach)
        self.body.Children.Add(row)

    def _items_panel(self):
        ui = self.ui
        from System.Windows import GridLength, GridUnitType, Thickness, VerticalAlignment
        from System.Windows.Controls import ColumnDefinition, Grid, RowDefinition
        from namo import checklists
        section = None
        for item in self.record['items']:
            if item.get('section', '') != section:
                section = item.get('section', '')
                if section:
                    heading = ui.heading(section)
                    heading.Margin = Thickness(0, 16, 0, 6)
                    self.body.Children.Add(heading)
            grid = Grid()
            grid.Margin = Thickness(0, 4, 0, 8)
            for width in ('star', 12.0, 'auto'):
                column = ColumnDefinition()
                column.Width = _length(width, GridLength, GridUnitType)
                grid.ColumnDefinitions.Add(column)
            for _ in range(2):
                grid.RowDefinitions.Add(RowDefinition())
            label = ui.text(item['text'])
            label.VerticalAlignment = VerticalAlignment.Center
            grid.Children.Add(label)
            options = [(checklists.RESULT_LABELS[r], r) for r in checklists.RESULTS]
            panel, buttons = ui.radio_group(options, selected=item.get('result') or '__none__', inline=True,
                                            group='chk_%s_%s' % (self.index, item['id']))
            Grid.SetColumn(panel, 2)
            grid.Children.Add(panel)
            for button, (_label, value) in zip(buttons, options):
                button.Checked += ui.safe(self._on_result(item['id'], value), 'result', self.logger)
            shell, box = ui.text_box(item.get('note') or '', placeholder='Note')
            shell.Margin = Thickness(0, 6, 0, 0)
            Grid.SetRow(shell, 1)
            Grid.SetColumnSpan(shell, 3)
            grid.Children.Add(shell)
            box.TextChanged += ui.safe(self._on_note(item['id'], box), 'note', self.logger)
            self.body.Children.Add(grid)

    def _on_result(self, item_id, value):
        def handler(sender, args):
            if self.loading or self.record is None:
                return
            from namo import checklists
            checklists.set_result(self.record, item_id, value)
            self.touch()
        return handler

    def _on_note(self, item_id, box):
        def handler(sender, args):
            if self.loading or self.record is None:
                return
            from namo import checklists
            checklists.set_result(self.record, item_id, note=box.Text)
            self.touch()
        return handler

    # ---- actions ----

    def touch(self):
        if self.loading:
            return
        self.dirty = True
        self._update_info()

    def _update_info(self, saved=False):
        from namo import checklists
        if not self.views:
            self.info.Text = ''
            return
        if self.record is None:
            self.info.Text = 'No checklist attached.'
            return
        text = '%s. %s.' % (self.record.get('template') or 'Checklist', checklists.progress_text(self.record))
        if self.dirty:
            text += ' Not saved yet.'
        elif saved:
            text += ' Saved.'
        self.info.Text = text

    def attach(self, name):
        from pynavis import toast
        from namo import checklists
        if not name or name not in self.templates:
            return
        view = self.views[self.index]
        try:
            self.record = checklists.new_checklist(view['guid'], view['name'], view['folder'], name,
                                                   self.templates[name])
        except ValueError as error:
            toast.error('The template has no items', str(error))
            return
        self.record['inspector'] = self.user
        self.record['date'] = datetime.date.today().strftime('%Y-%m-%d')
        self._store()
        self.load(self.index, recall=False)
        toast.success('Attached %s' % name, view['path'])

    def save(self, quiet=False):
        from pynavis import toast
        from namo import checklists
        if self.record is None or (not self.dirty and quiet):
            return True
        self.record['inspector'] = self.inspector.Text.strip()
        self.record['date'] = self.date.Text.strip()
        wants = bool(self.signed.IsChecked)
        if wants and not self.record.get('signed_off'):
            try:
                checklists.sign_off(self.record, self.record['inspector'])
            except ValueError as error:
                self.signed.IsChecked = False
                if not quiet:
                    toast.info('Not signed off', str(error))
        elif not wants and self.record.get('signed_off'):
            checklists.sign_off(self.record, '', on=False)
        try:
            self._store()
        except (IOError, OSError) as error:
            toast.error('Could not save the checklist', str(error))
            return False
        self.dirty = False
        self._update_info(saved=True)
        if not quiet:
            toast.success('Saved the checklist', '%s: %s' % (self.views[self.index]['path'],
                                                             checklists.progress_text(self.record)))
        return True

    def _store(self):
        saved = self.records.put(_copy(self.record))
        self.by_id[saved['id']] = _copy(saved)
        self._relabel()

    def _relabel(self):
        try:
            current = self.combo.SelectedIndex
            self.loading = True
            for index, view in enumerate(self.views):
                self.combo.Items[index] = viewpoint_label(view, self.by_id.get(view['guid']))
            self.combo.SelectedIndex = current
        finally:
            self.loading = False

    def on_pick(self):
        if self.loading:
            return
        index = self.combo.SelectedIndex
        if index < 0 or index == self.index:
            return
        self.save(quiet=True)
        self.load(index)

    def step(self, offset):
        if not self.views:
            return
        target = max(0, min(len(self.views) - 1, self.index + offset))
        if target == self.index:
            return
        self.save(quiet=True)
        self.loading = True
        try:
            self.combo.SelectedIndex = target
        finally:
            self.loading = False
        self.load(target)

    def report(self):
        from pynavis import toast
        from namo import checklists, config as namo_config, fourd_common
        self.save(quiet=True)
        records = list(self.by_id.values())
        if not records:
            toast.info('No checklists yet', 'Attach a checklist to a viewpoint first.')
            return
        path = fourd_common.ask_save(self.doc, 'Field checklists', 'html', 'Export the checklist report')
        if path is None:
            return
        xlsx_path = path[:-5] + '.xlsx'
        try:
            checklists.build_report(records, 'Field checklists', fourd_common.doc_title(self.doc),
                                    namo_config.user_name()).save(path)
            checklists.write_xlsx(xlsx_path, records, 'Field checklists', namo_config.user_name())
        except (IOError, OSError) as error:
            toast.error('Could not write the report', 'Close it in Excel, then try again. %s' % error)
            return
        t = checklists.totals(records)
        toast.success('Exported %s, %d%% complete' % (fourd_common.plural(t['checklists'], 'checklist'), t['percent']),
                      'HTML and Excel in %s' % os.path.dirname(path))
        fourd_common.open_file(path)


def _length(width, GridLength, GridUnitType):
    if width == 'star':
        return GridLength(1, GridUnitType.Star)
    if width == 'auto':
        return GridLength.Auto
    return GridLength(float(width))


def _copy(record):
    import copy
    return copy.deepcopy(record)


def build(doc, records, views, templates, current_guid=None, user=''):
    return ChecklistWindow(doc, records, views, templates, current_guid, user).build()


def show(doc, records, views, templates, current_guid=None, user=''):
    from namo import ui
    existing = ui.Modeless.get(KEY)
    if existing is not None:
        ui.Modeless.close(KEY)
    return ui.Modeless(KEY, 'Field checklists', None,
                       window_factory=lambda: build(doc, records, views, templates, current_guid, user)).show()
