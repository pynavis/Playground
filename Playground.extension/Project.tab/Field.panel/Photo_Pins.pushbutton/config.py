# -*- coding: utf-8 -*-
"""Shows or hides the photo pins in the view and picks their size and what their labels say."""
from pynavis import toast

from namo import fourd_common, photopins, ui


def run():
    if ui.is_runner():
        return
    values = photopins.settings()
    fields = [
        {'kind': 'check', 'key': 'show_pins', 'label': 'Show photo pins in the view',
         'default': bool(values.get('show_pins', True)),
         'hint': 'Pins are redrawn whenever a model with pins opens.'},
        {'kind': 'radio', 'key': 'label', 'label': 'Pin labels show', 'inline': True,
         'options': [('Caption', 'caption'), ('Pin number', 'id')], 'default': values.get('label', 'caption'), 'fallback': 'caption'},
        {'kind': 'radio', 'key': 'size', 'label': 'Pin size', 'inline': True,
         'options': [(label, key) for key, label, _metres in photopins.PIN_SIZES],
         'default': values.get('size', 'medium'), 'fallback': 'medium',
         'hint': 'The marker is 0.2 m across when small, 0.4 m medium, 1 m large.'},
    ]
    answer = ui.form('Photo Pins settings', fields, ok='Save')
    if answer is None:
        return
    photopins.save_settings({'show_pins': bool(answer['show_pins']), 'label': answer['label'],
                             'size': answer['size']})
    doc = fourd_common.active_doc()
    if not answer['show_pins']:
        photopins.clear_drawn()
        toast.success('Photo pins hidden', 'They stay saved, and Photo Browser still lists them.')
        return
    if not fourd_common.has_models(doc):
        toast.success('Photo pins will show', 'Open a model with pins to see them.')
        return
    total = len(photopins.store(doc).list())
    drawn = photopins.refresh(doc)
    if total and not drawn:
        toast.warning('Photo pins could not be drawn', 'The view overlay is not loaded. Restart Navisworks, '
                      'then try again.')
    elif not total:
        toast.success('Photo pins shown', 'This model has no pins yet. Click Photo Pins to add one.')
    else:
        toast.success('Photo pins shown', '%s in this model.' % fourd_common.plural(drawn, 'pin'))


run()
