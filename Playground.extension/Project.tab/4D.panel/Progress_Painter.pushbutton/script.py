# -*- coding: utf-8 -*-
"""Sets percent complete on the selected objects and their TimeLiner tasks, or paints the model by progress."""
from pynavis import forms, script, toast

from namo import fourd_common, fourd_progress, fourd_ui, items, progress, timeliner, ui

TITLE = 'Progress Painter'
DEFAULTS = {'percent': 50.0}
SET = 'Set progress of the selection'
PAINT_ITEMS = 'Paint by object progress'
PAINT_TASKS = 'Paint by TimeLiner task progress'
CLEAR = 'Clear the progress paint'


def set_progress(doc, selected):
    values = script.get_config(DEFAULTS)
    objects = items.objects(selected)
    percent = forms.ask_number('Percent complete for %s (0 to 100):' % fourd_common.plural(len(objects), 'object'),
                               default=values.get('percent', 50.0), min_value=0, max_value=100, title=TITLE)
    if percent is None:
        return
    values['percent'] = percent
    script.save_config(values)
    result = progress.run(TITLE, lambda report: fourd_progress.set_progress(objects, percent, doc, report))
    if result is progress.CANCELLED:
        return
    shown = ('%.1f' % percent).rstrip('0').rstrip('.')
    if not result['timeliner']:
        detail = 'TimeLiner is not available here, so no task was updated.'
    elif result['tasks']:
        detail = 'Updated the progress of %s.' % fourd_common.plural(result['tasks'], 'TimeLiner task')
    else:
        detail = 'No TimeLiner task holds these objects.'
    if result['errors']:
        toast.warning('Set %s%% on %s, %d failed' % (shown, fourd_common.plural(result['objects'], 'object'),
                                                    len(result['errors'])), result['errors'][0])
    else:
        toast.success('Set %s%% on %s' % (shown, fourd_common.plural(result['objects'], 'object')), detail)


def paint(doc, by_tasks):
    if by_tasks:
        try:
            rows = timeliner.snapshot(doc)
        except RuntimeError as error:
            toast.error('TimeLiner is not available', str(error))
            return
        if not [r for r in rows if r.get('progress') is not None and (r.get('attach_kind') or 'none') != 'none']:
            toast.info('No task has progress and items', 'Set % Complete in TimeLiner, or use Set progress first.')
            return
        outcome = progress.run(TITLE, lambda report: fourd_progress.paint_tasks(rows, doc, report))
        source = 'Colours from TimeLiner task progress.'
    else:
        def work(report):
            objects = items.objects(items.roots(doc), tick=progress.tick(report))
            return fourd_progress.paint_items(objects, doc, report)
        outcome = progress.run(TITLE, work)
        source = 'Colours from each object\'s Playground > Progress.'
    if outcome is progress.CANCELLED:
        return
    counts, painted = outcome
    if not painted:
        toast.info('Nothing to paint', 'No object carries a progress value yet. Select objects and set their progress.')
        return
    toast.success('Painted %s by progress' % fourd_common.plural(len(painted), 'object'), 'Ctrl+Z undoes it.')

    def clear():
        count = fourd_progress.clear_paint(doc)
        if count:
            toast.success('Cleared the progress paint', fourd_common.plural(count, 'object'))
    fourd_ui.show_legend(counts, source, clear)


def run():
    if ui.is_runner():
        toast.info('%s needs a person at the screen' % TITLE, 'Run it from the ribbon.')
        return
    doc = fourd_common.active_doc()
    if not fourd_common.has_models(doc):
        toast.info('No model is open', 'Open or append a model first.')
        return
    selected = items.selected(doc)
    options = ([SET] if selected else []) + [PAINT_ITEMS, PAINT_TASKS, CLEAR]
    prompt = 'What should Progress Painter do?' if selected else \
        'Nothing is selected, so progress cannot be set. Paint instead?'
    choice = forms.ask_options(prompt, options, title=TITLE)
    if choice is None:
        return
    if choice == SET:
        set_progress(doc, selected)
    elif choice == CLEAR:
        count = fourd_progress.clear_paint(doc)
        if count is None:
            toast.info('Nothing painted in this session', 'Ctrl+Z, or Reset All > Appearance in Navisworks, removes older paint.')
        else:
            toast.success('Cleared the progress paint', fourd_common.plural(count, 'object'))
    else:
        paint(doc, choice == PAINT_TASKS)


run()
