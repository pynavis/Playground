# -*- coding: utf-8 -*-
"""Static checks for the Playground extension: the pyNavis bundle contract plus house rules.

    python dev/check.py            everything
    python dev/check.py --quiet    only problems and the summary line

What it enforces (each one is a rule that otherwise fails silently in Navisworks):
  * every container (tab, panel, stack, pulldown, splitbutton, splitpushbutton, slideout)
    has a bundle.yaml layout: listing every child, and lists nothing that is missing
  * stacks hold 2 or 3 pushbuttons; pushbutton-shaped bundles have script.py, a module
    docstring, a bundle.yaml with title and tooltip, and all four icons (toggles and
    dockpanes their extra on/off art); dockpanes have a pane.xaml whose root is not a Window
  * bundle.yaml keys are ones pyNavis reads, context: names are the seven real ones,
    shortcut: chords parse, need Ctrl or Alt, and collide with nothing in Playground or pyNavis
  * Python: parses, no f-strings, no `if __name__ == '__main__'`, no print() in bundle
    scripts, no em or en dashes in any string, no star imports from pynavis, no call to
    pynavis' custom pick tool (pick.point / pick.point_then: use namo.picking; a mention in
    a docstring or comment is fine, only code counts)
  * user-facing text (title, tooltip) has no dashes and starts with a capital letter
"""
import ast
import io
import os
import re
import sys
import xml.dom.minidom

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EXT = os.environ.get('PLAYGROUND_EXT') or os.path.join(ROOT, 'Playground.extension')
# A pyNavis checkout (PYNAVIS_SRC, else a 'pyNavis' folder beside this repo), for chord collisions.
PYNAVIS_EXT = os.path.join(os.environ.get('PYNAVIS_SRC') or os.path.join(os.path.dirname(ROOT), 'pyNavis'), 'extensions', 'pyNavis.extension')

CONTAINERS = ('.tab', '.panel', '.stack', '.pulldown', '.splitbutton', '.splitpushbutton', '.slideout')
PUSHLIKE = ('.pushbutton', '.nobutton', '.toggle', '.smartbutton')
ITEMS = PUSHLIKE + ('.stack', '.pulldown', '.splitbutton', '.splitpushbutton', '.slideout',
                    '.urlbutton', '.linkbutton', '.dockpane')
PUSH_KEYS = {'title', 'tooltip', 'engine', 'shortcut', 'keytip', 'context', 'min_host_version',
             'max_host_version', 'title_on', 'tooltip_on'}
CONTEXT_NAMES = {'doc', 'selection', 'clash-tests', 'clash-results', 'viewpoints',
                 'selection-sets', 'multi-model'}
HOOK_EVENTS = {'doc-opened', 'doc-closed', 'doc-saved', 'model-appended', 'model-removed',
               'selection-changed', 'selection-sets-changed', 'viewpoints-changed',
               'viewpoint-recalled', 'camera-moved', 'app-init', 'app-closing', 'before-command',
               'after-command'}
KEYS = set('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789') | {'F%d' % i for i in range(1, 25)} | {
    'LEFT', 'UP', 'RIGHT', 'DOWN', 'HOME', 'END', 'PGUP', 'PGDN'}
DASHES = (u'\u2014', u'\u2013')

# pynavis.pick's custom pick tool: the first field click showed its marker and the point it
# returns disagree. Every Playground pick goes through namo.picking (the host's Measure tool).
BANNED_PICKS = ('point', 'point_then')

problems = []
notes = []


def problem(path, message):
    problems.append('%s: %s' % (os.path.relpath(path, ROOT), message))


def read_yaml(path):
    """pyNavis' flat reader, plus the layout: block list."""
    result = {}
    layout = None
    if not os.path.exists(path):
        return result, layout
    with io.open(path, encoding='utf-8-sig') as handle:
        lines = handle.read().split('\n')
    in_layout = False
    for raw in lines:
        line = raw.rstrip('\r').strip()
        if not line or line.startswith('#'):
            continue
        if in_layout and line.startswith('-'):
            layout.append(line[1:].strip().strip('"').strip("'"))
            continue
        in_layout = False
        colon = line.find(':')
        if colon <= 0:
            # pyNavis' flat reader drops this line silently. The classic cause: a real
            # line break written where a two-line caption needed the two characters
            # backslash and n.
            problem(path, 'line %r has no key: pyNavis ignores it (titles need a literal '
                    'backslash-n, not a line break)' % line[:40])
            continue
        key = line[:colon].strip().lower()
        value = line[colon + 1:].strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in '"\'':
            value = value[1:-1]
        if key == 'layout' and not value:
            layout = []
            in_layout = True
            continue
        result[key] = value
    return result, layout


def suffix_of(name):
    lower = name.lower()
    for s in sorted(ITEMS + ('.tab', '.panel'), key=len, reverse=True):
        if lower.endswith(s):
            return s
    return None


def stem(name):
    s = suffix_of(name)
    base = name[:-len(s)] if s else name
    return re.sub(r'^\d{2,}_', '', base).lower()


def parse_chord(text):
    tokens = [t.strip().upper() for t in text.split('+') if t.strip()]
    mods = [t for t in tokens if t in ('CTRL', 'ALT', 'SHIFT')]
    keys = [t for t in tokens if t not in ('CTRL', 'ALT', 'SHIFT')]
    if len(keys) != 1:
        return None, 'needs exactly one key'
    if keys[0] not in KEYS:
        return None, 'unknown key %r' % keys[0]
    if 'CTRL' not in mods and 'ALT' not in mods:
        return None, 'needs Ctrl or Alt'
    order = [m for m in ('CTRL', 'ALT', 'SHIFT') if m in mods]
    return '+'.join(order + keys), None


def check_context(path, rule):
    names = re.split(r'[&|!]', rule)
    for name in names:
        name = name.strip().lower()
        if name and name not in CONTEXT_NAMES:
            problem(path, 'unknown context condition %r' % name)
    if '(' in rule or ')' in rule:
        problem(path, 'context rules have no parentheses')


def check_text(path, key, value):
    if any(d in value for d in DASHES):
        problem(path, '%s contains an em or en dash' % key)
    letters = value.replace('\\n', ' ').strip()
    brand = letters.startswith(('pyNavis', 'Playground', 'pyRevit'))
    if letters and letters[0].isalpha() and letters[0].islower() and not brand:
        problem(path, '%s should start with a capital letter: %r' % (key, value[:40]))


def check_container(folder):
    yaml_path = os.path.join(folder, 'bundle.yaml')
    _, layout = read_yaml(yaml_path)
    children = [d for d in sorted(os.listdir(folder))
                if os.path.isdir(os.path.join(folder, d)) and suffix_of(d) in ITEMS + ('.panel',)]
    if layout is None:
        if children:
            problem(folder, 'container has no layout: list in bundle.yaml')
        return children
    stems = {stem(c): c for c in children}
    listed = set()
    for entry in layout:
        key = stem(entry)
        if key not in stems:
            problem(yaml_path, 'layout entry %r names no folder' % entry)
        listed.add(key)
    for key, child in sorted(stems.items()):
        if key not in listed:
            problem(folder, 'child %r missing from layout:' % child)
    return children


shortcut_owner = {}


def pynavis_chords():
    taken = {}
    for folder, dirs, files in os.walk(PYNAVIS_EXT):
        if 'bundle.yaml' in files:
            data, _ = read_yaml(os.path.join(folder, 'bundle.yaml'))
            if data.get('shortcut'):
                chord, _ = parse_chord(data['shortcut'])
                if chord:
                    taken[chord] = 'pyNavis ' + os.path.basename(folder)
    taken['CTRL+SHIFT+C'] = 'pyNavis Console (user binding)'
    return taken


def check_pushlike(folder, kind):
    script = os.path.join(folder, 'script.py')
    yaml_path = os.path.join(folder, 'bundle.yaml')
    data, _ = read_yaml(yaml_path)
    if kind != '.dockpane' and not os.path.exists(script):
        problem(folder, 'no script.py (pyNavis drops the button silently)')
    if not os.path.exists(yaml_path):
        problem(folder, 'no bundle.yaml')
    for key in data:
        if key not in PUSH_KEYS and key != 'layout':
            problem(yaml_path, 'key %r is read by nothing' % key)
    if not data.get('title'):
        problem(yaml_path, 'no title:')
    if not data.get('tooltip'):
        problem(yaml_path, 'no tooltip:')
    for key in ('title', 'tooltip', 'title_on', 'tooltip_on'):
        if data.get(key):
            check_text(yaml_path, key, data[key])
    if data.get('engine') and data['engine'].lower() not in ('ironpython', 'cpython'):
        problem(yaml_path, 'engine %r fails at click time' % data['engine'])
    if data.get('context'):
        check_context(yaml_path, data['context'])
    if data.get('shortcut'):
        chord, error = parse_chord(data['shortcut'])
        if error:
            problem(yaml_path, 'shortcut %r: %s' % (data['shortcut'], error))
        elif chord in shortcut_owner:
            problem(yaml_path, 'shortcut %s already used by %s' % (chord, shortcut_owner[chord]))
        else:
            shortcut_owner[chord] = os.path.basename(folder)
    icons = ['icon.png', 'icon.dark.png', 'icon.small.png', 'icon.small.dark.png']
    if kind == '.toggle':
        icons += ['icon.on.png', 'icon.on.dark.png', 'icon.off.png', 'icon.off.dark.png']
    if kind == '.dockpane':
        icons += ['icon.on.png', 'icon.on.dark.png']
        pane = os.path.join(folder, 'pane.xaml')
        if not os.path.exists(pane):
            problem(folder, 'dockpane without pane.xaml is dropped')
        else:
            try:
                root = xml.dom.minidom.parse(pane).documentElement
                if root.tagName == 'Window':
                    problem(pane, 'pane.xaml root must be a plain element, not Window')
            except Exception as error:
                problem(pane, 'XAML does not parse: %s' % error)
    for icon in icons:
        if not os.path.exists(os.path.join(folder, icon)):
            problem(folder, 'missing %s' % icon)
    if os.path.exists(script):
        with io.open(script, encoding='utf-8') as handle:
            text = handle.read()
        try:
            tree = ast.parse(text)
            if not ast.get_docstring(tree):
                problem(script, 'no module docstring (it is the tooltip fallback and house style)')
        except SyntaxError:
            pass


def walk_panel_items(folder):
    for child in check_container(folder):
        path = os.path.join(folder, child)
        kind = suffix_of(child)
        if kind in PUSHLIKE or kind == '.dockpane':
            check_pushlike(path, kind)
        elif kind == '.stack':
            kids = check_container(path)
            pushes = [k for k in kids if suffix_of(k) == '.pushbutton']
            if len(pushes) not in (2, 3):
                problem(path, 'a stack needs 2 or 3 pushbuttons, has %d' % len(pushes))
            if len(pushes) != len(kids):
                problem(path, 'a stack reads only *.pushbutton children')
            for k in pushes:
                check_pushlike(os.path.join(path, k), '.pushbutton')
        elif kind in ('.pulldown', '.splitbutton', '.splitpushbutton'):
            kids = check_container(path)
            data, _ = read_yaml(os.path.join(path, 'bundle.yaml'))
            if not data.get('title'):
                problem(path, 'no title:')
            if not data.get('tooltip'):
                problem(path, 'no tooltip: (a pulldown has no docstring to fall back to)')
            for key in ('title', 'tooltip'):
                if data.get(key):
                    check_text(path, key, data[key])
            for icon in ('icon.png', 'icon.dark.png', 'icon.small.png', 'icon.small.dark.png'):
                if not os.path.exists(os.path.join(path, icon)):
                    problem(path, 'missing %s' % icon)
            for k in kids:
                if suffix_of(k) == '.pushbutton':
                    check_pushlike(os.path.join(path, k), '.pushbutton')
                else:
                    problem(os.path.join(path, k), 'pulldowns read only *.pushbutton children')
        elif kind == '.slideout':
            walk_panel_items(path)


class PyRules(ast.NodeVisitor):
    def __init__(self, path, is_bundle_script):
        self.path = path
        self.is_bundle_script = is_bundle_script

    def visit_JoinedStr(self, node):
        problem(self.path, 'line %d: f-string (house style is %% formatting)' % node.lineno)

    def visit_If(self, node):
        test = node.test
        if (isinstance(test, ast.Compare) and isinstance(test.left, ast.Name)
                and test.left.id == '__name__'):
            problem(self.path, "line %d: `if __name__ == '__main__'` never runs in pyNavis" % node.lineno)
        self.generic_visit(node)

    def visit_Call(self, node):
        if self.is_bundle_script and isinstance(node.func, ast.Name) and node.func.id == 'print':
            problem(self.path, 'line %d: print() opens an empty output window; toast or output.*' % node.lineno)
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr in BANNED_PICKS:
            owner = func.value
            owner_name = owner.id if isinstance(owner, ast.Name) else getattr(owner, 'attr', None)
            if owner_name == 'pick':
                problem(self.path, 'line %d: pick.%s() is banned in Playground (its marker and the picked '
                                   'point disagree in the field); use namo.picking.point / points'
                        % (node.lineno, func.attr))
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        if node.module and node.module.startswith('pynavis') and any(a.name == '*' for a in node.names):
            problem(self.path, 'line %d: star import from pynavis' % node.lineno)
        if node.module == 'pynavis.pick':
            for alias in node.names:
                if alias.name in BANNED_PICKS:
                    problem(self.path, 'line %d: pynavis.pick.%s is banned in Playground; use '
                                       'namo.picking.point / points' % (node.lineno, alias.name))

    def visit_NamedExpr(self, node):
        problem(self.path, 'line %d: walrus is not IronPython 3.4' % node.lineno)

    def visit_AsyncFunctionDef(self, node):
        problem(self.path, 'line %d: async is not IronPython 3.4' % node.lineno)

    def visit_Constant(self, node):
        if isinstance(node.value, str) and any(d in node.value for d in DASHES):
            problem(self.path, 'line %d: em or en dash in a string' % node.lineno)

    def visit_AnnAssign(self, node):
        problem(self.path, 'line %d: annotations are not IronPython 3.4' % node.lineno)

    def visit_FunctionDef(self, node):
        if node.returns is not None or any(a.annotation is not None for a in node.args.args):
            problem(self.path, 'line %d: annotations are not IronPython 3.4' % node.lineno)
        self.generic_visit(node)


def check_python():
    count = 0
    for folder, dirs, files in os.walk(EXT):
        dirs[:] = [d for d in dirs if d != '__pycache__']
        for name in files:
            if not name.endswith('.py'):
                continue
            path = os.path.join(folder, name)
            count += 1
            with io.open(path, encoding='utf-8') as handle:
                text = handle.read()
            try:
                tree = ast.parse(text, path)
            except SyntaxError as error:
                problem(path, 'syntax error line %s: %s' % (error.lineno, error.msg))
                continue
            bundle_script = name in ('script.py', 'config.py') or folder.endswith('hooks') or name == 'startup.py'
            PyRules(path, bundle_script).visit(tree)
    return count


def check_hooks():
    hooks = os.path.join(EXT, 'hooks')
    if not os.path.isdir(hooks):
        return
    for name in os.listdir(hooks):
        if name.endswith('.py') and name[:-3] not in HOOK_EVENTS:
            problem(os.path.join(hooks, name), 'not one of the 14 pyNavis events')


def main():
    quiet = '--quiet' in sys.argv
    shortcut_owner.update(pynavis_chords())
    check_container(EXT) if False else None
    _, ext_layout = read_yaml(os.path.join(EXT, 'extension.yaml'))
    tabs = [d for d in sorted(os.listdir(EXT)) if d.lower().endswith('.tab')]
    if ext_layout is not None:
        for t in tabs:
            if stem(t) not in [stem(e) for e in ext_layout]:
                problem(EXT, 'tab %r missing from extension.yaml layout:' % t)
    buttons = 0
    for tab in tabs:
        tab_path = os.path.join(EXT, tab)
        for panel in check_container(tab_path):
            walk_panel_items(os.path.join(tab_path, panel))
    for folder, dirs, files in os.walk(EXT):
        if os.path.basename(folder).lower().endswith(PUSHLIKE + ('.dockpane',)):
            buttons += 1
    files = check_python()
    check_hooks()
    if not quiet:
        for n in notes:
            print(n)
    for p in problems:
        print('PROBLEM ' + p)
    print('check: %d bundle(s), %d python file(s), %d problem(s)' % (buttons, files, len(problems)))
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
