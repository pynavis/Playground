# -*- coding: utf-8 -*-
"""namo.palette pure half: entries, ranking with MRU, blocked commands, display rows."""
import _compat

from namo import palette, paths

COMMANDS = [
    {'kind': 'bundle', 'key': 'Dev.tab/Automate.panel/Command_Palette.pushbutton',
     'title': 'Command Palette', 'path': 'Dev > Automate', 'tooltip': 'Runs any command by name.',
     'shortcut': 'Ctrl+Shift+P', 'extension': 'Playground', 'enabled': True, 'context': '', 'hidden': False},
    {'kind': 'bundle', 'key': 'pyNavis.tab/Clash.panel/Clash_Grouper.pushbutton',
     'title': 'Clash Grouper', 'path': 'pyNavis > Clash', 'tooltip': 'Groups clash results.',
     'shortcut': '', 'extension': 'pyNavis', 'enabled': True, 'context': 'clash-results', 'hidden': False},
    {'kind': 'bundle', 'key': 'Model.tab/Select.panel/Select_Similar.pushbutton',
     'title': 'Select Similar', 'path': 'Model > Select', 'tooltip': 'Selects elements like the selection.',
     'shortcut': '', 'extension': 'Playground', 'enabled': False, 'context': 'selection', 'hidden': False},
    {'kind': 'bundle', 'key': 'pyNavis.tab/Viewpoints.panel/Nudge_In.nobutton',
     'title': 'Nudge In', 'path': 'pyNavis > Viewpoints', 'tooltip': '', 'shortcut': 'Ctrl+Alt+Up',
     'extension': 'pyNavis', 'enabled': True, 'context': '', 'hidden': True},
    {'kind': 'native', 'key': 'native:ID_TabHome/ID_ClashDetective', 'title': 'Clash Detective',
     'path': 'Home > Tools', 'tooltip': '', 'shortcut': '', 'extension': 'Navisworks', 'enabled': True,
     'context': ''},
]


def entries():
    out = [palette.from_command(c) for c in COMMANDS]
    out += palette.view_entries([('', 'Overall'), ('Level 1/Coordination', 'Lobby clash')])
    out += palette.set_entries([
        {'key': '0', 'parent_key': '', 'name': 'MEP', 'is_folder': True},
        {'key': '0/0', 'parent_key': '0', 'name': 'Ducts', 'is_folder': False, 'guid': 'g1'},
        {'key': '0/1', 'parent_key': '0', 'name': 'Sub/Folder', 'is_folder': True},
        {'key': '0/1/0', 'parent_key': '0/1', 'name': 'Pipes', 'is_folder': False, 'guid': 'g2'},
        {'key': '1', 'parent_key': '', 'name': 'Walls', 'is_folder': False, 'guid': 'g3'},
    ])
    return out


def test_entries_and_ids():
    all_ = entries()
    assert all_[0]['id'] == 'bundle|playground|dev.tab/automate.panel/command_palette.pushbutton'
    assert all_[3]['detail'] == 'pyNavis > Viewpoints > shortcut only'
    assert all_[4]['detail'] == 'Navisworks > Home > Tools' and all_[4]['id'] == 'native|native:id_tabhome/id_clashdetective'
    views = [e for e in all_ if e['kind'] == 'view']
    assert [(v['title'], v['target'], v['detail']) for v in views] == [
        ('Go to view: Overall', 'Overall', 'Saved viewpoints'),
        ('Go to view: Lobby clash', 'Level 1/Coordination/Lobby clash',
         'Saved viewpoints > Level 1 > Coordination')]
    sets = [e for e in all_ if e['kind'] == 'set']
    assert [(s['title'], s['target'], s['detail']) for s in sets] == [
        ('Select set: Ducts', 'MEP/Ducts', 'Selection sets > MEP'),
        ('Select set: Pipes', 'MEP/Sub\\/Folder/Pipes', 'Selection sets > MEP > Sub/Folder'),
        ('Select set: Walls', 'Walls', 'Selection sets')]
    assert palette.set_path(['A/B', 'C']) == 'A\\/B/C'


def test_ranking_prefers_titles_then_mru():
    ranker = palette.Ranker(entries())
    total, order = ranker.rank('clash')
    titles = [ranker.entries[i]['title'] for i in order]
    assert titles[:2] == ['Clash Grouper', 'Clash Detective']
    assert 'Go to view: Lobby clash' in titles
    ranker.set_mru(['native|native:id_tabhome/id_clashdetective'])
    _total, order = ranker.rank('clash')
    assert ranker.entries[order[0]]['title'] == 'Clash Detective'
    _total, order = ranker.rank('zzzz')
    assert order == []
    _total, order = ranker.rank('ducts')
    assert ranker.entries[order[0]]['title'] == 'Select set: Ducts'


def test_ranking_by_path_and_tooltip():
    ranker = palette.Ranker(entries())
    _total, order = ranker.rank('automate')
    assert ranker.entries[order[0]]['title'] == 'Command Palette'
    _total, order = ranker.rank('groups results')
    assert ranker.entries[order[0]]['title'] == 'Clash Grouper'


def test_empty_query_lists_mru_first():
    items = entries()
    ranker = palette.Ranker(items, ['set|walls', 'missing|thing', 'view|overall'])
    total, order = ranker.rank('')
    assert total == len(items)
    assert [ranker.entries[i]['title'] for i in order[:3]] == \
        ['Select set: Walls', 'Go to view: Overall', 'Command Palette']
    _total, order = ranker.rank('', limit=2)
    assert len(order) == 2


def test_blocked_commands_sink_and_explain():
    items = entries()
    similar = [e for e in items if e['title'] == 'Select Similar'][0]
    assert palette.blocked(similar) == 'Select Similar needs a selection.'
    assert palette.blocked(items[0]) is None
    similar_two = dict(similar, context='')
    assert palette.blocked(similar_two) == 'Select Similar is not available right now.'
    shown = palette.display(similar, 'sim')
    assert shown['muted'] and shown['detail'] == 'Model > Select, needs a selection'
    assert shown['title_spans'] == [(7, 10)]
    shown = palette.display(items[0], '')
    assert shown == {'title': 'Command Palette', 'title_spans': [], 'detail': 'Dev > Automate',
                     'detail_spans': [], 'shortcut': 'Ctrl+Shift+P', 'muted': False}


def test_pieces_and_status():
    assert palette.pieces('Clash', [(0, 2)]) == [('Cl', True), ('ash', False)]
    assert palette.pieces('', []) == [('', False)]
    assert palette.status_text(320, 0, 0, '') == '320 commands, views and sets'
    assert palette.status_text(320, 0, 0, 'x') == 'No matches'
    assert palette.status_text(320, 1, 1, 'x') == '1 match'
    assert palette.status_text(3200, 1500, 100, 'x') == '1,500 matches, showing the best 100'


def test_mru_is_kept_locally():
    folder = _compat.tmpdir('palette_mru')
    previous = paths.redirect(folder)
    try:
        assert palette.load_mru() == []
        palette.remember({'id': 'a'})
        palette.remember({'id': 'b'})
        palette.remember({'id': 'a'})
        assert palette.load_mru() == ['a', 'b']
    finally:
        paths.redirect(previous)
