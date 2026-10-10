# -*- coding: utf-8 -*-
"""Environment Doctor: everything that decides whether pyNavis and Playground can work on
this machine, as pass / warning / fail lines.

gather() collects facts (each probe guarded: a probe that fails becomes a warning, never
a crash); checks(facts) turns them into results (pure, unit tested); the report goes to
the output window, or as plain text to the clipboard (Shift+Click).

Facts: navisworks {product, year, api}, pynavis {version, library, runtime}, engines
{ironpython, cpython_configured, cpython_found, cpython_bundles}, roots [{path, exists}],
extensions [{name, folder, tabs, buttons, problems, hooks, startup}], libs [path],
shortcuts {count, problems}, panes {slots, dockpanes, claims}, webview2, runner,
plugins [{id, name, developer, loaded, failed, version}], config {path, exists, error},
log {path, errors}, folders [{label, path, writable}], overlay, pick.
"""
import io
import os
import sys

from namo import paths, ribbon

PASS, WARN, FAIL, INFO = 'pass', 'warning', 'fail', 'info'
LABELS = {PASS: 'Pass', WARN: 'Warning', FAIL: 'Fail', INFO: 'Info'}
BOOT_MARKER = '==== pyNavis runtime booting ===='
WEBVIEW2_GUID = '{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}'
OVERLAY_ID = 'PyNavis.Overlay.PYNV'
PICK_ID = 'PyNavis.Pick.PYNV'
LOG_TAIL_BYTES = 2 * 1024 * 1024
MAX_ERRORS = 20

# ---- pure ------------------------------------------------------------------------------------


def last_session_errors(lines, cap=MAX_ERRORS):
    """First lines of the [ERROR] entries since the last boot marker (newest last, capped
    to the last `cap`), and how many there were in all."""
    start = 0
    for index, line in enumerate(lines):
        if BOOT_MARKER in line:
            start = index
    errors = [line.rstrip() for line in lines[start:] if '[ERROR]' in line]
    return errors[-cap:], len(errors)


def plural(n, word):
    return '%s %s%s' % ('{:,}'.format(n), word, '' if n == 1 else 's')


def checks(facts):
    """[(status, area, check, detail)] in report order."""
    out = []

    def add(status, area, check, detail=''):
        out.append((status, area, check, detail))

    nav = facts.get('navisworks') or {}
    if nav.get('product'):
        add(PASS, 'Navisworks', 'Product', '%s (API %s)' % (nav['product'], nav.get('api') or '?'))
    else:
        add(WARN, 'Navisworks', 'Product', 'Could not read the Navisworks version.')
    year = nav.get('year') or 0
    if year and year < 2023:
        add(WARN, 'Navisworks', 'Release', 'Playground is built for Navisworks 2023 to 2027; this is %d.' % year)

    pn = facts.get('pynavis') or {}
    if pn.get('version'):
        add(PASS, 'pyNavis', 'Version', pn['version'])
    else:
        add(FAIL, 'pyNavis', 'Version', 'The pyNavis runtime did not answer.')
    if pn.get('library') and pn.get('version') and pn['library'] != pn['version']:
        add(WARN, 'pyNavis', 'Library', 'The pynavis library is %s but the runtime is %s: reinstall '
                                       'pyNavis so they match.' % (pn['library'], pn['version']))
    if pn.get('runtime'):
        add(INFO, 'pyNavis', 'Runtime', pn['runtime'])

    eng = facts.get('engines') or {}
    add(PASS if eng.get('ironpython') else WARN, 'Engines', 'IronPython', eng.get('ironpython') or 'Unknown')
    if eng.get('cpython_found'):
        add(PASS, 'Engines', 'CPython', eng['cpython_found'])
    elif eng.get('cpython_bundles'):
        add(FAIL, 'Engines', 'CPython', '%s need CPython and none was found%s.' % (
            plural(eng['cpython_bundles'], 'button'),
            (' at %s' % eng['cpython_configured']) if eng.get('cpython_configured') else ''))
    elif eng.get('cpython_configured'):
        add(WARN, 'Engines', 'CPython', 'config.json names %s but no Python DLL is there.' % eng['cpython_configured'])
    else:
        add(INFO, 'Engines', 'CPython', 'Not set up (only buttons with engine: cpython need it).')

    for root in facts.get('roots') or []:
        if root.get('exists'):
            add(PASS, 'Extensions', 'Root', root['path'])
        else:
            add(WARN, 'Extensions', 'Root', '%s does not exist (listed in config.json).' % root['path'])
    names = {}
    for ext in facts.get('extensions') or []:
        names.setdefault(ext['name'].lower(), []).append(ext['folder'])
        detail = '%s, %s, %s' % (plural(ext.get('tabs', 0), 'tab'), plural(ext.get('buttons', 0), 'button'),
                                 ext['folder'])
        extra = []
        if ext.get('hooks'):
            extra.append('hooks: %s' % ', '.join(ext['hooks']))
        if ext.get('startup'):
            extra.append('startup.py')
        if extra:
            detail += '; ' + '; '.join(extra)
        problems = ext.get('problems') or []
        if problems:
            add(WARN, 'Extensions', ext['name'], '%s. %s: %s' % (detail, plural(len(problems), 'problem'), problems[0]))
        else:
            add(PASS, 'Extensions', ext['name'], detail)
    for name in sorted(names):
        if len(names[name]) > 1:
            add(WARN, 'Extensions', 'Duplicate', '%s is installed %d times: %s. Only the first loads.'
                % (name, len(names[name]), '; '.join(names[name])))
    libs = facts.get('libs') or []
    if libs:
        add(INFO, 'Extensions', 'Library folders', '; '.join(libs))

    sc = facts.get('shortcuts') or {}
    problems = sc.get('problems') or []
    if 'count' in sc:
        add(PASS if not problems else WARN, 'Shortcuts', 'Active', '%s%s' % (
            plural(sc['count'], 'shortcut'), ('; %s' % plural(len(problems), 'problem')) if problems else ''))
    for problem in problems[:10]:
        add(WARN, 'Shortcuts', 'Problem', problem)

    panes = facts.get('panes') or {}
    if 'slots' in panes:
        claimed = len(panes.get('dockpanes') or [])
        status = PASS if claimed <= panes['slots'] else WARN
        detail = '%s, %s' % (plural(panes['slots'], 'panel slot'), plural(claimed, 'dock panel'))
        if status == WARN:
            detail += ': add slots with Panel slots on the pyNavis tab, then restart Navisworks.'
        add(status, 'Panels', 'Slots', detail)

    if facts.get('webview2') is not None:
        if facts['webview2']:
            add(PASS, 'Windows', 'WebView2 runtime', facts['webview2'])
        else:
            add(WARN, 'Windows', 'WebView2 runtime', 'Not found: the output window falls back to plain text.')
    if facts.get('runner') is not None:
        add(PASS if facts['runner'] else INFO, 'pyNavis', 'Runner',
            facts['runner'] or 'pynavis.exe is not installed (only needed for pynavis run).')

    plugins = facts.get('plugins')
    if plugins is not None:
        loaded = [p for p in plugins if p.get('loaded')]
        add(INFO, 'Add-ins', 'Loaded', '%s of %s registered' % ('{:,}'.format(len(loaded)), '{:,}'.format(len(plugins))))
        failed = [p for p in plugins if p.get('failed')]
        for plugin in failed[:10]:
            add(WARN, 'Add-ins', plugin.get('name') or plugin.get('id'), 'Failed to start (%s).' % plugin.get('id'))
        ids = {}
        for plugin in plugins:
            if (plugin.get('developer') or '').upper() == 'PYNV':
                ids[plugin.get('id', '').lower()] = ids.get(plugin.get('id', '').lower(), 0) + 1
        dup = sorted(k for k, n in ids.items() if n > 1)
        if dup:
            add(FAIL, 'Add-ins', 'pyNavis loader', 'Registered more than once: %s. Uninstall the extra copy.' % ', '.join(dup))
        others = sorted(set(p.get('name') or p.get('id') for p in loaded
                            if (p.get('developer') or '').upper() not in ('ADSK', 'PYNV')))
        if others:
            add(INFO, 'Add-ins', 'Third party', ', '.join(others[:30]))

    cfg = facts.get('config') or {}
    if cfg:
        if cfg.get('error'):
            add(FAIL, 'Settings', 'config.json', cfg['error'])
        elif cfg.get('exists'):
            add(PASS, 'Settings', 'config.json', cfg.get('path'))
        else:
            add(INFO, 'Settings', 'config.json', 'Not created yet (pyNavis uses its defaults).')

    log = facts.get('log') or {}
    if 'errors' in log:
        errors = log['errors']
        total = log.get('total', len(errors))
        if not total:
            add(PASS, 'Log', 'Errors this session', 'None in %s' % log.get('path', 'the log'))
        else:
            add(WARN, 'Log', 'Errors this session', '%s; the latest are below. Log: %s'
                % (plural(total, 'error'), log.get('path', '')))
            for line in errors:
                add(WARN, 'Log', 'Error', line[:300])

    for folder in facts.get('folders') or []:
        add(PASS if folder.get('writable') else FAIL, 'Folders', folder['label'],
            folder['path'] if folder.get('writable') else '%s is not writable.' % folder['path'])

    for key, label in (('overlay', 'View overlay'), ('pick', 'Point picking')):
        if facts.get(key) is not None:
            add(PASS if facts[key] else WARN, 'pyNavis', label,
                'Available' if facts[key] else 'Not registered: redeploy pyNavis and restart Navisworks.')
    return out


def totals(results):
    counts = {PASS: 0, WARN: 0, FAIL: 0, INFO: 0}
    for status, _a, _c, _d in results:
        counts[status] = counts.get(status, 0) + 1
    return counts


def headline(results):
    counts = totals(results)
    if counts[FAIL]:
        return 'error', '%s, %s' % (plural(counts[FAIL], 'problem'), plural(counts[WARN], 'warning'))
    if counts[WARN]:
        return 'warning', 'Healthy, with %s' % plural(counts[WARN], 'warning')
    return 'success', 'Everything checks out'


def text_report(results, stamp=''):
    """The plain-text report (for the clipboard and support emails)."""
    lines = ['Playground Environment Doctor%s' % ((' ' + stamp) if stamp else ''), '']
    width = max([len(a) for _s, a, _c, _d in results] + [4])
    for status, area, check, detail in results:
        lines.append('%-7s %-*s %s%s' % (LABELS[status].upper(), width, area, check,
                                         (': ' + detail) if detail else ''))
    counts = totals(results)
    lines.append('')
    lines.append('%d pass, %d warning, %d fail, %d info' % (counts[PASS], counts[WARN], counts[FAIL], counts[INFO]))
    return '\n'.join(lines) + '\n'


def probe_writable(folder):
    """True when a file can be created and removed in folder (created if missing)."""
    try:
        paths.ensure_dir(folder)
        probe = os.path.join(folder, '.playground-write-test-%d' % os.getpid())
        with open(probe, 'wb') as handle:
            handle.write(b'ok')
        os.remove(probe)
        return True
    except Exception:
        return False


def read_log_tail(path, limit=LOG_TAIL_BYTES):
    """The last `limit` bytes of the log as lines ([] when missing)."""
    if not path or not os.path.exists(path):
        return []
    try:
        size = os.path.getsize(path)
        with io.open(path, 'rb') as handle:
            if size > limit:
                handle.seek(size - limit)
            data = handle.read()
        lines = data.decode('utf-8', 'replace').splitlines()
        return lines[1:] if size > limit else lines      # the first one was cut
    except Exception:
        return []


# ---- gathering (Navisworks and the runtime) ----------------------------------------------------


def _try(fn, default=None):
    try:
        return fn()
    except Exception:
        return default


def product_name(runtime_name, year):
    """'Navisworks Manage 2026' from the runtime product name and the host year (the
    year added only when the name does not already carry it)."""
    name = (runtime_name or 'Navisworks').strip() or 'Navisworks'
    if year and str(year) not in name:
        name = '%s %d' % (name, year)
    return name


def _navisworks():
    from pynavis._api import Application
    version = Application.Version
    year = _try(lambda: int(ribbon._runtime().HostYear), 0)
    return {'product': product_name(str(version.RuntimeProductName or ''), year),
            'api': '%d.%d' % (version.ApiMajor, version.ApiMinor), 'year': year,
            'build': int(version.Build)}


def _pynavis():
    ribbon._runtime()
    from PyNavis.Runtime import PyNavisVersion
    out = {'version': str(PyNavisVersion.Product), 'runtime': str(PyNavisVersion.RuntimePath)}
    try:
        import pynavis
        out['library'] = str(pynavis.__version__)
    except Exception:
        pass
    return out


def _engines(cfg_root, buttons):
    out = {'ironpython': sys.version.split('\n')[0]}
    configured = cfg_root.get('cpython') if isinstance(cfg_root, dict) else None
    out['cpython_configured'] = configured or ''
    found = _try(lambda: _cpython(configured), None)
    out['cpython_found'] = found or ''
    out['cpython_bundles'] = len([b for b in buttons if (b.get('engine') or '').lower() == 'cpython'])
    return out


def _cpython(configured):
    ribbon._runtime()
    from PyNavis.Runtime.Engine import CPythonLocator
    found = CPythonLocator.Resolve(configured)
    return str(found) if found else ''


def _extensions():
    out = []
    for ext in ribbon.extensions():
        tabs = list(ext.Tabs)
        buttons = 0
        for tab in tabs:
            for panel in tab.Panels:
                buttons += len(list(panel.Buttons))
        out.append({'name': str(ext.Name), 'folder': str(ext.Directory), 'tabs': len(tabs),
                    'buttons': buttons, 'problems': [str(p) for p in ext.Problems],
                    'hooks': sorted(str(h.EventName) for h in ext.Hooks),
                    'startup': bool(ext.StartupScriptPath)})
    return out


def _roots(cfg_root):
    listed = cfg_root.get('extensions') if isinstance(cfg_root, dict) else None
    out = []
    for path in listed or []:
        if isinstance(path, str):
            out.append({'path': path, 'exists': os.path.isdir(path)})
    default = os.path.join(paths.appdata(), 'pyNavis', 'extensions')
    if os.path.isdir(default) and default.lower() not in [r['path'].lower() for r in out]:
        out.append({'path': default, 'exists': True})
    return out


def _libs(roots):
    found = []
    for root in roots:
        if not root['exists']:
            continue
        for name in sorted(os.listdir(root['path'])):
            full = os.path.join(root['path'], name)
            if name.lower().endswith('.lib') and os.path.isdir(full):
                found.append(full)
    return found


def _shortcuts(cfg_root, buttons):
    from namo import hotkeys
    overrides = hotkeys.overrides_of(cfg_root) if isinstance(cfg_root, dict) else {}
    allow = hotkeys.allow_bare_of(cfg_root) if isinstance(cfg_root, dict) else False
    bound, problems = ribbon.resolve_bindings(
        [{'key': b['key'], 'shortcut': b.get('default') or None} for b in buttons], overrides, allow)
    return {'count': len(bound), 'problems': problems}


def _panes():
    from pynavis import panes
    keys = []
    try:
        from PyNavis.Runtime.Bundles import DockPaneModel
        for ext in ribbon.extensions():
            for tab in ext.Tabs:
                for panel in tab.Panels:
                    for item in list(panel.Items) + list(panel.Slideout):
                        if isinstance(item, DockPaneModel):
                            keys.append(str(item.BundleKey))
    except Exception:
        pass
    return {'slots': int(panes.slot_count()), 'dockpanes': keys}


def _webview2():
    import clr
    clr.AddReference('mscorlib')
    from Microsoft.Win32 import Registry
    for hive, sub in ((Registry.LocalMachine, 'SOFTWARE\\WOW6432Node\\Microsoft\\EdgeUpdate\\Clients\\'),
                      (Registry.LocalMachine, 'SOFTWARE\\Microsoft\\EdgeUpdate\\Clients\\'),
                      (Registry.CurrentUser, 'Software\\Microsoft\\EdgeUpdate\\Clients\\')):
        key = hive.OpenSubKey(sub + WEBVIEW2_GUID)
        if key is not None:
            try:
                value = key.GetValue('pv')
                if value and str(value) != '0.0.0.0':
                    return str(value)
            finally:
                key.Close()
    return ''


def _plugins():
    from pynavis._api import Application
    out = []
    for record in Application.Plugins.PluginRecords:
        item = {'id': str(record.Id), 'name': str(record.DisplayName or record.Name),
                'developer': str(record.DeveloperId), 'loaded': bool(record.IsLoaded),
                'failed': bool(record.HasFailedCreate)}
        if record.IsLoaded:
            item['version'] = _try(lambda: str(record.LoadedPlugin.GetType().Assembly.GetName().Version), '')
        out.append(item)
    return out


def _plugin_present(plugin_id):
    from pynavis._api import Application
    return Application.Plugins.FindPlugin(plugin_id) is not None


def gather():
    """Every fact the checks use; probes that fail leave their fact out."""
    from namo import hotkeys
    facts = {}
    config_path = ribbon.user_config_path()
    cfg_root, cfg_error = hotkeys.read_config(config_path)
    facts['config'] = {'path': config_path, 'exists': os.path.exists(config_path), 'error': cfg_error}
    cfg_root = cfg_root or {}
    buttons = _try(ribbon.buttons, []) or []
    facts['navisworks'] = _try(_navisworks, {}) or {}
    facts['pynavis'] = _try(_pynavis, {}) or {}
    facts['engines'] = _try(lambda: _engines(cfg_root, buttons), {}) or {}
    facts['roots'] = _try(lambda: _roots(cfg_root), []) or []
    facts['extensions'] = _try(_extensions, []) or []
    facts['libs'] = _try(lambda: _libs(facts['roots']), []) or []
    facts['shortcuts'] = _try(lambda: _shortcuts(cfg_root, buttons), {}) or {}
    facts['panes'] = _try(_panes, {}) or {}
    facts['webview2'] = _try(_webview2, None)
    runner = os.path.join(paths.appdata(), 'pyNavis', 'cli', 'pynavis.exe')
    facts['runner'] = runner if os.path.exists(runner) else ''
    facts['plugins'] = _try(_plugins, None)
    facts['overlay'] = _try(lambda: _plugin_present(OVERLAY_ID), None)
    facts['pick'] = _try(lambda: _plugin_present(PICK_ID), None)
    log_path = os.path.join(paths.appdata(), 'pyNavis', 'logs', 'pyNavis.log')
    errors, total = last_session_errors(read_log_tail(log_path))
    facts['log'] = {'path': log_path, 'errors': errors, 'total': total}
    folders = [('Playground data', paths.data_root()),
               ('pyNavis settings', os.path.join(paths.appdata(), 'pyNavis', 'settings')),
               ('User extensions', os.path.join(paths.appdata(), 'pyNavis', 'extensions'))]
    shared = paths.shared_root()
    reachable = bool(shared) and paths.team_available()
    if reachable:
        folders.append(('Team folder', paths.team_root()))
    facts['folders'] = [{'label': label, 'path': path, 'writable': probe_writable(path)}
                        for label, path in folders]
    if shared and not reachable:
        facts['folders'].append({'label': 'Team folder', 'path': shared, 'writable': False})
    return facts


def print_report(results):
    from pynavis import output
    output.set_title('Environment Doctor')
    counts = totals(results)
    output.print_md('# Environment Doctor\n\n%d pass, %d warning, %d fail. '
                    'Shift+Click Environment Doctor to copy this report as text.'
                    % (counts[PASS], counts[WARN], counts[FAIL]))
    order = {FAIL: 0, WARN: 1, PASS: 2, INFO: 3}
    if counts[FAIL] or counts[WARN]:
        output.print_md('## Needs attention')
        output.print_table([[LABELS[s], a, c, d] for s, a, c, d in
                            sorted([r for r in results if r[0] in (FAIL, WARN)], key=lambda r: order[r[0]])],
                           ['Result', 'Area', 'Check', 'Detail'])
    output.print_md('## Every check')
    output.print_table([[LABELS[s], a, c, d] for s, a, c, d in results], ['Result', 'Area', 'Check', 'Detail'])
