# -*- coding: utf-8 -*-
"""Runs a Quick or Zone Takeoff configuration and shows its result window: shared by the
two takeoff buttons and Takeoff Templates."""

from namo import qty_ui

QUICK_KEY = 'playground-quick-takeoff'
ZONE_KEY = 'playground-zone-takeoff'


def run_quick(doc, config):
    return _run(doc, config, zone=False)


def run_zone(doc, config):
    return _run(doc, config, zone=True)


def _run(doc, config, zone):
    from pynavis import forms, toast
    from namo import config as namo_config
    from namo import dates, fourd_common, progress, takeoff, templates
    title = 'Zone Takeoff' if zone else 'Quick Takeoff'
    try:
        result = progress.run(title, lambda report: takeoff.run(config, doc, report))
    except ValueError as error:
        toast.info('No zones to take off by' if zone else 'Nothing to measure', str(error))
        return None
    if result is progress.CANCELLED:
        return None
    records = result['data']['records']
    if not records:
        toast.info('Nothing to measure', 'The scope holds no objects with geometry.')
        return None

    def export():
        label = 'Zone takeoff' if zone else 'Quick takeoff'
        path = fourd_common.ask_save(doc, label, 'xlsx', 'Export the takeoff')
        if path is None:
            return
        subtitle = '%s, %s, %s' % (fourd_common.doc_title(doc) or 'Untitled', takeoff.describe_config(config),
                                   dates.format(dates.now()))
        try:
            if zone:
                pivot = config.get('pivot_measure') or 'count'
                if pivot not in result['measures']:
                    pivot = 'count'
                takeoff.write_zone_xlsx(path, label, subtitle, records, result['measures'], result['unit_set'],
                                        result['group_titles'], result['notes'], pivot, result['data']['pairs'],
                                        author=namo_config.user_name())
            else:
                takeoff.write_quick_xlsx(path, label, subtitle, result['rows'], result['measures'],
                                         result['unit_set'], result['group_titles'], result['notes'],
                                         result['data']['pairs'], records if len(records) <= 50000 else None,
                                         author=namo_config.user_name())
        except (IOError, OSError) as error:
            toast.error('Could not write the workbook', 'Close it in Excel, then try again. %s' % error)
            return
        toast.success('Exported the takeoff', path)
        fourd_common.open_file(path)

    def select(records_, rows, selected):
        count = qty_ui.select_rows(records_, rows, selected, doc)
        toast.success('Selected %s' % fourd_common.plural(count, 'object'))

    def save_template():
        name = forms.ask_string('Name for this takeoff template:', default='', title=title)
        if name is None:
            return
        if not name.strip():
            toast.info('No name given', 'A template needs a name.')
            return
        tool = qty_ui.ZONE_TOOL if zone else qty_ui.QUICK_TOOL
        stored = templates.Templates(tool).save(name, config)
        toast.success('Saved the takeoff template', stored)

    window_title = 'Zone takeoff' if zone else 'Quick takeoff'
    qty_ui.show_results(window_title, ZONE_KEY if zone else QUICK_KEY, result, export, select, save_template,
                        zone=zone)
    if result['data'].get('sampled') or result['data'].get('geometry_skipped'):
        toast.warning('Takeoff of %s' % fourd_common.plural(len(records), 'object'), result['status'])
    return result
