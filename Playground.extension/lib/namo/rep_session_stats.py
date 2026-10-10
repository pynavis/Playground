# -*- coding: utf-8 -*-
"""Session Stats: one workbook row per appended model (files, items, geometry,
primitives, fragments, extent, arrival and load time)."""
from namo import reports

TITLE = 'Session Stats'


def default_config():
    """budget: geometry items read exactly per model before sampling primitives."""
    return reports.base_config(budget=40000, xlsx=True)


def describe(config):
    return 'Every model, primitives read exactly for the first {:,} geometry items'.format(
        int(config.get('budget') or 40000))


def run(config, doc=None, interactive=True, progress=None):
    from namo import mdl_stats, modelmgmt
    from pynavis._api import Application
    document = doc if doc is not None else Application.ActiveDocument
    if document is None or not modelmgmt.has_models(document):
        return reports.result('info', 'No models to measure', 'Append models first.')
    rows = mdl_stats.collect(document, int(config.get('budget') or 40000), progress)
    total = mdl_stats.totals(rows)
    paths = []
    if config.get('xlsx', True):
        path = reports.output_path(config, TITLE, 'xlsx')
        try:
            mdl_stats.write_workbook(path, rows, '%s: %s' % (TITLE, getattr(document, 'Title', '') or ''))
            paths.append(path)
        except (IOError, OSError) as error:
            out = reports.result('error', 'Could not write the workbook',
                                 '%s. Close it in Excel, then try again.' % error)
            out.update({'rows': rows, 'totals': total})
            return out
    message = '%s, %s primitives' % (modelmgmt.plural(total['models'], 'model'),
                                     '{:,}'.format(total['primitives']))
    detail = '{:,} items, {:,} with geometry'.format(total['items'], total['geometry'])
    if total['sampled']:
        detail += '; primitives estimated on the largest models'
    out = reports.result('success', message, detail, paths=paths)
    out.update({'rows': rows, 'totals': total})
    return out
