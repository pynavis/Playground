# -*- coding: utf-8 -*-
"""Shows everything Navisworks knows about the selected or clicked item in one card."""
from pynavis import output, toast

from namo import data_common, inspect, items, picking, ui


def target(doc):
    """(item, picked point or None, selection count), or (None, None, 0) when there is
    nothing to inspect (already reported) or the pick was cancelled (silent)."""
    selected = items.selected(doc)
    if selected:
        return selected[0], None, len(selected)
    if ui.is_runner():
        toast.info('Nothing selected', 'Select an item: clicking a point needs the Navisworks window.')
        return None, None, 0
    # The click runs on the host's Measure tool, like every shipped pyNavis pick; the
    # point is then resolved to the front-most item under it.
    hit = picking.point('Click the item to inspect', want_item=True, doc=doc)
    if hit is None:
        return None, None, 0                # Esc, right-click or another tool: say nothing
    if hit.item is None:
        toast.info('Nothing under that point', 'Click on model geometry, or select an item first.')
        return None, None, 0
    # A click lands on a geometry leaf (often an unnamed solid); the card is about the
    # element it belongs to, which is where the Revit tabs live.
    return items.object_of(hit.item), hit.point, 1


def run():
    doc = data_common.active_doc()
    if not data_common.has_models(doc):
        data_common.no_model_toast()
        return
    item, picked, count = target(doc)
    if item is None:
        return
    info = inspect.describe(item, doc, picked)
    name = info.get('name') or info.get('class_name') or 'Item'
    output.set_title('What Is It: %s' % name)
    output.print_html(inspect.card_html(info))
    detail = 'Summary copied to the clipboard.'
    if not ui.copy(inspect.summary_text(info)):
        detail = 'The clipboard was busy; the card is in the output window.'
    if count > 1:
        detail = 'First of %s selected items. %s' % ('{:,}'.format(count), detail)
    toast.success('Inspected %s' % name, detail)


run()
