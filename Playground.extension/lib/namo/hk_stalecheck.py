# -*- coding: utf-8 -*-
"""Stale File Alert handler: when a document opens and 'Check when a model opens' is on
(Stale File Alert's Shift+Click, off by default), compares every model's loaded file
with its source and toasts only when something is out of date or missing."""

TOOL = 'playground_stalefiles'
DEFAULTS = {'check_on_open': False, 'tolerance_seconds': 2.0}


def load_config():
    try:
        from pynavis import settings
        values = settings.load(TOOL, DEFAULTS)
    except Exception:
        values = dict(DEFAULTS)
    values['check_on_open'] = bool(values.get('check_on_open'))
    try:
        values['tolerance_seconds'] = max(0.0, float(values.get('tolerance_seconds')))
    except (TypeError, ValueError):
        values['tolerance_seconds'] = 2.0
    return values


def handle(name, event):
    if name != 'doc-opened':
        return
    config = load_config()
    if not config['check_on_open']:
        return
    from namo import modelmgmt
    from pynavis._api import Application
    document = Application.ActiveDocument
    if document is None or not modelmgmt.has_models(document):
        return
    rows = modelmgmt.stale_rows(document, tolerance=config['tolerance_seconds'])
    level, message, detail = modelmgmt.stale_summary(rows)
    if level != 'warning':
        return
    from pynavis import toast
    toast.warning(message, detail)
