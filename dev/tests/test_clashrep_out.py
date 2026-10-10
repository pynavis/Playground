# -*- coding: utf-8 -*-
"""clashrep_out.Page: a report's output-window page is recorded and printed only after the
progress window has closed (refit: printing, or even output.element_link, while the
progress window is up opens an empty output window behind it)."""
import os

import test_clashreport as fx
from namo import clashrep_forms as cf
from namo import clashrep_out as out
from namo import reports


class FakeOutput(object):
    def __init__(self):
        self.calls = []

    def set_title(self, text):
        self.calls.append(('title', text))

    def print_html(self, html):
        self.calls.append(('html', html))

    def chart_line(self, labels, series, title=None):
        self.calls.append(('line', list(labels), sorted(series), title))


def test_page_records_then_prints_once_in_order():
    built = []
    page = out.Page('Clash Delta').html('<b>head</b>').later(lambda: built.append(1) or '<i>links</i>')
    page.line_chart(['a', 'b'], {'Open': [1, 2]}, 'Open clashes').html('')
    page.saved(['C:\\reports\\Delta.xlsx', ''])
    assert built == []                                    # nothing is built before show()
    fake = FakeOutput()
    assert page.show(fake) == 5
    assert built == [1]
    assert [c[0] for c in fake.calls] == ['title', 'html', 'html', 'line', 'html']
    assert fake.calls[2][1] == '<i>links</i>'
    assert 'Saved to C:\\reports\\Delta.xlsx' in fake.calls[4][1]
    assert page.show(fake) == 0 and len(fake.calls) == 5  # a second show prints nothing


def test_deliver_defers_only_behind_a_progress_window():
    page = out.Page('T').html('x')
    result = out.deliver({'level': 'success'}, page, lambda fraction, label: True)
    assert result['output'] is page and page.calls
    assert 'output' not in out.deliver({'level': 'info'}, None, None)


def test_interactive_reports_leave_their_page_for_the_caller():
    """Behind a progress callback no report touches pynavis.output (FakeNav has none, so a
    print would raise ImportError and the report would come back as an error)."""
    doc, _a, _b = fx.fake_clash_doc()
    seen = []

    def progress(fraction, label):
        seen.append(fraction)
        return True

    with fx.Redirected('clashrep-out-run') as folder:
        with fx.nav.FakeNav(doc):
            matrix = reports.run('clash_matrix', {'folder': folder, 'axis': 'model', 'xlsx': True}, doc=doc,
                                 interactive=True, progress=progress)
            plain = reports.run('clash_matrix', {'folder': folder, 'axis': 'model', 'xlsx': False}, doc=doc,
                                interactive=True, progress=progress)
    assert matrix['level'] == 'success', matrix
    page = matrix['output']
    assert isinstance(page, out.Page) and seen
    fake = FakeOutput()
    page.show(fake)
    assert fake.calls[0] == ('title', 'Clash Count Matrix')
    assert 'Clash count matrix' in fake.calls[1][1]
    assert matrix['paths'] and os.path.isabs(matrix['paths'][0])
    assert 'Saved to %s' % matrix['paths'][0] in fake.calls[-1][1]      # the page says where the file is
    assert not plain['paths'] and isinstance(plain['output'], out.Page)


def test_reveal_only_for_a_report_that_wrote_a_file():
    assert cf.reveal(None) is False
    assert cf.reveal({'level': 'success', 'paths': []}) is False
    assert cf.reveal({'level': 'error', 'paths': ['C:\\x.xlsx']}) is False
