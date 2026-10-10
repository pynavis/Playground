# -*- coding: utf-8 -*-
"""namo.rep_viewpoint_images: the reports contract, the empty cases, and (IronPython,
where System.Drawing writes the fake renders) a whole run with its contact sheet. The
Batch PDF report's own run is exercised here too, on the same fake document."""
import os

import _compat

import test_items as nav
import test_vp_common as vpfake
from namo import paths, rep_batch_pdf, rep_viewpoint_images, reports


def test_contract():
    config = rep_viewpoint_images.default_config()
    for key in ('folder', 'name_template', 'views', 'width', 'height', 'format', 'quality', 'image_template'):
        assert key in config
    assert rep_viewpoint_images.describe(config) == 'All viewpoints, 1920 x 1080 PNG'
    assert rep_viewpoint_images.TITLE == reports.title_of('viewpoint_images')
    assert reports.module_exists('viewpoint_images')


def test_empty_and_missing_cases():
    doc = vpfake.make_doc()
    with nav.FakeNav(doc) as fake:
        vpfake.extend(fake.Api)
        out = rep_viewpoint_images.run(rep_viewpoint_images.default_config(), doc=doc, interactive=False)
        assert out['level'] == 'info' and out['message'] == 'No saved viewpoints'
        vpfake.tree(doc)
        config = rep_viewpoint_images.default_config()
        config['views'] = {'mode': 'list', 'views': [['Gone', 'View']]}
        out = rep_viewpoint_images.run(config, doc=doc, interactive=False)
        assert out['message'] == 'No viewpoints to capture' and 'Gone/View' in out['detail']
        config['views'] = {'mode': 'all'}
        config['width'] = 0
        out = rep_viewpoint_images.run(config, doc=doc, interactive=False)
        assert out['level'] == 'error'
        out = rep_batch_pdf.run(dict(rep_batch_pdf.default_config(), views={'mode': 'folders', 'folders': ['Q']}),
                                doc=doc, interactive=False)
        assert out['message'] == 'No viewpoints to print'


def test_full_runs_write_images_index_and_pdf():
    _compat.require_ironpython('the fake renders are System.Drawing bitmaps')
    root = _compat.tmpdir('rep_images_run')
    previous = paths.redirect(os.path.join(root, 'appdata'))
    try:
        doc = vpfake.make_doc()
        vpfake.tree(doc)
        with nav.FakeNav(doc) as fake:
            vpfake.extend(fake.Api)
            config = rep_viewpoint_images.default_config()
            config.update({'folder': root, 'name_template': 'Run', 'width': 320, 'height': 180,
                           'views': {'mode': 'folders', 'folders': ['A']}, 'image_template': '{folder}_{name}'})
            out = reports.run('viewpoint_images', config, doc=doc, interactive=False)
            assert out['level'] == 'success', out
            folder = os.path.join(root, 'Run')
            assert sorted(os.listdir(folder)) == ['A - B_Two.png', 'A_One.png', 'index.html', 'thumbs']
            assert out['index'] == os.path.join(folder, 'index.html') and len(out['paths']) == 3
            with open(out['index'], 'rb') as handle:
                assert b'thumbs/A_One.jpg' in handle.read()
            assert doc.images[0] == ('Scene', 320, 180, True)
            # a second run with the same (day-dated) name gets its own folder
            again = reports.run('viewpoint_images', config, doc=doc, interactive=False)
            assert again['folder'] == os.path.join(root, 'Run (2)'), again
            assert sorted(os.listdir(folder)) == ['A - B_Two.png', 'A_One.png', 'index.html', 'thumbs']
            pdf_config = rep_batch_pdf.default_config()
            pdf_config.update({'folder': root, 'name_template': 'Handout', 'dpi': 60,
                               'order': [['C', 'Three'], ['', 'Top']]})
            out = reports.run('batch_pdf', pdf_config, doc=doc, interactive=False)
            assert out['level'] == 'success', out
            with open(out['pdf'], 'rb') as handle:
                data = handle.read()
            assert data.startswith(b'%PDF') and out['pdf'].endswith('Handout.pdf')
            assert not os.listdir(os.path.join(root, 'appdata', 'pyNavis', 'playground', 'tmp'))
    finally:
        paths.redirect(previous)
