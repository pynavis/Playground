# -*- coding: utf-8 -*-
"""Field Checklists: inspection checklists attached to saved viewpoints.

Templates are team data (namo.templates 'checklists'); two examples ship built in (QA
inspection and Safety walk) and a team template of the same name replaces them. A
template's text form is one item per line with '# Section' lines starting a section:

    # Formwork
    Formwork clean and oiled
    Cover spacers fixed

A checklist is one record per saved viewpoint in the per-document RecordStore
'checklists', keyed by the viewpoint's GUID:

    {'id': guid, 'viewpoint': 'Level 2 core', 'folder': 'QA/Level 2', 'template': name,
     'items': [{'id': 'I01', 'section', 'text', 'result': 'pass'|'fail'|'na'|None, 'note'}],
     'inspector', 'date' ('YYYY-MM-DD'), 'signed_off', 'signed_by', 'signed_at', 'updated'}

Pure half: templates, records, progress, report rows and the HTML/Excel report.
"""

import datetime

TOOL = 'checklists'
STORE = 'checklists'
RESULTS = ('pass', 'fail', 'na')
RESULT_LABELS = {'pass': 'Pass', 'fail': 'Fail', 'na': 'N/A', None: 'Open'}
RESULT_TONES = {'pass': 'good', 'fail': 'bad', 'na': 'neutral', None: 'warn'}

BUILTIN = {
    'QA inspection': {
        'description': 'Pre-pour and close-in quality checks.',
        'text': '# Setting out\nGridlines and levels checked against the drawings\n'
                'Openings and penetrations in the right place\n'
                '# Structure\nReinforcement size, spacing and cover as detailed\n'
                'Cast-in items and sleeves fixed\nFormwork clean, sealed and propped\n'
                '# Services\nFirst fix complete and tested\nFire stopping installed at penetrations\n'
                'Access panels where the services need them\n'
                '# Finishes\nSurfaces ready for the next trade\nDefects photographed and logged',
    },
    'Safety walk': {
        'description': 'Weekly site safety walk.',
        'text': '# Access\nWalkways clear and lit\nStairs and ladders secured\n'
                '# Edges and openings\nEdge protection complete\nFloor openings covered and marked\n'
                '# Work at height\nScaffold tagged and inspected\nHarness points in use\n'
                '# Fire and housekeeping\nExtinguishers in place and in date\nHot work permits displayed\n'
                'Waste cleared, no trip hazards',
    },
}


def parse_template_text(text):
    """[{'id', 'section', 'text'}] from the text form. Raises ValueError when there are
    no items."""
    items = []
    section = ''
    for line in str(text or '').replace('\r', '').split('\n'):
        line = line.strip()
        if not line:
            continue
        if line.startswith('#'):
            section = line.lstrip('#').strip()
            continue
        items.append({'id': 'I%02d' % (len(items) + 1), 'section': section, 'text': line})
    if not items:
        raise ValueError('A checklist needs at least one item (one per line).')
    return items


def template_text(items):
    """The text form of items (the inverse of parse_template_text)."""
    lines = []
    section = None
    for item in items:
        if item.get('section', '') != section:
            section = item.get('section', '')
            if section:
                if lines:
                    lines.append('')
                lines.append('# ' + section)
        lines.append(item['text'])
    return '\n'.join(lines)


def template_items(config):
    """Items of a template config ({'text'} or {'items'})."""
    if config.get('items'):
        out = []
        for index, item in enumerate(config['items']):
            out.append({'id': item.get('id') or 'I%02d' % (index + 1), 'section': item.get('section', ''),
                        'text': item['text']})
        return out
    return parse_template_text(config.get('text', ''))


def all_templates(team):
    """{name: config}: the built-in examples overlaid by the team's templates."""
    out = dict((name, dict(config)) for name, config in BUILTIN.items())
    for name, config in (team or {}).items():
        out[name] = config
    return out


def new_checklist(guid, viewpoint, folder, template_name, template_config, now=None):
    items = []
    for item in template_items(template_config):
        items.append({'id': item['id'], 'section': item['section'], 'text': item['text'],
                      'result': None, 'note': ''})
    return {'id': str(guid), 'viewpoint': viewpoint, 'folder': folder or '', 'template': template_name,
            'items': items, 'inspector': '', 'date': '', 'signed_off': False, 'signed_by': '',
            'signed_at': '', 'updated': _stamp(now)}


def _stamp(now=None):
    return (now or datetime.datetime.now()).replace(microsecond=0).isoformat()


def progress(record):
    """{'total', 'answered', 'passed', 'failed', 'na', 'open', 'percent' (answered share,
    0..100 int), 'complete', 'signed'}."""
    items = record.get('items') or []
    counts = {'pass': 0, 'fail': 0, 'na': 0}
    for item in items:
        if item.get('result') in counts:
            counts[item['result']] += 1
    answered = counts['pass'] + counts['fail'] + counts['na']
    total = len(items)
    return {'total': total, 'answered': answered, 'passed': counts['pass'], 'failed': counts['fail'],
            'na': counts['na'], 'open': total - answered,
            'percent': int(round(100.0 * answered / total)) if total else 0,
            'complete': bool(total) and answered == total, 'signed': bool(record.get('signed_off'))}


def progress_text(record):
    p = progress(record)
    text = '%d of %d answered' % (p['answered'], p['total'])
    if p['failed']:
        text += ', %d failed' % p['failed']
    if p['signed']:
        text += ', signed off'
    return text


def set_result(record, item_id, result=None, note=None, now=None):
    """Records a result ('pass', 'fail', 'na' or None) and/or a note on one item."""
    if result is not None and result not in RESULTS:
        raise ValueError('A result is pass, fail or na.')
    for item in record.get('items') or []:
        if item['id'] == item_id:
            if result is not None or note is None:
                item['result'] = result
            if note is not None:
                item['note'] = note
            record['updated'] = _stamp(now)
            return item
    raise KeyError(item_id)


def sign_off(record, inspector, on=True, now=None):
    """Signs a checklist off (or withdraws it). ValueError when items are still open or
    no inspector is named."""
    if on:
        if not str(inspector or '').strip():
            raise ValueError('Name the inspector to sign off.')
        if progress(record)['open']:
            raise ValueError('Answer every item before signing off.')
        record['signed_off'] = True
        record['signed_by'] = str(inspector).strip()
        record['signed_at'] = _stamp(now)
    else:
        record['signed_off'] = False
        record['signed_by'] = ''
        record['signed_at'] = ''
    return record


def merge_template(record, template_config):
    """Adds items a template gained since the checklist was made (by text), keeping every
    answer. Returns how many were added."""
    have = set(i['text'].strip().lower() for i in record.get('items') or [])
    added = 0
    for item in template_items(template_config):
        if item['text'].strip().lower() in have:
            continue
        record['items'].append({'id': 'I%02d' % (len(record['items']) + 1), 'section': item['section'],
                                'text': item['text'], 'result': None, 'note': ''})
        added += 1
    return added


def summary_rows(records):
    """[viewpoint path, template, answered/total text, percent, failed, inspector, date,
    signed] per checklist, natural order by path."""
    from namo import naming
    out = []
    for record in sorted(records, key=lambda r: naming.natural_key(path_of(r))):
        p = progress(record)
        out.append([path_of(record), record.get('template', ''), '%d/%d' % (p['answered'], p['total']),
                    p['percent'], p['failed'], record.get('inspector', ''), record.get('date', ''),
                    'Yes' if p['signed'] else 'No'])
    return out


def failures(records):
    """[viewpoint path, section, item, note] for every failed item."""
    from namo import naming
    out = []
    for record in sorted(records, key=lambda r: naming.natural_key(path_of(r))):
        for item in record.get('items') or []:
            if item.get('result') == 'fail':
                out.append([path_of(record), item.get('section', ''), item['text'], item.get('note', '')])
    return out


def path_of(record):
    folder = record.get('folder') or ''
    return (folder + '/' if folder else '') + (record.get('viewpoint') or '')


def totals(records):
    total = answered = failed = signed = 0
    for record in records:
        p = progress(record)
        total += p['total']
        answered += p['answered']
        failed += p['failed']
        signed += 1 if p['signed'] else 0
    return {'checklists': len(records), 'items': total, 'answered': answered, 'failed': failed,
            'signed': signed, 'percent': int(round(100.0 * answered / total)) if total else 0}


def build_report(records, title, doc_name='', user=''):
    """The HTML report (namo.htmlreport.Report): completion, failures, then every
    checklist with its items."""
    from namo import htmlreport
    t = totals(records)
    report = htmlreport.Report(title, subtitle=doc_name or None,
                               meta=[('Checklists', t['checklists']), ('By', user or '')])
    report.kpis([('Completion', '%d%%' % t['percent'], 'good' if t['percent'] == 100 else None),
                 ('Items answered', '%s of %s' % ('{:,}'.format(t['answered']), '{:,}'.format(t['items'])), None),
                 ('Failures', t['failed'], 'bad' if t['failed'] else 'good'),
                 ('Signed off', '%d of %d' % (t['signed'], t['checklists']), None)])
    report.section('Completion by viewpoint')
    rows = summary_rows(records)
    report.table(['Viewpoint', 'Template', 'Answered', 'Complete %', 'Failed', 'Inspector', 'Date', 'Signed off'],
                 rows, row_tones=['bad' if r[4] else ('good' if r[3] == 100 else None) for r in rows])
    fails = failures(records)
    report.section('Failures', intro='Every item marked Fail, with its note.')
    if fails:
        report.table(['Viewpoint', 'Section', 'Item', 'Note'], fails)
    else:
        report.note('No item failed.')
    for record in sorted(records, key=lambda r: path_of(r).lower()):
        p = progress(record)
        report.section(path_of(record), intro='%s, %s' % (record.get('template', ''), progress_text(record)))
        item_rows = []
        html_cells = set()
        for index, item in enumerate(record.get('items') or []):
            result = item.get('result')
            item_rows.append([item.get('section', ''), item['text'],
                              htmlreport.status_chip(RESULT_LABELS[result], RESULT_TONES[result]),
                              item.get('note', '')])
            html_cells.add((index, 2))
        report.table(['Section', 'Item', 'Result', 'Note'], item_rows, cell_html=html_cells,
                     filterable=False)
        if p['signed']:
            report.note('Signed off by %s on %s.' % (record.get('signed_by', ''),
                                                     (record.get('signed_at') or '')[:10]))
    return report


def write_xlsx(path, records, title, author=None):
    """Summary, Failures and Items sheets. Returns path."""
    from namo import xlsx
    wb = xlsx.Workbook(title=title, author=author)
    ws = wb.sheet('Summary')
    ws.title(title, span=8)
    ws.columns([('Viewpoint', 36, None), ('Template', 18, None), ('Answered', 11, None),
                ('Complete %', 11, 'int'), ('Failed', 9, 'int'), ('Inspector', 18, None),
                ('Date', 12, None), ('Signed off', 11, None)])
    for row in summary_rows(records):
        ws.row(row, styles=[None, None, None, None, 'bad' if row[4] else None])
    ws.autofilter()
    fails = wb.sheet('Failures')
    fails.columns([('Viewpoint', 36, None), ('Section', 18, None), ('Item', 50, 'wrap'), ('Note', 50, 'wrap')])
    for row in failures(records):
        fails.row(row)
    items = wb.sheet('Items')
    items.columns([('Viewpoint', 36, None), ('Section', 18, None), ('Item', 50, 'wrap'),
                   ('Result', 10, None), ('Note', 50, 'wrap')])
    for record in sorted(records, key=lambda r: path_of(r).lower()):
        for item in record.get('items') or []:
            result = item.get('result')
            items.row([path_of(record), item.get('section', ''), item['text'], RESULT_LABELS[result],
                       item.get('note', '')],
                      styles=[None, None, None, {'pass': 'good', 'fail': 'bad'}.get(result)])
    items.autofilter()
    return wb.save(path)


# ---- API half ----------------------------------------------------------------------------------


def templates():
    from namo import templates as _templates
    return _templates.Templates(TOOL)


def available_templates():
    """{name: config} built-ins plus team templates."""
    store = templates()
    team = {}
    for name in store.names():
        config = store.get(name)
        if config is not None:
            team[name] = config
    return all_templates(team)


def records_store(doc=None):
    from namo import store as _store
    return _store.records_for_active_doc(STORE, doc=doc)


def viewpoint_list(doc=None):
    """[{'guid', 'name', 'folder', 'path', 'saved'}] for every saved viewpoint, tree order."""
    from namo import camera
    out = []
    for folder, saved in camera.saved_views(doc):
        name = str(saved.DisplayName or '')
        out.append({'guid': str(saved.Guid), 'name': name, 'folder': folder,
                    'path': (folder + '/' if folder else '') + name, 'saved': saved})
    return out


def current_guid(doc=None):
    from pynavis._api import Application
    document = doc or Application.ActiveDocument
    try:
        current = document.SavedViewpoints.CurrentSavedViewpoint
        return str(current.Guid) if current is not None else None
    except Exception:
        return None
