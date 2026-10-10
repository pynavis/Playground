# -*- coding: utf-8 -*-
"""namo.find_repair (Search-In Repair) and namo.find_sets (the set tree helpers)."""
import _compat

from namo import find_repair as fr
from namo import find_sets as fs


def test_classify():
    assert fr.classify({'is_clear': True, 'sources': [], 'explicit': None, 'resolved': 0}) == 'empty'
    assert fr.classify({'is_clear': False, 'sources': [], 'explicit': 0, 'resolved': 0}) == 'empty'
    assert fr.classify({'sources': [('Arch.nwc', 0)], 'resolved': 0}) == 'missing'
    assert fr.classify({'sources': [('Arch.nwc', 3), ('Old.nwc', 0)], 'resolved': 3}) == 'partial'
    assert fr.classify({'sources': [('everything', 4)], 'resolved': 4}) == 'ok'
    # one source that reports nothing while the scope as a whole resolves: trust the whole
    assert fr.classify({'sources': [('everything', None)], 'resolved': 4}) == 'ok'
    assert fr.classify({'sources': [], 'explicit': 12, 'resolved': 12}) == 'ok'


def test_pointed_text():
    assert fr.pointed_text({'sources': [('A.nwc', 0), ('B.nwc', 1)]}) == 'A.nwc; B.nwc'
    assert fr.pointed_text({'sources': [], 'explicit': 1204}) == '1,204 items'
    assert fr.pointed_text({}) == 'Nothing'
    long = fr.pointed_text({'sources': [('x' * 200, 0)]}, limit=20)
    assert len(long) == 20 and long.endswith('...')


def test_match_models():
    names = ['Arch.nwc', 'Arch-L1.nwc', 'MEP_Duct.nwc', 'Site.ifc']
    assert fr.match_models(['C:\\Old\\Arch-L1.rvt > Level 1'], names) == ['Arch-L1.nwc']
    assert fr.match_models(['arch.nwc/Walls', 'mep_duct'], names) == ['Arch.nwc', 'MEP_Duct.nwc']
    assert fr.match_models(['Archive.nwc'], names) == []          # whole names only
    assert fr.match_models([''], names) == []
    assert fr.match_models(['SITE.IFC'], names) == ['Site.ifc']


def test_scope_label_and_rows():
    assert fr.scope_label(fr.WHOLE) == 'Whole model'
    assert fr.scope_label([]) == 'No models'
    assert fr.scope_label(['A', 'B', 'C', 'D']) == 'A, B and 2 more'
    entries = [{'guid': 'g', 'name': 'Ducts', 'folder': 'F', 'status': 'missing',
                'pointed': 'Old.nwc', 'suggest': None},
               {'guid': 'h', 'name': 'Pipes', 'folder': '', 'status': 'repaired',
                'pointed': 'x', 'suggest': ['MEP.nwc'], 'after': 'MEP.nwc'}]
    rows = fr.table_rows(entries)
    assert rows[0]['cells'][2:5] == ['Points at missing items', 'Old.nwc', 'No file name to match']
    assert rows[1]['cells'][4:] == ['MEP.nwc', 'MEP.nwc']
    assert fr.status_line(entries, 30) == '1 of 30 search sets need a new Search In scope; 1 repaired'


ROWS = [
    {'guid': '1', 'key': '0', 'parent_key': '', 'name': 'By Level', 'depth': 0, 'is_folder': True,
     'has_search': False},
    {'guid': '2', 'key': '0/0', 'parent_key': '0', 'name': 'Level 1', 'depth': 1, 'is_folder': False,
     'has_search': True},
    {'guid': '3', 'key': '0/1', 'parent_key': '0', 'name': 'In/Out', 'depth': 1, 'is_folder': True,
     'has_search': False},
    {'guid': '4', 'key': '0/1/0', 'parent_key': '0/1', 'name': 'Doors', 'depth': 2, 'is_folder': False,
     'has_search': False},
    {'guid': '5', 'key': '1', 'parent_key': '', 'name': 'Loose', 'depth': 0, 'is_folder': False,
     'has_search': True},
]


def test_find_sets_paths():
    assert fs.escape('In/Out') == 'In\\/Out'
    assert fs.join('', 'A/B') == 'A\\/B'
    assert fs.join('F', 'x') == 'F/x'
    rows = fs.set_rows(ROWS)
    assert [(r['folder'], r['name'], r['path']) for r in rows] == [
        ('By Level', 'Level 1', 'By Level/Level 1'), ('By Level/In\\/Out', 'Doors', 'By Level/In\\/Out/Doors'),
        ('', 'Loose', 'Loose')]
    assert fs.folder_paths(ROWS) == ['By Level', 'By Level/In\\/Out']
    assert fs.existing_index(ROWS)[('by level/in\\/out', 'doors')] == '4'
    assert fs.plain_folder('By Level/In\\/Out') == 'By Level/In/Out'


def test_find_sets_names_and_kinds():
    assert fs.unique_among('Level 1', ['level 1', 'Level 1 (2)']) == 'Level 1 (3)'
    assert fs.unique_among('New', []) == 'New'
    assert fs.is_query({'or': []})
    assert not fs.is_query([1, 2])
