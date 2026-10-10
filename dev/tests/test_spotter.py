# -*- coding: utf-8 -*-
"""namo.spotter pure half: labels, rows, text exports, the typed-origin parser."""
import _compat
from _compat import approx

from namo import spotter


POINTS = [{'n': 1, 'point': (12.0, 3.5, 0.0), 'object': 'Basic Wall', 'model': 'ARCH.nwc'},
          {'n': 2, 'point': (-1.25, 0.0, 2.75), 'object': '', 'model': ''}]


def test_label_metric_and_relative():
    assert spotter.label(3, (12.0, 3.5, 0.0), 'Meters') == 'P3  X 12.000 m  Y 3.500 m  Z 0.000 m'
    assert spotter.label(1, (12.0, 3.5, 1.0), 'Meters', origin=(10.0, 3.5, 1.0)) == \
        'P1  X 2.000 m  Y 0.000 m  Z 0.000 m'


def test_label_feet_and_inches():
    text = spotter.label(2, (12.375, 30.0, 9.5), 'Feet')
    assert text == "P2  X 12' 4 1/2\"  Y 30' 0\"  Z 9' 6\""


def test_tag():
    assert spotter.tag(7) == 'playground-spot-7'


def test_prompt_carries_the_last_reading():
    assert spotter.prompt_text(1) == 'Click point 1'
    assert spotter.prompt_text(1, origin=(1.0, 2.0, 3.0)) == 'Click point 1, measured from the local origin'
    last = {'n': 3, 'point': (12.0, 3.5, 0.0)}
    assert spotter.prompt_text(4, last, 'Meters') == 'Click point 4. Last: P3  X 12.000 m  Y 3.500 m  Z 0.000 m'


def test_no_snap_column_a_measured_point_knows_none():
    # Regression: the pick moved to the Measure tool, which reports a point only, so a
    # 'Snapped to' column could only ever have said 'Surface' on every row.
    head = spotter.headers('Meters')
    assert head[-2:] == ['Object', 'Model'] and len(head) == 9
    assert all(len(row) == 9 for row in spotter.display_rows(POINTS, 'Meters'))
    assert all(len(row) == 9 for row in spotter.data_rows(POINTS, 'Meters'))


class _Hit(object):
    def __init__(self, point):
        self.point = point
        self.item = None
        self.normal = None
        self.snap = None


def test_record_of_a_picking_hit():
    record = spotter.record_of(5, _Hit((1, 2.5, 3)))
    assert record == {'n': 5, 'point': (1.0, 2.5, 3.0), 'object': '', 'model': ''}


def test_headers_mark_the_origin():
    assert spotter.headers('Millimeters')[1] == 'X (mm)'
    assert spotter.headers('Feet', origin=(0, 0, 0))[1] == 'X from origin (ft)'


def test_display_and_data_rows():
    rows = spotter.display_rows(POINTS, 'Millimeters')
    assert rows[0][:4] == ['P1', '12.000 mm', '3.500 mm', '0.000 mm']
    assert rows[0][4:] == ['0.012 m', '0.004 m', '0.000 m', 'Basic Wall', 'ARCH.nwc']
    data = spotter.data_rows(POINTS, 'Feet')
    assert data[1][:4] == ['P2', -1.25, 0.0, 2.75]
    assert approx(data[1][4], -0.381) and data[1][7:] == ['', '']


def test_tsv_and_csv():
    head = ['Point', 'X']
    text = spotter.tsv(head, [['P1', 1.5], ['P2', 'a\tb']])
    assert text == 'Point\tX\r\nP1\t1.5\r\nP2\ta b\r\n'
    csv_text = spotter.csv_text(head, [['P1', 'Wall, basic']])
    assert csv_text == 'Point,X\r\nP1,"Wall, basic"\r\n'


def test_parse_xyz_forms():
    assert spotter.parse_xyz('12.5, 3, 0', 'Meters') == (12.5, 3.0, 0.0)
    assert spotter.parse_xyz('X=1 Y=-2 Z=3', 'Meters') == (1.0, -2.0, 3.0)
    assert spotter.parse_xyz('[4; 5; 6]', 'Meters') == (4.0, 5.0, 6.0)
    feet = spotter.parse_xyz("10' 6\", -4', 0", 'Feet')
    assert approx(feet, (10.5, -4.0, 0.0))
    assert spotter.parse_xyz('2.5m, 1m, 0', 'Millimeters') == (2500.0, 1000.0, 0.0)
    for bad in ('1, 2', '1, 2, 3, 4', 'a, b, c', '', None):
        assert spotter.parse_xyz(bad, 'Meters') is None


def test_marker_geometry():
    segs = spotter.marker_segments((1.0, 2.0, 3.0), 0.5)
    assert segs[0] == ((0.5, 2.0, 3.0), (1.5, 2.0, 3.0), False)
    assert len(segs) == 3
    assert approx(spotter.marker_size('Meters'), 0.25)
    assert approx(spotter.marker_size('Millimeters'), 250.0)
    big = ((0.0, 0.0, 0.0), (1000.0, 0.0, 0.0))
    assert approx(spotter.marker_size('Meters', big), 1.0)          # capped at 1 m
    assert approx(spotter.marker_size('Meters', ((0.0, 0.0, 0.0), (200.0, 0.0, 0.0))), 0.4)
    # one stray object at the origin, the site 1,370,000 ft away: still a 1 m cross
    far = ((0.0, 0.0, 0.0), (1370000.0, 1370000.0, 100.0))
    assert approx(spotter.marker_size('Feet', far), 1.0 / 0.3048)
