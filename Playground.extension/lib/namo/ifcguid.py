# -*- coding: utf-8 -*-
"""IFC GlobalIds: the 22-character compressed form of a GUID, and Revit's export rule.

    ifcguid.compress('00000000-0000-0000-0000-000000000000')   # '0000000000000000000000'
    ifcguid.expand('3$$$$$$$$$$$$$$$$$$$$$')                    # 'ffffffff-ffff-ffff-ffff-ffffffffffff'
    ifcguid.from_revit_unique_id(element_unique_id)             # what Revit's IFC exporter writes
    ifcguid.new() ; ifcguid.is_valid(text)

A GUID is a 128-bit number written as 32 hex digits in its canonical string order. IFC
writes the same number in base 64 with the alphabet 0-9 A-Z a-z _ $ : 22 digits, the
first carrying only 2 bits (so it is 0..3). This equals the bytes-of-the-GUID-string
order used by IfcOpenShell and by Revit's IFC exporter (GUIDUtil.ConvertToIFCGuid,
which reassembles Guid.ToByteArray() back into string order).

Revit's export GUID for an element: its UniqueId is '<36-char episode GUID>-<8 hex
element id>'; the exporter XORs the last 8 hex digits of the episode GUID with the
element id and uses the result as the GUID (ExportUtils.GetExportId), then compresses it.
Elements whose IFC GUID was overridden by an 'IfcGUID' parameter in Revit carry that
value instead; read the property when present (namo.items.revit_ids) and use this only
as the fallback.

Pure stdlib.
"""
import re
import uuid

ALPHABET = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_$'
_INDEX = dict((ch, i) for i, ch in enumerate(ALPHABET))
_HEX32 = re.compile(r'^[0-9a-fA-F]{32}$')


def _hex32(uuid_text):
    """The 32 hex digits of a GUID in any common spelling (braces, hyphens, urn:uuid:,
    any case). ValueError when it is not one."""
    text = str(uuid_text or '').strip()
    if text.lower().startswith('urn:uuid:'):
        text = text[9:]
    text = text.strip('{}()').replace('-', '')
    if not _HEX32.match(text):
        raise ValueError('Not a GUID: %r' % (uuid_text,))
    return text.lower()


def _format_uuid(hex32):
    h = hex32.lower()
    return '%s-%s-%s-%s-%s' % (h[0:8], h[8:12], h[12:16], h[16:20], h[20:32])


def compress(uuid_text):
    """22-character IFC GlobalId for a GUID (hyphens/braces optional). ValueError for
    anything that is not a GUID."""
    number = int(_hex32(uuid_text), 16)
    digits = []
    for _ in range(22):
        digits.append(ALPHABET[number % 64])
        number //= 64
    return ''.join(reversed(digits))


def expand(ifc):
    """The GUID ('8-4-4-4-12', lowercase) of a 22-character IFC GlobalId. ValueError when
    it is not a valid GlobalId."""
    if not is_valid(ifc):
        raise ValueError('Not an IFC GlobalId: %r' % (ifc,))
    number = 0
    for ch in str(ifc).strip():
        number = number * 64 + _INDEX[ch]
    return _format_uuid('%032x' % number)


def is_valid(text):
    """True for a 22-character IFC GlobalId (alphabet 0-9A-Za-z_$, first digit 0..3)."""
    if text is None:
        return False
    text = str(text).strip()
    if len(text) != 22 or text[0] not in '0123':
        return False
    for ch in text:
        if ch not in _INDEX:
            return False
    return True


def new():
    """A random (version 4) IFC GlobalId."""
    return compress(uuid.uuid4().hex)


def revit_export_guid(unique_id):
    """Revit's export GUID ('8-4-4-4-12') for an element UniqueId
    ('<episode GUID>-<8 hex element id>'): the episode's last 8 hex digits XOR the
    element id. ValueError when unique_id does not have that shape."""
    text = str(unique_id or '').strip()
    match = re.match(r'^([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-'
                     r'[0-9a-fA-F]{12})-([0-9a-fA-F]{8})$', text)
    if not match:
        raise ValueError('Not a Revit UniqueId: %r' % (unique_id,))
    episode = match.group(1).lower()
    element = int(match.group(2), 16)
    last = int(episode[28:36], 16)
    return episode[:28] + '%08x' % (last ^ element)


def from_revit_unique_id(unique_id):
    """The IFC GlobalId Revit's IFC exporter writes for an element with this UniqueId
    (unless the element's IfcGUID parameter overrides it). ValueError for a malformed id."""
    return compress(revit_export_guid(unique_id))
