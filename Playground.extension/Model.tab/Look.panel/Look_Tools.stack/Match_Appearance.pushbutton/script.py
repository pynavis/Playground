"""Copies the look of the first selected item to the rest of the selection, or to each object clicked next."""
from namo import colorize, items, look_tools, picking, ui
from pynavis import doc as nwdoc
from pynavis import toast

TITLE = 'Match Appearance'


def source_look(document, source):
    """(hex, transparency, how) to paint with, or None on cancel. When Navisworks
    reports only part of the look (or none), a small form asks for the rest."""
    hex_value, transparency, how = look_tools.read_appearance(source, document)
    if hex_value is not None and transparency is not None:
        return hex_value, transparency, how
    answer = ui.form(TITLE, look_tools.match_fields(source.DisplayName or 'the source', hex_value, transparency),
                     ok='Paint')
    if answer is None:
        return None
    return answer['hex'], answer['transparency'] / 100.0, 'chosen'


def pick_source(document):
    """The object under a click, or None (cancelled, or nothing there: said)."""
    hit = picking.point('Click the object to copy the look from', want_item=True, doc=document)
    if hit is None:
        return None
    if hit.item is None:
        toast.info('Nothing under that point', 'Click on an object, or select the source object first.')
        return None
    return items.object_of(hit.item)


def paint_clicks(document, source, hex_value, transparency, how):
    """Paints each clicked object until Esc; each click is its own undo step."""
    painted = 0
    look = look_tools.appearance_text(hex_value, transparency)
    name = source.DisplayName or 'the source'
    note = ''
    while True:
        hit = picking.point(look_tools.click_prompt(look, painted, note), want_item=True, doc=document)
        if hit is None:
            break
        if hit.item is None:
            note = 'Nothing under that point.'
            continue
        target = items.object_of(hit.item)
        if target.Equals(source):
            note = 'That is the source object.'
            continue
        look_tools.paint_like([target], hex_value, transparency, document)
        painted += 1
        note = ''
    if painted:                             # Esc before any click is a cancel: say nothing
        toast.success('Painted %s like %s' % (colorize.plural(painted, 'object'), name),
                      look_tools.look_detail(look, how))


def run():
    document = nwdoc.get_doc()
    if document.Models.Count == 0:
        toast.info('No model open', 'Open a model, then run Match Appearance again.')
        return
    selected = items.selected(document)
    source = selected[0] if selected else pick_source(document)
    if source is None:
        return
    look = source_look(document, source)
    if look is None:
        return
    hex_value, transparency, how = look
    targets = [item for item in selected[1:] if not item.Equals(source)]
    if targets:
        count = look_tools.paint_like(targets, hex_value, transparency, document)
        toast.success('Painted %s like %s' % (colorize.plural(count, 'item'), source.DisplayName or 'the source'),
                      look_tools.look_detail(look_tools.appearance_text(hex_value, transparency), how))
        return
    paint_clicks(document, source, hex_value, transparency, how)


run()
