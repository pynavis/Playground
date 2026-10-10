# -*- coding: utf-8 -*-
"""namo.field_qr payload checks, and the pick route of the Field panel's scripts."""
import io
import os

import _compat  # noqa: F401 (puts lib on the path)
from namo import field_qr

HERE = os.path.dirname(os.path.abspath(__file__))
FIELD = os.path.join(os.path.dirname(os.path.dirname(HERE)), 'Playground.extension', 'Project.tab')


def test_repeated_payloads_counts_codes_that_scan_the_same():
    assert field_qr.repeated_payloads(['a|1', 'a|2', 'a|3']) == 0
    # Objects with no Element ID or GUID all render to the same text: three codes, one payload.
    assert field_qr.repeated_payloads(['Tower|T.nwf||', 'Tower|T.nwf||', 'Tower|T.nwf||', 'x']) == 2
    assert field_qr.repeated_payloads([]) == 0


def test_no_script_of_the_group_uses_the_custom_pick_tool():
    # Regression: Photo Pins called pynavis.pick.point, whose hover marker and hit
    # disagreed in the field. Every click in the view goes through namo.picking.
    banned = ('pick.point(', 'pick.point_then(', 'pick.Unavailable')
    seen = 0
    for panel in ('4D.panel', 'Quantities.panel', 'Field.panel'):
        for folder, _dirs, files in os.walk(os.path.join(FIELD, panel)):
            for name in files:
                if not name.endswith('.py'):
                    continue
                seen += 1
                with io.open(os.path.join(folder, name), encoding='utf-8') as handle:
                    text = handle.read()
                for word in banned:
                    assert word not in text.replace('picking.point(', ''), (name, folder, word)
    assert seen >= 14
    with io.open(os.path.join(FIELD, 'Field.panel', 'Photo_Pins.pushbutton', 'script.py'),
                 encoding='utf-8') as handle:
        assert 'picking.point(' in handle.read()
