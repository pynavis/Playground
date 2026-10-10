"""Applies, saves and manages named color presets kept in the team's preset folder."""
from namo import colorize, config, paint, progress, session, ui
from pynavis import doc as nwdoc
from pynavis import forms, script, toast

TITLE = 'Color Presets'
APPLY = 'Apply a preset'
SAVE = 'Save the last scheme'
MANAGE = 'Manage presets'
DEFAULTS = {'last': ''}


def find_values(document, preset):
    """[(value, [items])] for the preset's values: a native search per value when
    they are plain text, else (or when the searches find nothing at all) one
    walk over the model reading the property."""
    category = preset['property']['category']
    prop = preset['property']['property']
    values = [entry['value'] for entry in preset['entries']]
    if colorize.search_friendly(values):
        found = progress.run(TITLE, lambda report: colorize.find_by_search(
            category, prop, values, None, document, report))
        if found is progress.CANCELLED:
            return found
        if any(members for _value, members in found):
            session.log('info', 'color preset %s: found by native search' % preset['name'])
            return found
        session.log('info', 'color preset %s: searches found nothing, walking the model' % preset['name'])

    def walk(report):
        objects = colorize.scope_objects('model', document, tick=colorize.counting(report, 'Collecting items:'))
        return colorize.find_by_walk(category, prop, values, objects,
                                     tick=colorize.counting(report, 'Reading %s:' % prop))
    return progress.run(TITLE, walk)


def apply_preset(document, cfg):
    presets = colorize.list_presets()
    if not presets:
        toast.info('No presets yet', 'Color the model with Color by Property, then save the scheme here.')
        return
    rows = [{'value': p['name'], 'cells': colorize.preset_row(p)} for p in presets]
    picked = ui.choose('Apply a color preset', rows, colorize.MANAGE_HEADERS, multiselect=False,
                       checked=[cfg['last']] if cfg.get('last') else None, ok='Apply',
                       prompt='Colors from the preset replace the colors on the model now.')
    if picked is None:
        return
    preset = [p for p in presets if p['name'] == picked[0]][0]
    cfg['last'] = preset['name']
    script.save_config(cfg)
    found = find_values(document, preset)
    if found is progress.CANCELLED:
        return
    plan = colorize.preset_plan(preset, found)
    prop = preset['property']
    label = colorize.property_label(prop['category'], prop['property'])
    if not plan['painted']:
        toast.warning('Nothing matched "%s"' % preset['name'],
                      'No item carries any of its %s of %s. The model colors are unchanged.'
                      % (colorize.plural(len(preset['entries']), 'value'), label))
        return
    painted = colorize.apply(plan['groups'], document, reset_first=True, rest_hex=preset.get('other'),
                             rest_transparency=preset.get('ghost'), name='Apply color preset')
    try:
        paint.remember_scheme(plan['scheme'])
    except Exception as error:
        session.log('warning', 'color scheme not remembered for Legend Maker: %s' % error)
    colorize.show_legend(plan['scheme'])
    detail = 'Colored %s by %s.' % (colorize.plural(painted, 'item'), label)
    if plan['missed']:
        detail += ' ' + colorize.missed_text(plan['missed'])
        toast.warning('Applied "%s"' % preset['name'], detail)
    else:
        toast.success('Applied "%s"' % preset['name'], detail)


def save_scheme():
    scheme = paint.last_scheme()
    if not scheme or not colorize.value_pairs(scheme):
        toast.info('No color scheme yet', 'Run Color by Property or Status Painter first, then save it here.')
        return
    name = forms.ask_string('Name the preset:', default=scheme.get('title') or '', title='Save color preset')
    if name is None:
        return
    if not name.strip():
        toast.error('The preset needs a name', 'Click Color Presets again and type one.')
        return
    existing = colorize.find_preset(name)
    if existing is not None and not forms.confirm('Replace the preset "%s"?' % existing['name'],
                                                  title='Save color preset'):
        return
    try:
        preset = colorize.preset_from_scheme(scheme, name.strip(), user=config.user_name())
        path = colorize.save_preset(preset)
    except ValueError as error:
        toast.error('Could not save the preset', str(error))
        return
    except (IOError, OSError) as error:
        toast.error('Could not save the preset', str(error))
        return
    prop = preset['property']
    toast.success('Saved preset "%s"' % preset['name'], '%s of %s, in %s' % (
        colorize.plural(len(preset['entries']), 'value'),
        colorize.property_label(prop['category'], prop['property']), path))


def run():
    cfg = script.get_config(DEFAULTS)
    action = forms.ask_options(None, [APPLY, SAVE, MANAGE], title=TITLE)
    if action == APPLY:
        document = nwdoc.get_doc()
        if document.Models.Count == 0:
            toast.info('No model open', 'Open or append a model, then apply the preset.')
            return
        apply_preset(document, cfg)
    elif action == SAVE:
        save_scheme()
    elif action == MANAGE:
        ui.show_modal(colorize.build_manage_window())


run()
