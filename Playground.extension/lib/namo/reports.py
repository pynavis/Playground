# -*- coding: utf-8 -*-
"""The registry of automation-ready reports, and the helpers every report shares.

Each report tool keeps its logic in lib\\namo\\rep_<id>.py, so the ribbon button, Report
Templates, Scheduled Reports, macros and `pynavis run` can all produce it, the last
three with no dialog at all. A rep_<id>.py module provides:

    TITLE = 'Clash Excel Report'
    def default_config():                  # JSON-serialisable dict; includes 'folder'
        return reports.base_config(...)    #   ('' = %APPDATA%\\pyNavis\\playground\\reports) and
                                           #   'name_template' ('{report} {date}')
    def describe(config):                  # one line for lists
    def run(config, doc=None, interactive=True, progress=None):
        # interactive False: NO dialogs, prompts or windows (pynavis run, schedules, macros)
        # progress(fraction 0..1, label) may be None; raise reports.Cancelled to stop
        # returns {'level': 'success'|'info'|'warning'|'error', 'message': str,
        #          'detail': str, 'paths': [files written]}

    result = reports.run('clash_excel', {'tests': ['Ducts vs Pipes']}, interactive=False)

reports.run merges the given config over default_config(), never raises (a missing
module, a crash or a cancel all come back as a result dict, crashes logged with their
traceback), and adds 'report', 'title' and 'seconds' to the result. A cancel also sets
result['cancelled'] = True: interactive callers must then exit WITHOUT a toast
(cancelling is silent by house rule); automation may log it.

Pure stdlib (modules are imported on demand).
"""
import os
import time
import traceback

from namo import naming, paths, session

REGISTRY = [
    ('property_export', 'Property Export', 'rep_property_export'),
    ('model_tree', 'Model Tree Export', 'rep_model_tree'),
    ('count_by_property', 'Count by Property', 'rep_count_by_property'),
    ('data_validation', 'Data Validation', 'rep_data_validation'),
    ('clash_excel', 'Clash Excel Report', 'rep_clash_excel'),
    ('clash_html', 'Clash HTML Dashboard', 'rep_clash_html'),
    ('clash_matrix', 'Clash Count Matrix', 'rep_clash_matrix'),
    ('clash_delta', 'Clash Delta', 'rep_clash_delta'),
    ('clash_trends', 'Clash Trends', 'rep_clash_trends'),
    ('per_trade', 'Per-Trade Reports', 'rep_per_trade'),
    ('coordination', 'Coordination Report', 'rep_coordination'),
    ('kpi_export', 'KPI Export', 'rep_kpi_export'),
    ('health_check', 'Model Health Check', 'rep_health_check'),
    ('session_stats', 'Session Stats', 'rep_session_stats'),
    ('stale_files', 'Stale File Alert', 'rep_stale_files'),
    ('preflight', 'Preflight Checks', 'rep_preflight'),
    ('timeliner_export', 'TimeLiner Export', 'rep_timeliner_export'),
    ('schedule_health', 'Schedule Health', 'rep_schedule_health'),
    ('quick_takeoff', 'Quick Takeoff', 'rep_quick_takeoff'),
    ('zone_takeoff', 'Zone Takeoff', 'rep_zone_takeoff'),
    ('viewpoint_images', 'Viewpoints to Images', 'rep_viewpoint_images'),
    ('batch_pdf', 'Batch PDF Printer', 'rep_batch_pdf'),
]

LEVELS = ('success', 'info', 'warning', 'error')
DEFAULT_NAME_TEMPLATE = '{report} {date}'

# Where rep_<id>.py files are looked for (a test seam: point it at a scratch folder).
MODULE_DIR = os.path.dirname(os.path.abspath(__file__))


class Cancelled(Exception):
    """Raise from a report (or its progress callback) to stop; run() reports it as
    'info', 'Report cancelled'."""


def ids():
    """Every report id, registry order."""
    return [rid for rid, _title, _module in REGISTRY]


def entry(report_id):
    """(id, title, module) for a report id. KeyError for an id not in REGISTRY."""
    for row in REGISTRY:
        if row[0] == report_id:
            return row
    raise KeyError('Unknown report %r' % (report_id,))


def title_of(report_id):
    """The report's title from REGISTRY. KeyError for an unknown id."""
    return entry(report_id)[1]


def module_exists(report_id):
    """True when lib\\namo\\rep_<id>.py exists (no import)."""
    return os.path.exists(os.path.join(MODULE_DIR, entry(report_id)[2] + '.py'))


def module_for(report_id):
    """The imported namo.rep_<id> module. KeyError for an id not in REGISTRY,
    ImportError when the module is not built yet (or fails to import)."""
    _rid, _title, module_name = entry(report_id)
    if not os.path.exists(os.path.join(MODULE_DIR, module_name + '.py')):
        raise ImportError('The %s report is not built yet (namo.%s).'
                          % (title_of(report_id), module_name))
    return __import__('namo.' + module_name, fromlist=['run'])


def available():
    """[(id, title)] for the reports whose module exists, registry order."""
    return [(rid, title) for rid, title, module in REGISTRY
            if os.path.exists(os.path.join(MODULE_DIR, module + '.py'))]


def base_config(**extra):
    """The keys every report config starts with: {'folder': '', 'name_template':
    '{report} {date}'} plus extra."""
    config = {'folder': '', 'name_template': DEFAULT_NAME_TEMPLATE}
    config.update(extra)
    return config


def default_config(report_id):
    """module.default_config() for a report (ImportError when not built)."""
    return module_for(report_id).default_config()


def describe(report_id, config=None):
    """The module's one-line description of a config, falling back to the title."""
    try:
        module = module_for(report_id)
        merged = module.default_config()
        merged.update(config or {})
        text = module.describe(merged)
        return str(text) if text else title_of(report_id)
    except Exception:
        try:
            return title_of(report_id)
        except KeyError:
            return str(report_id)


def result(level, message, detail='', paths=None):  # noqa: shadows the module inside only
    """A report result dict: {'level', 'message', 'detail', 'paths'}."""
    return {'level': level if level in LEVELS else 'info', 'message': str(message or ''),
            'detail': str(detail or ''), 'paths': list(paths or [])}


def normalise_result(value):
    """Any return value as a valid result dict (missing keys filled, bad level 'info')."""
    if not isinstance(value, dict):
        return result('error', 'The report returned nothing', 'Expected a result dict.')
    out = result(value.get('level'), value.get('message'), value.get('detail'), value.get('paths'))
    for key in value:
        if key not in out:
            out[key] = value[key]
    return out


def _is_cancel(error):
    return isinstance(error, Cancelled) or type(error).__name__ == 'Cancelled'


def run(report_id, config, doc=None, interactive=False, progress=None):
    """Runs a report and returns its result dict (see the module docstring), plus
    'report' (id), 'title' and 'seconds'. Never raises."""
    started = time.time()
    try:
        title = title_of(report_id)
    except KeyError:
        out = result('error', 'Unknown report', 'There is no report called %s.' % report_id)
        out.update({'report': report_id, 'title': str(report_id), 'seconds': 0.0})
        return out
    try:
        module = module_for(report_id)
        merged = module.default_config()
        merged.update(config or {})
        out = normalise_result(module.run(merged, doc=doc, interactive=interactive,
                                          progress=progress))
    except ImportError as error:
        out = result('error', '%s is not available' % title, str(error))
    except Exception as error:
        if _is_cancel(error):
            out = result('info', 'Report cancelled', title)
            out['cancelled'] = True
        else:
            session.log('error', 'report %s failed:\n%s' % (report_id, traceback.format_exc()))
            out = result('error', '%s failed' % title,
                         '%s. Details are in the pyNavis log.' % (str(error) or type(error).__name__))
    out['report'] = report_id
    out['title'] = title
    out['seconds'] = round(time.time() - started, 3)
    return out


# ---- output-window pages ----------------------------------------------------------


class Page(object):
    """What a report wants in the pyNavis output window, recorded now and printed by
    show(). A report that runs behind a progress window must not touch pynavis.output
    while that window is up: the output window would open empty behind the progress
    bar (the shipped Clash Grouper notes the same), and even output.element_link opens
    it. So an interactive report records a Page and hands it over with deliver(); the
    page is printed once the progress window has closed (namo.progress.run does that
    for a result it returns; show_output() does it by hand).

        page = reports.Page('Count by Property').html(card).bar_chart(labels, values)
        page.table(rows, headers).md('Showing the first 500 rows.')
        page.later(lambda: links_html(items))     # built at show(): may call element_link
        return reports.deliver(result, page, progress)
    """

    def __init__(self, title=None):
        self.calls = []
        if title:
            self.calls.append(('title', title))

    def html(self, html):
        """Trusted HTML for output.print_html."""
        if html:
            self.calls.append(('html', html))
        return self

    def md(self, text):
        """Markdown for output.print_md."""
        if text:
            self.calls.append(('md', text))
        return self

    def table(self, rows, headers):
        """A table for output.print_table (rows of cells, header names)."""
        self.calls.append(('table', [list(row) for row in rows], list(headers)))
        return self

    def later(self, build):
        """HTML built only when the page is shown: build() -> trusted HTML. For markup that
        needs pynavis.output.element_link, which opens the output window when called."""
        self.calls.append(('later', build))
        return self

    def line_chart(self, labels, series, title=None):
        self.calls.append(('line', list(labels), dict(series), title))
        return self

    def bar_chart(self, labels, values, title=None):
        self.calls.append(('bar', list(labels), list(values), title))
        return self

    def saved(self, paths):
        """A closing line naming the files written (full paths, as text)."""
        paths = [p for p in (paths or []) if p]
        if paths:
            from namo.htmlreport import escape
            self.html(u'<div style="color:var(--muted);font-size:12px;margin:10px 0 0">%s</div>'
                      % escape('Saved to %s' % ', '.join(paths)))
        return self

    def show(self, output=None):
        """Prints everything recorded, once. output: pynavis.output (a test seam).
        Returns the number of calls printed."""
        if not self.calls:
            return 0
        if output is None:
            from pynavis import output
        calls, self.calls = self.calls, []
        for call in calls:
            kind = call[0]
            if kind == 'title':
                output.set_title(call[1])
            elif kind == 'html':
                output.print_html(call[1])
            elif kind == 'md':
                output.print_md(call[1])
            elif kind == 'table':
                output.print_table(call[1], call[2])
            elif kind == 'later':
                html = call[1]()
                if html:
                    output.print_html(html)
            elif kind == 'line':
                output.chart_line(call[1], call[2], call[3])
            elif kind == 'bar':
                output.chart_bar(call[1], call[2], call[3])
        return len(calls)


def deliver(result, page, progress):  # noqa: the result argument shadows result() inside only
    """Hands a report's output-window page over with its result: printed at once when no
    progress window can be open (progress is None), else left in result['output'] for the
    caller to show after its progress window closed. Returns result."""
    if page is not None:
        if progress is None:
            page.show()
        else:
            result['output'] = page
    return result


def show_output(result, output=None):  # noqa: as above
    """Prints and removes the page a report left in result['output']. Call it after the
    progress window has closed (namo.progress.run already does). True when a page was
    shown. Safe on anything: a result without a page, None, the CANCELLED marker."""
    if not isinstance(result, dict):
        return False
    page = result.pop('output', None)
    if page is None or not hasattr(page, 'show'):
        return False
    page.show(output)
    return True


def output_path(config, default_name, ext, values=None, unique=False):
    """Where a report writes its file: config['path'] when set (an explicit file the user
    picked; ext appended when missing), else config['folder'] (default
    %APPDATA%\\pyNavis\\playground\\reports; %VARS% and ~ expanded; created) joined with
    config['name_template'] (default '{report} {date}') rendered by namo.naming (standard
    tokens, plus {report} = default_name, plus values) and made a safe file name, then
    ext ('xlsx' or '.xlsx'). unique=True adds ' (2)'... instead of overwriting an
    existing file."""
    config = config or {}
    explicit = str(config.get('path') or '').strip()
    if explicit:
        # A file the user picked (Save As in an interactive run) wins over folder +
        # name_template; the extension is added only when it is missing.
        explicit = os.path.expanduser(os.path.expandvars(explicit))
        want = str(ext or '').strip()
        if want and not want.startswith('.'):
            want = '.' + want
        if want and not explicit.lower().endswith(want.lower()):
            explicit += want
        paths.ensure_dir(os.path.dirname(os.path.abspath(explicit)))
        return paths.unique_path(explicit) if unique else explicit
    base = str(config.get('folder') or '').strip()
    if base:
        base = os.path.expanduser(os.path.expandvars(base))
    else:
        base = os.path.join(paths.data_root(), 'reports')
    paths.ensure_dir(base)
    tokens = naming.standard_values()
    tokens['report'] = default_name
    tokens.update(values or {})
    template = str(config.get('name_template') or '').strip() or DEFAULT_NAME_TEMPLATE
    name, _missing = naming.render(template, tokens)
    name = naming.sanitize(name, for_file=True)
    ext = str(ext or '').strip()
    if ext and not ext.startswith('.'):
        ext = '.' + ext
    if ext and name.lower().endswith(ext.lower()):
        name = name[:-len(ext)]
    path = os.path.join(base, name + ext)
    return paths.unique_path(path) if unique else path
