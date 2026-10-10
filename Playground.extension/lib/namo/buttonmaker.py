# -*- coding: utf-8 -*-
"""Button Maker: writes new pyNavis bundles into the user's own extension.

The user extension is %APPDATA%\\pyNavis\\extensions\\MyTools.extension, a root the
installed pyNavis scans by itself. Everything here takes the root folder as a parameter
(the real one is resolved only at click time), so tests write into temp folders.

Pure half (tested on both engines):
    folder_stem(title)                       'My tool (v2)' -> 'My_tool_v2'
    yaml_value(text) / bundle_yaml(pairs)    pyNavis' flat bundle.yaml grammar, safely quoted
    read_flat_yaml(text) -> (values, layout) the reader pyNavis and dev/check.py use
    add_layout_entry(text, entry) / remove_layout_entry(text, entry)
    initials(title) -> 'MT'
    docstring(text)                          a safe one-line module docstring
    script_source(template, title, tooltip, **kw)   'selection' | 'report' | 'toggle' |
                                             'blank' | 'macro' | 'native' | 'bundle'
    plan_bundle(root, spec) -> plan          every folder/file/layout edit, nothing written
    apply_plan(plan) -> written paths        writes atomically, creating folders
    existing_tabs(root) / existing_panels(root, tab)
    validate_spec(spec, root, taken) -> {field: sentence}

API half: render_icons(folder, spec) draws the four (or eight, for a toggle) icons with
WPF: two letters or a simple glyph on the accent colour, or a PNG the user picked.

Generated scripts that need Playground (macro buttons, native-command hotkeys, the Hotkeys
button) carry a small loader: they find Playground's lib folder through
RuntimeHost.Extensions (falling back to the path recorded when the button was made)
and append it to sys.path for that run.
"""
import io
import os
import re

from namo import paths, ribbon

EXTENSION = 'MyTools'
DEFAULT_TAB = 'MyTools'
DEFAULT_PANEL = 'Tools'
# (label, value) pairs, the order namo.ui.form options take. They were written
# (value, label) at first: the form then handed back 'Selection tool' as the template
# and Button Maker failed on its first click with "unknown template".
TEMPLATES = (('Selection tool', 'selection'), ('Report', 'report'), ('Toggle', 'toggle'),
             ('My own script file', 'file'))
TEMPLATE_IDS = tuple(value for _label, value in TEMPLATES)
GLYPHS = ('letters', 'play', 'check', 'star', 'bolt', 'grid', 'keys', 'png')
GLYPH_LABELS = (('Two letters', 'letters'), ('Play', 'play'), ('Check', 'check'),
                ('Star', 'star'), ('Bolt', 'bolt'), ('Grid', 'grid'), ('A PNG file', 'png'))


def user_root(appdata=None):
    """%APPDATA%\\pyNavis\\extensions (where MyTools.extension lives)."""
    base = appdata or os.environ.get('APPDATA') or os.path.expanduser('~')
    return os.path.join(base, 'pyNavis', 'extensions')


def extension_folder(root):
    return os.path.join(root, EXTENSION + '.extension')


# ---- names and the flat yaml grammar -------------------------------------------------

_STEM_BAD = re.compile(r'[^A-Za-z0-9_ ]+')


def folder_stem(title):
    """A folder stem pyNavis turns back into the same words: letters, digits and
    underscores; never a leading NN_ (pyNavis would strip it from the key)."""
    text = ribbon.flatten_title(title or '') or ''
    text = _STEM_BAD.sub(' ', text)
    stem = '_'.join(text.split())
    stem = re.sub(r'_+', '_', stem).strip('_')
    if re.match(r'^\d{2,}_', stem):
        stem = 'N' + stem
    return stem[:60] or 'Tool'


def yaml_value(text):
    """A value pyNavis' flat reader gives back unchanged: one line, trimmed, and wrapped
    in the other quote when it starts and ends with the same quote character."""
    value = ' '.join(str(text or '').replace('\r', ' ').split('\n')).strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in '"\'':
        other = "'" if value[0] == '"' else '"'
        value = other + value + other
    return value


def bundle_yaml(pairs, layout=None):
    """bundle.yaml text from [(key, value)] (None and '' skipped) plus a layout list."""
    lines = []
    for key, value in pairs:
        if value is None or value == '':
            continue
        lines.append('%s: %s' % (key, yaml_value(value)))
    if layout:
        lines.append('layout:')
        for entry in layout:
            lines.append('  - %s' % entry)
    return '\n'.join(lines) + '\n'


def read_flat_yaml(text):
    """(values, layout) the way pyNavis reads bundle.yaml (layout None when absent)."""
    values = {}
    layout = None
    in_layout = False
    for raw in (text or '').split('\n'):
        line = raw.rstrip('\r').strip()
        if not line or line.startswith('#'):
            continue
        if in_layout and line.startswith('-'):
            layout.append(line[1:].strip().strip('"').strip("'"))
            continue
        in_layout = False
        colon = line.find(':')
        if colon <= 0:
            continue
        key = line[:colon].strip().lower()
        value = line[colon + 1:].strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in '"\'':
            value = value[1:-1]
        if key == 'layout' and not value:
            layout = []
            in_layout = True
            continue
        values[key] = value
    return values, layout


def layout_stem(entry):
    """How pyNavis matches a layout entry to a folder: suffix optional, NN_ ignored, any case."""
    return re.sub(r'^\d{2,}_', '', ribbon.strip_suffix(str(entry).strip())).lower()


def _layout_span(lines):
    """(index of 'layout:', index after its last item) or (None, None)."""
    for index, raw in enumerate(lines):
        stripped = raw.strip()
        if stripped.lower().replace(' ', '') == 'layout:':
            end = index + 1
            cursor = index + 1
            while cursor < len(lines):
                item = lines[cursor].strip()
                if item.startswith('-'):
                    cursor += 1
                    end = cursor
                elif not item or item.startswith('#'):
                    cursor += 1
                else:
                    break
            return index, end
    return None, None


def add_layout_entry(text, entry):
    """text with entry appended to its layout: list (created when missing); unchanged
    when an entry already names the same folder."""
    _values, layout = read_flat_yaml(text)
    if layout is not None and layout_stem(entry) in [layout_stem(e) for e in layout]:
        return text
    lines = (text or '').replace('\r\n', '\n').split('\n')
    while lines and lines[-1] == '':
        lines.pop()
    start, end = _layout_span(lines)
    if start is None:
        lines.append('layout:')
        lines.append('  - %s' % entry)
    else:
        lines.insert(end, '  - %s' % entry)
    return '\n'.join(lines) + '\n'


def remove_layout_entry(text, entry):
    """text without the layout item naming entry's folder."""
    lines = (text or '').replace('\r\n', '\n').split('\n')
    start, end = _layout_span(lines)
    if start is None:
        return text
    wanted = layout_stem(entry)
    kept = lines[:start + 1]
    for line in lines[start + 1:end]:
        item = line.strip()
        if item.startswith('-') and layout_stem(item[1:].strip().strip('"').strip("'")) == wanted:
            continue
        kept.append(line)
    kept.extend(lines[end:])
    while kept and kept[-1] == '':
        kept.pop()
    return '\n'.join(kept) + '\n'


def initials(title):
    """Two letters for a generated icon: first letters of the first two words, else the
    first two letters."""
    words = re.findall(r'[A-Za-z0-9]+', ribbon.flatten_title(title or '') or '')
    if len(words) >= 2:
        return (words[0][0] + words[1][0]).upper()
    if words:
        return words[0][:2].upper() if len(words[0]) > 1 else words[0].upper()
    return 'T'


def docstring(text):
    """One safe line for a generated module docstring (pyNavis' tooltip fallback)."""
    line = ' '.join(str(text or '').split())
    line = line.replace('\\', '/').replace('"""', "'''")
    while line.endswith('"'):
        line = line[:-1].rstrip()
    return line or 'A tool made with Playground Button Maker.'


# ---- generated scripts -----------------------------------------------------------------

_LOADER = '''

NAMO_LIB = %(lib)r


def _load_namo():
    """Puts Playground's library on sys.path for this run (Playground made this button)."""
    import os
    import sys
    folders = []
    try:
        import clr
        clr.AddReference('PyNavis.Runtime')
        from PyNavis.Runtime import RuntimeHost
        for ext in RuntimeHost.Extensions:
            if str(ext.Name).lower() == 'playground' and ext.LibDirectory:
                folders.append(str(ext.LibDirectory))
    except Exception:
        pass
    folders.append(NAMO_LIB)
    for folder in folders:
        if folder and os.path.isdir(os.path.join(folder, 'namo')):
            if folder not in sys.path:
                sys.path.append(folder)
            return True
    return False
'''

_MISSING = ("toast.error('The Playground extension is not installed', "
            "'This button needs the Playground extension. Install it, or delete the button.')")


def script_source(template, title, tooltip, **kw):
    """The script.py text for a template. kw: macro (name), native_key, native_label,
    bundle_key, extension, namo_lib."""
    doc = docstring(tooltip or title)
    head = '# -*- coding: utf-8 -*-\n"""%s"""\n' % doc
    if template == 'selection':
        return head + '''from pynavis import selection, toast

items = selection.get_items()

if not items:
    toast.info('Nothing selected', 'Select something in the model and run this again.')
else:
    # Your code here: items is a list of the selected ModelItems.
    names = sorted(set(item.DisplayName for item in items))
    count = '{:,}'.format(len(items))
    toast.success('%s item%s selected' % (count, '' if len(items) == 1 else 's'), ', '.join(names[:5]))
'''
    if template == 'report':
        return head + '''from pynavis import output, selection, toast

items = selection.get_items()

if not items:
    toast.info('Nothing selected', 'Select something in the model and run this again.')
else:
    # Your code here: one row per selected item.
    rows = []
    for item in items:
        rows.append([item.DisplayName, item.ClassDisplayName])
    output.print_md('## %s' % __title__)
    output.print_table(rows, ['Name', 'Type'])
    toast.success('Listed %s item%s' % ('{:,}'.format(len(rows)), '' if len(rows) == 1 else 's'))
'''
    if template == 'toggle':
        return head + '''from pynavis import script, toast

on = not script.get_toggle_state()
script.set_toggle_state(on)
# Your code here: switch your feature on or off.
toast.info('%s is %s' % (__title__, 'on' if on else 'off'))
'''
    if template == 'blank':
        return head + '''from pynavis import toast

toast.info(__title__, 'Edit script.py to make this button do something.')
'''
    loader = _LOADER % {'lib': kw.get('namo_lib') or ''}
    if template == 'macro':
        return head + 'from pynavis import toast\n\nMACRO = %r\n' % kw['macro'] + loader + '''

if not _load_namo():
    %s
else:
    from namo import macros
    macros.play_named(MACRO)
''' % _MISSING
    if template == 'native':
        return head + 'from pynavis import toast\n\nCOMMAND = %r\nLABEL = %r\n' % (
            kw['native_key'], kw.get('native_label') or title) + loader + '''

if not _load_namo():
    %s
else:
    from namo import ribbon
    ribbon.run_native(COMMAND)
''' % _MISSING
    if template == 'bundle':
        return head + 'from pynavis import toast\n\nBUNDLE = %r\nEXTENSION = %r\n' % (
            kw['bundle_key'], kw.get('extension') or 'Playground') + loader + '''

if not _load_namo():
    %s
else:
    from namo import ribbon
    ribbon.run_bundle(BUNDLE, EXTENSION)
''' % _MISSING
    raise ValueError('unknown template %r' % template)


# ---- planning a bundle ----------------------------------------------------------------


def existing_tabs(root):
    """Tab titles already in the user extension, folder order."""
    folder = extension_folder(root)
    if not os.path.isdir(folder):
        return []
    return [ribbon.title_from_folder(d) for d in sorted(os.listdir(folder))
            if d.lower().endswith('.tab') and os.path.isdir(os.path.join(folder, d))]


def _match_folder(parent, title, suffix):
    """The existing child folder whose title is title (any case), else None."""
    if not os.path.isdir(parent):
        return None
    wanted = layout_stem(folder_stem(title))
    for name in sorted(os.listdir(parent)):
        if name.lower().endswith(suffix) and layout_stem(name) == wanted:
            return name
    return None


def existing_panels(root, tab_title):
    folder = extension_folder(root)
    tab = _match_folder(folder, tab_title, '.tab')
    if tab is None:
        return []
    path = os.path.join(folder, tab)
    return [ribbon.title_from_folder(d) for d in sorted(os.listdir(path))
            if d.lower().endswith('.panel') and os.path.isdir(os.path.join(path, d))]


def _read(path):
    if not os.path.exists(path):
        return None
    with io.open(path, encoding='utf-8-sig') as handle:
        return handle.read()


def bundle_folder_for(root, spec):
    """(tab folder, panel folder, bundle folder) names for a spec, reusing existing ones."""
    ext = extension_folder(root)
    tab = _match_folder(ext, spec['tab'], '.tab') or folder_stem(spec['tab']) + '.tab'
    panel_parent = os.path.join(ext, tab)
    panel = _match_folder(panel_parent, spec['panel'], '.panel') or folder_stem(spec['panel']) + '.panel'
    kind = spec.get('kind') or ('toggle' if spec.get('template') == 'toggle' else 'pushbutton')
    bundle = (spec.get('folder') or folder_stem(spec['title'])) + '.' + kind
    return tab, panel, bundle


def plan_bundle(root, spec):
    """Everything a new bundle needs, as data: {'folder', 'key', 'files': [(path, text)],
    'yaml': [(path, new_text)], 'icons': {...}}. spec keys: title, tooltip, template,
    script_text (for 'file'), tab, panel, shortcut, icon, letters, png, kind
    ('pushbutton' | 'toggle' | 'nobutton'), folder (stem override), extra_yaml
    [(key, value)], script kw (macro, native_key, ...)."""
    ext = extension_folder(root)
    tab, panel, bundle = bundle_folder_for(root, spec)
    tab_dir = os.path.join(ext, tab)
    panel_dir = os.path.join(tab_dir, panel)
    folder = os.path.join(panel_dir, bundle)
    yaml_edits = []

    ext_yaml_path = os.path.join(ext, 'extension.yaml')
    ext_text = _read(ext_yaml_path)
    if ext_text is None:
        ext_text = 'name: %s\nengine: ironpython\n' % EXTENSION
    new_ext = add_layout_entry(ext_text, ribbon.strip_suffix(tab))
    if new_ext != _read(ext_yaml_path):
        yaml_edits.append((ext_yaml_path, new_ext))

    tab_yaml_path = os.path.join(tab_dir, 'bundle.yaml')
    tab_text = _read(tab_yaml_path) or ''
    new_tab = add_layout_entry(tab_text, ribbon.strip_suffix(panel))
    if new_tab != tab_text or not os.path.exists(tab_yaml_path):
        yaml_edits.append((tab_yaml_path, new_tab))

    panel_yaml_path = os.path.join(panel_dir, 'bundle.yaml')
    panel_text = _read(panel_yaml_path) or ''
    new_panel = add_layout_entry(panel_text, ribbon.strip_suffix(bundle))
    if new_panel != panel_text or not os.path.exists(panel_yaml_path):
        yaml_edits.append((panel_yaml_path, new_panel))

    template = spec.get('template') or 'blank'
    if template == 'file':
        script = spec.get('script_text') or ''
    else:
        kw = dict((k, spec[k]) for k in ('macro', 'native_key', 'native_label', 'bundle_key',
                                         'extension', 'namo_lib') if k in spec)
        script = script_source(template, spec['title'], spec.get('tooltip'), **kw)
    pairs = [('title', spec['title']), ('tooltip', spec.get('tooltip')),
             ('shortcut', spec.get('shortcut'))]
    if bundle.endswith('.toggle') and spec.get('title_on'):
        pairs.append(('title_on', spec['title_on']))
    for key, value in spec.get('extra_yaml') or []:
        pairs.append((key, value))
    files = [(os.path.join(folder, 'script.py'), script),
             (os.path.join(folder, 'bundle.yaml'), bundle_yaml(pairs))]
    key = ribbon.bundle_key(ext, folder)
    return {'folder': folder, 'key': key, 'extension': EXTENSION, 'files': files,
            'yaml': yaml_edits, 'tab': ribbon.title_from_folder(tab),
            'panel': ribbon.title_from_folder(panel), 'kind': bundle.rsplit('.', 1)[-1],
            'icon': {'glyph': spec.get('icon') or 'letters',
                     'letters': (spec.get('letters') or initials(spec['title']))[:2],
                     'png': spec.get('png') or '', 'toggle': bundle.endswith('.toggle')}}


def apply_plan(plan):
    """Writes the plan (layout edits first, then the bundle). Returns the paths written.
    Raises IOError naming the file on failure."""
    written = []
    for path, text in plan['yaml'] + plan['files']:
        paths.ensure_dir(os.path.dirname(path))
        paths.atomic_write_text(path, text)
        written.append(path)
    return written


def validate_spec(spec, root, taken=None, allow_bare=False):
    """{field: sentence} for problems in a Button Maker spec. taken: {canonical chord:
    command title} of every chord in use."""
    problems = {}
    title = (spec.get('title') or '').strip()
    if not title:
        problems['title'] = 'Give the button a name.'
    elif not re.search(r'[A-Za-z0-9]', title):
        problems['title'] = 'Use at least one letter or digit in the name.'
    if not (spec.get('tab') or '').strip():
        problems['tab'] = 'Name the tab.'
    if not (spec.get('panel') or '').strip():
        problems['panel'] = 'Name the panel.'
    if title and 'title' not in problems and 'tab' not in problems and 'panel' not in problems:
        _tab, _panel, bundle = bundle_folder_for(root, spec)
        tab_dir = _match_folder(extension_folder(root), spec['tab'], '.tab')
        if tab_dir:
            panel_dir = _match_folder(os.path.join(extension_folder(root), tab_dir), spec['panel'], '.panel')
            if panel_dir:
                parent = os.path.join(extension_folder(root), tab_dir, panel_dir)
                stem = layout_stem(bundle)
                for name in os.listdir(parent):
                    if os.path.isdir(os.path.join(parent, name)) and layout_stem(name) == stem:
                        problems['title'] = 'That panel already has a button called %s.' % title
                        break
    chord_text = (spec.get('shortcut') or '').strip()
    if chord_text:
        chord, error = ribbon.parse_chord(chord_text, allow_bare)
        if chord is None:
            problems['shortcut'] = ribbon.chord_error_sentence(error)
        elif taken and chord in taken:
            problems['shortcut'] = '%s is already used by %s.' % (chord, taken[chord])
    if spec.get('template') == 'file':
        path = (spec.get('script_file') or '').strip()
        if not path:
            problems['script_file'] = 'Pick the .py file to use.'
        elif not os.path.isfile(path):
            problems['script_file'] = 'That file does not exist.'
    if spec.get('icon') == 'png':
        png = (spec.get('png') or '').strip()
        if not png:
            problems['png'] = 'Pick a PNG file for the icon.'
        elif not os.path.isfile(png):
            problems['png'] = 'That file does not exist.'
    return problems


def taken_chords(commands):
    """{canonical chord: 'Title (Tab > Panel)'} from ribbon command dicts."""
    out = {}
    for command in commands:
        chord = ribbon.chord_or_none(command.get('shortcut'), True)
        if chord and chord not in out:
            where = command.get('path') or ''
            out[chord] = '%s (%s)' % (command.get('title'), where) if where else command.get('title')
    return out


def form_fields(last, tabs, macro=False):
    """namo.ui.form fields for Button Maker (macro=True: the Macro to Button subset)."""
    if tabs:
        tab_hint = 'Existing tabs: %s. A new name makes a new tab.' % ', '.join(tabs)
    else:
        tab_hint = 'A new tab in your own MyTools extension.'
    fields = [
        {'kind': 'text', 'key': 'title', 'label': 'Button name', 'default': last.get('title', ''),
         'required': True, 'hint': 'Write \\n to break a long name onto two lines.'},
        {'kind': 'text', 'key': 'tooltip', 'label': 'Tooltip', 'default': last.get('tooltip', ''),
         'hint': 'One or two sentences: what it does and to what.'},
    ]
    if not macro:
        fields += [
            {'kind': 'radio', 'key': 'template', 'label': 'Script', 'options': list(TEMPLATES),
             'default': last.get('template', 'selection'), 'fallback': 'selection'},
            {'kind': 'file_open', 'key': 'script_file', 'label': 'Script file',
             'filter': 'Python files (*.py)|*.py', 'enabled_if': ('template', 'file')},
        ]
    fields += [
        {'kind': 'separator'},
        {'kind': 'text', 'key': 'tab', 'label': 'Tab', 'default': last.get('tab', DEFAULT_TAB), 'hint': tab_hint},
        {'kind': 'text', 'key': 'panel', 'label': 'Panel', 'default': last.get('panel', DEFAULT_PANEL)},
        {'kind': 'text', 'key': 'shortcut', 'label': 'Shortcut (optional)', 'default': '',
         'placeholder': 'Ctrl+Alt+K', 'hint': 'Ctrl or Alt plus one key: a letter, digit, F1 to F24 or an arrow.'},
        {'kind': 'choice', 'key': 'icon', 'label': 'Icon', 'options': list(GLYPH_LABELS),
         'default': last.get('icon', 'play' if macro else 'letters'), 'fallback': 'play' if macro else 'letters'},
        {'kind': 'text', 'key': 'letters', 'label': 'Letters on the icon', 'default': '',
         'placeholder': 'From the name', 'enabled_if': ('icon', 'letters')},
        {'kind': 'file_open', 'key': 'png', 'label': 'Icon file', 'filter': 'PNG images (*.png)|*.png',
         'enabled_if': ('icon', 'png')},
    ]
    return fields


def spec_from(values, macro_name=None):
    """A plan_bundle spec from the form values."""
    spec = {'title': (values.get('title') or '').strip(), 'tooltip': (values.get('tooltip') or '').strip(),
            'template': values.get('template') or ('macro' if macro_name else 'selection'),
            'script_file': values.get('script_file') or '', 'tab': (values.get('tab') or '').strip(),
            'panel': (values.get('panel') or '').strip(),
            'shortcut': ribbon.chord_or_none(values.get('shortcut'), True) or (values.get('shortcut') or '').strip(),
            'icon': values.get('icon') or 'letters', 'letters': (values.get('letters') or '').strip().upper()[:2],
            'png': values.get('png') or ''}
    if macro_name:
        spec['template'] = 'macro'
        spec['macro'] = macro_name
        if not spec['tooltip']:
            spec['tooltip'] = 'Plays the macro %s.' % macro_name
    if spec['template'] == 'toggle':
        spec['kind'] = 'toggle'
    return spec


def remembered(values):
    """What Button Maker remembers for next time (never the name or the shortcut)."""
    return dict((k, values.get(k)) for k in ('template', 'tab', 'panel', 'icon') if values.get(k))


def namo_lib_folder():
    """This library's own lib folder (what generated scripts load)."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ---- icons (WPF) ---------------------------------------------------------------------------

LIGHT = {'accent': (0, 120, 212), 'on_accent': (255, 255, 255)}
DARK = {'accent': (76, 194, 255), 'on_accent': (32, 32, 32)}

# Glyph outlines on a 96 x 96 canvas: (kind, geometry), kind 'fill' or 'stroke'.
GLYPH_SHAPES = {
    'play': [('fill', 'M 36,26 L 72,48 L 36,70 Z')],
    'check': [('stroke', 'M 26,50 L 42,66 L 72,32')],
    'star': [('fill', 'M 48,18 L 57,38 L 79,40 L 62,55 L 67,77 L 48,66 L 29,77 L 34,55 '
                      'L 17,40 L 39,38 Z')],
    'bolt': [('fill', 'M 54,14 L 28,54 L 46,54 L 40,82 L 68,40 L 50,40 Z')],
    'grid': [('fill', 'M 24,24 L 44,24 L 44,44 L 24,44 Z M 52,24 L 72,24 L 72,44 L 52,44 Z '
                      'M 24,52 L 44,52 L 44,72 L 24,72 Z M 52,52 L 72,52 L 72,72 L 52,72 Z')],
    'keys': [('stroke', 'M 22,30 L 74,30 L 74,66 L 22,66 Z'),
             ('fill', 'M 30,38 L 38,38 L 38,44 L 30,44 Z M 44,38 L 52,38 L 52,44 L 44,44 Z '
                      'M 58,38 L 66,38 L 66,44 L 58,44 Z M 34,52 L 62,52 L 62,58 L 34,58 Z')],
}

ICON_FILES = (('icon.png', 96, False), ('icon.dark.png', 96, True),
              ('icon.small.png', 32, False), ('icon.small.dark.png', 32, True))
TOGGLE_FILES = (('icon.on.png', 96, False, True), ('icon.on.dark.png', 96, True, True),
                ('icon.off.png', 96, False, False), ('icon.off.dark.png', 96, True, False))


def _color(rgb):
    from System.Windows.Media import Color
    return Color.FromRgb(rgb[0], rgb[1], rgb[2])


def _brush(rgb):
    from System.Windows.Media import SolidColorBrush
    value = SolidColorBrush(_color(rgb))
    value.Freeze()
    return value


def _draw_badge(dc, theme, filled, glyph, letters):
    """Draws on a 96-unit canvas: an accent tile (or outline) with the glyph or letters."""
    from System.Globalization import CultureInfo
    from System.Windows import FlowDirection, FontStyles, FontWeights, FontStretches, Point, Rect
    from System.Windows.Media import FontFamily, FormattedText, Geometry, Pen, PenLineCap, Typeface
    accent = _brush(theme['accent'])
    mark = _brush(theme['on_accent']) if filled else accent
    pen = Pen(accent, 6.0)
    dc.DrawRoundedRectangle(accent if filled else None, None if filled else pen,
                            Rect(8, 8, 80, 80), 16, 16)
    if glyph in GLYPH_SHAPES:
        for kind, data in GLYPH_SHAPES[glyph]:
            geometry = Geometry.Parse(data)
            if kind == 'fill':
                dc.DrawGeometry(mark, None, geometry)
            else:
                stroke = Pen(mark, 8.0)
                stroke.StartLineCap = PenLineCap.Round
                stroke.EndLineCap = PenLineCap.Round
                dc.DrawGeometry(None, stroke, geometry)
        return
    text = (letters or 'T')[:2]
    typeface = Typeface(FontFamily('Segoe UI Variable Display, Segoe UI'), FontStyles.Normal,
                        FontWeights.SemiBold, FontStretches.Normal)
    size = 44.0 if len(text) == 1 else 38.0
    try:
        formatted = FormattedText(text, CultureInfo.InvariantCulture, FlowDirection.LeftToRight,
                                  typeface, size, mark, 1.0)
    except Exception:
        formatted = FormattedText(text, CultureInfo.InvariantCulture, FlowDirection.LeftToRight,
                                  typeface, size, mark)
    x = 48 - formatted.Width / 2.0
    y = 48 - formatted.Height / 2.0
    dc.DrawText(formatted, Point(x, y))


def _render(path, size, theme, filled, glyph, letters, png=None):
    import clr
    for name in ('PresentationCore', 'PresentationFramework', 'WindowsBase'):
        clr.AddReference(name)
    from System.IO import File, FileMode
    from System.Windows import Rect
    from System.Windows.Media import DrawingVisual, PixelFormats, ScaleTransform
    from System.Windows.Media.Imaging import (BitmapCacheOption, BitmapFrame, BitmapImage,
                                              PngBitmapEncoder, RenderTargetBitmap)
    from System import Uri
    visual = DrawingVisual()
    dc = visual.RenderOpen()
    try:
        if png:
            image = BitmapImage()
            image.BeginInit()
            image.CacheOption = BitmapCacheOption.OnLoad
            image.UriSource = Uri(os.path.abspath(png))
            image.EndInit()
            w, h = float(image.PixelWidth), float(image.PixelHeight)
            scale = min(size / w, size / h) if w and h else 1.0
            dw, dh = w * scale, h * scale
            dc.DrawImage(image, Rect((size - dw) / 2.0, (size - dh) / 2.0, dw, dh))
        else:
            dc.PushTransform(ScaleTransform(size / 96.0, size / 96.0))
            _draw_badge(dc, theme, filled, glyph, letters)
            dc.Pop()
    finally:
        dc.Close()
    bitmap = RenderTargetBitmap(size, size, 96.0, 96.0, PixelFormats.Pbgra32)
    bitmap.Render(visual)
    encoder = PngBitmapEncoder()
    encoder.Frames.Add(BitmapFrame.Create(bitmap))
    paths.ensure_dir(os.path.dirname(path))
    temp = path + '.tmp'
    stream = File.Open(temp, FileMode.Create)
    try:
        encoder.Save(stream)
    finally:
        stream.Close()
    os.replace(temp, path)
    return path


def render_icons(folder, icon):
    """Writes icon.png, icon.dark.png, icon.small.png, icon.small.dark.png (and the
    on/off pairs for a toggle). icon: {'glyph', 'letters', 'png', 'toggle'}. Returns the
    files written."""
    glyph = icon.get('glyph') or 'letters'
    png = icon.get('png') if glyph == 'png' else None
    letters = icon.get('letters') or 'T'
    toggle = bool(icon.get('toggle'))
    written = []
    for name, size, dark in ICON_FILES:
        filled = not toggle
        written.append(_render(os.path.join(folder, name), size, DARK if dark else LIGHT,
                               filled, glyph, letters, png))
    if toggle:
        for name, size, dark, on in TOGGLE_FILES:
            written.append(_render(os.path.join(folder, name), size, DARK if dark else LIGHT,
                                   on, glyph, letters, png))
    return written


def make(root, spec, icons=True):
    """Plans and writes a bundle, then its icons. Returns the plan."""
    plan = plan_bundle(root, spec)
    apply_plan(plan)
    if icons:
        render_icons(plan['folder'], plan['icon'])
    return plan
