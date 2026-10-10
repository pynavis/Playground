"""Colours elements by how many open clashes they have and marks the densest spots in the view."""
from pynavis import script, toast

from namo import clashheat, progress, ui, units
from namo import clashset_common as common
from namo import clashset_tests as defs

DEFAULTS = {'tests': [], 'statuses': list(common.OPEN_STATUSES), 'ghost': True, 'markers': False,
            'cell_m': clashheat.DEFAULT_CELL_M}
TITLE = 'Clash Heatmap'


def ask(values, doc_units):
    fields = [
        {'kind': 'multi', 'key': 'statuses', 'label': 'Count clashes with these statuses',
         'options': [(s, s) for s in common.STATUS_NAMES], 'default': values['statuses']},
        {'kind': 'check', 'key': 'ghost', 'label': 'Ghost the elements without clashes',
         'default': values['ghost']},
        {'kind': 'check', 'key': 'markers', 'label': 'Mark the densest spots in the view',
         'default': values['markers']},
        {'kind': 'length', 'key': 'cell', 'label': 'Marker cell size', 'required': True,
         'default': units.from_meters(values['cell_m'] or clashheat.DEFAULT_CELL_M, doc_units),
         'min': 0.0001, 'enabled_if': ('markers', True)},
    ]

    def validate(answers):
        if not answers['statuses']:
            return {'statuses': 'Tick at least one status.'}
        return None

    return ui.form(TITLE, fields, ok='Show', validate=validate, units=doc_units,
                   intro='Every chosen clash counts once for each of its two elements.')


def run():
    from pynavis import doc as pdoc
    doc = pdoc.get_doc()
    problem = common.clash_problem(doc, need_results=True)
    if problem:
        toast.show(*problem)
        return
    values = script.get_config(DEFAULTS)
    tests = common.choose_tests(TITLE, 'Tick the tests to count.', values['tests'], doc=doc)
    if tests is None:
        return
    if not tests:
        toast.info('No clash results yet', 'Run your clash tests in Clash Detective first.')
        return
    doc_units = defs.doc_units(doc)
    answers = ask(values, doc_units)
    if answers is None:
        return
    values.update({'statuses': answers['statuses'], 'ghost': answers['ghost'],
                   'markers': answers['markers'], 'tests': [t.DisplayName for t in tests]})
    if answers.get('cell'):
        values['cell_m'] = units.to_meters(answers['cell'], doc_units)
    script.save_config(values)
    try:
        entries = common.read_entries(tests, doc)
    except RuntimeError as error:
        toast.error('Could not read the clashes', str(error))
        return
    if entries is progress.CANCELLED:
        return
    counts, elements, names, centres = clashheat.collect(entries, answers['statuses'])
    if not counts:
        toast.info('No clashes to count', 'None of the chosen tests has %s clashes.'
                   % ' or '.join(answers['statuses']))
        return
    coloured = common.write_progress(TITLE, lambda report_to: clashheat.show(
        counts, elements, answers['ghost'], doc))
    markers = 0
    overlay_ok = True
    if answers['markers']:
        cell = units.from_meters(values['cell_m'], doc_units)
        markers, overlay_ok = clashheat.draw_markers(centres, cell)
    legend = clashheat.legend(counts)
    title = 'Clash heatmap: %s' % ', '.join(e['name'] for e in entries)
    clashheat.report(counts, elements, names, legend, markers if overlay_ok else 0, title, doc)
    top_key, top_count = clashheat.ranked(counts, names, 1)[0]
    detail = 'Hotspot: %s with %s.' % (names.get(top_key) or 'an element',
                                       common.plural(top_count, 'clash', 'clashes'))
    if answers['markers'] and not overlay_ok:
        toast.warning(clashheat.summary_text(coloured, len(legend), 0),
                      'Markers need the pyNavis overlay; restart Navisworks to finish installing it.')
        return
    toast.success(clashheat.summary_text(coloured, len(legend), markers), detail)


if globals().get('__runner__'):
    toast.warning(*common.RUNNER_MESSAGE)
else:
    run()
