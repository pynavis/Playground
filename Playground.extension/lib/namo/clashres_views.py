# -*- coding: utf-8 -*-
"""Clash to Viewpoints: saved viewpoints for chosen clashes, in folders by test and group.

One viewpoint per group (ungrouped clashes get their own) or one per clash, filtered by
status. The camera is Clash Detective's own view of the result
(DocumentClashTests.TestsViewpointForResult, which takes groups too); each viewpoint
gets one comment with the status, distance, both elements, grid and level.

Folders and names come from templates (namo.naming syntax):

    folder  'Clashes/{test}/{group}'    '/' separates folders; empty segments drop out,
                                         so an ungrouped clash, or a group itself, lands
                                         in 'Clashes/<test>'
    name    '{name}'

Tokens: {test} {group} {name} {n} {status} {grid} {level} {distance} {model_a}
{model_b} {trade_a} {trade_b} {count} plus {date} {user} {project} {file}. A '/' inside
a value never splits a folder. Names are made unique within their folder; a name that
already exists is skipped unless 'replace' is on (the old viewpoint is removed first).

Everything is written in ONE undo step. Api.SavedViewpoint(Viewpoint) stores the camera
and sections only (no hide/override state, like namo.camera.save_view).

Pure planning first (unit tested); the API half after.
"""

from namo import naming

DEFAULT_FOLDER = 'Clashes/{test}/{group}'
DEFAULT_NAME = '{name}'
CONFIRM_ABOVE = 500
MODES = [('One per group (ungrouped clashes get their own)', 'group'), ('One per clash', 'clash')]


# ---- pure ---------------------------------------------------------------------------------


def _segment_safe(value):
    return str(value if value is not None else '').replace('/', '-').replace('\\', '-')


def split_folder(path):
    """'A/ B //C' -> ['A', 'B', 'C']."""
    return [part.strip() for part in str(path or '').split('/') if part.strip()]


def render_folder(template, values):
    """The folder path for a view: every value made slash-free first, then rendered,
    then empty segments dropped. Returns '/'-joined text ('' for the top level)."""
    safe = dict((key, _segment_safe(values[key]) if isinstance(values[key], str) else values[key])
                for key in values)
    text, _missing = naming.render(template or '', safe)
    return '/'.join(naming.sanitize(part) for part in split_folder(text) if naming.sanitize(part))


def unit_values(unit, doc_units, n):
    """Token values for a unit (namo.clashassign.units_of shape, or a single clash row
    wrapped as one)."""
    from namo import clashname
    rows = unit['rows']
    if unit['kind'] == 'group':
        values = clashname.group_values(unit['name'], rows, doc_units, unit.get('test', ''))
        values['group'] = ''
    else:
        values = clashname.clash_values(rows[0], doc_units)
        values['test'] = unit.get('test', '')
        values['group'] = rows[0].get('group') or ''
        values['count'] = 1
    values['name'] = unit['name']
    values['n'] = n
    return values


def comment_text(unit, doc_units):
    """The viewpoint comment: status, distance, both elements, grid and level, test."""
    from namo import clashset_tests as defs
    from namo import clashname
    rows = unit['rows']
    first = rows[0] if rows else {}
    lines = []
    if unit['kind'] == 'group':
        statuses = {}
        for row in rows:
            statuses[row.get('status')] = statuses.get(row.get('status'), 0) + 1
        parts = ['%s %s' % ('{:,}'.format(statuses[s]), s) for s in
                 sorted(statuses, key=lambda s: (-statuses[s], str(s)))]
        lines.append('Group of {:,} clash{}: {}'.format(len(rows), '' if len(rows) == 1 else 'es',
                                                         ', '.join(parts)))
        distances = [r.get('distance') for r in rows if r.get('distance') is not None]
        if distances:
            lines.append('Deepest: %s' % defs.length_text(min(distances), doc_units))
        grid = clashname.dominant(r.get('grid') for r in rows)
        level = clashname.dominant(r.get('level') for r in rows)
    else:
        lines.append('Status: %s' % (first.get('status') or ''))
        if first.get('distance') is not None:
            lines.append('Distance: %s' % defs.length_text(first.get('distance'), doc_units))
        grid, level = first.get('grid'), first.get('level')
    lines.append('A: %s%s' % (first.get('item_a_name') or '',
                              ' (%s)' % first['model_a'] if first.get('model_a') else ''))
    lines.append('B: %s%s' % (first.get('item_b_name') or '',
                              ' (%s)' % first['model_b'] if first.get('model_b') else ''))
    where = []
    if grid:
        where.append('Grid %s' % grid)
    if level:
        where.append('Level %s' % level)
    if where:
        lines.append(', '.join(where))
    lines.append('Test: %s' % unit.get('test', ''))
    return '\n'.join(lines)


def candidates(units, mode, statuses):
    """The units to save views for: in 'group' mode the units as given (groups and
    ungrouped clashes); in 'clash' mode every clash of every unit. A unit is kept when
    one of its clashes has a chosen status. Clash units come back as {'kind': 'clash',
    'rows': [row], 'name', 'test', 'ref': ('clash', row id)}."""
    wanted = set(str(s) for s in statuses or [])
    out = []
    for unit in units:
        if mode == 'clash':
            for row in unit['rows']:
                if str(row.get('status')) in wanted:
                    out.append({'kind': 'clash', 'rows': [row], 'name': row.get('name') or '',
                                'test': unit.get('test', ''), 'ref': ('clash', row['id'])})
            continue
        if any(str(r.get('status')) in wanted for r in unit['rows']):
            ref = ('group', unit.get('guid')) if unit['kind'] == 'group' else ('clash', unit['rows'][0]['id'])
            out.append(dict(unit, ref=ref))
    return out


def plan(units_by_test, mode, statuses, folder_template, name_template, doc_units,
         existing=None, standard=None):
    """[{'test' (the key), 'ref', 'folder', 'name', 'comment', 'exists'}] in test then
    tree order. units_by_test: [(key, test name, units)] (the key tells two tests with
    one name apart). existing(folder) -> set of lowercased names already in that folder
    (None: nothing exists). Names are unique per folder."""
    out = []
    taken = {}
    for test_key, test_name, units in units_by_test:
        for n, unit in enumerate(candidates(units, mode, statuses)):
            values = dict(standard or {})
            values.update(unit_values(unit, doc_units, n + 1))
            values['test'] = test_name
            folder = render_folder(folder_template or DEFAULT_FOLDER, values)
            text, _missing = naming.render(name_template or DEFAULT_NAME, values)
            name = naming.sanitize(text) or unit['name'] or 'Clash'
            key = folder.lower()
            if key not in taken:
                taken[key] = set()
            final = naming.unique(name, taken[key])
            taken[key].add(final.lower())
            already = existing(folder) if existing is not None else set()
            out.append({'test': test_key, 'ref': unit['ref'], 'folder': folder, 'name': final,
                        'comment': comment_text(unit, doc_units),
                        'exists': final.lower() in already})
    return out


def counts(planned, replace):
    """{'create', 'replace', 'skip'} for a plan."""
    exists = sum(1 for p in planned if p['exists'])
    return {'create': len(planned) - exists, 'replace': exists if replace else 0,
            'skip': 0 if replace else exists}


def top_folder(planned):
    """The common first folder of a plan ('Clashes'), or ''."""
    firsts = set(split_folder(p['folder'])[0] if split_folder(p['folder']) else '' for p in planned)
    return firsts.pop() if len(firsts) == 1 else ''


# ==== API half (Navisworks only; lazy imports) ============================================


def _doc(doc):
    if doc is not None:
        return doc
    from pynavis._api import Application
    return Application.ActiveDocument


def _find_folder(Api, saved, path):
    """The live folder at path, or None (no creation)."""
    node = saved.RootItem
    for segment in split_folder(path):
        found = None
        for child in node.Children:
            if isinstance(child, Api.FolderItem) and child.DisplayName == segment:
                found = child
                break
        if found is None:
            return None
        node = found
    return node


def existing_names(doc=None):
    """existing(folder) -> lowercased names of the viewpoints directly in that folder."""
    from pynavis._api import Api
    document = _doc(doc)
    cache = {}

    def existing(folder):
        key = folder.lower()
        if key not in cache:
            node = _find_folder(Api, document.SavedViewpoints, folder)
            cache[key] = set() if node is None else \
                set(str(child.DisplayName).lower() for child in node.Children)
        return cache[key]

    return existing


def create(planned, items_by_ref, replace=False, doc=None, progress=None):
    """Saves the planned viewpoints in ONE undo step. items_by_ref: {(test, ref): live
    ClashResult or ClashResultGroup}. Returns {'created', 'replaced', 'skipped', 'failed'}.
    progress(fraction, label) only reports."""
    from pynavis._api import Api
    from pynavis.viewpoints import transaction
    from namo import camera
    from namo import clashset_tests as defs
    document = _doc(doc)
    saved = document.SavedViewpoints
    data = defs._clash().get_clash(document).TestsData
    totals = {'created': 0, 'replaced': 0, 'skipped': 0, 'failed': 0}
    folders = {}
    names = {}          # folder key -> {lowercased name: viewpoint}, read once per folder
    total = len(planned) or 1
    with transaction('Clash viewpoints', document):
        for index, view in enumerate(planned):
            if progress is not None and index % 20 == 0:
                progress(float(index) / total, 'Saving {:,} of {:,}'.format(index, len(planned)))
            key = view['folder'].lower()
            if key not in folders:
                try:
                    folders[key] = camera.ensure_folder(view['folder'], document) if view['folder'] \
                        else saved.RootItem
                    names[key] = dict((str(child.DisplayName).lower(), child)
                                      for child in folders[key].Children
                                      if not isinstance(child, Api.FolderItem))
                except Exception:
                    folders[key] = None           # the folder could not be made
                    names[key] = {}
            parent = folders[key]
            if parent is None:
                totals['failed'] += 1
                continue
            at_root = not view['folder']
            lowered = view['name'].lower()
            existing = names[key].get(lowered)
            if existing is not None and not replace:
                totals['skipped'] += 1
                continue
            item = items_by_ref.get((view['test'], view['ref']))
            if item is None:
                totals['failed'] += 1
                continue
            try:
                viewpoint = data.TestsViewpointForResult(item)
                fresh = Api.SavedViewpoint(viewpoint)
                fresh.DisplayName = view['name']
                # The comment goes on the detached viewpoint before it is added, the way
                # the shipped Clash Grouper comments its new groups; DocumentSavedViewpoints
                # .AddComment on the added item is only the fallback.
                commented = not view['comment']
                if not commented:
                    try:
                        fresh.Comments.Add(Api.Comment(view['comment'], Api.CommentStatus.New))
                        commented = True
                    except Exception:
                        commented = False
                if existing is not None:
                    if at_root:
                        saved.Remove(existing)
                    else:
                        saved.Remove(parent, existing)
                    names[key].pop(lowered, None)
                count = _count(parent.Children)
                if at_root:
                    saved.AddCopy(fresh)
                else:
                    saved.AddCopy(parent, fresh)
            except Exception:
                totals['failed'] += 1
                continue
            totals['replaced' if existing is not None else 'created'] += 1
            if not commented:
                try:
                    added = _added(parent, count, view['name'])
                    if added is not None:
                        saved.AddComment(added, Api.Comment(view['comment'], Api.CommentStatus.New))
                except Exception:
                    pass                          # the viewpoint is saved; only its note is missing
    if progress is not None:
        progress(1.0, 'Done')
    return totals


def _count(collection):
    try:
        return collection.Count
    except AttributeError:
        return len(collection)


def _added(parent, count_before, name):
    """The child AddCopy just appended (checked by name; falls back to a search from
    the end)."""
    children = parent.Children
    size = _count(children)
    try:
        if size > count_before and children[count_before].DisplayName == name:
            return children[count_before]
    except Exception:
        pass
    for index in range(size - 1, -1, -1):
        if children[index].DisplayName == name:
            return children[index]
    return None


def items_by_ref(entries):
    """{(test key, ref): live item} for read_test entries, keyed by their position in
    the list (the key plan() gets): groups by Guid, clashes by leaf id."""
    out = {}
    for key, entry in enumerate(entries):
        for index, leaf in enumerate(entry['leaves']):
            out[(key, ('clash', index))] = leaf
        for group in entry['groups']:
            out[(key, ('group', str(group.Guid)))] = group
    return out
