# -*- coding: utf-8 -*-
"""namo.ifcguid: IFC GlobalId compression and Revit's export GUID rule."""
import uuid

from _compat import raises

from namo import ifcguid


def test_known_vectors():
    assert ifcguid.compress('00000000-0000-0000-0000-000000000000') == '0000000000000000000000'
    assert ifcguid.compress('ffffffff-ffff-ffff-ffff-ffffffffffff') == '3$$$$$$$$$$$$$$$$$$$$$'
    assert ifcguid.compress('00000000-0000-0000-0000-000000000001') == '0000000000000000000001'
    assert ifcguid.compress('00000000-0000-0000-0000-00000000003f') == '000000000000000000000$'
    assert ifcguid.compress('00000000-0000-0000-0000-000000000040') == '0000000000000000000010'
    assert ifcguid.expand('0000000000000000000000') == '00000000-0000-0000-0000-000000000000'
    assert ifcguid.expand('3$$$$$$$$$$$$$$$$$$$$$') == 'ffffffff-ffff-ffff-ffff-ffffffffffff'


def test_accepts_common_guid_spellings():
    plain = 'b1e2a3c4-d5e6-47f8-9a0b-1c2d3e4f5a6b'
    expected = ifcguid.compress(plain)
    for spelling in (plain.upper(), '{%s}' % plain, plain.replace('-', ''), 'urn:uuid:' + plain,
                     ' %s ' % plain):
        assert ifcguid.compress(spelling) == expected, spelling
    for bad in ('', None, 'xyz', plain[:-1], plain + '0', 'g' * 32):
        raises(ValueError, ifcguid.compress, bad)


def test_round_trips():
    for _ in range(200):
        u = uuid.uuid4()
        packed = ifcguid.compress(str(u))
        assert len(packed) == 22 and ifcguid.is_valid(packed)
        assert ifcguid.expand(packed) == str(u)
    for _ in range(50):
        packed = ifcguid.new()
        assert ifcguid.is_valid(packed)
        assert ifcguid.compress(ifcguid.expand(packed)) == packed


def test_matches_independent_bit_packing():
    # Revit's ConvertToIFCGuid packs the GUID's string-order bytes as 8 bits + 5 x 24 bits.
    u = uuid.UUID('3f2504e0-4f89-11d3-9a0c-0305e82c3301')
    data = bytearray(u.bytes)                     # big-endian, string order
    nums = [data[0]] + [(data[i] << 16) | (data[i + 1] << 8) | data[i + 2] for i in range(1, 16, 3)]
    chars = []
    for index, num in enumerate(nums):
        width = 2 if index == 0 else 4
        part = []
        for _ in range(width):
            part.append(ifcguid.ALPHABET[num % 64])
            num //= 64
        chars.append(''.join(reversed(part)))
    assert ifcguid.compress(str(u)) == ''.join(chars)


def test_is_valid():
    assert ifcguid.is_valid('0000000000000000000000')
    assert ifcguid.is_valid('3$$$$$$$$$$$$$$$$$$$$$')
    assert not ifcguid.is_valid('4$$$$$$$$$$$$$$$$$$$$$')         # first digit carries 2 bits
    assert not ifcguid.is_valid('000000000000000000000')           # 21 chars
    assert not ifcguid.is_valid('000000000000000000000-')          # '-' not in the alphabet
    assert not ifcguid.is_valid(None)
    raises(ValueError, ifcguid.expand, 'nope')


def test_revit_export_guid_xors_the_element_id():
    unique_id = '00000000-0000-0000-0000-0000000000ff-0000000f'
    assert ifcguid.revit_export_guid(unique_id) == '00000000-0000-0000-0000-0000000000f0'
    unique_id = '60f91daf-3dd7-4283-a86d-24137b73f3da-0001fd0b'
    assert ifcguid.revit_export_guid(unique_id) == '60f91daf-3dd7-4283-a86d-24137b720ed1'
    assert ifcguid.from_revit_unique_id(unique_id) == \
        ifcguid.compress('60f91daf-3dd7-4283-a86d-24137b720ed1')
    assert ifcguid.from_revit_unique_id(unique_id.upper()) == ifcguid.from_revit_unique_id(unique_id)
    for bad in ('', None, '60f91daf-3dd7-4283-a86d-24137b73f3da', 'x' * 45,
                '60f91daf-3dd7-4283-a86d-24137b73f3da-0001fd0'):
        raises(ValueError, ifcguid.from_revit_unique_id, bad)
