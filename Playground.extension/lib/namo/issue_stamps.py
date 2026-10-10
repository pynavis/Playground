# -*- coding: utf-8 -*-
"""Issue Stamps: click a point, get an issue there.

Each stamp button (RFI, Hold, Verify, Safety, Stamp from Template) asks for a point
with Navisworks' own Measure tool (namo.picking: its marker and snapping, the prompt on
the banner), then creates an issue from its
template: type, number prefix, title pattern ('{type} {n:000}'), priority, assignee, due
date (today + the template's days), description and labels; the trade is the template's,
else the trade of the clicked object's model (namo.trades). The clicked object becomes
the issue's element, the point its pin (with grid and level), and the current camera and
a snapshot are recorded. The toast says 'RFI 012 created'; pins redraw when Issue Pins
is on (through the issue events every view listens to).

Pure part: plan_fields (tested); stamp() is the API flow the buttons call.
"""


def _text(value):
    return '' if value is None else (u'%s' % (value,)).strip()


def plan_fields(template, element=None, trade_of_model='', location=None, now=None):
    """(fields, prefix, title_pattern, title_values) for a stamp (pure). element: the
    clicked object's record (namo.issueapi.element_record) or None."""
    from namo import issuestore
    fields, prefix, pattern = issuestore.template_fields(template, now)
    if not fields.get('trade') and trade_of_model and trade_of_model != 'Unassigned':
        fields['trade'] = trade_of_model
    if element:
        fields['elements'] = [element]
    if location:
        fields['location'] = location
    fields['source'] = {'kind': 'stamp', 'ref': _text(template.get('type'))}
    values = {'element': _text((element or {}).get('name')),
              'model': _text((element or {}).get('model')),
              'level': _text((location or {}).get('level')),
              'grid': _text((location or {}).get('grid'))}
    return fields, prefix, pattern, values


def created_message(issue, template):
    """'RFI 012 created' (the stamp name and the issue number)."""
    label = _text(template.get('stamp_label')) or _text(template.get('type')) or 'Issue'
    number = issue.get('number')
    if number is None:
        return '%s created' % issue.get('id')
    return '%s %03d created' % (label, number)


def created_detail(issue, element, where, shot_error=None):
    """The toast's second line: the issue id, where it landed (level and grid when the
    model has grids), what was under the click, and a missing snapshot if any (pure).
    where: issueui.location_text(issue)."""
    location = issue.get('location') or {}
    parts = [_text(issue.get('id'))]
    if location.get('level') or location.get('grid'):
        parts.append(where)
    parts.append('on %s' % (_text((element or {}).get('name')) or 'the clicked object')
                 if element else 'no object under the point')
    text = ', '.join(p for p in parts if p)
    if shot_error:
        text += '. No snapshot: %s' % shot_error
    return text


def ready(doc=None):
    """(document, register) when a stamp can be placed now; otherwise toasts why not (no
    model, model not saved, running without a window) and returns None. Stamp from
    Template asks this before it asks for a template."""
    from pynavis import toast
    from namo import issueapi, issuestore, ui
    if ui.is_runner():
        toast.info('Issue Stamps needs the Navisworks window', 'A stamp is placed with a click '
                   'in the view, so it cannot run under pynavis run.')
        return None
    document = doc if doc is not None else issuestore.active_doc()
    if document is None or not issueapi.has_model(document):
        toast.info('No model open', 'Open or append a model, then stamp an issue on it.')
        return None
    store = issuestore.for_doc(document)
    if not store.saved:
        toast.info('Save the model first', issuestore.NOT_SAVED)
        return None
    return document, store


def stamp(type_name, doc=None):
    """The whole stamp flow for one template type name. Toasts every outcome; a cancelled
    pick is silent. Returns the new issue or None."""
    from pynavis import toast
    from namo import camera, issue_templates, issueapi, issueui, picking
    found = ready(doc)
    if found is None:
        return None
    document, store = found
    template = issue_templates.resolve(type_name)
    if template is None:
        toast.error('No template called %s' % type_name,
                    'Add it in Issue Templates, or use Stamp from Template.')
        return None
    label = template['stamp_label'] or template['type']
    hit = picking.point('Click where the %s goes' % label, want_item=True, doc=document)
    if hit is None:                     # Esc, right-click or another tool: say nothing
        return None
    element = None
    model_trade = ''
    if hit.item is not None:
        try:
            record = issueapi.elements_of([hit.item], document, 1)[0]
            element = record[0] if record else None
            model_trade = issueapi.trade_of_item(hit.item)
        except Exception:
            element = None
    location = issueapi.location_of(hit.point, document)
    fields, prefix, pattern, values = plan_fields(template, element, model_trade, location)
    fields['camera'] = camera.capture(document)
    fields['camera_units'] = issueapi.doc_units(document)
    shot = None
    shot_error = None
    try:
        shot = issueapi.snapshot(document)
    except Exception as error:
        shot_error = str(error)
    try:
        issue = store.create(fields, prefix=prefix, title_pattern=pattern, title_values=values)
    except (IOError, OSError) as error:
        toast.error('Could not save the %s' % label, '%s Check the data folder, then try again.' % error)
        return None
    except ValueError as error:
        # A sentence by the issuestore contract, e.g. a template title pattern that came
        # out empty ('{element}' with nothing under the point).
        toast.error('Could not save the %s' % label, str(error))
        return None
    if shot:
        try:
            issue = store.add_image(issue['id'], shot, kind='snapshot', move=True)
        except Exception as error:
            shot_error = str(error)
    toast.success(created_message(issue, template),
                  created_detail(issue, element, issueui.location_text(issue), shot_error))
    return issue


def choose_template():
    """Asks which template to stamp with (a searchable list). None on cancel."""
    from pynavis import forms
    from namo import issue_templates
    templates = issue_templates.load()
    options = [('%s  (%s, %s)' % (t['stamp_label'] or t['type'], t['priority'],
                                   ('due in %s' % issue_templates.days_text(t['due_days']))
                                   if t['due_days'] is not None else 'no due date'), t['type'])
               for t in templates]
    return forms.select_from_list(options, title='Stamp from template',
                                  prompt='Choose the kind of issue, then click where it goes.')
