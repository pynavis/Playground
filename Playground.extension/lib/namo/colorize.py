# -*- coding: utf-8 -*-
"""Colouring by property: the engine behind Color by Property, Color Presets and
Status Painter.

A *scheme* is what a colouring run produced, in the shape namo.paint remembers
(paint.normalize_scheme): {'title', 'property': {'category', 'property'},
'entries': [{'value', 'hex', 'count'}], 'ghost', 'time'} plus three keys of ours
that normalize_scheme keeps:

    'kinds'     ['value' | 'missing' | 'other'] parallel to entries: value rows
                first (most common first), then the '(no value)' row, then the
                'Other (N values)' row. hex None means "left unchanged".
    'subtitle'  one line for legends: 'Element > Category, visible items'
    'total'     items the run looked at

Colours stay put between runs: for each property the colour every value got is
remembered (global store 'colorize-memory', newest first, capped), and the next
run hands a remembered value the same colour unless a more common value already
claimed it. New values take the first palette colour nobody holds.

Presets are one JSON file each in <team_root>\\presets\\colors\\ (the team folder
when Playground shares one, else %APPDATA%\\pyNavis\\playground), so a team colours the same way.

The pure half is tested on both engines; the API half lazy-imports pynavis.
"""

import datetime
import os
import re

from namo import colors, items, naming, paths

NO_VALUE = items.NO_VALUE
DEFAULT_TOP = 12
MAX_TOP = 40
GHOST_TRANSPARENCY = 0.85
MEMORY_STORE = 'colorize-memory'
MEMORY_LIMIT = 400
PROPERTY_SAMPLE = 300
SEARCH_MAX_VALUES = 16
PRESET_FORMAT = 'playground-color-preset'
PRESET_VERSION = 1

SCOPES = (('selection', 'Current selection'), ('visible', 'Visible items'),
          ('model', 'Whole model'))
OTHER_MODES = (('grey', 'Grey'), ('leave', 'Leave unchanged'))


# =============================================================================
# Pure half
# =============================================================================


def property_label(category, prop):
    """'Element > Category' as people read it."""
    return '%s > %s' % (str(category or '').strip(), str(prop or '').strip())


def scheme_key(category, prop):
    """The memory key of a property: its label, lower case."""
    return property_label(category, prop).lower()


def count_text(n):
    return '{:,}'.format(int(n))


def plural(n, word, many=None):
    """'1 item' / '2,345 items'."""
    return '%s %s' % (count_text(n), word if n == 1 else (many or word + 's'))


def rank_groups(groups):
    """[(value_text, members)] most common first, ties in natural order, so the
    order is the same on every engine. groups: {text: [members]} or pairs."""
    pairs = list(groups.items()) if isinstance(groups, dict) else list(groups)
    return sorted(pairs, key=lambda pair: (-len(pair[1]), naming.natural_key(pair[0]), str(pair[0])))


def group_by_value(members, texts):
    """[(text, [members])] ranked (rank_groups) from two parallel lists."""
    groups = {}
    for member, text in zip(members, texts):
        groups.setdefault(text, []).append(member)
    return rank_groups(groups)


def assign_colors(values, remembered=None, palette=None, reserved=(colors.GHOST, colors.MISSING)):
    """[(value, hex)] for values in their order. A value keeps its remembered
    colour unless an earlier value already holds it; the others take the first
    palette colours (continuing with generated hues) that nobody holds. No two
    values share a colour, and none gets a reserved one."""
    remembered = remembered or {}
    used = set(colors.parse_hex(h) for h in reserved if colors.parse_hex(h))
    out = [None] * len(values)
    for index, value in enumerate(values):
        hex_value = colors.parse_hex(remembered.get(value)) if value in remembered else None
        if hex_value and hex_value not in used:
            out[index] = hex_value
            used.add(hex_value)
    cursor = 0
    for index in range(len(values)):
        if out[index] is not None:
            continue
        while True:
            candidate = colors.color_at(cursor, palette)
            cursor += 1
            if candidate not in used:
                break
        out[index] = candidate
        used.add(candidate)
    return list(zip(values, out))


def plan_scheme(ranked, top=DEFAULT_TOP, other='grey', remembered=None, palette=None):
    """The scheme rows for ranked [(value_text, count)] (rank_groups order).

    The `top` most common values get colours (assign_colors); '(no value)' never
    takes a palette slot: it gets colors.MISSING, or stays unchanged with
    other='leave'; the remaining values fold into one 'Other (N values)' row in
    colors.GHOST grey, or unchanged. Returns {'entries', 'kinds', 'other_values'
    (texts folded into Other), 'total'}."""
    top = max(1, min(MAX_TOP, int(top or DEFAULT_TOP)))
    values = [(text, int(count)) for text, count in ranked if text != NO_VALUE]
    missing = [int(count) for text, count in ranked if text == NO_VALUE]
    kept = values[:top]
    folded = values[top:]
    entries = []
    kinds = []
    for (text, count), (_v, hex_value) in zip(kept, assign_colors([t for t, _c in kept], remembered, palette)):
        entries.append({'value': text, 'hex': hex_value, 'count': count})
        kinds.append('value')
    if missing and missing[0]:
        entries.append({'value': NO_VALUE, 'hex': colors.MISSING if other == 'grey' else None,
                        'count': missing[0]})
        kinds.append('missing')
    if folded:
        entries.append({'value': 'Other (%s)' % plural(len(folded), 'value'),
                        'hex': colors.GHOST if other == 'grey' else None,
                        'count': sum(c for _t, c in folded)})
        kinds.append('other')
    return {'entries': entries, 'kinds': kinds, 'other_values': [t for t, _c in folded],
            'total': sum(c for _t, c in values) + sum(missing)}


def memory_map(memory, key):
    """{value: hex} remembered for one property key."""
    pairs = (memory or {}).get(key) or []
    out = {}
    for pair in reversed(pairs):                 # newest last so it wins
        if isinstance(pair, (list, tuple)) and len(pair) == 2 and colors.parse_hex(pair[1]):
            out[pair[0]] = colors.parse_hex(pair[1])
    return out


def update_memory(memory, key, pairs, limit=MEMORY_LIMIT):
    """A NEW memory dict where key's list starts with pairs [(value, hex)] (the
    newest assignment), followed by older pairs for other values, capped."""
    out = dict(memory or {})
    fresh = [[value, hex_value] for value, hex_value in pairs if hex_value]
    seen = set(value for value, _h in fresh)
    for pair in (memory or {}).get(key) or []:
        if isinstance(pair, (list, tuple)) and len(pair) == 2 and pair[0] not in seen:
            fresh.append([pair[0], pair[1]])
            seen.add(pair[0])
    out[key] = fresh[:max(1, int(limit))]
    return out


def value_pairs(scheme):
    """[(value, hex)] of a scheme's value rows (not '(no value)' or Other)."""
    kinds = scheme.get('kinds') or ['value'] * len(scheme.get('entries') or [])
    return [(e['value'], e['hex']) for e, k in zip(scheme.get('entries') or [], kinds)
            if k == 'value' and e.get('hex')]


def make_scheme(category, prop, plan, scope_label, ghost=None, title=None):
    """A scheme dict (paint.remember_scheme shape plus ours) from plan_scheme."""
    label = property_label(category, prop)
    return {'title': title or prop or label, 'property': {'category': category, 'property': prop},
            'entries': plan['entries'], 'kinds': plan['kinds'], 'ghost': ghost,
            'subtitle': '%s, %s' % (label, scope_label), 'total': plan['total']}


def escape(text):
    """HTML-escapes text for the output window."""
    text = '' if text is None else str(text)
    return (text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            .replace('"', '&quot;').replace("'", '&#39;'))


def share_text(count, total):
    """'12.5%' (one decimal under 10%, none above), '' without a total."""
    if not total:
        return ''
    share = 100.0 * count / total
    if share and share < 0.1:
        return '<0.1%'
    return ('%.1f%%' % share) if share < 10 else ('%.0f%%' % share)


def swatch_html(hex_value, size=14):
    """An inline swatch: the colour, or an empty outlined box for 'unchanged'."""
    if hex_value:
        return ('<span style="display:inline-block;width:%dpx;height:%dpx;border-radius:3px;'
                'background:#%s;border:1px solid rgba(0,0,0,.18);vertical-align:-2px"></span>'
                % (size, size, colors.parse_hex(hex_value)))
    return ('<span style="display:inline-block;width:%dpx;height:%dpx;border-radius:3px;'
            'border:1px dashed var(--muted);vertical-align:-2px" title="Unchanged"></span>'
            % (size - 2, size - 2))


def legend_html(scheme):
    """The legend for the output window: a heading, the subtitle, and a table of
    swatch, value, item count and share. Every text is escaped."""
    entries = scheme.get('entries') or []
    total = scheme.get('total') or sum(int(e.get('count') or 0) for e in entries)
    rows = []
    for entry in entries:
        count = int(entry.get('count') or 0)
        label = escape(entry.get('value'))
        if not entry.get('hex'):
            label += ' <span style="color:var(--muted)">(unchanged)</span>'
        rows.append('<tr><td style="width:24px">%s</td><td>%s</td><td class="num">%s</td>'
                    '<td class="num">%s</td></tr>'
                    % (swatch_html(entry.get('hex')), label, count_text(count),
                       share_text(count, total) if count else ''))
    head = '<h3 style="margin:4px 0 2px 0">%s</h3>' % escape(scheme.get('title') or 'Legend')
    sub = ''
    if scheme.get('subtitle'):
        sub = '<div style="color:var(--muted);margin-bottom:8px">%s</div>' % escape(scheme['subtitle'])
    table = ('<table class="pynavis"><thead><tr><th></th><th>Value</th><th class="num">Items</th>'
             '<th class="num">Share</th></tr></thead><tbody>%s</tbody></table>' % ''.join(rows))
    return head + sub + table


def legend_lines(scheme):
    """Plain text legend (viewpoint comments, clipboard): one value per line."""
    lines = [scheme.get('title') or 'Legend']
    if scheme.get('subtitle'):
        lines.append(scheme['subtitle'])
    for entry in scheme.get('entries') or []:
        hex_value = entry.get('hex')
        lines.append('%s  %s  %s' % ('#' + hex_value if hex_value else 'unchanged',
                                     entry.get('value'), count_text(entry.get('count') or 0)))
    return lines


def summary(scheme, painted):
    """(message, detail) for the toast after a colouring run."""
    kinds = scheme.get('kinds') or []
    values = kinds.count('value')
    other = [e for e, k in zip(scheme.get('entries') or [], kinds) if k == 'other']
    detail = plural(values, 'value') + ' colored'
    if other:
        detail += ', %s as Other' % other[0]['value'][len('Other ('):-1]
    detail += '. Legend in the output window.'
    return ('Colored %s by %s' % (plural(painted, 'item'), scheme.get('title') or 'property'), detail)


def counting(report, verb):
    """An items-style tick(done, total) that drives a progress(fraction, label)
    callback with '<verb> 1,234 of 5,678' (or '<verb> 1,234' while the total is
    unknown)."""
    def tick(done, total=None):
        if total:
            report(float(done) / float(total), '%s %s of %s' % (verb, count_text(done), count_text(total)))
        else:
            report(0.0, '%s %s' % (verb, count_text(done)))
        return True
    return tick


def sample_evenly(sequence, limit):
    """Up to `limit` members spread evenly over sequence (first and last kept),
    so a property list is not drawn from the first model only."""
    data = list(sequence)
    if limit is None or len(data) <= limit:
        return data
    if limit <= 1:
        return data[:1]
    step = (len(data) - 1) / float(limit - 1)
    return [data[int(round(i * step))] for i in range(limit)]


def property_rows(names, sampled):
    """ui.choose rows for [(category, property, count)] from items.sample_properties:
    value (category, property), cells [category, property, found-on count]."""
    rows = []
    for category, prop, count in names:
        rows.append({'value': (category, prop), 'cells': [category, prop, int(count)]})
    rows.sort(key=lambda r: (naming.natural_key(r['cells'][0]), naming.natural_key(r['cells'][1])))
    return rows


def options_fields(selection_count, defaults):
    """The Color by Property options form (namo.ui field dicts)."""
    scope_options = []
    if selection_count:
        scope_options.append(('Current selection (%s)' % plural(selection_count, 'item'), 'selection'))
    scope_options.append(('Visible items', 'visible'))
    scope_options.append(('Whole model', 'model'))
    scope = defaults.get('scope') or 'visible'
    if selection_count:
        scope = 'selection'             # a selection is what the user means; else the remembered scope
    elif scope == 'selection':
        scope = 'visible'
    return [
        {'kind': 'radio', 'key': 'scope', 'label': 'Color', 'options': scope_options, 'default': scope, 'fallback': None},
        {'kind': 'int', 'key': 'top', 'label': 'Values that get their own color', 'min': 1,
         'max': MAX_TOP, 'default': int(defaults.get('top') or DEFAULT_TOP),
         'hint': 'The most common values come first. The rest share the Other row.'},
        {'kind': 'radio', 'key': 'other', 'label': 'Other values and items without the property',
         'options': [('Grey', 'grey'), ('Leave unchanged', 'leave')], 'inline': True,
         'default': defaults.get('other') or 'grey', 'fallback': 'grey'},
        {'kind': 'check', 'key': 'reset', 'label': 'Clear earlier colors first',
         'default': bool(defaults.get('reset', True)),
         'hint': 'Only on the selection when you color the selection, else on the whole model.'},
        {'kind': 'check', 'key': 'ghost', 'label': 'Ghost everything that is not colored',
         'default': bool(defaults.get('ghost', False))},
    ]


# ---- presets (pure) ------------------------------------------------------------


def _now_text(now=None):
    return (now or datetime.datetime.now()).strftime('%Y-%m-%dT%H:%M:%S')


def preset_from_scheme(scheme, name, user=None, now=None):
    """A preset dict from a scheme: its value colours, the '(no value)' and
    Other colours and the ghost setting. ValueError when the scheme has no
    coloured value."""
    prop = scheme.get('property') or {}
    kinds = scheme.get('kinds') or ['value'] * len(scheme.get('entries') or [])
    entries = []
    missing = None
    other = None
    for entry, kind in zip(scheme.get('entries') or [], kinds):
        if kind == 'value' and entry.get('hex'):
            entries.append({'value': entry.get('value'), 'hex': colors.parse_hex(entry['hex'])})
        elif kind == 'missing':
            missing = colors.parse_hex(entry.get('hex'))
        elif kind == 'other':
            other = colors.parse_hex(entry.get('hex'))
    if not entries:
        raise ValueError('The last color scheme has no colored values to keep.')
    return normalize_preset({
        'format': PRESET_FORMAT, 'version': PRESET_VERSION, 'name': name,
        'property': {'category': prop.get('category', ''), 'property': prop.get('property', '')},
        'entries': entries, 'missing': missing, 'other': other, 'ghost': scheme.get('ghost'),
        'updated': _now_text(now), 'user': user or ''})


def normalize_preset(data):
    """A clean preset dict, or ValueError with a sentence a toast can show."""
    if not isinstance(data, dict) or data.get('format') != PRESET_FORMAT:
        raise ValueError('That file is not a Playground color preset.')
    name = naming.sanitize(data.get('name') or '').strip()
    if not name:
        raise ValueError('The preset has no name.')
    prop = data.get('property') or {}
    category = str(prop.get('category') or '').strip()
    prop_name = str(prop.get('property') or '').strip()
    if not category or not prop_name:
        raise ValueError('The preset "%s" names no property.' % name)
    entries = []
    seen = set()
    for entry in data.get('entries') or []:
        if not isinstance(entry, dict):
            continue
        value = entry.get('value')
        hex_value = colors.parse_hex(entry.get('hex'))
        if value is None or hex_value is None or value in seen:
            continue
        seen.add(value)
        entries.append({'value': str(value), 'hex': hex_value})
    if not entries:
        raise ValueError('The preset "%s" has no colors.' % name)
    ghost = data.get('ghost')
    try:
        ghost = None if ghost is None else max(0.0, min(1.0, float(ghost)))
    except (TypeError, ValueError):
        ghost = None
    return {'format': PRESET_FORMAT, 'version': PRESET_VERSION, 'name': name,
            'property': {'category': category, 'property': prop_name}, 'entries': entries,
            'missing': colors.parse_hex(data.get('missing')),
            'other': colors.parse_hex(data.get('other')), 'ghost': ghost,
            'updated': str(data.get('updated') or ''), 'user': str(data.get('user') or '')}


def preset_file_name(name):
    """The file a preset lives in: its name made Windows-safe, '.json'."""
    return paths.safe_filename(name, max_len=80) + '.json'


def preset_row(preset):
    """ui table cells: name, property, value count, updated date."""
    prop = preset['property']
    return [preset['name'], property_label(prop['category'], prop['property']),
            len(preset['entries']), (preset.get('updated') or '')[:10]]


def is_numberish(text):
    return bool(re.match(r'^\s*[-+]?[\d,.\s]+\s*$', str(text))) and bool(re.search(r'\d', str(text)))


def search_friendly(values, limit=SEARCH_MAX_VALUES):
    """True when a native search per value can find these values: a handful of
    plain text values. Numbers are not (native matching compares the display
    text, which for a number carries units and rounding), nor is '(no value)'."""
    values = list(values)
    if not values or len(values) > limit:
        return False
    for value in values:
        text = str(value)
        if not text.strip() or text == NO_VALUE or is_numberish(text):
            return False
    return True


def preset_plan(preset, found, total=None):
    """The scheme and paint groups for a preset after its values were found.

    found: [(value, [items])] in preset order (items [] when nothing matched).
    Returns {'scheme', 'groups' [(items, hex, None)], 'missed' [values with no
    match], 'painted' count}."""
    entries = []
    kinds = []
    groups = []
    missed = []
    painted = 0
    colour = dict((e['value'], e['hex']) for e in preset['entries'])
    for value, members in found:
        count = len(members)
        if not count:
            missed.append(value)
        entries.append({'value': value, 'hex': colour.get(value), 'count': count})
        kinds.append('value')
        if count and colour.get(value):
            groups.append((members, colour[value], None))
            painted += count
    prop = preset['property']
    scheme = {'title': preset['name'], 'property': dict(prop), 'entries': entries, 'kinds': kinds,
              'ghost': preset.get('ghost'),
              'subtitle': '%s, preset' % property_label(prop['category'], prop['property']),
              'total': total if total is not None else painted}
    return {'scheme': scheme, 'groups': groups, 'missed': missed, 'painted': painted}


def missed_text(missed, limit=4):
    """'3 values had no match: A, B, C' (the first few named)."""
    if not missed:
        return ''
    names = ', '.join(str(m) for m in missed[:limit])
    if len(missed) > limit:
        names += ' and %s more' % count_text(len(missed) - limit)
    return '%s no match: %s.' % (plural(len(missed), 'value had', 'values had'), names)


# =============================================================================
# API half (Navisworks; lazy imports)
# =============================================================================


def _doc(doc):
    if doc is not None:
        return doc
    from pynavis._api import Application
    return Application.ActiveDocument


def visible_objects(roots, tick=None):
    """ItemList of distinct objects with at least one visible geometry item under
    roots. One native walk per root: DescendantsAndSelf is depth first, so the
    current branch is a stack and each item's hidden state is its parent's
    (popped to) plus its own flag; an item whose parent is not on the stack is
    climbed instead, so the answer is right in any order."""
    ticker = items.Ticker(tick)
    seen = set()
    out = items.ItemList()
    for root in items.as_list(roots):
        path = []
        for item in root.DescendantsAndSelf:
            ticker.step()
            parent = item.Parent
            while path and (parent is None or not path[-1][0].Equals(parent)):
                path.pop()
            if path:
                inherited = path[-1][1]
            else:
                inherited = parent is not None and not items.visible(parent)
            hidden = inherited or bool(item.IsHidden)
            path.append((item, hidden))
            if hidden or not item.HasGeometry:
                continue
            element = items.object_of(item)
            if element in seen:
                continue
            seen.add(element)
            out.append(element)
    ticker.finish()
    return out


def scope_objects(scope, doc=None, tick=None):
    """The objects a scope covers: 'selection' (objects under the selected
    items), 'visible' (visible_objects over every model) or 'model'."""
    document = _doc(doc)
    if scope == 'selection':
        return items.objects(items.selected(document), tick=tick)
    roots = items.roots(document)
    if scope == 'visible':
        return visible_objects(roots, tick=tick)
    return items.objects(roots, tick=tick)


def property_names(objects, limit=PROPERTY_SAMPLE):
    """([(category, property, count)], sampled_count) over an even sample."""
    sample = sample_evenly(objects, limit)
    return items.sample_properties(sample, limit=None), len(sample)


def read_groups(objects, category, prop, tick=None):
    """[(value_text, [objects])] ranked, reading the property on each object
    (missing reads '(no value)'). tick(done, total) every ~500; False cancels."""
    data = items.as_list(objects)
    ticker = items.Ticker(tick, total=len(data))
    texts = []
    for item in data:
        texts.append(items.value_text(items.prop(item, category, prop, fallback_to_object=False)))
        ticker.step()
    ticker.finish()
    return group_by_value(data, texts)


def paint_groups(groups_by_value, scheme):
    """[(items, hex, None)] for paint.apply from read_groups output and a
    plan_scheme scheme (Other rows collect every folded value's items)."""
    by_value = dict(groups_by_value)
    kinds = scheme.get('kinds') or []
    folded_hex = None
    named = set()
    out = []
    for entry, kind in zip(scheme.get('entries') or [], kinds):
        if kind == 'other':
            folded_hex = entry.get('hex')
            continue
        named.add(entry['value'])
        if entry.get('hex') and entry['value'] in by_value:
            out.append((by_value[entry['value']], entry['hex'], None))
    if folded_hex:
        rest = []
        for value, members in groups_by_value:
            if value not in named:
                rest.extend(members)
        if rest:
            out.append((rest, folded_hex, None))
    return out


def apply(groups, doc=None, reset_first=False, rest_hex=None, rest_transparency=None,
          name='Color by property', reset_items=None):
    """Paints [(items, hex, transparency)] in ONE undo step. reset_first clears
    permanent colours and transparency first: on reset_items when given (a
    selection being recoloured), else on the whole model. rest_hex / rest_transparency
    paint everything that was NOT painted (namo.items.complement of the painted
    items): grey for a preset's Other colour, a transparency to ghost the rest.
    Returns the items painted (the rest not counted)."""
    from namo import paint
    from pynavis.viewpoints import transaction
    document = _doc(doc)
    planned = paint.plan_groups(groups)
    with transaction(name, document):
        if reset_first and reset_items is not None:
            if reset_items:
                document.Models.ResetPermanentMaterials(items.collection(reset_items))
        elif reset_first:
            document.Models.ResetAllPermanentMaterials()
        painted = paint.apply(planned, document, name)
        if rest_hex is not None or rest_transparency is not None:
            keep = []
            for members, _hex, _t in planned:
                keep.extend(members)
            if keep:
                others = items.complement(keep, document)
                if others:
                    paint.apply([(others, rest_hex, rest_transparency)], document, name)
    if reset_first and reset_items is None:
        _forget_ghost(document)
    return painted


def _forget_ghost(document):
    """A whole-model reset also wiped what Trade Ghost faded: drop its record,
    or its next click would offer to clear a ghost that is no longer there."""
    try:
        from namo import look_ghost
        if look_ghost.load_record(document) is not None:
            look_ghost.save_record(None, document)
    except Exception:
        pass


def load_memory():
    from namo import store
    try:
        value = store.Store(MEMORY_STORE, scope='global').load({})
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def save_memory(memory):
    """Saves the colour memory; a failure is logged, never raised (the colours
    were painted, only next time's stability is at stake)."""
    from namo import session, store
    try:
        store.Store(MEMORY_STORE, scope='global').save(memory)
    except Exception as error:
        session.log('warning', 'could not save the color memory: %s' % error)


def show_legend(scheme):
    """Prints the legend into the output window."""
    from pynavis import output
    output.print_html(legend_html(scheme))


# ---- finding preset values ------------------------------------------------------


def find_by_search(category, prop, values, scope=None, doc=None, progress=None):
    """[(value, [items])] with one native search per value (pruned below a match,
    so a matched element does not bring its own parts). scope: items to search
    under, or None for the whole model. progress(fraction, label) per value."""
    from pynavis import sets
    document = _doc(doc)
    out = []
    for index, value in enumerate(values):
        if progress is not None:
            progress(float(index) / max(1, len(values)), 'Finding %s' % value)
        query = sets.query().prop(category, prop).equals(str(value)).ignore_case()
        found = sets.run(query, document, prune=True, scope=scope)
        out.append((value, list(found)))
    if progress is not None:
        progress(1.0, 'Found %s' % plural(len(values), 'value'))
    return out


def find_by_walk(category, prop, values, objects, tick=None):
    """[(value, [items])] by reading the property on every object (values that
    match case-insensitively and with spaces trimmed count)."""
    wanted = dict((str(v).strip().lower(), v) for v in values)
    found = dict((v, []) for v in values)
    data = items.as_list(objects)
    ticker = items.Ticker(tick, total=len(data))
    for item in data:
        text = items.value_text(items.prop(item, category, prop, fallback_to_object=False))
        key = text.strip().lower()
        if key in wanted:
            found[wanted[key]].append(item)
        ticker.step()
    ticker.finish()
    return [(v, found[v]) for v in values]


# ---- preset files -----------------------------------------------------------------


def presets_folder():
    """<team_root>\\presets\\colors (not created)."""
    return os.path.join(paths.team_root(), 'presets', 'colors')


def list_presets(folder=None):
    """Every readable preset, natural name order. Damaged files are skipped
    (logged); a file that is not a preset is ignored."""
    from namo import session
    folder = folder or presets_folder()
    if not os.path.isdir(folder):
        return []
    out = []
    for name in sorted(os.listdir(folder)):
        if not name.lower().endswith('.json'):
            continue
        path = os.path.join(folder, name)
        data = paths.load_json(path, None)
        try:
            preset = normalize_preset(data)
        except ValueError as error:
            session.log('warning', 'skipped color preset %s: %s' % (name, error))
            continue
        preset['path'] = path
        out.append(preset)
    out.sort(key=lambda p: naming.natural_key(p['name']))
    return out


def find_preset(name, folder=None):
    """The preset named `name` (case-insensitive), or None."""
    for preset in list_presets(folder):
        if preset['name'].lower() == str(name).strip().lower():
            return preset
    return None


def save_preset(preset, folder=None):
    """Writes a preset (replacing one of the same name). Returns its path.
    IOError when the folder cannot be written."""
    folder = folder or presets_folder()
    clean = normalize_preset(preset)
    existing = find_preset(clean['name'], folder)
    path = existing['path'] if existing else os.path.join(folder, preset_file_name(clean['name']))
    paths.ensure_dir(folder)
    paths.write_json(path, clean)
    return path


def delete_preset(name, folder=None):
    preset = find_preset(name, folder)
    if preset is None:
        return False
    try:
        os.remove(preset['path'])
    except OSError as error:
        raise IOError('Could not delete %s: %s' % (preset['path'], error))
    return True


def rename_preset(old, new, folder=None):
    """Renames a preset (file and name). ValueError for an empty or taken name."""
    folder = folder or presets_folder()
    preset = find_preset(old, folder)
    if preset is None:
        raise ValueError('There is no preset named "%s".' % old)
    new = naming.sanitize(new or '').strip()
    if not new:
        raise ValueError('A preset needs a name.')
    other = find_preset(new, folder)
    if other is not None and other['path'] != preset['path']:
        raise ValueError('A preset named "%s" already exists.' % other['name'])
    old_path = preset.pop('path')
    preset['name'] = new
    target = os.path.join(folder, preset_file_name(new))
    paths.write_json(target, normalize_preset(preset))
    if os.path.normcase(target) != os.path.normcase(old_path):
        try:
            os.remove(old_path)
        except OSError:
            pass
    return new


def export_preset(name, path, folder=None):
    preset = find_preset(name, folder)
    if preset is None:
        raise ValueError('There is no preset named "%s".' % name)
    paths.write_json(path, normalize_preset(preset))
    return path


def import_preset(path, folder=None):
    """Adds the preset in a file; a name already taken gets ' (2)'. Returns the
    stored name. ValueError (a sentence) for a file that is not a preset."""
    folder = folder or presets_folder()
    data = paths.load_json(path, None, move_aside=False)
    preset = normalize_preset(data)
    taken = [p['name'] for p in list_presets(folder)]
    preset['name'] = naming.unique(preset['name'], taken)
    save_preset(preset, folder)
    return preset['name']


# ---- the Manage presets window ----------------------------------------------------

MANAGE_HEADERS = ['Preset', 'Property', 'Values', 'Updated']
PRESET_FILTER = 'Playground color preset (*.json)|*.json'


def manage_rows(presets):
    return [{'value': p['name'], 'cells': preset_row(p)} for p in presets]


def build_manage_window(folder=None):
    """The Manage presets window (namo.ui table, unshown): Rename, Delete,
    Export, Import and Open folder. Every action refreshes the list and says
    what it did on the status line."""
    from namo import ui
    folder = folder or presets_folder()
    holder = {}

    def refresh(status):
        holder['win'].Tag.update(manage_rows(list_presets(folder)), status)

    def rename(selected):
        from pynavis import forms, toast
        if len(selected) != 1:
            toast.info('Pick one preset to rename')
            return
        old = selected[0]
        new = forms.ask_string('New name for "%s":' % old, default=old, title='Rename preset')
        if new is None:
            return
        try:
            final = rename_preset(old, new, folder)
        except ValueError as error:
            toast.error('Could not rename the preset', str(error))
            return
        refresh('Renamed "%s" to "%s".' % (old, final))

    def delete(selected):
        from pynavis import forms
        names = list(selected)
        what = '"%s"' % names[0] if len(names) == 1 else plural(len(names), 'preset')
        if not forms.confirm('Delete %s? Everyone who shares this folder loses it too.' % what,
                             title='Delete presets'):
            return
        for name in names:
            delete_preset(name, folder)
        refresh('Deleted %s.' % what)

    def export(selected):
        from pynavis import forms
        names = list(selected)
        if len(names) == 1:
            path = forms.save_file(filter=PRESET_FILTER, default_name=preset_file_name(names[0]),
                                   title='Export preset')
            if path is None:
                return
            export_preset(names[0], path, folder)
            refresh('Exported "%s" to %s.' % (names[0], path))
            return
        target = forms.pick_folder(title='Export presets to')
        if target is None:
            return
        for name in names:
            export_preset(name, os.path.join(target, preset_file_name(name)), folder)
        refresh('Exported %s to %s.' % (plural(len(names), 'preset'), target))

    def import_file(selected):
        from pynavis import forms, toast
        path = forms.open_file(filter=PRESET_FILTER, title='Import preset')
        if path is None:
            return
        try:
            name = import_preset(path, folder)
        except ValueError as error:
            toast.error('Could not import the preset', str(error))
            return
        refresh('Imported "%s".' % name)

    def open_folder(selected):
        paths.ensure_dir(folder)
        ui.show_in_explorer(folder)

    actions = [('Rename', rename), ('Delete', delete), ('Export', export),
               ('Import', import_file, False), ('Open folder', open_folder, False)]
    status = 'Shared with the team: %s' % folder if paths.team_available() else 'Folder: %s' % folder
    win = ui.build_table('Color presets', MANAGE_HEADERS, manage_rows(list_presets(folder)),
                         actions=actions, status=status, width=760, height=460)
    holder['win'] = win
    return win
