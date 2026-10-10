# -*- coding: utf-8 -*-
"""namo.presentation pure half: options, the state codec and the messages."""
import _compat

from namo import presentation


def test_normalize_options():
    assert presentation.normalize_options(None) == {'panes': True, 'maximize': True, 'background': ''}
    opts = presentation.normalize_options({'panes': 0, 'maximize': 1, 'background': 'Dark gradient'})
    assert opts == {'panes': False, 'maximize': True, 'background': 'Dark gradient'}
    assert presentation.normalize_options({'background': 'Neon'})['background'] == ''


def test_option_fields():
    fields = presentation.option_fields({'background': 'Black'})
    by_key = dict((f['key'], f) for f in fields if f.get('key'))
    assert by_key['background']['default'] == 'Black'
    assert by_key['background']['options'][0] == ('Keep the current background', '')
    assert by_key['panes']['default'] is True


def test_state_codec_is_stable_and_safe():
    state = presentation.new_state()
    state['ribbon'] = 'None'
    state['panes'] = ['b.pane', 'a.pane']
    text = presentation.encode(state)
    assert text == presentation.encode(presentation.decode(text))
    assert text.index('"background"') < text.index('"panes"') < text.index('"ribbon"')
    assert presentation.decode(text)['ribbon'] == 'None'
    for bad in (None, '', 'not json', '[1, 2]'):
        assert presentation.decode(bad) is None


def test_enter_message():
    state = presentation.new_state()
    message, detail = presentation.enter_message(state, [])
    assert message == 'Presentation mode on'
    assert 'Ctrl+Alt+F11' in detail
    state.update({'ribbon': 'None', 'panes': ['a'], 'window': True})
    message, detail = presentation.enter_message(state, ['The ribbon could not be minimized.'])
    assert message == 'Presentation mode on: ribbon minimized, 1 panel closed, window maximized'
    assert detail.startswith('The ribbon could not be minimized.')


def test_changed_and_nothing_message():
    state = presentation.new_state()
    assert not presentation.changed(state) and not presentation.changed(None)
    for key, value in (('ribbon', 'None'), ('panes', ['a']), ('window', True),
                       ('background', {'style': 'plain', 'colors': ['FFFFFF']})):
        other = presentation.new_state()
        other[key] = value
        assert presentation.changed(other), key
    assert presentation.nothing_message([])[1].startswith('The ribbon is already')
    assert presentation.nothing_message(['X.'])[1] == 'X.'


def test_exit_message():
    assert presentation.exit_message(['ribbon', 'panels'], []) == \
        ('success', 'Presentation mode off', 'Restored the ribbon and panels.')
    assert presentation.exit_message([], [])[2] == 'Nothing needed restoring.'
    level, message, detail = presentation.exit_message(['ribbon'], ['The background stayed.'])
    assert level == 'warning' and detail == 'The background stayed.'


def test_leave_without_state_is_quiet():
    _compat.require_ironpython('needs the .NET AppDomain')
    assert presentation.is_on() is False
    assert presentation.leave() == ([], [])


def test_panes_close_and_reopen_through_the_loaded_plugin():
    """Dock panels are switched the way pyNavis' own panel buttons do it
    (DockPanePlugin.Visible on the loaded plugin), and a plugin nobody loaded
    is never loaded just to be closed."""
    import test_items as nav

    class Pane(object):
        def __init__(self, visible):
            self.Visible = visible

        def ActivatePane(self):
            pass

    class Record(object):
        def __init__(self, plugin_id, plugin, loaded=True):
            self.Id = plugin_id
            self.LoadedPlugin = plugin
            self.IsLoaded = loaded

    open_pane, closed_pane = Pane(True), Pane(False)
    records = [Record('B.Pane', open_pane), Record('A.Pane', closed_pane),
               Record('Tool.X', object()), Record('C.Pane', None, loaded=False)]
    by_id = dict((r.Id, r) for r in records)
    with nav.FakeNav() as layer:
        import sys
        application = sys.modules['pynavis._api'].Application
        application.Plugins = nav._Ns(PluginRecords=records, FindPlugin=lambda pid: by_id.get(pid))
        assert presentation._visible_panes() == ['B.Pane']
        presentation._set_pane('B.Pane', False)
        assert open_pane.Visible is False and presentation._visible_panes() == []
        presentation._set_pane('B.Pane', True)
        assert open_pane.Visible is True
        for gone in ('C.Pane', 'Tool.X', 'Missing'):
            _compat.raises(LookupError, presentation._set_pane, gone, True)
    del layer
