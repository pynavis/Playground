# -*- coding: utf-8 -*-
"""Scores every appended model for units, origin distance, stray objects, element IDs, duplicates, transforms and file age."""
import os

from pynavis import doc as nwdoc
from pynavis import output, script, toast

from namo import health, mdl_output, progress, reports, rep_health_check, ui


def report_config(values, document):
    """The report config from this button's settings: the document's folder when it
    is saved and no folder was chosen."""
    config = rep_health_check.default_config()
    config.update(health.settings(values))
    if not config.get('folder'):
        filename = nwdoc.get_filename(document) or ''
        if filename and os.path.isdir(os.path.dirname(filename)):
            config['folder'] = os.path.dirname(filename)
    return config


def link_for(model, outlier_items):
    found = outlier_items.get(model['index']) or []
    outliers = model.get('outliers') or []

    def link(i):
        if i < len(found) and i < len(outliers):
            return output.element_link(found[i], outliers[i].get('name') or 'Object')
        return None
    return link


def run():
    document = nwdoc.get_doc()
    values = health.settings(script.get_config(health.DEFAULTS))
    config = report_config(values, document)
    result = progress.run('Health check', lambda report: reports.run(
        'health_check', config, doc=document, interactive=True, progress=report))
    if result is progress.CANCELLED or result.get('cancelled'):
        return
    models = result.get('models') or []
    if not models:
        toast.show(result['level'], result['message'], result['detail'] or None)
        return
    outlier_items = result.get('outlier_items') or {}
    output.set_title('Model health check')
    output.print_html(mdl_output.heading('Model health check', 1) + health.overview_html(models))
    ordered = sorted(models, key=lambda m: (m['score'], m['index']))
    for model in ordered:
        output.print_html(health.card_html(model, link_for(model, outlier_items)))
    paths = result.get('paths') or []
    for path in paths:
        output.print_html(mdl_output.path_line('Saved:', path))
    if result['level'] == 'error':
        toast.error(result['message'], result['detail'] or None)
        return
    level, message, detail = health.summary(models)
    toast.show(level, message, detail)
    html = [p for p in paths if p.lower().endswith('.html')]
    if values['open_report'] and html:
        ui.open_path(html[0])


run()
