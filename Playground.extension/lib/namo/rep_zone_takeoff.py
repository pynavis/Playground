# -*- coding: utf-8 -*-
"""Zone Takeoff: quantities by zone (grid levels, zone objects, grid bays or tiles) and by
group, written to a workbook (Pivot, Zones, one sheet per zone, Notes)."""
from namo import reports

TITLE = 'Zone Takeoff'


def default_config():
    from namo import takeoff
    config = reports.base_config()
    config.update(takeoff.default_zone_config())
    config['scope'] = 'model'
    return config


def describe(config):
    from namo import takeoff
    return takeoff.describe_config(config)


def run(config, doc=None, interactive=True, progress=None):
    from namo import config as namo_config, dates, fourd_common, takeoff
    if not fourd_common.has_models(doc):
        return reports.result('info', 'No model is open', 'Open or append a model first.')
    if not config.get('zones'):
        config = dict(config, zones={'mode': 'levels'})
    try:
        result = takeoff.run(config, doc, progress)
    except ValueError as error:
        return reports.result('info', 'No zones to take off by', str(error))
    records = result['data']['records']
    if not records:
        return reports.result('info', 'Nothing to measure', 'The scope holds no objects with geometry.')
    if progress:
        progress(0.98, 'Writing the workbook')
    subtitle = '%s, %s, %s' % (fourd_common.doc_title(doc) or 'Untitled', takeoff.describe_config(config),
                               dates.format(dates.now()))
    pivot_measure = config.get('pivot_measure') or 'count'
    if pivot_measure not in result['measures']:
        pivot_measure = 'count'
    path = reports.output_path(config, TITLE, 'xlsx')
    try:
        _path, sheets, zones = takeoff.write_zone_xlsx(
            path, 'Zone takeoff', subtitle, records, result['measures'], result['unit_set'],
            result['group_titles'], result['notes'], pivot_measure, result['data']['pairs'],
            author=namo_config.user_name())
    except (IOError, OSError) as error:
        return reports.result('error', 'Could not write the workbook',
                              'Close it in Excel, then try again. %s' % error)
    level = 'warning' if result['data'].get('sampled') else 'success'
    return reports.result(level, 'Takeoff of %s in %s' % (fourd_common.plural(len(records), 'object'),
                                                          fourd_common.plural(len(zones), 'zone')),
                          result['status'], paths=[path])
