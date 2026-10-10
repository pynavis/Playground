# -*- coding: utf-8 -*-
"""Set Exchange: selection sets to and from a portable Playground XML file.

    <playground-sets version="1" document="Hospital.nwf" exported="2026-10-05T14:30:00" user="amol">
      <models>
        <model index="0" name="Arch.nwc"/>
      </models>
      <folder name="By Level">
        <search-set name="Level 1">
          <condition category="Element" property="Level" op="equals" value="Level 1" type="text"/>
        </search-set>
        <static-set name="Picked" count="2">
          <item model="Arch.nwc" model-index="0" path="0/3/12" name="Basic Wall"
                element-id="312045" unique-id="..." ifc-guid="..." instance-guid="..."/>
        </static-set>
      </folder>
    </playground-sets>

Search sets travel as their conditions (pynavis.sets.to_dict; a condition Navisworks
does not expose readably is kept as op="raw" with its text and reported on import).
Static sets travel as item REFERENCES that survive into another file or session: the
model file name and PathId first, then the Revit Element ID, UniqueId, IFC GlobalId and
Navisworks InstanceGuid when the item has them. Import resolves PathId first (instant)
and keeps a hit only when the item there still carries the reference's id (a re-exported
model can put a different element at the same path). What is still missing is then found
by id: a few Element IDs by one native search each, scoped to their model (the route
pyNavis' own Select by IDs uses), anything more in ONE walk of the elements of the
matching models.

Pure half: XML write/read, tree flattening, the identity index. API half: collect a
document's sets, resolve references, create sets.
"""

import datetime
from xml.sax.saxutils import quoteattr

ROOT = 'playground-sets'
VERSION = '1'
ID_FIELDS = ('element_id', 'unique_id', 'ifc_guid', 'instance_guid')
ATTRS = [('model', 'model'), ('model_index', 'model-index'), ('path', 'path'), ('name', 'name'),
         ('element_id', 'element-id'), ('unique_id', 'unique-id'), ('ifc_guid', 'ifc-guid'),
         ('instance_guid', 'instance-guid')]
EMPTY_GUID = '00000000-0000-0000-0000-000000000000'
REVIT_FIELDS = ('element_id', 'unique_id', 'ifc_guid')
# Up to this many missing Element IDs are searched for natively, one search each (well
# under a second per id when scoped to one file); more are matched in one walk instead.
SEARCH_LIMIT = 20
ELEMENT_CATEGORY = 'LcRevitData_Element'    # internal name: only real Revit elements carry it


# ---- pure half: values -----------------------------------------------------------------


def type_of(value):
    if isinstance(value, bool):
        return 'bool'
    if isinstance(value, int):
        return 'int'
    if isinstance(value, float):
        return 'float'
    return 'text'


def value_from(text, kind):
    """A condition value back from its XML text and type."""
    if kind == 'bool':
        return str(text).strip().lower() in ('true', 'yes', '1')
    if kind == 'int':
        try:
            return int(text)
        except ValueError:
            return float(text)
    if kind == 'float':
        return float(text)
    return text


def value_text(value):
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, float):
        return repr(value)
    return str(value)


def _clean_xml_text(text):
    """Characters XML 1.0 cannot hold are dropped."""
    out = []
    for ch in str(text):
        code = ord(ch)
        if code in (9, 10, 13) or 32 <= code <= 0xD7FF or 0xE000 <= code <= 0xFFFD:
            out.append(ch)
    return ''.join(out)


def _attr(name, value):
    return '%s=%s' % (name, quoteattr(_clean_xml_text(value)))


# ---- pure half: write ------------------------------------------------------------------


def write_xml(meta, tree):
    """XML text for a set tree.

    meta: {'document', 'exported', 'user', 'models': [names]}; tree: nodes
    {'kind': 'folder', 'name', 'children'} | {'kind': 'search', 'name', 'conditions'} |
    {'kind': 'static', 'name', 'items': [ref dicts]}."""
    lines = ['<?xml version="1.0" encoding="utf-8"?>']
    lines.append('<%s %s %s %s %s>' % (ROOT, _attr('version', VERSION),
                                       _attr('document', meta.get('document') or ''),
                                       _attr('exported', meta.get('exported') or ''),
                                       _attr('user', meta.get('user') or '')))
    lines.append('  <models>')
    for index, name in enumerate(meta.get('models') or []):
        lines.append('    <model %s %s/>' % (_attr('index', index), _attr('name', name)))
    lines.append('  </models>')

    def node(entry, depth):
        pad = '  ' * depth
        kind = entry.get('kind')
        if kind == 'folder':
            lines.append('%s<folder %s>' % (pad, _attr('name', entry.get('name', ''))))
            for child in entry.get('children') or []:
                node(child, depth + 1)
            lines.append('%s</folder>' % pad)
        elif kind == 'search':
            lines.append('%s<search-set %s>' % (pad, _attr('name', entry.get('name', ''))))
            for cond in entry.get('conditions') or []:
                lines.append('%s  <condition %s/>' % (pad, ' '.join(_condition_attrs(cond))))
            lines.append('%s</search-set>' % pad)
        elif kind == 'static':
            refs = entry.get('items') or []
            lines.append('%s<static-set %s %s>' % (pad, _attr('name', entry.get('name', '')),
                                                   _attr('count', len(refs))))
            for ref in refs:
                attrs = [_attr(xml_name, ref[key]) for key, xml_name in ATTRS
                         if ref.get(key) not in (None, '')]
                lines.append('%s  <item %s/>' % (pad, ' '.join(attrs)))
            lines.append('%s</static-set>' % pad)
    for entry in tree:
        node(entry, 1)
    lines.append('</%s>' % ROOT)
    return '\n'.join(lines) + '\n'


def _condition_attrs(cond):
    op = cond.get('op', '')
    if op == 'raw':
        return [_attr('op', 'raw'), _attr('text', cond.get('text', ''))]
    attrs = [_attr('category', cond.get('category', ''))]
    if op != 'has_category':
        attrs.append(_attr('property', cond.get('prop', '')))
    attrs.append(_attr('op', op))
    if 'value' in cond and cond['value'] is not None:
        attrs.append(_attr('value', value_text(cond['value'])))
        attrs.append(_attr('type', type_of(cond['value'])))
    if cond.get('ignore_case'):
        attrs.append(_attr('ignore-case', 'true'))
    return attrs


# ---- pure half: read --------------------------------------------------------------------


def read_xml(text):
    """(meta, tree) from XML text. Raises ValueError with a sentence when the file is not
    a Playground sets file this version reads."""
    from xml.dom import minidom
    try:
        dom = minidom.parseString(text.encode('utf-8') if isinstance(text, str) else text)
    except Exception as error:
        raise ValueError('The file is not readable XML (%s).' % error)
    root = dom.documentElement
    if root.tagName != ROOT:
        raise ValueError('This is not a Playground sets file (it starts with <%s>).' % root.tagName)
    if root.getAttribute('version') != VERSION:
        raise ValueError('This sets file is version %s; this Playground reads version %s.'
                         % (root.getAttribute('version') or '?', VERSION))
    meta = {'document': root.getAttribute('document'), 'exported': root.getAttribute('exported'),
            'user': root.getAttribute('user'), 'models': []}

    def elements(parent):
        return [n for n in parent.childNodes if n.nodeType == n.ELEMENT_NODE]

    def parse(parent):
        out = []
        for child in elements(parent):
            tag = child.tagName
            if tag == 'models':
                for model in elements(child):
                    meta['models'].append(model.getAttribute('name'))
            elif tag == 'folder':
                out.append({'kind': 'folder', 'name': child.getAttribute('name'),
                            'children': parse(child)})
            elif tag == 'search-set':
                conds = [_condition_from(c) for c in elements(child) if c.tagName == 'condition']
                out.append({'kind': 'search', 'name': child.getAttribute('name'), 'conditions': conds})
            elif tag == 'static-set':
                refs = [_ref_from(c) for c in elements(child) if c.tagName == 'item']
                out.append({'kind': 'static', 'name': child.getAttribute('name'), 'items': refs})
        return out
    tree = parse(root)
    return meta, tree


def _condition_from(element):
    op = element.getAttribute('op')
    if op == 'raw':
        return {'op': 'raw', 'text': element.getAttribute('text')}
    cond = {'category': element.getAttribute('category'), 'op': op}
    if op != 'has_category':
        cond['prop'] = element.getAttribute('property')
    if element.hasAttribute('value'):
        try:
            cond['value'] = value_from(element.getAttribute('value'), element.getAttribute('type') or 'text')
        except ValueError:
            cond['value'] = element.getAttribute('value')
    if element.getAttribute('ignore-case') == 'true':
        cond['ignore_case'] = True
    return cond


def _ref_from(element):
    ref = {}
    for key, xml_name in ATTRS:
        if element.hasAttribute(xml_name):
            ref[key] = element.getAttribute(xml_name)
    if 'model_index' in ref:
        try:
            ref['model_index'] = int(ref['model_index'])
        except ValueError:
            ref['model_index'] = -1
    return ref


# ---- pure half: trees and identities ----------------------------------------------------


def flatten(tree, folder=''):
    """[(folder path escaped, node)] for every set, tree order."""
    from namo import find_sets
    out = []
    for node in tree:
        if node.get('kind') == 'folder':
            sub = find_sets.join(folder, node.get('name', ''))
            out.extend(flatten(node.get('children') or [], sub))
        else:
            out.append((folder, node))
    return out


def tree_from(rows, payloads):
    """A tree from find_sets.set_rows-shaped rows (with 'folder_names': [names]) and
    {guid: node} payloads, keeping tree order and only the folders that hold a chosen
    set."""
    root = []
    folders = {}
    for row in rows:
        node = payloads.get(row['guid'])
        if node is None:
            continue
        children = root
        path = ()
        for name in row.get('folder_names') or []:
            path = path + (name,)
            folder = folders.get(path)
            if folder is None:
                folder = {'kind': 'folder', 'name': name, 'children': []}
                folders[path] = folder
                children.append(folder)
            children = folder['children']
        children.append(node)
    return root


def has_raw(node):
    return any(c.get('op') == 'raw' for c in node.get('conditions') or [])


def search_query(node):
    """The pynavis query dict of a search-set node (one AND group)."""
    return {'or': [{'and': [dict(c) for c in node.get('conditions') or []]}]}


def identity_keys(ref):
    """[(kind, key)] an item reference can be found by after its PathId, strongest
    first. Element IDs are only unique inside one model, so they carry the model name."""
    keys = []
    guid = str(ref.get('instance_guid') or '').strip().lower()
    if guid and guid != EMPTY_GUID:
        keys.append(('instance_guid', guid))
    for field in ('unique_id', 'ifc_guid'):
        text = str(ref.get(field) or '').strip().lower()
        if text:
            keys.append((field, text))
    element_id = str(ref.get('element_id') or '').strip()
    if element_id:
        keys.append(('element_id', '%s|%s' % (str(ref.get('model') or '').lower(), element_id)))
    return keys


def contradicts(ref, actual):
    """True when the item found at a reference's path is plainly a different item.

    actual: {'unique_id', 'ifc_guid', 'element_id', 'name'} read from the item found. The
    first Revit/IFC id both sides carry decides; with no id in common the display name
    does (both non-blank and different). Nothing to compare is not a contradiction."""
    for field in ('unique_id', 'ifc_guid', 'element_id'):
        mine = str(ref.get(field) or '').strip().lower()
        theirs = str(actual.get(field) or '').strip().lower()
        if mine and theirs:
            return mine != theirs
    mine = str(ref.get('name') or '').strip()
    theirs = str(actual.get('name') or '').strip()
    return bool(mine and theirs and mine != theirs)


def check_fields(ref):
    """The id fields worth reading off an item to check it against a reference: the
    first one the reference carries (contradicts() stops at the first shared id)."""
    for field in ('unique_id', 'ifc_guid', 'element_id'):
        if str(ref.get(field) or '').strip():
            return (field,)
    return ()


def id_search_plan(pending, model_names, limit=SEARCH_LIMIT):
    """Positions (into pending) of the references to find by a native Element ID search:
    those with an Element ID whose model is in this document, when there are at most
    `limit` of them. More than that, or none, gives [] (the walk handles them)."""
    known = set(str(n).lower() for n in model_names)
    wanted = [position for position, ref in enumerate(pending)
              if str(ref.get('element_id') or '').strip()
              and str(ref.get('model') or '').lower() in known]
    return wanted if 0 < len(wanted) <= limit else []


def element_id_query(element_id, elements_only=True):
    """The query that finds one Revit element by id: Element ID > Value as text (the
    exporter stores a display string) and, when the model marks its elements, the
    exporter's Element category, so a TYPE id carried by nested parts finds nothing."""
    conds = [{'category': 'Element ID', 'prop': 'Value', 'op': 'equals', 'value': str(element_id)}]
    if elements_only:
        conds.append({'category': ELEMENT_CATEGORY, 'op': 'has_category', 'by_display': False})
    return {'or': [{'and': conds}]}


def wanted_index(refs):
    """{(kind, key): [positions]} for the references still to find."""
    index = {}
    for position, ref in enumerate(refs):
        for key in identity_keys(ref):
            index.setdefault(key, []).append(position)
    return index


def kinds_wanted(index):
    return set(kind for kind, _key in index)


def entry_of(ref):
    """pynavis.memory entry for a reference."""
    try:
        index = int(ref.get('model_index', -1))
    except (TypeError, ValueError):
        index = -1
    return {'m': ref.get('model') or '', 'i': index, 'p': ref.get('path') or ''}


def describe_tree(tree):
    """(search sets, static sets, items) counts."""
    search = static = items_ = 0
    for _folder, node in flatten(tree):
        if node['kind'] == 'search':
            search += 1
        else:
            static += 1
            items_ += len(node.get('items') or [])
    return search, static, items_


def preview_rows(flat):
    """ui.choose rows for the sets in a file: value = position."""
    from namo import find_query, find_sets
    rows = []
    for position, (folder, node) in enumerate(flat):
        if node['kind'] == 'search':
            what = find_query.join_descriptions(
                [find_query.describe_condition(c) for c in node.get('conditions') or []], 2)
            kind = 'Search'
        else:
            what = '%s items' % '{:,}'.format(len(node.get('items') or []))
            kind = 'Static'
        rows.append({'value': position, 'cells': [find_sets.plain_folder(folder), node.get('name', ''),
                                                  kind, what]})
    return rows


def now_text():
    return datetime.datetime.now().replace(microsecond=0).isoformat()


# ---- API half: export ---------------------------------------------------------------------


def _doc(doc=None):
    if doc is not None:
        return doc
    from pynavis._api import Application
    return Application.ActiveDocument


def _id_nodes(item):
    """Where an item's ids are read, in order: the nearest real Revit element (nested
    parts under a family instance carry the TYPE's id themselves), the item, its object
    ancestor. The same order namo.items.revit_ids uses."""
    from namo import items
    nodes = []
    revit = items.revit_element(item)
    if revit is not None:
        nodes.append(revit)
    for node in (item, items.object_of(item)):
        if not any(node.Equals(known) for known in nodes):
            nodes.append(node)
    return nodes


def _ids(item, fields=REVIT_FIELDS):
    """({field: text}, source) for the wanted id fields of an item: only what the model
    actually carries (no derived IFC GUIDs), read with as few property lookups as
    possible (this runs once per element of a model). source is the item the ids
    belong to: the Revit element when there is one, else the item."""
    from namo import items
    nodes = _id_nodes(item)
    out = {}
    for field in fields:
        text = ''
        for node in nodes:
            for category, name in items.REVIT_PROPERTIES[field]:
                value = items._get(node, category, name)
                if value is not None and str(value).strip():
                    text = items.value_text(value)
                    break
            if text:
                break
        out[field] = text
    return out, nodes[0]


def refs_for(found, doc=None, report=None):
    """Portable references for items (report(fraction, label) every 50)."""
    from pynavis import memory
    document = _doc(doc)
    data = list(found)
    entries = memory.encode_items(data, document)
    out = []
    for position, (item, entry) in enumerate(zip(data, entries)):
        ref = {'model': entry['m'], 'model_index': entry['i'], 'path': entry['p'],
               'name': item.DisplayName or item.ClassDisplayName or ''}
        try:
            ref.update(_ids(item)[0])
        except Exception:
            pass
        try:
            guid = str(item.InstanceGuid)
            if guid and guid.lower() != EMPTY_GUID:
                ref['instance_guid'] = guid
        except Exception:
            pass
        out.append(ref)
        if report is not None and position % 50 == 0:
            report(float(position) / max(1, len(data)), 'Describing %s of %s items' % (
                '{:,}'.format(position), '{:,}'.format(len(data))))
    return out


def export_rows(doc=None):
    """Set rows for the chooser (tree order), with 'folder_names' for tree_from."""
    from namo import find_sets
    rows = find_sets.snapshot(doc)
    names = dict((r['key'], r['name']) for r in rows if r['is_folder'])
    parent = dict((r['key'], r['parent_key']) for r in rows)
    out = []
    for row in find_sets.set_rows(rows):
        parts = []
        key = row['parent_key']
        while key:
            parts.append(names.get(key, ''))
            key = parent.get(key, '')
        row['folder_names'] = list(reversed(parts))
        out.append(row)
    return out


def collect(rows, doc=None, report=None):
    """(meta, tree) for the chosen set rows. Static sets get item references."""
    from pynavis import sets
    from namo import find_sets, items
    document = _doc(doc)
    payloads = {}
    total = len(rows)
    for position, row in enumerate(rows):
        item = find_sets.resolve_guid(row['guid'], document)
        if item is None:
            continue
        if report is not None:
            report(float(position) / max(1, total), 'Reading %s' % row['name'])
        if row.get('has_search'):
            # Values cleaned of 'DisplayString:' and each condition's options kept.
            conds = find_sets.set_conditions(item, document)
            payloads[row['guid']] = {'kind': 'search', 'name': row['name'], 'conditions': conds}
        else:
            found = list(sets.items_of(item, document))
            payloads[row['guid']] = {'kind': 'static', 'name': row['name'],
                                     'items': refs_for(found, document, report if len(found) > 200 else None)}
    meta = {'document': _doc_name(document), 'exported': now_text(), 'user': _user(),
            'models': [m['name'] for m in items.models(document)]}
    return meta, tree_from(rows, payloads)


def _doc_name(document):
    import os
    try:
        return os.path.basename(document.FileName or '') or document.Title or ''
    except Exception:
        return ''


def _user():
    try:
        from namo import config
        return config.user_name()
    except Exception:
        return ''


# ---- API half: import -----------------------------------------------------------------------


def _still_the_item(ref, item):
    """False when the item at a reference's path is a different one now."""
    fields = check_fields(ref)
    actual = {'name': item.DisplayName or item.ClassDisplayName or ''}
    if fields:
        try:
            actual.update(_ids(item, fields)[0])
        except Exception:
            pass
    return not contradicts(ref, actual)


def resolve_refs(refs, doc=None, report=None):
    """(items, found_count) for references. PathId first, kept only while the item there
    still carries the reference's id; then by id: a few Element IDs by native search,
    the rest in one walk of the elements of the models the references name (all models
    when none match), matching InstanceGuid, UniqueId, IFC GlobalId, then Element ID
    within its model. A reference found through an id resolves to its element.
    report(fraction, label) raises to cancel."""
    from namo import items
    document = _doc(doc)
    found = [None] * len(refs)
    for position, ref in enumerate(refs):
        hits, _missing = items.resolve([entry_of(ref)], document)
        if hits and _still_the_item(ref, hits[0]):
            found[position] = hits[0]
        if report is not None and position % 200 == 0:
            report(float(position) / max(1, len(refs)), 'Finding items by path: %s of %s' % (
                '{:,}'.format(position), '{:,}'.format(len(refs))))
    remaining = [p for p, item in enumerate(found) if item is None]
    if remaining:
        pending = [refs[p] for p in remaining]
        _search_for_ids(pending, remaining, found, document, report)
        remaining = [p for p in remaining if found[p] is None]
    if remaining:
        pending = [refs[p] for p in remaining]
        index = wanted_index(pending)
        if index:
            _walk_for_ids(index, pending, remaining, found, document, report)
    out = [item for item in found if item is not None]
    return out, len(out)


def _search_for_ids(pending, remaining, found, document, report):
    """Finds a few references by Element ID, one native search each, scoped to the
    reference's own model (an Element ID is only unique inside one file). Failures are
    left for the walk."""
    from pynavis import sets
    from namo import items, session
    models = items.models(document)
    plan = id_search_plan(pending, [m['name'] for m in models])
    if not plan:
        return
    root_of = {}
    for model in models:
        root_of.setdefault(model['name'].lower(), model['root'])
    marked = {}
    for count, position in enumerate(plan):
        ref = pending[position]
        element_id = str(ref.get('element_id')).strip()
        name = str(ref.get('model') or '').lower()
        root = root_of[name]
        if report is not None:
            report(float(count) / len(plan), 'Searching for Element ID %s (%d of %d)' % (
                element_id, count + 1, len(plan)))
        try:
            if name not in marked:
                marked[name] = sets.find_first(
                    {'or': [{'and': [{'category': ELEMENT_CATEGORY, 'op': 'has_category',
                                      'by_display': False}]}]}, document, scope=[root]) is not None
            hit = sets.find_first(element_id_query(element_id, marked[name]), document, scope=[root])
        except Exception as error:
            session.log('warning', 'Import Sets: the search for Element ID %s failed (%s)' % (
                element_id, error))
            return
        if hit is not None:
            found[remaining[position]] = hit


def _walk_for_ids(index, pending, remaining, found, document, report):
    from namo import items
    wanted_models = set(str(r.get('model') or '').lower() for r in pending)
    models = items.models(document)
    chosen = [m for m in models if m['name'].lower() in wanted_models] or models
    kinds = kinds_wanted(index)
    fields = tuple(f for f in REVIT_FIELDS if f in kinds)
    state = {'left': len([p for p in remaining if found[p] is None])}

    def take(key, item):
        for position in index.get(key, []):
            slot = remaining[position]
            if found[slot] is None:
                found[slot] = item
                state['left'] -= 1

    for number, model in enumerate(chosen):
        model_name = model['name'].lower()

        def tick(done, total=None, _name=model['name'], _number=number):
            if report is not None:
                report(float(_number) / len(chosen), 'Searching %s by id: %s items walked' % (
                    _name, '{:,}'.format(done)))
            return True
        elements = items.objects([model['root']], tick=tick)
        done = set()
        for position, element in enumerate(elements):
            # Reading ids is the slow part (several property lookups per element): keep
            # the bar moving and Cancel live.
            if report is not None and position % 200 == 0:
                report((number + float(position) / max(1, len(elements))) / len(chosen),
                       'Matching ids in %s: %s of %s elements' % (
                           model['name'], '{:,}'.format(position), '{:,}'.format(len(elements))))
            if 'instance_guid' in kinds:
                try:
                    take(('instance_guid', str(element.InstanceGuid).lower()), element)
                except Exception:
                    pass
            if fields:
                try:
                    ids, source = _ids(element, fields)
                except Exception:
                    continue
                if source in done:
                    continue                # the parts of one element share its ids
                done.add(source)
                if ids.get('unique_id'):
                    take(('unique_id', ids['unique_id'].lower()), source)
                if ids.get('ifc_guid'):
                    take(('ifc_guid', ids['ifc_guid'].lower()), source)
                if ids.get('element_id'):
                    take(('element_id', '%s|%s' % (model_name, ids['element_id'])), source)
            if state['left'] <= 0:
                return


def create_static(name, found, folder=None, doc=None):
    from namo import find_sets
    _item, final = find_sets.create_set(name, found, folder, doc=doc)
    return final


def create_search(name, node, folder=None, doc=None):
    from namo import find_sets
    _item, final = find_sets.create_set(name, search_query(node), folder, doc=doc)
    return final
