# -*- coding: utf-8 -*-
"""Inspecting single items: What Is It, Copy IDs, Open in Explorer, Properties Plus.

Pure half (tested on both engines):
  * the What Is It card (card_html) and its clipboard summary (summary_text), both
    built from a plain info dict, so every field and every escape is testable
  * Copy IDs columns and rows (ID_COLUMNS, id_table)
  * Open in Explorer target choice (explorer_targets)
  * Properties Plus: pinned-property keys and the agree / varies summary of one
    property over many selected items (summarize)

API half (lazy imports): describe(item) gathers the info dict from the live model,
id_records(items) the Copy IDs records, link_html() wraps pynavis.output.element_link.
"""

from namo import htmlreport, naming, units

ID_COLUMNS = [('name', 'Name'), ('element_id', 'Element ID'), ('unique_id', 'UniqueId'),
              ('ifc_guid', 'IFC GlobalId'), ('instance_guid', 'InstanceGuid'),
              ('file', 'Source file'), ('path', 'Tree path')]
ID_KEYS = [key for key, _label in ID_COLUMNS]
ID_LABELS = dict(ID_COLUMNS)
EMPTY_GUID = '00000000-0000-0000-0000-000000000000'
GEOMETRY_SAMPLE = 5000       # descendants read for an element's geometry summary
VARIES_SHOWN = 5             # first values listed in a "Varies" tooltip

_esc = htmlreport.escape


# =============================================================================
# Pure half
# =============================================================================


def guid_text(value):
    """A GUID as lowercase text, '' for None or the empty GUID."""
    if value is None:
        return ''
    text = str(value).strip().strip('{}').lower()
    if not text or text == EMPTY_GUID:
        return ''
    return text


def length_text(value, doc_units, decimals=3):
    """'12.500 ft' in document units."""
    if value is None:
        return ''
    return units.format(value, units.doc_unit_symbol(doc_units), decimals)


def length_pair(value, doc_units):
    """'12.500 ft (3.810 m)': document units, then metres when they differ."""
    if value is None:
        return ''
    text = length_text(value, doc_units)
    if units.doc_unit_symbol(doc_units) != 'm':
        try:
            text += ' (%s)' % units.format(units.to_meters(value, doc_units), 'm', 3)
        except (ValueError, TypeError):
            pass
    return text


def point_text(point, doc_units, decimals=3):
    """'12.500, 4.000, 3.000 ft'."""
    if point is None:
        return ''
    numbers = ', '.join(('{:,.%df}' % decimals).format(float(v)) for v in point)
    return '%s %s' % (numbers, units.doc_unit_symbol(doc_units))


def yes_no(value):
    if value is None:
        return 'Unknown'
    return 'Yes' if value else 'No'


def swatch_html(hex_value):
    """A small colour square (hex 'RRGGBB'), or '' for None."""
    if not hex_value:
        return ''
    return ('<span class="playground-swatch" style="background:#%s"></span>'
            % _esc(str(hex_value).lstrip('#')[:6]))


def color_hex(rgb01):
    """'RRGGBB' from 0..1 floats (r, g, b); None stays None."""
    if rgb01 is None:
        return None
    out = []
    for channel in rgb01:
        value = int(round(max(0.0, min(1.0, float(channel))) * 255))
        out.append('%02X' % value)
    return ''.join(out)


def percent(value):
    """0.25 -> '25%'."""
    if value is None:
        return ''
    return '%d%%' % int(round(float(value) * 100))


_CARD_CSS = (
    '<style>'
    '.playground-wii{padding:16px 18px}'
    '.playground-wii h2{margin:0;font-size:18px;font-weight:600}'
    '.playground-wii .playground-sub{color:var(--muted);margin:2px 0 12px 0}'
    '.playground-wii h3{font-size:13px;font-weight:600;margin:16px 0 6px 0;padding-top:10px;'
    'border-top:1px solid var(--line)}'
    '.playground-wii table.playground-kv{border-collapse:collapse;width:100%}'
    '.playground-wii table.playground-kv td{padding:3px 8px 3px 0;vertical-align:top}'
    '.playground-wii table.playground-kv td.k{color:var(--muted);width:170px;white-space:nowrap}'
    '.playground-wii td.v{word-break:break-all}'
    '.playground-wii .playground-num{font-variant-numeric:tabular-nums}'
    '.playground-wii .playground-swatch{display:inline-block;width:12px;height:12px;margin-right:6px;'
    'vertical-align:-1px;border:1px solid var(--line);border-radius:2px}'
    '.playground-wii details{margin:2px 0}'
    '.playground-wii summary{cursor:pointer;padding:3px 0}'
    '.playground-wii summary .c{color:var(--muted)}'
    '.playground-wii details table{margin:2px 0 8px 18px;border-collapse:collapse}'
    '.playground-wii details td{padding:2px 12px 2px 0;vertical-align:top}'
    '.playground-wii details td.k{color:var(--muted)}'
    '.playground-wii .playground-note{color:var(--muted);font-size:12px}'
    '</style>')


def _kv(rows):
    """<table> of (label, trusted html) rows; empty values are skipped."""
    cells = []
    for label, value_html in rows:
        if value_html in (None, ''):
            continue
        cells.append('<tr><td class="k">%s</td><td class="v">%s</td></tr>' % (_esc(label), value_html))
    if not cells:
        return ''
    return '<table class="playground-kv">%s</table>' % ''.join(cells)


def _t(value):
    """Escaped text, '' for None."""
    return '' if value is None else _esc(value)


def card_html(info):
    """The What Is It card from describe()'s info dict. Text is escaped here; only
    info['path_links'] and info['object_link'] are trusted HTML (element links)."""
    doc_units = info.get('doc_units') or 'Meters'
    title = info.get('name') or info.get('class_name') or 'Item'
    sub = [part for part in (info.get('category'), info.get('family'), info.get('type'))
           if part]
    if not sub and info.get('class_name'):
        sub = [info['class_name']]
    parts = ['<div class="pynavis-card playground-wii">', _CARD_CSS,
             '<h2>%s</h2>' % _esc(title),
             '<div class="playground-sub">%s</div>' % _esc(', '.join(sub))]

    identity = [
        ('Class', _t(info.get('class_name')) + (
            ' <span class="playground-note">(%s)</span>' % _esc(info['class_internal'])
            if info.get('class_internal') and info.get('class_internal') != info.get('class_name')
            else '')),
        ('Revit category', _t(info.get('category'))),
        ('Family', _t(info.get('family'))),
        ('Type', _t(info.get('type'))),
        ('Element', info.get('object_link') or ''),
        ('Source file', _t(info.get('model_name'))),
        ('Source path', _t(info.get('source_path'))),
        ('Cache file', _t(info.get('cache_path')) if info.get('cache_path') != info.get('source_path') else ''),
        ('Tree path', ' &gt; '.join(info.get('path_links') or [_esc(n) for n in info.get('path_names') or []])),
    ]
    parts.append(_kv(identity))

    ids = [
        ('Element ID', _t(info.get('element_id'))),
        ('UniqueId', _t(info.get('unique_id'))),
        ('IFC GlobalId', _t(info.get('ifc_guid')) + (
            ' <span class="playground-note">(derived from UniqueId)</span>'
            if info.get('ifc_guid') and info.get('ifc_guid_derived') else '')),
        ('InstanceGuid', _t(info.get('instance_guid'))),
        ('Element InstanceGuid', _t(info.get('object_guid'))
         if info.get('object_guid') and info.get('object_guid') != info.get('instance_guid') else ''),
        ('Model index', _t(info.get('model_index'))),
        ('PathId', _t(info.get('path_id'))),
    ]
    block = _kv(ids)
    if block:
        parts.append('<h3>Identity</h3>' + block)

    box = info.get('bbox')
    if box is not None:
        size = tuple(box[1][i] - box[0][i] for i in range(3))
        centre = tuple((box[0][i] + box[1][i]) / 2.0 for i in range(3))
        location = [
            ('Minimum', '<span class="playground-num">%s</span>' % _esc(point_text(box[0], doc_units))),
            ('Maximum', '<span class="playground-num">%s</span>' % _esc(point_text(box[1], doc_units))),
            ('Centre', '<span class="playground-num">%s</span>' % _esc(point_text(centre, doc_units))),
            ('Size X', '<span class="playground-num">%s</span>' % _esc(length_pair(size[0], doc_units))),
            ('Size Y', '<span class="playground-num">%s</span>' % _esc(length_pair(size[1], doc_units))),
            ('Size Z', '<span class="playground-num">%s</span>' % _esc(length_pair(size[2], doc_units))),
        ]
        if info.get('picked') is not None:
            location.append(('Picked point', '<span class="playground-num">%s</span>'
                             % _esc(point_text(info['picked'], doc_units))))
        parts.append('<h3>Location</h3>' + _kv(location))
    elif info.get('picked') is not None:
        parts.append('<h3>Location</h3>' + _kv([('Picked point', _esc(point_text(info['picked'], doc_units)))]))

    geometry = info.get('geometry')
    if geometry:
        note = ''
        if geometry.get('sampled'):
            note = ' <span class="playground-note">(first %s geometry items read)</span>' % '{:,}'.format(
                geometry.get('items') or 0)
        rows = [
            ('Geometry items', '<span class="playground-num">%s</span>%s' % (
                '{:,}'.format(geometry.get('items') or 0), note)),
            ('Primitives', '<span class="playground-num">%s</span>' % '{:,}'.format(geometry.get('primitives') or 0)),
            ('Fragments', '<span class="playground-num">%s</span>' % '{:,}'.format(geometry.get('fragments') or 0)),
            ('Primitive types', _t(geometry.get('types'))),
            ('Solid', _t(yes_no(geometry.get('solid')))),
        ]
        parts.append('<h3>Geometry</h3>' + _kv(rows))

    color = info.get('color')
    state_rows = []
    if color:
        state_rows.append(('Original colour', '%s%s, %s transparent' % (
            swatch_html(color.get('original')), _t(color.get('original') and '#' + color['original']),
            _t(percent(color.get('original_t'))))))
        state_rows.append(('Active colour', '%s%s, %s transparent' % (
            swatch_html(color.get('active')), _t(color.get('active') and '#' + color['active']),
            _t(percent(color.get('active_t'))))))
    transform = info.get('transform') or {}
    if transform.get('item_identity') is not None:
        state_rows.append(('Transformed', _t('No' if transform['item_identity'] else 'Yes')))
    if transform.get('override') is not None:
        state_rows.append(('Moved by override', _t('Yes' if transform['override'] else 'No')))
    flags = info.get('flags') or {}
    if flags:
        hidden = 'Yes' if flags.get('hidden_self') else (
            'By a parent' if flags.get('hidden_effective') else 'No')
        state_rows.append(('Hidden', _t(hidden)))
        state_rows.append(('Required', _t(yes_no(flags.get('required')))))
        state_rows.append(('Frozen', _t(yes_no(flags.get('frozen')))))
    if state_rows:
        parts.append('<h3>Appearance and state</h3>' + _kv(state_rows))
        if color:
            parts.append('<div class="playground-note">Colours are read from the first geometry item; '
                         'override read-back is best effort.</div>')

    tabs = info.get('tabs') or []
    if tabs:
        count = sum(len(props) for _cat, props in tabs)
        parts.append('<h3>Properties <span class="playground-note">%s tabs, %s properties</span></h3>'
                     % ('{:,}'.format(len(tabs)), '{:,}'.format(count)))
        for category, props in tabs:
            rows = ''.join('<tr><td class="k">%s</td><td>%s</td></tr>' % (_esc(p), _esc(v))
                           for p, v in props)
            parts.append('<details><summary>%s <span class="c">(%d)</span></summary><table>%s</table>'
                         '</details>' % (_esc(category), len(props), rows))
    parts.append('</div>')
    return ''.join(parts)


def summary_text(info):
    """The plain-text summary What Is It puts on the clipboard."""
    doc_units = info.get('doc_units') or 'Meters'
    lines = []

    def add(label, value):
        if value not in (None, ''):
            lines.append('%s: %s' % (label, value))
    add('Name', info.get('name'))
    add('Class', info.get('class_name'))
    add('Revit category', info.get('category'))
    add('Family', info.get('family'))
    add('Type', info.get('type'))
    add('Source file', info.get('model_name'))
    add('Source path', info.get('source_path'))
    add('Tree path', ' > '.join(info.get('path_names') or []))
    add('Element ID', info.get('element_id'))
    add('UniqueId', info.get('unique_id'))
    add('IFC GlobalId', info.get('ifc_guid'))
    add('InstanceGuid', info.get('instance_guid'))
    add('Model index', info.get('model_index'))
    add('PathId', info.get('path_id'))
    box = info.get('bbox')
    if box is not None:
        add('Minimum', point_text(box[0], doc_units))
        add('Maximum', point_text(box[1], doc_units))
        size = tuple(box[1][i] - box[0][i] for i in range(3))
        add('Size', '%s x %s x %s' % tuple(length_text(s, doc_units) for s in size))
    if info.get('picked') is not None:
        add('Picked point', point_text(info['picked'], doc_units))
    return '\r\n'.join(lines)


def id_table(records, columns=None):
    """(headers, rows) for Copy IDs: one row per record, the chosen column keys in
    ID_COLUMNS order (unknown keys ignored)."""
    wanted = [key for key in ID_KEYS if columns is None or key in columns]
    headers = [ID_LABELS[key] for key in wanted]
    rows = [[record.get(key) or '' for key in wanted] for record in records]
    return headers, rows


def explorer_targets(cache_file, source_file, exists):
    """[(label, path, present)] for Open in Explorer: the model's cache file and its
    source file, the same path listed once. exists(path) -> bool."""
    out = []
    seen = []
    for label, path in (('Source file', source_file), ('Cache file', cache_file)):
        path = (path or '').strip()
        if not path:
            continue
        key = path.replace('/', '\\').lower()
        if key in seen:
            continue
        seen.append(key)
        out.append((label, path, bool(exists(path))))
    return out


# ---- Properties Plus ------------------------------------------------------------


def pin_key(category, prop):
    """'Element > Category'."""
    return '%s > %s' % (category, prop)


def parse_pin(text):
    """(category, property) from 'Element > Category', or None."""
    text = (text or '').strip()
    if '>' not in text:
        return None
    category, prop = text.split('>', 1)
    category, prop = category.strip(), prop.strip()
    if not category or not prop:
        return None
    return (category, prop)


def clean_pins(pins):
    """Valid pins, duplicates removed (case-insensitive), order kept."""
    out = []
    seen = set()
    for pin in pins or []:
        pair = parse_pin(pin)
        if pair is None:
            continue
        key = pin_key(*pair)
        if key.lower() in seen:
            continue
        seen.add(key.lower())
        out.append(key)
    return out


def summarize(texts, missing_text='(missing)'):
    """One pinned property over the selection. texts: display text per selected item
    (missing_text where the item lacks it). Returns {'state': 'none' | 'same' |
    'varies' | 'missing', 'value', 'distinct', 'present', 'total', 'first': [first
    values, most common first], 'counts': [(text, n)]}."""
    total = len(texts)
    counts = {}
    present = 0
    for text in texts:
        if text != missing_text:
            present += 1
        counts[text] = counts.get(text, 0) + 1
    ordered = sorted(counts.items(), key=lambda p: (-p[1], naming.natural_key(p[0]), p[0]))
    out = {'total': total, 'present': present, 'distinct': len(ordered), 'counts': ordered,
           'first': [text for text, _n in ordered[:VARIES_SHOWN]]}
    if not total:
        out.update({'state': 'none', 'value': ''})
    elif present == 0:
        out.update({'state': 'missing', 'value': 'Not on the selection'})
    elif len(ordered) == 1:
        out.update({'state': 'same', 'value': ordered[0][0]})
    else:
        out.update({'state': 'varies', 'value': 'Varies (%s values)' % '{:,}'.format(len(ordered))})
    return out


def varies_tooltip(summary):
    """Tooltip text for a summarized row: the most common values with counts."""
    if summary.get('state') not in ('varies', 'missing'):
        return summary.get('value') or ''
    lines = ['%s  (%s)' % (text, '{:,}'.format(n)) for text, n in summary['counts'][:VARIES_SHOWN]]
    more = summary['distinct'] - VARIES_SHOWN
    if more > 0:
        lines.append('and %s more' % '{:,}'.format(more))
    return '\n'.join(lines)


# =============================================================================
# API half
# =============================================================================


def _doc(doc):
    if doc is not None:
        return doc
    from pynavis._api import Application
    return Application.ActiveDocument


def link_html(item, label):
    """pynavis.output.element_link, escaped plain text when no link can be made."""
    try:
        from pynavis import output
        link = output.element_link(item, label)
        if link and link != label:
            return link
    except Exception:
        pass
    return _esc(label)


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:
        return default


def _color_tuple(color):
    if color is None:
        return None
    return (color.R, color.G, color.B)


def _geometry_summary(item):
    """{'items', 'primitives', 'fragments', 'solid', 'types', 'sampled'} for the item's
    own geometry, or summed over its geometry descendants (first GEOMETRY_SAMPLE)."""
    sources = []
    sampled = False
    if item.HasGeometry:
        sources = [item.Geometry]
    else:
        for node in item.Descendants:
            if node.HasGeometry:
                sources.append(node.Geometry)
                if len(sources) >= GEOMETRY_SAMPLE:
                    sampled = True
                    break
    if not sources:
        return None
    primitives = fragments = 0
    solid = True
    types = []
    for geometry in sources:
        primitives += int(_safe(lambda: geometry.PrimitiveCount, 0) or 0)
        fragments += int(_safe(lambda: geometry.FragmentCount, 0) or 0)
        if not _safe(lambda: geometry.IsSolid, False):
            solid = False
        kind = _safe(lambda: str(geometry.PrimitiveTypes), '')
        for part in [p.strip() for p in kind.split(',') if p.strip()]:
            if part not in types and part != 'None':
                types.append(part)
    return {'items': len(sources), 'primitives': primitives, 'fragments': fragments,
            'solid': solid, 'types': ', '.join(sorted(types)), 'sampled': sampled}


def describe(item, doc=None, picked=None, reader=None, links=True):
    """The info dict card_html/summary_text render, read from the live item."""
    from namo import items, propindex
    document = _doc(doc)
    reader = reader or propindex.Reader(document)
    info = {'doc_units': str(document.Units), 'picked': picked}
    info['name'] = _safe(lambda: item.DisplayName, '') or ''
    info['class_name'] = _safe(lambda: item.ClassDisplayName, '') or ''
    info['class_internal'] = _safe(lambda: item.ClassName, '') or ''
    ids = _safe(lambda: items.revit_ids(item), {}) or {}
    for key in ('category', 'family', 'type', 'element_id', 'unique_id', 'ifc_guid'):
        info[key] = ids.get(key)
    info['ifc_guid_derived'] = bool(ids.get('ifc_guid_derived'))
    info['instance_guid'] = guid_text(_safe(lambda: item.InstanceGuid))
    element = items.object_of(item)
    if element is not None and not element.Equals(item):
        info['object_guid'] = guid_text(_safe(lambda: element.InstanceGuid))
        name = _safe(lambda: element.DisplayName, '') or _safe(lambda: element.ClassDisplayName, '')
        info['object_link'] = link_html(element, name) if links else _esc(name)
    model = _safe(lambda: items.model_of(item))
    if model is not None:
        info['source_path'] = _safe(lambda: model.SourceFileName, '') or ''
        info['cache_path'] = _safe(lambda: model.FileName, '') or ''
        info['model_name'] = items.model_name(item)
    path_id = _safe(lambda: document.Models.CreatePathId(item))
    if path_id is not None:
        info['model_index'] = _safe(lambda: int(path_id.ModelIndex))
        info['path_id'] = _safe(lambda: str(path_id.PathId))
    chain = []
    node = item
    while node is not None:
        chain.append(node)
        node = node.Parent
    chain.reverse()
    names = [(_safe(lambda n=n: n.DisplayName, '') or _safe(lambda n=n: n.ClassDisplayName, '') or '')
             for n in chain]
    info['path_names'] = names
    if links:
        info['path_links'] = [link_html(n, name) for n, name in zip(chain, names)]
    info['bbox'] = _safe(lambda: items.bbox(item))
    info['geometry'] = _safe(lambda: _geometry_summary(item))
    geometry = _safe(lambda: item.Geometry if item.HasGeometry else item.FindFirstGeometry())
    if geometry is not None:
        info['color'] = {
            'original': color_hex(_safe(lambda: _color_tuple(geometry.OriginalColor))),
            'active': color_hex(_safe(lambda: _color_tuple(geometry.ActiveColor))),
            'original_t': _safe(lambda: float(geometry.OriginalTransparency)),
            'active_t': _safe(lambda: float(geometry.ActiveTransparency)),
        }
        override = _safe(lambda: geometry.PermanentOverrideTransform)
        info['transform'] = {
            'item_identity': _safe(lambda: bool(item.Transform.IsIdentity())),
            'override': (not bool(override.IsIdentity())) if override is not None else None,
        }
    else:
        info['transform'] = {'item_identity': _safe(lambda: bool(item.Transform.IsIdentity())),
                             'override': None}
    info['flags'] = {
        'hidden_self': _safe(lambda: bool(item.IsHidden), False),
        'hidden_effective': not _safe(lambda: items.visible(item), True),
        'required': _safe(lambda: bool(item.IsRequired)),
        'frozen': _safe(lambda: bool(item.IsFrozen)),
    }
    tabs = []
    current = None
    for category, prop, _kind, _vtype, text in reader.all(item):
        if current is None or current[0] != category:
            current = (category, [])
            tabs.append(current)
        current[1].append((prop, text))
    info['tabs'] = tabs
    return info


def id_record(item, doc=None):
    """The Copy IDs record of one object."""
    from namo import items
    ids = _safe(lambda: items.revit_ids(item), {}) or {}
    return {
        'name': _safe(lambda: item.DisplayName, '') or _safe(lambda: item.ClassDisplayName, '') or '',
        'element_id': ids.get('element_id') or '',
        'unique_id': ids.get('unique_id') or '',
        'ifc_guid': ids.get('ifc_guid') or '',
        'instance_guid': guid_text(_safe(lambda: item.InstanceGuid)),
        'file': items.model_name(item),
        'path': _safe(lambda: items.tree_path(item), '') or '',
    }


def id_records(selected, doc=None, tick=None):
    """Copy IDs records, one per distinct object of the selected items, in selection
    order."""
    from namo import items
    seen = set()
    out = []
    ticker = items.Ticker(tick, total=len(selected), every=200)
    for item in selected:
        element = items.object_of(item)
        ticker.step()
        if element in seen:
            continue
        seen.add(element)
        out.append(id_record(element, doc))
    ticker.finish()
    return out
