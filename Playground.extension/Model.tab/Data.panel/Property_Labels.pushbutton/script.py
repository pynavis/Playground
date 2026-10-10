# -*- coding: utf-8 -*-
"""Labels each selected object in the view with the value of a chosen property."""
from pynavis import script, toast

from namo import data_common, data_labels, items, propindex, ui

DEFAULTS = {'property': 'Item > Name'}


def run():
    if ui.is_runner():
        toast.info('Property Labels needs the Navisworks window', 'It cannot open under pynavis run.')
        return
    doc = data_common.active_doc()
    selected = items.selected(doc) if data_common.has_models(doc) else []
    if not selected:
        toast.info('Nothing selected', 'Select the objects to label, then run Property Labels again.')
        return
    values = script.get_config(DEFAULTS)
    choices = propindex.property_choices(doc, scope='selection')
    rows = [{'cells': [c, p, n], 'value': propindex.pair_text(c, p)} for c, p, n in choices]
    if not rows:
        toast.info('No properties on the selection', 'Select objects that carry properties.')
        return
    picked = ui.choose('Property Labels', rows, ['Tab', 'Property', 'Items seen'], multiselect=False,
                       checked=[values.get('property')], prompt='Label each selected object with which value?',
                       ok='Label')
    if picked is None:
        return
    script.save_config({'property': picked[0]})
    category, prop = propindex.split_pair(picked[0])
    # One label per element. The value is read from the element, then from the item
    # as selected (a geometry part can carry a property its element does not).
    objects = []
    picked_as = {}
    for item in selected:
        obj = items.object_of(item)
        if obj not in picked_as:
            picked_as[obj] = item
            objects.append(obj)
    capped = len(objects) > data_labels.MAX_LABELS
    reader = propindex.Reader(doc)
    labels = []
    without = 0
    for obj in objects[:data_labels.MAX_LABELS]:
        text = reader.text(obj, category, prop)
        if text == propindex.MISSING:
            text = reader.text(picked_as[obj], category, prop)
        if text in (propindex.MISSING, propindex.NO_VALUE):
            without += 1
            continue
        box = items.bbox(obj)
        if box is None:
            without += 1
            continue
        labels.append((box, text))
    if not labels:
        toast.info('Nothing to label', 'None of the selected objects has a value for %s.' % picked[0])
        return
    drawn, loaded = data_labels.draw(labels, doc)
    if not loaded:
        toast.warning('Labels could not be drawn',
                      'The pyNavis view overlay is not loaded. Restart Navisworks, then try again.')
        return
    notes = ['Clear Labels removes them.']
    if without:
        notes.insert(0, '%s without a value.' % '{:,}'.format(without))
    if capped:
        notes.insert(0, 'First %s of %s objects.' % ('{:,}'.format(data_labels.MAX_LABELS),
                                                     '{:,}'.format(len(objects))))
    level = toast.warning if capped else toast.success
    level('Labelled %s %s with %s' % ('{:,}'.format(drawn), 'object' if drawn == 1 else 'objects', prop),
          ' '.join(notes))


run()
