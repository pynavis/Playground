# -*- coding: utf-8 -*-
"""Model Tree Export: the selection tree to depth N as an Excel workbook, one sheet per
model, each node with its depth, name, class, descendant and geometry counts and
whether it is hidden; names indented by depth and repeated in one column per level so
the tree filters and pivots in Excel."""

from namo import data_common, reports

TITLE = 'Model Tree Export'
DEFAULT_DEPTH = 4
MAX_ROWS = 200000


def default_config():
    return reports.base_config(depth=DEFAULT_DEPTH, models=[], path='', max_rows=MAX_ROWS,
                               name_template='{file} - Model tree - {date}')


def describe(config):
    models = config.get('models') or []
    return 'Depth %d, %s' % (int(config.get('depth') or DEFAULT_DEPTH),
                             '%d models' % len(models) if models else 'every model')


# ---- pure ------------------------------------------------------------------------


def aggregate(nodes):
    """Fills 'descendants' and 'geometry' (items with geometry at or under the node)
    bottom-up. nodes: pre-order [{'depth', 'own_geometry', 'below': None or (count,
    geometry) for a frontier node measured natively}]; a node's subtree ends at the
    next node with depth <= its own."""
    stack = []
    for node in nodes:
        node['descendants'] = 0
        node['geometry'] = 1 if node.get('own_geometry') else 0
    for index in range(len(nodes) - 1, -1, -1):
        node = nodes[index]
        below = node.get('below')
        if below is not None:
            node['descendants'] += below[0]
            node['geometry'] += below[1]
        while stack and nodes[stack[-1]]['depth'] > node['depth']:
            child = nodes[stack.pop()]
            if child['depth'] == node['depth'] + 1:
                node['descendants'] += 1 + child['descendants']
                node['geometry'] += child['geometry']
        stack.append(index)
    return nodes


def sheet_rows(nodes, depth):
    """Workbook rows: [depth, level 0..depth names, name, class, descendants, geometry,
    hidden]."""
    rows = []
    for node in nodes:
        levels = [''] * (depth + 1)
        levels[node['depth']] = node['name']
        rows.append([node['depth']] + levels + [node['name'], node['class'], node['descendants'],
                                                node['geometry'], 'Yes' if node['hidden'] else ''])
    return rows


def headers(depth):
    return ['Depth'] + ['Level %d' % d for d in range(depth + 1)] + ['Name', 'Class', 'Descendants',
                                                                     'Geometry items', 'Hidden']


# ---- API -------------------------------------------------------------------------


def collect(model, depth, tick=None, max_rows=MAX_ROWS):
    """(nodes, truncated) for one model's tree to depth: pre-order dicts. Nodes at the
    depth limit count their whole subtree natively (one pass over it)."""
    from namo import items
    root = model['root']
    nodes = []
    stack = [(root, 0, False)]
    frontier = []
    truncated = False
    while stack:
        item, level, parent_hidden = stack.pop()
        try:
            own_hidden = bool(item.IsHidden)
        except Exception:
            own_hidden = False
        hidden = parent_hidden or own_hidden
        try:
            name = item.DisplayName or ''
        except Exception:
            name = ''
        try:
            klass = item.ClassDisplayName or ''
        except Exception:
            klass = ''
        node = {'depth': level, 'name': name or klass, 'class': klass, 'hidden': hidden,
                'own_geometry': bool(item.HasGeometry), 'below': None}
        nodes.append(node)
        if len(nodes) >= max_rows:
            truncated = True
            break
        children = list(item.Children)
        if level >= depth:
            if children:
                frontier.append((node, item))
            continue
        for child in reversed(children):
            stack.append((child, level + 1, hidden))
    ticker = items.Ticker(tick, total=len(frontier), every=1)
    for node, item in frontier:
        count = geometry = 0
        for descendant in item.Descendants:
            count += 1
            if descendant.HasGeometry:
                geometry += 1
        node['below'] = (count, geometry)
        ticker.step()
    ticker.finish()
    return aggregate(nodes), truncated


def run(config, doc=None, interactive=True, progress=None):
    from namo import items, naming, xlsx
    document = doc if doc is not None else data_common.active_doc()
    if not data_common.has_models(document):
        return reports.result('info', 'No model is open', 'Open or append a model, then export again.')
    depth = max(0, min(30, int(config.get('depth') if config.get('depth') is not None else DEFAULT_DEPTH)))
    max_rows = int(config.get('max_rows') or MAX_ROWS)
    models = items.models(document)
    wanted = [m.lower() for m in (config.get('models') or [])]
    if wanted:
        models = [m for m in models if m['name'].lower() in wanted]
    if not models:
        return reports.result('warning', 'None of the chosen models is in this document',
                              'Choose models that are appended, or leave the list empty for all.')
    path = config.get('path') or reports.output_path(config, TITLE, 'xlsx')
    wb = xlsx.Workbook(title=TITLE, author=naming.standard_values().get('user'))
    for d in range(depth + 1):
        wb.style('indent%d' % d, indent=d)
    summary = wb.sheet('Summary')
    summary.columns([('Model', 40, None), ('Nodes exported', 16, 'int'), ('Items in model', 16, 'int'),
                     ('Geometry items', 16, 'int'), ('Note', 40, None)])
    total_rows = 0
    truncated_any = False
    span = 0.9 / len(models)
    for index, model in enumerate(models):
        data_common.report(progress, index * span, 'Reading %s' % model['name'])
        nodes, truncated = collect(model, depth,
                                   tick=data_common.stage(progress, index * span, span,
                                                          'Counting %s: %%s' % model['name'].replace('%', '')),
                                   max_rows=max(1, max_rows - total_rows))
        truncated_any = truncated_any or truncated
        total_rows += len(nodes)
        ws = wb.sheet(model['name'] or 'Model %d' % (index + 1))
        heads = headers(depth)
        specs = [('Depth', 7, 'int')] + [(h, 18, None) for h in heads[1:depth + 2]] + [
            ('Name', 40, None), ('Class', 18, None), ('Descendants', 13, 'int'), ('Geometry items', 15, 'int'),
            ('Hidden', 8, 'center')]
        ws.columns(specs, freeze=True)
        name_col = depth + 2
        for node, row in zip(nodes, sheet_rows(nodes, depth)):
            styles = [None] * len(row)
            styles[name_col] = 'indent%d' % node['depth']
            ws.row(row, styles=styles)
        ws.autofilter()
        root = nodes[0] if nodes else {'descendants': 0, 'geometry': 0}
        summary.row([model['name'], len(nodes), root['descendants'] + 1, root['geometry'],
                     'Stopped at the row limit' if truncated else ''])
        if truncated:
            break
    summary.autofilter()
    data_common.report(progress, 0.95, 'Writing the workbook')
    try:
        wb.save(path)
    except (IOError, OSError) as error:
        return reports.result('error', 'Could not write the workbook', '%s %s' % (data_common.LOCKED, error))
    message = 'Exported %s tree %s from %d %s' % ('{:,}'.format(total_rows), 'node' if total_rows == 1 else 'nodes',
                                                 len(models), 'model' if len(models) == 1 else 'models')
    if truncated_any:
        return reports.result('warning', message, 'Stopped at %s rows. %s' % ('{:,}'.format(max_rows), path),
                              [path])
    return reports.result('success', message, path, [path])
