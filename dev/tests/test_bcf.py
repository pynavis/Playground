# -*- coding: utf-8 -*-
"""namo.bcf: BCF 2.1 / 3.0 writing (element order, required parts, version rules), reading
of 2.0 / 2.1 / 3.0 (hand-written samples in the shapes other tools produce), round trips,
the structure checker, and (CPython with lxml) validation against XSDs reconstructed from
the buildingSMART BCF-XML release_2_1 / release_3_0 schemas."""
import datetime
import io
import zipfile

import _compat
from _compat import raises

from namo import bcf, issues

CREATED = datetime.datetime(2026, 10, 5, 14, 30, 0)
T1 = '3f2504e0-4f89-41d3-9a0c-0305e82c3301'
T2 = '9a7b1c2d-0000-4abc-8def-1234567890ab'
VP1 = 'aaaaaaaa-1111-4222-8333-444444444444'
C1 = 'cccccccc-1111-4222-8333-444444444444'
PNG = b'\x89PNG\r\n\x1a\n' + b'\x00' * 24
JPG = b'\xff\xd8\xff\xe0' + b'\x00' * 24


def _topic(**over):
    topic = {
        'guid': T1, 'type': 'RFI', 'status': 'Open', 'title': 'Duct hits beam & pipe <L2>',
        'priority': 'High', 'index': 12, 'labels': ['Mechanical', 'Level 2'],
        'creation_date': '2026-10-01T08:00:00', 'creation_author': 'amol',
        'modified_date': '2026-10-04T09:15:00', 'modified_author': 'jane',
        'due_date': '2026-10-12', 'assigned_to': 'Jane', 'description': 'Line one\nLine two',
        'reference_links': ['https://example.com/rfi/12'], 'related_topics': [T2],
        'document_references': [],
        'comments': [{'guid': C1, 'date': '2026-10-02T10:00:00', 'author': 'jane',
                      'comment': 'Looking at it', 'viewpoint_guid': VP1}],
        'viewpoints': [{'guid': VP1, 'snapshot_data': PNG, 'visinfo': {
            'camera': {'type': 'PerspectiveCamera', 'CameraViewPoint': (12.5, -3.25, 4.0),
                       'CameraDirection': (0.0, 1.0, 0.0), 'CameraUpVector': (0.0, 0.0, 1.0),
                       'FieldOfView': 50.0, 'AspectRatio': 1.6},
            'selection': [{'ifc_guid': '2O2Fr$t4X7Zf8NOew3FLOH', 'authoring_tool_id': '123456',
                           'originating_system': 'Autodesk Revit'},
                          {'ifc_guid': 'bad'}],
            'visibility': {'default': True, 'exceptions': []},
            'clipping_planes': [{'location': (1.0, 2.0, 3.0), 'direction': (0.0, 0.0, -1.0)}],
            'lines': [{'start': (0.0, 0.0, 0.0), 'end': (1.0, 1.0, 1.0)}]}}],
    }
    topic.update(over)
    return topic


def _zip_entries(data):
    return sorted(zipfile.ZipFile(io.BytesIO(data)).namelist())


# ---- writing -----------------------------------------------------------------------------


def test_package_layout_21():
    data, report = bcf.package([_topic()], '2.1', {'name': 'Tower'}, created=CREATED)
    assert _zip_entries(data) == sorted(['bcf.version', 'project.bcfp', T1 + '/markup.bcf',
                                         T1 + '/snapshot.png', T1 + '/viewpoint.bcfv'])
    assert report['topics'] == 1 and report['viewpoints'] == 1 and report['snapshots'] == 1
    assert any('without a valid IFC GlobalId' in n for n in report['notes'])
    found = bcf.check(data)
    assert found['errors'] == [] and found['version'] == '2.1' and found['topics'] == 1


def test_package_layout_30_with_documents():
    doc_guid = 'dddddddd-1111-4222-8333-444444444444'
    topic = _topic(document_references=[{'guid': 'eeeeeeee-1111-4222-8333-444444444444',
                                         'document_guid': doc_guid, 'description': 'Site photo'}])
    data, report = bcf.package([topic], '3.0', {'name': 'Tower'}, created=CREATED,
                               documents=[{'guid': doc_guid, 'filename': 'photo.jpg',
                                           'description': 'Photo', 'data': JPG}],
                               extensions={'statuses': issues.STATUSES})
    names = _zip_entries(data)
    assert 'extensions.xml' in names and 'documents.xml' in names
    assert 'documents/' + doc_guid in names
    assert report['documents'] == 1
    found = bcf.check(data)
    assert found['errors'] == [] and found['version'] == '3.0'
    z = zipfile.ZipFile(io.BytesIO(data))
    ext = z.read('extensions.xml').decode('utf-8')
    assert '<TopicStatus>Void</TopicStatus>' in ext and '<user>jane</user>' in ext.lower()


def test_markup_order_21_and_30():
    t21 = bcf.markup_xml(dict(_topic(), viewpoints=[]), '2.1').decode('utf-8')
    order = ['<ReferenceLink>', '<Title>', '<Priority>', '<Index>', '<Labels>', '<CreationDate>',
             '<CreationAuthor>', '<ModifiedDate>', '<ModifiedAuthor>', '<DueDate>', '<AssignedTo>',
             '<Description>', '<RelatedTopic ', '</Topic>', '<Comment Guid']
    positions = [t21.index(tag) for tag in order]
    assert positions == sorted(positions)
    assert '&amp; pipe &lt;L2&gt;' in t21
    assert '<DueDate>2026-10-12T00:00:00</DueDate>' in t21
    assert t21.count('<Labels>') == 2
    t30 = bcf.markup_xml(dict(_topic(), viewpoints=[{'guid': VP1, 'viewpoint': 'viewpoint.bcfv',
                                                     'snapshot': 'snapshot.png', 'index': 0}]),
                         '3.0').decode('utf-8')
    order = ['<ReferenceLinks>', '<Title>', '<Priority>', '<Labels>', '<Label>', '<CreationDate>',
             '<DueDate>', '<Description>', '<RelatedTopics>', '<Comments>', '<Viewpoints>',
             '<ViewPoint ', '</Topic>']
    positions = [t30.index(tag) for tag in order]
    assert positions == sorted(positions)
    assert '<Index>12</Index>' not in t30                       # Topic Index only in 2.1
    assert 'TopicType="RFI"' in t30 and 'TopicStatus="Open"' in t30


def test_30_requires_type_and_status():
    text = bcf.markup_xml(dict(_topic(type='', status=''), viewpoints=[]), '3.0').decode('utf-8')
    assert 'TopicType="Issue"' in text and 'TopicStatus="Open"' in text
    text = bcf.markup_xml(dict(_topic(type='', status=''), viewpoints=[]), '2.1').decode('utf-8')
    assert 'TopicType' not in text and 'TopicStatus' not in text


def test_visinfo_camera_rules():
    notes = []
    wide = {'type': 'PerspectiveCamera', 'CameraViewPoint': (0, 0, 0), 'CameraDirection': (1, 0, 0),
            'CameraUpVector': (0, 0, 1), 'FieldOfView': 75.0}
    text = bcf.visinfo_xml({'guid': VP1, 'camera': wide}, '2.1', notes).decode('utf-8')
    assert '<FieldOfView>60</FieldOfView>' in text and 'AspectRatio' not in text
    assert 'clamped' in notes[0]
    notes = []
    text = bcf.visinfo_xml({'guid': VP1, 'camera': wide}, '3.0', notes).decode('utf-8')
    assert '<FieldOfView>75</FieldOfView>' in text
    assert text.index('<FieldOfView>') < text.index('<AspectRatio>')
    assert 'Aspect ratio not known' in notes[0]
    ortho = {'type': 'OrthogonalCamera', 'CameraViewPoint': (0, 0, 10), 'CameraDirection': (0, 0, -1),
             'CameraUpVector': (0, 1, 0), 'ViewToWorldScale': 25.0, 'AspectRatio': 2.0}
    text = bcf.visinfo_xml({'guid': VP1, 'camera': ortho}, '3.0').decode('utf-8')
    assert '<OrthogonalCamera>' in text and '<ViewToWorldScale>25</ViewToWorldScale>' in text
    assert text.index('<ViewToWorldScale>') < text.index('<AspectRatio>2</AspectRatio>')
    empty = bcf.visinfo_xml({'guid': VP1}, '2.1').decode('utf-8')
    assert '<Components>' not in empty and 'Camera' not in empty


def test_components_need_visibility():
    text = bcf.visinfo_xml({'guid': VP1, 'selection': [{'ifc_guid': '0000000000000000000000'}]},
                           '2.1').decode('utf-8')
    assert text.index('<Selection>') < text.index('<Visibility DefaultVisibility="true" />')
    hidden = bcf.visinfo_xml({'guid': VP1, 'visibility': {'default': False, 'exceptions': [
        {'ifc_guid': '0000000000000000000000'}]}}, '3.0').decode('utf-8')
    assert '<Visibility DefaultVisibility="false">' in hidden and '<Exceptions>' in hidden


def test_numbers_dates_and_guids():
    assert bcf.num(0.0) == '0' and bcf.num(-0.0) == '0'
    assert bcf.num(1.5) == '1.5' and bcf.num(500000.123456) == '500000.123456'
    assert bcf.num(1e-15) == '0.000000000000' or float(bcf.num(1e-15)) == 0.0
    assert bcf.guid('{3F2504E0-4F89-41D3-9A0C-0305E82C3301}') == T1
    assert bcf.guid('3F2504E04F8941D39A0C0305E82C3301') == T1
    assert bcf.GUID_RE.match(bcf.guid('nonsense'))
    assert bcf.project_guid('Tower') == bcf.project_guid('tower')
    stamp = bcf.xs_datetime('2026-10-05T14:30:00')
    assert stamp.endswith('Z') and len(stamp) == 20
    from namo import dates
    assert dates.parse(stamp) == datetime.datetime(2026, 10, 5, 14, 30, 0)   # round trip
    assert bcf.xs_datetime('') == '' and bcf.xs_datetime('garbage') == ''
    assert bcf.xs_date_only('12/10/2026') == '2026-10-12T00:00:00'
    raises(ValueError, bcf.version_xml, '2.0')


def test_jpeg_snapshot_named_by_type():
    topic = _topic()
    topic['viewpoints'][0]['snapshot_data'] = JPG
    data, report = bcf.package([topic], '2.1', created=CREATED)
    assert T1 + '/snapshot.jpg' in _zip_entries(data)
    assert any('JPEG snapshot' in n for n in report['notes'])
    data, report = bcf.package([topic], '3.0', created=CREATED)
    assert not any('JPEG snapshot' in n for n in report['notes'])


def test_second_viewpoint_names_and_duplicate_topics():
    topic = _topic()
    topic['viewpoints'].append({'guid': 'bbbbbbbb-1111-4222-8333-444444444444', 'snapshot_data': PNG,
                                'visinfo': {}})
    data, report = bcf.package([topic, dict(topic)], '2.1', created=CREATED)
    names = _zip_entries(data)
    assert T1 + '/bbbbbbbb-1111-4222-8333-444444444444.bcfv' in names
    assert T1 + '/bbbbbbbb-1111-4222-8333-444444444444.png' in names
    assert report['topics'] == 1 and any('appears twice' in n for n in report['notes'])


def test_comment_viewpoint_refs_name_written_viewpoints():
    # Comments brought in from another BCF keep that file's viewpoint guid; a re-export
    # writes fresh viewpoints, so a stale reference is dropped instead of left dangling.
    stale = 'dddddddd-1111-4222-8333-444444444444'
    comments = [{'guid': C1, 'date': '2026-10-02T10:00:00', 'author': 'jane',
                 'comment': 'From the old file', 'viewpoint_guid': stale},
                {'guid': 'cccccccc-2222-4222-8333-444444444444', 'date': '2026-10-03T10:00:00',
                 'author': 'kim', 'comment': 'This view', 'viewpoint_guid': VP1}]
    for version in bcf.VERSIONS:
        data, _report = bcf.package([_topic(comments=comments)], version, {'name': 'Tower'},
                                    created=CREATED)
        back = bcf.read(data)['topics'][0]
        assert [c['viewpoint_guid'] for c in back['comments']] == ['', VP1]
        assert [c['comment'] for c in back['comments']] == ['From the old file', 'This view']
        assert bcf.check(data)['errors'] == []


def test_deterministic_bytes():
    a, _ = bcf.package([_topic()], '2.1', {'name': 'Tower'}, created=CREATED)
    b, _ = bcf.package([_topic()], '2.1', {'name': 'Tower'}, created=CREATED)
    assert a == b


# ---- round trips ---------------------------------------------------------------------------


def _round_trip(version):
    data, _report = bcf.package([_topic(), _topic(guid=T2, title='Second', index=13,
                                                  related_topics=[], viewpoints=[], comments=[])],
                                version, {'name': 'Tower', 'id': T2}, created=CREATED)
    back = bcf.read(data)
    assert back['version'] == version
    assert back['project']['name'] == 'Tower' and back['project']['id'] == T2
    assert [t['guid'] for t in back['topics']] == [T1, T2]
    t = back['topics'][0]
    original = _topic()
    for key in ('type', 'status', 'title', 'priority', 'labels', 'creation_author',
                'modified_author', 'assigned_to', 'description', 'reference_links',
                'related_topics'):
        assert t[key] == original[key], key
    from namo import dates
    assert dates.parse(t['creation_date']) == dates.parse(original['creation_date'])
    assert dates.parse(t['modified_date']) == dates.parse(original['modified_date'])
    assert t['due_date'].startswith('2026-10-12')
    assert t['comments'][0]['guid'] == C1 and t['comments'][0]['comment'] == 'Looking at it'
    assert t['comments'][0]['viewpoint_guid'] == VP1
    vp = t['viewpoints'][0]
    assert vp['guid'] == VP1 and vp['snapshot_data'] == PNG
    cam = vp['visinfo']['camera']
    assert cam['type'] == 'PerspectiveCamera'
    assert _compat.approx(cam['CameraViewPoint'], (12.5, -3.25, 4.0))
    assert _compat.approx(cam['FieldOfView'], 50.0)
    sel = vp['visinfo']['selection']
    assert sel == [{'ifc_guid': '2O2Fr$t4X7Zf8NOew3FLOH', 'authoring_tool_id': '123456',
                    'originating_system': 'Autodesk Revit'}]
    assert vp['visinfo']['clipping_planes'][0]['direction'] == (0.0, 0.0, -1.0)
    assert vp['visinfo']['lines'][0]['end'] == (1.0, 1.0, 1.0)
    return back


def test_round_trip_21():
    back = _round_trip('2.1')
    assert back['topics'][0]['index'] == 12
    assert back['topics'][0]['viewpoints'][0]['visinfo']['camera']['AspectRatio'] is None


def test_round_trip_30():
    back = _round_trip('3.0')
    assert back['topics'][0]['viewpoints'][0]['visinfo']['camera']['AspectRatio'] == 1.6
    assert 'RFI' in back['extensions']['types']


def test_issue_round_trip_through_bcf():
    issue = issues.new_issue({'title': 'Pipe through beam', 'type': 'Clash', 'trade': 'Plumbing',
                              'priority': 'Critical', 'due': '2026-10-20', 'assignee': 'Jane',
                              'labels': ['L3'], 'camera': {
                                  'position': [100.0, 50.0, 10.0], 'rotation': None,
                                  'direction': [0.6, 0.8, 0.0], 'up': [0, 0, 1],
                                  'projection': 'persp', 'height_field': 0.8, 'aspect': 1.5},
                              'camera_units': 'Feet'}, 'amol', CREATED)
    issue['id'], issue['number'] = 'CLA-004', 4
    issue = issues.add_comment_to(issue, 'Please reroute', 'kim', CREATED)
    topic = issues.to_topic(issue, unit_to_m=0.3048)
    for version in bcf.VERSIONS:
        back = bcf.read(bcf.package([topic], version, created=CREATED)[0])['topics'][0]
        made = issues.from_topic(back, None, ['Plumbing'])
        assert made['action'] == 'create'
        f = made['fields']
        assert (f['title'], f['type'], f['priority'], f['trade'], f['assignee'], f['due']) == \
            ('Pipe through beam', 'Clash', 'Critical', 'Plumbing', 'Jane', '2026-10-20')
        assert f['labels'] == ['L3']
        assert made['new_comments'][0]['text'] == 'Please reroute'
        from namo import camera
        cam = camera.from_bcf(made['camera'], 1 / 0.3048)
        assert _compat.approx(cam['position'], (100.0, 50.0, 10.0), 1e-9)
        assert _compat.approx(cam['direction'], (0.6, 0.8, 0.0), 1e-9)
        again = issues.from_topic(back, dict(issue), ['Plumbing'])
        assert again['new_comments'] == []                    # same guids: no duplicates


# ---- hand-written samples ------------------------------------------------------------------

SAMPLE_20_MARKUP = u'''<?xml version="1.0" encoding="utf-8"?>
<Markup xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema">
  <Header>
    <File IfcProject="0M6o7Znnv7hxsbWgeu7oQq" isExternal="true">
      <Filename>Tower.ifc</Filename>
      <Date>2014-10-27T16:27:27Z</Date>
    </File>
  </Header>
  <Topic Guid="A245DD8E-5E4F-4C6A-8F3B-6F7B2A43A111" TopicType="Error" TopicStatus="Active">
    <ReferenceLink />
    <Title>Wall in the way</Title>
    <Labels>Architecture</Labels>
    <CreationDate>2014-10-16T13:10:56+02:00</CreationDate>
    <CreationAuthor>Architect@example.com</CreationAuthor>
    <AssignedTo>MEP@example.com</AssignedTo>
    <Description>Move the wall</Description>
  </Topic>
  <Comment Guid="780FAE52-C432-42BE-ADEA-FF3E7A8CD8E1">
    <VerbalStatus>Active</VerbalStatus>
    <Status>Error</Status>
    <Date>2014-10-16T13:10:56+02:00</Date>
    <Author>Architect@example.com</Author>
    <Comment>Please fix</Comment>
    <Topic Guid="A245DD8E-5E4F-4C6A-8F3B-6F7B2A43A111" />
  </Comment>
</Markup>'''

SAMPLE_20_VISINFO = u'''<?xml version="1.0" encoding="utf-8"?>
<VisualizationInfo xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema">
  <Components>
    <Component IfcGuid="2MF28NhmDBiRVyFakgdbCT" Selected="true" Visible="true">
      <OriginatingSystem>Revit</OriginatingSystem>
      <AuthoringToolId>291523</AuthoringToolId>
    </Component>
    <Component IfcGuid="1wnyQgUm9Ewh$CeuWdpHTm" Selected="false" Visible="false" />
  </Components>
  <PerspectiveCamera>
    <CameraViewPoint><X>-4.3</X><Y>3.2</Y><Z>1.7</Z></CameraViewPoint>
    <CameraDirection><X>0.7</X><Y>-0.7</Y><Z>0</Z></CameraDirection>
    <CameraUpVector><X>0</X><Y>0</Y><Z>1</Z></CameraUpVector>
    <FieldOfView>60</FieldOfView>
  </PerspectiveCamera>
</VisualizationInfo>'''

SAMPLE_21_MARKUP = u'''<?xml version="1.0" encoding="UTF-8"?>
<Markup>
  <Topic Guid="5c3e2e46-3a83-4d4a-8f8e-9d3b8f2b1a01" TopicType="Clash" TopicStatus="Closed">
    <Title>Duct vs beam</Title>
    <Priority>Critical</Priority>
    <Index>3</Index>
    <Labels>Structure</Labels>
    <Labels>Level 4</Labels>
    <CreationDate>2026-09-30T10:00:00Z</CreationDate>
    <CreationAuthor>solibri@example.com</CreationAuthor>
    <ModifiedDate>2026-10-02T11:00:00Z</ModifiedDate>
    <ModifiedAuthor>bob@example.com</ModifiedAuthor>
    <DueDate>2026-10-10T00:00:00Z</DueDate>
    <AssignedTo>bob@example.com</AssignedTo>
    <Description>Lower the duct</Description>
  </Topic>
  <Comment Guid="7d4b2c1e-0000-4000-8000-000000000001">
    <Date>2026-10-01T09:00:00Z</Date>
    <Author>bob@example.com</Author>
    <Comment>Done</Comment>
    <Viewpoint Guid="6d4b2c1e-0000-4000-8000-000000000001" />
  </Comment>
  <Viewpoints Guid="6d4b2c1e-0000-4000-8000-000000000001">
    <Viewpoint>Viewpoint_6d4b.bcfv</Viewpoint>
    <Snapshot>Snapshot_6d4b.png</Snapshot>
  </Viewpoints>
</Markup>'''

SAMPLE_21_VISINFO = u'''<?xml version="1.0" encoding="UTF-8"?>
<VisualizationInfo Guid="6d4b2c1e-0000-4000-8000-000000000001">
  <Components>
    <ViewSetupHints SpacesVisible="false" SpaceBoundariesVisible="false" OpeningsVisible="false" />
    <Selection>
      <Component IfcGuid="3b2hZ3G8n0ZvRfJrO1x$Yk" />
    </Selection>
    <Visibility DefaultVisibility="true">
      <Exceptions><Component IfcGuid="0vFL9wTnX7aQ2eGbYp1$Zz" /></Exceptions>
    </Visibility>
    <Coloring>
      <Color Color="FF0000"><Component IfcGuid="3b2hZ3G8n0ZvRfJrO1x$Yk" /></Color>
    </Coloring>
  </Components>
  <OrthogonalCamera>
    <CameraViewPoint><X>10</X><Y>20</Y><Z>100</Z></CameraViewPoint>
    <CameraDirection><X>0</X><Y>0</Y><Z>-1</Z></CameraDirection>
    <CameraUpVector><X>0</X><Y>1</Y><Z>0</Z></CameraUpVector>
    <ViewToWorldScale>35.5</ViewToWorldScale>
  </OrthogonalCamera>
  <ClippingPlanes>
    <ClippingPlane>
      <Location><X>0</X><Y>0</Y><Z>12</Z></Location>
      <Direction><X>0</X><Y>0</Y><Z>1</Z></Direction>
    </ClippingPlane>
  </ClippingPlanes>
</VisualizationInfo>'''

SAMPLE_30_MARKUP = u'''<?xml version="1.0" encoding="utf-8"?>
<Markup xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <Topic Guid="0f1e2d3c-4b5a-4968-8776-655443322110" TopicType="Request" TopicStatus="In Progress">
    <ReferenceLinks><ReferenceLink>https://example.com/x</ReferenceLink></ReferenceLinks>
    <Title>Missing fire damper</Title>
    <Priority>Medium</Priority>
    <Labels><Label>Fire Protection</Label><Label>Zone B</Label></Labels>
    <CreationDate>2026-10-03T08:30:00+01:00</CreationDate>
    <CreationAuthor>fp@example.com</CreationAuthor>
    <DueDate>2026-10-17</DueDate>
    <AssignedTo>mech@example.com</AssignedTo>
    <Description>Add a damper at the wall</Description>
    <DocumentReferences>
      <DocumentReference Guid="1a2b3c4d-0000-4000-8000-000000000009">
        <DocumentGuid>2a2b3c4d-0000-4000-8000-000000000009</DocumentGuid>
        <Description>Spec page</Description>
      </DocumentReference>
    </DocumentReferences>
    <Comments>
      <Comment Guid="8e7d6c5b-0000-4000-8000-000000000002">
        <Date>2026-10-03T09:00:00+01:00</Date>
        <Author>mech@example.com</Author>
        <Comment>On it</Comment>
      </Comment>
    </Comments>
    <Viewpoints>
      <ViewPoint Guid="9f8e7d6c-0000-4000-8000-000000000003">
        <Viewpoint>9f8e7d6c-0000-4000-8000-000000000003.bcfv</Viewpoint>
        <Snapshot>9f8e7d6c-0000-4000-8000-000000000003.jpg</Snapshot>
        <Index>0</Index>
      </ViewPoint>
    </Viewpoints>
  </Topic>
</Markup>'''

SAMPLE_30_VISINFO = u'''<?xml version="1.0" encoding="utf-8"?>
<VisualizationInfo Guid="9f8e7d6c-0000-4000-8000-000000000003">
  <Components>
    <Selection><Component IfcGuid="1hKpQ0rG1EuPz7Yt$9e3Wq"><AuthoringToolId>778899</AuthoringToolId></Component></Selection>
    <Visibility DefaultVisibility="true"><ViewSetupHints SpacesVisible="false" /></Visibility>
  </Components>
  <PerspectiveCamera>
    <CameraViewPoint><X>1</X><Y>2</Y><Z>3</Z></CameraViewPoint>
    <CameraDirection><X>1</X><Y>0</Y><Z>0</Z></CameraDirection>
    <CameraUpVector><X>0</X><Y>0</Y><Z>1</Z></CameraUpVector>
    <FieldOfView>90</FieldOfView>
    <AspectRatio>1.78</AspectRatio>
  </PerspectiveCamera>
</VisualizationInfo>'''


def _zip(entries):
    buf = io.BytesIO()
    z = zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED)
    for name in sorted(entries):
        value = entries[name]
        z.writestr(name, value.encode('utf-8') if not isinstance(value, bytes) else value)
    z.close()
    return buf.getvalue()


def test_read_bcf_20_sample():
    folder = 'A245DD8E-5E4F-4C6A-8F3B-6F7B2A43A111/'
    data = _zip({'bcf.version': u'<?xml version="1.0"?><Version VersionId="2.0"><DetailedVersion>2.0 RC</DetailedVersion></Version>',
                 folder + 'markup.bcf': SAMPLE_20_MARKUP, folder + 'viewpoint.bcfv': SAMPLE_20_VISINFO,
                 folder + 'snapshot.png': PNG})
    back = bcf.read(data)
    assert back['version'] == '2.0'
    t = back['topics'][0]
    assert t['guid'] == 'a245dd8e-5e4f-4c6a-8f3b-6f7b2a43a111'
    assert (t['type'], t['status'], t['title'], t['labels']) == ('Error', 'Active', 'Wall in the way',
                                                                 ['Architecture'])
    assert t['comments'][0]['comment'] == 'Please fix' and t['comments'][0]['verbal_status'] == 'Active'
    vp = t['viewpoints'][0]                                        # implicit viewpoint.bcfv
    assert vp['snapshot_data'] == PNG
    assert [c['ifc_guid'] for c in vp['visinfo']['selection']] == ['2MF28NhmDBiRVyFakgdbCT']
    assert vp['visinfo']['selection'][0]['authoring_tool_id'] == '291523'
    assert [c['ifc_guid'] for c in vp['visinfo']['visibility']['exceptions']] == ['1wnyQgUm9Ewh$CeuWdpHTm']
    assert vp['visinfo']['camera']['FieldOfView'] == 60.0
    made = issues.from_topic(t, None, ['Architecture'])
    assert made['fields']['status'] == 'Open' and made['fields']['trade'] == 'Architecture'


def test_read_bcf_21_sample():
    folder = '5c3e2e46-3a83-4d4a-8f8e-9d3b8f2b1a01/'
    data = _zip({'bcf.version': u'<Version VersionId="2.1"><DetailedVersion>2.1</DetailedVersion></Version>',
                 'project.bcfp': u'<ProjectExtension><Project ProjectId="p-1"><Name>Tower</Name></Project><ExtensionSchema></ExtensionSchema></ProjectExtension>',
                 folder + 'markup.bcf': SAMPLE_21_MARKUP,
                 folder + 'Viewpoint_6d4b.bcfv': SAMPLE_21_VISINFO,
                 folder + 'Snapshot_6d4b.png': PNG})
    back = bcf.read(data)
    assert back['version'] == '2.1' and back['project'] == {'id': 'p-1', 'name': 'Tower'}
    t = back['topics'][0]
    assert (t['priority'], t['index'], t['labels']) == ('Critical', 3, ['Structure', 'Level 4'])
    vis = t['viewpoints'][0]['visinfo']
    assert vis['camera']['type'] == 'OrthogonalCamera' and vis['camera']['ViewToWorldScale'] == 35.5
    assert vis['coloring'][0]['color'] == 'FF0000'
    assert vis['visibility'] == {'default': True, 'exceptions': [
        {'ifc_guid': '0vFL9wTnX7aQ2eGbYp1$Zz', 'originating_system': '', 'authoring_tool_id': ''}]}
    assert vis['clipping_planes'][0]['location'] == (0.0, 0.0, 12.0)
    assert t['viewpoints'][0]['snapshot_data'] == PNG
    assert bcf.check(data)['errors'] == []
    made = issues.from_topic(t, None, ['Structure'])
    assert made['fields']['status'] == 'Closed' and made['fields']['due'] == \
        issues.due_text(t['due_date'])


def test_read_bcf_30_sample():
    folder = '0f1e2d3c-4b5a-4968-8776-655443322110/'
    vp = '9f8e7d6c-0000-4000-8000-000000000003'
    data = _zip({'bcf.version': u'<Version VersionId="3.0" />',
                 'project.bcfp': u'<ProjectInfo><Project ProjectId="0f1e2d3c-4b5a-4968-8776-655443322119"><Name>Tower</Name></Project></ProjectInfo>',
                 'extensions.xml': u'<Extensions><TopicTypes><TopicType>Request</TopicType></TopicTypes><TopicStatuses><TopicStatus>In Progress</TopicStatus></TopicStatuses></Extensions>',
                 'documents.xml': u'<DocumentInfo><Documents><Document Guid="2a2b3c4d-0000-4000-8000-000000000009"><Filename>spec.pdf</Filename></Document></Documents></DocumentInfo>',
                 'documents/2a2b3c4d-0000-4000-8000-000000000009': b'%PDF-1.4',
                 folder + 'markup.bcf': SAMPLE_30_MARKUP, folder + vp + '.bcfv': SAMPLE_30_VISINFO,
                 folder + vp + '.jpg': JPG})
    back = bcf.read(data)
    assert back['version'] == '3.0'
    assert back['extensions']['types'] == ['Request']
    assert back['documents']['2a2b3c4d-0000-4000-8000-000000000009']['filename'] == 'spec.pdf'
    assert back['documents']['2a2b3c4d-0000-4000-8000-000000000009']['data'] == b'%PDF-1.4'
    t = back['topics'][0]
    assert t['labels'] == ['Fire Protection', 'Zone B'] and t['reference_links'] == ['https://example.com/x']
    assert t['document_references'][0]['document_guid'] == '2a2b3c4d-0000-4000-8000-000000000009'
    assert t['comments'][0]['comment'] == 'On it'
    assert t['viewpoints'][0]['snapshot_data'] == JPG
    cam = t['viewpoints'][0]['visinfo']['camera']
    assert cam['FieldOfView'] == 90.0 and cam['AspectRatio'] == 1.78
    assert bcf.check(data)['errors'] == []
    made = issues.from_topic(t, None, ['Fire Protection'])
    f = made['fields']
    assert (f['status'], f['priority'], f['trade'], f['labels']) == ('In progress', 'Normal',
                                                                     'Fire Protection', ['Zone B'])
    assert f['due'] == '2026-10-17'


def test_read_skips_damaged_topics_and_rejects_non_zip():
    data = _zip({'bcf.version': u'<Version VersionId="2.1" />',
                 'aaaaaaaa-1111-4222-8333-444444444444/markup.bcf': u'<Markup><Topic',
                 '3f2504e0-4f89-41d3-9a0c-0305e82c3301/markup.bcf': bcf.markup_xml(
                     dict(_topic(), viewpoints=[]), '2.1')})
    back = bcf.read(data)
    assert [t['guid'] for t in back['topics']] == [T1]
    assert any('skipped' in n for n in back['notes'])
    error = raises(bcf.BcfError, bcf.read, b'not a zip at all')
    assert 'not a BCF file' in str(error)
    assert bcf.check(b'nope')['errors']


def test_check_finds_order_and_missing_parts():
    bad = u'''<Markup><Topic Guid="3F2504E0-4F89-41D3-9A0C-0305E82C3301"><CreationDate>2026-10-01T08:00:00Z</CreationDate><Title>x</Title></Topic></Markup>'''
    data = _zip({'bcf.version': u'<Version VersionId="2.1" />',
                 T1 + '/markup.bcf': bad})
    errors = bcf.check(data)['errors']
    assert any('Title is out of order' in e for e in errors)
    assert any('CreationAuthor is missing' in e for e in errors)
    assert any('not a lowercase GUID' in e for e in errors)
    data = _zip({T1 + '/markup.bcf': bcf.markup_xml(dict(_topic(), viewpoints=[{
        'guid': VP1, 'viewpoint': 'viewpoint.bcfv', 'snapshot': 'snapshot.png'}]), '2.1')})
    errors = bcf.check(data)['errors']
    assert 'bcf.version is missing.' in errors
    assert any('viewpoint file viewpoint.bcfv is missing' in e for e in errors)
    vis = u'''<VisualizationInfo Guid="%s"><PerspectiveCamera><CameraDirection><X>0</X><Y>1</Y><Z>0</Z></CameraDirection><CameraViewPoint><X>0</X><Y>0</Y><Z>0</Z></CameraViewPoint><CameraUpVector><X>0</X><Y>0</Y><Z>1</Z></CameraUpVector><FieldOfView>30</FieldOfView></PerspectiveCamera></VisualizationInfo>''' % VP1
    found = bcf.check_visinfo(vis.encode('utf-8'), '2.1')
    assert any('out of order' in e for e in found) and any('outside 45..60' in e for e in found)


# ---- XSD validation (CPython + lxml) ------------------------------------------------------
# Reconstructed from the buildingSMART BCF-XML schemas (release_2_1 and release_3_0). Simple
# string restrictions (Priority, TopicType...) are written as xs:string; everything about
# structure (element names, order, multiplicity, required attributes, GUID patterns, the
# FieldOfView ranges, AspectRatio) is as recalled. This proves the writer matches the
# schemas as reconstructed here; it is not a substitute for a run against the official files.

GUID = '''<xs:simpleType name="Guid"><xs:restriction base="xs:string"><xs:pattern value="[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}"/></xs:restriction></xs:simpleType>'''
IFCGUID = '''<xs:simpleType name="IfcGuid"><xs:restriction base="xs:string"><xs:length value="22"/><xs:pattern value="[0-9,A-Z,a-z,_$]*"/></xs:restriction></xs:simpleType>'''
HEAD = '<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema" elementFormDefault="qualified" attributeFormDefault="unqualified">'

XSD_VERSION = HEAD + '''<xs:element name="Version"><xs:complexType><xs:sequence>
<xs:element name="DetailedVersion" type="xs:string" minOccurs="0"/></xs:sequence>
<xs:attribute name="VersionId" type="xs:string" use="required"/></xs:complexType></xs:element></xs:schema>'''

XSD_PROJECT_21 = HEAD + '''<xs:element name="ProjectExtension"><xs:complexType><xs:sequence>
<xs:element name="Project" type="Project" minOccurs="0"/><xs:element name="ExtensionSchema" type="xs:string"/>
</xs:sequence></xs:complexType></xs:element>
<xs:complexType name="Project"><xs:sequence><xs:element name="Name" type="xs:string" minOccurs="0"/></xs:sequence>
<xs:attribute name="ProjectId" type="xs:string" use="required"/></xs:complexType></xs:schema>'''

XSD_PROJECT_30 = HEAD + '''<xs:element name="ProjectInfo"><xs:complexType><xs:sequence>
<xs:element name="Project" type="Project"/></xs:sequence></xs:complexType></xs:element>
<xs:complexType name="Project"><xs:sequence><xs:element name="Name" type="xs:string"/></xs:sequence>
<xs:attribute name="ProjectId" type="Guid" use="required"/></xs:complexType>''' + GUID + '</xs:schema>'

_FILE = '''<xs:sequence><xs:element name="Filename" type="xs:string" minOccurs="0"/>
<xs:element name="Date" type="xs:dateTime" minOccurs="0"/><xs:element name="Reference" type="xs:string" minOccurs="0"/></xs:sequence>'''

XSD_MARKUP_21 = HEAD + '''<xs:element name="Markup"><xs:complexType><xs:sequence>
<xs:element name="Header" type="Header" minOccurs="0"/><xs:element name="Topic" type="Topic"/>
<xs:element name="Comment" type="Comment" minOccurs="0" maxOccurs="unbounded"/>
<xs:element name="Viewpoints" type="ViewPoint" minOccurs="0" maxOccurs="unbounded"/>
</xs:sequence></xs:complexType></xs:element>
<xs:complexType name="Header"><xs:sequence><xs:element name="File" maxOccurs="unbounded"><xs:complexType>''' + _FILE + '''
<xs:attribute name="IfcProject" type="IfcGuid"/><xs:attribute name="IfcSpatialStructureElement" type="IfcGuid"/>
<xs:attribute name="isExternal" type="xs:boolean" default="true"/></xs:complexType></xs:element></xs:sequence></xs:complexType>
<xs:complexType name="ViewPoint"><xs:sequence><xs:element name="Viewpoint" type="xs:string" minOccurs="0"/>
<xs:element name="Snapshot" type="xs:string" minOccurs="0"/><xs:element name="Index" type="xs:integer" minOccurs="0"/></xs:sequence>
<xs:attribute name="Guid" type="Guid" use="required"/></xs:complexType>
<xs:complexType name="Comment"><xs:sequence><xs:element name="Date" type="xs:dateTime"/><xs:element name="Author" type="xs:string"/>
<xs:element name="Comment" type="xs:string"/><xs:element name="Viewpoint" minOccurs="0"><xs:complexType>
<xs:attribute name="Guid" type="Guid" use="required"/></xs:complexType></xs:element>
<xs:element name="ModifiedDate" type="xs:dateTime" minOccurs="0"/><xs:element name="ModifiedAuthor" type="xs:string" minOccurs="0"/>
</xs:sequence><xs:attribute name="Guid" type="Guid" use="required"/></xs:complexType>
<xs:complexType name="Topic"><xs:sequence>
<xs:element name="ReferenceLink" type="xs:string" minOccurs="0" maxOccurs="unbounded"/>
<xs:element name="Title" type="xs:string"/><xs:element name="Priority" type="xs:string" minOccurs="0"/>
<xs:element name="Index" type="xs:integer" minOccurs="0"/>
<xs:element name="Labels" type="xs:string" minOccurs="0" maxOccurs="unbounded"/>
<xs:element name="CreationDate" type="xs:dateTime"/><xs:element name="CreationAuthor" type="xs:string"/>
<xs:element name="ModifiedDate" type="xs:dateTime" minOccurs="0"/><xs:element name="ModifiedAuthor" type="xs:string" minOccurs="0"/>
<xs:element name="DueDate" type="xs:dateTime" minOccurs="0"/><xs:element name="AssignedTo" type="xs:string" minOccurs="0"/>
<xs:element name="Stage" type="xs:string" minOccurs="0"/><xs:element name="Description" type="xs:string" minOccurs="0"/>
<xs:element name="BimSnippet" minOccurs="0"><xs:complexType><xs:sequence><xs:element name="Reference" type="xs:string"/>
<xs:element name="ReferenceSchema" type="xs:string"/></xs:sequence><xs:attribute name="SnippetType" type="xs:string" use="required"/>
<xs:attribute name="isExternal" type="xs:boolean" default="false"/></xs:complexType></xs:element>
<xs:element name="DocumentReference" minOccurs="0" maxOccurs="unbounded"><xs:complexType><xs:sequence>
<xs:element name="ReferencedDocument" type="xs:string" minOccurs="0"/><xs:element name="Description" type="xs:string" minOccurs="0"/>
</xs:sequence><xs:attribute name="Guid" type="Guid"/><xs:attribute name="isExternal" type="xs:boolean" default="false"/></xs:complexType></xs:element>
<xs:element name="RelatedTopic" minOccurs="0" maxOccurs="unbounded"><xs:complexType><xs:attribute name="Guid" type="Guid" use="required"/></xs:complexType></xs:element>
</xs:sequence><xs:attribute name="Guid" type="Guid" use="required"/>
<xs:attribute name="TopicType" type="xs:string"/><xs:attribute name="TopicStatus" type="xs:string"/></xs:complexType>
''' + GUID + IFCGUID + '</xs:schema>'

XSD_MARKUP_30 = HEAD + '''<xs:element name="Markup"><xs:complexType><xs:sequence>
<xs:element name="Header" type="Header" minOccurs="0"/><xs:element name="Topic" type="Topic"/>
</xs:sequence></xs:complexType></xs:element>
<xs:complexType name="Header"><xs:sequence><xs:element name="Files"><xs:complexType><xs:sequence>
<xs:element name="File" type="File" maxOccurs="unbounded"/></xs:sequence></xs:complexType></xs:element></xs:sequence></xs:complexType>
<xs:complexType name="File">''' + _FILE + '''<xs:attribute name="IfcProject" type="IfcGuid"/>
<xs:attribute name="IfcSpatialStructureElement" type="IfcGuid"/><xs:attribute name="IsExternal" type="xs:boolean" default="true"/></xs:complexType>
<xs:complexType name="ViewPoint"><xs:sequence><xs:element name="Viewpoint" type="xs:string" minOccurs="0"/>
<xs:element name="Snapshot" type="xs:string" minOccurs="0"/><xs:element name="Index" type="xs:integer" minOccurs="0"/></xs:sequence>
<xs:attribute name="Guid" type="Guid" use="required"/></xs:complexType>
<xs:complexType name="Comment"><xs:sequence><xs:element name="Date" type="xs:dateTime"/><xs:element name="Author" type="xs:string"/>
<xs:element name="Comment" type="xs:string" minOccurs="0"/><xs:element name="Viewpoint" minOccurs="0"><xs:complexType>
<xs:attribute name="Guid" type="Guid" use="required"/></xs:complexType></xs:element>
<xs:element name="ModifiedDate" type="xs:dateTime" minOccurs="0"/><xs:element name="ModifiedAuthor" type="xs:string" minOccurs="0"/>
</xs:sequence><xs:attribute name="Guid" type="Guid" use="required"/></xs:complexType>
<xs:complexType name="DocumentReference"><xs:sequence><xs:choice><xs:element name="DocumentGuid" type="Guid"/>
<xs:element name="Url" type="xs:string"/></xs:choice><xs:element name="Description" type="xs:string" minOccurs="0"/></xs:sequence>
<xs:attribute name="Guid" type="Guid" use="required"/></xs:complexType>
<xs:complexType name="Topic"><xs:sequence>
<xs:element name="ReferenceLinks" minOccurs="0"><xs:complexType><xs:sequence><xs:element name="ReferenceLink" type="xs:string" maxOccurs="unbounded"/></xs:sequence></xs:complexType></xs:element>
<xs:element name="Title" type="xs:string"/><xs:element name="Priority" type="xs:string" minOccurs="0"/>
<xs:element name="Index" type="xs:integer" minOccurs="0"/>
<xs:element name="Labels" minOccurs="0"><xs:complexType><xs:sequence><xs:element name="Label" type="xs:string" maxOccurs="unbounded"/></xs:sequence></xs:complexType></xs:element>
<xs:element name="CreationDate" type="xs:dateTime"/><xs:element name="CreationAuthor" type="xs:string"/>
<xs:element name="ModifiedDate" type="xs:dateTime" minOccurs="0"/><xs:element name="ModifiedAuthor" type="xs:string" minOccurs="0"/>
<xs:element name="DueDate" type="xs:dateTime" minOccurs="0"/><xs:element name="AssignedTo" type="xs:string" minOccurs="0"/>
<xs:element name="Stage" type="xs:string" minOccurs="0"/><xs:element name="Description" type="xs:string" minOccurs="0"/>
<xs:element name="BimSnippet" minOccurs="0"><xs:complexType><xs:sequence><xs:element name="Reference" type="xs:string"/>
<xs:element name="ReferenceSchema" type="xs:string"/></xs:sequence><xs:attribute name="SnippetType" type="xs:string" use="required"/>
<xs:attribute name="IsExternal" type="xs:boolean" default="false"/></xs:complexType></xs:element>
<xs:element name="DocumentReferences" minOccurs="0"><xs:complexType><xs:sequence><xs:element name="DocumentReference" type="DocumentReference" maxOccurs="unbounded"/></xs:sequence></xs:complexType></xs:element>
<xs:element name="RelatedTopics" minOccurs="0"><xs:complexType><xs:sequence><xs:element name="RelatedTopic" maxOccurs="unbounded"><xs:complexType><xs:attribute name="Guid" type="Guid" use="required"/></xs:complexType></xs:element></xs:sequence></xs:complexType></xs:element>
<xs:element name="Comments" minOccurs="0"><xs:complexType><xs:sequence><xs:element name="Comment" type="Comment" maxOccurs="unbounded"/></xs:sequence></xs:complexType></xs:element>
<xs:element name="Viewpoints" minOccurs="0"><xs:complexType><xs:sequence><xs:element name="ViewPoint" type="ViewPoint" maxOccurs="unbounded"/></xs:sequence></xs:complexType></xs:element>
</xs:sequence><xs:attribute name="Guid" type="Guid" use="required"/>
<xs:attribute name="TopicType" type="xs:string" use="required"/><xs:attribute name="TopicStatus" type="xs:string" use="required"/></xs:complexType>
''' + GUID + IFCGUID + '</xs:schema>'

_POINT = '''<xs:complexType name="Point"><xs:sequence><xs:element name="X" type="xs:double"/><xs:element name="Y" type="xs:double"/>
<xs:element name="Z" type="xs:double"/></xs:sequence></xs:complexType>
<xs:complexType name="Direction"><xs:sequence><xs:element name="X" type="xs:double"/><xs:element name="Y" type="xs:double"/>
<xs:element name="Z" type="xs:double"/></xs:sequence></xs:complexType>
<xs:complexType name="Component"><xs:sequence><xs:element name="OriginatingSystem" type="xs:string" minOccurs="0"/>
<xs:element name="AuthoringToolId" type="xs:string" minOccurs="0"/></xs:sequence><xs:attribute name="IfcGuid" type="IfcGuid"/></xs:complexType>
<xs:complexType name="ComponentColoringColor"><xs:sequence><xs:element name="Component" type="Component" maxOccurs="unbounded"/></xs:sequence>
<xs:attribute name="Color" use="required"><xs:simpleType><xs:restriction base="xs:string"><xs:pattern value="([0-9A-Fa-f]{6}|[0-9A-Fa-f]{8})"/></xs:restriction></xs:simpleType></xs:attribute></xs:complexType>
<xs:complexType name="ViewSetupHints"><xs:attribute name="SpacesVisible" type="xs:boolean" default="false"/>
<xs:attribute name="SpaceBoundariesVisible" type="xs:boolean" default="false"/><xs:attribute name="OpeningsVisible" type="xs:boolean" default="false"/></xs:complexType>
<xs:complexType name="Line"><xs:sequence><xs:element name="StartPoint" type="Point"/><xs:element name="EndPoint" type="Point"/></xs:sequence></xs:complexType>
<xs:complexType name="ClippingPlane"><xs:sequence><xs:element name="Location" type="Point"/><xs:element name="Direction" type="Direction"/></xs:sequence></xs:complexType>
<xs:complexType name="Bitmap"><xs:sequence><xs:element name="Format" type="xs:string"/><xs:element name="Reference" type="xs:string"/>
<xs:element name="Location" type="Point"/><xs:element name="Normal" type="Direction"/><xs:element name="Up" type="Direction"/>
<xs:element name="Height" type="xs:double"/></xs:sequence></xs:complexType>'''

_CAMERA_START = '''<xs:element name="CameraViewPoint" type="Point"/><xs:element name="CameraDirection" type="Direction"/>
<xs:element name="CameraUpVector" type="Direction"/>'''

XSD_VISINFO_21 = HEAD + '''<xs:element name="VisualizationInfo"><xs:complexType><xs:sequence>
<xs:element name="Components" type="Components" minOccurs="0"/>
<xs:element name="OrthogonalCamera" type="OrthogonalCamera" minOccurs="0"/>
<xs:element name="PerspectiveCamera" type="PerspectiveCamera" minOccurs="0"/>
<xs:element name="Lines" minOccurs="0"><xs:complexType><xs:sequence><xs:element name="Line" type="Line" minOccurs="0" maxOccurs="unbounded"/></xs:sequence></xs:complexType></xs:element>
<xs:element name="ClippingPlanes" minOccurs="0"><xs:complexType><xs:sequence><xs:element name="ClippingPlane" type="ClippingPlane" minOccurs="0" maxOccurs="unbounded"/></xs:sequence></xs:complexType></xs:element>
<xs:element name="Bitmap" type="Bitmap" minOccurs="0" maxOccurs="unbounded"/>
</xs:sequence><xs:attribute name="Guid" type="Guid" use="required"/></xs:complexType></xs:element>
<xs:complexType name="Components"><xs:sequence><xs:element name="ViewSetupHints" type="ViewSetupHints" minOccurs="0"/>
<xs:element name="Selection" minOccurs="0"><xs:complexType><xs:sequence><xs:element name="Component" type="Component" maxOccurs="unbounded"/></xs:sequence></xs:complexType></xs:element>
<xs:element name="Visibility" type="ComponentVisibility"/>
<xs:element name="Coloring" minOccurs="0"><xs:complexType><xs:sequence><xs:element name="Color" type="ComponentColoringColor" maxOccurs="unbounded"/></xs:sequence></xs:complexType></xs:element>
</xs:sequence></xs:complexType>
<xs:complexType name="ComponentVisibility"><xs:sequence><xs:element name="Exceptions" minOccurs="0"><xs:complexType><xs:sequence>
<xs:element name="Component" type="Component" maxOccurs="unbounded"/></xs:sequence></xs:complexType></xs:element></xs:sequence>
<xs:attribute name="DefaultVisibility" type="xs:boolean" default="false"/></xs:complexType>
<xs:complexType name="OrthogonalCamera"><xs:sequence>''' + _CAMERA_START + '''<xs:element name="ViewToWorldScale" type="xs:double"/></xs:sequence></xs:complexType>
<xs:complexType name="PerspectiveCamera"><xs:sequence>''' + _CAMERA_START + '''<xs:element name="FieldOfView" type="FieldOfView"/></xs:sequence></xs:complexType>
<xs:simpleType name="FieldOfView"><xs:restriction base="xs:double"><xs:minInclusive value="45"/><xs:maxInclusive value="60"/></xs:restriction></xs:simpleType>
''' + _POINT + GUID + IFCGUID + '</xs:schema>'

_POSITIVE = '<xs:simpleType><xs:restriction base="xs:double"><xs:minExclusive value="0"/></xs:restriction></xs:simpleType>'

XSD_VISINFO_30 = HEAD + '''<xs:element name="VisualizationInfo"><xs:complexType><xs:sequence>
<xs:element name="Components" type="Components" minOccurs="0"/>
<xs:element name="OrthogonalCamera" type="OrthogonalCamera" minOccurs="0"/>
<xs:element name="PerspectiveCamera" type="PerspectiveCamera" minOccurs="0"/>
<xs:element name="Lines" minOccurs="0"><xs:complexType><xs:sequence><xs:element name="Line" type="Line" maxOccurs="unbounded"/></xs:sequence></xs:complexType></xs:element>
<xs:element name="ClippingPlanes" minOccurs="0"><xs:complexType><xs:sequence><xs:element name="ClippingPlane" type="ClippingPlane" maxOccurs="unbounded"/></xs:sequence></xs:complexType></xs:element>
<xs:element name="Bitmaps" minOccurs="0"><xs:complexType><xs:sequence><xs:element name="Bitmap" type="Bitmap" maxOccurs="unbounded"/></xs:sequence></xs:complexType></xs:element>
</xs:sequence><xs:attribute name="Guid" type="Guid" use="required"/></xs:complexType></xs:element>
<xs:complexType name="Components"><xs:sequence>
<xs:element name="Selection" minOccurs="0"><xs:complexType><xs:sequence><xs:element name="Component" type="Component" maxOccurs="unbounded"/></xs:sequence></xs:complexType></xs:element>
<xs:element name="Visibility" type="ComponentVisibility"/>
<xs:element name="Coloring" minOccurs="0"><xs:complexType><xs:sequence><xs:element name="Color" type="ComponentColoringColor" maxOccurs="unbounded"/></xs:sequence></xs:complexType></xs:element>
</xs:sequence></xs:complexType>
<xs:complexType name="ComponentVisibility"><xs:sequence><xs:element name="ViewSetupHints" type="ViewSetupHints" minOccurs="0"/>
<xs:element name="Exceptions" minOccurs="0"><xs:complexType><xs:sequence><xs:element name="Component" type="Component" maxOccurs="unbounded"/></xs:sequence></xs:complexType></xs:element></xs:sequence>
<xs:attribute name="DefaultVisibility" type="xs:boolean" default="false"/></xs:complexType>
<xs:complexType name="OrthogonalCamera"><xs:sequence>''' + _CAMERA_START + '''<xs:element name="ViewToWorldScale">''' + _POSITIVE + '''</xs:element>
<xs:element name="AspectRatio">''' + _POSITIVE + '''</xs:element></xs:sequence></xs:complexType>
<xs:complexType name="PerspectiveCamera"><xs:sequence>''' + _CAMERA_START + '''<xs:element name="FieldOfView"><xs:simpleType><xs:restriction base="xs:double">
<xs:minExclusive value="0"/><xs:maxExclusive value="180"/></xs:restriction></xs:simpleType></xs:element>
<xs:element name="AspectRatio">''' + _POSITIVE + '''</xs:element></xs:sequence></xs:complexType>
''' + _POINT + GUID + IFCGUID + '</xs:schema>'

_LIST = '<xs:element name="%s" minOccurs="0"><xs:complexType><xs:sequence><xs:element name="%s" type="xs:string" maxOccurs="unbounded"/></xs:sequence></xs:complexType></xs:element>'
XSD_EXTENSIONS_30 = HEAD + '<xs:element name="Extensions"><xs:complexType><xs:sequence>' + ''.join(
    _LIST % (w, t) for _k, w, t in bcf.EXTENSION_LISTS) + '</xs:sequence></xs:complexType></xs:element></xs:schema>'

XSD_DOCUMENTS_30 = HEAD + '''<xs:element name="DocumentInfo"><xs:complexType><xs:sequence>
<xs:element name="Documents" minOccurs="0"><xs:complexType><xs:sequence><xs:element name="Document" type="Document" maxOccurs="unbounded"/>
</xs:sequence></xs:complexType></xs:element></xs:sequence></xs:complexType></xs:element>
<xs:complexType name="Document"><xs:sequence><xs:element name="Filename" type="xs:string"/>
<xs:element name="Description" type="xs:string" minOccurs="0"/></xs:sequence><xs:attribute name="Guid" type="Guid" use="required"/></xs:complexType>
''' + GUID + '</xs:schema>'


def _validate_all(data, version):
    _compat.require_cpython('lxml schema validation runs under CPython')
    try:
        from lxml import etree
    except ImportError:
        raise _compat.SkipTest('lxml not installed')
    schemas = {'version': XSD_VERSION,
               'project': XSD_PROJECT_21 if version == '2.1' else XSD_PROJECT_30,
               'markup': XSD_MARKUP_21 if version == '2.1' else XSD_MARKUP_30,
               'visinfo': XSD_VISINFO_21 if version == '2.1' else XSD_VISINFO_30,
               'extensions': XSD_EXTENSIONS_30, 'documents': XSD_DOCUMENTS_30}
    compiled = dict((k, etree.XMLSchema(etree.fromstring(v.encode('utf-8')))) for k, v in schemas.items())
    z = zipfile.ZipFile(io.BytesIO(data))
    checked = 0
    for name in z.namelist():
        kind = None
        if name == 'bcf.version':
            kind = 'version'
        elif name == 'project.bcfp':
            kind = 'project'
        elif name.endswith('markup.bcf'):
            kind = 'markup'
        elif name.endswith('.bcfv'):
            kind = 'visinfo'
        elif name == 'extensions.xml':
            kind = 'extensions'
        elif name == 'documents.xml':
            kind = 'documents'
        if kind is None:
            continue
        doc = etree.fromstring(z.read(name))
        schema = compiled[kind]
        assert schema.validate(doc), '%s %s: %s' % (version, name, schema.error_log)
        checked += 1
    return checked


def test_written_files_validate_against_xsd_21():
    topic = _topic()
    topic['viewpoints'].append({'guid': 'bbbbbbbb-1111-4222-8333-444444444444', 'visinfo': {
        'camera': {'type': 'OrthogonalCamera', 'CameraViewPoint': (0, 0, 9), 'CameraDirection': (0, 0, -1),
                   'CameraUpVector': (0, 1, 0), 'ViewToWorldScale': 12.0},
        'visibility': {'default': False, 'exceptions': [{'ifc_guid': '0000000000000000000000'}]},
        'coloring': [{'color': 'FF8800', 'components': [{'ifc_guid': '0000000000000000000000'}]}]}})
    data, _ = bcf.package([topic, _topic(guid=T2, comments=[], viewpoints=[], labels=[],
                                         reference_links=[], related_topics=[], priority='',
                                         due_date='', assigned_to='', description='')],
                          '2.1', {'name': 'Tower'}, created=CREATED)
    assert _validate_all(data, '2.1') == 6


def test_written_files_validate_against_xsd_30():
    doc_guid = 'dddddddd-1111-4222-8333-444444444444'
    topic = _topic(document_references=[{'guid': 'eeeeeeee-1111-4222-8333-444444444444',
                                         'document_guid': doc_guid},
                                        {'guid': 'ffffffff-1111-4222-8333-444444444444',
                                         'url': 'https://example.com/spec.pdf'}])
    data, _ = bcf.package([topic, _topic(guid=T2, comments=[], viewpoints=[], labels=[],
                                         reference_links=[], related_topics=[], type='',
                                         status='')],
                          '3.0', {'name': 'Tower'}, created=CREATED,
                          documents=[{'guid': doc_guid, 'filename': 'a.pdf', 'data': b'%PDF'}])
    assert _validate_all(data, '3.0') == 7


def test_xsd_catches_a_broken_markup():
    _compat.require_cpython('lxml schema validation runs under CPython')
    try:
        from lxml import etree
    except ImportError:
        raise _compat.SkipTest('lxml not installed')
    schema = etree.XMLSchema(etree.fromstring(XSD_MARKUP_21.encode('utf-8')))
    good = bcf.markup_xml(dict(_topic(), viewpoints=[]), '2.1')
    assert schema.validate(etree.fromstring(good))
    swapped = good.replace(b'<Priority>High</Priority>\n    <Index>12</Index>',
                           b'<Index>12</Index>\n    <Priority>High</Priority>')
    assert swapped != good
    assert not schema.validate(etree.fromstring(swapped))



def test_lens_adjustments_are_counted_apart_from_losses():
    # A Navisworks lens is usually outside BCF 2.1's 45..60 degrees. Bringing it inside
    # is not a loss, so package() counts it under 'adjusted' and keeps 'notes' for losses
    # (BCF Export toasts a warning only for notes).
    narrow = {'type': 'PerspectiveCamera', 'CameraViewPoint': (417576.5, 417576.5, 9.0),
              'CameraDirection': (1, 0, 0), 'CameraUpVector': (0, 0, 1), 'FieldOfView': 38.2}
    topic = dict(_topic(), viewpoints=[{'guid': VP1, 'visinfo': {'guid': VP1, 'camera': narrow}}])
    data, report = bcf.package([topic], '2.1', created=CREATED)
    assert report['notes'] == [] and report['adjusted'] == {'fov': 1}
    assert bcf.check(data)['errors'] == []
    archive = zipfile.ZipFile(io.BytesIO(data))
    text = archive.read('%s/viewpoint.bcfv' % T1).decode('utf-8')
    assert '<FieldOfView>45</FieldOfView>' in text
    # Far from the origin the eye keeps millimetre precision in metres.
    assert '<X>417576.5</X>' in text
    data, report = bcf.package([topic], '3.0', created=CREATED)
    assert report['adjusted'] == {'aspect': 1} and report['notes'] == []


def test_reads_30_coloring_components_wrapper():
    xml = (u'<VisualizationInfo Guid="%s"><Components><Visibility DefaultVisibility="true"/>'
           u'<Coloring><Color Color="FF00FF00"><Components>'
           u'<Component IfcGuid="0abcdefghijklmnopqrstu"/></Components></Color>'
           u'<Color Color="FFFF0000"><Component IfcGuid="1abcdefghijklmnopqrstu"/></Color>'
           u'</Coloring></Components></VisualizationInfo>' % VP1).encode('utf-8')
    coloring = bcf.parse_visinfo(xml)['coloring']
    assert [len(c['components']) for c in coloring] == [1, 1]
    assert coloring[0]['components'][0]['ifc_guid'] == '0abcdefghijklmnopqrstu'
