# -*- coding: utf-8 -*-
"""TimeLiner Export: every TimeLiner task to a styled workbook (outline, dates, durations,
type, progress, status, attachments, user columns)."""
from namo import reports

TITLE = 'TimeLiner Export'


def default_config():
    """'count_items': resolve each attachment to count its items (sets and searches are
    evaluated, which takes a while on big models)."""
    return reports.base_config(count_items=True)


def describe(config):
    return 'Every task%s' % (', with attached item counts' if config.get('count_items') else '')


def run(config, doc=None, interactive=True, progress=None):
    from namo import config as namo_config, dates, fourd_common, timeliner
    try:
        rows = timeliner.snapshot(doc)
    except RuntimeError as error:
        return reports.result('error', 'TimeLiner is not available', str(error))
    if not rows:
        return reports.result('info', 'No TimeLiner tasks',
                              'Add tasks in TimeLiner, or build them with TimeLiner from Excel.')
    counts = {}
    if config.get('count_items', True):
        attached = [i for i, r in enumerate(rows) if (r.get('attach_kind') or 'none') != 'none']
        for done, index in enumerate(attached):
            if progress:
                progress(0.9 * done / float(len(attached) or 1),
                         'Counting items of task %s of %s' % ('{:,}'.format(done + 1),
                                                              '{:,}'.format(len(attached))))
            collection = timeliner.selected_items(rows[index]['task'], doc)
            counts[index] = collection.Count if collection is not None else 0
    if progress:
        progress(0.95, 'Writing the workbook')
    table = timeliner.export_rows(rows, counts, dates.today())
    title = 'TimeLiner tasks'
    subtitle = '%s, %s tasks, exported %s' % (fourd_common.doc_title(doc) or 'Untitled',
                                             '{:,}'.format(len(rows)), dates.format(dates.now()))
    path = reports.output_path(config, TITLE, 'xlsx')
    try:
        timeliner.write_export_xlsx(path, table, title, subtitle, author=namo_config.user_name())
    except (IOError, OSError) as error:
        return reports.result('error', 'Could not write the workbook',
                              'Close it in Excel, then try again. %s' % error)
    leaves = len([r for r in rows if not r.get('has_children')])
    return reports.result('success', 'Exported %s' % fourd_common.plural(len(rows), 'task'),
                          '%s leaf tasks. %s' % ('{:,}'.format(leaves), path), paths=[path])
