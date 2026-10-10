# -*- coding: utf-8 -*-
"""namo.issueui pure half (list cells, sort keys, chip colours, filter options, field diffs,
texts, empty states) and namo.bcf_exchange's summary lines."""
import datetime

import _compat

from namo import bcf_exchange, issues, issueui

NOW = datetime.datetime(2026, 10, 5, 14, 30, 0)
TODAY = datetime.date(2026, 10, 5)
PALETTE = {'paper': '#FFFFFF', 'surface': '#F7F7F7', 'ink': '#1A1A1A', 'muted': '#6B6B6B',
           'success': '#0F7B0F', 'warning': '#9D5D00', 'error': '#C42B1C', 'info': '#005FB8',
           'line': '#E5E5E5'}
DARK = {'paper': '#202020', 'surface': '#2B2B2B', 'ink': '#FFFFFF', 'muted': '#9E9E9E',
        'success': '#6CCB5F', 'warning': '#FCE100', 'error': '#FF99A4', 'info': '#60CDFF',
        'line': '#3A3A3A'}


def _issue(id_, **fields):
    record = issues.new_issue(dict({'title': 'Issue %s' % id_}, **fields), 'amol', NOW)
    record['id'] = id_
    record['number'] = issues.split_id(id_)[1]
    return record


def test_sort_keys_order_like_people_expect():
    a, b, c = _issue('RFI-9', title='Level 2 duct'), _issue('RFI-10', title='Level 10 duct'), \
        _issue('HOLD-1', title='level 3')
    keys = [issueui.sort_keys(i) for i in (a, b, c)]
    assert sorted(['RFI-9', 'RFI-10', 'HOLD-1'], key=lambda x: issueui.sort_keys(_issue(x))['k_id']) == \
        ['HOLD-1', 'RFI-9', 'RFI-10']
    assert keys[0]['k_title'] < keys[2]['k_title'] < keys[1]['k_title']
    assert issueui.natural_text_key('Level 2') < issueui.natural_text_key('level 10')
    crit = issueui.sort_keys(_issue('A-1', priority='Critical'))
    low = issueui.sort_keys(_issue('A-2', priority='Low'))
    assert crit['k_priority'] < low['k_priority']
    assert issueui.sort_keys(_issue('A-3'))['k_due'] == '9999-12-31'


def test_row_values():
    late = _issue('A-1', due='2026-10-01', priority='Critical', status='In progress', trade='MEP')
    v = issueui.row_values(late, TODAY)
    assert (v['id'], v['status'], v['due'], v['due_state']) == ('A-1', 'In progress', '2026-10-01', 'overdue')
    assert v['status_tone'] == 'info' and v['priority_tone'] == 'bad'


def test_chip_colors_are_readable_in_both_themes():
    from namo import colors
    for palette in (PALETTE, DARK):
        for tone in ('good', 'warn', 'bad', 'info'):
            background, foreground = issueui.chip_colors(tone, palette)
            assert background.startswith('#') and len(background) == 7
            assert colors.contrast_ratio(foreground.lstrip('#'), background.lstrip('#')) >= 3.0, \
                (tone, palette['paper'], background, foreground)
        assert issueui.chip_colors('neutral', palette) == (palette['surface'], palette['muted'])


def test_filter_options_and_apply():
    rows = [_issue('A-1', trade='Mechanical', assignee='Jane'), _issue('A-2', trade='structure'),
            _issue('A-3', status='Closed')]
    trades, people = issueui.filter_options(rows, ['Mechanical', 'Electrical', 'Unassigned'])
    assert trades[0] == ('All trades', '') and trades[-1] == ('No trade', 'No trade')
    assert [v for _l, v in trades[1:-1]] == ['Electrical', 'Mechanical', 'structure']
    assert people == [('Everyone', ''), ('Jane', 'Jane'), ('Unassigned', 'Unassigned')]
    shown = issueui.apply_filters(rows, 'open', '', '', '')
    assert [i['id'] for i in shown] == ['A-1', 'A-2']
    assert [i['id'] for i in issueui.apply_filters(rows, 'all', 'Mechanical', '', '')] == ['A-1']
    assert [i['id'] for i in issueui.apply_filters(rows, 'all', '', 'Unassigned', 'a-3')] == ['A-3']


def test_diff_fields_sends_only_real_changes():
    loaded = _issue('A-1', labels=['L2'], due='2026-10-12', description='Line\n')
    same = {'title': ' Issue A-1 ', 'type': 'Issue', 'status': 'Open', 'priority': 'Normal',
            'trade': '', 'assignee': '', 'due': '12/10/2026', 'labels': 'L2', 'description': 'Line\n'}
    assert issueui.diff_fields(loaded, same) == {}
    edited = dict(same, title='New title', labels='L2, MEP', due='2026-10-20', description='Line')
    assert issueui.diff_fields(loaded, edited) == {'title': 'New title', 'labels': ['L2', 'MEP'],
                                                   'due': '2026-10-20', 'description': 'Line'}
    assert issueui.diff_fields(loaded, dict(same, due='rubbish')) == {'due': 'rubbish'}


def test_texts():
    issue = _issue('A-1', location={'point': [1, 2, 3], 'level': 'Level 2', 'grid': 'C-4'})
    assert issueui.location_text(issue) == 'Level 2, grid C-4'
    assert issueui.location_text(_issue('A-2', location={'point': [1, 2, 3], 'level': 'L3'})) == 'Level L3'
    assert issueui.location_text(_issue('A-3', location={'point': [1, 2, 3]})) == 'Pin set (no grid nearby)'
    assert issueui.location_text(_issue('A-4')) == 'No pin'
    assert issueui.elements_text(_issue('A-5', elements=[{'name': 'Duct'}, {'name': 'Beam'}])) == \
        'Duct and 1 more'
    assert issueui.elements_text(_issue('A-6')) == 'No elements'
    assert issueui.comment_head({'author': 'jane', 'date': '2026-10-05T09:15:00'}) == \
        'jane, 2026-10-05 09:15'
    assert issueui.created_text(issue).startswith('Raised by amol on 2026-10-05')
    assert issueui.hidden_columns(800) == [] and issueui.hidden_columns(550) == [4]
    assert issueui.hidden_columns(300) == [3, 4, 5]


def test_empty_states():
    assert issueui.empty_state(False, False, False, 0, 0)[0] == 'No model open'
    assert issueui.empty_state(True, True, False, 0, 0)[0] == 'Save the model first'
    assert issueui.empty_state(True, True, True, 0, 0)[0] == 'No issues yet'
    assert issueui.empty_state(True, True, True, 5, 0)[0] == 'No issues match'
    assert issueui.empty_state(True, True, True, 5, 2) is None


def test_bcf_exchange_lines_and_vocabulary():
    report = {'created': 8, 'updated': 3, 'kept': 1, 'viewpoints': 12, 'folder': 'BCF/Week 40',
              'found': 20, 'missing': 2, 'not_searched': 0, 'notes': ['Section planes were not applied.']}
    assert bcf_exchange.summary_line(report) == '12 topics: 8 new, 3 updated, 1 kept (newer here)'
    detail = bcf_exchange.detail_line(report)
    assert detail.startswith('12 viewpoints under BCF/Week 40; 20 elements found, 2 not found.')
    assert detail.endswith('Section planes were not applied.')
    nothing = {'created': 0, 'updated': 0, 'kept': 0}
    assert bcf_exchange.summary_line(nothing) == '0 topics: nothing new'
    words = bcf_exchange.vocabulary()
    assert 'In Progress' in words['statuses'] and 'Critical' in words['priorities']
    assert 'RFI' in words['types'] and 'Clash' in words['types']


def test_save_failure_toast_text():
    # Pane and meeting buttons toast a failed register write instead of only logging it.
    message, detail = issueui.save_failure(IOError('Could not write X.json: denied'))
    assert message == 'Could not save the change'
    assert detail == 'Could not write X.json: denied Check the data folder is reachable, then try again.'
    assert issueui.save_failure(ValueError('There is no issue RFI-009 in this model.')) == \
        ('Could not save the change', 'There is no issue RFI-009 in this model.')
    assert issueui.save_failure(ValueError())[1] == 'The change could not be saved.'



def test_points_come_from_namo_picking_only():
    # Refit: the custom pick tool (pynavis.pick.point) put its marker and its hit in
    # different places in the field. Stamps and Set pin go through namo.picking (the
    # host's Measure tool); nothing in the issue modules may name the banned calls.
    import io
    import re
    from namo import issue_stamps, issueapi
    banned = re.compile(r'pick\.(point|point_then|Unavailable)')
    for module in (issue_stamps, issueui, issueapi):
        path = module.__file__
        if path.endswith('.pyc'):
            path = path[:-1]
        with io.open(path, encoding='utf-8') as handle:
            source = handle.read()
        assert not banned.search(source), path
    with io.open(issue_stamps.__file__.replace('.pyc', '.py'), encoding='utf-8') as handle:
        assert 'picking.point(' in handle.read()


def test_stray_pin_tags():
    # Hide Pins must clear pins the session no longer remembers: found by tag prefix.
    from namo import issueapi
    tags = ['true-distance', 'playground-issues:RFI-001', 'playground-photos:PH-001', None,
            'playground-issues:RFI-002', 'playground-issues:RFI-002']
    assert issueapi.stray_pin_tags(tags) == ['playground-issues:RFI-001', 'playground-issues:RFI-002']
    assert issueapi.stray_pin_tags(tags, ['playground-issues:RFI-001']) == ['playground-issues:RFI-002']
    assert issueapi.stray_pin_tags(None) == []
