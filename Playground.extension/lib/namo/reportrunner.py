# -*- coding: utf-8 -*-
"""Report Templates: every saved template of every Playground report in one list, forms
generated from each report's default_config(), and the one runner both the ribbon and
Scheduled Reports use.

Reports are discovered through namo.reports at run time: a report whose rep_<id>.py is
not built yet still shows its templates, marked "Not built yet", and cannot be run or
given a new template until it exists. Templates live in namo.templates (tool id = report
id), so they follow Playground's shared folder when one is set.

Pure half (tested on both engines): catalog(), cells(), fields_for(), config_from(),
humanize(), kind_for(), bundle_body(), bundle_parts(), summarize(), schedule_problems().
API half: run_templates() (reports.run with interactive=False) and open_window() (the
table window behind the ribbon button).
"""
import copy
import datetime
import json
import os

from namo import naming, reports, templates

BUNDLE_FORMAT = 'playground-report-templates'
BUNDLE_VERSION = 1
FIRST_KEYS = ('folder', 'name_template', 'path')
NOT_BUILT = 'Not built yet'
JSON_FILTER = 'Playground templates (*.json)|*.json|All files (*.*)|*.*'


# =====================================================================================
# Catalog
# =====================================================================================


def catalog(registry=None, exists=None, store=None, describe=None):
    """[{'report', 'title', 'name', 'available', 'description', 'updated', 'user',
    'config'}] for every saved template, registry order then natural name order.
    Seams for tests: registry [(id, title, module)], exists(id), store(id) -> an object
    with names()/get()/info(), describe(id, config)."""
    registry = reports.REGISTRY if registry is None else registry
    exists = exists or reports.module_exists
    store = store or templates.Templates
    describe = describe or reports.describe
    rows = []
    for report_id, title, _module in registry:
        try:
            available = bool(exists(report_id))
        except Exception:
            available = False
        holder = store(report_id)
        for name in holder.names():
            config = holder.get(name) or {}
            info = holder.info(name) or {}
            if available:
                try:
                    text = describe(report_id, config)
                except Exception:
                    text = title
            else:
                text = NOT_BUILT
            rows.append({'report': report_id, 'title': title, 'name': name, 'available': available,
                         'description': text, 'updated': info.get('updated') or '',
                         'user': info.get('user') or '', 'config': config})
    return rows


def reports_list(registry=None, exists=None, store=None):
    """[{'report', 'title', 'available', 'count'}] for the New template chooser."""
    registry = reports.REGISTRY if registry is None else registry
    exists = exists or reports.module_exists
    store = store or templates.Templates
    out = []
    for report_id, title, _module in registry:
        try:
            available = bool(exists(report_id))
        except Exception:
            available = False
        out.append({'report': report_id, 'title': title, 'available': available,
                    'count': len(store(report_id).names())})
    return out


def updated_text(stamp):
    """'2026-10-05 14:30' from an ISO time, '' when there is none."""
    text = str(stamp or '')
    return text[:16].replace('T', ' ')


def cells(row):
    """The table cells of a catalog row."""
    return [row['title'], row['name'], row['description'], updated_text(row['updated']), row['user']]


HEADERS = ['Report', 'Template', 'Settings', 'Updated', 'By']


# =====================================================================================
# Forms generated from default_config()
# =====================================================================================


def humanize(key):
    """'count_items' -> 'Count items'."""
    text = str(key).replace('_', ' ').strip()
    return text[:1].upper() + text[1:]


def kind_for(value):
    """The form kind for a config value: check, int, number, text, or json (lists,
    dicts and None are edited as JSON)."""
    if isinstance(value, bool):
        return 'check'
    if isinstance(value, int):
        return 'int'
    if isinstance(value, float):
        return 'number'
    if isinstance(value, str):
        return 'text'
    return 'json'


def ordered_keys(config, defaults):
    """FIRST_KEYS present, then every other key in alphabetical order."""
    keys = set(defaults or {}) | set(config or {})
    first = [k for k in FIRST_KEYS if k in keys]
    return first + sorted(k for k in keys if k not in FIRST_KEYS)


def json_check(expected):
    """A field validator for JSON text whose value must be the same kind as expected
    (list, dict, or anything when expected is None)."""
    def check(text):
        try:
            value = json.loads(text or 'null')
        except ValueError as error:
            return 'Not valid JSON: %s.' % str(error).split(':')[0]
        if isinstance(expected, list) and not isinstance(value, list):
            return 'Enter a JSON list, like ["A", "B"].'
        if isinstance(expected, dict) and not isinstance(value, dict):
            return 'Enter a JSON object, like {"key": "value"}.'
        return None
    return check


def _float_or(value, fallback):
    for candidate in (value, fallback):
        try:
            if candidate is not None and not isinstance(candidate, bool):
                return float(candidate)
        except (TypeError, ValueError):
            continue
    return None


def fields_for(config, defaults, name='', existing=()):
    """(fields for namo.ui.form, kinds {key: kind}) for a template: its name, then one
    field per config key. existing: other template names of the same report (the
    name must not clash with one of them, ignoring case)."""
    taken = set(str(n).strip().lower() for n in existing)

    def name_check(value):
        if str(value).strip().lower() in taken:
            return 'Another template of this report already has that name.'
        return None

    fields = [{'kind': 'text', 'key': '__name', 'label': 'Template name', 'default': name,
               'required': True, 'validate': name_check}]
    kinds = {}
    for key in ordered_keys(config, defaults):
        default_value = (defaults or {}).get(key)
        value = (config or {}).get(key, default_value)
        kind = kind_for(default_value if key in (defaults or {}) else value)
        field = {'key': key, 'label': humanize(key)}
        if key == 'folder':
            text = '' if value is None else str(value)
            literal = '%' in text or text.startswith('~')
            field.update({'kind': 'text' if literal else 'folder', 'default': text,
                          'hint': 'Blank: Playground\'s reports folder. A shared folder suits team templates.'})
            kind = 'text'
        elif key == 'name_template':
            field.update({'kind': 'text', 'default': '' if value is None else str(value),
                          'hint': 'Tokens: {report} {file} {date} {time} {user} {project} {project_number}.'})
            kind = 'text'
        elif key == 'path':
            field.update({'kind': 'text', 'default': '' if value is None else str(value),
                          'hint': 'A fixed file, replaced on every run. Blank: the folder and name template decide.'})
            kind = 'text'
        elif kind == 'check':
            field.update({'kind': 'check', 'default': bool(value)})
        elif kind == 'int':
            field.update({'kind': 'int', 'required': True,
                          'default': value if isinstance(value, int) and not isinstance(value, bool) else default_value})
        elif kind == 'number':
            field.update({'kind': 'number', 'default': _float_or(value, default_value), 'required': True})
        elif kind == 'text':
            field.update({'kind': 'text', 'default': '' if value is None else str(value)})
            if key == 'scope':
                field['hint'] = 'Scheduled runs have no selection, so use model there.'
        else:
            field.update({'kind': 'textarea', 'rows': 3,
                          'default': json.dumps(value, sort_keys=True, ensure_ascii=False),
                          'validate': json_check(default_value if key in (defaults or {}) else value),
                          'hint': 'JSON.'})
        kinds[key] = kind
        fields.append(field)
    return fields, kinds


def config_from(values, kinds):
    """(template name, config) from the form's values and the kinds fields_for gave."""
    config = {}
    for key in sorted(kinds):
        kind = kinds[key]
        value = values.get(key)
        if kind == 'json':
            config[key] = json.loads(value or 'null')
        elif kind == 'check':
            config[key] = bool(value)
        elif kind == 'text':
            config[key] = '' if value is None else str(value).strip()
        else:
            config[key] = value
    return naming.sanitize(values.get('__name') or ''), config


# =====================================================================================
# Export and import of several reports' templates in one file
# =====================================================================================


def bundle_body(entries_by_report):
    """The portable file for templates of several reports: {'format', 'version',
    'reports': {report id: {name: {'config', 'updated', 'user'}}}}."""
    return {'format': BUNDLE_FORMAT, 'version': BUNDLE_VERSION,
            'reports': dict((rid, copy.deepcopy(entries_by_report[rid])) for rid in entries_by_report)}


def bundle_parts(data, known_ids=None):
    """{report id: per-tool templates body (namo.templates format)} from a bundle or a
    single-report templates file. ValueError with a sentence for anything else, or for
    reports this Playground does not know."""
    known = set(reports.ids() if known_ids is None else known_ids)
    if not isinstance(data, dict):
        raise ValueError('That file is not a Playground templates file.')
    if data.get('format') == templates.FORMAT:
        tool = str(data.get('tool') or '')
        if tool not in known:
            raise ValueError('That file holds templates for %s, which is not a Playground report.' % (tool or 'another tool'))
        return {tool: data}
    if data.get('format') != BUNDLE_FORMAT:
        raise ValueError('That file is not a Playground templates file.')
    found = data.get('reports')
    if not isinstance(found, dict):
        raise ValueError('That file holds no templates.')
    out = {}
    unknown = []
    for rid in sorted(found):
        if rid not in known:
            unknown.append(rid)
            continue
        entries = found[rid]
        if isinstance(entries, dict) and entries:
            out[rid] = {'format': templates.FORMAT, 'version': templates.VERSION, 'tool': rid,
                        'templates': entries}
    if not out:
        if unknown:
            raise ValueError('That file holds templates only for reports this Playground does not have: %s.'
                             % ', '.join(unknown))
        raise ValueError('That file holds no templates.')
    return out


def entries_of(report_id, names, store=None):
    """{name: entry} for the named templates of one report, read from its file."""
    from namo import paths
    holder = (store or templates.Templates)(report_id)
    data = paths.load_json(holder.path, {})
    found = templates._entries(data)
    out = {}
    for name in names:
        key = templates._find(found, name)
        if key is not None:
            out[key] = found[key]
    return out


# =====================================================================================
# Running
# =====================================================================================


def prepared_config(config, folder=None):
    """A template config for a run: a copy, with folder overriding the template's own
    folder (and its fixed path) when given."""
    out = copy.deepcopy(config or {})
    if folder:
        out['folder'] = folder
        if 'path' in out:
            out['path'] = ''
    return out


def run_templates(pairs, doc=None, progress=None, folder=None, interactive=False, store=None, runner=None):
    """Runs (report id, template name) pairs one after another without dialogs and
    returns their results (namo.reports result dicts plus 'template'). A missing
    template or report becomes an error result; nothing raises except a cancel
    (namo.reports.Cancelled / namo.items.Cancelled / forms.Cancelled), which stops the
    batch. progress(fraction, label) covers the whole batch."""
    store = store or templates.Templates
    runner = runner or reports.run
    results = []
    count = len(pairs)
    for index, (report_id, name) in enumerate(pairs):
        try:
            title = reports.title_of(report_id)
        except KeyError:
            title = str(report_id)
        config = store(report_id).get(name)

        def part(fraction, label='', _i=index, _name=name):
            if progress is None:
                return True
            value = (float(_i) + max(0.0, min(1.0, float(fraction or 0.0)))) / max(1, count)
            return progress(value, '%s: %s' % (_name, label) if label else _name)

        if progress is not None:
            part(0.0, 'Starting')
        if config is None:
            result = reports.result('error', 'Template not found', 'There is no %s template called %s.' % (
                title, name))
            result.update({'report': report_id, 'title': title, 'seconds': 0.0})
        else:
            result = runner(report_id, prepared_config(config, folder), doc=doc, interactive=interactive,
                            progress=part)
            if result.get('cancelled'):
                result['template'] = name
                results.append(result)
                raise reports.Cancelled()
        result['template'] = name
        results.append(result)
    if progress is not None and count:
        progress(1.0, 'Done')
    return results


def summarize(results):
    """(level, message, detail, paths) for a toast after running templates."""
    paths = []
    for result in results:
        for path in result.get('paths') or []:
            if path not in paths:
                paths.append(path)
    if not results:
        return ('info', 'Nothing ran', 'Pick one or more templates first.', paths)
    failed = [r for r in results if r.get('level') == 'error']
    warned = [r for r in results if r.get('level') == 'warning']
    if len(results) == 1:
        r = results[0]
        detail = r.get('detail') or ''
        if r.get('paths'):
            detail = r['paths'][0]
        return (r.get('level') or 'info', '%s: %s' % (r.get('template') or r.get('title'), r.get('message') or ''),
                detail or None, paths)
    message = 'Ran %d templates' % len(results)
    if failed:
        first = failed[0]
        return ('error', '%s, %d failed' % (message, len(failed)),
                '%s: %s' % (first.get('template'), first.get('message')), paths)
    if warned:
        return ('warning', '%s, %d with warnings' % (message, len(warned)),
                '%s: %s' % (warned[0].get('template'), warned[0].get('message')), paths)
    return ('success', message, files_text(paths), paths)


def files_text(paths):
    r"""'2 files written, in C:\Reports' (their one folder), or '..., the first in <folder>'
    when they went to several; None without files. The toast says where the files are."""
    if not paths:
        return None
    folders = []
    for path in paths:
        folder = os.path.dirname(path)
        if folder.lower() not in [f.lower() for f in folders]:
            folders.append(folder)
    count = '%d %s written' % (len(paths), 'file' if len(paths) == 1 else 'files')
    return '%s, %s %s' % (count, 'in' if len(folders) == 1 else 'the first in', folders[0])


def schedule_problems(pairs, rows):
    """Sentences for templates a scheduled run cannot use: missing, report not built,
    or set to the current selection (a scheduled run has none). rows: catalog()."""
    index = dict(((r['report'], r['name'].lower()), r) for r in rows)
    out = []
    for report_id, name in pairs:
        row = index.get((report_id, str(name).lower()))
        if row is None:
            out.append('The template %s no longer exists.' % name)
        elif not row['available']:
            out.append('%s is not built yet, so %s cannot run.' % (row['title'], name))
        elif str((row.get('config') or {}).get('scope') or '').lower() == 'selection':
            out.append('%s works on the current selection, which a scheduled run does not have. '
                       'Edit it to use the whole model.' % name)
    return out


# =====================================================================================
# The window (API + WPF half)
# =====================================================================================


def _table_rows(rows):
    return [{'cells': cells(r), 'value': (r['report'], r['name'])} for r in rows]


def _status(rows):
    available = len([r for r in rows if r['available']])
    unavailable = len(rows) - available
    if not rows:
        return 'No templates yet. Make one with New.'
    text = '%s %s' % ('{:,}'.format(len(rows)), 'template' if len(rows) == 1 else 'templates')
    if unavailable:
        text += ', %d for reports not built yet' % unavailable
    return text + '.'


def _toast(level, message, detail=None):
    from pynavis import toast
    toast.show(level, message, detail)


def _doc_folder(doc):
    try:
        name = str(doc.FileName or '')
        folder = os.path.dirname(name)
        if folder and os.path.isdir(folder):
            return folder
    except Exception:
        pass
    documents = os.path.join(os.path.expanduser('~'), 'Documents')
    return documents if os.path.isdir(documents) else os.path.expanduser('~')


def edit_template(report_id, name=None, config=None):
    """Shows the generated form for a template (a new one from defaults when name is
    None). Returns the stored name, or None when cancelled."""
    from namo import ui
    holder = templates.Templates(report_id)
    defaults = reports.default_config(report_id)
    title = reports.title_of(report_id)
    current = config if config is not None else copy.deepcopy(defaults)
    others = [n for n in holder.names() if name is None or n.lower() != str(name).lower()]
    suggested = name or naming.unique('%s template' % title, holder.names())
    fields, kinds = fields_for(current, defaults, suggested, others)
    answer = ui.form('%s template' % title, fields,
                     intro='These settings are used whenever the template runs, from here, '
                           'from Scheduled Reports or from a macro.',
                     ok='Save', width=560)
    if answer is None:
        return None
    new_name, new_config = config_from(answer, kinds)
    if name is not None and new_name.lower() != str(name).lower():
        holder.rename(name, new_name)
    return holder.save(new_name, new_config)


def open_window(doc):
    """The Report Templates window: list, New, Run, Edit, Duplicate, Delete, Export,
    Import. Modal; Run closes it and then runs the chosen templates. Returns when closed
    (and any run has finished)."""
    from namo import ui
    from pynavis import forms

    state = {'rows': catalog()}
    holder = {}

    def refresh(status=None):
        state['rows'] = catalog()
        holder['win'].Tag.update(_table_rows(state['rows']), status or _status(state['rows']))

    def find(value):
        for row in state['rows']:
            if (row['report'], row['name']) == tuple(value):
                return row
        return None

    def chosen(values):
        return [r for r in (find(v) for v in values) if r is not None]

    def on_new(_values):
        choices = reports_list()
        rows = [{'cells': [c['title'], 'Ready' if c['available'] else NOT_BUILT,
                           c['count']], 'value': c['report']} for c in choices]
        picked = ui.choose('New template', rows, ['Report', 'Status', 'Templates'], multiselect=False,
                           prompt='Pick the report the template is for.')
        if picked is None:
            return
        report_id = picked[0]
        if not reports.module_exists(report_id):
            _toast('info', '%s is not built yet' % reports.title_of(report_id),
                   'Templates can be made once the report is in Playground.')
            return
        stored = edit_template(report_id)
        if stored is not None:
            refresh()
            _toast('success', 'Saved the template %s' % stored, reports.title_of(report_id))

    def on_edit(values):
        rows = chosen(values)
        if not rows:
            return
        row = rows[0]
        if not row['available']:
            _toast('info', '%s is not built yet' % row['title'], 'Its templates can be edited once it exists.')
            return
        stored = edit_template(row['report'], row['name'], row['config'])
        if stored is not None:
            refresh()
            _toast('success', 'Saved the template %s' % stored, row['title'])

    def on_duplicate(values):
        rows = chosen(values)
        if not rows:
            return
        row = rows[0]
        store = templates.Templates(row['report'])
        name = forms.ask_string('Name of the copy:', naming.unique(row['name'], store.names()),
                                'Duplicate template')
        if name is None:
            return
        name = naming.sanitize(name)
        if not name:
            _toast('info', 'A template needs a name', 'Type a name for the copy.')
            return
        if name.lower() in [n.lower() for n in store.names()]:
            _toast('info', 'That name is taken', 'Pick a name no other %s template has.' % row['title'])
            return
        stored = store.save(name, row['config'])
        refresh()
        _toast('success', 'Duplicated as %s' % stored, row['title'])

    def on_delete(values):
        rows = chosen(values)
        if not rows:
            return
        what = rows[0]['name'] if len(rows) == 1 else '%d templates' % len(rows)
        if not forms.confirm('Delete %s? Scheduled Reports that use %s will report it missing.' % (
                what, 'it' if len(rows) == 1 else 'them'), 'Delete templates'):
            return
        removed = 0
        for row in rows:
            if templates.Templates(row['report']).delete(row['name']):
                removed += 1
        refresh()
        _toast('success', 'Deleted %d %s' % (removed, 'template' if removed == 1 else 'templates'))

    def on_run(values):
        rows = chosen(values)
        runnable = [r for r in rows if r['available']]
        if not runnable:
            _toast('info', 'Nothing to run', 'The selected templates belong to reports not built yet.')
            return
        # The run happens after this window has closed (see run_closed): a progress window
        # opened over a modal window leaves that window clickable and, when it closes,
        # switches Navisworks itself back on underneath the modal window.
        holder['run'] = ([(r['report'], r['name']) for r in runnable], len(rows) - len(runnable))
        holder['win'].Tag.close()

    def on_export(values):
        rows = chosen(values)
        if not rows:
            return
        by_report = {}
        for row in rows:
            by_report.setdefault(row['report'], []).append(row['name'])
        stamp = datetime.datetime.now().strftime('%Y-%m-%d')
        if len(by_report) == 1:
            report_id = list(by_report)[0]
            default = '%s templates %s.json' % (reports.title_of(report_id), stamp)
        else:
            default = 'Playground report templates %s.json' % stamp
        path = forms.save_file(JSON_FILTER, os.path.join(_doc_folder(doc), naming.sanitize(default, True)),
                               'Export templates')
        if path is None:
            return
        try:
            if len(by_report) == 1:
                report_id = list(by_report)[0]
                count = templates.Templates(report_id).export(path, by_report[report_id])
            else:
                from namo import paths as _paths
                body = bundle_body(dict((rid, entries_of(rid, by_report[rid])) for rid in by_report))
                _paths.write_json(path, body)
                count = sum(len(v) for v in body['reports'].values())
        except (IOError, OSError) as error:
            _toast('error', 'Could not export the templates', str(error))
            return
        _toast('success', 'Exported %d %s' % (count, 'template' if count == 1 else 'templates'), path)

    def on_import(_values):
        from namo import paths as _paths
        path = forms.open_file(JSON_FILTER, 'Import templates')
        if path is None:
            return
        data = _paths.load_json(path, None, move_aside=False)
        try:
            parts = bundle_parts(data)
        except ValueError as error:
            _toast('error', 'Could not import the templates', str(error))
            return
        count = 0
        temp_folder = os.path.join(_paths.data_root(), 'temp')
        for report_id in sorted(parts):
            temp = os.path.join(_paths.ensure_dir(temp_folder), 'import-%s.json' % report_id)
            try:
                _paths.write_json(temp, parts[report_id])
                count += templates.Templates(report_id).import_file(temp)
            except ValueError as error:
                _toast('error', 'Could not import the templates', str(error))
                return
            finally:
                try:
                    os.remove(temp)
                except OSError:
                    pass
        refresh()
        _toast('success', 'Imported %d %s' % (count, 'template' if count == 1 else 'templates'),
               'Names already in use got a number added.' if count else None)

    actions = [
        {'label': 'New', 'fn': on_new, 'needs_selection': False},
        {'label': 'Edit', 'fn': on_edit},
        {'label': 'Duplicate', 'fn': on_duplicate},
        {'label': 'Delete', 'fn': on_delete},
        {'label': 'Export', 'fn': on_export},
        {'label': 'Import', 'fn': on_import, 'needs_selection': False},
        {'label': 'Run', 'fn': on_run, 'primary': True},
    ]
    win = ui.build_table('Report templates', HEADERS, _table_rows(state['rows']), actions=actions,
                         on_open=lambda value: on_edit([value]), status=_status(state['rows']),
                         width=940, height=560)
    holder['win'] = win
    ui.show_modal(win)
    if holder.get('run'):
        pairs, skipped = holder['run']
        run_closed(pairs, doc, skipped)
    return win


def run_closed(pairs, doc=None, skipped=0):
    """Runs templates from the ribbon once the Report Templates window has closed: behind
    the cancellable progress window, without dialogs, then one toast naming the file and
    the file opened (one template) or shown in Explorer (several). Returns the results,
    or None when cancelled (silent)."""
    from namo import progress, ui
    outcome = progress.run('Running report templates',
                           lambda report: run_templates(pairs, doc=doc, progress=report))
    if outcome is progress.CANCELLED:
        return None
    level, message, detail, paths = summarize(outcome)
    if skipped:
        detail = ((detail + ' ') if detail else '') + '%d not run: report not built yet.' % skipped
    _toast(level, message, detail)
    if paths and level in ('success', 'warning'):
        try:
            if len(outcome) == 1 and len(paths) == 1:
                ui.open_path(paths[0])
            else:
                ui.show_in_explorer(paths[0])
        except Exception:
            _toast('warning', 'Could not open the report', paths[0])
    return outcome
