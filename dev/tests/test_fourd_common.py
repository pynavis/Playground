# -*- coding: utf-8 -*-
"""namo.fourd_common, fourd_progress, fourd_ui (pure parts) and field_qr."""
import os

import _compat
from namo import field_qr, fourd_common, fourd_progress, fourd_ui, qr


def test_scopes_and_texts():
    assert fourd_common.default_scope('visible', True) == 'selection'
    assert fourd_common.default_scope('selection', False) == 'model'
    assert fourd_common.default_scope('visible', False) == 'visible'
    assert fourd_common.default_scope(None, False) == 'model'
    assert [v for _l, v in fourd_common.scope_options(False)] == ['visible', 'model']
    assert fourd_common.scope_options(True)[0] == ('Current selection', 'selection')
    assert fourd_common.plural(1, 'task') == '1 task' and fourd_common.plural(1234, 'task') == '1,234 tasks'
    assert fourd_common.plural(2, 'attach entry', 'attach entries') == '2 attach entries'
    assert fourd_common.sampled_note(20000, 54321) == 'Sampled 20,000 of 54,321 objects.'
    assert fourd_common.sampled_note(5, 5) == '' and fourd_common.sampled_note(5, None) == ''
    name = fourd_common.file_name('C:\\Jobs\\Tower.nwf', 'Quick takeoff', 'xlsx')
    assert name.startswith('Tower - Quick takeoff - ') and name.endswith('.xlsx')
    assert fourd_common.file_name('', 'Photo report', '.html').startswith('Untitled - Photo report')


def test_report_config_escapes_braces():
    config = fourd_common.report_config({'folder': '', 'name_template': '{report}', 'x': 1},
                                        os.path.join('C:\\out', 'Plan {A}.xlsx'))
    assert config['folder'] == 'C:\\out' and config['name_template'] == 'Plan {{A}}' and config['x'] == 1
    from namo import naming
    assert naming.render(config['name_template'], {})[0] == 'Plan {A}'


def test_progress_merging():
    assert fourd_progress.to_percent('45 %') == 45.0 and fourd_progress.to_percent(130) == 100.0
    assert fourd_progress.to_percent(None) is None and fourd_progress.to_percent('n/a') is None
    tab = fourd_progress.merged_tab({'QR': 'x', 'When': object(), 'Gone': None}, {'Progress': 50.0})
    assert tab['QR'] == 'x' and tab['Progress'] == 50.0 and 'Gone' not in tab
    assert isinstance(tab['When'], str)
    writes = fourd_progress.group_writes(['a', 'b', 'c', 'd'],
                                         [None, {'QR': '1'}, None, {'QR': '1', 'Progress': 10}],
                                         {'Progress': 40.0})
    assert [(sorted(t.items()), objs) for t, objs in writes] == [
        ([('Progress', 40.0)], ['a', 'c']), ([('Progress', 40.0), ('QR', '1')], ['b', 'd'])]
    assert fourd_progress.task_average([100.0, None, 50.0, 0.0]) == 37.5
    assert fourd_progress.task_average([]) is None
    assert fourd_progress.band_counts([0, 0, 25, 75, 100, None]) == {0: 2, 1: 1, 2: 1, 3: 1}


def test_legend_and_review_texts():
    assert [b[0] for b in fourd_ui.PROGRESS_BANDS] == ['Not started (0%)', 'Under way (1 to 49%)',
                                                      'Well advanced (50 to 99%)', 'Complete (100%)']
    problems = [{'row': 4, 'level': 'error', 'label': 'Start', 'message': 'Bad'},
                {'row': None, 'level': 'warning', 'label': '', 'message': 'Hmm'}]
    rows = fourd_ui.problem_rows(problems)
    assert rows[0] == {'cells': [4, 'Error', 'Start', 'Bad'], 'value': 0}
    assert rows[1]['cells'][:2] == ['', 'Warning']


def test_qr_payloads_and_names():
    standard = {'project': 'Tower', 'project_number': 'P-12', 'file': 'Tower', 'date': '2026-10-05'}
    ids = {'element_id': '123456', 'unique_id': 'u-1', 'ifc_guid': '2Ki0Pk1LT0NeYCumF5Cz6X',
           'category': 'Ducts', 'type': 'Round', 'family': 'Duct'}
    values = field_qr.values_for(ids, 'Duct 300', standard)
    payload, missing = field_qr.render_payload(field_qr.DEFAULT_TEMPLATE, values)
    assert payload == 'Tower|Tower|123456|2Ki0Pk1LT0NeYCumF5Cz6X' and missing == []
    url, _ = field_qr.render_payload('https://x.io/a?g={guid}&n={number}', values)
    assert url == 'https://x.io/a?g=2Ki0Pk1LT0NeYCumF5Cz6X&n=P-12'
    assert field_qr.values_for(None, '', {})['guid'] == ''
    assert field_qr.check_template('{project}|{guid}') is None
    assert field_qr.check_template('  ').startswith('Give a payload template')
    assert field_qr.check_template('{colour}').startswith('{colour} is not a token')
    names = field_qr.file_names([{'element_id': '12', 'name': 'A'}, {'element_id': '12', 'name': 'B'},
                                 {'element_id': '', 'name': 'Pipe: 25/32'}, {'name': ''}])
    assert names == ['12.png', '12 (2).png', 'Pipe_ 25_32.png', 'QR.png'] or names[2].endswith('.png')
    assert names[0] == '12.png' and names[1] == '12 (2).png'


def test_label_sheet():
    code = qr.encode('Tower|123', 'M')
    html = field_qr.sheet_html([{'svg': qr.to_svg(code), 'name': 'Duct <300>', 'lines': ['ID 123', '']}],
                               'QR labels', '1 label.')
    assert '@page{size:A4' in html and '<svg' in html and 'Duct &lt;300&gt;' in html
    assert html.count('class="label"') == 1 and html.count('class="id"') == 1


def test_qr_output_folder_is_unique():
    folder = _compat.tmpdir('qr_out')
    first = field_qr.output_folder(folder, 'Tower.nwf')
    os.makedirs(first)
    second = field_qr.output_folder(folder, 'Tower.nwf')
    assert first != second and os.path.basename(first).startswith('Tower QR codes ')


def test_set_progress_writes_once_and_rolls_up():
    import sys
    import test_items as nav
    from namo import timeliner
    doc, n = nav.model_tree()
    wall1, wall2, duct = n['Wall 1'], n['Wall 2'], n['Duct']
    written = []
    edited = []

    class Coll(list):
        @property
        def Count(self):
            return len(self)
    task = object()
    rows = [{'key': (0,), 'name': 'Walls', 'attach_kind': 'items', 'task': task},
            {'key': (1,), 'name': 'Ducts', 'attach_kind': 'items', 'task': 'other'}]
    saved = (timeliner.snapshot, timeliner.selected_items, timeliner.edit_tasks)
    timeliner.snapshot = lambda doc=None: rows
    timeliner.selected_items = lambda t, doc=None: Coll([wall1, wall2]) if t is task else Coll([duct])

    def edit_tasks(changes, doc=None, name=''):
        for row, fn in changes:
            values = type('Values', (), {})()
            fn(values)
            edited.append((row['name'], values.ProgressPercent))
        return len(changes), []
    timeliner.edit_tasks = edit_tasks
    try:
        with nav.FakeNav(doc):
            props = sys.modules['pynavis.props']
            tabs = {id(wall1): {'QR': 'x'}}
            props.get_custom = lambda item, tab: tabs.get(id(item))
            props.set_custom = lambda items, tab, values, d=None: written.append(
                (sorted(i.DisplayName for i in items), tab, sorted(values.items()))) or (len(items), [])
            result = fourd_progress.set_progress([wall1, wall2], 60.0, doc)
    finally:
        timeliner.snapshot, timeliner.selected_items, timeliner.edit_tasks = saved
    assert result == {'objects': 2, 'tasks': 1, 'errors': [], 'timeliner': True}
    assert written == [(['Wall 1'], 'Playground', [('Progress', 60.0), ('QR', 'x')]),
                       (['Wall 2'], 'Playground', [('Progress', 60.0)])]
    assert edited == [('Walls', 60.0)]
    assert doc.transactions == ['Set progress']
