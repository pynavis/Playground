# -*- coding: utf-8 -*-
"""Model Health Check: a scorecard per appended model, as an HTML report and a workbook.

The logic is namo.health; this module is the reports contract around it, so the
ribbon button, Report Templates, Scheduled Reports and `pynavis run` produce the same
files. The result carries 'models' (JSON-safe scored model dicts, see health.scored)
for the ribbon script to show, and, on interactive runs only, 'outlier_items'
({model index: [ModelItem]}) so far-away objects can be shown as element links.
"""
from namo import health, reports

TITLE = 'Model Health Check'
NAME_TEMPLATE = '{file} - Health check - {date}'


def default_config():
    """Report settings: health.DEFAULTS thresholds plus folder and name template."""
    config = reports.base_config(name_template=NAME_TEMPLATE)
    for key in sorted(health.DEFAULTS):
        if key not in ('folder',):
            value = health.DEFAULTS[key]
            config[key] = list(value) if isinstance(value, list) else value
    return config


def describe(config):
    cfg = health.settings(config)
    formats = ' and '.join(f.upper() if f == 'html' else 'Excel' for f in cfg['formats']) or 'no file'
    return 'Every model, origin warning at %s km, outliers at %sx, %s' % (
        health.num_text(cfg['warn_km']), health.num_text(cfg['outlier_factor']), formats)


def _doc_title(doc):
    try:
        from pynavis import doc as _doc
        return _doc.get_title(doc) or 'Untitled'
    except Exception:
        return 'Untitled'


def run(config, doc=None, interactive=True, progress=None):
    """Checks every model and writes the files config['formats'] asks for."""
    from namo import modelmgmt, naming
    if doc is None:
        from pynavis._api import Application
        doc = Application.ActiveDocument
    cfg = health.settings(config)
    if not modelmgmt.has_models(doc):
        out = reports.result('info', 'No models to check',
                             'Append models first, then run the health check.')
        out['models'] = []
        return out
    models, outlier_items = health.collect(doc, cfg, progress)
    level, message, detail = health.summary(models)
    values = {}
    standard = naming.standard_values(doc)
    if not standard.get('file'):
        values['file'] = 'Untitled'
    paths = []
    title = _doc_title(doc)
    meta = [('Document', title), ('Models', len(models)), ('Units', str(doc.Units)),
            ('Checked by', standard.get('user') or '')]
    try:
        if 'html' in cfg['formats']:
            path = reports.output_path(config, 'Health check', 'html', values)
            health.write_html(path, models, subtitle=title, meta=meta)
            paths.append(path)
        if 'xlsx' in cfg['formats']:
            path = reports.output_path(config, 'Health check', 'xlsx', values)
            health.write_xlsx(path, models, author=standard.get('user') or None)
            paths.append(path)
    except (IOError, OSError) as error:
        out = reports.result('error', 'Could not save the health check report',
                             '%s. Close the file if it is open, then try again.' % error, paths)
        out['models'] = health.json_safe(models)
        if interactive:
            out['outlier_items'] = outlier_items
        return out
    out = reports.result(level, message, detail, paths)
    out['models'] = health.json_safe(models)
    if interactive:
        out['outlier_items'] = outlier_items
    return out
