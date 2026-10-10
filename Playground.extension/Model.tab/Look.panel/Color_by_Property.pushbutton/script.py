"""Colors every item in the chosen scope by the value of one property and prints the legend."""
from namo import colorize, items, paint, progress, session, ui
from pynavis import doc as nwdoc
from pynavis import script, toast

TITLE = 'Color by Property'
DEFAULTS = {'scope': 'visible', 'top': colorize.DEFAULT_TOP, 'other': 'grey', 'reset': True,
            'ghost': False, 'property': []}
SCOPE_LABELS = {'selection': 'current selection', 'visible': 'visible items', 'model': 'whole model'}
EMPTY_SCOPE = {
    'selection': 'The selection holds no items with geometry. Select some objects first.',
    'visible': 'No visible item was found. Unhide something, or choose Whole model.',
    'model': 'The model holds no items with geometry.',
}


def run():
    document = nwdoc.get_doc()
    if document.Models.Count == 0:
        toast.info('No model open', 'Open or append a model, then run Color by Property again.')
        return
    cfg = script.get_config(DEFAULTS)
    selected = items.selected(document)
    options = ui.form(TITLE, colorize.options_fields(len(selected), cfg), ok='Next')
    if options is None:
        return
    scope = options['scope']
    remembered = cfg.get('scope')
    cfg.update(options)
    if scope == 'selection' and remembered in ('visible', 'model'):
        cfg['scope'] = remembered           # the selection is offered anyway; keep the other choice
    script.save_config(cfg)

    objects = progress.run(TITLE, lambda report: colorize.scope_objects(
        scope, document, tick=colorize.counting(report, 'Collecting items:')))
    if objects is progress.CANCELLED:
        return
    if not objects:
        toast.info('Nothing to color', EMPTY_SCOPE[scope])
        return

    names, sampled = colorize.property_names(objects)
    if not names:
        toast.info('No properties found', 'The items in the %s carry no properties.' % SCOPE_LABELS[scope])
        return
    last = tuple(cfg.get('property') or ())
    picked = ui.choose(TITLE, colorize.property_rows(names, sampled), ['Category', 'Property', 'Found on'],
                       multiselect=False, checked=[last] if last else None, ok='Color',
                       prompt='Pick the property to color by. Found on says how many of %s sampled '
                              'items carry it.' % colorize.count_text(sampled))
    if picked is None:
        return
    category, prop = picked[0]
    cfg['property'] = [category, prop]
    script.save_config(cfg)
    label = colorize.property_label(category, prop)

    groups = progress.run(TITLE, lambda report: colorize.read_groups(
        objects, category, prop, tick=colorize.counting(report, 'Reading %s:' % prop)))
    if groups is progress.CANCELLED:
        return
    if all(value == colorize.NO_VALUE for value, _members in groups):
        toast.info('Nothing to color', 'None of the %s carries %s.' % (
            colorize.plural(len(objects), 'item'), label))
        return

    memory = colorize.load_memory()
    key = colorize.scheme_key(category, prop)
    ranked = [(value, len(members)) for value, members in groups]
    plan = colorize.plan_scheme(ranked, options['top'], options['other'], colorize.memory_map(memory, key))
    ghost = colorize.GHOST_TRANSPARENCY if options['ghost'] else None
    scheme = colorize.make_scheme(category, prop, plan, SCOPE_LABELS[scope], ghost=ghost)
    painted = colorize.apply(colorize.paint_groups(groups, plan), document,
                             reset_first=options['reset'], rest_transparency=ghost,
                             reset_items=objects if scope == 'selection' else None)

    colorize.save_memory(colorize.update_memory(memory, key, colorize.value_pairs(scheme)))
    try:
        paint.remember_scheme(scheme)
    except Exception as error:
        session.log('warning', 'color scheme not remembered for Legend Maker: %s' % error)
    colorize.show_legend(scheme)
    message, detail = colorize.summary(scheme, painted)
    toast.success(message, detail)


run()
