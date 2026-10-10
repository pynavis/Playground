# -*- coding: utf-8 -*-
"""tools/build_site.py: the public catalog site in docs/. CPython only (the tools are
dev-time CPython 3.11)."""
import copy
import io
import json
import os
import re
import sys
from urllib.parse import unquote

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


# ---- the source section ----------------------------------------------------------------------

BLOB = re.compile(r'href="(https://github\.com/pynavis/Playground/blob/main/([^"]+))"')
CODE = re.compile(r'<pre><code class="language-(\w+)">(.*?)</code></pre>', re.S)
SAMPLES = ('Model.tab/Select.panel/Select_Similar.pushbutton',      # script.py only
           'Model.tab/Select.panel/Quick.stack/Invert.pushbutton',   # with config.py
           'Coordinate.tab/Issues.panel/Issues.dockpane')            # with pane.xaml


def ext_text(rel):
    with io.open(os.path.join(_compat.ROOT, catalog()['extension'], rel.replace('/', os.sep)),
                 encoding='utf-8') as handle:
        return handle.read()


def strip_tags(text):
    return re.sub(r'<[^>]+>', '', text)


def test_sample_pages_show_their_files_verbatim():
    c = catalog()
    for tool_id in SAMPLES:
        tool = [t for t in c['tools'] if t['id'] == tool_id][0]
        text = pages()[bs.slug_of(tool_id) + '.html']
        blocks = [strip_tags(body) for _lang, body in CODE.findall(text)]
        for name in ('script.py', 'config.py', 'pane.xaml', 'bundle.yaml'):
            rel = tool_id + '/' + name
            if rel not in tool['files']:
                assert '<code>%s</code>' % rel not in text
                continue
            assert bs.esc_code(ext_text(rel)) in blocks, rel
            assert 'href="%s"' % bs.blob_url(c, rel) in text
    assert 'id="src-config-py"' in pages()[bs.slug_of(SAMPLES[1]) + '.html']
    assert 'id="src-pane-xaml"' in pages()[bs.slug_of(SAMPLES[2]) + '.html']


def test_every_tool_page_carries_its_script():
    for tool in catalog()['tools']:
        text = pages()[bs.slug_of(tool['id']) + '.html']
        rel = tool['id'] + '/script.py'
        if rel in tool['files']:
            assert bs.esc_code(ext_text(rel)) in strip_tags(text), rel
        assert '<h2 id="source">Source</h2>' in text
        assert text.index('id="source"') < text.index('class="pagenav"')


def test_the_tokenizer_never_changes_the_text():
    samples = ['@deco.x\ndef f(a=r"x\\"y", b=\'\'\'q\n\'\'\'):  # hi <b>&\n    return a @ b\n',
               'x = "unterminated\ny = \'\'\'never closed', '']
    for tool in catalog()['tools']:
        samples.extend(ext_text(f) for f in tool['files'] if f.endswith('.py'))
    for src in samples:
        out = bs.highlight_python(src)
        assert strip_tags(out) == bs.esc_code(src)
        assert set(re.findall(r'<span class="(\w+)">', out)) <= {'k', 's', 'c', 'd'}
    out = bs.highlight_python('@property\ndef x(self):  # c\n    return "s"\n')
    for want in ('<span class="d">@property</span>', '<span class="k">def</span>',
                 '<span class="c"># c</span>', '<span class="s">"s"</span>'):
        assert want in out, want


def test_python_blocks_are_coloured_and_others_are_plain():
    text = pages()[bs.slug_of(SAMPLES[2]) + '.html']
    for lang, body in CODE.findall(text):
        assert lang in ('python', 'xml', 'yaml')
        if lang != 'python':
            assert '<span' not in body


def test_every_github_link_names_a_real_file():
    root = _compat.ROOT
    seen = 0
    for rel, text in pages().items():
        for _url, path in BLOB.findall(text):
            path = unquote(path)
            assert os.path.isfile(os.path.join(root, path.replace('/', os.sep))), (rel, path)
            seen += 1
    assert seen >= 3 * len(catalog()['tools'])


def test_library_modules_are_the_imported_ones_with_their_docstrings():
    c = catalog()
    tool = [t for t in c['tools'] if t['id'] == SAMPLES[2]][0]
    text = pages()[bs.slug_of(tool['id']) + '.html']
    names = set()
    for f in tool['files']:
        if f.endswith('.py'):
            names.update(bs.namo_imports(ext_text(f), f))
    assert names
    for name in names:
        rel = 'lib/namo/%s.py' % name
        assert 'href="%s"' % bs.blob_url(c, rel) in text
        assert '<code>namo.%s</code>' % name in text
        assert bs.esc(bs.doc_summary(ext_text(rel))) in text
    assert bs.namo_imports('from namo import a, b as c\nimport namo.d\nfrom namo.e import f\n'
                           'import os\nfrom namox import g\n', 'x') == ['a', 'b', 'd', 'e']


def test_every_tool_page_declares_software_source_code():
    for tool in catalog()['tools']:
        text = pages()[bs.slug_of(tool['id']) + '.html']
        found = re.findall(r'<script type="application/ld\+json">(.*?)</script>', text, re.S)
        assert len(found) == 1
        data = json.loads(found[0])
        assert data['@type'] == 'SoftwareSourceCode'
        assert data['name'] == tool['title'] and data['description'] == tool['summary']
        assert data['programmingLanguage'] == 'Python'
        assert data['codeRepository'] == catalog()['repo']
        assert 'Apache-2.0' in data['license'] or 'LICENSE-2.0' in data['license']
        assert data['url'] == bs.SITE_URL + bs.slug_of(tool['id']) + '.html'


def test_the_sidebar_links_the_pynavis_family():
    text = pages()['index.html']
    order = [text.index('href="%s"' % u) for u in (
        'https://pynavis.com/', 'https://docs.pynavis.com/', 'https://tools.pynavis.com/',
        catalog()['repo'])]
    assert order == sorted(order)
