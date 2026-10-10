# -*- coding: utf-8 -*-
"""Builds a search set step by step: scope, conditions from the model's own values, count, save."""
from pynavis import script, toast
from pynavis._api import Application

from namo import find_sets, items, progress, setwizard

cfg = script.get_config({'model': None})
document = Application.ActiveDocument

if document is None or document.Models.Count == 0:
    toast.info('Nothing to search', 'Open or append a model first.')
else:
    sample = progress.run('Reading the model for the wizard',
                          lambda report: setwizard.build_sample(document, report=report),
                          'Sampling elements')
    if sample is not progress.CANCELLED:
        source = setwizard.LiveSource(sample, document)
        answer = setwizard.dialog(cfg.get('model') or setwizard.new_model(), source,
                                  [m['name'] for m in items.models(document)],
                                  setwizard.folder_paths(document))
        if answer is not None:
            model, counted = answer
            script.save_config({'model': model})
            kinds = sample.kinds()
            try:
                names = setwizard.create(model, kinds, document)
            except ValueError as error:
                toast.error('Could not create the search set', str(error))
            else:
                key = setwizard.query_key(setwizard.queries(model, kinds), model)
                if model['select_now'] or counted is None or counted['key'] != key:
                    found = setwizard.matches(model, kinds, document)
                    total = found.Count
                    if model['select_now']:
                        items.select(found, doc=document)
                else:
                    total = counted['union']
                where = " in '%s'" % find_sets.plain_folder(model['folder']) if model['folder'] else ''
                count_text = '%s %s' % ('{:,}'.format(total), 'item' if total == 1 else 'items')
                if len(names) == 1:
                    message = "Created search set '%s' (%s)" % (names[0], count_text)
                else:
                    message = 'Created %d search sets (%s in all)' % (len(names), count_text)
                detail = 'Saved%s.%s' % (where, ' The matches are selected.' if model['select_now'] else '')
                if total:
                    toast.success(message, detail)
                else:
                    toast.warning(message, 'It finds nothing yet. Check the values, or the Search In scope.')
