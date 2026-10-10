# -*- coding: utf-8 -*-
"""Reports which pyNavis tools are used, how often and by whom (opt-in)."""
from pynavis import forms, toast

from namo import paths, ribbon, usage


def plural(count, one, many):
    return '%s %s' % ('{:,}'.format(count), one if count == 1 else many)


def run():
    settings = usage.load_settings()
    rows = usage.read_rows(usage.report_folders(settings))
    if not settings['enabled'] and not rows:
        # Nothing recorded and recording is off: explain exactly what it keeps, then ask.
        if globals().get('__runner__'):
            toast.info('Usage Analytics is off', 'Turn it on from the ribbon; it asks first.')
            return
        agreed = forms.confirm(
            'Usage Analytics records which pyNavis tools are run: the time, your user name, this '
            'computer\'s name, the tool and how long it took. It never records document names, file '
            'paths or model data.\n\nTurn it on?', title='Usage Analytics')
        if agreed:
            usage.save_settings({'enabled': True, 'asked': True})
            toast.success('Usage Analytics is on',
                          'Run a few tools, then click it again for the report. Shift+Click turns it off.')
        return                                      # No: say nothing
    if not rows:
        toast.info('No usage recorded yet', 'Run a few tools, then click Usage Analytics again.')
        return
    summary = usage.aggregate(rows, ribbon.buttons())
    shared = settings.get('shared') and paths.team_available()
    scope = 'Everyone writing to the team folder.' if shared else 'This computer.'
    if not settings['enabled']:
        scope += ' Recording is off now: Shift+Click Usage Analytics to turn it back on.'
    usage.print_report(summary, scope)
    toast.success('Usage report: %s' % plural(summary['runs'], 'run', 'runs'),
                  '%s, %s. Shift+Click for settings and Excel export.'
                  % (plural(summary['tools'], 'tool', 'tools'), plural(summary['users'], 'person', 'people')))


run()
