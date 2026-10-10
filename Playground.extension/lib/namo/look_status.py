# -*- coding: utf-8 -*-
"""Status Painter: construction status kept in a property, painted as colour.

The status lives in one property, by default the custom tab 'Playground' >
'Status' that Set status writes (merged into whatever else that tab holds:
pynavis.props.set_custom replaces a whole tab, so the tab is read first and
written back with the new value). Any other property can be the source
instead (a Revit 'Phase' or a status parameter); then the tool paints from it
but will not write to it, because a Revit tab is read-only and a custom tab of
the same name would only shadow it.

Statuses are an ordered list of [name, hex or None]; None means "leave the
model colour" (Not started by default). Values match a status ignoring case
and surrounding spaces; anything else is reported, never painted.

The pure half is tested on both engines; the API half lazy-imports pynavis.
"""

from namo import colors, colorize, naming

DEFAULT_TAB = 'Playground'
DEFAULT_PROPERTY = 'Status'
USER_TAB_NAME = 'LcOaPropOverrideCat'      # internal Name of a user-defined tab

DEFAULT_STATUSES = [
    ['Installed', '59A14F'],
    ['In progress', 'F1A340'],
    ['Planned', 'A3A9B2'],
    ['On hold', 'B07AA1'],
    ['Issue', 'E15759'],
    ['Not started', None],
]

DEFAULTS = {'category': DEFAULT_TAB, 'property': DEFAULT_PROPERTY,
            'statuses': [list(s) for s in DEFAULT_STATUSES]}

CLEAR = 'Clear status'
CHUNK = 250
ACTIONS = ['Paint by status', 'Set status of selection', 'Legend']


# =============================================================================
# Pure half
# =============================================================================


def normalize_config(cfg):
    """{'category', 'property', 'statuses': [[name, hex or None]]} with blanks
    filled from DEFAULTS, names trimmed and deduplicated (case-insensitive),
    colours parsed (a bad colour leaves that status unpainted)."""
    cfg = cfg or {}
    category = str(cfg.get('category') or '').strip() or DEFAULT_TAB
    prop = str(cfg.get('property') or '').strip() or DEFAULT_PROPERTY
    statuses = []
    seen = set()
    for entry in cfg.get('statuses') or DEFAULTS['statuses']:
        if not isinstance(entry, (list, tuple)) or not entry:
            continue
        name = naming.sanitize(entry[0] or '').strip()
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        hex_value = colors.parse_hex(entry[1]) if len(entry) > 1 else None
        statuses.append([name, hex_value])
    if not statuses:
        statuses = [list(s) for s in DEFAULT_STATUSES]
    return {'category': category, 'property': prop, 'statuses': statuses}


def is_default_source(cfg):
    return cfg['category'] == DEFAULT_TAB and cfg['property'] == DEFAULT_PROPERTY


def match_status(value, statuses):
    """The status name a property value stands for (ignoring case and spaces),
    or None."""
    if value is None:
        return None
    wanted = ' '.join(str(value).split()).lower()
    for name, _hex in statuses:
        if ' '.join(name.split()).lower() == wanted:
            return name
    return None


def plan_paint(groups, statuses):
    """What Paint by status does with [(value_text, [items])].

    Returns {'groups': [(items, hex, None)] for painted statuses, 'reset':
    [items] whose status leaves the model colour, 'counts': [(name, count)] in
    status order, 'unknown': [(value, count)] for values that are no status}."""
    by_name = dict((name, []) for name, _hex in statuses)
    unknown = []
    for value, members in groups:
        name = match_status(value, statuses)
        if name is None:
            if value != colorize.NO_VALUE:
                unknown.append((value, len(members)))
            continue
        by_name[name].extend(members)
    paint = []
    reset = []
    for name, hex_value in statuses:
        if not by_name[name]:
            continue
        if hex_value:
            paint.append((by_name[name], hex_value, None))
        else:
            reset.extend(by_name[name])
    counts = [(name, len(by_name[name])) for name, _hex in statuses]
    return {'groups': paint, 'reset': reset, 'counts': counts, 'unknown': unknown}


def status_scheme(cfg, counts, unknown=()):
    """A scheme (colorize shape) for the legend: one row per status in order,
    plus an unchanged Other row for values that are no status."""
    count_of = dict(counts)
    entries = []
    kinds = []
    for name, hex_value in cfg['statuses']:
        entries.append({'value': name, 'hex': hex_value, 'count': int(count_of.get(name, 0))})
        kinds.append('value')
    if unknown:
        entries.append({'value': 'Other (%s)' % colorize.plural(len(unknown), 'value'), 'hex': None,
                        'count': sum(c for _v, c in unknown)})
        kinds.append('other')
    label = colorize.property_label(cfg['category'], cfg['property'])
    return {'title': 'Construction status', 'property': {'category': cfg['category'],
                                                         'property': cfg['property']},
            'entries': entries, 'kinds': kinds, 'ghost': None, 'subtitle': label,
            'total': sum(e['count'] for e in entries)}


def counts_detail(counts, unknown=()):
    """'Installed 1,200, In progress 300' (statuses with items only), plus
    the values that are no status."""
    parts = ['%s %s' % (name, colorize.count_text(n)) for name, n in counts if n]
    text = ', '.join(parts) if parts else 'No item carries a known status'
    if unknown:
        names = ', '.join('"%s"' % v for v, _c in unknown[:3])
        more = ' and %s more' % colorize.count_text(len(unknown) - 3) if len(unknown) > 3 else ''
        text += '. Not a status: %s%s' % (names, more)
    return text + '.'


def clean_value(value):
    """A value set_custom accepts (str/int/float/bool); anything else as text."""
    if isinstance(value, (bool, int, float)) or value is None:
        return '' if value is None else value
    return str(value)


def merge_tab(existing, prop, value):
    """The tab's new {name: value} after setting prop to value (value None
    removes prop). Every other property on the tab is kept."""
    out = {}
    for key in sorted(existing or {}):
        out[key] = clean_value(existing[key])
    if value is None:
        out.pop(prop, None)
    else:
        out[prop] = value
    return out


def group_writes(current, prop, value):
    """[(new_tab_dict, [members])] for [(member, existing_tab_or_None)], one
    group per distinct resulting tab, in first-seen order. A {} tab means the
    tab is to be removed."""
    groups = []
    index = {}
    for member, existing in current:
        tab = merge_tab(existing, prop, value)
        key = tuple((k, repr(tab[k])) for k in sorted(tab))
        if key not in index:
            index[key] = len(groups)
            groups.append((tab, []))
        groups[index[key]][1].append(member)
    return groups


def status_options(cfg):
    """The Set status list: every status, then Clear status."""
    return [name for name, _hex in cfg['statuses']] + [CLEAR]


def parse_extra(text):
    """([[name, hex]], [problem sentences]) from 'Name = RRGGBB' lines."""
    statuses = []
    problems = []
    for number, line in enumerate((text or '').splitlines()):
        line = line.strip()
        if not line:
            continue
        if '=' not in line:
            problems.append('Line %d needs a name, "=" and a color.' % (number + 1))
            continue
        name, hex_text = line.rsplit('=', 1)
        name = name.strip()
        hex_value = colors.parse_hex(hex_text)
        if not name:
            problems.append('Line %d has no name.' % (number + 1))
        elif hex_value is None:
            problems.append('Line %d: "%s" is not a color like 4E79A7.' % (number + 1, hex_text.strip()))
        else:
            statuses.append([name, hex_value])
    return statuses, problems


def config_fields(cfg):
    """The Status Painter settings form (namo.ui fields)."""
    defaults = dict((n, h) for n, h in DEFAULT_STATUSES)
    fields = [
        {'kind': 'label', 'text': 'Where the status is stored. Set status writes only to a custom tab.'},
        {'kind': 'text', 'key': 'category', 'label': 'Tab', 'default': cfg['category'], 'required': True},
        {'kind': 'text', 'key': 'property', 'label': 'Property', 'default': cfg['property'],
         'required': True},
        {'kind': 'separator'},
        {'kind': 'label', 'text': 'Colors. A status that is not painted keeps the model colors.'},
    ]
    current = dict((n, h) for n, h in cfg['statuses'])
    for index, (name, fallback) in enumerate(DEFAULT_STATUSES):
        hex_value = current.get(name, fallback) if name in current else fallback
        fields.append({'kind': 'check', 'key': 'on%d' % index, 'label': 'Paint %s' % name,
                       'default': bool(hex_value)})
        fields.append({'kind': 'color', 'key': 'hex%d' % index, 'label': name,
                       'default': hex_value or defaults.get(name) or colors.GHOST,
                       'enabled_if': ('on%d' % index, True)})
    extra = [s for s in cfg['statuses'] if s[0] not in defaults]
    fields.append({'kind': 'textarea', 'key': 'extra', 'label': 'More statuses', 'rows': 3,
                   'default': '\n'.join('%s = %s' % (n, h or '') for n, h in extra),
                   'placeholder': 'Delivered = 4E79A7',
                   'validate': lambda text: (parse_extra(text)[1] or [None])[0]})
    return fields


def config_from_form(values):
    """The config dict from config_fields' answers."""
    statuses = []
    for index, (name, _fallback) in enumerate(DEFAULT_STATUSES):
        statuses.append([name, values.get('hex%d' % index) if values.get('on%d' % index) else None])
    extra, _problems = parse_extra(values.get('extra') or '')
    statuses.extend(extra)
    return normalize_config({'category': values.get('category'), 'property': values.get('property'),
                             'statuses': statuses})


# =============================================================================
# API half
# =============================================================================


def _doc(doc):
    if doc is not None:
        return doc
    from pynavis._api import Application
    return Application.ActiveDocument


def find_items(cfg, doc=None):
    """Every topmost item carrying the status property (one native search,
    pruned below a match)."""
    from pynavis import sets
    query = sets.query().prop(cfg['category'], cfg['property']).exists()
    return list(sets.run(query, _doc(doc), prune=True))


def user_tab_name():
    """The internal Name every user-defined tab carries
    (LcOaPropOverrideCategory.GetInternalCatName), USER_TAB_NAME when the
    Interop call refuses."""
    try:
        from pynavis._api import Api  # noqa: F401  (loads the API assembly)
        from Autodesk.Navisworks.Api.Interop import LcOaPropOverrideCategory
        return str(LcOaPropOverrideCategory.GetInternalCatName()) or USER_TAB_NAME
    except Exception:
        return USER_TAB_NAME


def writable_problem(cfg, targets, user_name=None):
    """A sentence when Set status may not write cfg's property on targets: the
    tab exists there as a tab Navisworks or Revit made (not a custom tab)."""
    user_name = user_name or user_tab_name()
    # pyNavis' COM writer (pynavis._com.set_custom_tab) creates user tabs with the
    # internal name 'pyNavis', so a tab this tool wrote itself must count as custom too.
    custom_names = (user_name, 'pyNavis')
    for item in targets[:50]:
        try:
            for category in item.PropertyCategories:
                if category.DisplayName != cfg['category']:
                    continue
                try:
                    editable = bool(category.IsEditable)
                except Exception:
                    editable = False
                if not editable and category.Name not in custom_names:
                    return ('%s is a tab from the model, so Set status cannot write to it. '
                            'Shift+Click Status Painter to keep the status in a custom tab.'
                            % cfg['category'])
        except Exception:
            continue
    return None


def chunks(groups, size=None):
    """[(tab, members)] cut into pieces of at most `size` members, so a long
    write can stop between pieces."""
    size = size or CHUNK
    out = []
    for tab, members in groups:
        for start in range(0, len(members), size):
            out.append((tab, members[start:start + size]))
    return out


def set_status(targets, cfg, status, doc=None, progress=None):
    """Writes status (None clears it) into cfg's custom tab on every target,
    merging with the tab's other properties, then paints them with the
    status colour (or puts their model colour back). ONE transaction.

    progress(fraction, label) is called between pieces of CHUNK items; when it
    raises a Cancelled the write stops there and what was written so far is
    painted and kept (Ctrl+Z undoes it). Returns (written, errors, stopped)."""
    from namo import paint
    from pynavis import props
    from pynavis.viewpoints import transaction
    document = _doc(doc)
    current = []
    for item in targets:
        try:
            existing = props.get_custom(item, cfg['category'])
        except Exception:
            existing = None
        current.append((item, existing))
    written = 0
    errors = []
    done = []
    stopped = False
    hex_value = None
    if status is not None:
        hex_value = dict((n, h) for n, h in cfg['statuses']).get(status)
    pieces = chunks(group_writes(current, cfg['property'], status))
    try:
        with transaction('Set status', document):
            for index, (tab, members) in enumerate(pieces):
                if progress is not None and len(pieces) > 1:
                    try:
                        progress(float(index) / len(pieces), 'Writing %s of %s' % (
                            colorize.count_text(len(done)), colorize.count_text(len(targets))))
                    except Exception as error:
                        if type(error).__name__ != 'Cancelled':
                            raise
                        stopped = True
                        break
                if tab:
                    count, problems = props.set_custom(members, cfg['category'], tab, document)
                else:
                    count, problems = props.remove_custom(members, cfg['category'], document)
                written += count
                errors.extend(problems)
                done.extend(members)
            if done:
                if hex_value:
                    paint.apply([(done, hex_value, None)], document, 'Set status')
                else:
                    paint.reset(done, document, 'Set status')
    finally:
        # A custom tab changed: Property Explorer's cached scan must not show the old
        # status (the namo README rule for every custom-property writer).
        try:
            from namo import propindex
            propindex.invalidate()
        except Exception:
            pass
    return written, errors, stopped


def paint(cfg, groups, doc=None):
    """Paints a plan_paint() plan in ONE transaction: statuses with a colour
    get it, statuses without one get their model colours back. Returns the
    item count touched."""
    from namo import paint as _paint
    from pynavis.viewpoints import transaction
    document = _doc(doc)
    plan = plan_paint(groups, cfg['statuses'])
    touched = 0
    with transaction('Paint by status', document):
        if plan['groups']:
            touched += _paint.apply(plan['groups'], document, 'Paint by status')
        if plan['reset']:
            touched += _paint.reset(plan['reset'], document, 'Paint by status')
    return touched, plan
