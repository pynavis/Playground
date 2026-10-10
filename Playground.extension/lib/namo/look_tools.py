# -*- coding: utf-8 -*-
"""The small Look tools: Match Appearance, Reset All Overrides and Background.

Match Appearance reads what an item really looks like. Overrides are read
from Navisworks' own snapshot of them: DocumentSavedViewpoints.
CaptureRuntimeOverrides() returns a detached SavedViewpoint whose
GetAppearanceOverrides().MaterialOverrides lists every overridden item with
its Color and Transparency (Nullable). An override set on an ancestor applies
to the item too, so colour and transparency are each taken from the nearest
level that overrides them. What no override covers comes from the item's
first geometry (ModelGeometry.ActiveColor / ActiveTransparency, through
namo.paint.read_color). Both reads are UNVERIFIED in-app (see the notes).

Background presets are applied with Document.SetPlainBackground /
SetGraduatedBackground / SetHorizonBackground. The current background is read
through the Interop layer (LcOpState.GetActiveInstance, LcOpBackgroundElement
.Get(state).GetSettings()): best effort, None when that refuses, so cycling
falls back to the last preset this session set.

The pure half is tested on both engines; the API half lazy-imports pynavis.
"""

from namo import colors

# ---- Reset All Overrides -------------------------------------------------------

RESET_KINDS = [
    ('materials', 'Colors and transparency'),
    ('temporary', 'Temporary colors'),
    ('hidden', 'Hidden items'),
    ('transforms', 'Moved and rotated items (includes deliberate moves)'),
    ('flags', 'Required and frozen flags'),
]
RESET_DEFAULT = ['materials', 'temporary', 'hidden']
RESET_SHORT = {'materials': 'colors and transparency', 'temporary': 'temporary colors',
               'hidden': 'hidden items', 'transforms': 'moved items',
               'flags': 'required and frozen flags'}

# ---- Background ------------------------------------------------------------------

BACKGROUNDS = [
    {'name': 'White', 'style': 'plain', 'colors': ['FFFFFF']},
    {'name': 'Light gradient', 'style': 'graduated', 'colors': ['FFFFFF', 'C9D1DB']},
    {'name': 'Dark gradient', 'style': 'graduated', 'colors': ['3C4352', '121519']},
    {'name': 'Black', 'style': 'plain', 'colors': ['000000']},
    {'name': 'Horizon', 'style': 'horizon', 'colors': ['5C8DC9', 'D4E3F2', 'BAB5AB', '6E695F']},
]
STYLE_COLORS = {'plain': 1, 'graduated': 2, 'horizon': 4}
CUSTOM_PLAIN = 'Custom color'
CUSTOM_GRADIENT = 'Custom gradient'


# =============================================================================
# Pure half
# =============================================================================


def normalize_kinds(kinds):
    """Known reset kinds, in RESET_KINDS order."""
    wanted = set(kinds or [])
    return [key for key, _label in RESET_KINDS if key in wanted]


def reset_fields(defaults):
    chosen = normalize_kinds(defaults) or list(RESET_DEFAULT)
    return [{'kind': 'multi', 'key': 'kinds', 'label': 'Reset',
             'options': [(label, key) for key, label in RESET_KINDS], 'default': chosen,
             'validate': lambda value: None if value else 'Tick at least one thing to reset.'}]


def reset_summary(kinds):
    """'Reset colors and transparency, hidden items and moved items'."""
    names = [RESET_SHORT[k] for k in normalize_kinds(kinds)]
    if not names:
        return 'Nothing reset'
    if len(names) == 1:
        return 'Reset ' + names[0]
    return 'Reset %s and %s' % (', '.join(names[:-1]), names[-1])


def nearest_override(chain):
    """(hex or None, transparency or None) from overrides along an item's
    chain, item first then each ancestor: [(hex or None, transparency or
    None) or None]. Colour and transparency each come from the nearest level
    that sets them."""
    hex_value = None
    transparency = None
    for level in chain:
        if level is None:
            continue
        if hex_value is None and level[0]:
            hex_value = colors.parse_hex(level[0])
        if transparency is None and level[1] is not None:
            transparency = max(0.0, min(1.0, float(level[1])))
        if hex_value is not None and transparency is not None:
            break
    return hex_value, transparency


def merge_appearance(override, model):
    """(hex, transparency, how): override parts win, model parts fill the gaps.
    how is 'override' when any part came from an override, 'model' when all
    of it is the model's own look, None when nothing is known."""
    o_hex, o_t = override
    m_hex, m_t = model
    hex_value = o_hex or m_hex
    transparency = o_t if o_t is not None else m_t
    if o_hex or o_t is not None:
        how = 'override'
    elif hex_value is not None or transparency is not None:
        how = 'model'
    else:
        how = None
    return hex_value, transparency, how


def appearance_text(hex_value, transparency):
    """'#4E79A7, 30% transparent' / '#4E79A7' / '30% transparent'."""
    parts = []
    if hex_value:
        parts.append('#' + hex_value)
    if transparency:
        parts.append('%d%% transparent' % int(round(transparency * 100)))
    elif transparency is not None and hex_value is None:
        parts.append('opaque')
    return ', '.join(parts) or 'unknown'


def look_detail(look, how):
    """The toast detail after painting: the look and where it was read from,
    so a wrong read shows. how: 'override', 'model', 'chosen' or None."""
    source = {'override': 'its color override', 'model': 'its own model color'}.get(how)
    if source is None:
        return '%s.' % look
    return '%s, read from %s.' % (look, source)


def click_prompt(look, painted, note=''):
    """The banner prompt of Match Appearance's click loop. note says why the
    last click painted nothing."""
    if painted:
        text = 'Click the next object (%s painted)' % '{:,}'.format(int(painted))
    else:
        text = 'Click an object to paint it %s' % look
    return ('%s %s' % (note, text)) if note else text


def match_fields(name, hex_value, transparency):
    """The form shown when the source's look could not be read in full."""
    return [
        {'kind': 'label', 'text': 'Navisworks did not report how %s looks. Choose the look to '
                                  'paint with.' % name},
        {'kind': 'color', 'key': 'hex', 'label': 'Color', 'default': hex_value or colors.GHOST,
         'required': True},
        {'kind': 'int', 'key': 'transparency', 'label': 'Transparency', 'min': 0, 'max': 100,
         'suffix': '%', 'default': int(round((transparency or 0.0) * 100)), 'required': True},
    ]


def background_named(name):
    for spec in BACKGROUNDS:
        if spec['name'].lower() == str(name or '').strip().lower():
            return dict(spec, colors=list(spec['colors']))
    return None


def normalize_background(spec):
    """A background dict with the right number of parsed colours, or None."""
    if not isinstance(spec, dict):
        return None
    style = spec.get('style')
    if style not in STYLE_COLORS:
        return None
    parsed = [colors.parse_hex(c) for c in (spec.get('colors') or [])]
    if len(parsed) != STYLE_COLORS[style] or None in parsed:
        return None
    return {'name': str(spec.get('name') or 'Custom'), 'style': style, 'colors': parsed}


def match_background(spec, tolerance=6.0):
    """The preset index a background (as read back) matches, or None. Colours
    within `tolerance` RGB distance count as equal (read-back rounding)."""
    spec = normalize_background(spec)
    if spec is None:
        return None
    for index, preset in enumerate(BACKGROUNDS):
        if preset['style'] != spec['style']:
            continue
        if all(colors.distance(a, b) <= tolerance for a, b in zip(preset['colors'], spec['colors'])):
            return index
    return None


def next_background(current_index):
    """The preset after current_index (None or unknown starts at the first)."""
    if current_index is None or not 0 <= current_index < len(BACKGROUNDS):
        return 0
    return (current_index + 1) % len(BACKGROUNDS)


def background_fields(defaults):
    """Shift+Click Background: a preset or a custom colour pair."""
    options = [spec['name'] for spec in BACKGROUNDS] + [CUSTOM_PLAIN, CUSTOM_GRADIENT]
    choice = defaults.get('choice') if defaults.get('choice') in options else BACKGROUNDS[0]['name']
    return [
        {'kind': 'radio', 'key': 'choice', 'label': 'Background', 'options': options, 'default': choice, 'fallback': None},
        {'kind': 'color', 'key': 'top', 'label': 'Color (top of a gradient)',
         'default': defaults.get('top') or 'FFFFFF',
         'enabled_if': ('choice', [CUSTOM_PLAIN, CUSTOM_GRADIENT])},
        {'kind': 'color', 'key': 'bottom', 'label': 'Bottom of the gradient',
         'default': defaults.get('bottom') or 'C9D1DB', 'enabled_if': ('choice', CUSTOM_GRADIENT)},
    ]


def background_from_form(values):
    choice = values.get('choice')
    if choice == CUSTOM_PLAIN:
        return normalize_background({'name': CUSTOM_PLAIN, 'style': 'plain',
                                     'colors': [values.get('top')]})
    if choice == CUSTOM_GRADIENT:
        return normalize_background({'name': CUSTOM_GRADIENT, 'style': 'graduated',
                                     'colors': [values.get('top'), values.get('bottom')]})
    return background_named(choice)


# =============================================================================
# API half
# =============================================================================


def _doc(doc):
    if doc is not None:
        return doc
    from pynavis._api import Application
    return Application.ActiveDocument


def _chain(item):
    out = []
    node = item
    while node is not None:
        out.append(node)
        node = node.Parent
    return out


def _overrides_on(document, nodes):
    """[(hex or None, transparency or None) or None] parallel to nodes: the
    permanent override each node carries itself, from CaptureRuntimeOverrides.
    All None when nothing is overridden or the snapshot refuses. Only the
    wanted nodes are kept: after Color by Property the snapshot lists every
    coloured object."""
    found = {}
    try:
        snapshot = document.SavedViewpoints.CaptureRuntimeOverrides()
        if snapshot is not None and snapshot.ContainsAppearanceOverrides:
            wanted = set(nodes)
            for override in snapshot.GetAppearanceOverrides().MaterialOverrides:
                item = override.Item
                if item is None or item not in wanted:
                    continue
                hex_value = None
                try:
                    color = override.Color
                    if color is not None:
                        hex_value = colors.from_rgb01(color.R, color.G, color.B)
                except Exception:
                    hex_value = None
                transparency = None
                try:
                    value = override.Transparency
                    if value is not None:
                        transparency = float(value)
                except Exception:
                    transparency = None
                found[item] = (hex_value, transparency)
    except Exception as error:
        found = {}
        try:
            from namo import session
            session.log('warning', 'match appearance: overrides not read: %s' % error)
        except Exception:
            pass
    return [found.get(node) for node in nodes]


def read_appearance(item, doc=None):
    """(hex, transparency, how) the item is drawn with (see the module
    docstring); how is 'override', 'model' or None."""
    from namo import paint
    document = _doc(doc)
    chain = _overrides_on(document, _chain(item))
    return merge_appearance(nearest_override(chain), paint.read_color(item))


def paint_like(targets, hex_value, transparency, doc=None, name='Match appearance'):
    """Paints targets with the colour and transparency (either may be None),
    one undo step. Returns the count."""
    from namo import paint
    return paint.apply([(targets, hex_value, transparency)], _doc(doc), name)


def reset(kinds, doc=None):
    """Resets the chosen kinds of override in ONE transaction. Returns the
    kinds reset (RESET_KINDS order)."""
    from pynavis.viewpoints import transaction
    document = _doc(doc)
    chosen = normalize_kinds(kinds)
    models = document.Models
    with transaction('Reset overrides', document):
        if 'materials' in chosen:
            models.ResetAllPermanentMaterials()
        if 'temporary' in chosen:
            models.ResetAllTemporaryMaterials()
        if 'hidden' in chosen:
            models.ResetAllHidden()
        if 'transforms' in chosen:
            models.ResetAllPermanentTransforms()
        if 'flags' in chosen:
            models.ResetAllRequired()
            models.ResetAllFrozen()
    return chosen


def read_background(doc=None):
    """The current background as {'style', 'colors'}, or None when the
    Interop read refuses (best effort, UNVERIFIED in-app)."""
    try:
        from pynavis._api import Api  # noqa: F401  (loads the API assembly)
        from Autodesk.Navisworks.Api.Interop import (LcOpBackgroundBackgroundStyle,
                                                     LcOpBackgroundColorIndex,
                                                     LcOpBackgroundElement, LcOpState)
        state = LcOpState.GetActiveInstance()
        settings = LcOpBackgroundElement.Get(state).GetSettings()
        style = settings.GetStyle()
        if style == LcOpBackgroundBackgroundStyle.eSTYLE_PLAIN:
            indexes, name = [LcOpBackgroundColorIndex.ePLAIN_COLOR], 'plain'
        elif style == LcOpBackgroundBackgroundStyle.eSTYLE_GRADUATED:
            indexes = [LcOpBackgroundColorIndex.eGRADUATED_COLOR_1,
                       LcOpBackgroundColorIndex.eGRADUATED_COLOR_2]
            name = 'graduated'
        elif style == LcOpBackgroundBackgroundStyle.eSTYLE_HORIZON:
            indexes = [LcOpBackgroundColorIndex.eHORIZON_COLOR_1,
                       LcOpBackgroundColorIndex.eHORIZON_COLOR_2,
                       LcOpBackgroundColorIndex.eHORIZON_COLOR_3,
                       LcOpBackgroundColorIndex.eHORIZON_COLOR_4]
            name = 'horizon'
        else:
            return None
        values = []
        for index in indexes:
            color = settings.GetColor(index)
            values.append(colors.from_rgb01(color.R, color.G, color.B))
        return normalize_background({'name': 'Current', 'style': name, 'colors': values})
    except Exception:
        return None


def set_background(spec, doc=None):
    """Applies a background dict (normalize_background shape)."""
    from namo import paint
    spec = normalize_background(spec)
    if spec is None:
        raise ValueError('That is not a background Navisworks can show.')
    document = _doc(doc)
    c = [paint.nw_color(h) for h in spec['colors']]
    if spec['style'] == 'plain':
        document.SetPlainBackground(c[0])
    elif spec['style'] == 'graduated':
        document.SetGraduatedBackground(c[0], c[1])
    else:
        document.SetHorizonBackground(c[0], c[1], c[2], c[3])
    return spec


def current_background_index(doc=None):
    """The preset showing now: read back when possible, else the last one this
    session set, else None."""
    from namo import session
    index = match_background(read_background(doc))
    if index is not None:
        return index
    return session.get(HOLDER_BACKGROUND, 'index')


HOLDER_BACKGROUND = 'look_background'


def remember_background(index):
    from namo import session
    session.set(HOLDER_BACKGROUND, 'index', index)
