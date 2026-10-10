# -*- coding: utf-8 -*-
"""Windows of the Views tools: the hand-order list Batch PDF uses.

build_order(title, labels) returns the unshown window (window.Tag is the state:
.order is the list of indices into labels in their current order, .move(where)
moves the selected row 'top' | 'up' | 'down' | 'bottom', .accepted); order(...) shows
it and returns the order or None when cancelled. Ctrl+Up / Ctrl+Down move the
selected row from the keyboard; Enter is OK and Esc cancels.
"""


def moved(order, value, where):
    """A new order list with value moved 'top' | 'up' | 'down' | 'bottom' (pure)."""
    out = list(order)
    if value not in out:
        return out
    i = out.index(value)
    out.pop(i)
    if where == 'top':
        j = 0
    elif where == 'bottom':
        j = len(out)
    elif where == 'up':
        j = max(0, i - 1)
    else:
        j = min(len(out), i + 1)
    out.insert(j, value)
    return out


def rows_for(order, labels):
    """Table rows: position number and label, valued by the original index."""
    return [{'value': index, 'cells': [position + 1, labels[index]]} for position, index in enumerate(order)]


def build_order(title, labels, prompt=None):
    from namo import ui
    ui.load_wpf()
    from System.Windows.Controls import Dock, DockPanel, Orientation, StackPanel
    from System.Windows.Input import Key, Keyboard, ModifierKeys
    logger = ui.pinned_logger()
    win = ui.window(title, width=600, height=620, resizable=True, min_width=440, min_height=380)
    state = ui.Bag(order=list(range(len(labels))), accepted=False)
    table = ui.Table(['#', 'Viewpoint'], rows_for(state.order, labels), checkboxes=False,
                     multiselect=False, show_headers=False, logger=logger)
    state.table = table

    def move(where):
        selected = table.selected_values()
        if not selected:
            return
        value = selected[0]
        state.order = moved(state.order, value, where)
        table.update(rows_for(state.order, labels))
        table.select_values([value])
        try:
            table.grid.ScrollIntoView(table.grid.SelectedItem)
        except Exception:
            pass
    state.move = move

    def accept():
        state.accepted = True
        ui.close_with(win, True)

    side = StackPanel()
    side.Orientation = Orientation.Vertical
    side.Margin = ui.thickness(8, 0, 0, 0)
    for label, where in (('Top', 'top'), ('Up', 'up'), ('Down', 'down'), ('Bottom', 'bottom')):
        control = ui.button(label, (lambda w: lambda: move(w))(where), 'secondary', logger)
        control.Margin = ui.thickness(0, 0, 0, 8)
        side.Children.Add(control)

    body = DockPanel()
    body.Margin = ui.thickness(16, 16, 16, 12)
    lead = ui.text(prompt or 'Select a viewpoint and move it. The PDF follows this order.')
    lead.Margin = ui.thickness(0, 0, 0, 12)
    DockPanel.SetDock(lead, Dock.Top)
    body.Children.Add(lead)
    DockPanel.SetDock(side, Dock.Right)
    body.Children.Add(side)
    body.Children.Add(table.element)

    ok_button = ui.button('OK', accept, 'primary', logger)
    ok_button.IsDefault = True
    cancel_button = ui.button('Cancel', lambda: ui.close_with(win, False), 'secondary', logger)
    cancel_button.IsCancel = True
    bar = ui.footer([ok_button, cancel_button], left=ui.hint('Ctrl+Up and Ctrl+Down move the selected row.'),
                    padding=16)

    layout = DockPanel()
    DockPanel.SetDock(bar, Dock.Bottom)
    layout.Children.Add(bar)
    layout.Children.Add(body)
    win.Content = layout

    def keys(sender, args):
        if Keyboard.Modifiers == ModifierKeys.Control and args.Key in (Key.Up, Key.Down):
            move('up' if args.Key == Key.Up else 'down')
            args.Handled = True
    win.PreviewKeyDown += ui.safe(keys, 'order keys', logger)
    win.ContentRendered += ui.safe(lambda s, e: table.focus_first(), 'order focus', logger)
    win.Tag = state
    return win


def order(title, labels, prompt=None):
    """Shows the order window; returns the indices of labels in the chosen order,
    or None when cancelled."""
    from namo import ui
    win = build_order(title, labels, prompt)
    ui.show_modal(win)
    state = win.Tag
    return list(state.order) if state.accepted else None
