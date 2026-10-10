# -*- coding: utf-8 -*-
"""Builds the public catalog site, published by GitHub Pages from docs/.

    python tools/build_site.py            write docs/
    python tools/build_site.py --check    exit 1 when docs/ is stale

CPython 3.11, stdlib only. The only input about tools is catalog.json (never the
extension tree): every word on a page is either a catalog field or one of the fixed
sentences in this file. The one thing read from the extension is each tool's icon, by the
catalog's own `icon` path, copied beside the pages. Look and behaviour come from
tools/site/ (base.css and guide.css are copies of the pyNavis sites' styles, site.js of
their script, playground.css is this site's own).

Output, all generated, never hand-edited:

  docs/.nojekyll                       GitHub Pages serves the folder as is
  docs/index.html                      lead, status summary, filter, every tool by tab and panel
  docs/<slug>.html                     one page per tool; the slug comes from the tool id
  docs/_assets/site.css                base.css + guide.css + playground.css
  docs/_assets/site.js                 theme, sidebar search, index filter
  docs/_assets/search-index.js         window.PLAYGROUND_SEARCH, for the sidebar search
  docs/_assets/icons/<slug>.png        the tool's ribbon icon, and <slug>.dark.png

Any other file under docs/ is stale: a write removes it, --check reports it.
"""
import html
import io
import json
import os
import re
import sys
from urllib.parse import quote, urlencode

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CATALOG = os.path.join(ROOT, 'catalog.json')
DOCS = os.path.join(ROOT, 'docs')
SITE_SRC = os.path.join(HERE, 'site')
SITE_URL = 'https://pynavis.github.io/Playground/'
PYNAVIS_URL = 'https://github.com/pynavis/pyNavis'
CSS_PARTS = ('base.css', 'guide.css', 'playground.css')

STATUSES = ('untested', 'launched', 'verified', 'known-issue')
STATUS_LABEL = {'untested': 'Untested', 'launched': 'Launched', 'verified': 'Verified',
                'known-issue': 'Known issue'}
# The status ladder, word for word from the README.
STATUS_MEANING = {
    'untested': 'Never executed inside Navisworks. Passed the headless checks only.',
    'launched': 'Ran inside Navisworks at least once with no error logged; nobody checked '
                'the result yet.',
    'verified': 'A person confirmed it does what its tooltip says, on a real model.',
    'known-issue': 'Ran and misbehaved. The note says how. Still installable.',
}
BY_SENTENCE = {
    'log': 'The evidence is a line in a pyNavis log.',
    'runner': 'The evidence is a pynavis run transcript.',
    'person': 'The evidence is a named person\'s check.',
}
KIND_LABEL = {
    'pushbutton': 'Button',
    'toggle': 'Toggle button',
    'nobutton': 'No ribbon button; run it by its shortcut',
    'smartbutton': 'Button',
    'dockpane': 'Dock panel',
    'urlbutton': 'Link button',
    'linkbutton': 'Link button',
}
CONTEXT_LABEL = {
    'doc': 'A model is open',
    'selection': 'Something is selected',
    'clash-tests': 'The model has clash tests',
    'clash-results': 'The model has clash results',
    'viewpoints': 'The model has saved viewpoints',
    'selection-sets': 'The model has selection sets',
    'multi-model': 'More than one model is loaded',
}
VIA_SENTENCE = {
    'page': 'Quoted from the page itself.',
    'search snippet': 'The page would not open to an automated fetch, so this is the '
                      'search engine\'s own snippet, as shown.',
}
EM_DASH = chr(8212)


class SiteError(Exception):
    pass


# ---- small helpers ------------------------------------------------------------------------

def esc(text):
    return html.escape(text or '', quote=True)


def slug_of(tool_id):
    """'Model.tab/Select.panel/Quick.stack/Select_All.pushbutton' -> 'model-select-quick-select-all'."""
    stems = [part.rsplit('.', 1)[0] for part in tool_id.split('/')]
    return re.sub(r'[^a-z0-9]+', '-', '-'.join(stems).lower()).strip('-')


def anchor(text):
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')


def dark_icon(tool):
    """The dark variant beside the catalog icon, when the bundle ships one."""
    icon = tool.get('icon')
    if not icon:
        return None
    folder, name = icon.rsplit('/', 1)
    dark = folder + '/' + name[:-len('.png')] + '.dark.png'
    return dark if dark in tool['files'] else None


def count_statuses(tools):
    counts = dict((s, 0) for s in STATUSES)
    for tool in tools:
        counts[tool['status']] = counts.get(tool['status'], 0) + 1
    return counts


def source_split(tools):
    """(with a quote, with leads only, with neither): always adds up to the tool count."""
    quoted = sum(1 for t in tools if t['source'])
    leads = sum(1 for t in tools if not t['source'] and t['leads'])
    return quoted, leads, len(tools) - quoted - leads


def plural(n, one, many):
    return '%d %s' % (n, one if n == 1 else many)


def jstr(text):
    out = (text or '').replace('\\', '\\\\').replace('"', '\\"')
    out = out.replace('\n', ' ').replace('\r', ' ').replace('</', '<\\/')
    return '"%s"' % out


def read_source(name):
    with io.open(os.path.join(SITE_SRC, name), encoding='utf-8') as handle:
        return handle.read()


# ---- the model ------------------------------------------------------------------------------

class Site(object):
    """The catalog plus what the pages need: slugs, icons, groups, order."""

    def __init__(self, catalog):
        self.catalog = catalog
        self.tools = list(catalog['tools'])
        if not self.tools:
            raise SiteError('catalog.json has no tools')
        self.by_id = {}
        self.slug = {}
        seen = {}
        for tool in self.tools:
            if tool['status'] not in STATUSES:
                raise SiteError('%s: unknown status %r' % (tool['id'], tool['status']))
            slug = slug_of(tool['id'])
            if not slug or slug == 'index' or slug in seen:
                raise SiteError('slug %r of %s is not unique' % (slug, tool['id']))
            seen[slug] = tool['id']
            self.slug[tool['id']] = slug
            self.by_id[tool['id']] = tool
        # Tabs, then panels, in catalog order (the catalog is in ribbon order).
        self.groups = []
        for tool in self.tools:
            if not self.groups or self.groups[-1][0] != tool['tab']:
                self.groups.append((tool['tab'], []))
            panels = self.groups[-1][1]
            if not panels or panels[-1][0] != tool['panel']:
                panels.append((tool['panel'], []))
            panels[-1][1].append(tool)

    def url(self, tool):
        return self.slug[tool['id']] + '.html'

    def icon_url(self, tool, dark=False):
        if not tool.get('icon') or (dark and not dark_icon(tool)):
            return None
        return '_assets/icons/%s%s.png' % (self.slug[tool['id']], '.dark' if dark else '')

    def icon_files(self):
        """{published path: source path under Playground.extension/}."""
        out = {}
        for tool in self.tools:
            if tool.get('icon'):
                out[self.icon_url(tool)] = tool['icon']
            if dark_icon(tool):
                out[self.icon_url(tool, True)] = dark_icon(tool)
        return out

    def report_url(self, tool):
        query = urlencode([('template', '1-tried-a-tool.yml'),
                           ('title', '[Tried] ' + tool['title']),
                           ('tool', tool['id'])], quote_via=quote)
        return '%s/issues/new?%s' % (self.catalog['repo'], query)


# ---- shared page parts ------------------------------------------------------------------

LOGO = ('<svg class="brand-mark" width="26" height="26" viewBox="0 0 26 26" aria-hidden="true">'
        '<rect x="1.5" y="1.5" width="23" height="23" rx="4" fill="none" stroke="currentColor" '
        'stroke-width="1.5"/><rect x="6" y="6" width="6" height="6" rx="1" fill="currentColor"/>'
        '<rect x="14" y="6" width="6" height="6" rx="1" fill="none" stroke="currentColor" '
        'stroke-width="1.5"/><rect x="6" y="14" width="6" height="6" rx="1" fill="none" '
        'stroke="currentColor" stroke-width="1.5"/><rect x="14" y="14" width="6" height="6" '
        'rx="1" fill="none" stroke="currentColor" stroke-width="1.5"/></svg>')

SHELL = """<!doctype html>
<html lang="en" data-theme="light">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{description}">
<link rel="stylesheet" href="_assets/site.css">
</head>
<body data-base="">
<div class="layout">
<div class="sidebar">
  <div class="brand"><a href="index.html">{logo}<span class="brand-name">pyNavis Playground
    <span class="brand-sub">Tool catalog</span></span></a></div>
  <div class="search-wrap">
    <svg class="search-icon" width="14" height="14" viewBox="0 0 14 14" fill="none">
      <circle cx="6" cy="6" r="4.2" stroke="currentColor" stroke-width="1.5"/>
      <path d="M9.2 9.2 12.5 12.5" stroke="currentColor" stroke-width="1.5"
            stroke-linecap="round"/></svg>
    <input id="search" type="search" placeholder="Search the tools" autocomplete="off"
           spellcheck="false" aria-label="Search the Playground tools">
    <span class="search-kbd">/</span>
    <div id="search-results" class="search-results"></div>
  </div>
  {sidebar}
  <div class="side-foot">
    <span>Playground {version}</span>
    <a class="side-link" href="{repo}">GitHub</a>
    <button id="theme-toggle" type="button" aria-label="Toggle colour theme">
      <span>Dark</span></button>
  </div>
</div>
<main class="main">
<article>
{body}
</article>
<aside class="toc"></aside>
</main>
</div>
<script src="_assets/search-index.js"></script>
<script src="_assets/site.js"></script>
</body>
</html>
"""


def icon_pair(site, tool, cls, size_alt=''):
    light = site.icon_url(tool)
    if not light:
        return '<span class="no-icon"></span>'
    out = '<img class="%s ic-light" src="%s" alt="%s">' % (cls, light, esc(size_alt))
    dark = site.icon_url(tool, True)
    if dark:
        out += '<img class="%s ic-dark" src="%s" alt="%s">' % (cls, dark, esc(size_alt))
    return out


def chip(status):
    return '<span class="chip st-%s">%s</span>' % (status, STATUS_LABEL[status])


def marker(tool):
    if tool['source']:
        return '<span class="marker" title="A public user ask is quoted on this tool\'s page">Quote</span>'
    if tool['leads']:
        return '<span class="marker" title="Threads that look related, still to be read">Leads</span>'
    return ''


def sidebar(site, current):
    out = ['<nav class="pages">']
    cls = ' class="active"' if current is None else ''
    out.append('<a href="index.html"%s>All tools</a>' % cls)
    for tab, panels in site.groups:
        out.append('<div class="grp">%s</div>' % esc(tab))
        for panel, tools in panels:
            out.append('<div class="sub">%s</div>' % esc(panel))
            for tool in tools:
                cls = ' class="active"' if tool is current else ''
                out.append('<a href="%s"%s>%s%s</a>' % (
                    site.url(tool), cls, icon_pair(site, tool, 'nav-icon'), esc(tool['title'])))
    out.append('</nav>')
    return '\n'.join(out)


def page(site, title, description, body, current):
    return SHELL.format(title=esc(title), description=esc(description), logo=LOGO,
                        sidebar=sidebar(site, current), body=body,
                        version=esc(site.catalog['version']), repo=esc(site.catalog['repo']))


def zip_sentence(catalog):
    return ('Download <a href="%s"><code>Playground.extension.zip</code></a>, unzip it, put the '
            '<code>Playground.extension</code> folder in <code>%%APPDATA%%\\pyNavis\\extensions\\</code>, '
            'and click pyNavis &gt; Reload.' % esc(catalog['download']['zip']))


# ---- index --------------------------------------------------------------------------------

def render_index(site):
    catalog = site.catalog
    tools = site.tools
    counts = count_statuses(tools)
    quoted, leads, neither = source_split(tools)
    status_bits = ', '.join('<strong data-status-count="%s">%d</strong> %s'
                            % (s, counts[s], STATUS_LABEL[s].lower()) for s in STATUSES)
    body = []
    body.append('<p class="eyebrow">pyNavis Playground %s</p>' % esc(catalog['version']))
    body.append('<h1>Experimental tools for pyNavis</h1>')
    body.append(
        '<p class="lead">Playground is a second extension for <a href="%s">pyNavis</a>, the '
        'open-source pyRevit-style add-in for Autodesk Navisworks. Nothing here is a finished '
        'pyNavis tool. Every tool carries an honest status, and most have never run inside '
        'Navisworks. Install the ones you need, try them on a real model, and tell us what '
        'happened.</p>' % PYNAVIS_URL)
    body.append('<p class="summary-line" id="status-summary"><strong data-total="%d">%d</strong> '
                'tools: %s.</p>' % (len(tools), len(tools), status_bits))
    body.append(
        '<p class="source-line" id="source-summary">The public user ask behind a tool is quoted '
        'word for word for <span data-quoted="%d">%s</span>; <span data-leads="%d">%s</span> '
        'only leads, threads a person still has to read; <span data-none="%d">%s</span> no '
        'public source on record.</p>'
        % (quoted, plural(quoted, 'tool', 'tools'), leads,
           plural(leads, 'tool has', 'tools have'), neither,
           plural(neither, 'tool has', 'tools have')))

    body.append('<div class="note"><span class="note-t">Status ladder</span>'
                '<div class="table-scroll"><table><thead><tr><th>Status</th><th>Meaning</th>'
                '</tr></thead><tbody>')
    for status in STATUSES:
        body.append('<tr><td>%s</td><td>%s</td></tr>' % (chip(status), esc(STATUS_MEANING[status])))
    body.append('</tbody></table></div>'
                '<p>A status only goes up with evidence: a log excerpt, a <code>pynavis run</code> '
                'transcript, or a named person\'s check.</p></div>')

    body.append('<div class="note tip"><span class="note-t">Install</span>'
                '<p>You need pyNavis %s or later.</p>'
                '<p><strong>The whole extension.</strong> %s To remove it, delete the folder and '
                'Reload.</p>'
                '<p><strong>Only the tools you want.</strong> In Navisworks, click pyNavis &gt; '
                'Playground. It opens a browser over the same catalog: search, read the user ask '
                'behind each tool, tick the ones you want, and click Install. It downloads only '
                'those tools, plus the shared library they all use, and reloads.</p>'
                '<p>Every installed Playground tool is marked experimental on the ribbon. Tried '
                'one? <a href="%s/issues/new/choose">Report back</a>, whether it worked or not.</p>'
                '</div>' % (esc(catalog['min_pynavis']), zip_sentence(catalog), esc(catalog['repo'])))

    body.append('<h2 id="tools">All tools</h2>')
    body.append('<div class="filter-bar">'
                '<input id="filter" type="search" placeholder="Filter by title, summary, tab or panel" '
                'autocomplete="off" spellcheck="false" aria-label="Filter the tools">'
                '<div class="fchips" role="group" aria-label="Status">')
    body.append('<button type="button" class="fchip" data-status="" aria-pressed="true">All'
                '<span class="n">%d</span></button>' % len(tools))
    for status in STATUSES:
        body.append('<button type="button" class="fchip" data-status="%s" aria-pressed="false">%s'
                    '<span class="n">%d</span></button>' % (status, STATUS_LABEL[status], counts[status]))
    body.append('</div><div class="filter-count" id="filter-count" aria-live="polite">'
                'Showing all %d tools</div></div>' % len(tools))
    body.append('<p class="filter-empty" id="filter-empty" hidden>No tool matches that filter.</p>')

    for tab, panels in site.groups:
        body.append('<section class="tab-group" id="tab-%s"><h2>%s</h2>' % (anchor(tab), esc(tab)))
        for panel, group in panels:
            body.append('<section class="panel-group" id="panel-%s-%s"><h3>%s</h3><ul class="tool-list">'
                        % (anchor(tab), anchor(panel), esc(panel)))
            for tool in group:
                text = ' '.join([tool['title'], tool['summary'], tool['tab'], tool['panel']]).lower()
                body.append(
                    '<li class="tool-row" data-status="%s" data-text="%s"><a href="%s">%s'
                    '<span><span class="row-head"><span class="row-title">%s</span>%s%s</span>'
                    '<span class="row-sum">%s</span></span></a></li>'
                    % (tool['status'], esc(text), site.url(tool), icon_pair(site, tool, 'row-icon'),
                       esc(tool['title']), chip(tool['status']), marker(tool), esc(tool['summary'])))
            body.append('</ul></section>')
        body.append('</section>')

    description = ('%d experimental tools for pyNavis and Autodesk Navisworks, each with an '
                   'honest status: what it does, the user ask behind it, and how to install it.'
                   % len(tools))
    return page(site, 'pyNavis Playground', description, '\n'.join(body), None)


# ---- tool page ----------------------------------------------------------------------------

def facts(tool):
    rows = [('Tab and panel', '%s &gt; %s' % (esc(tool['tab']), esc(tool['panel']))),
            ('Kind', esc(KIND_LABEL.get(tool['kind'], tool['kind'])))]
    if tool.get('shortcut'):
        rows.append(('Shortcut', '<kbd>%s</kbd>' % esc(tool['shortcut'])))
    context = tool.get('context')
    if context:
        label = CONTEXT_LABEL.get(context)
        rows.append(('Live when', esc(label) if label else '<code>%s</code>' % esc(context)))
    return '<div class="facts">%s</div>' % ''.join(
        '<div class="fact"><span class="fact-k">%s</span><span class="fact-v">%s</span></div>'
        % (k, v) for k, v in rows)


def status_section(tool):
    out = ['<h2 id="status">Status</h2><div class="status-block">']
    out.append('<p>%s %s</p>' % (chip(tool['status']), esc(STATUS_MEANING[tool['status']])))
    if tool.get('status_note'):
        out.append('<p>%s</p>' % esc(tool['status_note']))
    meta = []
    if tool.get('status_date'):
        meta.append('Recorded on %s.' % esc(tool['status_date']))
    if tool.get('status_by') in BY_SENTENCE:
        meta.append(BY_SENTENCE[tool['status_by']])
    if meta:
        out.append('<p class="status-meta">%s</p>' % ' '.join(meta))
    out.append('</div>')
    return '\n'.join(out)


def ask_section(tool):
    source = tool['source']
    if source:
        cite = esc(source.get('site', ''))
        if source.get('date'):
            cite += ', %s' % esc(source['date'])
        out = ['<h2 id="ask">The public ask</h2>',
               '<blockquote class="ask">%s</blockquote>' % esc(source['quote']),
               '<p class="ask-cite">%s. <a href="%s" rel="nofollow noopener">Open the source</a></p>'
               % (cite, esc(source['url']))]
        via = VIA_SENTENCE.get(source.get('via', ''))
        if via:
            out.append('<p class="status-meta">%s</p>' % via)
        return '\n'.join(out)
    if tool['leads']:
        out = ['<h2 id="ask">Related asks to confirm</h2>',
               '<p>No quote is on record yet. These threads look related, but a person still '
               'has to open and read them.</p><ul class="lead-links">']
        for lead in tool['leads']:
            out.append('<li><a href="%s" rel="nofollow noopener">%s</a></li>'
                       % (esc(lead['url']), esc(lead.get('title') or lead['url'])))
        out.append('</ul>')
        return '\n'.join(out)
    return ('<h2 id="ask">The public ask</h2>'
            '<p>No public source is on record for this tool.</p>')


def render_tool(site, index):
    tool = site.tools[index]
    catalog = site.catalog
    hero_icon = ''
    if site.icon_url(tool):
        hero_icon = icon_pair(site, tool, 'hero-icon')
    body = ['<div class="hero">%s<div><p class="eyebrow">%s &gt; %s</p><h1>%s</h1>'
            '<p class="lead">%s</p></div></div>'
            % (hero_icon, esc(tool['tab']), esc(tool['panel']), esc(tool['title']),
               esc(tool['summary'])), facts(tool)]
    body.append(status_section(tool))
    body.append(ask_section(tool))

    if tool['siblings']:
        body.append('<h2 id="installs-with">Installs with</h2>'
                    '<p>%s sits in a stack, so installing it also installs:</p><ul>'
                    % esc(tool['title']))
        for sibling in tool['siblings']:
            other = site.by_id.get(sibling)
            if other is None:
                raise SiteError('%s: sibling %s is not in the catalog' % (tool['id'], sibling))
            body.append('<li><a href="%s">%s</a></li>' % (site.url(other), esc(other['title'])))
        body.append('</ul>')

    body.append('<h2 id="hooks">Events it listens to</h2>')
    if tool['hooks']:
        body.append('<p>It needs these Navisworks event hooks, so installing it also copies '
                    'the shared <code>hooks</code> folder:</p><ul>%s</ul>'
                    % ''.join('<li><code>%s</code></li>' % esc(h) for h in tool['hooks']))
    else:
        body.append('<p>None. It runs only when you click it.</p>')

    body.append('<h2 id="files">Files</h2>'
                '<p>Paths are relative to the <code>Playground.extension</code> folder.</p>'
                '<ul class="files">%s</ul>'
                % ''.join('<li><code>%s</code></li>' % esc(f) for f in tool['files']))

    body.append('<h2 id="install">Install</h2><ol class="steps">')
    body.append('<li><strong>Only this tool.</strong> In Navisworks, click pyNavis &gt; '
                'Playground, search for %s, tick it and click Install.</li>' % esc(tool['title']))
    body.append('<li><strong>The whole extension.</strong> %s %s is on the %s tab, %s panel.</li>'
                % (zip_sentence(catalog), esc(tool['title']), esc(tool['tab']), esc(tool['panel'])))
    body.append('</ol><p>You need pyNavis %s or later.</p>' % esc(catalog['min_pynavis']))

    body.append('<div class="report"><p><strong>Tried it?</strong> Tell us whether it worked or '
                'not. That report is what moves a tool up the status ladder.</p>'
                '<a class="button" href="%s" rel="noopener">Report</a></div>'
                % esc(site.report_url(tool)))

    prev = site.tools[index - 1] if index > 0 else None
    nxt = site.tools[index + 1] if index < len(site.tools) - 1 else None
    nav = ['<div class="pagenav">']
    if prev:
        nav.append('<a href="%s"><span class="dir">Previous</span><span class="ttl">%s</span></a>'
                   % (site.url(prev), esc(prev['title'])))
    else:
        nav.append('<span></span>')
    if nxt:
        nav.append('<a class="next" href="%s"><span class="dir">Next</span><span class="ttl">%s</span></a>'
                   % (site.url(nxt), esc(nxt['title'])))
    else:
        nav.append('<span></span>')
    nav.append('</div>')
    body.append('\n'.join(nav))
    return page(site, '%s - pyNavis Playground' % tool['title'], tool['summary'],
                '\n'.join(body), tool)


# ---- search index and assets --------------------------------------------------------------

def render_search_index(site):
    rows = []
    for tool in site.tools:
        rows.append('{t:%s,p:%s,u:%s,b:%s}' % (
            jstr(tool['title']), jstr('%s > %s' % (tool['tab'], tool['panel'])),
            jstr(site.url(tool)), jstr(tool['summary'])))
    return ('/* Generated by tools/build_site.py from catalog.json - do not edit. */\n'
            'window.PLAYGROUND_SEARCH = [\n%s\n];\n' % ',\n'.join(rows))


def render_css():
    return '\n'.join(read_source(name).rstrip('\n') + '\n' for name in CSS_PARTS)


# ---- build ----------------------------------------------------------------------------------

def load_catalog(path=CATALOG):
    with io.open(path, encoding='utf-8-sig') as handle:
        return json.load(handle)


def build(catalog, ext_root=None):
    """{path under docs/ (forward slashes): str for text, bytes for icons}."""
    site = Site(catalog)
    ext_root = ext_root or os.path.join(ROOT, catalog['extension'])
    out = {'.nojekyll': '', 'index.html': render_index(site)}
    for index, tool in enumerate(site.tools):
        out[site.url(tool)] = render_tool(site, index)
    out['_assets/site.css'] = render_css()
    out['_assets/site.js'] = read_source('site.js')
    out['_assets/search-index.js'] = render_search_index(site)
    for published, source in site.icon_files().items():
        path = os.path.join(ext_root, source.replace('/', os.sep))
        if not os.path.isfile(path):
            raise SiteError('icon %s named by the catalog is missing' % source)
        with open(path, 'rb') as handle:
            out[published] = handle.read()
    for rel, data in out.items():
        if isinstance(data, str) and EM_DASH in data:
            raise SiteError('%s holds an em dash' % rel)
    return out


def existing(folder=DOCS):
    found = []
    for dirpath, _dirs, names in os.walk(folder):
        for name in names:
            found.append(os.path.relpath(os.path.join(dirpath, name), folder).replace(os.sep, '/'))
    return sorted(found)


def read_existing(rel, binary):
    path = os.path.join(DOCS, rel.replace('/', os.sep))
    if not os.path.isfile(path):
        return None
    if binary:
        with open(path, 'rb') as handle:
            return handle.read()
    # Text mode reads CRLF and LF alike, so a CRLF checkout is not stale.
    with io.open(path, encoding='utf-8') as handle:
        return handle.read()


def diff(files):
    changed = [rel for rel, data in sorted(files.items())
               if read_existing(rel, isinstance(data, bytes)) != data]
    extra = [rel for rel in existing() if rel not in files] if os.path.isdir(DOCS) else []
    return changed, extra


def write(files, changed, extra):
    for rel in changed:
        path = os.path.join(DOCS, rel.replace('/', os.sep))
        folder = os.path.dirname(path)
        if not os.path.isdir(folder):
            os.makedirs(folder)
        data = files[rel]
        if isinstance(data, bytes):
            with open(path, 'wb') as handle:
                handle.write(data)
        else:
            with io.open(path, 'w', encoding='utf-8', newline='\n') as handle:
                handle.write(data)
    for rel in extra:
        os.remove(os.path.join(DOCS, rel.replace('/', os.sep)))


def main(argv):
    try:
        catalog = load_catalog()
        files = build(catalog)
    except (SiteError, KeyError, ValueError) as error:
        sys.stderr.write('build_site: %s\n' % error)
        return 1
    pages = sum(1 for rel in files if rel.endswith('.html'))
    changed, extra = diff(files)
    if '--check' in argv:
        if changed or extra:
            sys.stderr.write('build_site: docs/ is stale; run python tools/build_site.py\n')
            for rel in changed[:20]:
                sys.stderr.write('  changed: %s\n' % rel)
            for rel in extra[:20]:
                sys.stderr.write('  not generated: %s\n' % rel)
            return 1
        print('build_site: docs/ is current: %d pages, %d files' % (pages, len(files)))
        return 0
    write(files, changed, extra)
    print('build_site: wrote docs/: %d pages, %d files (%d changed, %d removed)'
          % (pages, len(files), len(changed), len(extra)))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
