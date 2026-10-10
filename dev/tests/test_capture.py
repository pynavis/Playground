# -*- coding: utf-8 -*-
"""namo.capture pure half: file names, relative links, the contact sheet grid, form
fields, summaries and issue picking; the contact sheet written to disk."""
import os

import _compat

from namo import capture, ui


def test_file_names_tokens_uniqueness_and_slashes():
    entries = [{'name': 'Level 2/Corridor', 'folder': 'A/B'}, {'name': 'Level 2/Corridor', 'folder': 'A/B'},
               {'name': '', 'folder': ''}, {'name': 'CON', 'folder': ''}]
    names = capture.file_names(entries, '{folder}_{name}', 'PNG')
    assert names[0] == 'A - B_Level 2 - Corridor.png'
    assert names[1] == 'A - B_Level 2 - Corridor (2).png'
    assert names[2] in ('_.png', 'Image 3.png')
    assert names[3].lower() not in ('con_.png', 'con.png')
    numbered = capture.file_names([{'name': 'a'}, {'name': 'b'}], '{n:00} {name}', 'jpg')
    assert numbered == ['01 a.jpg', '02 b.jpg']
    fallback = capture.file_names([{'name': ''}], '{name}', 'png', 'Clash')
    assert fallback == ['Clash 1.png']


def test_ext_and_relative_urls():
    assert capture.ext_for('JPG') == 'jpg' and capture.ext_for('jpeg') == 'jpg' and capture.ext_for('png') == 'png'
    url = capture.relative_url(r'C:\Out\Run 1\thumbs\A #2.jpg', r'C:\Out\Run 1')
    assert url == 'thumbs/A%20%232.jpg'


def test_grid_html_escapes_and_links_relative():
    html = capture.grid_html([{'image': r'C:\o\a <b>.png', 'thumb': r'C:\o\thumbs\a.jpg',
                               'caption': 'View <1>', 'detail': 'Folder & co'}], r'C:\o', columns=3)
    assert html.startswith('<div class="gal" style="--cols:3">')
    assert 'href="a%20&lt;b&gt;.png"' in html and 'src="thumbs/a.jpg"' in html
    assert 'View &lt;1&gt;' in html and 'Folder &amp; co' in html


def test_summary_levels():
    ok = capture.summary([('viewpoint images', 3, []), ('clash images', 2, [])], False, 5)
    assert ok == ('success', 'Saved 5 images', '3 viewpoint images, 2 clash images.')
    partial = capture.summary([('viewpoint images', 3, [('V4', 'no image')])], False, 4)
    assert partial == ('warning', 'Saved 3 images, 1 failed', 'V4: no image')
    assert capture.summary([('x', 0, [('a', 'b')])], False, 1)[0] == 'error'
    assert capture.summary([('x', 2, [])], True, 9)[1] == 'Stopped after 2 of 9 images'
    assert capture.summary([], False, 0)[1] == 'No images saved'


def test_image_fields_and_values():
    cfg = {'width': 1920, 'height': 1080, 'format': 'jpg', 'quality': 80, 'image_template': '{name}', 'folder': ''}
    import test_vp_common as vpfake
    vpfake.check_defaults(capture.image_fields(cfg, r'C:\Jobs'))
    specs = ui.normalize_fields(capture.image_fields(cfg, r'C:\Jobs'))
    by_key = dict((f['key'], f) for f in specs if f.get('key'))
    assert by_key['size']['default'] == '1920x1080' and by_key['format']['default'] == 'jpg'
    assert by_key['folder']['default'] == r'C:\Jobs'
    odd = ui.normalize_fields(capture.image_fields(dict(cfg, width=1000, height=777), 'x', with_template=False))
    assert [f for f in odd if f.get('key') == 'size'][0]['default'] == 'custom'
    assert 'image_template' not in [f.get('key') for f in odd]
    out = capture.image_values(cfg, {'size': 'custom', 'width': 800, 'height': 600, 'format': 'png',
                                     'quality': 70, 'folder': r'D:\x'})
    assert (out['width'], out['height'], out['format'], out['folder']) == (800, 600, 'png', r'D:\x')
    out = capture.image_values(cfg, {'size': '3840x2160'})
    assert (out['width'], out['height']) == (3840, 2160)


def test_pick_issues():
    records = [{'id': 'RFI-001', 'title': 'Duct', 'status': 'Open', 'camera': {'position': [0, 0, 0]}},
               {'id': 'RFI-002', 'title': 'Pipe', 'status': 'Closed', 'camera': {'position': [0, 0, 0]}},
               {'id': 'RFI-003', 'title': 'No view', 'status': 'Open'},
               {'id': 'RFI-004', 'title': 'Beam', 'status': 'In progress', 'camera': {'position': [1, 1, 1]}},
               'junk']
    open_ones = capture.pick_issues(records)
    assert [u['id'] for u in open_ones] == ['RFI-001', 'RFI-004'] and open_ones[0]['name'] == 'RFI-001 Duct'
    closed = capture.pick_issues(records, ['Closed'])
    assert [u['id'] for u in closed] == ['RFI-002']


def test_issues_available_is_a_bool():
    assert capture.issues_available() in (True, False)
    statuses = capture.issue_statuses()
    assert isinstance(statuses, list)


def test_write_index_makes_a_page():
    folder = _compat.tmpdir('capture_index')
    image = os.path.join(folder, 'one.png')
    with open(image, 'wb') as handle:
        handle.write(b'not really a png')
    path = capture.write_index(os.path.join(folder, 'index.html'), 'Viewpoint images', 'Tower',
                               [('Model', 'Tower'), ('Images', 1)],
                               [('Viewpoints', 'Click an image.', [{'image': image, 'caption': 'One',
                                                                    'detail': '(top level)'}]),
                                ('Empty', None, [])])
    with open(path, 'rb') as handle:
        text = handle.read().decode('utf-8')
    assert 'href="one.png"' in text and '<h2' in text and 'Empty' not in text


def test_keep_state_restores_the_users_hidden_state_in_one_transaction():
    import test_items as nav
    import test_vp_common as vpfake
    doc = vpfake.make_doc()
    vpfake.tree(doc)
    plain = doc.SavedViewpoints.RootItem.Children[0]
    with nav.FakeNav(doc) as fake:
        vpfake.extend(fake.Api)
        with capture.KeepState(doc, [plain]) as keep:
            assert keep.temp is None and keep.tx is None
        assert doc.transactions == []
        stateful = vpfake.view('Hidden walls')
        stateful.ContainsVisibilityOverrides = True
        with capture.KeepState(doc, [plain, stateful]) as keep:
            assert keep.temp is not None and keep.temp.DisplayName == capture.TEMP_VIEW
            doc.CurrentViewpoint.vp.Position = nav.Point3D(99, 99, 99)
        assert doc.transactions == ['Keep the view']
        assert capture.TEMP_VIEW not in [c.DisplayName for c in doc.SavedViewpoints.RootItem.Children]
        assert doc.CurrentViewpoint.vp.Position.t() == (0.0, 0.0, 10.0)
    assert capture.carries_state(stateful) and not capture.carries_state(plain)


def test_keep_state_never_reapplies_a_current_view_that_carries_state():
    """Regression: with plain views captured, the saved viewpoint current before the run
    was recalled again afterwards; one that stores hidden items put its own hidden
    state back over what the user had hidden or shown by hand since."""
    import test_items as nav
    import test_vp_common as vpfake
    doc = vpfake.make_doc()
    vpfake.tree(doc)
    plain = doc.SavedViewpoints.RootItem.Children[0]
    current = vpfake.view('Hidden walls')
    current.ContainsVisibilityOverrides = True
    with nav.FakeNav(doc) as fake:
        vpfake.extend(fake.Api)
        doc.SavedViewpoints.CurrentSavedViewpoint = current
        with capture.KeepState(doc, [plain]) as keep:
            assert keep.temp is None and not keep.keeper.restore_saved
            doc.SavedViewpoints.CurrentSavedViewpoint = plain        # what a capture does
        assert doc.SavedViewpoints.CurrentSavedViewpoint is plain    # 'Hidden walls' not re-applied
        assert doc.transactions == []
        with capture.KeepState(doc, [plain]) as keep:               # a plain current view still comes back
            assert keep.keeper.restore_saved


def test_clash_and_issue_steps_need_a_choice():
    """Regression: no status ticked meant every status (clash_units treats [] as all,
    pick_issues as Open and In progress), and a blank cap reached '>' as None."""
    import test_vp_common as vpfake
    fields = capture.clash_fields({'statuses': ['Active'], 'cap': 50})
    vpfake.check_defaults(fields)
    specs = ui.normalize_fields(fields)
    _values, errors = ui.collect(specs, {'statuses': [], 'cap': ''})
    assert 'statuses' in errors and 'cap' in errors
    values, errors = ui.collect(specs, {'statuses': ['Active'], 'cap': '50'})
    assert not errors and values == {'statuses': ['Active'], 'cap': 50}
    issue = ui.normalize_fields(capture.issue_fields({}, ['Open', 'In progress', 'Closed']))
    assert issue[0]['default'] == ['Open', 'In progress']
    _values, errors = ui.collect(issue, {'issue_statuses': []})
    assert 'issue_statuses' in errors


def test_source_fields_and_validator():
    import test_vp_common as vpfake
    cfg = {'views_on': True, 'clashes_on': True, 'issues_on': False, 'width': 1280, 'height': 720,
           'format': 'jpg', 'quality': 88, 'folder': '', 'open': True}
    fields = capture.source_fields(cfg, r'C:\Jobs', True, False, False)
    vpfake.check_defaults(fields)
    keys = [f.get('key') for f in fields]
    assert 'issues_on' not in keys and 'image_template' not in keys and keys[-1] == 'open'
    assert [f['default'] for f in fields if f.get('key') == 'clashes_on'] == [False]
    validate = capture.source_validator(True, False)
    assert validate({'views_on': False, 'clashes_on': False}) == 'Tick at least one source.'
    assert validate({'clashes_on': True}) == {'clashes_on': 'This model has no clash tests with results.'}
    assert validate({'views_on': True}) is None
