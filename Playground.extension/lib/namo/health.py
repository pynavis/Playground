# -*- coding: utf-8 -*-
"""Model Health Check: a scorecard per appended model.

Pure half (unit tested): settings, distance formatting, medians, a stride sampler,
the far-away outlier search (find_far), one builder per check, evaluate() turning a
model's plain facts into checks, score() and grade(), the toast summary and the
HTML / Excel writers. API half: collect() reads the facts of every model in one
budgeted pass per model.

How the facts are gathered (per model):
  * one walk over root.DescendantsAndSelf, up to `item_budget` items, counting items
    and geometry items and keeping an evenly spaced sample of about 3,000 geometry
    items (StrideSampler);
  * the sample's objects (FindFirstObjectAncestor) give a ROBUST model centre (the
    component-wise median of their box centres, so a stray object cannot drag it)
    and the median object distance d_med from that centre;
  * far-away objects: find_far() descends the tree from the root, skipping every
    subtree whose box lies wholly within outlier_factor x d_med of the centre, so a
    clean model costs one box test and a model with a stray object costs one path of
    box tests down to it;
  * identity coverage: about 300 sampled objects probed for an Element ID, UniqueId
    or IFC GlobalId (namo.items.REVIT_PROPERTIES, by display name).

Scores: 100, minus 25 per failed check and 8 per warning, never below 0. Good from
85, Fair from 60, else Poor.
"""

import math
import time

LEVEL_ORDER = {'fail': 0, 'warn': 1, 'info': 2, 'pass': 3}

DEFAULTS = {
    'warn_km': 10.0,
    'fail_km': 100.0,
    'outlier_factor': 20.0,
    'age_days': 30,
    'item_budget': 400000,
    'formats': ['html', 'xlsx'],
    'folder': '',
    'open_report': False,
}

SAMPLE_TARGET = 3000
IDENTITY_SAMPLE = 300
OUTLIER_LIMIT = 50
OUTLIER_NODE_BUDGET = 200000
LARGE_M = 5000.0             # a site this big is possible: warn
HUGE_M = 50000.0             # a building model this big has wrong units: fail
SMALL_M = 0.05
ID_KINDS = ('RVT', 'IFC', 'IFCZIP', 'IFCXML')
# Far from the origin, what matters is how true the geometry still reads. Navisworks
# keeps each object's vertices relative to the object and places it with a double
# precision matrix, so a model in shared coordinates hundreds of kilometres out is
# usually still exact (field: under 0.001 mm at 418 km). The health check measures
# that (pynavis.geometry.float_noise through namo.mesh) instead of assuming the worst.
NOISE_FINE_M = 0.0005        # half a millimetre: the floor pynavis.faces works to
NOISE_BAD_M = 0.01
NOISE_PROBES = 6
NOISE_PRIMITIVES = 20000


def settings(values=None):
    """DEFAULTS overlaid with values, numbers coerced and kept sane."""
    out = dict(DEFAULTS)
    out['formats'] = list(DEFAULTS['formats'])
    for key, value in (values or {}).items():
        if key in out and value is not None:
            out[key] = value
    for key in ('warn_km', 'fail_km', 'outlier_factor'):
        try:
            out[key] = float(out[key])
        except (TypeError, ValueError):
            out[key] = DEFAULTS[key]
    for key in ('age_days', 'item_budget'):
        try:
            out[key] = int(out[key])
        except (TypeError, ValueError):
            out[key] = DEFAULTS[key]
    out['warn_km'] = max(0.001, out['warn_km'])
    out['fail_km'] = max(out['warn_km'], out['fail_km'])
    out['outlier_factor'] = max(2.0, out['outlier_factor'])
    out['age_days'] = max(1, out['age_days'])
    out['item_budget'] = max(1000, out['item_budget'])
    formats = [f for f in (out.get('formats') or []) if f in ('html', 'xlsx')]
    out['formats'] = sorted(set(formats), key=lambda f: ('html', 'xlsx').index(f))
    out['folder'] = str(out.get('folder') or '')
    out['open_report'] = bool(out.get('open_report'))
    return out


# ---- pure maths ---------------------------------------------------------------------


def median(values):
    """Median of numbers (mean of the middle two for an even count); None when empty."""
    data = sorted(float(v) for v in values)
    if not data:
        return None
    middle = len(data) // 2
    if len(data) % 2:
        return data[middle]
    return (data[middle - 1] + data[middle]) / 2.0


def median_point(points):
    """Component-wise median of (x, y, z) points; None when empty."""
    points = [p for p in points if p is not None]
    if not points:
        return None
    return tuple(median([p[axis] for p in points]) for axis in range(3))


def distance(a, b):
    return math.sqrt(sum((float(a[i]) - float(b[i])) ** 2 for i in range(3)))


def box_center(box):
    if box is None:
        return None
    return tuple((box[0][i] + box[1][i]) / 2.0 for i in range(3))


def box_diagonal(box):
    if box is None:
        return None
    return distance(box[0], box[1])


def farthest_corner(box, center):
    """Distance from center to the box corner farthest from it."""
    total = 0.0
    for axis in range(3):
        span = max(abs(box[0][axis] - center[axis]), abs(box[1][axis] - center[axis]))
        total += span * span
    return math.sqrt(total)


class StrideSampler(object):
    """Keeps an evenly spaced sample (every stride-th element) of a stream of unknown
    length: when the sample reaches twice the target it drops every other element and
    doubles the stride. Use: `if s.offer(): s.add(x)`."""

    def __init__(self, target=SAMPLE_TARGET):
        self.target = max(1, int(target))
        self.stride = 1
        self.seen = 0
        self.kept = []

    def offer(self):
        keep = self.seen % self.stride == 0
        self.seen += 1
        return keep

    def add(self, value):
        self.kept.append(value)
        if len(self.kept) >= 2 * self.target:
            self.kept = self.kept[::2]
            self.stride *= 2


def spread(values, count):
    """At most count values, evenly spaced, first one included, order kept."""
    values = list(values)
    if count <= 0:
        return []
    if len(values) <= count:
        return values
    step = float(len(values)) / count
    return [values[int(i * step)] for i in range(count)]


def find_far(roots, children_of, box_of, is_leaf, center, radius, node_budget=OUTLIER_NODE_BUDGET,
             limit=OUTLIER_LIMIT):
    """Leaves whose box centre is farther than radius from center, farthest first, as
    [(node, distance)], plus sampled (True when the node budget or the limit stopped
    the search before the whole tree was covered).

    Depth-first from roots; a subtree whose box lies entirely within radius of center
    (its farthest corner is no farther) is skipped without being opened. Nodes with no
    box are skipped. box_of(node) -> ((x0,y0,z0),(x1,y1,z1)) or None."""
    hits = []
    sampled = False
    visited = 0
    stack = list(reversed(list(roots)))
    while stack:
        node = stack.pop()
        visited += 1
        if visited > node_budget:
            sampled = True
            break
        box = box_of(node)
        if box is None:
            continue
        if farthest_corner(box, center) <= radius:
            continue
        if is_leaf(node):
            gap = distance(box_center(box), center)
            if gap > radius:
                hits.append((node, gap))
                if len(hits) >= limit:
                    sampled = bool(stack)
                    break
            continue
        children = list(children_of(node))
        for child in reversed(children):
            stack.append(child)
    hits.sort(key=lambda pair: -pair[1])
    return hits, sampled


# ---- pure formatting -------------------------------------------------------------------


def fmt_m(metres):
    """'412 km', '12.4 km', '84.2 m', '35 cm', '4 mm' for a length in metres."""
    if metres is None:
        return ''
    value = abs(float(metres))
    if value >= 100000:
        return '{:,.0f} km'.format(value / 1000.0)
    if value >= 1000:
        return '{:,.1f} km'.format(value / 1000.0)
    if value >= 10:
        return '{:,.0f} m'.format(value)
    if value >= 1:
        return '{:,.1f} m'.format(value)
    if value >= 0.01:
        return '{:,.0f} cm'.format(value * 100.0)
    return '{:,.0f} mm'.format(value * 1000.0)


def count_text(number):
    return '{:,}'.format(int(number))


def age_days_text(seconds):
    days = int(max(0.0, float(seconds)) // 86400)
    if days == 0:
        return 'today'
    if days == 1:
        return '1 day ago'
    return '{:,} days ago'.format(days)


# ---- checks ---------------------------------------------------------------------------------


def check(check_id, name, level, detail):
    return {'id': check_id, 'name': name, 'level': level, 'detail': detail}


def check_units(units, doc_units):
    if not units:
        return check('units', 'Units', 'info', 'The model does not say what units it uses.')
    if doc_units and units != doc_units:
        return check('units', 'Units', 'info',
                     '%s, the document uses %s (Navisworks converts).' % (units, doc_units))
    return check('units', 'Units', 'pass', '%s, the same as the document.' % units)


def check_size(diag_m, geometry):
    if diag_m is None or not geometry:
        return check('size', 'Size', 'info', 'No extent to measure.')
    if diag_m > HUGE_M:
        return check('size', 'Size', 'fail',
                     'The model spans %s corner to corner: check its units.' % fmt_m(diag_m))
    if diag_m > LARGE_M:
        return check('size', 'Size', 'warn',
                     'The model spans %s corner to corner: right for a site, wrong units for a '
                     'building.' % fmt_m(diag_m))
    if diag_m < SMALL_M:
        return check('size', 'Size', 'warn',
                     'The model is only %s across: check its units.' % fmt_m(diag_m))
    return check('size', 'Size', 'pass', 'Spans %s corner to corner.' % fmt_m(diag_m))


def fmt_fine(metres):
    """A small length for people: '0.0003 mm', '0.4 mm', '12 mm', else fmt_m."""
    value = abs(float(metres))
    if value >= 0.1:
        return fmt_m(value)
    mm = value * 1000.0
    if mm >= 10:
        return '%.0f mm' % mm
    if mm >= 0.001:
        return '%s mm' % ('%.1g' % mm)
    return 'under 0.001 mm'


def check_origin(center_m, warn_km, fail_km, noise_m=None):
    """noise_m: how far the model's vertices can be off from single precision storage
    (measured on a few objects), or None when it could not be measured; then the
    distance alone decides."""
    if center_m is None:
        return check('origin', 'Distance from origin', 'info', 'No extent to measure.')
    if center_m > warn_km * 1000.0 and noise_m is not None:
        where = 'The model sits %s from 0,0,0 (over %s km)' % (fmt_m(center_m), num_text(warn_km))
        if noise_m <= NOISE_FINE_M:
            return check('origin', 'Distance from origin', 'info',
                         '%s, as models in shared coordinates do. Its geometry still reads true '
                         'to %s, so nothing is lost.' % (where, fmt_fine(noise_m)))
        if noise_m <= NOISE_BAD_M:
            return check('origin', 'Distance from origin', 'warn',
                         '%s and its geometry reads true only to %s: expect small measuring '
                         'errors.' % (where, fmt_fine(noise_m)))
        return check('origin', 'Distance from origin', 'fail',
                     '%s and its geometry reads true only to %s: expect jitter and inaccurate '
                     'clashes; move it nearer the origin.' % (where, fmt_fine(noise_m)))
    if center_m > fail_km * 1000.0:
        return check('origin', 'Distance from origin', 'fail',
                     'The model sits %s from 0,0,0 (over %s km): expect jitter and inaccurate '
                     'clashes; move it nearer the origin.' % (fmt_m(center_m), num_text(fail_km)))
    if center_m > warn_km * 1000.0:
        return check('origin', 'Distance from origin', 'warn',
                     'The model sits %s from 0,0,0 (over %s km): precision starts to suffer.'
                     % (fmt_m(center_m), num_text(warn_km)))
    return check('origin', 'Distance from origin', 'pass', 'Centre %s from 0,0,0.' % fmt_m(center_m))


def num_text(value):
    value = float(value)
    return ('%d' % value) if value == int(value) else ('%g' % value)


def check_outliers(outliers, sampled, factor, d_med_m, searched):
    if not searched:
        return check('outliers', 'Far-away objects', 'info',
                     'Not searched: too few objects to tell what is typical.')
    if not outliers:
        detail = 'None found beyond %sx the typical %s.' % (num_text(factor), fmt_m(d_med_m))
        if sampled:
            detail += ' The search stopped early, so some may remain.'
        return check('outliers', 'Far-away objects', 'pass', detail)
    furthest = max(o.get('distance_m') or 0.0 for o in outliers)
    detail = ('%s %s more than %sx the typical %s from the model centre (furthest %s).'
              % (count_text(len(outliers)), 'object lies' if len(outliers) == 1 else 'objects lie',
                 num_text(factor), fmt_m(d_med_m), fmt_m(furthest)))
    if sampled:
        detail += ' The search stopped early: there may be more.'
    return check('outliers', 'Far-away objects', 'warn', detail)


def check_empty(geometry, walk_sampled):
    if geometry:
        return check('geometry', 'Geometry', 'pass', '%s items with geometry.' % count_text(geometry))
    if walk_sampled:
        return check('geometry', 'Geometry', 'warn',
                     'No geometry in the items read so far: the model may draw nothing.')
    return check('geometry', 'Geometry', 'fail', 'No geometry: the model draws nothing.')


def check_identity(identity, kind):
    checked = (identity or {}).get('checked') or 0
    found = (identity or {}).get('with_ids') or 0
    if not checked:
        return check('identity', 'Element IDs', 'info', 'No objects to sample.')
    share = float(found) / checked
    percent = int(round(share * 100))
    expected = (kind or '').upper() in ID_KINDS
    if not found and not expected:
        return check('identity', 'Element IDs', 'info',
                     'No element IDs (normal for DWG, DGN and point clouds).')
    detail = '%d%% of %s sampled objects carry an Element ID, UniqueId or IFC GlobalId.' % (
        percent, count_text(checked))
    if share >= 0.9:
        return check('identity', 'Element IDs', 'pass', detail)
    if share >= 0.5:
        return check('identity', 'Element IDs', 'info', detail)
    return check('identity', 'Element IDs', 'warn',
                 detail + ' Clash grouping, BCF and model compare need them.')


def check_duplicate(index, duplicate_of):
    others = [i for i in (duplicate_of or []) if i != index]
    if not others:
        return check('duplicate', 'Appended once', 'pass', 'Not appended twice.')
    names = ', '.join('model %d' % (i + 1) for i in sorted(others))
    return check('duplicate', 'Appended once', 'fail',
                 'The same file is also appended as %s: remove the extra copy.' % names)


def check_transform(transformed):
    if transformed:
        return check('transform', 'Model transform', 'warn',
                     'The model is moved, rotated or scaled by its Units and Transform: check '
                     'it is intended.')
    return check('transform', 'Model transform', 'pass', 'No transform applied.')


def check_age(stale, now, age_days):
    from namo import modelmgmt
    stale = stale or {}
    status = stale.get('status')
    if status == modelmgmt.OUT_OF_DATE:
        return check('age', 'File age', 'warn', stale.get('detail') or 'The source is newer.')
    if status in (modelmgmt.CACHE_NOT_FOUND, modelmgmt.CACHE_OFFLINE):
        return check('age', 'File age', 'warn', stale.get('detail') or 'The file cannot be found.')
    cache_time = stale.get('cache_time')
    if cache_time is None:
        return check('age', 'File age', 'info', stale.get('detail') or 'The file date is unknown.')
    age = float(now) - float(cache_time)
    if age > age_days * 86400.0:
        return check('age', 'File age', 'info',
                     'The loaded file was saved %s (over %d days).' % (age_days_text(age), age_days))
    return check('age', 'File age', 'pass', 'The loaded file was saved %s.' % age_days_text(age))


def check_counts(items, geometry, walk_sampled, budget):
    detail = '%s items, %s with geometry.' % (count_text(items), count_text(geometry))
    if walk_sampled:
        detail = 'At least %s items (counting stopped at %s), %s with geometry so far.' % (
            count_text(items), count_text(budget), count_text(geometry))
    return check('items', 'Items', 'info', detail)


def evaluate(facts, values=None):
    """The checks (list of dicts, display order) for one model's facts."""
    cfg = settings(values)
    if facts.get('error'):
        return [check('read', 'Read', 'fail', 'Could not read this model: %s' % facts['error'])]
    out = [
        check_units(facts.get('units'), facts.get('doc_units')),
        check_size(facts.get('diag_m'), facts.get('geometry')),
        check_origin(facts.get('center_m'), cfg['warn_km'], cfg['fail_km'], facts.get('noise_m')),
        check_outliers(facts.get('outliers') or [], facts.get('outliers_sampled'),
                       cfg['outlier_factor'], facts.get('d_med_m'), facts.get('outliers_searched')),
        check_empty(facts.get('geometry') or 0, facts.get('walk_sampled')),
        check_identity(facts.get('identity'), facts.get('kind')),
        check_duplicate(facts.get('index'), facts.get('duplicate_of')),
        check_transform(facts.get('transformed')),
        check_age(facts.get('stale'), facts.get('now') or time.time(), cfg['age_days']),
        check_counts(facts.get('items') or 0, facts.get('geometry') or 0,
                     facts.get('walk_sampled'), cfg['item_budget']),
    ]
    return out


def score(checks):
    fails = sum(1 for c in checks if c['level'] == 'fail')
    warns = sum(1 for c in checks if c['level'] == 'warn')
    return max(0, 100 - 25 * fails - 8 * warns)


def grade(value):
    if value >= 85:
        return 'Good'
    if value >= 60:
        return 'Fair'
    return 'Poor'


def grade_level(name):
    return {'Good': 'pass', 'Fair': 'warn', 'Poor': 'fail'}.get(name, 'info')


def scored(facts, values=None):
    """facts plus 'checks', 'score', 'grade', 'fails', 'warns' (a new dict)."""
    out = dict(facts)
    checks = evaluate(facts, values)
    out['checks'] = checks
    out['score'] = score(checks)
    out['grade'] = grade(out['score'])
    out['fails'] = sum(1 for c in checks if c['level'] == 'fail')
    out['warns'] = sum(1 for c in checks if c['level'] == 'warn')
    return out


def overview(models):
    """{'models', 'average', 'fails', 'warns', 'attention'}: attention = models not Good."""
    count = len(models)
    average = int(round(sum(m['score'] for m in models) / float(count))) if count else 0
    return {'models': count, 'average': average,
            'fails': sum(m['fails'] for m in models), 'warns': sum(m['warns'] for m in models),
            'attention': [m for m in models if m['grade'] != 'Good']}


def summary(models):
    """(level, message, detail) for the toast."""
    if not models:
        return ('info', 'No models to check', 'Append models first, then run the health check.')
    view = overview(models)
    attention = sorted(view['attention'], key=lambda m: (m['score'], m['index']))
    if not attention:
        if view['models'] == 1:
            return ('success', 'The model looks healthy', 'Score %d.' % view['average'])
        return ('success', 'All %d models look healthy' % view['models'],
                'Average score %d.' % view['average'])
    parts = ['%s %d (%s)' % (m['name'], m['score'], m['grade']) for m in attention[:3]]
    if len(attention) > 3:
        parts.append('%d more' % (len(attention) - 3))
    noun = 'model needs' if len(attention) == 1 else 'models need'
    return ('warning', 'Health check: %d %s attention' % (len(attention), noun), ', '.join(parts) + '.')


def json_safe(models):
    """The scored models without anything that is not JSON (ModelItems stay out)."""
    keys = ('index', 'name', 'kind', 'units', 'doc_units', 'file', 'source', 'diag_m', 'center_m',
            'items', 'geometry', 'walk_sampled', 'd_med_m', 'outliers', 'outliers_sampled',
            'outliers_searched', 'identity', 'duplicate_of', 'transformed', 'stale', 'error', 'noise_m',
            'checks', 'score', 'grade', 'fails', 'warns', 'box')
    out = []
    for model in models:
        out.append(dict((k, model.get(k)) for k in keys))
    return out


# ---- writers (pure) ------------------------------------------------------------------------

_TONE = {'pass': 'good', 'warn': 'warn', 'fail': 'bad', 'info': 'info'}
_LABEL = {'pass': 'Pass', 'warn': 'Warning', 'fail': 'Fail', 'info': 'Info'}


def write_html(path, models, title='Model health check', subtitle=None, meta=None):
    """A standalone HTML report (namo.htmlreport). Returns path."""
    from namo import htmlreport
    view = overview(models)
    report = htmlreport.Report(title, subtitle=subtitle, meta=meta)
    report.kpis([('Models', view['models'], None),
                 ('Average score', view['average'], 'good' if view['average'] >= 85 else
                  ('warn' if view['average'] >= 60 else 'bad')),
                 ('Failed checks', view['fails'], 'bad' if view['fails'] else None),
                 ('Warnings', view['warns'], 'warn' if view['warns'] else None)])
    report.section('Scores', intro='One row per appended model, worst first.')
    rows = []
    html_cells = set()
    ordered = sorted(models, key=lambda m: (m['score'], m['index']))
    for r, model in enumerate(ordered):
        rows.append([model['name'], model['score'],
                     report.status(model['grade'], _TONE[grade_level(model['grade'])]),
                     model['fails'], model['warns'], model.get('items') or 0, model.get('units') or ''])
        html_cells.add((r, 2))
    report.table(['Model', 'Score', 'Grade', 'Fails', 'Warnings', 'Items', 'Units'], rows,
                 cell_html=html_cells)
    for model in sorted(models, key=lambda m: m['index']):
        report.section(model['name'], intro='Score %d (%s). %s' % (
            model['score'], model['grade'], model.get('file') or model.get('source') or ''))
        check_rows = []
        cells = set()
        for r, item in enumerate(model['checks']):
            check_rows.append([report.status(_LABEL[item['level']], _TONE[item['level']]),
                               item['name'], item['detail']])
            cells.add((r, 0))
        report.table(['Result', 'Check', 'Detail'], check_rows, cell_html=cells, numeric=[],
                     filterable=False)
        if model.get('outliers'):
            report.table(['Object', 'Distance from centre', 'Where'],
                         [[o.get('name', ''), fmt_m(o.get('distance_m')), o.get('path', '')]
                          for o in model['outliers']],
                         numeric=[], caption='Far-away objects')
    return report.save(path)


def write_xlsx(path, models, title='Model health check', author=None):
    """Summary, Checks and Outliers sheets (namo.xlsx). Returns path."""
    from namo import xlsx
    wb = xlsx.Workbook(title=title, author=author)
    ws = wb.sheet('Summary')
    ws.title(title, span=8)
    ws.columns([('Model', 32, None), ('Score', 8, 'int'), ('Grade', 9, None), ('Fails', 7, 'int'),
                ('Warnings', 10, 'int'), ('Items', 12, 'int'), ('Units', 12, None),
                ('File', 60, None)])
    style_for = {'Good': 'good', 'Fair': 'warn', 'Poor': 'bad'}
    for model in sorted(models, key=lambda m: (m['score'], m['index'])):
        ws.row([model['name'], model['score'], model['grade'], model['fails'], model['warns'],
                model.get('items') or 0, model.get('units') or '',
                model.get('file') or model.get('source') or ''],
               styles=[None, None, style_for.get(model['grade'])])
    ws.autofilter()
    checks = wb.sheet('Checks')
    checks.columns([('Model', 32, None), ('Check', 22, None), ('Result', 10, None),
                    ('Detail', 90, 'wrap')])
    level_style = {'pass': 'good', 'warn': 'warn', 'fail': 'bad', 'info': 'info'}
    for model in sorted(models, key=lambda m: m['index']):
        for item in model['checks']:
            checks.row([model['name'], item['name'], _LABEL[item['level']], item['detail']],
                       styles=[None, None, level_style[item['level']]])
    checks.autofilter()
    far = wb.sheet('Outliers')
    far.columns([('Model', 32, None), ('Object', 40, None), ('Distance (m)', 14, 'num2'),
                 ('Where', 90, None)])
    for model in sorted(models, key=lambda m: m['index']):
        for item in model.get('outliers') or []:
            far.row([model['name'], item.get('name', ''), item.get('distance_m'), item.get('path', '')])
    far.autofilter()
    return wb.save(path)


def card_html(model, link=None):
    """Output-window HTML for one model: heading, score and grade chip, checklist,
    far-away objects (link(i) may return element-link HTML for outlier i)."""
    from namo import mdl_output as out
    parts = ['<div class="pynavis-card">',
             '<h2>%s <span style="font-weight:300;color:var(--muted);">%d</span> %s</h2>'
             % (out.esc(model['name']), model['score'],
                out.chip(grade_level(model['grade']), model['grade'])),
             out.checklist(model['checks'])]
    outliers = model.get('outliers') or []
    if outliers:
        rows = []
        raw = set()
        for i, item in enumerate(outliers):
            label = link(i) if link is not None else None
            if label:
                raw.add((i, 0))
                rows.append([label, fmt_m(item.get('distance_m')), item.get('path', '')])
            else:
                rows.append([item.get('name', ''), fmt_m(item.get('distance_m')), item.get('path', '')])
        parts.append('<h3>Far-away objects</h3>')
        parts.append(out.table(['Object', 'Distance from centre', 'Where'], rows, raw=raw, numeric=[]))
    parts.append('</div>')
    return ''.join(parts)


def overview_html(models):
    from namo import mdl_output as out
    view = overview(models)
    return out.kpis([('Models', view['models'], None),
                     ('Average score', view['average'], 'pass' if view['average'] >= 85 else
                      ('warn' if view['average'] >= 60 else 'fail')),
                     ('Failed checks', view['fails'], 'fail' if view['fails'] else None),
                     ('Warnings', view['warns'], 'warn' if view['warns'] else None)])


# ---- API half --------------------------------------------------------------------------------


def _box(item):
    from namo import items
    try:
        return items.bbox(item)
    except Exception:
        return None


def _identity_present(node, pairs):
    from namo import variants
    for category, name in pairs:
        try:
            value = variants.get(node, category, name)
        except Exception:
            value = None
        if value is not None and str(value).strip():
            return True
    return False


def _identity_pairs():
    from namo import items
    pairs = []
    for field in ('element_id', 'unique_id', 'ifc_guid'):
        pairs.extend(items.REVIT_PROPERTIES[field])
    return pairs


def _path_text(item, depth=4):
    names = []
    node = item
    while node is not None:
        try:
            names.append(node.DisplayName or node.ClassDisplayName or '')
        except Exception:
            names.append('')
        node = node.Parent
    names.reverse()
    if len(names) > depth:
        names = names[:1] + ['...'] + names[-(depth - 1):]
    return ' > '.join(n for n in names if n is not None)


def measured_noise(objects, probes=NOISE_PROBES, budget=NOISE_PRIMITIVES):
    """The largest float32 noise (document units) among the triangles of a few evenly
    spaced objects, or None when no object could be read (no COM, over budget). The
    route True Distance and Clear Clash use: pynavis.geometry.world_triangles' stats."""
    from namo import mesh
    worst = None
    for obj in spread(objects, probes):
        try:
            data = mesh.item_triangles(obj, budget=budget)
        except Exception:
            continue
        if not data.get('tris'):
            continue
        noise = float(data.get('noise') or 0.0)
        worst = noise if worst is None else max(worst, noise)
    return worst


def collect_model(info, doc_units, cfg, tick=None):
    """(facts, outlier_items) for one model info dict (namo.modelmgmt.models_info).
    tick(items_read) is called every 5,000 items; a Cancelled raised there stops."""
    from namo import items as _items
    from namo import units
    root = info['root']
    to_m = lambda value: units.to_meters(value, doc_units) if value is not None else None
    facts = {'index': info['index'], 'name': info['name'], 'kind': info.get('kind') or '',
             'units': info.get('units') or '', 'doc_units': doc_units,
             'file': info.get('file') or '', 'source': info.get('source') or '',
             'transformed': bool(info.get('transformed')), 'error': None}
    box = _box(root)
    facts['box'] = [list(box[0]), list(box[1])] if box else None
    facts['diag_m'] = to_m(box_diagonal(box)) if box else None
    facts['center_m'] = to_m(distance(box_center(box), (0.0, 0.0, 0.0))) if box else None

    sampler = StrideSampler(SAMPLE_TARGET)
    count = geometry = 0
    walk_sampled = False
    budget = cfg['item_budget']
    for item in root.DescendantsAndSelf:
        count += 1
        if item.HasGeometry:
            geometry += 1
            if sampler.offer():
                sampler.add(item)
        if tick is not None and count % 5000 == 0:
            tick(count)
        if count >= budget:
            walk_sampled = True
            break
    facts['items'] = count
    facts['geometry'] = geometry
    facts['walk_sampled'] = walk_sampled

    objects = _items.dedupe([_items.object_of(leaf) for leaf in sampler.kept])
    centers = []
    for obj in objects:
        center = box_center(_box(obj))
        if center is not None:
            centers.append(center)
    model_center = median_point(centers)
    d_med = median([distance(c, model_center) for c in centers]) if model_center else None
    facts['d_med_m'] = to_m(d_med) if d_med is not None else None
    facts['outliers'] = []
    facts['outliers_sampled'] = False
    facts['outliers_searched'] = False
    outlier_items = []
    if model_center is not None and d_med and len(centers) >= 5:
        radius = cfg['outlier_factor'] * d_med
        hits, sampled = find_far([root], lambda n: n.Children, _box, lambda n: n.HasGeometry,
                                 model_center, radius)
        facts['outliers_searched'] = True
        facts['outliers_sampled'] = sampled
        seen = set()
        for leaf, gap in hits:
            obj = _items.object_of(leaf)
            if obj in seen:
                continue
            seen.add(obj)
            outlier_items.append(obj)
            facts['outliers'].append({'name': obj.DisplayName or obj.ClassDisplayName or '',
                                      'distance_m': to_m(gap), 'path': _path_text(obj)})

    facts['noise_m'] = None
    if facts['center_m'] is not None and facts['center_m'] > cfg['warn_km'] * 1000.0:
        noise = measured_noise(objects)
        facts['noise_m'] = to_m(noise) if noise is not None else None

    pairs = _identity_pairs()
    probe = spread(objects, IDENTITY_SAMPLE)
    with_ids = sum(1 for obj in probe if _identity_present(obj, pairs))
    facts['identity'] = {'checked': len(probe), 'with_ids': with_ids}
    return facts, outlier_items


def collect(doc=None, values=None, progress=None):
    """(scored model dicts, {model index: [outlier ModelItems]}) for every appended
    model. progress(fraction, label) may raise a Cancelled to stop."""
    from namo import modelmgmt, session
    import traceback
    from pynavis._api import Application
    document = doc if doc is not None else Application.ActiveDocument
    cfg = settings(values)
    infos = modelmgmt.models_info(document)
    doc_units = str(document.Units)
    stale = dict((row['index'], row) for row in modelmgmt.stale_rows(document, infos))
    duplicates = modelmgmt.duplicate_files(infos)
    dup_of = {}
    for indexes in duplicates.values():
        for index in indexes:
            dup_of[index] = sorted(indexes)
    now = time.time()
    models = []
    outliers = {}
    total = max(1, len(infos))
    for number, info in enumerate(infos):
        label = '%s (%d of %d)' % (info['name'], number + 1, len(infos))
        if progress is not None:
            progress(float(number) / total, label)

        def tick(done, number=number, label=label):
            if progress is not None:
                share = min(0.9, float(done) / cfg['item_budget'])
                progress((number + share) / total, '%s: %s items' % (label, count_text(done)))

        try:
            facts, items_far = collect_model(info, doc_units, cfg, tick)
        except Exception as error:
            if type(error).__name__ == 'Cancelled':
                raise
            session.log('error', 'health check could not read %s:\n%s'
                        % (info['name'], traceback.format_exc()))
            facts = {'index': info['index'], 'name': info['name'], 'kind': info.get('kind') or '',
                     'units': info.get('units') or '', 'doc_units': doc_units,
                     'file': info.get('file') or '', 'source': info.get('source') or '',
                     'error': str(error) or type(error).__name__}
            items_far = []
        row = stale.get(info['index'])
        if row is not None:
            facts['stale'] = {'status': row['status'], 'level': row['level'],
                              'detail': row['detail'], 'cache_time': row['cache_time']}
        facts['duplicate_of'] = dup_of.get(info['index'], [])
        facts['now'] = now
        models.append(scored(facts, cfg))
        outliers[info['index']] = items_far
    if progress is not None:
        progress(1.0, 'Done')
    return models, outliers
