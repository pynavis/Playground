# -*- coding: utf-8 -*-
"""Shows which model the selection comes from, with its files, units and transform, then acts on that model."""
from namo import mdl_output, modelmgmt, sourcefiles, transforms, ui

from pynavis import app, forms, output, panes, selection, toast

# Items counted before the card shows, shared by every model in the selection: the
# click must answer at once even on a federation of millions of items (the Source Files
# panel counts in full, in the background).
ITEM_BUDGET = 200000


def card(info, stale, doc, total, budget):
    doc_units = str(doc.Units)
    try:
        state = transforms.read_state(info['model'])
        factor = transforms.unit_factor(doc_units, state['units'], transforms.convention())
        transform = '; '.join(transforms.describe(state, doc_units, factor)[:3])
    except Exception:
        transform = 'Could not be read'
    try:
        counted = modelmgmt.count_items(info['root'], budget=max(1, budget[0]))
        budget[0] -= counted['items']
        items = '{:,} items, {:,} with geometry'.format(counted['items'], counted['geometry'])
        if counted['sampled']:
            items = ('Over {:,} items (Source Files counts them all)'.format(counted['items'])
                     if counted['items'] > 1 else 'Not counted (Source Files counts them all)')
    except Exception:
        items = 'Could not be counted'
    file_text = info['file'] or 'none (embedded)'
    if stale.get('cache_time') is not None:
        file_text += '\n%s, saved %s' % (modelmgmt.format_size(stale.get('cache_size')),
                                          modelmgmt.format_time(stale['cache_time']))
    source_text = info['source'] or 'none recorded'
    if stale.get('source_time') is not None and info['source'] != info['file']:
        source_text += '\n%s, saved %s' % (modelmgmt.format_size(stale.get('source_size')),
                                            modelmgmt.format_time(stale['source_time']))
    pairs = [('Model', '%d of %d in the Selection Tree' % (info['index'] + 1, total)),
             ('Loaded from', file_text), ('Source file', source_text),
             ('Freshness', '%s. %s' % (stale.get('status', ''), stale.get('detail', ''))),
             ('Created by', info['creator'] or 'not recorded'), ('Units', info['units'] or 'unknown'),
             ('Transform', transform), ('Contents', items)]
    return mdl_output.heading(info['name'], 2) + mdl_output.kv_table(pairs)


def act(choice, infos, doc):
    keys = [i['key'] for i in infos]
    names = modelmgmt.join_names([i['name'] for i in infos])
    noun = modelmgmt.plural(len(infos), 'model')
    if choice.startswith('Select'):
        modelmgmt.select_models(keys, doc)
        toast.success('Selected %s' % noun, names)
    elif choice.startswith('Isolate'):
        modelmgmt.isolate_models(keys, doc)
        toast.success('Isolated %s' % noun, names)
    elif choice.startswith('Hide'):
        modelmgmt.set_models_hidden(keys, True, doc)
        toast.success('Hid %s' % noun, names)
    elif choice == 'Open folder':
        target = modelmgmt.model_folder(infos[0])
        if not target:
            toast.warning('Folder not found', 'Neither the file of %s nor its source is on this computer.'
                          % infos[0]['name'])
            return
        ui.show_in_explorer(target)
    elif choice == 'Refresh files':
        try:
            changed = modelmgmt.refresh_files(doc)
        except Exception as error:
            toast.error('Could not refresh the files', str(error) or type(error).__name__)
            return
        if changed:
            toast.success('Reloaded the changed models')
        else:
            toast.info('No model files changed', 'Every model is as new as its file.')
    elif choice.startswith('Remove'):
        question = 'Remove %s from this document?\n\n%s\n\nSave first if you may want %s back.' % (
            noun, '\n'.join(i['name'] for i in infos), 'it' if len(infos) == 1 else 'them')
        if not forms.confirm(question, 'Link Navigator'):
            return
        removed, failed = modelmgmt.remove_models(keys, doc)
        if failed:
            toast.warning('Removed %d, %d failed' % (len(removed), len(failed)),
                          'Could not remove %s.' % modelmgmt.join_names(failed))
        else:
            toast.success('Removed %s' % modelmgmt.plural(len(removed), 'model'), modelmgmt.join_names(removed))
    elif choice == 'Show in Source Files':
        if not panes.show(sourcefiles.PANE_KEY):
            toast.warning('The Source Files panel has no slot',
                          'Every pyNavis panel slot is claimed. Add more with Panel slots on the pyNavis '
                          'tab, then restart Navisworks.')
            return
        sourcefiles.show_model(keys[0])


def run():
    doc = app.get_doc()
    picked = selection.get_items(doc)
    if not picked:
        toast.info('Nothing selected', 'Select an element to find the model it comes from.')
        return
    infos = modelmgmt.models_of_items(picked, doc)
    if not infos:
        toast.warning('Could not find the model of the selection', 'Select an element in the scene or the Selection Tree.')
        return
    all_infos = modelmgmt.models_info(doc)
    stale = dict((r['key'], r) for r in modelmgmt.stale_rows(doc, infos))
    shown = infos[:8]
    budget = [ITEM_BUDGET]
    html = [card(info, stale.get(info['key']) or {}, doc, len(all_infos), budget) for info in shown]
    if len(infos) > len(shown):
        html.append(mdl_output.note('%d more models are in the selection.' % (len(infos) - len(shown))))
    output.print_html(''.join(html))
    many = len(infos) > 1
    options = ['Select models' if many else 'Select model',
               'Isolate models' if many else 'Isolate model',
               'Hide models' if many else 'Hide model',
               'Open folder', 'Refresh files',
               'Remove models' if many else 'Remove model',
               'Show in Source Files']
    prompt = ('The selection comes from %s. What next?' % modelmgmt.join_names([i['name'] for i in infos])
              if many else 'The selection comes from %s. What next?' % infos[0]['name'])
    choice = forms.ask_options(prompt, options, 'Link Navigator')
    if choice is None:
        return
    act(choice, infos, doc)


run()
