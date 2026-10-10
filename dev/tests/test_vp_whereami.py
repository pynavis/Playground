# -*- coding: utf-8 -*-
"""namo.vp_whereami: the words of the popup, and gathering them on the fake."""
import _compat

import test_items as nav
import test_vp_common as vpfake
from namo import camera, levels, session, vp_whereami

DEG = chr(176)


def test_direction_text():
    assert vp_whereami.direction_text((0.0, 1.0, 0.0)) == 'N, bearing 0%s, level' % DEG
    text = vp_whereami.direction_text((1.0, 1.0, -0.2))
    assert text.startswith('NE, bearing 45%s, 8%s below the horizon' % (DEG, DEG))
    assert vp_whereami.direction_text((0.0, 0.0, -1.0)) == 'straight down'
    assert vp_whereami.direction_text((-1.0, -0.0001, 0.5)).startswith('W, bearing 270%s' % DEG)


def test_lens_and_section_text():
    persp = camera.make_cam((0, 0, 0), direction=(0, 1, 0), projection='persp', height_field=camera.height_field_for(45))
    assert vp_whereami.lens_text(persp, 'Meters') == 'Perspective, 45%s vertical field of view' % DEG
    ortho = camera.make_cam((0, 0, 0), direction=(0, 0, -1), projection='ortho', height_field=25.0)
    assert vp_whereami.lens_text(ortho, 'Meters') == 'Orthographic, 25.000 m tall view'
    assert vp_whereami.section_text(None) == 'Off'
    assert vp_whereami.section_text({'enabled': True, 'mode': 'Box'}) == 'Section box on'
    assert vp_whereami.section_text({'enabled': True, 'mode': 'Planes', 'active': 2}) == '2 planes on'
    assert vp_whereami.section_text({'enabled': True, 'mode': 'Planes', 'active': 0}) == 'On, no planes enabled'


def test_level_text():
    lvls = [levels.level('L1', 0.0), levels.level('L2', 4.0, 'property', True)]
    assert vp_whereami.level_text(lvls, 5.6, 'Meters') == 'L2, eye 1.600 m above it (approximate elevation)'
    assert vp_whereami.level_text(lvls, -1.0, 'Meters') == 'L1, eye 1.000 m below it'
    assert vp_whereami.level_text([], 1.0, 'Meters') is None


def test_lines_full_and_bare():
    cam = camera.make_cam((1.0, 2.0, 1.6), direction=(0, 1, 0), projection='persp',
                          height_field=camera.height_field_for(60))
    info = {'units': 'Meters', 'file': 'Tower.nwf', 'saved': 'Lobby', 'on_saved': True, 'camera': cam,
            'levels': [levels.level('L1', 0.0)], 'grid': {'label': 'B(-1.2)-3(+0.4)', 'nearest': 'B-3',
                                                          'distance': 1.26},
            'section': {'enabled': False}, 'models': 3, 'geometry': 120000, 'geometry_partial': False,
            'selected': 4}
    text = vp_whereami.lines(info)
    assert text[0] == 'File: Tower.nwf' and text[1] == 'Saved viewpoint: Lobby'
    assert text[2] == 'Eye: X 1.000 m  Y 2.000 m  Z 1.600 m'
    assert 'Level: L1, eye 1.600 m above it' in text
    assert 'Grid: B(-1.2)-3(+0.4) (nearest B-3, 1.260 m away)' in text
    assert 'Models: 3 models loaded, 120,000 geometry items' in text and 'Selection: 4 items' in text
    bare = vp_whereami.lines({'units': 'Feet', 'saved': 'Old', 'on_saved': False, 'models': 1,
                              'geometry': 500, 'geometry_partial': True})
    assert 'Saved viewpoint: moved away from Old' in bare and 'Grid: no grid system' in bare
    assert 'Models: 1 model loaded, more than 500 geometry items (stopped counting)' in bare
    assert bare[-1] == 'Selection: nothing selected' and bare[0] == 'File: Untitled (not saved yet)'


def test_gather_on_the_fake():
    session.clear('whereami')
    session.clear('levels')
    doc, named = nav.model_tree()
    doc.SavedViewpoints = vpfake.ViewsSaved(doc)
    doc.FileName = r'C:\Jobs\Tower.nwf'
    with nav.FakeNav(doc) as fake:
        vpfake.extend(fake.Api)
        saved = vpfake.view('Here', position=(0.0, 0.0, 10.0))
        doc.SavedViewpoints.RootItem.Children.append(saved)
        doc.SavedViewpoints.CurrentSavedViewpoint = saved
        doc.CurrentSelection.SelectedItems.extend([named['Wall 1']])
        info = vp_whereami.gather(doc)
        count, partial = vp_whereami.geometry_count(doc)
    assert info['file'] == 'Tower.nwf' and info['saved'] == 'Here' and info['on_saved'] is True
    assert info['geometry'] == 4 and not info['geometry_partial'] and (count, partial) == (4, False)
    assert info['selected'] == 1 and info['grid'] is None and info['levels'] is None
    text = vp_whereami.lines(info)
    assert 'Level: no grid levels (Level Sectioner can estimate them from the objects)' in text
    session.clear('whereami')
