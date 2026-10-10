# -*- coding: utf-8 -*-
"""QR Tagger: payloads from a template, PNG files, a printable label sheet and the
'Playground > QR' property.

Pure half: the token values a payload template can use, payload rendering and checks,
file names, and the label sheet (A4, 3 x 8 labels, each with its QR as inline SVG so it
prints sharp, the object's name and its IDs). API half: reading an object's values and
writing the property (merged into the object's existing Playground tab).
"""

import os

DEFAULT_TEMPLATE = '{project}|{file}|{element_id}|{guid}'
TOKENS = ['project', 'number', 'company', 'file', 'name', 'category', 'family', 'type', 'element_id',
          'unique_id', 'guid', 'date']
TAB = 'Playground'
PROPERTY = 'QR'

_SHEET = u"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>%(title)s</title>
<style>
@page{size:A4;margin:10mm}
*{box-sizing:border-box}
body{margin:0;font:9pt/1.3 "Segoe UI",system-ui,sans-serif;color:#1A1A1A;background:#FFFFFF}
.intro{padding:0 0 4mm;color:#6B6B6B}
.sheet{display:grid;grid-template-columns:repeat(3,63mm);grid-auto-rows:34mm;gap:2mm 3mm}
.label{display:flex;gap:2.5mm;align-items:center;border:0.2mm dashed #C9C9C9;padding:2mm;overflow:hidden;
break-inside:avoid;page-break-inside:avoid}
.label svg{flex:0 0 28mm;width:28mm;height:28mm}
.text{min-width:0}
.name{font-weight:600;font-size:9pt;overflow:hidden;text-overflow:ellipsis;display:-webkit-box;
-webkit-line-clamp:2;-webkit-box-orient:vertical}
.id{color:#4D4D4D;font-size:7pt;word-break:break-all;margin-top:1mm}
@media print{.intro{display:none}.label{border-color:#E0E0E0}}
</style></head><body>
<div class="intro">%(intro)s</div>
<div class="sheet">
%(labels)s
</div>
</body></html>
"""


def values_for(ids, name, standard):
    """Token values for one object: the standard ones (project, file, date...) plus the
    object's own (name, category, family, type, element_id, unique_id, guid)."""
    out = dict(standard)
    out['number'] = standard.get('project_number', '')
    out['name'] = name or ''
    for key in ('category', 'family', 'type', 'element_id', 'unique_id'):
        out[key] = (ids or {}).get(key) or ''
    out['guid'] = (ids or {}).get('ifc_guid') or ''
    return out


def render_payload(template, values):
    """(payload, missing tokens): the template filled; unknown tokens stay as written."""
    from namo import naming
    text, missing = naming.render(template, values)
    return text.strip(), missing


def check_template(template):
    """A sentence when the template cannot work, else None."""
    from namo import naming
    if not str(template or '').strip():
        return 'Give a payload template, such as %s.' % DEFAULT_TEMPLATE
    unknown = [t for t in naming.tokens(template) if t.lower() not in TOKENS]
    if unknown:
        return '{%s} is not a token. Use %s.' % (unknown[0], ', '.join('{%s}' % t for t in TOKENS))
    return None


def repeated_payloads(payloads):
    """How many payloads repeat an earlier one: codes that scan the same although they
    sit on different objects (objects with no Element ID or GUID, or a template with no
    per-object token)."""
    seen = set()
    repeats = 0
    for payload in payloads:
        if payload in seen:
            repeats += 1
        seen.add(payload)
    return repeats


def file_names(labels):
    """A unique, safe PNG file name per label from its element id or name."""
    from namo import naming
    out = []
    taken = []
    for label in labels:
        base = label.get('element_id') or label.get('name') or 'QR'
        stem = naming.sanitize(str(base), for_file=True)
        name = naming.unique(stem, taken)
        taken.append(name)
        out.append(name + '.png')
    return out


def label_html(svg, name, lines):
    from namo import htmlreport
    detail = ''.join('<div class="id">%s</div>' % htmlreport.escape(line) for line in lines if line)
    return ('<div class="label">%s<div class="text"><div class="name">%s</div>%s</div></div>'
            % (svg, htmlreport.escape(name), detail))


def sheet_html(labels, title='QR labels', intro=''):
    """The printable sheet: labels = [{'svg', 'name', 'lines'}]."""
    from namo import htmlreport
    body = '\n'.join(label_html(l['svg'], l['name'], l.get('lines') or []) for l in labels)
    return _SHEET % {'title': htmlreport.escape(title), 'intro': htmlreport.escape(intro), 'labels': body}


# ---- API half ---------------------------------------------------------------------------------


def object_values(obj, standard):
    from namo import items
    try:
        ids = items.revit_ids(obj)
    except Exception:
        ids = {}
    return values_for(ids, str(obj.DisplayName or '') or items.category(obj), standard)


def write_property(objects, payloads, doc=None):
    """Writes each payload into its object's Playground tab (merged), ONE undo step.
    Returns (written, errors)."""
    from pynavis import props
    from pynavis.viewpoints import transaction
    from namo import fourd_progress
    from pynavis._api import Application
    document = doc or Application.ActiveDocument
    written = 0
    errors = []
    try:
        with transaction('Tag QR codes', document):
            for obj, payload in zip(objects, payloads):
                try:
                    existing = props.get_custom(obj, TAB)
                except Exception:
                    existing = None
                tab = fourd_progress.merged_tab(existing, {PROPERTY: payload})
                count, problems = props.set_custom([obj], TAB, tab, document)
                written += count
                errors.extend(problems)
    finally:
        # A custom tab changed: Property Explorer's cached scan must not show the old
        # values (the namo README rule for every custom-property writer).
        try:
            from namo import propindex
            propindex.invalidate()
        except Exception:
            pass
    return written, errors


def output_folder(base, doc_title):
    from namo import dates, naming, paths
    stem = os.path.splitext(doc_title or '')[0] or 'Untitled'
    name = naming.sanitize('%s QR codes %s' % (stem, dates.today().strftime('%Y-%m-%d')), for_file=True)
    return paths.unique_path(os.path.join(base, name))
