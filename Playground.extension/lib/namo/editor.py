# -*- coding: utf-8 -*-
"""Script Editor: a code editor beside Navisworks for the bundles you can change.

Left, the bundles of every loaded extension you can write to (MyTools, a development
copy of Playground...; never the shipped pyNavis extension, which updates replace) as a
keyboard-driven tree. Right, the editor: Consolas, line numbers, Tab = 4 spaces (indents
or dedents a selected block), Enter keeps the indent (one level more after a colon),
Ctrl+S saves (a .py file is compiled on save and a syntax error marks its line in the
gutter), Ctrl+F finds, Ctrl+G goes to a line, F5 saves and runs the bundle (deferred
through namo.ribbon, so it runs like a click; F5 on config.py runs the Shift+Click
action), Ctrl+Space or a '.' opens completions: Python keywords and builtins, names in
the file, members of imported pynavis modules (dir()) and of Navisworks API types by
reflection (doc, item, Application.ActiveDocument.Models ... resolved a step at a
time, cached for the session).

One window per session (modeless, keyboard interop before Show); it survives Reload.

Pure half (tested): indent_after, indent_block, normalize_newlines, find_index,
syntax_error, completion_context, identifiers, imports_of, rank_names, scan_tree,
flatten, bundle_of, writable_extensions.
"""
import io
import keyword
import os
import re

from namo import paths, ribbon, session, textmatch, ui

INDENT = '    '
NEWLINE = chr(10)
DEDENT_WORDS = ('return', 'pass', 'break', 'continue', 'raise')
FILE_TYPES = ('.py', '.yaml', '.xaml', '.json', '.md', '.txt', '.csv')
BUNDLE_SUFFIXES = ('.pushbutton', '.nobutton', '.toggle', '.smartbutton', '.dockpane')
CONTAINER_SUFFIXES = ('.tab', '.panel', '.stack', '.pulldown', '.splitbutton', '.splitpushbutton',
                      '.slideout')
KEY = 'playground-script-editor'
MAX_COMPLETIONS = 60
TYPE_HINTS = {
    'doc': 'Document', 'document': 'Document', 'd': 'Document', 'item': 'ModelItem',
    'model_item': 'ModelItem', 'items': 'ModelItemCollection', 'collection': 'ModelItemCollection',
    'selection': 'ModelItemCollection', 'sel': 'ModelItemCollection', 'model': 'Model',
    'vp': 'Viewpoint', 'viewpoint': 'Viewpoint', 'saved': 'SavedViewpoint', 'view': 'View',
    'Application': 'Application', 'search': 'Search', 'prop': 'DataProperty',
    'category': 'PropertyCategory', 'bbox': 'BoundingBox3D', 'box': 'BoundingBox3D',
    'point': 'Point3D', 'color': 'Color', 'transaction': 'Transaction',
}

# ---- pure: editing ----------------------------------------------------------------------


def indent_after(line):
    """The indent for the line after `line` (the text before the caret on Enter)."""
    stripped = line.rstrip()
    indent = line[:len(line) - len(line.lstrip(' \t'))].replace('\t', INDENT)
    code = stripped.split('#', 1)[0].rstrip() if '#' in stripped and not ('"' in stripped or "'" in stripped) \
        else stripped
    if code.endswith(':'):
        return indent + INDENT
    first = code.strip().split(' ', 1)[0] if code.strip() else ''
    if first in DEDENT_WORDS and len(indent) >= len(INDENT):
        return indent[:-len(INDENT)]
    return indent


def block_span(text, start, length):
    """(first index, end index) of the whole lines a selection touches (a selection
    ending right after a line break does not take in the next line)."""
    line_start = text.rfind('\n', 0, start) + 1
    end = start + length
    if length and text[end - 1:end] == '\n':
        end -= 1
    line_end = text.find('\n', end)
    if line_end < 0:
        line_end = len(text)
    return line_start, line_end


def indent_block(text, start, length, dedent=False):
    """(new text, new start, new length) after indenting (or dedenting) every line the
    selection touches by four spaces. Lines are split on '\\n' ('\\r\\n' kept)."""
    line_start, line_end = block_span(text, start, length)
    block = text[line_start:line_end]
    lines = block.split('\n')
    out = []
    for line in lines:
        if dedent:
            removed = 0
            while removed < len(INDENT) and line[removed:removed + 1] == ' ':
                removed += 1
            if removed == 0 and line.startswith('\t'):
                removed = 1
            out.append(line[removed:])
        else:
            out.append(line if not line.strip() else INDENT + line)
    new_block = '\n'.join(out)
    return text[:line_start] + new_block + text[line_end:], line_start, len(new_block)


def normalize_newlines(text, crlf):
    """Every line ending as '\\r\\n' (crlf) or '\\n'."""
    flat = text.replace('\r\n', '\n').replace('\r', '\n')
    return flat.replace('\n', '\r\n') if crlf else flat


def find_index(text, needle, start, backwards=False, match_case=False):
    """Index of the next (or previous) match from start, wrapping around; -1 if none."""
    if not needle:
        return -1
    hay = text if match_case else text.lower()
    pin = needle if match_case else needle.lower()
    if backwards:
        found = hay.rfind(pin, 0, max(0, start))
        return found if found >= 0 else hay.rfind(pin)
    found = hay.find(pin, start)
    return found if found >= 0 else hay.find(pin)


def syntax_error(source, filename='script.py'):
    """None when source compiles, else (line, column, message)."""
    try:
        compile(normalize_newlines(source, False), filename, 'exec')
    except SyntaxError as error:
        return (error.lineno or 1, error.offset or 1, error.msg or 'invalid syntax')
    except Exception as error:
        return (1, 1, str(error))
    return None


# ---- pure: completion --------------------------------------------------------------------

_RUN = re.compile(r'[\w\.]*$')
_NAME = re.compile(r'[A-Za-z_][A-Za-z0-9_]*')


def completion_context(before):
    """(base, prefix) for the text before the caret: 'doc.Mod' -> ('doc', 'Mod'),
    'pri' -> ('', 'pri'); None inside a number, after '..' or after a call ('f().')."""
    chain = _RUN.search(before or '').group(0)
    if chain[:1].isdigit() or chain[:1] == '.' or '..' in chain:
        return None
    if '.' in chain:
        base, prefix = chain.rsplit('.', 1)
        return base, prefix
    return '', chain


def identifiers(source):
    """Distinct names (two characters or more) used in the source, sorted."""
    return sorted(set(n for n in _NAME.findall(source or '') if len(n) > 1))


def imports_of(source):
    """{alias: dotted module or 'module.attribute'} from the file's import lines."""
    out = {}
    for line in (source or '').splitlines():
        line = line.strip()
        match = re.match(r'^import\s+(.+)$', line)
        if match:
            for part in match.group(1).split(','):
                bits = part.strip().split()
                if not bits:
                    continue
                if len(bits) == 3 and bits[1] == 'as':
                    out[bits[2]] = bits[0]
                else:
                    out[bits[0].split('.')[0]] = bits[0].split('.')[0]
            continue
        match = re.match(r'^from\s+([\w\.]+)\s+import\s+\(?(.+?)\)?$', line)
        if match:
            module = match.group(1)
            for part in match.group(2).split(','):
                bits = part.strip().split()
                if not bits or bits[0] == '*':
                    continue
                alias = bits[2] if len(bits) == 3 and bits[1] == 'as' else bits[0]
                out[alias] = '%s.%s' % (module, bits[0])
    return out


def base_names(source):
    """Names offered with no base: keywords, builtins, the file's names and imports."""
    try:
        import builtins
        builtin_names = [n for n in dir(builtins) if not n.startswith('_')]
    except Exception:
        builtin_names = []
    names = set(keyword.kwlist) | set(builtin_names) | set(identifiers(source)) | set(imports_of(source))
    names |= set(['__title__', '__commandpath__', '__file__', '__runner__'])
    return sorted(names)


def rank_names(prefix, names, limit=MAX_COMPLETIONS):
    """Names for a prefix: exact-case starts first, then any-case starts, then fuzzy
    matches (textmatch), each group in natural order; the prefix itself left out."""
    names = sorted(set(n for n in names if n))
    if not prefix:
        visible = [n for n in names if not n.startswith('_')]
        return visible[:limit]
    low = prefix.lower()
    exact = [n for n in names if n.startswith(prefix) and n != prefix]
    loose = [n for n in names if n.lower().startswith(low) and n not in exact and n != prefix]
    fuzzy = []
    if len(prefix) >= 3:
        taken = set(exact) | set(loose)
        rest = [n for n in names if n not in taken and n != prefix]
        fuzzy = [n for _s, n in textmatch.rank(prefix, rest, limit=limit)]
    return (exact + loose + fuzzy)[:limit]


# ---- pure: the bundle tree ------------------------------------------------------------------


def _natural(name):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r'(\d+)', name)]


def scan_tree(ext_folder, name=None):
    """A node tree for one extension folder: {'label', 'path', 'kind' ('ext' | 'folder' |
    'bundle' | 'file'), 'children'}. Containers and bundles by name, files that can be
    edited (FILE_TYPES), plus lib\\ and hooks\\ and startup.py."""
    def files_in(folder):
        out = []
        for entry in sorted(os.listdir(folder), key=_natural):
            full = os.path.join(folder, entry)
            if os.path.isfile(full) and os.path.splitext(entry)[1].lower() in FILE_TYPES:
                out.append({'label': entry, 'path': full, 'kind': 'file', 'children': []})
        return out

    def walk(folder, depth):
        nodes = []
        support = []
        for entry in sorted(os.listdir(folder), key=_natural):
            full = os.path.join(folder, entry)
            if not os.path.isdir(full) or entry.startswith('.') or entry == '__pycache__':
                continue
            lower = entry.lower()
            if lower.endswith(BUNDLE_SUFFIXES):
                nodes.append({'label': ribbon.title_from_folder(entry), 'path': full, 'kind': 'bundle',
                              'suffix': lower.rsplit('.', 1)[-1], 'children': files_in(full)})
            elif lower.endswith(CONTAINER_SUFFIXES):
                nodes.append({'label': ribbon.title_from_folder(entry), 'path': full, 'kind': 'folder',
                              'suffix': lower.rsplit('.', 1)[-1], 'children': walk(full, depth + 1)})
            elif depth == 0 and lower in ('lib', 'hooks'):
                support.append({'label': entry, 'path': full, 'kind': 'folder', 'suffix': lower,
                                'children': lib_tree(full)})
        nodes.extend(support)
        if depth == 0:
            for item in files_in(folder):
                if item['label'].lower() in ('startup.py', 'extension.yaml'):
                    nodes.append(item)
        return nodes

    def lib_tree(folder):
        nodes = []
        for entry in sorted(os.listdir(folder), key=_natural):
            full = os.path.join(folder, entry)
            if os.path.isdir(full) and not entry.startswith('.') and entry != '__pycache__':
                nodes.append({'label': entry, 'path': full, 'kind': 'folder', 'suffix': 'package',
                              'children': lib_tree(full)})
        return nodes + files_in(folder)

    label = name or ribbon.strip_suffix(os.path.basename(ext_folder))
    return {'label': label, 'path': ext_folder, 'kind': 'ext', 'children': walk(ext_folder, 0)}


def flatten(nodes, expanded, depth=0):
    """[(depth, node)] for the visible rows: children of expanded paths only."""
    rows = []
    for node in nodes:
        rows.append((depth, node))
        if node['children'] and node['path'].lower() in expanded:
            rows.extend(flatten(node['children'], expanded, depth + 1))
    return rows


def filter_tree(nodes, query):
    """The nodes whose label (or a descendant's) contains every word; their ancestors kept."""
    words = (query or '').lower().split()
    if not words:
        return nodes
    out = []
    for node in nodes:
        kids = filter_tree(node['children'], query)
        text = node['label'].lower()
        if all(w in text for w in words) or kids:
            copy = dict(node)
            copy['children'] = kids if kids else ([] if node['kind'] == 'file' else node['children'])
            out.append(copy)
    return out


def all_folder_paths(nodes):
    out = set()
    for node in nodes:
        if node['children']:
            out.add(node['path'].lower())
            out |= all_folder_paths(node['children'])
    return out


def bundle_of(path):
    """(extension folder, bundle folder, is_config) for a file inside a bundle, or None."""
    folder = os.path.dirname(os.path.abspath(path))
    bundle = None
    current = folder
    while True:
        name = os.path.basename(current).lower()
        if bundle is None and name.endswith(BUNDLE_SUFFIXES):
            bundle = current
        if name.endswith('.extension'):
            if bundle is None:
                return None
            return current, bundle, os.path.basename(path).lower() == 'config.py'
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


def writable_extensions(items):
    """The extensions the editor offers: [{'name', 'folder', 'writable'}] minus the
    shipped pyNavis extension and folders that cannot be written."""
    out = []
    seen = set()
    for item in items:
        if (item.get('name') or '').lower() == 'pynavis' or not item.get('writable'):
            continue
        key = os.path.normcase(item['folder'])
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def caret_text(line, column):
    return 'Line %d, column %d' % (line, column)


def line_of(text, index):
    """1-based line number of a character index (works without a laid-out TextBox)."""
    return text.count(NEWLINE, 0, max(0, index)) + 1


def line_start(text, line):
    """Index of the first character of a 1-based line (clamped to the text)."""
    index = 0
    for _ in range(max(0, line - 1)):
        found = text.find(NEWLINE, index)
        if found < 0:
            return index
        index = found + 1
    return index


# ==================================================================================
# API half
# ==================================================================================


def _probe(folder):
    try:
        probe = os.path.join(folder, '.playground-editor-probe')
        with open(probe, 'wb') as handle:
            handle.write(b'x')
        os.remove(probe)
        return True
    except Exception:
        return False


def editable():
    """[{'name', 'folder', 'writable'}] for the loaded extensions."""
    items = []
    for ext in ribbon.extensions():
        folder = str(ext.Directory)
        name = str(ext.Name)
        # The shipped pyNavis extension is never offered, so it is never probed either
        # (the probe creates and removes a file in the folder).
        items.append({'name': name, 'folder': folder,
                      'writable': name.lower() != 'pynavis' and _probe(folder)})
    return writable_extensions(items)


# ---- member lookup by reflection ----------------------------------------------------------


def _cache():
    holder = session.holder('editor_cache')
    members = getattr(holder, 'members', None)
    if members is None:
        members = {}
        holder.members = members
    return members


def _api_assembly():
    import clr
    from pynavis._api import Api
    return clr.GetClrType(Api.Document).Assembly


def _api_type(name):
    try:
        return _api_assembly().GetType('Autodesk.Navisworks.Api.' + name)
    except Exception:
        return None


def _type_members(clr_type):
    """{name: member type or None} for a .NET type's public members (cached)."""
    key = str(clr_type.FullName)
    cache = _cache()
    if key in cache:
        return cache[key]
    from System.Reflection import BindingFlags, MemberTypes
    flags = BindingFlags.Public | BindingFlags.Instance | BindingFlags.Static | BindingFlags.FlattenHierarchy
    found = {}
    for member in clr_type.GetMembers(flags):
        name = str(member.Name)
        if name.startswith(('get_', 'set_', 'add_', 'remove_', 'op_')) or name == '.ctor':
            continue
        kind = member.MemberType
        result = None
        if kind == MemberTypes.Property:
            result = member.PropertyType
        elif kind == MemberTypes.Field:
            result = member.FieldType
        elif kind == MemberTypes.Method:
            result = member.ReturnType
        elif kind != MemberTypes.Event:
            continue
        if name not in found or found[name] is None:
            found[name] = result
    cache[key] = found
    return found


def _namespace_types():
    cache = _cache()
    if '__namespace__' in cache:
        return cache['__namespace__']
    names = {}
    for clr_type in _api_assembly().GetExportedTypes():
        if str(clr_type.Namespace) == 'Autodesk.Navisworks.Api' and not clr_type.IsNested:
            names[str(clr_type.Name)] = clr_type
    cache['__namespace__'] = names
    return names


def _module_members(dotted):
    import sys
    module = sys.modules.get(dotted)
    if module is None and dotted.split('.')[0] in ('pynavis',):
        try:
            module = __import__(dotted, fromlist=['_'])
        except Exception:
            module = None
    if module is None:
        return None
    return sorted(n for n in dir(module) if not n.startswith('_'))


def members_of(base, source):
    """Names after 'base.' (None when unknown): imported modules, the Api namespace,
    Navisworks types by name or by a usual variable name, then a chain of members."""
    parts = base.split('.')
    imports = imports_of(source)
    head = parts[0]
    try:
        if len(parts) == 1 and head in imports:
            names = _module_members(imports[head])
            if names is not None:
                return names
        if head == 'Api' and len(parts) <= 2:
            types = _namespace_types()
            if len(parts) == 1:
                return sorted(types)
            current = types.get(parts[1])
            return sorted(_type_members(current)) if current is not None else None
        current = None
        types = _namespace_types()
        if head in types:
            current = types[head]
        elif head in TYPE_HINTS:
            current = _api_type(TYPE_HINTS[head])
        if current is None:
            return None
        for part in parts[1:]:
            current = _type_members(current).get(part)
            if current is None:
                return None
        return sorted(_type_members(current))
    except Exception as error:
        session.log('debug', 'editor: no members for %s: %s' % (base, error))
        return None


def complete(source, before):
    """Completion names for the caret ([] when there is nothing to offer)."""
    context = completion_context(before)
    if context is None:
        return []
    base, prefix = context
    if not base:
        if not prefix:
            return []
        return rank_names(prefix, base_names(source))
    names = members_of(base, source)
    if names is None:
        names = sorted(set(re.findall(r'\b%s\.([A-Za-z_]\w*)' % re.escape(base), source or '')))
    return rank_names(prefix, names)


# ---- the window ---------------------------------------------------------------------------

_ROW_STYLE = r'''
<Style xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
       xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml" TargetType="ListBoxItem">
  <Setter Property="FocusVisualStyle" Value="{x:Null}"/>
  <Setter Property="Template">
    <Setter.Value>
      <ControlTemplate TargetType="ListBoxItem">
        <Grid Background="Transparent" MinHeight="26">
          <Border x:Name="Wash" Background="Transparent"/>
          <Border x:Name="Rail" Width="3" HorizontalAlignment="Left" Background="Transparent"/>
          <ContentPresenter Margin="8,3,8,3" VerticalAlignment="Center"/>
        </Grid>
        <ControlTemplate.Triggers>
          <Trigger Property="IsMouseOver" Value="True">
            <Setter TargetName="Wash" Property="Background" Value="%(surface)s"/>
          </Trigger>
          <Trigger Property="IsSelected" Value="True">
            <Setter TargetName="Wash" Property="Background" Value="%(selection)s"/>
            <Setter TargetName="Rail" Property="Background" Value="%(accent)s"/>
          </Trigger>
        </ControlTemplate.Triggers>
      </ControlTemplate>
    </Setter.Value>
  </Setter>
</Style>
'''

def _read_file(path):
    with io.open(path, 'rb') as handle:
        data = handle.read()
    text = data.decode('utf-8-sig') if data[:3] == b'\xef\xbb\xbf' else data.decode('utf-8', 'replace')
    return text, b'\r\n' in data


def build_window(extensions, logger=None):
    """The Script Editor, unshown; window.Tag holds its parts (tests drive them)."""
    ui.load_wpf()
    from System.Windows import (GridLength, GridUnitType, HorizontalAlignment, TextAlignment,
                                TextWrapping, VerticalAlignment, Visibility)
    from System.Windows.Controls import (Border, Canvas, ColumnDefinition, Dock, DockPanel, Grid,
                                         GridSplitter, ListBox, Orientation, ScrollBarVisibility,
                                         ScrollViewer, StackPanel, TextBlock, TextBox)
    from System.Windows.Controls.Primitives import Popup, PlacementMode
    from System.Windows.Input import Key, Keyboard, ModifierKeys
    from System.Windows.Markup import XamlReader
    from System.Windows.Media import FontFamily
    logger = logger or ui.pinned_logger()
    colors = ui.palette()
    mono = FontFamily('Consolas')
    NO_MODS = getattr(ModifierKeys, 'None')
    win = ui.window('Script Editor', width=1180, height=760, min_width=760, min_height=420)
    parts = ui.Bag(path=None, crlf=True, saved_text='', error_line=None, expanded=set(), rows=[],
                   extensions=list(extensions), trees=[], filter='', logger=logger)
    win.Tag = parts

    # -- tree --------------------------------------------------------------------------
    tree = ListBox()
    tree.BorderThickness = ui.thickness(0)
    tree.Background = ui.brush(colors['paper'])
    tree.ItemContainerStyle = XamlReader.Parse(_ROW_STYLE % colors)
    ScrollViewer.SetHorizontalScrollBarVisibility(tree, ScrollBarVisibility.Disabled)

    def load_trees():
        trees = []
        for item in parts.extensions:
            try:
                trees.append(scan_tree(item['folder'], item['name']))
            except Exception as error:
                ui.log_error('editor: could not list %s: %s' % (item['folder'], error), logger)
        parts.trees = trees
        if not parts.expanded:
            parts.expanded = set(t['path'].lower() for t in trees)

    def row_visual(depth, node):
        panel = StackPanel()
        panel.Orientation = Orientation.Horizontal
        arrow = ui.text('', size=11, muted=True, wrap=False)
        arrow.Width = 14.0
        if node['children']:
            arrow.Text = u'▾' if node['path'].lower() in parts.expanded else u'▸'
        arrow.Margin = ui.thickness(depth * 14, 0, 2, 0)
        panel.Children.Add(arrow)
        label = ui.text(node['label'], size=13, wrap=False, bold=node['kind'] in ('ext', 'bundle'))
        panel.Children.Add(label)
        if node['kind'] in ('folder', 'bundle') and node.get('suffix'):
            suffix = ui.text(node['suffix'], size=11, muted=True, wrap=False)
            suffix.Margin = ui.thickness(8, 0, 0, 0)
            suffix.VerticalAlignment = VerticalAlignment.Center
            panel.Children.Add(suffix)
        return panel

    def refresh_tree(select_path=None):
        nodes = filter_tree(parts.trees, parts.filter)
        expanded = all_folder_paths(nodes) if parts.filter else parts.expanded
        parts.rows = flatten(nodes, expanded)
        tree.Items.Clear()
        chosen = -1
        for index, (depth, node) in enumerate(parts.rows):
            tree.Items.Add(row_visual(depth, node))
            if select_path and node['path'].lower() == select_path.lower():
                chosen = index
        if chosen >= 0:
            tree.SelectedIndex = chosen
            tree.ScrollIntoView(tree.Items[chosen])

    def selected_node():
        index = tree.SelectedIndex
        if 0 <= index < len(parts.rows):
            return parts.rows[index][1]
        return None

    def activate(node, toggle_only=False):
        if node is None:
            return
        if node['kind'] == 'file':
            if not toggle_only:
                open_file(node['path'])
            return
        key = node['path'].lower()
        if key in parts.expanded:
            parts.expanded.discard(key)
        else:
            parts.expanded.add(key)
            if node['kind'] == 'bundle' and not toggle_only:
                script = [c for c in node['children'] if c['label'].lower() == 'script.py']
                if script:
                    open_file(script[0]['path'])
        refresh_tree(node['path'])

    def tree_keys(sender, args):
        node = selected_node()
        if node is None:
            return
        key = node['path'].lower()
        if args.Key in (Key.Enter, Key.Return):
            activate(node)
        elif args.Key == Key.Right and node['children'] and key not in parts.expanded:
            activate(node, True)
        elif args.Key == Key.Left and node['children'] and key in parts.expanded:
            activate(node, True)
        else:
            return
        args.Handled = True
    tree.PreviewKeyDown += ui.safe(tree_keys, 'editor tree keys', logger)
    tree.MouseDoubleClick += ui.safe(lambda s, e: activate(selected_node()), 'editor tree open', logger)

    def tree_filter(text):
        parts.filter = text or ''
        refresh_tree()
    tree_search, tree_box = ui.search_box('Filter bundles and files', tree_filter, delay_ms=120)

    # -- editor ------------------------------------------------------------------------
    box = TextBox()
    box.FontFamily = mono
    box.FontSize = 13.0
    box.AcceptsReturn = True
    box.AcceptsTab = False
    box.TextWrapping = TextWrapping.NoWrap
    box.HorizontalScrollBarVisibility = ScrollBarVisibility.Auto
    box.VerticalScrollBarVisibility = ScrollBarVisibility.Auto
    box.BorderThickness = ui.thickness(0)
    box.Background = ui.brush(colors['paper'])
    box.Foreground = ui.brush(colors['ink'])
    box.CaretBrush = ui.brush(colors['ink'])
    box.Padding = ui.thickness(6, 4, 6, 4)
    box.IsUndoEnabled = True
    box.UndoLimit = 500
    box.IsEnabled = False

    gutter = Canvas()
    gutter.Width = 48.0
    gutter.ClipToBounds = True
    gutter.Background = ui.brush(colors['surface'])

    def redraw_gutter(*args):
        gutter.Children.Clear()
        try:
            first = box.GetFirstVisibleLineIndex()
            last = box.GetLastVisibleLineIndex()
        except Exception:
            return
        if first < 0 or last < 0:
            return
        for index in range(first, last + 1):
            try:
                rect = box.GetRectFromCharacterIndex(box.GetCharacterIndexFromLineIndex(index))
            except Exception:
                continue
            number = TextBlock()
            number.Text = str(index + 1)
            number.FontFamily = mono
            number.FontSize = 12.0
            number.Width = 40.0
            number.TextAlignment = TextAlignment.Right
            is_error = parts.error_line == index + 1
            number.Foreground = ui.brush(colors['error'] if is_error else colors['muted'])
            if is_error:
                from System.Windows import FontWeights
                number.FontWeight = FontWeights.Bold
            Canvas.SetTop(number, rect.Top + 1)
            gutter.Children.Add(number)

    from System.Windows.Controls import ScrollChangedEventHandler
    box.AddHandler(ScrollViewer.ScrollChangedEvent,
                   ScrollChangedEventHandler(ui.safe(redraw_gutter, 'editor gutter', logger)))
    box.SizeChanged += ui.safe(redraw_gutter, 'editor gutter size', logger)

    path_label = ui.text('Pick a file on the left', size=12, muted=True, wrap=False)
    status = ui.text('', size=12, muted=True, wrap=False)
    caret = ui.text('', size=12, muted=True, wrap=False)

    def set_status(text, error=False):
        status.Text = text or ''
        status.Foreground = ui.brush(colors['error'] if error else colors['muted'])

    def dirty():
        return parts.path is not None and normalize_newlines(box.Text, parts.crlf) != parts.saved_text

    def update_title():
        name = os.path.basename(parts.path) if parts.path else ''
        win.Title = 'Script Editor' + ((' - %s%s' % (name, ' *' if dirty() else '')) if name else '')

    def caret_moved(*args):
        if parts.path is None:
            caret.Text = ''
            return
        index = box.CaretIndex
        line = line_of(box.Text, index)
        caret.Text = caret_text(line, index - line_start(box.Text, line) + 1)
    box.SelectionChanged += ui.safe(caret_moved, 'editor caret', logger)

    def text_changed(*args):
        update_title()
        redraw_gutter()
        if popup.IsOpen:
            show_completions(False)
    box.TextChanged += ui.safe(text_changed, 'editor text', logger)

    def ask_save():
        """True when it is fine to leave the current file (saved, discarded or clean)."""
        if not dirty():
            return True
        from pynavis import forms
        answer = forms.ask_options('Save the changes to %s?' % os.path.basename(parts.path),
                                   ['Save', 'Do not save', 'Cancel'], title='Script Editor')
        if answer == 'Save':
            return save()
        return answer == 'Do not save'

    def open_file(path, line=None):
        if parts.path and os.path.normcase(path) == os.path.normcase(parts.path):
            if line:
                go_to_line(line)
            return True
        if not ask_save():
            return False
        try:
            text, crlf = _read_file(path)
        except (IOError, OSError) as error:
            set_status('Could not open %s: %s' % (os.path.basename(path), error), True)
            return False
        parts.path = path
        parts.crlf = crlf
        parts.saved_text = normalize_newlines(text, crlf)
        parts.error_line = None
        box.IsEnabled = True
        box.Text = text
        box.CaretIndex = 0
        box.ScrollToHome()
        path_label.Text = path
        set_status('Opened %s' % os.path.basename(path))
        update_title()
        box.Focus()
        if line:
            go_to_line(line)
        ui.run_later(redraw_gutter, 50)
        return True

    def save():
        if parts.path is None:
            return False
        text = normalize_newlines(box.Text, parts.crlf)
        try:
            paths.atomic_write_text(parts.path, text)
        except (IOError, OSError) as error:
            set_status('Could not save: %s' % error, True)
            return False
        parts.saved_text = text
        parts.error_line = None
        name = os.path.basename(parts.path)
        if parts.path.lower().endswith('.py'):
            problem = syntax_error(text, name)
            if problem:
                parts.error_line = problem[0]
                set_status('Saved %s, but line %d has a syntax error: %s' % (name, problem[0], problem[2]), True)
                redraw_gutter()
                update_title()
                return True
        set_status('Saved %s' % name)
        redraw_gutter()
        update_title()
        return True

    def run():
        if parts.path is None:
            return
        found = bundle_of(parts.path)
        if found is None:
            set_status('F5 runs a bundle: open its script.py or config.py.', True)
            return
        if not save():
            return
        if parts.error_line:
            return
        ext_dir, bundle_dir, is_config = found
        key = ribbon.bundle_key(ext_dir, bundle_dir)
        ext_name = ribbon.strip_suffix(os.path.basename(ext_dir))
        for item in parts.extensions:
            if os.path.normcase(item['folder']) == os.path.normcase(ext_dir):
                ext_name = item['name']
        model = ribbon.find_button(key, ext_name)
        if model is None:
            set_status('This bundle is not loaded yet: click Reload pyNavis, then F5.', True)
            return
        if is_config and not model.ConfigScriptPath:
            set_status('This config.py is new: click Reload pyNavis, then F5.', True)
            return
        ribbon.run_bundle(model, ext_name, config=is_config)
        set_status('Running %s%s' % (ribbon.flatten_title(str(model.Title)), ' (Shift+Click action)' if is_config else ''))

    def set_extensions(items):
        """Swaps in a fresh list of editable extensions (after a Reload, or when the
        button is clicked again: Button Maker may have made MyTools since)."""
        parts.extensions = list(items)
        known = set(os.path.normcase(t['path']) for t in parts.trees)
        load_trees()
        for found in parts.trees:
            if os.path.normcase(found['path']) not in known:
                parts.expanded.add(found['path'].lower())
        refresh_tree(parts.path)
        if not parts.extensions:
            set_status('No extension you can edit is loaded. Make one with Button Maker first.', True)

    def reload_pynavis():
        if not ask_save():
            return
        busy = ribbon.gate_title() if ribbon.gate_held() else None
        if busy is not None:
            set_status('%s is still running. Reload when it has finished.' % (busy or 'A tool'), True)
            return
        try:
            from pynavis import script
            script.reload_pynavis()
        except Exception as error:
            set_status('Reload failed: %s' % error, True)
            return
        try:
            set_extensions(editable())
        except Exception as error:
            ui.log_error('editor: could not list the extensions after a reload: %s' % error, logger)
        set_status('Reloaded pyNavis')

    # -- find and go to line ------------------------------------------------------------
    find_shell, find_box = ui.text_box('', placeholder='Find')
    find_shell.Width = 260.0
    case_check = ui.check('Match case')
    goto_shell, goto_box = ui.text_box('', placeholder='Line number')
    goto_shell.Width = 140.0

    def find(backwards=False):
        needle = find_box.Text
        if not needle:
            return
        start = box.SelectionStart if backwards else box.SelectionStart + max(box.SelectionLength, 0)
        index = find_index(box.Text, needle, start, backwards, bool(case_check.IsChecked))
        if index < 0:
            set_status('%s was not found' % needle, True)
            return
        box.Select(index, len(needle))
        line = box.GetLineIndexFromCharacterIndex(index)
        box.ScrollToLine(max(0, line))
        set_status('')

    def go_to_line(number):
        try:
            line = int(number)
        except (TypeError, ValueError):
            set_status('Type a line number.', True)
            return
        line = max(1, min(box.Text.count(NEWLINE) + 1, line))
        box.CaretIndex = line_start(box.Text, line)
        try:
            box.ScrollToLine(line - 1)
        except Exception:
            pass
        box.Focus()

    find_bar = StackPanel()
    find_bar.Orientation = Orientation.Horizontal
    find_bar.Margin = ui.thickness(0, 8, 0, 0)
    next_button = ui.button('Next', lambda: find(False), 'quiet', logger)
    previous_button = ui.button('Previous', lambda: find(True), 'quiet', logger)
    for index, control in enumerate((find_shell, next_button, previous_button, case_check)):
        control.Margin = ui.thickness(0 if index == 0 else 8, 0, 0, 0)
        control.VerticalAlignment = VerticalAlignment.Center
        find_bar.Children.Add(control)
    find_bar.Visibility = Visibility.Collapsed
    goto_bar = StackPanel()
    goto_bar.Orientation = Orientation.Horizontal
    goto_bar.Margin = ui.thickness(0, 8, 0, 0)
    goto_bar.Children.Add(goto_shell)
    goto_hint = ui.hint('Enter goes there, Esc closes')
    goto_hint.Margin = ui.thickness(8, 0, 0, 0)
    goto_hint.VerticalAlignment = VerticalAlignment.Center
    goto_bar.Children.Add(goto_hint)
    goto_bar.Visibility = Visibility.Collapsed

    def show_bar(bar, field):
        for other in (find_bar, goto_bar):
            other.Visibility = Visibility.Visible if other is bar else Visibility.Collapsed
        if box.SelectedText and bar is find_bar and '\n' not in box.SelectedText:
            find_box.Text = box.SelectedText
        field.Focus()
        field.SelectAll()

    def hide_bars():
        find_bar.Visibility = Visibility.Collapsed
        goto_bar.Visibility = Visibility.Collapsed
        box.Focus()

    def find_keys(sender, args):
        if args.Key in (Key.Enter, Key.Return):
            find(Keyboard.Modifiers == ModifierKeys.Shift)
            args.Handled = True
        elif args.Key == Key.Escape:
            hide_bars()
            args.Handled = True
    find_box.PreviewKeyDown += ui.safe(find_keys, 'editor find keys', logger)

    def goto_keys(sender, args):
        if args.Key in (Key.Enter, Key.Return):
            go_to_line(goto_box.Text)
            goto_bar.Visibility = Visibility.Collapsed
            args.Handled = True
        elif args.Key == Key.Escape:
            hide_bars()
            args.Handled = True
    goto_box.PreviewKeyDown += ui.safe(goto_keys, 'editor goto keys', logger)

    # -- completion ----------------------------------------------------------------------
    popup = Popup()
    popup.PlacementTarget = box
    popup.Placement = PlacementMode.Relative
    popup.StaysOpen = False
    completions = ListBox()
    completions.Focusable = False
    completions.MaxHeight = 240.0
    completions.MinWidth = 220.0
    completions.FontFamily = mono
    completions.FontSize = 12.0
    completions.Background = ui.brush(colors['paper'])
    completions.Foreground = ui.brush(colors['ink'])
    completions.BorderThickness = ui.thickness(0)
    completions.ItemContainerStyle = XamlReader.Parse(_ROW_STYLE % colors)
    frame = Border()
    frame.BorderBrush = ui.brush(colors['line_strong'])
    frame.BorderThickness = ui.thickness(1)
    frame.Background = ui.brush(colors['paper'])
    frame.Child = completions
    popup.Child = frame
    parts.completion_names = []

    def text_before_caret():
        index = box.CaretIndex
        return box.Text[line_start(box.Text, line_of(box.Text, index)):index]

    def show_completions(forced=True):
        if parts.path is None or not parts.path.lower().endswith('.py'):
            popup.IsOpen = False
            return
        before = text_before_caret()
        context = completion_context(before)
        if context is None or (not forced and not context[0] and not context[1]):
            popup.IsOpen = False
            return
        names = complete(box.Text, before)
        parts.completion_names = names
        completions.Items.Clear()
        for name in names:
            completions.Items.Add(name)
        if not names:
            popup.IsOpen = False
            return
        completions.SelectedIndex = 0
        rect = box.GetRectFromCharacterIndex(box.CaretIndex)
        popup.HorizontalOffset = rect.Left
        popup.VerticalOffset = rect.Bottom + 2
        popup.IsOpen = True

    def accept_completion():
        index = completions.SelectedIndex
        if not (0 <= index < len(parts.completion_names)):
            popup.IsOpen = False
            return
        name = parts.completion_names[index]
        context = completion_context(text_before_caret()) or ('', '')
        prefix = context[1]
        caret_index = box.CaretIndex
        box.Select(caret_index - len(prefix), len(prefix))
        box.SelectedText = name
        box.CaretIndex = caret_index - len(prefix) + len(name)
        popup.IsOpen = False

    def text_input(sender, args):
        if args.Text == '.':
            ui.run_later(lambda: show_completions(True), 0)
    box.PreviewTextInput += ui.safe(text_input, 'editor text input', logger)

    # -- editing keys --------------------------------------------------------------------------
    def newline():
        return '\r\n' if parts.crlf else '\n'

    def box_keys(sender, args):
        mods = Keyboard.Modifiers
        key = args.Key
        if popup.IsOpen:
            if key == Key.Down:
                completions.SelectedIndex = min(completions.Items.Count - 1, completions.SelectedIndex + 1)
                completions.ScrollIntoView(completions.SelectedItem)
            elif key == Key.Up:
                completions.SelectedIndex = max(0, completions.SelectedIndex - 1)
                completions.ScrollIntoView(completions.SelectedItem)
            elif key in (Key.Enter, Key.Return, Key.Tab):
                accept_completion()
            elif key == Key.Escape:
                popup.IsOpen = False
            else:
                return
            args.Handled = True
            return
        if key == Key.Space and mods == ModifierKeys.Control:
            show_completions(True)
        elif key == Key.Tab and mods in (NO_MODS, ModifierKeys.Shift):
            dedent = mods == ModifierKeys.Shift
            selected = box.SelectedText
            if dedent or '\n' in selected:
                text, start, length = indent_block(box.Text, box.SelectionStart, box.SelectionLength, dedent)
                line_start, line_end = block_span(box.Text, box.SelectionStart, box.SelectionLength)
                box.Select(line_start, line_end - line_start)
                box.SelectedText = text[start:start + length]
                box.Select(start, length)
            else:
                line = text_before_caret()
                spaces = len(INDENT) - (len(line) % len(INDENT))
                box.SelectedText = ' ' * spaces
                box.CaretIndex = box.SelectionStart + spaces
                box.SelectionLength = 0
        elif key in (Key.Enter, Key.Return) and mods == NO_MODS:
            indent = indent_after(text_before_caret())
            insert = newline() + indent
            start = box.SelectionStart
            box.SelectedText = insert
            box.CaretIndex = start + len(insert)
            box.SelectionLength = 0
        else:
            return
        args.Handled = True
    box.PreviewKeyDown += ui.safe(box_keys, 'editor keys', logger)

    def window_keys(sender, args):
        mods = Keyboard.Modifiers
        key = args.Key
        ctrl = mods == ModifierKeys.Control
        if key == Key.S and ctrl:
            save()
        elif key == Key.F and ctrl:
            show_bar(find_bar, find_box)
        elif key == Key.G and ctrl:
            show_bar(goto_bar, goto_box)
        elif key == Key.F5:
            run()
        elif key == Key.F3:
            find(mods == ModifierKeys.Shift)
        elif key == Key.Escape and not popup.IsOpen and (find_bar.Visibility == Visibility.Visible or
                                                         goto_bar.Visibility == Visibility.Visible):
            hide_bars()
        else:
            return
        args.Handled = True
    win.PreviewKeyDown += ui.safe(window_keys, 'editor window keys', logger)

    def closing(sender, args):
        if dirty() and not ask_save():
            args.Cancel = True
    win.Closing += ui.safe(closing, 'editor closing', logger)

    # -- layout -----------------------------------------------------------------------------
    save_button = ui.button('Save', save, 'secondary', logger)
    run_button = ui.button('Run', run, 'primary', logger)
    reload_button = ui.button('Reload pyNavis', reload_pynavis, 'quiet', logger)
    toolbar = DockPanel()
    buttons = StackPanel()
    buttons.Orientation = Orientation.Horizontal
    for index, control in enumerate((reload_button, save_button, run_button)):
        control.Margin = ui.thickness(8, 0, 0, 0)
        buttons.Children.Add(control)
    DockPanel.SetDock(buttons, Dock.Right)
    toolbar.Children.Add(buttons)
    path_label.VerticalAlignment = VerticalAlignment.Center
    toolbar.Children.Add(path_label)

    code = Grid()
    for width in ('auto', 'star'):
        column = ColumnDefinition()
        column.Width = GridLength(1, GridUnitType.Star) if width == 'star' else GridLength.Auto
        code.ColumnDefinitions.Add(column)
    Grid.SetColumn(gutter, 0)
    code.Children.Add(gutter)
    Grid.SetColumn(box, 1)
    code.Children.Add(box)
    code_frame = Border()
    code_frame.BorderBrush = ui.brush(colors['line_strong'])
    code_frame.BorderThickness = ui.thickness(1)
    code_frame.Child = code
    code_frame.Margin = ui.thickness(0, 8, 0, 0)

    right = DockPanel()
    right.Margin = ui.thickness(12, 16, 16, 8)
    top = StackPanel()
    top.Children.Add(toolbar)
    top.Children.Add(find_bar)
    top.Children.Add(goto_bar)
    DockPanel.SetDock(top, Dock.Top)
    right.Children.Add(top)
    right.Children.Add(code_frame)

    left = DockPanel()
    left.Margin = ui.thickness(16, 16, 4, 8)
    heading = ui.text('Bundles you can edit', size=12, bold=True)
    heading.Margin = ui.thickness(0, 0, 0, 8)
    tree_top = StackPanel()
    tree_top.Children.Add(heading)
    tree_top.Children.Add(tree_search)
    DockPanel.SetDock(tree_top, Dock.Top)
    left.Children.Add(tree_top)
    tree.Margin = ui.thickness(0, 8, 0, 0)
    left.Children.Add(tree)

    body = Grid()
    for width in (300, 6, 'star'):
        column = ColumnDefinition()
        if width == 'star':
            column.Width = GridLength(1, GridUnitType.Star)
        else:
            column.Width = GridLength(width)
        body.ColumnDefinitions.Add(column)
    body.ColumnDefinitions[0].MinWidth = 180.0
    Grid.SetColumn(left, 0)
    body.Children.Add(left)
    splitter = GridSplitter()
    splitter.Width = 6.0
    splitter.HorizontalAlignment = HorizontalAlignment.Stretch
    splitter.Background = ui.brush(colors['paper'])
    Grid.SetColumn(splitter, 1)
    body.Children.Add(splitter)
    Grid.SetColumn(right, 2)
    body.Children.Add(right)

    bar = DockPanel()
    caret.Margin = ui.thickness(16, 0, 0, 0)
    DockPanel.SetDock(caret, Dock.Right)
    bar.Children.Add(caret)
    bar.Children.Add(status)
    status_bar = Border()
    status_bar.Background = ui.brush(colors['surface'])
    status_bar.BorderBrush = ui.brush(colors['line_strong'])
    status_bar.BorderThickness = ui.thickness(0, 1, 0, 0)
    status_bar.Padding = ui.thickness(16, 6, 16, 6)
    status_bar.Child = bar

    layout = DockPanel()
    DockPanel.SetDock(status_bar, Dock.Bottom)
    layout.Children.Add(status_bar)
    layout.Children.Add(body)
    win.Content = layout

    load_trees()
    refresh_tree()
    if not parts.extensions:
        set_status('No extension you can edit is loaded. Make one with Button Maker first.', True)
    else:
        set_status('Pick a file. Ctrl+S saves, F5 runs, Ctrl+F finds, Ctrl+G goes to a line, Ctrl+Space completes.')

    parts.box = box
    parts.tree = tree
    parts.open_file = open_file
    parts.save = save
    parts.run = run
    parts.find = find
    parts.find_box = find_box
    parts.go_to_line = go_to_line
    parts.show_completions = show_completions
    parts.accept_completion = accept_completion
    parts.completions = completions
    parts.popup = popup
    parts.status = status
    parts.dirty = dirty
    parts.activate = activate
    parts.refresh_tree = refresh_tree
    parts.redraw_gutter = redraw_gutter
    parts.box_keys = box_keys
    parts.tree_filter = tree_filter
    parts.set_extensions = set_extensions
    return win


def show(open_path=None):
    """Opens the editor (or brings the open one forward), optionally on a file."""
    existing = ui.Modeless.get(KEY)
    logger = ui.pinned_logger()
    extensions = editable()
    if existing is None:
        built = {}

        def factory():
            built['win'] = build_window(extensions, logger)
            return built['win']
        win = ui.Modeless(KEY, 'Script Editor', window_factory=factory).show()
    else:
        win = ui.Modeless(KEY, 'Script Editor').show()
        try:
            win.Tag.set_extensions(extensions)
        except Exception as error:
            ui.log_error('editor: could not refresh the extension list: %s' % error, logger)
    if open_path:
        try:
            win.Tag.open_file(open_path)
        except Exception as error:
            ui.log_error('editor: could not open %s: %s' % (open_path, error), logger)
    return win
