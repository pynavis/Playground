"""Paints items by construction status, sets the status of the selection, or shows the status legend."""
from namo import colorize, items, look_status, paint, progress, session
from pynavis import doc as nwdoc
from pynavis import forms, script, toast

TITLE = 'Status Painter'


def read_status(document, cfg):
    """[(value, [items])] for every item carrying the status property, or
    progress.CANCELLED."""
    def work(report):
        report(0.0, 'Finding items with %s' % cfg['property'])
        found = look_status.find_items(cfg, document)
        return colorize.read_groups(found, cfg['category'], cfg['property'],
                                    tick=colorize.counting(report, 'Reading status:'))
    return progress.run(TITLE, work)


def remember(scheme):
    try:
        paint.remember_scheme(scheme)
    except Exception as error:
        session.log('warning', 'status scheme not remembered for Legend Maker: %s' % error)


def nothing_found(cfg):
    label = colorize.property_label(cfg['category'], cfg['property'])
    if look_status.is_default_source(cfg):
        toast.info('No status set yet', 'Select items and use Set status of selection, or Shift+Click '
                                        'to read the status from another property.')
    else:
        toast.info('No item carries %s' % label, 'Shift+Click Status Painter to pick the property '
                                                 'that holds the status.')


def paint_by_status(document, cfg):
    groups = read_status(document, cfg)
    if groups is progress.CANCELLED:
        return
    if not groups:
        nothing_found(cfg)
        return
    touched, plan = look_status.paint(cfg, groups, document)
    scheme = look_status.status_scheme(cfg, plan['counts'], plan['unknown'])
    remember(scheme)
    if not touched:
        toast.warning('No known status found', look_status.counts_detail(plan['counts'], plan['unknown']))
        return
    toast.success('Painted %s by status' % colorize.plural(touched, 'item'),
                  look_status.counts_detail(plan['counts'], plan['unknown']))


def set_status(document, cfg):
    targets = items.selected(document)
    if not targets:
        toast.info('Nothing selected', 'Select the items whose status changed, then run Set status again.')
        return
    problem = look_status.writable_problem(cfg, targets)
    if problem:
        toast.error('Cannot write the status', problem)
        return
    status = forms.select_from_list(look_status.status_options(cfg), title='Set status',
                                    prompt='Status for %s:' % colorize.plural(len(targets), 'selected item'))
    if status is None:
        return
    value = None if status == look_status.CLEAR else status
    if len(targets) > look_status.CHUNK:
        outcome = progress.run(TITLE, lambda report: look_status.set_status(targets, cfg, value, document, report))
    else:
        outcome = look_status.set_status(targets, cfg, value, document)
    if outcome is progress.CANCELLED:
        return
    written, errors, stopped = outcome
    if errors and not written:
        toast.error('Could not set the status', errors[0])
        return
    noun = colorize.plural(written, 'item')
    message = ('Cleared the status of %s' % noun) if value is None else ('Set %s to %s' % (noun, value))
    if stopped:
        toast.warning('Stopped after %s of %s' % (colorize.count_text(written), colorize.plural(len(targets), 'item')),
                      'Ctrl+Z undoes the part that was written.')
    elif errors:
        toast.warning(message, '%s failed: %s' % (colorize.plural(len(errors), 'item'), errors[0]))
    else:
        toast.success(message, 'Stored in %s.' % colorize.property_label(cfg['category'], cfg['property']))


def legend(document, cfg):
    groups = read_status(document, cfg)
    if groups is progress.CANCELLED:
        return
    plan = look_status.plan_paint(groups or [], cfg['statuses'])
    scheme = look_status.status_scheme(cfg, plan['counts'], plan['unknown'])
    remember(scheme)
    colorize.show_legend(scheme)
    toast.info('Status legend in the output window', look_status.counts_detail(plan['counts'], plan['unknown']))


def run():
    document = nwdoc.get_doc()
    if document.Models.Count == 0:
        toast.info('No model open', 'Open or append a model, then run Status Painter again.')
        return
    cfg = look_status.normalize_config(script.get_config(look_status.DEFAULTS))
    action = forms.ask_options(None, look_status.ACTIONS, title=TITLE)
    if action == look_status.ACTIONS[0]:
        paint_by_status(document, cfg)
    elif action == look_status.ACTIONS[1]:
        set_status(document, cfg)
    elif action == look_status.ACTIONS[2]:
        legend(document, cfg)


run()
