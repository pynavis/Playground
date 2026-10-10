# -*- coding: utf-8 -*-
"""Finds objects with the same class, primitive count and bounding box within a tolerance, and selects the extra copies."""
import datetime

from pynavis import doc as nwdoc
from pynavis import output, script, toast

from namo import duplicates, items, mdl_output, modelmgmt, progress, ui, units

LINKS_PER_ROW = 6
MAX_ROWS = 500


def choose_models(document):
    infos = modelmgmt.models_info(document)
    rows = [{'value': info['index'], 'cells': [info['name'], info['kind'], info['units']]}
            for info in infos]
    picked = ui.choose('Choose models', rows, ['Model', 'Type', 'Units'], multiselect=True,
                       checked=[info['index'] for info in infos],
                       prompt='Tick the models to search for duplicates.')
    if picked is None:
        return None
    wanted = set(picked)
    return [info['root'] for info in infos if info['index'] in wanted]


def ask(document, cfg, selected, prefill):
    doc_units = str(document.Units)
    options = []
    if selected:
        options.append(('Current selection (%s)' % modelmgmt.plural(len(selected), 'item'), 'selection'))
    options.extend([('Whole model', 'all'), ('Choose models', 'models')])
    values = [value for _label, value in options]
    scope = 'selection' if selected else (cfg['scope'] if cfg['scope'] in values else 'all')
    fields = [
        {'kind': 'radio', 'key': 'scope', 'label': 'Look in', 'options': options, 'default': scope, 'fallback': None},
        {'kind': 'length', 'key': 'tolerance', 'label': 'Tolerance', 'required': True,
         'default': prefill,
         'validate': lambda v: None if v is None or v > 0 else 'The tolerance must be more than zero.',
         'hint': 'Every corner of the two bounding boxes must be this close.'},
        {'kind': 'check', 'key': 'deep', 'label': 'Also compare shape volume and centre (slow)',
         'default': cfg['deep']},
        {'kind': 'check', 'key': 'select', 'label': 'Select the extra copies', 'default': cfg['select']},
        {'kind': 'check', 'key': 'make_set', 'label': 'Save them as a selection set',
         'default': cfg['make_set']},
    ]
    return ui.form('Duplicate finder', fields, ok='Find', units=doc_units,
                   intro='Objects count as duplicates when their class, primitive count and '
                         'bounding box match.')


def search(document, roots, asked, deep):
    def work(report):
        data = duplicates.collect(roots, document,
                                  progress=lambda f, label: report(0.7 * f, label))
        report(0.72, 'Grouping %s objects' % '{:,}'.format(len(data['entries'])))
        # Far from the origin the boxes may be coarser than the tolerance asked for:
        # search at whichever is larger, and say so in the result.
        precision = duplicates.box_precision(data['entries'])
        tol, widened = duplicates.effective_tolerance(asked, precision)
        data['tolerance'], data['widened'] = tol, widened
        groups = duplicates.group_duplicates(data['entries'], tol)
        data['deep_read'] = 0
        if deep and groups:
            stats = {}
            props, read = duplicates.deep_props(
                groups, data['objects'], progress=lambda f, label: report(0.75 + 0.25 * f, label),
                stats=stats)
            checked, rest = groups[:read], groups[read:]
            groups = duplicates.refine(checked, props, max(tol, 4.0 * stats.get('noise', 0.0))) + rest
            data['deep_read'] = read
        data['groups'] = groups
        report(1.0, 'Done')
        return data
    return progress.run('Duplicate finder', work)


def show(data, names_by_index, tol_label):
    groups = data['groups']
    objects = data['objects']
    model_of = dict((e[0], e[4]) for e in data['entries'])
    class_of = dict((e[0], e[1]) for e in data['entries'])
    kinds = [duplicates.classify(group, lambda i: model_of.get(i)) for group in groups]
    rows = []
    for number, group in enumerate(groups[:MAX_ROWS]):
        links = [output.element_link(objects[i], objects[i].DisplayName or class_of.get(i) or 'Object')
                 for i in group[:LINKS_PER_ROW]]
        if len(group) > LINKS_PER_ROW:
            links.append(mdl_output.esc('and %d more' % (len(group) - LINKS_PER_ROW)))
        models = sorted(set(names_by_index.get(model_of.get(i), '') for i in group))
        rows.append([number + 1, kinds[number], len(group), class_of.get(group[0], ''),
                     ', '.join(models), ', '.join(links)])
    copies = sum(len(g) - 1 for g in groups)
    across = sum(1 for kind in kinds if kind == 'Across models')
    note = 'Tolerance %s.' % tol_label
    if data.get('widened'):
        note += (' Wider than asked: this far from the origin the bounding boxes are only that '
                 'precise. Tick the shape check to confirm the groups.')
    if data['sampled']:
        note += ' Sampled: the object budget stopped the search early.'
    if data.get('deep_read'):
        note += ' Shapes compared for the first %s groups.' % '{:,}'.format(data['deep_read'])
    html = [mdl_output.heading('Duplicate finder', 1),
            mdl_output.kpis([('Objects checked', len(data['entries']), None),
                             ('Groups', len(groups), 'warn'),
                             ('Extra copies', copies, 'warn'),
                             ('Across models', across, None)]),
            mdl_output.note(note),
            mdl_output.table(['#', 'Kind', 'Copies', 'Class', 'Models', 'Objects'], rows,
                             raw=set([5]), numeric=[0, 2])]
    if len(groups) > MAX_ROWS:
        html.append(mdl_output.note('Showing the first %s of %s groups; the selection holds them all.'
                                    % ('{:,}'.format(MAX_ROWS), '{:,}'.format(len(groups)))))
    output.print_html(''.join(html))


def run():
    document = nwdoc.get_doc()
    doc_units = str(document.Units)
    cfg = script.get_config(duplicates.DEFAULTS)
    selected = items.selected(document)
    prefill = duplicates.default_tolerance(cfg['tolerance_m'], doc_units)
    answer = ask(document, cfg, selected, prefill)
    if answer is None:
        return
    tol = answer['tolerance']
    script.save_config({'tolerance_m': duplicates.kept_tolerance_m(tol, prefill, cfg['tolerance_m'],
                                                                   doc_units),
                        'scope': answer['scope'], 'deep': answer['deep'], 'select': answer['select'],
                        'make_set': answer['make_set']})
    if answer['scope'] == 'selection':
        roots = selected
    elif answer['scope'] == 'models':
        roots = choose_models(document)
        if roots is None:
            return
    else:
        roots = items.roots(document)
    if not roots:
        toast.info('Nothing to search', 'Select some objects or tick at least one model.')
        return
    data = search(document, roots, tol, answer['deep'])
    if data is progress.CANCELLED:
        return
    tol_label = duplicates.tolerance_text(units.to_meters(data['tolerance'], doc_units),
                                          units.is_imperial(doc_units))
    groups = data['groups']
    level, message, detail = duplicates.summary(groups, len(data['entries']), tol_label, data['sampled'])
    if not groups:
        toast.show(level, message, detail)
        return
    names = dict((info['index'], info['name']) for info in modelmgmt.models_info(document))
    show(data, names, tol_label)
    extra = [data['objects'][i] for i in duplicates.extras(groups)]
    done = []
    if answer['select']:
        items.select(extra, doc=document)
        done.append('Selected the %s extra copies' % '{:,}'.format(len(extra)))
    if answer['make_set']:
        try:
            path = duplicates.make_set(extra, duplicates.set_name(datetime.datetime.now()), document)
        except Exception as error:
            toast.warning(message, 'Could not save the selection set: %s' % error)
            return
        done.append(('set %s' if done else 'Saved the extra copies as set %s') % path)
    if done:
        detail = '; '.join(done) + '.'
    toast.show(level, message, detail)


run()
