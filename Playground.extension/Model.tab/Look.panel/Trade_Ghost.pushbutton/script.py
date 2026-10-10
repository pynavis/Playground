"""Keeps the chosen trades or the selection solid and ghosts every other model; click again to change or clear."""
from namo import items, look_ghost, paint, ui
from pynavis import doc as nwdoc
from pynavis import forms, script, toast

TITLE = 'Trade Ghost'


def choose_focus(document, cfg):
    """The focus values ticked in the chooser, or None on cancel."""
    groups, _models = look_ghost.model_groups(document)
    selected = items.selected(document)
    rows = look_ghost.chooser_rows([(t, [m['name'] for m in ms]) for t, ms in groups], len(selected))
    remembered = [t for t in cfg['trades'] if t in [g[0] for g in groups]]
    picked = ui.choose(TITLE, rows, ['Focus', 'Size', 'Models'], multiselect=True, checked=remembered,
                       ok='Ghost the rest',
                       prompt='Tick what stays solid. Everything else fades to %d%% transparent.'
                              % cfg['transparency'])
    return picked, groups


def ghost(document, cfg, record):
    picked, groups = choose_focus(document, cfg)
    if picked is None:
        return
    keep = look_ghost.focus_items(picked, groups, document)
    if not keep:
        toast.info('Nothing to keep solid', 'Tick a trade, or select something and tick Current selection.')
        return
    previous = []
    if record is not None:
        previous, _missing = items.resolve(record['entries'], document)
    cfg['trades'] = [p for p in picked if p != look_ghost.SELECTION]
    script.save_config(cfg)
    others = look_ghost.ghost(keep, cfg, previous, document)
    label = look_ghost.focus_label(picked)
    if not others:
        look_ghost.save_record(None, document)
        toast.info('Nothing left to ghost', '%s is the whole model.' % label)
        return
    look_ghost.save_record(look_ghost.make_record(items.entries(others, document), label, cfg), document)
    toast.success('Ghosted everything but %s' % label,
                  '%d%% transparent%s. Click Trade Ghost again to change or clear it.'
                  % (cfg['transparency'], ' and grey' if cfg['grey'] else ''))


def clear(document, record):
    count, missing = look_ghost.clear(record, document)
    look_ghost.save_record(None, document)
    if missing and not count:
        if forms.confirm('The ghosted items could not be found again. Reset every color and '
                         'transparency in the model instead?', title=TITLE):
            paint.reset(None, document, 'Clear ghost')
            toast.success('Ghost cleared', 'Every color and transparency is back to the model.')
        return
    toast.success('Ghost cleared', 'Everything outside %s is back to its own colors.' % record.get('focus', 'the focus'))


def run():
    document = nwdoc.get_doc()
    if document.Models.Count == 0:
        toast.info('No model open', 'Open or append models, then run Trade Ghost again.')
        return
    cfg = look_ghost.normalize_config(script.get_config(look_ghost.DEFAULTS))
    record = look_ghost.load_record(document)
    if record is None:
        ghost(document, cfg, None)
        return
    action = forms.ask_options(None, [look_ghost.CHANGE, look_ghost.CLEAR], title=TITLE)
    if action == look_ghost.CHANGE:
        ghost(document, cfg, record)
    elif action == look_ghost.CLEAR:
        clear(document, record)


run()
