"""Spreads the selected objects (or their models) apart in one undo step; click again to collapse or spread further."""
from namo import colorize, explode, items, ui
from pynavis import doc as nwdoc
from pynavis import forms, script, toast

TITLE = 'Exploded View'


def new_explode(document, cfg):
    selected = items.selected(document)
    if not selected:
        toast.info('Nothing selected', 'Select the objects to spread apart, then run Exploded View again.')
        return
    model_count = len(explode.units_of(selected, 'models'))
    values = ui.form(TITLE, explode.option_fields(cfg, model_count), ok='Explode')
    if values is None:
        return
    opts = explode.normalize_options(values)
    script.save_config(opts)
    nodes = explode.units_of(selected, opts['units'])
    if len(nodes) > explode.MAX_UNITS:
        toast.info('Too many objects to spread', 'Exploded View moves up to %s objects at a time; %s are '
                   'selected. Select fewer, or choose Their whole models.'
                   % (colorize.count_text(explode.MAX_UNITS), colorize.count_text(len(nodes))))
        return
    if len(nodes) < 2:
        what = 'models' if opts['units'] == 'models' else 'objects'
        toast.info('Select two or more %s' % what,
                   'One %s has nothing to spread away from.' % what[:-1])
        return
    moved, record = explode.explode(nodes, opts, document)
    if not moved or record is None:
        toast.info('Nothing moved', 'The selected items share one center, or have no size.')
        return
    explode.save_record(record, document)
    toast.success('Exploded %s' % colorize.plural(moved, 'model' if opts['units'] == 'models' else 'object'),
                  'Spread %s. Ctrl+Z undoes it, or click Exploded View again to collapse.'
                  % explode.factor_text(opts['factor']))


def explode_more(document, record):
    factor = forms.ask_number('Spread the exploded view further by:', default=1.5,
                              min_value=explode.MIN_FACTOR, max_value=explode.MAX_FACTOR, title=TITLE)
    if factor is None:
        return
    moved, record, missing = explode.explode_more(record, factor, document)
    explode.save_record(record, document)
    detail = 'Now %s.' % explode.describe(record)
    if missing:
        detail += ' %s could not be found.' % colorize.plural(missing, 'item')
    if moved:
        toast.success('Spread %s further' % colorize.plural(moved, 'item'), detail)
    else:
        toast.warning('Nothing moved', detail)


def collapse(document, record):
    route = explode.collapse_route(record)
    back, moved_since, missing = explode.collapse(record, document)
    explode.save_record(None, document)
    problems = []
    if moved_since:
        problems.append('%s no longer sat where the explode left them (moved or undone since), '
                        'so they stayed put.' % colorize.plural(moved_since, 'item'))
    if missing:
        problems.append('%s could not be found.' % colorize.plural(missing, 'item'))
    if problems:
        title = 'Collapsed %s' % colorize.plural(back, 'item') if back else 'Nothing collapsed'
        toast.warning(title, ' '.join(problems))
    else:
        toast.success('Collapsed %s' % colorize.plural(back, 'item'),
                      'Everything is back where it was.' if route == 'inverse'
                      else 'Everything is back where its file has it.')


def run():
    document = nwdoc.get_doc()
    if document.Models.Count == 0:
        toast.info('No model open', 'Open a model, then run Exploded View again.')
        return
    cfg = explode.normalize_options(script.get_config(explode.DEFAULTS))
    record = explode.load_record(document)
    if record is not None and explode.check(record, document)['stale']:
        explode.save_record(None, document)         # undone or moved since: start afresh
        record = None
    if record is None:
        new_explode(document, cfg)
        return
    action = forms.ask_options(None, [explode.COLLAPSE, explode.MORE], title=TITLE)
    if action == explode.COLLAPSE:
        collapse(document, record)
    elif action == explode.MORE:
        explode_more(document, record)


run()
