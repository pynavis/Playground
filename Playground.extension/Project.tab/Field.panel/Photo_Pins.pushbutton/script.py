# -*- coding: utf-8 -*-
"""Pins site photos to a point you click in the model, with a caption, the level, grid and object there."""
import os

from pynavis import forms, toast

from namo import camera, config as namo_config, field_photobrowser, fourd_common, items, photopins, picking, ui

TITLE = 'Photo Pins'


def linked_object(hit, doc):
    """(entries, name) of the object under the clicked point, ([], '') when there is none."""
    if hit.item is None:
        return [], ''
    try:
        element = items.object_of(hit.item)
        return items.entries([element], doc), str(element.DisplayName or '') or items.category(element)
    except Exception:
        return [], ''


def ask():
    """(photo files, caption) for the new pin, or None when the user backs out."""
    files = photopins.choose_photos('Photos to pin here')
    if not files:
        return None
    default = os.path.splitext(os.path.basename(files[0]))[0]
    caption = forms.ask_string('Caption for %s:' % fourd_common.plural(len(files), 'photo'), default=default,
                               title=TITLE)
    if caption is None:
        return None
    return files, caption


def run():
    if ui.is_runner():
        toast.info('%s needs a person at the screen' % TITLE, 'Run it from the ribbon.')
        return
    doc = fourd_common.active_doc()
    if not fourd_common.has_models(doc):
        toast.info('No model is open', 'Open or append a model first.')
        return
    hit = picking.point('Click where the photos were taken', want_item=True, doc=doc)
    if hit is None:
        return
    view_camera = camera.capture(doc)
    photopins.preview(hit.point, doc)          # the pin shows where it will land while you choose
    try:
        answer = ask()
    finally:
        photopins.clear_preview()
    if answer is None:
        return
    files, caption = answer
    level, grid = photopins.location_labels(hit.point, doc)
    item_entries, item_name = linked_object(hit, doc)
    record = photopins.new_pin(hit.point, str(doc.Units), [], caption, level, grid, item_entries, item_name,
                               view_camera, namo_config.user_name())
    records = photopins.store(doc)
    try:
        saved = photopins.add_pin(records, record, files, doc)
    except (IOError, OSError, ValueError) as error:
        toast.error('Could not pin the photos', str(error))
        return
    place = ', '.join(p for p in (level, 'grid %s' % grid if grid else '', item_name) if p)
    detail = (place + '. ' if place else '')
    shown = photopins.settings().get('show_pins', True)
    drawn = photopins.refresh(doc)
    browser_open = field_photobrowser.refresh_open(records.list())
    if not shown:
        detail += 'Pins are hidden: Shift+Click Photo Pins to show them.'
    elif not drawn:
        detail += 'The pin is saved but could not be drawn in the view. Photo Browser lists it.'
    elif not browser_open:
        detail += 'Open Photo Browser to see them.'
    if records.note:
        detail = records.note + ' ' + detail
    toast.success('Pinned %s as %s' % (fourd_common.plural(len(saved['photos']), 'photo'), saved['id']),
                  detail.strip() or None)


run()
