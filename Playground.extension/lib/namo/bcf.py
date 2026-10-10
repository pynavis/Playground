# -*- coding: utf-8 -*-
"""BCF (BIM Collaboration Format) files: write 2.1 and 3.0, read 2.0, 2.1 and 3.0.

Pure Python (zipfile + ElementTree for reading, string-built XML for writing, so element
ORDER is exactly the schemas' xs:sequence order); runs the same on CPython and
IronPython 3.4. No Navisworks: callers turn issues or clashes into the plain dicts
below (namo.issues.to_topic, namo.bcf_exchange) and hand over snapshot bytes.

    from namo import bcf
    report = bcf.write(path, topics, version='2.1', project={'name': 'Hospital'})
    data = bcf.read(path)          # {'version', 'project', 'extensions', 'topics', 'documents', 'notes'}
    found = bcf.check(path)        # {'errors': [...], 'warnings': [...]}: structure check

A topic (what write takes and read returns):

    {'guid', 'type', 'status', 'title', 'priority', 'index', 'labels': [..],
     'creation_date', 'creation_author', 'modified_date', 'modified_author',
     'due_date', 'assigned_to', 'stage', 'description', 'reference_links': [..],
     'related_topics': [guid], 'document_references': [{'guid', 'document_guid', 'url',
     'referenced_document', 'is_external', 'description'}],
     'comments': [{'guid', 'date', 'author', 'comment', 'viewpoint_guid',
                   'modified_date', 'modified_author'}],
     'viewpoints': [{'guid', 'viewpoint' (file), 'snapshot' (file), 'index',
                     'snapshot_data' (bytes or None), 'visinfo': VISINFO}]}

    VISINFO = {'guid', 'camera': {'type': 'PerspectiveCamera' | 'OrthogonalCamera',
               'CameraViewPoint': (x, y, z) METRES, 'CameraDirection', 'CameraUpVector',
               'FieldOfView' (vertical degrees) | 'ViewToWorldScale' (view height, m),
               'AspectRatio'} or None,
               'selection': [{'ifc_guid', 'originating_system', 'authoring_tool_id'}],
               'visibility': {'default': bool, 'exceptions': [component]},
               'coloring': [{'color': 'RRGGBB' or 'AARRGGBB', 'components': [component]}],
               'clipping_planes': [{'location': (x, y, z), 'direction': (x, y, z)}],
               'lines': [{'start': (x, y, z), 'end': (x, y, z)}]}

The camera dict is namo.camera.to_bcf's shape, so from_bcf reads it back. Dates are
written as UTC ('...Z'), due dates as a plain date at midnight with no zone; read dates
come back as text exactly as stored (namo.dates.parse converts any zone to local).

Version differences the writer follows (buildingSMART BCF-XML release_2_1 and
release_3_0 schemas, reconstructed; see dev/notes/issues_bcf.md):
  * 2.1: Markup = Header?, Topic, Comment*, Viewpoints*; Topic children ReferenceLink*,
    Title, Priority?, Index?, Labels*, CreationDate, CreationAuthor, ModifiedDate?,
    ModifiedAuthor?, DueDate?, AssignedTo?, Stage?, Description?, BimSnippet?,
    DocumentReference*, RelatedTopic*; FieldOfView restricted to 45..60 degrees (a
    camera outside is clamped and noted); no AspectRatio; project.bcfp is
    ProjectExtension(Project?, ExtensionSchema).
  * 3.0: Markup = Header?, Topic; Topic carries ReferenceLinks?, Labels?, Comments?,
    Viewpoints?, DocumentReferences?, RelatedTopics? wrappers and REQUIRES TopicType and
    TopicStatus; cameras end with AspectRatio (required); project.bcfp is ProjectInfo;
    extensions.xml lists the types, statuses, priorities, labels and users used;
    documents.xml + documents/<guid> hold attached documents.
  * Components (both): Selection?, Visibility (required, DefaultVisibility attribute),
    Coloring?; a Component carries IfcGuid plus OriginatingSystem? and AuthoringToolId?;
    only components with a valid IFC GlobalId are written.
  * GUIDs are written lower case (the schemas' Guid pattern).
"""

import datetime
import io
import re
import time
import uuid
import zipfile

VERSIONS = ('2.1', '3.0')
READ_VERSIONS = ('2.0', '2.1', '3.0')
FOV_RANGE_21 = (45.0, 60.0)
DEFAULT_ASPECT = 16.0 / 9.0
GUID_RE = re.compile(r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$')
IFC_GUID_RE = re.compile(r'^[0-3][0-9A-Za-z_$]{21}$')
_XML_DECL = '<?xml version="1.0" encoding="utf-8"?>\n'
_BAD_XML = re.compile(u'[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]')

# Child order per element and version (the xs:sequence order). check() uses these.
MARKUP_ORDER = {'2.1': ['Header', 'Topic', 'Comment', 'Viewpoints'],
                '3.0': ['Header', 'Topic']}
TOPIC_ORDER = {
    '2.1': ['ReferenceLink', 'Title', 'Priority', 'Index', 'Labels', 'CreationDate',
            'CreationAuthor', 'ModifiedDate', 'ModifiedAuthor', 'DueDate', 'AssignedTo', 'Stage',
            'Description', 'BimSnippet', 'DocumentReference', 'RelatedTopic'],
    '3.0': ['ReferenceLinks', 'Title', 'Priority', 'Index', 'Labels', 'CreationDate',
            'CreationAuthor', 'ModifiedDate', 'ModifiedAuthor', 'DueDate', 'AssignedTo', 'Stage',
            'Description', 'BimSnippet', 'DocumentReferences', 'RelatedTopics', 'Comments',
            'Viewpoints'],
}
TOPIC_REQUIRED = ['Title', 'CreationDate', 'CreationAuthor']
COMMENT_ORDER = ['Date', 'Author', 'Comment', 'Viewpoint', 'ModifiedDate', 'ModifiedAuthor']
COMMENT_REQUIRED = {'2.1': ['Date', 'Author', 'Comment'], '3.0': ['Date', 'Author']}
VIEWPOINT_REF_ORDER = ['Viewpoint', 'Snapshot', 'Index']
VISINFO_ORDER = {'2.1': ['Components', 'OrthogonalCamera', 'PerspectiveCamera', 'Lines',
                         'ClippingPlanes', 'Bitmap'],
                 '3.0': ['Components', 'OrthogonalCamera', 'PerspectiveCamera', 'Lines',
                         'ClippingPlanes', 'Bitmaps']}
COMPONENTS_ORDER = {'2.1': ['ViewSetupHints', 'Selection', 'Visibility', 'Coloring'],
                    '3.0': ['Selection', 'Visibility', 'Coloring']}
CAMERA_ORDER = {
    ('2.1', 'PerspectiveCamera'): ['CameraViewPoint', 'CameraDirection', 'CameraUpVector',
                                   'FieldOfView'],
    ('2.1', 'OrthogonalCamera'): ['CameraViewPoint', 'CameraDirection', 'CameraUpVector',
                                  'ViewToWorldScale'],
    ('3.0', 'PerspectiveCamera'): ['CameraViewPoint', 'CameraDirection', 'CameraUpVector',
                                   'FieldOfView', 'AspectRatio'],
    ('3.0', 'OrthogonalCamera'): ['CameraViewPoint', 'CameraDirection', 'CameraUpVector',
                                  'ViewToWorldScale', 'AspectRatio'],
}
EXTENSION_LISTS = [('types', 'TopicTypes', 'TopicType'), ('statuses', 'TopicStatuses', 'TopicStatus'),
                   ('priorities', 'Priorities', 'Priority'), ('labels', 'TopicLabels', 'TopicLabel'),
                   ('users', 'Users', 'User'), ('snippet_types', 'SnippetTypes', 'SnippetType'),
                   ('stages', 'Stages', 'Stage')]


class BcfError(ValueError):
    """The file is not a BCF this module can read (the message is a toast sentence)."""


# =====================================================================================
# Small helpers
# =====================================================================================


def _t(value):
    if value is None:
        return ''
    return u'%s' % (value,)


def _clean(text):
    return _BAD_XML.sub(u'', _t(text))


def esc(text):
    """XML-escaped text (element content and quoted attributes), illegal characters dropped."""
    return (_clean(text).replace(u'&', u'&amp;').replace(u'<', u'&lt;').replace(u'>', u'&gt;')
            .replace(u'"', u'&quot;'))


def num(value):
    """A number as XML text: up to 12 significant digits, no exponent for normal model
    coordinates, '-0' written as '0'."""
    v = float(value)
    if v == 0.0:
        return '0'
    text = '%.12g' % v
    if 'e' in text or 'E' in text:
        text = ('%.12f' % v).rstrip('0').rstrip('.')
    return text


def guid(value=None):
    """A lowercase GUID text: value normalised when it is one, else a fresh uuid4."""
    text = _t(value).strip().strip('{}').lower()
    if GUID_RE.match(text):
        return text
    if re.match(r'^[a-f0-9]{32}$', text):
        return '%s-%s-%s-%s-%s' % (text[:8], text[8:12], text[12:16], text[16:20], text[20:])
    return str(uuid.uuid4()).lower()


def project_guid(name):
    """A stable project GUID for a project / model name (uuid5)."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, 'playground:' + _t(name).lower())).lower()


def xs_datetime(value):
    """'YYYY-MM-DDTHH:MM:SSZ' (UTC) for a local datetime or any text namo.dates reads;
    '' when blank or unreadable."""
    from namo import dates
    if value is None or not _t(value).strip():
        return ''
    dt = dates.parse(value)
    if dt is None:
        return ''
    try:
        utc = datetime.datetime.utcfromtimestamp(time.mktime(dt.timetuple()))
        return utc.strftime('%Y-%m-%dT%H:%M:%SZ')
    except (OverflowError, ValueError, OSError):
        return dt.strftime('%Y-%m-%dT%H:%M:%S')


def xs_date_only(value):
    """'YYYY-MM-DDT00:00:00' (no zone: a calendar date) for a due date; '' when blank."""
    from namo import dates
    if value is None or not _t(value).strip():
        return ''
    dt = dates.parse(value)
    return dt.strftime('%Y-%m-%dT00:00:00') if dt is not None else ''


def _bool(value):
    return 'true' if value else 'false'


def _sniff(data):
    if not data:
        return None
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        return 'png'
    if data[:3] == b'\xff\xd8\xff':
        return 'jpeg'
    return None


class _Xml(object):
    """An indented XML text builder; elements are written in the order called."""

    def __init__(self):
        self.lines = [_XML_DECL.rstrip('\n')]
        self.depth = 0

    def _attrs(self, attrs):
        out = []
        for key, value in attrs or []:
            if value is None or value == '':
                continue
            out.append(u' %s="%s"' % (key, esc(value)))
        return u''.join(out)

    def open(self, tag, attrs=None):
        self.lines.append(u'%s<%s%s>' % ('  ' * self.depth, tag, self._attrs(attrs)))
        self.depth += 1

    def close(self, tag):
        self.depth -= 1
        self.lines.append(u'%s</%s>' % ('  ' * self.depth, tag))

    def leaf(self, tag, text, attrs=None):
        self.lines.append(u'%s<%s%s>%s</%s>' % ('  ' * self.depth, tag, self._attrs(attrs),
                                                esc(text), tag))

    def empty(self, tag, attrs=None):
        self.lines.append(u'%s<%s%s />' % ('  ' * self.depth, tag, self._attrs(attrs)))

    def text(self):
        return u'\n'.join(self.lines) + u'\n'

    def bytes(self):
        return self.text().encode('utf-8')


def _point(x, tag, point):
    x.open(tag)
    x.leaf('X', num(point[0]))
    x.leaf('Y', num(point[1]))
    x.leaf('Z', num(point[2]))
    x.close(tag)


# =====================================================================================
# Writing
# =====================================================================================


def _check_version(version):
    version = _t(version).strip()
    if version not in VERSIONS:
        raise ValueError('BCF version must be %s, not %s.' % (' or '.join(VERSIONS), version or 'blank'))
    return version


def version_xml(version):
    version = _check_version(version)
    x = _Xml()
    if version == '2.1':
        x.open('Version', [('VersionId', '2.1')])
        x.leaf('DetailedVersion', '2.1')
        x.close('Version')
    else:
        x.empty('Version', [('VersionId', '3.0')])
    return x.bytes()


def project_xml(project, version):
    """project.bcfp. project: {'id' (guid), 'name'}."""
    version = _check_version(version)
    project = project or {}
    pid = guid(project.get('id')) if project.get('id') else project_guid(project.get('name'))
    name = _t(project.get('name')) or 'Project'
    x = _Xml()
    if version == '2.1':
        x.open('ProjectExtension')
        x.open('Project', [('ProjectId', pid)])
        x.leaf('Name', name)
        x.close('Project')
        x.leaf('ExtensionSchema', '')
        x.close('ProjectExtension')
    else:
        x.open('ProjectInfo')
        x.open('Project', [('ProjectId', pid)])
        x.leaf('Name', name)
        x.close('Project')
        x.close('ProjectInfo')
    return x.bytes()


def extensions_of(topics):
    """{'types', 'statuses', 'priorities', 'labels', 'users'}: the sorted distinct values
    the topics use (BCF 3.0 extensions.xml)."""
    found = {'types': set(), 'statuses': set(), 'priorities': set(), 'labels': set(),
             'users': set()}
    for topic in topics:
        for key, field in (('types', 'type'), ('statuses', 'status'), ('priorities', 'priority')):
            if _t(topic.get(field)).strip():
                found[key].add(_t(topic.get(field)).strip())
        for label in topic.get('labels') or []:
            if _t(label).strip():
                found['labels'].add(_t(label).strip())
        for field in ('assigned_to', 'creation_author', 'modified_author'):
            if _t(topic.get(field)).strip():
                found['users'].add(_t(topic.get(field)).strip())
        for comment in topic.get('comments') or []:
            if _t(comment.get('author')).strip():
                found['users'].add(_t(comment.get('author')).strip())
    return dict((k, sorted(v, key=lambda s: s.lower())) for k, v in found.items())


def extensions_xml(extensions):
    """extensions.xml (BCF 3.0) from {'types': [...], 'statuses': [...], ...}."""
    x = _Xml()
    x.open('Extensions')
    for key, wrapper, tag in EXTENSION_LISTS:
        values = [v for v in (extensions or {}).get(key) or [] if _t(v).strip()]
        if not values:
            continue
        x.open(wrapper)
        for value in values:
            x.leaf(tag, value)
        x.close(wrapper)
    x.close('Extensions')
    return x.bytes()


def documents_xml(documents):
    """documents.xml (BCF 3.0) from [{'guid', 'filename', 'description'}]."""
    x = _Xml()
    x.open('DocumentInfo')
    if documents:
        x.open('Documents')
        for doc in documents:
            x.open('Document', [('Guid', guid(doc.get('guid')))])
            x.leaf('Filename', _t(doc.get('filename')) or 'document')
            if _t(doc.get('description')):
                x.leaf('Description', doc.get('description'))
            x.close('Document')
        x.close('Documents')
    x.close('DocumentInfo')
    return x.bytes()


def _write_comment(x, comment, version):
    x.open('Comment', [('Guid', guid(comment.get('guid')))])
    x.leaf('Date', xs_datetime(comment.get('date')) or xs_datetime(datetime.datetime.now()))
    x.leaf('Author', _t(comment.get('author')) or 'Unknown')
    text = _t(comment.get('comment'))
    if version == '2.1' or text:
        x.leaf('Comment', text)
    if _t(comment.get('viewpoint_guid')):
        x.empty('Viewpoint', [('Guid', guid(comment['viewpoint_guid']))])
    if xs_datetime(comment.get('modified_date')):
        x.leaf('ModifiedDate', xs_datetime(comment['modified_date']))
    if _t(comment.get('modified_author')):
        x.leaf('ModifiedAuthor', comment['modified_author'])
    x.close('Comment')


def _write_viewpoint_ref(x, vp, tag):
    x.open(tag, [('Guid', vp['guid'])])
    if vp.get('viewpoint'):
        x.leaf('Viewpoint', vp['viewpoint'])
    if vp.get('snapshot'):
        x.leaf('Snapshot', vp['snapshot'])
    if vp.get('index') is not None:
        x.leaf('Index', str(int(vp['index'])))
    x.close(tag)


def markup_xml(topic, version):
    """markup.bcf for one topic. topic['viewpoints'] entries must already carry their
    'guid', 'viewpoint' and 'snapshot' file names (package() assigns them)."""
    version = _check_version(version)
    x = _Xml()
    x.open('Markup')
    attrs = [('Guid', guid(topic.get('guid'))),
             ('TopicType', _t(topic.get('type')).strip() or ('Issue' if version == '3.0' else '')),
             ('TopicStatus', _t(topic.get('status')).strip() or ('Open' if version == '3.0' else ''))]
    x.open('Topic', attrs)
    links = [l for l in topic.get('reference_links') or [] if _t(l).strip()]
    if links and version == '2.1':
        for link in links:
            x.leaf('ReferenceLink', link)
    elif links:
        x.open('ReferenceLinks')
        for link in links:
            x.leaf('ReferenceLink', link)
        x.close('ReferenceLinks')
    x.leaf('Title', _t(topic.get('title')).strip() or 'Untitled')
    if _t(topic.get('priority')).strip():
        x.leaf('Priority', topic['priority'])
    if version == '2.1' and topic.get('index') is not None:
        try:
            x.leaf('Index', str(int(topic['index'])))
        except (TypeError, ValueError):
            pass
    labels = [l for l in topic.get('labels') or [] if _t(l).strip()]
    if labels and version == '2.1':
        for label in labels:
            x.leaf('Labels', label)
    elif labels:
        x.open('Labels')
        for label in labels:
            x.leaf('Label', label)
        x.close('Labels')
    x.leaf('CreationDate', xs_datetime(topic.get('creation_date')) or xs_datetime(datetime.datetime.now()))
    x.leaf('CreationAuthor', _t(topic.get('creation_author')).strip() or 'Unknown')
    if xs_datetime(topic.get('modified_date')):
        x.leaf('ModifiedDate', xs_datetime(topic['modified_date']))
    if _t(topic.get('modified_author')).strip():
        x.leaf('ModifiedAuthor', topic['modified_author'])
    if xs_date_only(topic.get('due_date')):
        x.leaf('DueDate', xs_date_only(topic['due_date']))
    if _t(topic.get('assigned_to')).strip():
        x.leaf('AssignedTo', topic['assigned_to'])
    if _t(topic.get('stage')).strip():
        x.leaf('Stage', topic['stage'])
    if _t(topic.get('description')):
        x.leaf('Description', topic['description'])
    references = topic.get('document_references') or []
    if references and version == '2.1':
        for ref in references:
            x.open('DocumentReference', [('Guid', guid(ref.get('guid'))),
                                         ('isExternal', _bool(ref.get('is_external', True)))])
            if _t(ref.get('referenced_document') or ref.get('url')):
                x.leaf('ReferencedDocument', ref.get('referenced_document') or ref.get('url'))
            if _t(ref.get('description')):
                x.leaf('Description', ref['description'])
            x.close('DocumentReference')
    elif references:
        x.open('DocumentReferences')
        for ref in references:
            x.open('DocumentReference', [('Guid', guid(ref.get('guid')))])
            if _t(ref.get('document_guid')):
                x.leaf('DocumentGuid', guid(ref['document_guid']))
            else:
                x.leaf('Url', ref.get('url') or ref.get('referenced_document') or '')
            if _t(ref.get('description')):
                x.leaf('Description', ref['description'])
            x.close('DocumentReference')
        x.close('DocumentReferences')
    related = [guid(g) for g in topic.get('related_topics') or [] if _t(g).strip()]
    if related and version == '2.1':
        for g in related:
            x.empty('RelatedTopic', [('Guid', g)])
    elif related:
        x.open('RelatedTopics')
        for g in related:
            x.empty('RelatedTopic', [('Guid', g)])
        x.close('RelatedTopics')
    comments = topic.get('comments') or []
    viewpoints = topic.get('viewpoints') or []
    if version == '3.0':
        if comments:
            x.open('Comments')
            for comment in comments:
                _write_comment(x, comment, version)
            x.close('Comments')
        if viewpoints:
            x.open('Viewpoints')
            for vp in viewpoints:
                _write_viewpoint_ref(x, vp, 'ViewPoint')
            x.close('Viewpoints')
        x.close('Topic')
    else:
        x.close('Topic')
        for comment in comments:
            _write_comment(x, comment, version)
        for vp in viewpoints:
            _write_viewpoint_ref(x, vp, 'Viewpoints')
    x.close('Markup')
    return x.bytes()


def _write_component(x, component):
    x.open('Component', [('IfcGuid', component.get('ifc_guid'))])
    if _t(component.get('originating_system')).strip():
        x.leaf('OriginatingSystem', component['originating_system'])
    if _t(component.get('authoring_tool_id')).strip():
        x.leaf('AuthoringToolId', component['authoring_tool_id'])
    x.close('Component')


def _valid_components(components, notes):
    out = []
    dropped = 0
    for component in components or []:
        if IFC_GUID_RE.match(_t(component.get('ifc_guid'))):
            out.append(component)
        else:
            dropped += 1
    if dropped:
        notes.append('%d component%s without a valid IFC GlobalId left out.'
                     % (dropped, '' if dropped == 1 else 's'))
    return out


def visinfo_xml(visinfo, version, notes=None, adjusted=None):
    """viewpoint.bcfv. Returns bytes; what was changed on the way out (FOV clamped for
    2.1, components without an IFC GUID dropped, aspect ratio assumed) is appended to
    notes. adjusted: a dict that, when given, counts the harmless camera adjustments
    instead ({'fov': n, 'aspect': n}), so a caller can tell them from real losses."""
    version = _check_version(version)
    notes = notes if notes is not None else []
    visinfo = visinfo or {}
    x = _Xml()
    x.open('VisualizationInfo', [('Guid', guid(visinfo.get('guid')))])
    selection = _valid_components(visinfo.get('selection'), notes)
    visibility = visinfo.get('visibility') or {}
    exceptions = _valid_components(visibility.get('exceptions'), notes)
    coloring = [c for c in visinfo.get('coloring') or []
                if _valid_components(c.get('components'), []) and _color_ok(c.get('color'))]
    if selection or exceptions or coloring:
        x.open('Components')
        if selection:
            x.open('Selection')
            for component in selection:
                _write_component(x, component)
            x.close('Selection')
        vis_attrs = [('DefaultVisibility', _bool(visibility.get('default', True)))]
        if exceptions:
            x.open('Visibility', vis_attrs)
            x.open('Exceptions')
            for component in exceptions:
                _write_component(x, component)
            x.close('Exceptions')
            x.close('Visibility')
        else:
            x.empty('Visibility', vis_attrs)
        if coloring:
            x.open('Coloring')
            for color in coloring:
                x.open('Color', [('Color', _t(color['color']).upper().lstrip('#'))])
                for component in _valid_components(color.get('components'), []):
                    _write_component(x, component)
                x.close('Color')
            x.close('Coloring')
        x.close('Components')
    cam = visinfo.get('camera')
    if cam:
        _write_camera(x, cam, version, notes, adjusted)
    lines = visinfo.get('lines') or []
    if lines:
        x.open('Lines')
        for line in lines:
            x.open('Line')
            _point(x, 'StartPoint', line['start'])
            _point(x, 'EndPoint', line['end'])
            x.close('Line')
        x.close('Lines')
    planes = visinfo.get('clipping_planes') or []
    if planes:
        x.open('ClippingPlanes')
        for plane in planes:
            x.open('ClippingPlane')
            _point(x, 'Location', plane['location'])
            _point(x, 'Direction', plane['direction'])
            x.close('ClippingPlane')
        x.close('ClippingPlanes')
    x.close('VisualizationInfo')
    return x.bytes()


def _color_ok(value):
    return bool(re.match(r'^([0-9A-Fa-f]{6}|[0-9A-Fa-f]{8})$', _t(value).lstrip('#')))


def _adjust(adjusted, key, notes, sentence):
    if adjusted is None:
        notes.append(sentence)
    else:
        adjusted[key] = adjusted.get(key, 0) + 1


def _write_camera(x, cam, version, notes, adjusted=None):
    kind = cam.get('type') or ('OrthogonalCamera' if cam.get('ViewToWorldScale') is not None
                               else 'PerspectiveCamera')
    if kind not in ('PerspectiveCamera', 'OrthogonalCamera'):
        kind = 'PerspectiveCamera'
    x.open(kind)
    _point(x, 'CameraViewPoint', cam['CameraViewPoint'])
    _point(x, 'CameraDirection', cam['CameraDirection'])
    _point(x, 'CameraUpVector', cam.get('CameraUpVector') or (0.0, 0.0, 1.0))
    if kind == 'PerspectiveCamera':
        fov = cam.get('FieldOfView')
        fov = 60.0 if fov is None else float(fov)
        if version == '2.1':
            low, high = FOV_RANGE_21
            if fov < low or fov > high:
                _adjust(adjusted, 'fov', notes,
                        'Field of view %.1f degrees clamped to %.0f..%.0f for BCF 2.1.'
                        % (fov, low, high))
                fov = max(low, min(high, fov))
        else:
            fov = max(1.0, min(179.0, fov))
        x.leaf('FieldOfView', num(fov))
    else:
        scale = cam.get('ViewToWorldScale')
        scale = 1.0 if scale is None or float(scale) <= 0 else float(scale)
        x.leaf('ViewToWorldScale', num(scale))
    if version == '3.0':
        aspect = cam.get('AspectRatio')
        try:
            aspect = float(aspect)
        except (TypeError, ValueError):
            aspect = None
        if aspect is None or aspect <= 0:
            _adjust(adjusted, 'aspect', notes, 'Aspect ratio not known; 16:9 written.')
            aspect = DEFAULT_ASPECT
        x.leaf('AspectRatio', num(aspect))
    x.close(kind)


def merge_extensions(*sources):
    """One extensions dict from several (each list merged, distinct, sorted)."""
    out = {}
    for source in sources:
        for key, _wrapper, _tag in EXTENSION_LISTS:
            values = (source or {}).get(key) or []
            bucket = out.setdefault(key, {})
            for value in values:
                text = _t(value).strip()
                if text:
                    bucket.setdefault(text.lower(), text)
    return dict((k, sorted(v.values(), key=lambda s: s.lower())) for k, v in out.items() if v)


def package(topics, version='2.1', project=None, documents=None, created=None, extensions=None):
    """The .bcfzip as bytes, plus a report: (data, {'topics', 'viewpoints', 'snapshots',
    'documents', 'notes': [sentence], 'adjusted': {'fov': n, 'aspect': n}}). notes are
    things left out or changed that a person should know; adjusted counts the cameras
    whose lens was brought inside what the version allows (the view still lands on the
    same place).

    topics: dicts as in the module docstring; their viewpoints may carry
    'snapshot_data' (PNG or JPEG bytes). documents (3.0 only): [{'guid', 'filename',
    'description', 'data'}] referenced from topics' document_references by
    'document_guid'. created: the zip entries' time (default now). extensions (3.0):
    vocabularies to declare on top of what the topics use (all statuses, say)."""
    version = _check_version(version)
    when = created or datetime.datetime.now()
    stamp = (when.year, when.month, when.day, when.hour, when.minute, when.second)
    notes = []
    buf = io.BytesIO()
    adjusted = {}
    report = {'topics': 0, 'viewpoints': 0, 'snapshots': 0, 'documents': 0, 'notes': notes,
              'adjusted': adjusted}
    archive = zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED)

    def put(name, data):
        info = zipfile.ZipInfo(name, stamp)
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o644 << 16
        archive.writestr(info, data)

    try:
        put('bcf.version', version_xml(version))
        put('project.bcfp', project_xml(project, version))
        prepared = []
        seen = set()
        for topic in topics:
            topic = dict(topic)
            topic['guid'] = guid(topic.get('guid'))
            if topic['guid'] in seen:
                notes.append('Topic %s appears twice; written once.' % topic['guid'])
                continue
            seen.add(topic['guid'])
            prepared.append(topic)
        if version == '3.0':
            put('extensions.xml', extensions_xml(merge_extensions(extensions_of(prepared),
                                                                  extensions)))
            docs = [d for d in documents or [] if d.get('data') is not None]
            if docs:
                put('documents.xml', documents_xml(docs))
                for doc in docs:
                    put('documents/%s' % guid(doc.get('guid')), doc['data'])
                    report['documents'] += 1
        elif documents:
            notes.append('Attached documents are a BCF 3.0 feature; not written to 2.1.')
        for topic in prepared:
            folder = topic['guid']
            viewpoints = []
            for index, vp in enumerate(topic.get('viewpoints') or []):
                vp = dict(vp)
                vp['guid'] = guid(vp.get('guid') or (vp.get('visinfo') or {}).get('guid'))
                visinfo = dict(vp.get('visinfo') or {})
                visinfo['guid'] = vp['guid']
                vp['viewpoint'] = 'viewpoint.bcfv' if index == 0 else '%s.bcfv' % vp['guid']
                put('%s/%s' % (folder, vp['viewpoint']),
                    visinfo_xml(visinfo, version, notes, adjusted))
                report['viewpoints'] += 1
                data = vp.get('snapshot_data')
                kind = _sniff(data)
                if kind:
                    ext = '.png' if kind == 'png' else '.jpg'
                    if version == '2.1' and kind != 'png':
                        notes.append('A JPEG snapshot was written to a BCF 2.1 file; '
                                     'some 2.1 readers expect PNG.')
                    vp['snapshot'] = ('snapshot' if index == 0 else vp['guid']) + ext
                    put('%s/%s' % (folder, vp['snapshot']), data)
                    report['snapshots'] += 1
                else:
                    vp['snapshot'] = ''
                vp['index'] = index if vp.get('index') is None else vp['index']
                viewpoints.append(vp)
            topic['viewpoints'] = viewpoints
            # A comment's Viewpoint must name a viewpoint of THIS topic: comments brought
            # in from another BCF keep that file's viewpoint guids, which are not written
            # here, so those references are dropped rather than left dangling.
            written = set(vp['guid'] for vp in viewpoints)
            comments = []
            for comment in topic.get('comments') or []:
                if _t(comment.get('viewpoint_guid')) and guid(comment['viewpoint_guid']) not in written:
                    comment = dict(comment)
                    comment['viewpoint_guid'] = ''
                comments.append(comment)
            topic['comments'] = comments
            put('%s/markup.bcf' % folder, markup_xml(topic, version))
            report['topics'] += 1
    finally:
        archive.close()
    return buf.getvalue(), report


def write(path, topics, version='2.1', project=None, documents=None, created=None,
          extensions=None):
    """Writes a .bcfzip atomically (namo.paths) and returns package()'s report plus
    'path'. IOError when the file cannot be written (open in another program)."""
    from namo import paths
    data, report = package(topics, version, project, documents, created, extensions)
    paths.atomic_write_bytes(path, data)
    report['path'] = path
    return report


# =====================================================================================
# Reading
# =====================================================================================


def _local(tag):
    return tag.split('}', 1)[-1] if isinstance(tag, str) or hasattr(tag, 'split') else tag


def _parse_xml(data):
    import xml.etree.ElementTree as ET
    if data[:3] == b'\xef\xbb\xbf':
        data = data[3:]
    return ET.fromstring(data)


def _kids(element, name=None):
    out = []
    for child in element:
        if not isinstance(child.tag, str) and not hasattr(child.tag, 'split'):
            continue                                   # comments, processing instructions
        if name is None or _local(child.tag) == name:
            out.append(child)
    return out


def _kid(element, name):
    if element is None:
        return None
    for child in _kids(element, name):
        return child
    return None


def _kid_text(element, name, default=''):
    child = _kid(element, name)
    if child is None or child.text is None:
        return default
    return child.text.strip() if name not in ('Description', 'Comment') else child.text


def _attr(element, name, default=''):
    if element is None:
        return default
    for key in element.attrib:
        if _local(key).lower() == name.lower():
            return element.attrib[key]
    return default


def _xyz(element):
    if element is None:
        return None
    try:
        return (float(_kid_text(element, 'X')), float(_kid_text(element, 'Y')),
                float(_kid_text(element, 'Z')))
    except (TypeError, ValueError):
        return None


def _float(text):
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _truth(text, default=False):
    value = _t(text).strip().lower()
    if value in ('true', '1'):
        return True
    if value in ('false', '0'):
        return False
    return default


def _component(element):
    return {'ifc_guid': _attr(element, 'IfcGuid'),
            'originating_system': _kid_text(element, 'OriginatingSystem'),
            'authoring_tool_id': _kid_text(element, 'AuthoringToolId')}


def parse_visinfo(data):
    """A VISINFO dict from viewpoint.bcfv bytes (2.0, 2.1 or 3.0)."""
    root = _parse_xml(data)
    out = {'guid': _attr(root, 'Guid').lower(), 'camera': None, 'selection': [],
           'visibility': {'default': True, 'exceptions': []}, 'coloring': [],
           'clipping_planes': [], 'lines': []}
    components = _kid(root, 'Components')
    if components is not None:
        flat = _kids(components, 'Component')
        if flat:                                       # BCF 2.0: one flat list
            for element in flat:
                component = _component(element)
                if _truth(_attr(element, 'Selected'), False):
                    out['selection'].append(component)
                if not _truth(_attr(element, 'Visible'), True):
                    out['visibility']['exceptions'].append(component)
                color = _attr(element, 'Color')
                if color:
                    out['coloring'].append({'color': color.upper(), 'components': [component]})
        selection = _kid(components, 'Selection')
        if selection is not None:
            out['selection'] += [_component(e) for e in _kids(selection, 'Component')]
        visibility = _kid(components, 'Visibility')
        if visibility is not None:
            out['visibility']['default'] = _truth(_attr(visibility, 'DefaultVisibility'), False)
            exceptions = _kid(visibility, 'Exceptions')
            if exceptions is not None:
                out['visibility']['exceptions'] += [_component(e) for e in _kids(exceptions, 'Component')]
        coloring = _kid(components, 'Coloring')
        if coloring is not None:
            for color in _kids(coloring, 'Color'):
                # 2.1 lists the components straight under Color; 3.0 wraps them in Components.
                members = _kids(color, 'Component')
                wrapper = _kid(color, 'Components')
                if wrapper is not None:
                    members += _kids(wrapper, 'Component')
                out['coloring'].append({'color': _attr(color, 'Color').upper(),
                                        'components': [_component(e) for e in members]})
    for kind in ('PerspectiveCamera', 'OrthogonalCamera'):
        element = _kid(root, kind)
        if element is None:
            continue
        cam = {'type': kind, 'CameraViewPoint': _xyz(_kid(element, 'CameraViewPoint')),
               'CameraDirection': _xyz(_kid(element, 'CameraDirection')),
               'CameraUpVector': _xyz(_kid(element, 'CameraUpVector')),
               'AspectRatio': _float(_kid_text(element, 'AspectRatio'))}
        if kind == 'PerspectiveCamera':
            cam['FieldOfView'] = _float(_kid_text(element, 'FieldOfView'))
        else:
            cam['ViewToWorldScale'] = _float(_kid_text(element, 'ViewToWorldScale'))
        if cam['CameraViewPoint'] is not None and cam['CameraDirection'] is not None:
            out['camera'] = cam
            break
    lines = _kid(root, 'Lines')
    if lines is not None:
        for line in _kids(lines, 'Line'):
            start, end = _xyz(_kid(line, 'StartPoint')), _xyz(_kid(line, 'EndPoint'))
            if start and end:
                out['lines'].append({'start': start, 'end': end})
    planes = _kid(root, 'ClippingPlanes')
    if planes is not None:
        for plane in _kids(planes, 'ClippingPlane'):
            location, direction = _xyz(_kid(plane, 'Location')), _xyz(_kid(plane, 'Direction'))
            if location and direction:
                out['clipping_planes'].append({'location': location, 'direction': direction})
    return out


def _comment_of(element):
    viewpoint = _kid(element, 'Viewpoint')
    return {'guid': _attr(element, 'Guid').lower(), 'date': _kid_text(element, 'Date'),
            'author': _kid_text(element, 'Author'), 'comment': _kid_text(element, 'Comment'),
            'viewpoint_guid': _attr(viewpoint, 'Guid').lower() if viewpoint is not None else '',
            'modified_date': _kid_text(element, 'ModifiedDate'),
            'modified_author': _kid_text(element, 'ModifiedAuthor'),
            'status': _kid_text(element, 'Status'),
            'verbal_status': _kid_text(element, 'VerbalStatus')}


def _viewpoint_ref(element):
    index = _kid_text(element, 'Index')
    try:
        index = int(index) if index else None
    except ValueError:
        index = None
    return {'guid': _attr(element, 'Guid').lower(), 'viewpoint': _kid_text(element, 'Viewpoint'),
            'snapshot': _kid_text(element, 'Snapshot'), 'index': index}


def parse_markup(data):
    """A topic dict (without viewpoint contents) from markup.bcf bytes, any version."""
    root = _parse_xml(data)
    topic_el = _kid(root, 'Topic')
    if topic_el is None:
        raise BcfError('A markup file has no Topic.')
    labels = []
    for element in _kids(topic_el, 'Labels'):
        inner = _kids(element, 'Label')
        if inner:
            labels += [(e.text or '').strip() for e in inner]
        elif element.text and element.text.strip():
            labels.append(element.text.strip())
    links = [(e.text or '').strip() for e in _kids(topic_el, 'ReferenceLink')]
    wrapper = _kid(topic_el, 'ReferenceLinks')
    if wrapper is not None:
        links += [(e.text or '').strip() for e in _kids(wrapper, 'ReferenceLink')]
    references = []
    ref_elements = _kids(topic_el, 'DocumentReference')
    wrapper = _kid(topic_el, 'DocumentReferences')
    if wrapper is not None:
        ref_elements += _kids(wrapper, 'DocumentReference')
    for element in ref_elements:
        references.append({'guid': _attr(element, 'Guid').lower(),
                           'document_guid': _kid_text(element, 'DocumentGuid').lower(),
                           'url': _kid_text(element, 'Url'),
                           'referenced_document': _kid_text(element, 'ReferencedDocument'),
                           'is_external': _truth(_attr(element, 'isExternal'), False),
                           'description': _kid_text(element, 'Description')})
    related = [_attr(e, 'Guid').lower() for e in _kids(topic_el, 'RelatedTopic')]
    wrapper = _kid(topic_el, 'RelatedTopics')
    if wrapper is not None:
        related += [_attr(e, 'Guid').lower() for e in _kids(wrapper, 'RelatedTopic')]
    comments = [_comment_of(e) for e in _kids(root, 'Comment')]
    wrapper = _kid(topic_el, 'Comments')
    if wrapper is not None:
        comments += [_comment_of(e) for e in _kids(wrapper, 'Comment')]
    viewpoints = [_viewpoint_ref(e) for e in _kids(root, 'Viewpoints')]
    wrapper = _kid(topic_el, 'Viewpoints')
    if wrapper is not None:
        viewpoints += [_viewpoint_ref(e) for e in _kids(wrapper, 'ViewPoint')]
    index = _kid_text(topic_el, 'Index')
    try:
        index = int(index) if index else None
    except ValueError:
        index = None
    return {
        'guid': _attr(topic_el, 'Guid').lower(), 'type': _attr(topic_el, 'TopicType'),
        'status': _attr(topic_el, 'TopicStatus'), 'title': _kid_text(topic_el, 'Title'),
        'priority': _kid_text(topic_el, 'Priority'), 'index': index, 'labels': labels,
        'creation_date': _kid_text(topic_el, 'CreationDate'),
        'creation_author': _kid_text(topic_el, 'CreationAuthor'),
        'modified_date': _kid_text(topic_el, 'ModifiedDate'),
        'modified_author': _kid_text(topic_el, 'ModifiedAuthor'),
        'due_date': _kid_text(topic_el, 'DueDate'),
        'assigned_to': _kid_text(topic_el, 'AssignedTo'),
        'stage': _kid_text(topic_el, 'Stage'),
        'description': _kid_text(topic_el, 'Description'),
        'reference_links': [l for l in links if l],
        'related_topics': [g for g in related if g],
        'document_references': references,
        'comments': comments,
        'viewpoints': viewpoints,
    }


def _open_zip(source):
    try:
        if isinstance(source, (bytes, bytearray)):
            return zipfile.ZipFile(io.BytesIO(bytes(source)))
        return zipfile.ZipFile(source)
    except (zipfile.BadZipfile, IOError, OSError) as error:
        raise BcfError('This is not a BCF file (%s).' % error)


def _names(archive):
    """{lower name: real name} with folders normalised to '/'."""
    return dict((n.replace('\\', '/').lower(), n) for n in archive.namelist() if not n.endswith('/'))


def _read(archive, names, name):
    real = names.get(name.lower())
    return archive.read(real) if real is not None else None


def read(source):
    """Reads a .bcfzip/.bcf (a path or bytes) of BCF 2.0, 2.1 or 3.0:

    {'version': '2.1', 'project': {'id', 'name'}, 'extensions': {...},
     'documents': {guid: {'filename', 'description', 'data'}},
     'topics': [topic dicts with viewpoints' 'visinfo' and 'snapshot_data'],
     'notes': [sentences about anything skipped]}

    Topics come in Index order, then creation date, then title. BcfError (a toast
    sentence) when it is not a BCF zip at all; a damaged topic is skipped with a note."""
    archive = _open_zip(source)
    notes = []
    try:
        names = _names(archive)
        version = ''
        data = _read(archive, names, 'bcf.version')
        if data is not None:
            try:
                version = _attr(_parse_xml(data), 'VersionId').strip()
            except Exception:
                notes.append('bcf.version could not be read.')
        if not version:
            version = '2.1'
            notes.append('No version file; read as BCF 2.1.')
        elif version not in READ_VERSIONS and not version.startswith(('2.', '3.')):
            notes.append('BCF %s is not a version this reader knows; read as best it can.' % version)
        project = {'id': '', 'name': ''}
        data = _read(archive, names, 'project.bcfp')
        if data is not None:
            try:
                root = _parse_xml(data)
                element = _kid(root, 'Project')
                if element is not None:
                    project = {'id': _attr(element, 'ProjectId'), 'name': _kid_text(element, 'Name')}
            except Exception:
                notes.append('project.bcfp could not be read.')
        extensions = {}
        data = _read(archive, names, 'extensions.xml')
        if data is not None:
            try:
                root = _parse_xml(data)
                for key, wrapper, tag in EXTENSION_LISTS:
                    element = _kid(root, wrapper)
                    if element is not None:
                        extensions[key] = [(e.text or '').strip() for e in _kids(element, tag)]
            except Exception:
                notes.append('extensions.xml could not be read.')
        documents = {}
        data = _read(archive, names, 'documents.xml')
        if data is not None:
            try:
                root = _parse_xml(data)
                wrapper = _kid(root, 'Documents')
                for element in _kids(wrapper, 'Document') if wrapper is not None else []:
                    key = _attr(element, 'Guid').lower()
                    documents[key] = {'filename': _kid_text(element, 'Filename'),
                                      'description': _kid_text(element, 'Description'),
                                      'data': _read(archive, names, 'documents/' + key)}
            except Exception:
                notes.append('documents.xml could not be read.')
        topics = []
        markups = sorted(n for n in names if n.endswith('/markup.bcf'))
        for name in markups:
            folder = name[:-len('markup.bcf')]
            try:
                topic = parse_markup(archive.read(names[name]))
            except Exception as error:
                notes.append('Topic %s skipped: %s' % (folder.rstrip('/'), error))
                continue
            if not topic['guid']:
                topic['guid'] = folder.rstrip('/').split('/')[-1].lower()
            refs = topic['viewpoints']
            if not refs and (folder + 'viewpoint.bcfv') in names:
                refs = [{'guid': '', 'viewpoint': 'viewpoint.bcfv',
                         'snapshot': 'snapshot.png' if (folder + 'snapshot.png') in names else '',
                         'index': 0}]
            viewpoints = []
            for ref in refs:
                vp = dict(ref)
                vp['visinfo'] = None
                vp['snapshot_data'] = None
                if vp.get('viewpoint'):
                    raw = _read(archive, names, folder + vp['viewpoint'])
                    if raw is None:
                        notes.append('%s: viewpoint file %s is missing.' % (topic['title'] or topic['guid'],
                                                                            vp['viewpoint']))
                    else:
                        try:
                            vp['visinfo'] = parse_visinfo(raw)
                            if not vp['guid']:
                                vp['guid'] = vp['visinfo']['guid']
                        except Exception as error:
                            notes.append('%s: viewpoint %s skipped: %s'
                                         % (topic['title'] or topic['guid'], vp['viewpoint'], error))
                if vp.get('snapshot'):
                    vp['snapshot_data'] = _read(archive, names, folder + vp['snapshot'])
                viewpoints.append(vp)
            topic['viewpoints'] = viewpoints
            topics.append(topic)
    finally:
        archive.close()
    topics.sort(key=lambda t: (t['index'] if t['index'] is not None else 1 << 30,
                               t['creation_date'] or '', (t['title'] or '').lower(), t['guid']))
    return {'version': version, 'project': project, 'extensions': extensions,
            'documents': documents, 'topics': topics, 'notes': notes}


# =====================================================================================
# Structure check
# =====================================================================================


def _order_problems(element, order, where, errors):
    """Children must be known and in sequence order (repeats allowed in place)."""
    last = -1
    for child in _kids(element):
        name = _local(child.tag)
        if name not in order:
            errors.append('%s: unexpected element %s.' % (where, name))
            continue
        position = order.index(name)
        if position < last:
            errors.append('%s: %s is out of order.' % (where, name))
        last = max(last, position)


def _require(element, names, where, errors):
    for name in names:
        if _kid(element, name) is None:
            errors.append('%s: %s is missing.' % (where, name))


def _guid_ok(value, where, errors):
    if not GUID_RE.match(_t(value)):
        errors.append('%s: Guid %r is not a lowercase GUID.' % (where, value))


def _check_component(element, where, errors):
    value = _attr(element, 'IfcGuid')
    if value and not IFC_GUID_RE.match(value):
        errors.append('%s: IfcGuid %r is not an IFC GlobalId.' % (where, value))
    _order_problems(element, ['OriginatingSystem', 'AuthoringToolId'], where, errors)


def check_visinfo(data, version, where='viewpoint'):
    """[error] for one viewpoint.bcfv against the version's structure."""
    errors = []
    try:
        root = _parse_xml(data)
    except Exception as error:
        return ['%s: not well-formed XML (%s).' % (where, error)]
    if _local(root.tag) != 'VisualizationInfo':
        return ['%s: the root is %s, not VisualizationInfo.' % (where, _local(root.tag))]
    _guid_ok(_attr(root, 'Guid'), where, errors)
    _order_problems(root, VISINFO_ORDER[version], where, errors)
    components = _kid(root, 'Components')
    if components is not None:
        _order_problems(components, COMPONENTS_ORDER[version], where + ' Components', errors)
        if _kid(components, 'Visibility') is None:
            errors.append('%s: Components without Visibility.' % where)
        for wrapper in ('Selection',):
            element = _kid(components, wrapper)
            if element is not None:
                for component in _kids(element, 'Component'):
                    _check_component(component, where + ' ' + wrapper, errors)
        visibility = _kid(components, 'Visibility')
        if visibility is not None:
            if version == '3.0':
                _order_problems(visibility, ['ViewSetupHints', 'Exceptions'], where + ' Visibility', errors)
            exceptions = _kid(visibility, 'Exceptions')
            if exceptions is not None:
                for component in _kids(exceptions, 'Component'):
                    _check_component(component, where + ' Exceptions', errors)
    cameras = [c for c in (_kid(root, 'PerspectiveCamera'), _kid(root, 'OrthogonalCamera')) if c is not None]
    if len(cameras) > 1:
        errors.append('%s: more than one camera.' % where)
    for cam in cameras:
        kind = _local(cam.tag)
        order = CAMERA_ORDER[(version, kind)]
        _order_problems(cam, order, where + ' ' + kind, errors)
        _require(cam, order, where + ' ' + kind, errors)
        for part in ('CameraViewPoint', 'CameraDirection', 'CameraUpVector'):
            element = _kid(cam, part)
            if element is not None:
                _order_problems(element, ['X', 'Y', 'Z'], where + ' ' + part, errors)
                if _xyz(element) is None:
                    errors.append('%s: %s needs numeric X, Y, Z.' % (where, part))
        if kind == 'PerspectiveCamera':
            fov = _float(_kid_text(cam, 'FieldOfView'))
            if fov is None:
                pass
            elif version == '2.1' and not FOV_RANGE_21[0] <= fov <= FOV_RANGE_21[1]:
                errors.append('%s: FieldOfView %s is outside 45..60 (BCF 2.1).' % (where, fov))
            elif version == '3.0' and not 0.0 < fov < 180.0:
                errors.append('%s: FieldOfView %s is outside 0..180.' % (where, fov))
        if version == '3.0':
            aspect = _float(_kid_text(cam, 'AspectRatio'))
            if aspect is not None and aspect <= 0:
                errors.append('%s: AspectRatio must be positive.' % where)
    return errors


def check(source):
    """Structure check of a BCF zip against its declared version (2.1 or 3.0):
    {'version', 'errors': [...], 'warnings': [...], 'topics': n}. Checks the zip,
    bcf.version, every markup (well-formed, required elements, child order, GUID
    patterns, required 3.0 attributes), every referenced viewpoint and snapshot file,
    every viewpoint (order, cameras, FOV range, IFC GUIDs), project.bcfp and
    extensions.xml. It is what dev tests run on every file the writer makes."""
    errors = []
    warnings = []
    try:
        archive = _open_zip(source)
    except BcfError as error:
        return {'version': '', 'errors': [str(error)], 'warnings': [], 'topics': 0}
    count = 0
    try:
        names = _names(archive)
        data = _read(archive, names, 'bcf.version')
        version = ''
        if data is None:
            errors.append('bcf.version is missing.')
        else:
            try:
                root = _parse_xml(data)
                if _local(root.tag) != 'Version':
                    errors.append('bcf.version: the root is %s, not Version.' % _local(root.tag))
                version = _attr(root, 'VersionId').strip()
                if not version:
                    errors.append('bcf.version: VersionId is missing.')
                _order_problems(root, ['DetailedVersion'], 'bcf.version', errors)
            except Exception as error:
                errors.append('bcf.version: not well-formed XML (%s).' % error)
        if version not in VERSIONS:
            warnings.append('Version %s: checked as 2.1.' % (version or 'unknown'))
            version = '2.1'
        data = _read(archive, names, 'project.bcfp')
        if data is not None:
            try:
                root = _parse_xml(data)
                expected = 'ProjectExtension' if version == '2.1' else 'ProjectInfo'
                if _local(root.tag) != expected:
                    errors.append('project.bcfp: the root is %s, not %s.' % (_local(root.tag), expected))
                project = _kid(root, 'Project')
                if version == '2.1':
                    _order_problems(root, ['Project', 'ExtensionSchema'], 'project.bcfp', errors)
                    _require(root, ['ExtensionSchema'], 'project.bcfp', errors)
                else:
                    _require(root, ['Project'], 'project.bcfp', errors)
                    if project is not None:
                        _require(project, ['Name'], 'project.bcfp Project', errors)
                        _guid_ok(_attr(project, 'ProjectId'), 'project.bcfp Project', errors)
                if project is not None and not _attr(project, 'ProjectId'):
                    errors.append('project.bcfp: Project has no ProjectId.')
            except Exception as error:
                errors.append('project.bcfp: not well-formed XML (%s).' % error)
        if version == '3.0':
            data = _read(archive, names, 'extensions.xml')
            if data is None:
                warnings.append('extensions.xml is missing (BCF 3.0 expects it).')
            else:
                try:
                    root = _parse_xml(data)
                    if _local(root.tag) != 'Extensions':
                        errors.append('extensions.xml: the root is %s, not Extensions.' % _local(root.tag))
                    _order_problems(root, [w for _k, w, _t2 in EXTENSION_LISTS], 'extensions.xml', errors)
                except Exception as error:
                    errors.append('extensions.xml: not well-formed XML (%s).' % error)
        folders = set()
        for name in names:
            if '/' in name and not name.startswith('documents/'):
                folders.add(name.split('/', 1)[0])
        for folder in sorted(folders):
            markup_name = folder + '/markup.bcf'
            if markup_name not in names:
                errors.append('%s: markup.bcf is missing.' % folder)
                continue
            count += 1
            where = folder + '/markup.bcf'
            if not GUID_RE.match(folder):
                warnings.append('%s: the folder is not named by the topic Guid.' % folder)
            try:
                root = _parse_xml(archive.read(names[markup_name]))
            except Exception as error:
                errors.append('%s: not well-formed XML (%s).' % (where, error))
                continue
            if _local(root.tag) != 'Markup':
                errors.append('%s: the root is %s, not Markup.' % (where, _local(root.tag)))
                continue
            _order_problems(root, MARKUP_ORDER[version], where, errors)
            topic = _kid(root, 'Topic')
            if topic is None:
                errors.append('%s: Topic is missing.' % where)
                continue
            _guid_ok(_attr(topic, 'Guid'), where + ' Topic', errors)
            if version == '3.0':
                for attribute in ('TopicType', 'TopicStatus'):
                    if not _attr(topic, attribute):
                        errors.append('%s: Topic needs %s in BCF 3.0.' % (where, attribute))
            _order_problems(topic, TOPIC_ORDER[version], where + ' Topic', errors)
            _require(topic, TOPIC_REQUIRED, where + ' Topic', errors)
            comments = _kids(root, 'Comment') if version == '2.1' else \
                _kids(_kid(topic, 'Comments'), 'Comment') if _kid(topic, 'Comments') is not None else []
            for comment in comments:
                _guid_ok(_attr(comment, 'Guid'), where + ' Comment', errors)
                _order_problems(comment, COMMENT_ORDER, where + ' Comment', errors)
                _require(comment, COMMENT_REQUIRED[version], where + ' Comment', errors)
            refs = _kids(root, 'Viewpoints') if version == '2.1' else \
                _kids(_kid(topic, 'Viewpoints'), 'ViewPoint') if _kid(topic, 'Viewpoints') is not None else []
            for ref in refs:
                _guid_ok(_attr(ref, 'Guid'), where + ' viewpoint', errors)
                _order_problems(ref, VIEWPOINT_REF_ORDER, where + ' viewpoint', errors)
                file_name = _kid_text(ref, 'Viewpoint')
                if file_name:
                    raw = _read(archive, names, folder + '/' + file_name)
                    if raw is None:
                        errors.append('%s: viewpoint file %s is missing.' % (where, file_name))
                    else:
                        errors += check_visinfo(raw, version, folder + '/' + file_name)
                snapshot = _kid_text(ref, 'Snapshot')
                if snapshot and _read(archive, names, folder + '/' + snapshot) is None:
                    errors.append('%s: snapshot %s is missing.' % (where, snapshot))
    finally:
        archive.close()
    return {'version': version, 'errors': errors, 'warnings': warnings, 'topics': count}
