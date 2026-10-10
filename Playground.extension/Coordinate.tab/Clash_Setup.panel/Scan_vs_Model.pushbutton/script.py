"""Checks the design against laser scans with a point clearance test, colouring elements by how close the scan comes."""
from pynavis import output, script, toast

from namo import progress, ui
from namo import clashset_common as common
from namo import clashset_tests as defs
from namo import scanvsmodel as svm
from namo.htmlreport import escape

DEFAULTS = {'scans': [], 'design': 'others', 'design_models': [], 'design_set': '', 'bands': '',
            'name': svm.DEFAULT_TEST_NAME, 'paint': True, 'ghost': False}
TITLE = 'Scan vs Model'
TOP = 25


def set_paths(doc):
    from pynavis import sets
    rows = sets.snapshot(doc)
    names = dict((row['key'], row['name']) for row in rows)
    out = []
    for row in rows:
        if row['is_folder']:
            continue
        chain = []
        key = row['key']
        while key:
            chain.append(names.get(key, ''))
            key = key.rpartition('/')[0]
        chain.reverse()
        out.append(defs.join_set_path(chain))
    return out


def ask(models, set_options, values, doc_units):
    names = [m['name'] for m in models]
    suggested = [m['name'] for m in models if m['points']]
    scans = [n for n in values['scans'] if n in names] or suggested
    design_models = [n for n in values['design_models'] if n in names]
    design_choices = [('Every other model', 'others'), ('Models I choose', 'models')]
    if set_options:
        design_choices.append(('A selection set', 'set'))
    design = values['design'] if values['design'] in [v for _l, v in design_choices] else 'others'
    fields = [
        {'kind': 'multi', 'key': 'scans', 'label': 'Scan models', 'default': scans,
         'options': [(m['name'] + ('  (points)' if m['points'] else ''), m['name']) for m in models],
         'hint': 'Models drawn with points or saved as .rcp, .rcs, .e57 are suggested.'},
        {'kind': 'radio', 'key': 'design', 'label': 'Design to check', 'default': design, 'fallback': None,
         'options': design_choices},
        {'kind': 'multi', 'key': 'design_models', 'label': 'Design models', 'default': design_models,
         'options': [(n, n) for n in names], 'enabled_if': ('design', 'models')},
    ]
    if set_options:
        fields.append({'kind': 'choice', 'key': 'design_set', 'label': 'Selection set',
                       'options': [(p, p) for p in set_options],
                       'default': values['design_set'] if values['design_set'] in set_options else set_options[0],
                       'enabled_if': ('design', 'set')})
    fields.extend([
        {'kind': 'text', 'key': 'bands', 'label': 'Deviation bands',
         'default': values['bands'] or svm.default_bands_text(doc_units),
         'hint': 'Smallest first, like 25, 50, 100 mm. The largest is the test tolerance.'},
        {'kind': 'text', 'key': 'name', 'label': 'Clash test name', 'default': values['name']},
        {'kind': 'check', 'key': 'paint', 'label': 'Colour design elements by band',
         'default': values['paint']},
        {'kind': 'check', 'key': 'ghost', 'label': 'Ghost everything else', 'default': values['ghost'],
         'enabled_if': ('paint', True)},
    ])

    def validate(answers):
        errors = {}
        problem = svm.validate_choice(answers['scans'], answers['design_models']
                                      if answers['design'] == 'models' else [])
        if problem:
            errors['scans'] = problem
        if answers['design'] == 'models' and not answers['design_models']:
            errors['design_models'] = 'Choose at least one design model.'
        if answers['design'] == 'others' and not [n for n in names if n not in answers['scans']]:
            errors['design'] = 'Every model is a scan; keep at least one model for the design.'
        try:
            svm.parse_bands(answers['bands'], doc_units)
        except ValueError as error:
            errors['bands'] = str(error)
        if not answers['name'].strip():
            errors['name'] = 'Name the clash test.'
        return errors or None

    return ui.form(TITLE, fields, ok='Run test', validate=validate, width=520,
                   intro='One clearance test with points switched on for the scans; every design '
                         'element is then coloured by the band its closest scan points fall in.')


def report(test_name, summary, elements, bands, doc_units):
    labels = svm.band_labels(bands, doc_units)
    palette = svm.band_colors(len(bands))
    output.set_title(TITLE)
    output.print_md('# %s' % TITLE)
    output.print_md('Clash test "%s". Each design element counts once, in the band of its closest '
                    'scan points.' % test_name)
    lines = ['<table class="pynavis"><tr><th>Band</th><th></th><th class="num">Elements</th></tr>']
    for index, label in enumerate(labels):
        lines.append('<tr><td>%s</td><td><span style="display:inline-block;width:28px;height:12px;'
                     'background:#%s;border:1px solid var(--line)"></span></td><td class="num">%s</td></tr>'
                     % (escape(label), palette[index], '{:,}'.format(summary['counts'][index])))
    lines.append('</table>')
    output.print_html(''.join(lines))
    output.print_md('## Closest elements')
    rows = ['<table class="pynavis"><tr><th>Element</th><th class="num">Closest</th>'
            '<th class="num">Results</th><th>Band</th><th></th></tr>']
    for entry in summary['elements'][:TOP]:
        band = labels[entry['band']] if entry['band'] is not None else 'Beyond the bands'
        rows.append('<tr><td>%s</td><td class="num">%s</td><td class="num">%s</td><td>%s</td>'
                    '<td>%s</td></tr>' % (escape(entry['name']),
                                          escape(defs.length_text(entry['distance'], doc_units)),
                                          '{:,}'.format(entry['hits']), escape(band),
                                          output.element_link(elements[entry['key']], 'Show')))
    rows.append('</table>')
    output.print_html(''.join(rows))
    if len(summary['elements']) > TOP:
        output.print_md('The %d closest of %s are listed.' % (
            TOP, common.plural(len(summary['elements']), 'element')))


def run():
    from pynavis import doc as pdoc
    doc = pdoc.get_doc()
    if not defs.available(doc):
        toast.error('Clash Detective is not available', 'Scan vs Model needs Navisworks Manage.')
        return
    models = svm.models_info(doc)
    if len(models) < 2:
        toast.info('Append a scan and a design model first', 'Scan vs Model compares two or more models.')
        return
    doc_units = defs.doc_units(doc)
    values = script.get_config(DEFAULTS)
    answers = ask(models, set_paths(doc), values, doc_units)
    if answers is None:
        return
    values.update(answers)
    script.save_config(values)
    bands = svm.parse_bands(answers['bands'], doc_units)
    scans = answers['scans']
    if answers['design'] == 'set':
        design = defs.new_side([{'kind': 'set', 'path': answers['design_set']}])
    else:
        chosen = answers['design_models'] if answers['design'] == 'models' else \
            [m['name'] for m in models if m['name'] not in scans]
        design = defs.new_side([{'kind': 'model', 'name': n} for n in chosen])
    definition = svm.definition(answers['name'].strip(), scans, design, bands, doc_units)

    def build(report_to):
        report_to(0.05, 'Running %s; a large scan takes a while' % definition['name'])
        return svm.build_and_run(definition, doc)

    try:
        test, _outcome = common.write_progress(TITLE, build)
    except ValueError as error:
        toast.error('Could not build the scan test', str(error))
        return
    except Exception as error:
        # A point clearance test through the API is the one thing here nobody has seen
        # run: whatever Navisworks answers, say it plainly instead of a traceback.
        script.get_logger().error('Scan vs Model: %s' % error)
        toast.error('Navisworks could not run the scan test',
                    'Open "%s" in Clash Detective and run it there. (%s)' % (definition['name'], error))
        return
    read = progress.run('Reading the results', lambda report_to: svm.collect(test, doc, report_to))
    if read is progress.CANCELLED:
        return
    hits, elements = read
    widest = defs.length_text(bands[-1], doc_units)
    if not hits:
        toast.info('No scan points within %s of the design' % widest,
                   'The test "%s" found nothing; widen the bands to look further.' % definition['name'])
        return
    summary = svm.summarize(hits, bands)
    coloured = 0
    if answers['paint']:
        coloured = common.write_progress(TITLE, lambda report_to: svm.paint(summary, elements,
                                                                          answers['ghost'], doc))
    report(definition['name'], summary, elements, bands, doc_units)
    labels = svm.band_labels(bands, doc_units)
    parts = ['%s %s' % (labels[i], '{:,}'.format(n)) for i, n in enumerate(summary['counts']) if n]
    headline = 'Checked %s against the scan' % common.plural(len(summary['elements']), 'design element')
    if coloured:
        headline = 'Coloured %s by scan distance' % common.plural(coloured, 'design element')
    toast.success(headline, ', '.join(parts))


if globals().get('__runner__'):
    toast.warning(*common.RUNNER_MESSAGE)
else:
    run()
