# -*- coding: utf-8 -*-
"""Quick Takeoff: counts, lengths, areas, volumes and weights grouped by one or two
properties, written to a workbook (Takeoff, Objects, Notes)."""
from namo import reports

TITLE = 'Quick Takeoff'


def default_config():
    from namo import takeoff
    config = reports.base_config()
    config.update(takeoff.default_quick_config())
    config['scope'] = 'model'            # automation has no selection to rely on
    return config


def describe(config):
    from namo import takeoff
    return takeoff.describe_config(config)


def run(config, doc=None, interactive=True, progress=None):
    from namo import config as namo_config, dates, fourd_common, takeoff
    if not fourd_common.has_models(doc):
        return reports.result('info', 'No model is open', 'Open or append a model first.')
    result = takeoff.run(config, doc, progress)
    if not result['data']['records']:
        return reports.result('info', 'Nothing to measure', 'The scope holds no objects with geometry.')
    if progress:
        progress(0.98, 'Writing the workbook')
    subtitle = '%s, %s, %s' % (fourd_common.doc_title(doc) or 'Untitled', takeoff.describe_config(config),
                               dates.format(dates.now()))
    path = reports.output_path(config, TITLE, 'xlsx')
    objects = result['data']['records'] if len(result['data']['records']) <= 50000 else None
    try:
        takeoff.write_quick_xlsx(path, 'Quick takeoff', subtitle, result['rows'], result['measures'],
                                 result['unit_set'], result['group_titles'], result['notes'],
                                 result['data']['pairs'], objects, author=namo_config.user_name())
    except (IOError, OSError) as error:
        return reports.result('error', 'Could not write the workbook',
                              'Close it in Excel, then try again. %s' % error)
    level = 'warning' if result['data'].get('sampled') else 'success'
    return reports.result(level, 'Takeoff of %s' % fourd_common.plural(len(result['data']['records']), 'object'),
                          result['status'], paths=[path])
