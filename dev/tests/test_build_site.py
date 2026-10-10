# -*- coding: utf-8 -*-
"""tools/build_site.py: the public catalog site in docs/. CPython only (the tools are
dev-time CPython 3.11)."""
import copy
import json
import os
import re
import sys

import _compat
from _compat import raises

if _compat.IRONPYTHON:
    raise _compat.SkipTest('tools/ are CPython-only')

TOOLS = os.path.join(_compat.ROOT, 'tools')
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import build_site as bs  # noqa: E402

_BUILT = []
HREF = re.compile(r'(?:href|src)="([^"]*)"')


def catalog():
    return bs.load_catalog()


def built():
    """One build per test process: {path: str or bytes}."""
    if not _BUILT:
        _BUILT.append(bs.build(catalog()))
    return _BUILT[0]


def pages():
    return dict((k, v) for k, v in built().items() if k.endswith('.html'))


# ---- slugs and pages -----------------------------------------------------------------------

def test_slug_comes_from_the_tool_id():
    assert bs.slug_of('Model.tab/Select.panel/Select_Similar.pushbutton') == 'model-select-select-similar'
    assert bs.slug_of('Model.tab/Select.panel/Quick.stack/Select_All.pushbutton') == \
        'model-select-quick-select-all'


def test_slugs_are_unique():
    slugs = [bs.slug_of(t['id']) for t in catalog()['tools']]
    assert len(slugs) == len(set(slugs))
    assert 'index' not in slugs


def test_a_slug_clash_is_refused():
    c = copy.deepcopy(catalog())
    twin = copy.deepcopy(c['tools'][0])
    twin['id'] = twin['id'].replace('.pushbutton', '.toggle')
    c['tools'].append(twin)
    raises(bs.SiteError, bs.build, c)


def test_every_tool_gets_a_page_and_nothing_else_does():
    expected = set(bs.slug_of(t['id']) + '.html' for t in catalog()['tools']) | {'index.html'}
    assert set(pages()) == expected
    assert '.nojekyll' in built()
    for name in ('site.css', 'site.js', 'search-index.js'):
        assert '_assets/' + name in built()


def test_every_tool_page_carries_its_title_summary_and_status():
    for tool in catalog()['tools']:
        text = pages()[bs.slug_of(tool['id']) + '.html']
        assert '<title>%s - pyNavis Playground</title>' % bs.esc(tool['title']) in text
        assert '<meta name="description" content="%s">' % bs.esc(tool['summary']) in text
        assert 'chip st-%s' % tool['status'] in text
        assert 'template=1-tried-a-tool.yml' in text


def test_icons_are_the_catalog_icons():
    c = catalog()
    ext = os.path.join(_compat.ROOT, c['extension'])
    for tool in c['tools']:
        slug = bs.slug_of(tool['id'])
        with open(os.path.join(ext, tool['icon']), 'rb') as handle:
            assert built()['_assets/icons/%s.png' % slug] == handle.read()


# ---- the index -------------------------------------------------------------------------------

def test_index_counts_equal_the_catalog():
    tools = catalog()['tools']
    index = pages()['index.html']
    assert 'data-total="%d"' % len(tools) in index
    for status in bs.STATUSES:
        n = sum(1 for t in tools if t['status'] == status)
        assert 'data-status-count="%s">%d<' % (status, n) in index
        assert 'data-status="%s" aria-pressed="false">%s<span class="n">%d</span>' % (
            status, bs.STATUS_LABEL[status], n) in index
    quoted = sum(1 for t in tools if t['source'])
    leads = sum(1 for t in tools if not t['source'] and t['leads'])
    assert 'data-quoted="%d"' % quoted in index
    assert 'data-leads="%d"' % leads in index
    assert 'data-none="%d"' % (len(tools) - quoted - leads) in index
    assert index.count('class="tool-row"') == len(tools)


def test_index_lists_tools_in_catalog_order():
    index = pages()['index.html']
    positions = [index.index('href="%s.html"><' % bs.slug_of(t['id']), index.index('id="tools"'))
                 for t in catalog()['tools']]
    assert positions == sorted(positions)


# ---- text rules and links --------------------------------------------------------------------

def test_no_em_dash_anywhere_in_the_output():
    for rel, data in built().items():
        if isinstance(data, str):
            assert bs.EM_DASH not in data, rel


def test_an_em_dash_in_the_catalog_fails_the_build():
    c = copy.deepcopy(catalog())
    c['tools'][0]['summary'] = u'Does one thing %s well.' % bs.EM_DASH
    raises(bs.SiteError, bs.build, c)


def test_every_local_link_resolves():
    files = built()
    for rel, text in pages().items():
        for target in HREF.findall(text):
            if target.startswith(('http://', 'https://', 'mailto:')):
                continue
            path = target.split('#', 1)[0]
            if not path:
                continue
            assert path in files, '%s links to missing %s' % (rel, target)


def test_the_search_index_names_every_page():
    index = built()['_assets/search-index.js']
    for tool in catalog()['tools']:
        assert 'u:"%s.html"' % bs.slug_of(tool['id']) in index


def test_no_external_scripts_or_stylesheets():
    for rel, text in pages().items():
        for match in re.findall(r'<(?:script|link)\b[^>]*>', text):
            assert 'http' not in match, (rel, match)


# ---- the public ask block --------------------------------------------------------------------

def test_a_source_is_quoted_verbatim_with_its_link():
    for tool in catalog()['tools']:
        text = pages()[bs.slug_of(tool['id']) + '.html']
        if tool['source']:
            assert '<blockquote class="ask">%s</blockquote>' % bs.esc(tool['source']['quote']) in text
            assert 'href="%s"' % bs.esc(tool['source']['url']) in text
        elif tool['leads']:
            assert 'Related asks to confirm' in text
            for lead in tool['leads']:
                assert 'href="%s"' % bs.esc(lead['url']) in text
        else:
            assert 'No public source is on record for this tool.' in text


def test_siblings_link_to_their_pages():
    for tool in catalog()['tools']:
        text = pages()[bs.slug_of(tool['id']) + '.html']
        for sibling in tool['siblings']:
            assert 'href="%s.html"' % bs.slug_of(sibling) in text


def test_status_by_reaches_the_page():
    for tool in catalog()['tools']:
        if tool.get('status_by'):
            text = pages()[bs.slug_of(tool['id']) + '.html']
            assert bs.BY_SENTENCE[tool['status_by']] in text


def test_docs_folder_is_current():
    """The committed docs/ matches catalog.json (dev/verify.py runs --check too)."""
    changed, extra = bs.diff(built())
    assert not changed and not extra, (changed[:5], extra[:5])
