# -*- coding: utf-8 -*-
"""Renders a 4D construction sequence from TimeLiner dates as stamped frames, an HTML player and an MP4."""
import os

from pynavis import script, toast

from namo import camera, dates, fourd_common, movie, naming, paths, progress, timeliner, ui

TITLE = '4D Movie Maker'
CURRENT = '@current'
DEFAULTS = {'basis': 'planned', 'step': 1, 'unit': 'weeks', 'size': '1920 x 1080', 'viewpoint': CURRENT,
            'show_unscheduled': True, 'mp4': True, 'fps': 4, 'folder': ''}


def ask(doc, rows, values):
    first, last = timeliner.schedule_bounds(rows)
    first_actual, last_actual = timeliner.schedule_bounds(rows, actual=True)
    views = [('Current view', CURRENT)] + [(path_of(folder, saved), path_of(folder, saved))
                                           for folder, saved in camera.saved_views(doc)]
    view_values = [v for _l, v in views]
    folder = values.get('folder') or ''
    if not folder or not os.path.isdir(folder):
        folder = fourd_common.doc_folder(doc)
    start = first_actual if values.get('basis') == 'actual' else first
    end = last_actual if values.get('basis') == 'actual' else last
    fields = [
        {'kind': 'radio', 'key': 'basis', 'label': 'Dates', 'inline': True,
         'options': [('Planned', 'planned'), ('Actual, planned where missing', 'actual')],
         'default': values.get('basis', 'planned'), 'fallback': 'planned'},
        {'kind': 'date', 'key': 'start', 'label': 'From', 'default': dates.iso(start, True), 'required': True},
        {'kind': 'date', 'key': 'end', 'label': 'To', 'default': dates.iso(end, True), 'required': True},
        {'kind': 'int', 'key': 'step', 'label': 'One frame every', 'min': 1, 'max': 365,
         'default': int(values.get('step') or 1), 'required': True},
        {'kind': 'radio', 'key': 'unit', 'label': 'Step in', 'inline': True,
         'options': [('Days', 'days'), ('Weeks', 'weeks')], 'default': values.get('unit', 'weeks'), 'fallback': 'weeks'},
        {'kind': 'choice', 'key': 'viewpoint', 'label': 'Camera', 'options': views,
         'default': values.get('viewpoint') if values.get('viewpoint') in view_values else CURRENT},
        {'kind': 'choice', 'key': 'size', 'label': 'Frame size', 'options': [l for l, _s in movie.SIZES],
         'default': values.get('size', '1920 x 1080'), 'fallback': '1920 x 1080'},
        {'kind': 'int', 'key': 'fps', 'label': 'Frames per second when played', 'min': 1, 'max': 30,
         'default': int(values.get('fps') or 4), 'required': True},
        {'kind': 'check', 'key': 'show_unscheduled', 'label': 'Show items that are in no task',
         'default': bool(values.get('show_unscheduled', True))},
        {'kind': 'check', 'key': 'mp4', 'label': 'Also make an MP4 when ffmpeg is installed',
         'default': bool(values.get('mp4', True))},
        {'kind': 'folder', 'key': 'folder', 'label': 'Save in', 'default': folder, 'required': True,
         'hint': 'A new folder for the frames and the player is made inside it.'},
    ]
    attached = len([r for r in rows if (r.get('attach_kind') or 'none') != 'none'])
    intro = '%s with items attached, planned from %s to %s.' % (
        fourd_common.plural(attached, 'task'), dates.format(first) or 'no date', dates.format(last) or 'no date')

    def validate(answer):
        start_, end_ = dates.parse(answer.get('start')), dates.parse(answer.get('end'))
        if start_ is None or end_ is None:
            return {'end': 'Give both dates.'}
        if end_ < start_:
            return {'end': 'The end date is before the start date.'}
        count = movie.count_frames(start_, end_, answer.get('step') or 1, answer.get('unit'))
        if count > movie.MAX_FRAMES:
            return {'step': 'That makes %s frames; the most is %s. Use a longer step.'
                    % ('{:,}'.format(count), '{:,}'.format(movie.MAX_FRAMES))}
        return None
    return ui.form(TITLE, fields, intro=intro, ok='Make movie', validate=validate, width=520)


def path_of(folder, saved):
    name = str(saved.DisplayName or '')
    return '%s/%s' % (folder, name) if folder else name


def run():
    if ui.is_runner():
        toast.info('%s needs a person at the screen' % TITLE, 'Run it from the ribbon.')
        return
    doc = fourd_common.active_doc()
    if not fourd_common.has_models(doc):
        toast.info('No model is open', 'Open or append a model first.')
        return
    try:
        rows = timeliner.snapshot(doc)
    except RuntimeError as error:
        toast.error('TimeLiner is not available', str(error))
        return
    if not rows:
        toast.info('No TimeLiner tasks', 'Add tasks in TimeLiner, or build them with TimeLiner from Excel.')
        return
    if not [r for r in rows if (r.get('attach_kind') or 'none') != 'none']:
        toast.info('No task has items attached', 'Attach items with Auto Attach or TimeLiner from Excel first.')
        return
    values = script.get_config(DEFAULTS)
    answer = ask(doc, rows, values)
    if answer is None:
        return
    values.update(dict((k, answer[k]) for k in ('basis', 'step', 'unit', 'size', 'viewpoint',
                                                 'show_unscheduled', 'mp4', 'fps', 'folder')))
    script.save_config(values)
    stem = os.path.splitext(fourd_common.doc_title(doc) or 'Untitled')[0]
    title = '%s 4D sequence' % stem
    name = naming.sanitize('%s 4D %s' % (stem, dates.today().strftime('%Y-%m-%d')), for_file=True)
    folder = paths.unique_path(os.path.join(answer['folder'], name))
    size = dict(movie.SIZES).get(answer['size'], (1920, 1080))
    saved = None
    if answer['viewpoint'] != CURRENT:
        saved = camera.find_view(answer['viewpoint'], doc)
    options = {'basis': answer['basis'], 'start': dates.parse(answer['start']), 'end': dates.parse(answer['end']),
               'step': answer['step'], 'unit': answer['unit'], 'width': size[0], 'height': size[1],
               'folder': folder, 'title': title, 'viewpoint': saved, 'show_unscheduled': answer['show_unscheduled'],
               'mp4': answer['mp4'], 'fps': answer['fps'], 'date_format': '%Y-%m-%d'}
    result = progress.run(TITLE, lambda report: movie.make(doc, rows, options, report))
    if result is progress.CANCELLED:
        return
    if not result['items']:
        toast.info('Nothing to animate', 'No attached task has dates of the kind chosen.')
        return
    detail = '%s of %s tasks in %s.' % (fourd_common.plural(result['items'], 'item'),
                                        '{:,}'.format(result['tasks']), folder)
    if result.get('mp4'):
        detail = 'Player and MP4 in %s.' % folder
    elif result.get('mp4_note') and answer['mp4']:
        detail += ' ' + result['mp4_note']
    if result['no_dates']:
        detail += ' %s had no dates.' % fourd_common.plural(result['no_dates'], 'task')
    toast.success('Made a 4D movie of %s' % fourd_common.plural(result['frames'], 'frame'), detail)
    if result.get('html'):
        fourd_common.open_file(result['html'])


run()
