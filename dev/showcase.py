# -*- coding: utf-8 -*-
"""Builds the Playground showcase page (one self-contained HTML file) from the extension
itself: every tool's real title, tooltip and icon in ribbon order, plus the signature
work and the build facts. Nothing on the page is typed twice: rerun after any change.

    python dev/showcase.py OUT.html [--stats dev/notes/stats.json]

stats.json (optional) carries numbers only a verify run knows:
    {"cpython_passed": n, "ipy_passed": n, "smoke_passed": n, "review_fixes": n}
"""
import base64
import html
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EXT = os.path.join(ROOT, 'Playground.extension')
sys.path.insert(0, HERE)
import check  # noqa: E402  (pyNavis' flat yaml reader + layout helpers)

KIND_LABEL = {'.toggle': 'Toggle', '.dockpane': 'Dock pane', '.nobutton': 'Shortcut only'}


def esc(text):
    return html.escape(u'%s' % (text,), quote=True)


def yaml(folder):
    return check.read_yaml(os.path.join(folder, 'bundle.yaml'))


def ordered(folder):
    """Children in pyNavis order: layout entries first, the rest by name."""
    _, layout = yaml(folder) if not folder.endswith('.extension') else check.read_yaml(
        os.path.join(folder, 'extension.yaml'))
    kids = [d for d in sorted(os.listdir(folder), key=str.lower)
            if os.path.isdir(os.path.join(folder, d)) and check.suffix_of(d)]
    by_stem = dict((check.stem(k), k) for k in kids)
    out = []
    for entry in layout or []:
        key = check.stem(entry)
        if key in by_stem and by_stem[key] not in out:
            out.append(by_stem[key])
    out += [k for k in kids if k not in out]
    return out


def title_of(folder, data):
    title = data.get('title')
    if not title:
        base = os.path.basename(folder)
        base = base[:-len(check.suffix_of(base) or '')]
        title = re.sub(r'^\d{2,}_', '', base).replace('_', ' ')
    return title.replace('\\n', ' ').replace('  ', ' ').strip()


def icon(folder, name):
    path = os.path.join(folder, name)
    if not os.path.exists(path):
        return ''
    with open(path, 'rb') as handle:
        return 'data:image/png;base64,' + base64.b64encode(handle.read()).decode('ascii')


def tool(folder, kind, parent=None):
    data, _ = yaml(folder)
    return {
        'title': title_of(folder, data),
        'tooltip': (data.get('tooltip') or '').replace('\\n', ' '),
        'shortcut': data.get('shortcut') or '',
        'kind': KIND_LABEL.get(kind, ''),
        'parent': parent,
        'light': icon(folder, 'icon.png'),
        'dark': icon(folder, 'icon.dark.png') or icon(folder, 'icon.png'),
    }


def collect():
    tabs = []
    for tab in ordered(EXT):
        if not tab.lower().endswith('.tab'):
            continue
        tab_path = os.path.join(EXT, tab)
        panels = []
        for panel in ordered(tab_path):
            panel_path = os.path.join(tab_path, panel)
            tools = []
            for item in ordered(panel_path):
                path = os.path.join(panel_path, item)
                kind = check.suffix_of(item)
                if kind in ('.stack', '.slideout'):
                    for child in ordered(path):
                        tools.append(tool(os.path.join(path, child), check.suffix_of(child)))
                elif kind in ('.pulldown', '.splitbutton', '.splitpushbutton'):
                    menu = title_of(path, yaml(path)[0])
                    for child in ordered(path):
                        tools.append(tool(os.path.join(path, child), check.suffix_of(child), menu))
                else:
                    tools.append(tool(path, kind))
            panels.append({'title': title_of(panel_path, {}), 'tools': tools})
        tabs.append({'title': title_of(tab_path, {}), 'panels': panels})
    return tabs


def facts(stats):
    lib = os.path.join(EXT, 'lib', 'namo')
    modules = [n for n in os.listdir(lib) if n.endswith('.py') and n != '__init__.py']
    lines = 0
    for folder, dirs, files in os.walk(EXT):
        dirs[:] = [d for d in dirs if d != '__pycache__']
        for name in files:
            if name.endswith('.py') or name.endswith('.xaml'):
                with io.open(os.path.join(folder, name), encoding='utf-8') as handle:
                    lines += sum(1 for _ in handle)
    tests = 0
    test_dir = os.path.join(HERE, 'tests')
    for name in os.listdir(test_dir):
        if (name.startswith('test_') or name.startswith('smoke_')) and name.endswith('.py'):
            with io.open(os.path.join(test_dir, name), encoding='utf-8') as handle:
                tests += len(re.findall(r'^def test_', handle.read(), re.M))
    api = 0
    for name in os.listdir(os.path.join(HERE, 'api')):
        with io.open(os.path.join(HERE, 'api', name), encoding='utf-8', errors='replace') as handle:
            api += sum(1 for _ in handle)
    out = {'modules': len(modules), 'lines': lines, 'tests': tests, 'api_lines': api}
    out.update(stats or {})
    return out


HIGHLIGHTS = [
    ('Coordinate', 'Clash Reports', 'Clash reports people actually open',
     'A styled workbook per run: a summary in Clash Detective colours, one sheet per test, '
     'a thumbnail anchored to every row so filtering hides it with its clash, an All clashes '
     'sheet for pivots. The same report also comes as an offline dashboard and as a '
     'trade-against-trade count matrix.',
     'The workbook writer opens in Excel 16 with no repair prompt; reports come out byte-identical from CPython and IronPython.'),
    ('Project', 'Exchange', 'IFC4 from any selection',
     'Tessellated geometry, storeys from levels, classes mapped from Revit categories, colours, '
     'one property set per Navisworks tab, and GlobalIds derived from Revit UniqueIds the way '
     'Revit\'s own exporter derives them. glTF, OBJ, STL and DXF from the same triangles.',
     'ifcopenshell validate with EXPRESS rules: 0 issues. pygltflib and ezdxf read the other formats back.'),
    ('Coordinate', 'Issues', 'An issue register that travels inside the model',
     'A dock pane register with stamps (RFI, Hold, Verify, Safety), 3D pins, comments, '
     'screenshots and a meeting mode that writes minutes. Issues live on this computer, in a '
     'shared team folder, or inside the NWF itself through the document\'s own SQLite database.',
     'Pane, meeting window and editors built and driven under IronPython with sample issues.'),
    ('Coordinate', 'BCF', 'BCF 2.1 and 3.0, both directions',
     'Issues or clash groups out to a .bcfzip with cameras converted to metres, IFC GUID '
     'components and snapshots; BCF 2.0, 2.1 and 3.0 back in as issues and saved viewpoints, '
     'merged by topic GUID.',
     'Write, read and compare round trips on both engines; structure checked against schemas reconstructed in the tests.'),
    ('Dev', 'Automate', 'One keystroke to anything',
     'Ctrl+Shift+P searches every pyNavis and Playground button, the native Navisworks ribbon, saved '
     'views and selection sets, and runs the choice once the palette closes. Record any chain of '
     'tools as a macro, replay it, or turn it into a ribbon button. Native commands get hotkeys '
     'through generated shortcut-only buttons.',
     'Chord grammar cross-checked against pyNavis\' own ChordParser and ShortcutMap.'),
    ('Project', 'Field', 'A QR encoder written from the standard',
     'QR Tagger encodes element identities or URLs with its own ISO 18004 encoder (Reed-Solomon, '
     'masks, format and version words), writes a PNG per object and a printable A4 label sheet, '
     'and stamps the payload onto each element.',
     'Reproduces the published ISO test vectors; every symbol decodes with OpenCV.'),
    ('Project', '4D', '4D movies without the TimeLiner player',
     'Builds TimeLiner from a spreadsheet, attaches items by rules, then renders a dated movie by '
     'computing each item\'s state per frame (hidden, building, built, demolished) from the '
     'schedule. Visibility, colours and camera come back exactly, even on cancel.',
     'Frame planning and schedule validation unit tested on both engines.'),
    ('Views', 'Navigate', 'Two Navisworks windows, one camera',
     'Camera Sync mirrors the view between two sessions on one machine, for comparing two model '
     'versions side by side, with echo protection and clean shutdown. Sheet Overlay lays a 2D '
     'DXF plan onto the 3D model at any level.',
     'DXF parser (arcs, bulges, blocks, arrays) and the sync protocol unit tested.'),
    ('Model', 'Find', 'Find anything as you type',
     'Quick Find indexes every element by name, Element ID, category, type, mark, level and IFC '
     "GlobalId, saves the index beside the model's file signature so the next session opens "
     'instantly, and ranks matches fuzzily as you type. Enter selects and zooms.',
     'Ranking 20,000 entries measured 70 to 150 ms on IronPython 3.4.'),
    ('Dev', 'Reports', 'Reports on a schedule',
     'Twenty-two reports share one contract, so any of them runs from a saved template, a macro, '
     'or a Windows scheduled task through pyNavis\' headless runner, and mails the result. The '
     'SMTP password is stored with Windows DPAPI, never as text.',
     'Mail exchange proven against a loopback SMTP server on both engines.'),
]

PIPELINE = [
    ('Read the API before writing a line',
     'A reflection dump of the Navisworks 2026 assemblies, one member per line, so every call '
     'is checked against what exists, static or instance, with its overloads.'),
    ('Build the shared library first',
     'Styled Excel, HTML, PDF and PNG writers; stores that work locally, on a team share or '
     'inside the model; a rules engine; units; cameras, images, clash data, paint and a themed '
     'WPF kit, each with a pure half tested outside Navisworks.'),
    ('Eleven build groups, one panel each',
     'Every group owned its panels, modules, icons, tests and notes, and wrote down what only a '
     'click in Navisworks can confirm.'),
    ('Independent review of every tab',
     'Reviewers read each tool as IronPython would run it inside Navisworks and fixed what '
     'tests cannot see: wrong overloads, undo steps, late event handlers, missing references.'),
    ('Verify headlessly, every stage',
     'pyNavis\' bundle contract and house rules, pytest on CPython, the same tests on the '
     'IronPython 3.4 that pyNavis ships, WPF windows built for real, every module imported in a '
     'fresh engine, and pyNavis\' own BundleParser building the ribbon.'),
    ('Then the first session in Navisworks',
     'An ordered in-app checklist ships with it. Nothing here has run inside Navisworks yet.'),
]


CSS = u'''
/* Layout: a drawing sheet. Tabs are grid lines A-E with bubbles, the hero is a title
   block, tools sit in hairline schedules. */
:root {
  --paper: #f4f5f1; --sheet: #fbfbf9; --ink: #16222b; --muted: #56656f; --rule: #c9d2d7;
  --grid: #e2e7e3; --accent: #0a62c2; --spark: #d9302c; --chip: #e9edef;
  --display: "Barlow Condensed", "Arial Narrow", "Segoe UI", sans-serif;
  --body: "IBM Plex Sans", "Segoe UI", system-ui, sans-serif;
  --mono: "IBM Plex Mono", Consolas, "Courier New", monospace;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --paper: #0f161b; --sheet: #141d23; --ink: #dce5ea; --muted: #97a7b1; --rule: #2f3e48;
  --grid: #1a252c; --accent: #6bb8ff; --spark: #ff6b5f; --chip: #1f2b33; color-scheme: dark } }
:root[data-theme="dark"] {
  --paper: #0f161b; --sheet: #141d23; --ink: #dce5ea; --muted: #97a7b1; --rule: #2f3e48;
  --grid: #1a252c; --accent: #6bb8ff; --spark: #ff6b5f; --chip: #1f2b33; color-scheme: dark }

* { box-sizing: border-box }
body { background: var(--paper); color: var(--ink); font: 15px/1.6 var(--body);
  background-image: linear-gradient(var(--grid) 1px, transparent 1px),
                    linear-gradient(90deg, var(--grid) 1px, transparent 1px);
  background-size: 48px 48px; padding-inline: 16px; padding-block: 24px 48px }
.page { max-width: 1180px; margin: 0 auto; display: grid; gap: 56px }
a { color: var(--accent) }
:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px }
h1, h2, h3 { text-wrap: balance; margin: 0 }
p { margin: 0 }

.sheet { background: var(--sheet); border: 1.5px solid var(--ink); }
.hero { display: grid; grid-template-columns: minmax(0, 1.6fr) minmax(0, 1fr); }
.hero-main { padding: 32px 32px 28px; display: grid; gap: 32px; align-content: space-between; border-right: 1.5px solid var(--ink); min-width: 0 }
.hero-copy { display: grid; gap: 18px }
.eyebrow { font: 600 13px/1 var(--display); letter-spacing: .14em; text-transform: uppercase; color: var(--muted) }
.name { font: 700 clamp(64px, 11vw, 140px)/.95 var(--display); padding-bottom: .06em; letter-spacing: -.01em; display: flex; align-items: flex-end; gap: 14px }
.spark { width: .42em; height: .42em; flex: none; margin-bottom: .08em }
.lede { font-size: 19px; line-height: 1.5; max-width: 34em }
.lede strong { font-weight: 600 }
.titleblock { display: grid; grid-template-columns: 1fr 1fr; align-content: stretch; min-width: 0 }
.tb { padding: 12px 16px; border-bottom: 1px solid var(--rule); min-width: 0 }
.tb:nth-child(odd) { border-right: 1px solid var(--rule) }
.tb dt { font: 600 11px/1.2 var(--display); letter-spacing: .12em; text-transform: uppercase; color: var(--muted) }
.tb dd { margin: 4px 0 0; font: 500 15px/1.35 var(--mono); font-variant-numeric: tabular-nums; overflow-wrap: anywhere }
.tb.wide { grid-column: 1 / -1; border-right: 0 }
.tb.big dd { font: 600 30px/1.1 var(--display); letter-spacing: .01em }
.tb:last-child, .tb.last { border-bottom: 0 }

.section-head { display: flex; align-items: baseline; gap: 14px; flex-wrap: wrap; margin-bottom: 18px }
.section-head h2 { font: 700 34px/1 var(--display); letter-spacing: .01em; text-transform: uppercase }
.section-head p { color: var(--muted); max-width: 46em }

.work { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); border-top: 1.5px solid var(--ink) }
.job { padding: 22px 24px 24px 0; border-bottom: 1px solid var(--rule); display: grid; gap: 8px; align-content: start; min-width: 0 }
.job:nth-child(odd) { border-right: 1px solid var(--rule); padding-right: 28px }
.job:nth-child(even) { padding-left: 28px }
.where { font: 500 12px/1 var(--mono); color: var(--muted); display: flex; align-items: center; gap: 8px }
.job h3 { font: 600 24px/1.15 var(--display); letter-spacing: .01em }
.job p { max-width: 38em }
.proof { font: 13px/1.45 var(--mono); color: var(--ink); border-left: 3px solid var(--spark); padding-left: 10px }

.bubble { display: inline-grid; place-items: center; width: 30px; height: 30px; border: 1.5px solid currentColor;
  border-radius: 50%; font: 700 15px/1 var(--display); flex: none }
.where .bubble { width: 20px; height: 20px; font-size: 11px; border-width: 1px }

.tools-bar { display: flex; gap: 12px; flex-wrap: wrap; align-items: center; margin-bottom: 8px }
.search { flex: 1 1 280px; min-width: 0; font: 15px var(--body); color: var(--ink); background: var(--sheet);
  border: 1.5px solid var(--ink); border-radius: 0; padding: 9px 12px }
.count { font: 500 13px var(--mono); color: var(--muted) }
.jump { display: flex; gap: 8px; flex-wrap: wrap }
.jump a { display: flex; align-items: center; gap: 6px; text-decoration: none; color: var(--ink); font: 600 14px var(--display);
  letter-spacing: .06em; text-transform: uppercase; padding: 4px 8px 4px 4px; border: 1px solid var(--rule); background: var(--sheet) }
.jump a .bubble { width: 22px; height: 22px; font-size: 12px; border-width: 1px }

.tab { scroll-margin-top: 16px }
.tab-head { display: flex; align-items: center; gap: 14px; margin: 34px 0 6px }
.tab-head h3 { font: 700 30px/1 var(--display); text-transform: uppercase; letter-spacing: .02em }
.tab-head .line { flex: 1; height: 0; border-top: 1px dashed var(--rule) }
.panel { margin-top: 18px }
.panel h4 { margin: 0 0 6px; font: 600 13px/1 var(--display); letter-spacing: .14em; text-transform: uppercase; color: var(--muted) }
.schedule { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 340px), 1fr));
  background: var(--sheet); border: 1px solid var(--rule) }
.tool { display: grid; grid-template-columns: 44px minmax(0, 1fr); gap: 12px; padding: 12px 14px;
  border-bottom: 1px solid var(--rule); border-right: 1px solid var(--rule); align-items: start; min-width: 0 }
.tool img { width: 40px; height: 40px }
.tool .ic-d { display: none }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) .tool .ic-l { display: none }
  :root:not([data-theme="light"]) .tool .ic-d { display: block } }
:root[data-theme="dark"] .tool .ic-l { display: none }
:root[data-theme="dark"] .tool .ic-d { display: block }
.tool b { display: block; font: 600 16px/1.25 var(--body) }
.tool span { display: block; font-size: 13.5px; line-height: 1.45; color: var(--muted); margin-top: 3px }
.meta { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 6px }
.meta i { font: normal 500 11.5px/1 var(--mono); background: var(--chip); padding: 4px 6px; color: var(--ink) }
.none { color: var(--muted); padding: 18px 0 }

.steps { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(3, minmax(0, 1fr));
  border-top: 1.5px solid var(--ink) }
.steps li { padding: 20px 22px 22px 0; border-bottom: 1px solid var(--rule); display: grid; gap: 6px; align-content: start; min-width: 0 }
.steps li + li { padding-left: 22px; border-left: 1px solid var(--rule) }
.steps li:nth-child(3n+1) { border-left: 0; padding-left: 0 }
.steps .n { font: 700 40px/1 var(--display); color: var(--spark) }
.steps h3 { font: 600 20px/1.2 var(--display); letter-spacing: .01em }
.steps p { color: var(--muted); font-size: 14px }

.foot { display: grid; grid-template-columns: minmax(0, 2fr) repeat(3, minmax(0, 1fr)) }
.foot .tb { border-bottom: 0; border-right: 1px solid var(--rule) }
.foot .tb:last-child { border-right: 0 }

@media (max-width: 860px) {
  .hero { grid-template-columns: 1fr } .hero-main { border-right: 0; border-bottom: 1.5px solid var(--ink) }
  .work { grid-template-columns: 1fr } .job:nth-child(odd) { border-right: 0; padding-right: 0 } .job:nth-child(even) { padding-left: 0 }
  .steps { grid-template-columns: 1fr } .steps li + li { border-left: 0; padding-left: 0 }
  .foot { grid-template-columns: 1fr 1fr } .foot .tb { border-bottom: 1px solid var(--rule) }
}
@media (max-width: 480px) { .hero-main { padding: 22px 18px } .titleblock { grid-template-columns: 1fr } .tb:nth-child(odd) { border-right: 0 } }
@media (prefers-reduced-motion: no-preference) { .tool { transition: background-color .15s } .tool:hover { background: var(--chip) } }
'''

SPARK = (u'<svg class="spark" viewBox="0 0 24 24" aria-hidden="true">'
         u'<g stroke="var(--spark)" stroke-width="3.2" stroke-linecap="round">'
         u'<line x1="12" y1="2" x2="12" y2="22"/><line x1="3.3" y1="7" x2="20.7" y2="17"/>'
         u'<line x1="3.3" y1="17" x2="20.7" y2="7"/></g></svg>')

SCRIPT = u'''
(function () {
  var box = document.getElementById('find');
  var count = document.getElementById('count');
  var tools = Array.prototype.slice.call(document.querySelectorAll('.tool'));
  var panels = Array.prototype.slice.call(document.querySelectorAll('.panel'));
  var tabs = Array.prototype.slice.call(document.querySelectorAll('.tab'));
  var empty = document.getElementById('none');
  function run() {
    var words = box.value.toLowerCase().split(/\\s+/).filter(Boolean);
    var shown = 0;
    tools.forEach(function (t) {
      var hay = t.getAttribute('data-q');
      var ok = words.every(function (w) { return hay.indexOf(w) !== -1; });
      t.hidden = !ok; if (ok) shown++;
    });
    panels.forEach(function (p) { p.hidden = !p.querySelector('.tool:not([hidden])'); });
    tabs.forEach(function (t) { t.hidden = !t.querySelector('.panel:not([hidden])'); });
    count.textContent = shown + ' of ' + tools.length + ' tools';
    empty.hidden = shown !== 0;
  }
  box.addEventListener('input', run);
  run();
})();
'''


def render(tabs, f):
    letters = 'ABCDEFGHIJ'
    total = sum(len(p['tools']) for t in tabs for p in t['panels'])
    panels = sum(len(t['panels']) for t in tabs)
    out = []
    w = out.append
    w(u'<title>pyNavis Playground showcase</title>\n')
    w(u'<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n')
    w(u'<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600;700&family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&display=swap">\n')
    w(u'<style>%s</style>\n<div class="page">\n' % CSS)

    # Hero: name, thesis, title block.
    w(u'<header class="sheet hero"><div class="hero-main">')
    w(u'<div class="eyebrow">A pyNavis extension for Autodesk Navisworks</div><div class="hero-copy">')
    w(u'<h1 class="name">Playground%s</h1>' % SPARK)
    w(u'<p class="lede">Every tool left on the pyNavis feature list, built: <strong>%d tools on %d tabs</strong>, '
      u'from clash reporting and BCF to 4D movies, IFC export and a command palette, on one shared '
      u'library and verified without opening Navisworks once.</p>' % (total, len(tabs)))
    w(u'</div></div><dl class="titleblock">')
    cells = [
        ('Tools', '{:,}'.format(total), 'big'), ('Panels', '{:,}'.format(panels), 'big'),
        ('Library modules', '{:,}'.format(f['modules']), 'big'),
        ('Lines of Python and XAML', '{:,}'.format(f['lines']), 'big'),
        ('Tests written', '{:,}'.format(f['tests']), 'big'),
        ('Bugs fixed in review', '{:,}'.format(f.get('review_fixes') or 0), 'big'),
    ]
    if f.get('ipy_passed') and f.get('cpython_passed'):
        text = '{:,} tests'.format(f['ipy_passed'])
        if f.get('smoke_passed'):
            text += ' + {:,} WPF builds'.format(f['smoke_passed'])
        cells.append(('Passing on IronPython 3.4', text, ''))
        cells.append(('Passing on CPython', '{:,} tests'.format(f['cpython_passed']), ''))
    cells.append(('API members checked', '{:,} lines of reflection dump'.format(f['api_lines']), 'wide'))
    cells.append(('Status', 'Verified headlessly. Not yet run in Navisworks.', 'wide last'))
    for label, value, cls in cells:
        w(u'<div class="tb %s"><dt>%s</dt><dd>%s</dd></div>' % (cls, esc(label), esc(value)))
    w(u'</dl></header>\n')

    # Signature work.
    tab_letter = dict((t['title'], letters[i]) for i, t in enumerate(tabs))
    w(u'<section><div class="section-head"><h2>Signature work</h2>'
      u'<p>Ten pieces that show the range: file formats written from the specification, data '
      u'stored inside the model, automation that runs without a click.</p></div><div class="work">')
    for tab, panel, title, body, proof in HIGHLIGHTS:
        w(u'<article class="job"><div class="where"><span class="bubble">%s</span>%s &rsaquo; %s</div>'
          u'<h3>%s</h3><p>%s</p><p class="proof">%s</p></article>'
          % (esc(tab_letter.get(tab, '')), esc(tab), esc(panel), esc(title), esc(body), esc(proof)))
    w(u'</div></section>\n')

    # Catalog.
    w(u'<section><div class="section-head"><h2>Every tool</h2><p>In ribbon order, with the tooltip each '
      u'button shows in Navisworks.</p></div>')
    w(u'<div class="tools-bar"><label for="find" class="eyebrow">Find a tool</label>'
      u'<input id="find" class="search" type="search" placeholder="clash, excel, viewpoint, IFC..." autocomplete="off">'
      u'<span id="count" class="count"></span></div><nav class="jump" aria-label="Tabs">')
    for i, t in enumerate(tabs):
        w(u'<a href="#tab-%s"><span class="bubble">%s</span>%s</a>' % (letters[i], letters[i], esc(t['title'])))
    w(u'</nav>')
    for i, t in enumerate(tabs):
        w(u'<div class="tab" id="tab-%s"><div class="tab-head"><span class="bubble">%s</span><h3>%s</h3>'
          u'<span class="line"></span></div>' % (letters[i], letters[i], esc(t['title'])))
        for p in t['panels']:
            w(u'<div class="panel"><h4>%s</h4><div class="schedule">' % esc(p['title']))
            for tl in p['tools']:
                meta = []
                if tl['parent']:
                    meta.append(u'In %s' % tl['parent'])
                if tl['kind']:
                    meta.append(tl['kind'])
                if tl['shortcut']:
                    meta.append(tl['shortcut'])
                q = u' '.join([tl['title'], tl['tooltip'], p['title'], t['title']] + meta).lower()
                w(u'<div class="tool" data-q="%s"><div><img class="ic-l" alt="" src="%s"><img class="ic-d" alt="" src="%s"></div>'
                  u'<div><b>%s</b><span>%s</span>%s</div></div>'
                  % (esc(q), tl['light'], tl['dark'], esc(tl['title']), esc(tl['tooltip']),
                     (u'<div class="meta">%s</div>' % u''.join(u'<i>%s</i>' % esc(m) for m in meta)) if meta else u''))
            w(u'</div></div>')
        w(u'</div>')
    w(u'<p id="none" class="none" hidden>No tool matches that. Try a shorter word.</p></section>\n')

    # How it was built: a real sequence, so numbered.
    w(u'<section><div class="section-head"><h2>How it was built</h2><p>Nobody could click anything, so '
      u'correctness had to come from the API surface, the real parser and two Python engines.</p></div><ol class="steps">')
    for n, (title, body) in enumerate(PIPELINE, 1):
        w(u'<li><span class="n">%d</span><h3>%s</h3><p>%s</p></li>' % (n, esc(title), esc(body)))
    w(u'</ol></section>\n')

    w(u'<footer class="sheet foot"><div class="tb"><dt>Project</dt><dd>pyNavis Playground</dd></div>'
      u'<div class="tb"><dt>Engine</dt><dd>IronPython 3.4</dd></div>'
      u'<div class="tb"><dt>Host</dt><dd>Navisworks 2026</dd></div>'
      u'<div class="tb"><dt>Date</dt><dd>2026-10-05</dd></div></footer>\n')
    w(u'</div>\n<script>%s</script>\n' % SCRIPT)
    return u''.join(out)


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    stats = {}
    if '--stats' in sys.argv:
        with io.open(sys.argv[sys.argv.index('--stats') + 1], encoding='utf-8') as handle:
            stats = json.load(handle)
    tabs = collect()
    page = render(tabs, facts(stats))
    with io.open(sys.argv[1], 'w', encoding='utf-8') as handle:
        handle.write(page)
    print('%s: %d KB, %d tools' % (sys.argv[1], len(page.encode('utf-8')) // 1024,
                                   sum(len(p['tools']) for t in tabs for p in t['panels'])))


if __name__ == '__main__':
    main()
