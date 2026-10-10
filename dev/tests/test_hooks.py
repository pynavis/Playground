# -*- coding: utf-8 -*-
"""namo.hooks: the dispatcher hands handlers a plain dict (lead regression test)."""
import _compat

from namo import hooks


def test_as_dict_passes_python_dicts_and_none():
    d = {'name': 'after-command', 'command': 'x'}
    assert hooks.as_dict(d) is d
    assert hooks.as_dict(None) == {}


def test_as_dict_converts_a_net_dictionary():
    _compat.require_ironpython()
    from System.Collections.Generic import Dictionary
    from System import String, Object
    net = Dictionary[String, Object]()
    net['name'] = 'after-command'
    net['command'] = 'Dev.tab/Automate.panel/Command_Palette.pushbutton'
    out = hooks.as_dict(net)
    assert isinstance(out, dict)
    assert out.get('command').endswith('Command_Palette.pushbutton')


def test_every_registered_handler_module_exists_with_handle():
    import os
    here = os.path.dirname(hooks.__file__)
    for event, module in hooks.HANDLERS:
        path = os.path.join(here, module + '.py')
        assert os.path.exists(path), module
        with open(path) as handle:
            assert 'def handle(' in handle.read(), module
