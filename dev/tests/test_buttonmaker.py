# -*- coding: utf-8 -*-
"""namo.buttonmaker: names, the flat yaml grammar, layout edits, script templates and
whole-bundle plans written into temp roots. Under IronPython the real pyNavis
BundleParser reads what was written."""
import io
import os

import _compat

from namo import buttonmaker as bm


def test_folder_stem():
    assert bm.folder_stem('My tool') == 'My_tool'
    assert bm.folder_stem('  Export (v2): rooms!  ') == 'Export_v2_rooms'
    assert bm.folder_stem('Select\\nSimilar') == 'Select_Similar'
    assert bm.folder_stem('2026 Report') == 'N2026_Report'
    assert bm.folder_stem('***') == 'Tool'
    assert bm.folder_stem(None) == 'Tool'


def test_yaml_values_survive_the_flat_reader():
    for value in ['Plain', '"Quoted"', "'Single'", 'Ratio 3:1 # kept', 'Two\nlines']:
        text = bm.bundle_yaml([('tooltip', value)])
        values, layout = bm.read_flat_yaml(text)
        expected = ' '.join(value.split('\n')).strip()
        assert values['tooltip'] == expected, (value, values)
        assert layout is None
    text = bm.bundle_yaml([('title', 'A'), ('shortcut', None), ('tooltip', '')], layout=['X', 'Y'])
    assert text == 'title: A\nlayout:\n  - X\n  - Y\n'


def test_layout_add_and_remove():
    text = 'title: Panel\nlayout:\n  - One\n  # note\n  - Two\nother: x\n'
    added = bm.add_layout_entry(text, 'Three')
    assert bm.read_flat_yaml(added)[1] == ['One', 'Two', 'Three']
    assert bm.read_flat_yaml(added)[0]['other'] == 'x'
    assert bm.add_layout_entry(added, 'three.pushbutton') == added       # already listed
    assert bm.add_layout_entry(added, '01_Two') == added
    fresh = bm.add_layout_entry('', 'Hotkeys')
    assert fresh == 'layout:\n  - Hotkeys\n'
    no_layout = bm.add_layout_entry('name: MyTools\nengine: ironpython\n', 'MyTools')
    assert bm.read_flat_yaml(no_layout) == ({'name': 'MyTools', 'engine': 'ironpython'}, ['MyTools'])
    removed = bm.remove_layout_entry(added, 'Two.pushbutton')
    assert bm.read_flat_yaml(removed)[1] == ['One', 'Three']
    assert bm.remove_layout_entry('title: x\n', 'Two') == 'title: x\n'
    assert bm.layout_stem('02_Recall.pushbutton') == 'recall'


def test_initials_and_docstrings():
    assert bm.initials('Clash report') == 'CR'
    assert bm.initials('Export') == 'EX'
    assert bm.initials('x') == 'X'
    assert bm.initials('') == 'T'
    assert bm.docstring('Says "hi"') == 'Says "hi'
    assert bm.docstring('a """ b \\ c') == "a ''' b / c"
    assert bm.docstring('') == 'A tool made with Playground Button Maker.'


def test_every_template_compiles():
    for template in ('selection', 'report', 'toggle', 'blank'):
        source = bm.script_source(template, 'My tool', 'Does a thing.')
        compile(source, 'script.py', 'exec')
        assert '"""Does a thing."""' in source
    lib = r'C:\Users\me\AppData\Roaming\pyNavis\extensions\Playground.extension\lib'
    for template, kw in (('macro', {'macro': "Bob's macro"}),
                         ('native', {'native_key': 'native:ID_TabHome/ID_Select', 'native_label': 'Select'}),
                         ('bundle', {'bundle_key': 'Dev.tab/Build.panel/Hotkey_Manager.pushbutton'})):
        kw['namo_lib'] = lib
        source = bm.script_source(template, 'Title', 'Tip.', **kw)
        compile(source, 'script.py', 'exec')
        assert 'NAMO_LIB = %r' % lib in source
        assert '_load_namo()' in source
    raised = _compat.raises(ValueError, bm.script_source, 'nope', 'x', 'y')
    assert 'nope' in str(raised)


def _spec(**kw):
    spec = {'title': 'Count Doors', 'tooltip': 'Counts the selected doors.', 'template': 'selection',
            'tab': 'MyTools', 'panel': 'Tools', 'shortcut': 'Ctrl+Alt+D', 'icon': 'letters'}
    spec.update(kw)
    return spec


def _read(path):
    with io.open(path, encoding='utf-8') as handle:
        return handle.read()


def test_plan_and_apply_into_an_empty_root():
    root = _compat.tmpdir('buttonmaker_empty')
    plan = bm.plan_bundle(root, _spec())
    ext = os.path.join(root, 'MyTools.extension')
    assert plan['folder'] == os.path.join(ext, 'MyTools.tab', 'Tools.panel', 'Count_Doors.pushbutton')
    assert plan['key'] == 'MyTools.tab/Tools.panel/Count_Doors.pushbutton'
    assert plan['icon'] == {'glyph': 'letters', 'letters': 'CD', 'png': '', 'toggle': False}
    assert not os.path.exists(ext)                    # planning writes nothing
    bm.apply_plan(plan)
    values, layout = bm.read_flat_yaml(_read(os.path.join(ext, 'extension.yaml')))
    assert values == {'name': 'MyTools', 'engine': 'ironpython'} and layout == ['MyTools']
    assert bm.read_flat_yaml(_read(os.path.join(ext, 'MyTools.tab', 'bundle.yaml')))[1] == ['Tools']
    assert bm.read_flat_yaml(_read(os.path.join(ext, 'MyTools.tab', 'Tools.panel', 'bundle.yaml')))[1] == ['Count_Doors']
    values, _ = bm.read_flat_yaml(_read(os.path.join(plan['folder'], 'bundle.yaml')))
    assert values == {'title': 'Count Doors', 'tooltip': 'Counts the selected doors.', 'shortcut': 'Ctrl+Alt+D'}
    assert bm.existing_tabs(root) == ['MyTools']
    assert bm.existing_panels(root, 'mytools') == ['Tools']

    # A second button in the same panel reuses every container and appends one entry.
    plan2 = bm.plan_bundle(root, _spec(title='Toggle Thing', template='toggle', panel='tools',
                                       shortcut='', title_on='Thing\\nOff'))
    assert plan2['folder'].endswith(os.path.join('Tools.panel', 'Toggle_Thing.toggle'))
    assert [p for p, _t in plan2['yaml']] == [os.path.join(ext, 'MyTools.tab', 'Tools.panel', 'bundle.yaml')]
    bm.apply_plan(plan2)
    assert bm.read_flat_yaml(_read(os.path.join(ext, 'MyTools.tab', 'Tools.panel', 'bundle.yaml')))[1] == \
        ['Count_Doors', 'Toggle_Thing']
    values, _ = bm.read_flat_yaml(_read(os.path.join(plan2['folder'], 'bundle.yaml')))
    assert values['title_on'] == 'Thing\\nOff' and 'shortcut' not in values
    assert plan2['icon']['toggle'] is True


def test_validate_spec():
    root = _compat.tmpdir('buttonmaker_validate')
    bm.apply_plan(bm.plan_bundle(root, _spec()))
    taken = {'Ctrl+Shift+P': 'Command Palette (Dev > Automate)'}
    assert bm.validate_spec(_spec(title='New one', shortcut='ctrl+alt+n'), root, taken) == {}
    problems = bm.validate_spec(_spec(title='count doors', shortcut='Ctrl+Shift+P'), root, taken)
    assert problems['title'] == 'That panel already has a button called count doors.'
    assert problems['shortcut'] == 'Ctrl+Shift+P is already used by Command Palette (Dev > Automate).'
    problems = bm.validate_spec(_spec(title='', tab='', shortcut='Shift+K'), root, taken)
    assert set(problems) == set(['title', 'tab', 'shortcut'])
    assert problems['shortcut'] == 'A shortcut needs Ctrl or Alt.'
    problems = bm.validate_spec(_spec(title='X', template='file', script_file='', icon='png', png='nope.png'),
                                root, taken)
    assert problems['script_file'] == 'Pick the .py file to use.'
    assert problems['png'] == 'That file does not exist.'


def test_taken_chords():
    commands = [{'title': 'A', 'path': 'T > P', 'shortcut': 'ctrl+shift+a'},
                {'title': 'B', 'path': '', 'shortcut': 'Ctrl+Shift+A'},
                {'title': 'C', 'path': 'T > P', 'shortcut': ''}]
    assert bm.taken_chords(commands) == {'Ctrl+Shift+A': 'A (T > P)'}


def test_the_real_parser_reads_what_was_written():
    _compat.require_ironpython()
    import clr
    clr.AddReference('PyNavis.Runtime')
    from PyNavis.Runtime.Bundles import BundleParser
    root = _compat.tmpdir('buttonmaker_parser')
    bm.apply_plan(bm.plan_bundle(root, _spec()))
    bm.apply_plan(bm.plan_bundle(root, _spec(title='Toggle Thing', template='toggle', shortcut='')))
    bm.apply_plan(bm.plan_bundle(root, _spec(title='Run Select', kind='nobutton', template='native',
                                             native_key='native:ID_TabHome/ID_Select',
                                             namo_lib='C:\\x', shortcut='Ctrl+Alt+S',
                                             extra_yaml=[('command', 'native:ID_TabHome/ID_Select')])))
    found = list(BundleParser.ParseRoot(root))
    assert len(found) == 1
    ext = found[0]
    assert ext.Name == 'MyTools' and list(ext.Problems) == []
    tabs = list(ext.Tabs)
    assert [t.Title for t in tabs] == ['MyTools']
    panel = list(tabs[0].Panels)[0]
    assert panel.Title == 'Tools'
    buttons = list(panel.Buttons)
    assert [b.Title for b in buttons] == ['Count Doors', 'Toggle Thing', 'Run Select']
    assert buttons[0].Shortcut == 'Ctrl+Alt+D' and buttons[0].Tooltip == 'Counts the selected doors.'
    assert buttons[0].BundleKey == 'MyTools.tab/Tools.panel/Count_Doors.pushbutton'
    assert buttons[1].IsToggle and buttons[2].NoUi and buttons[2].Shortcut == 'Ctrl+Alt+S'


def test_form_fields_and_specs():
    fields = bm.form_fields({'tab': 'Review', 'template': 'report'}, ['MyTools', 'Review'])
    keys = [f.get('key') for f in fields if f.get('key')]
    assert keys == ['title', 'tooltip', 'template', 'script_file', 'tab', 'panel', 'shortcut', 'icon',
                    'letters', 'png']
    tab = [f for f in fields if f.get('key') == 'tab'][0]
    assert tab['default'] == 'Review' and tab['hint'].startswith('Existing tabs: MyTools, Review.')
    macro_fields = bm.form_fields({}, [], macro=True)
    assert 'template' not in [f.get('key') for f in macro_fields]
    assert [f for f in macro_fields if f.get('key') == 'icon'][0]['default'] == 'play'
    values = {'title': ' Count ', 'tooltip': '', 'template': 'toggle', 'tab': 'MyTools', 'panel': 'Tools',
              'shortcut': 'ctrl+alt+c', 'icon': 'letters', 'letters': 'cd', 'png': ''}
    spec = bm.spec_from(values)
    assert spec['title'] == 'Count' and spec['shortcut'] == 'Ctrl+Alt+C' and spec['letters'] == 'CD'
    assert spec['kind'] == 'toggle'
    spec = bm.spec_from(dict(values, template=None), macro_name='Morning')
    assert spec['template'] == 'macro' and spec['macro'] == 'Morning' and spec['tooltip'] == 'Plays the macro Morning.'
    assert bm.remembered(values) == {'template': 'toggle', 'tab': 'MyTools', 'panel': 'Tools', 'icon': 'letters'}
