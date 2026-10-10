# -*- coding: utf-8 -*-
"""Preflight Checks report: one profile's checks on the document, written as HTML and/or Excel."""
import datetime

from namo import reports

TITLE = 'Preflight Checks'
FORMATS = ('html', 'xlsx')

_TONE = {'pass': 'good', 'warn': 'warn', 'fail': 'bad', 'info': 'neutral'}
_LABEL = {'pass': 'Pass', 'warn': 'Warning', 'fail': 'Fail', 'info': 'Info'}
_XLSX_STYLE = {'pass': 'good', 'warn': 'warn', 'fail': 'bad', 'info': 'info'}
_RESULT_LEVEL = {'fail': 'error', 'warn': 'warning', 'pass': 'success', 'info': 'info'}


def default_config():
    """Profile 'Standard', an HTML file in the reports folder."""
    return reports.base_config(profile='Standard', formats=['html'])


def _formats(config):
    wanted = config.get('formats') or ['html']
    if isinstance(wanted, str):
        wanted = [wanted]
    out = [f for f in (str(w).lower().lstrip('.') for w in wanted) if f in FORMATS]
    return out or ['html']


def describe(config):
    """'Profile Standard, html' for Report Templates and Scheduled Reports."""
    return 'Profile %s, %s' % (config.get('profile') or 'Standard', ' and '.join(_formats(config)))


def write_html(path, checks, profile_name, doc_name, user):
    """A standalone checklist report."""
    from namo import htmlreport, preflight
    s = preflight.summarize(checks)
    report = htmlreport.Report('Preflight', subtitle=doc_name,
                               meta=[('Profile', profile_name), ('Run by', user),
                                     ('Date', datetime.datetime.now().strftime('%Y-%m-%d %H:%M'))])
    report.kpis([('Passed', s['passed'], 'good' if s['passed'] else None),
                 ('Warnings', s['warnings'], 'warn' if s['warnings'] else None),
                 ('Failures', s['failures'], 'bad' if s['failures'] else None)])
    rows = [[report.status(_LABEL[c['level']], _TONE[c['level']]), c['name'], c['detail']]
            for c in checks]
    report.table(['Result', 'Check', 'Detail'], rows,
                 cell_html=set((i, 0) for i in range(len(rows))), numeric=[],
                 caption='Checks in profile %s' % profile_name)
    return report.save(path)


def write_xlsx(path, checks, profile_name, doc_name, user):
    """One sheet: result, check, detail, with the result cell washed by level."""
    from namo import xlsx
    wb = xlsx.Workbook(title='Preflight %s' % doc_name, author=user)
    ws = wb.sheet('Preflight')
    ws.title('Preflight: %s' % doc_name, span=3)
    ws.subtitle('Profile %s, %s' % (profile_name, datetime.datetime.now().strftime('%Y-%m-%d %H:%M')), span=3)
    ws.columns([('Result', 12, None), ('Check', 40, None), ('Detail', 90, 'wrap')])
    for check in checks:
        ws.row([_LABEL[check['level']], check['name'], check['detail']],
               styles=[_XLSX_STYLE[check['level']], None, 'wrap'])
    ws.autofilter()
    return wb.save(path)


def run(config, doc=None, interactive=True, progress=None):
    """Runs the profile and writes the files. Never shows anything itself."""
    from namo import config as namo_config
    from namo import preflight
    name = config.get('profile') or preflight.DEFAULT_NAME
    profile = preflight.load_profile(name)
    if profile is None:
        return reports.result('error', 'There is no preflight profile called %s' % name,
                              'Pick a profile that exists, or save one with Shift+Click on Preflight.')
    checks = preflight.run_profile(profile, doc=doc, progress=progress)
    doc_name = preflight.document_name(doc)
    user = namo_config.user_name()
    written = []
    for fmt in _formats(config):
        path = reports.output_path(config, 'Preflight', fmt, values={'profile': profile['name']})
        try:
            if fmt == 'html':
                written.append(write_html(path, checks, profile['name'], doc_name, user))
            else:
                written.append(write_xlsx(path, checks, profile['name'], doc_name, user))
        except (IOError, OSError) as error:
            return reports.result('error', 'Could not write the preflight report',
                                  '%s: %s. Close the file if it is open, then try again.'
                                  % (path, error), paths=written)
    level, message, detail = preflight.toast_text(checks)
    summary = preflight.summarize(checks)
    out = reports.result(_RESULT_LEVEL[summary['level']], message, detail or '', paths=written)
    out['checks'] = checks
    out['profile'] = profile['name']
    return out
