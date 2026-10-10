# Playground foundation: the shared `namo` library (phase 1)

Three agents build the shared library before ~115 tools are written on top of it by
other agents. Those tool agents will code against the CONTRACTS below without being able
to ask you questions, so: keep the signatures stated here (you may ADD parameters with
defaults and add functions; never rename or remove), document every public function
with a docstring, and write `lib/namo/README.md` sections for your modules (see end).

Read `dev/BRIEF.md` first: it holds the engine, API, UX and verification rules that apply
to you too. All modules live in `Playground.extension/lib/namo/`. Pure modules must import
nothing from Navisworks at module level (they run under CPython pytest); API halves
lazy-import `pynavis._api` etc. inside functions, so `import namo.x` always succeeds
outside Navisworks.

Ownership:

| Agent | Modules |
|---|---|
| F1 Documents | `xlsx.py`, `htmlreport.py`, `pdf.py`, `png.py` |
| F2 Data core | `paths.py`, `config.py`, `session.py`, `store.py`, `docdb.py`, `naming.py`, `rules.py`, `trades.py`, `textmatch.py`, `ifcguid.py`, `templates.py`, `reports.py` (helpers around the registry already listed below), `dates.py`, `units.py` |
| F3 Navisworks core | `items.py`, `clashdata.py`, `camera.py`, `images.py`, `colors.py`, `paint.py`, `mesh.py`, `ui.py` |

Already written (do not change without a note): `__init__.py`, `hooks.py`.

---------------------------------------------------------------------------------------

## F1 Documents (pure, no Navisworks; CPython + IronPython)

### xlsx.py: styled Excel writer (no Excel needed)

`pynavis.xl` writes plain values with a bold header and nothing else. Playground's reports
need real workbooks: fills, number formats, widths, frozen headers, autofilter, merged
title rows, hyperlinks, embedded thumbnails. Write the OOXML package directly with
`zipfile` + string-built XML (escape everything; valid XML 1.0 chars only).

```python
wb = xlsx.Workbook()
wb.style(name, bold=False, italic=False, size=None, color=None, fill=None, border=False,
         align=None, valign=None, wrap=False, num_format=None, underline=False)  # colors 'RRGGBB'
wb.fill_style(hex_fill, base='cell')        # -> style name, cached: dynamic heatmap fills
ws = wb.sheet(name)                         # sanitised (31 chars, no []:*?/\), deduped
ws.title(text, span=6)                      # merged bold title row at the current row
ws.columns([(header, width_chars, style_or_None), ...])  # widths + header row (style 'header'),
                                            #   freezes below it, remembers the header row for autofilter
ws.row(values, styles=None, height=None)    # appends a row; styles: one name or per-cell list
ws.write(row, col, value, style=None)       # 0-based; values str/int/float/bool/None/
                                            #   datetime.date/datetime.datetime/xlsx.Formula('SUM(A2:A9)')/
                                            #   xlsx.Link(target, text)  (URL or file path)
ws.set_width(col, chars); ws.set_height(row, points); ws.merge(r1, c1, r2, c2)
ws.freeze(rows=1, cols=0); ws.autofilter(first_row=None, last_row=None)
ws.image(path_or_bytes, row, col, width_px=None, height_px=None)  # PNG/JPEG, oneCellAnchor
ws.next_row                                  # current append position
wb.save(path)                                # -> path; writes atomically (temp + replace)
xlsx.write_simple(path, sheets)              # sheets: [{'name','headers','rows','widths'}]
```
Built-in style names: `header` (bold, light grey fill, bottom border), `title`, `muted`,
`int` (#,##0), `num1` (#,##0.0), `num2`, `pct` (0%), `date` (yyyy-mm-dd), `datetime`,
`good`, `warn`, `bad`, `info` (soft fills, readable text), `link`, `wrap`, and clash status
fills `status_new`, `status_active`, `status_reviewed`, `status_approved`, `status_resolved`.
Dates are written as serial numbers with a date style. Shared strings table. Images need
drawing parts + rels + content types; read PNG/JPEG pixel size from the bytes when no size
is given. Tests (CPython): openpyxl loads the file, values/styles/merges/freeze/
autofilter/hyperlink/image count are as written; plus an IronPython run that writes a
workbook without error.

### htmlreport.py: standalone HTML report

One self-contained `.html` (inline CSS/JS/SVG, images as base64) that opens anywhere.

```python
r = htmlreport.Report(title, subtitle=None, meta=None)   # meta: [(label, value)] shown under the title
r.kpis([(label, value, tone_or_None), ...])              # tone: None|'good'|'warn'|'bad'|'info'
r.section(title, intro=None)
r.table(headers, rows, numeric=None, sortable=True, filterable=True, row_tones=None,
        cell_html=None, caption=None, max_rows=None)    # cell_html: set of (r, c) trusted-HTML cells
r.bar_chart(labels, values, title=None, horizontal=True)
r.line_chart(labels, series, title=None)                 # series: [(name, values)] ordered
r.donut(labels, values, title=None)
r.heatmap(row_labels, col_labels, matrix, title=None, value_format='{:,}')
r.image(path_or_bytes, caption=None, max_width=None)
r.gallery([(path_or_bytes, caption), ...], columns=4)
r.status(text, tone)                                      # -> HTML for a status chip (the ONLY chip)
r.text(paragraph); r.note(text); r.html(trusted_html)
r.to_string(); r.save(path)                               # -> path
htmlreport.escape(text)
```
Design: pyNavis design system translated to the web: system font stack starting with
"Segoe UI Variable", 13px body, solid surfaces, hairline borders, light and dark via
`prefers-color-scheme` CSS custom properties, accent only for focus/links, charts use 6
categorical chart colours, numbers right-aligned tabular, no gradients/shadows/emoji.
Tables: click a header to sort (numeric aware), a filter box per table, sticky header,
print stylesheet. Escape every text input. Tests: structure, escaping, sorting script
present, image embedding, deterministic output.

### pdf.py: minimal PDF writer

```python
doc = pdf.Document(size='A4', landscape=True, margin_mm=12, title=None, author=None)
page = doc.page()
page.text(x_mm, y_mm, text, size=11, bold=False, color=(0, 0, 0), align='left')  # y from TOP
page.wrap(x_mm, y_mm, w_mm, text, size=10, leading=1.3) -> y_after_mm
page.image(path_or_bytes, x_mm, y_mm, w_mm, h_mm=None)   # JPEG passthrough (DCTDecode); PNG decoded via png.py -> Flate RGB
page.line(x1, y1, x2, y2, width_mm=0.2, color=(0, 0, 0)); page.rect(x, y, w, h, stroke=..., fill=...)
doc.save(path)
pdf.SIZES  # A4, A3, Letter, Tabloid in mm
```
Helvetica / Helvetica-Bold, WinAnsi; characters outside cp1252 become '?'. Correct xref
offsets. Text width estimate from Helvetica AFM widths (embed the width table) so `align`
and `wrap` work. Tests: Pillow cannot read PDF, so parse your own output (xref table,
object count, page count) and, if `pypdf`/`fitz` happen to be importable, use them.

### png.py: tiny PNG codec

```python
png.encode(width, height, pixels, mode='RGB')   # -> bytes; pixels: flat bytes/bytearray/list rows; modes 'L','RGB','RGBA','1'
png.write(path, width, height, pixels, mode='RGB')
png.decode(data)  # -> (width, height, mode, bytes) for 8-bit non-interlaced L/LA/RGB/RGBA/palette
png.size(data)    # -> (w, h) from IHDR; also jpeg_size(data) for JPEG SOF markers
```
Pure `zlib` + `struct`. Tests against Pillow both ways.

---------------------------------------------------------------------------------------

## F2 Data core (pure except docdb; CPython + IronPython)

### paths.py
```python
paths.data_root()              # %APPDATA%\pyNavis\playground (created on demand)
paths.team_root()              # config shared_root when set and reachable, else data_root()
paths.doc_key(doc_path, shared=False)  # '<stem40>-<sha1[:8]>' of the lowercased full path; shared=True
                               #   keys by lowercased BASENAME only (users map drives differently);
                               #   '' or None -> 'untitled'
paths.ensure_dir(path) -> path
paths.safe_filename(text, max_len=80, replacement='_') -> str  (Windows-safe, no trailing dots/spaces,
                               #   reserved names CON/PRN/... prefixed)
paths.unique_path(path) -> path with ' (2)' etc when taken
paths.atomic_write_text(path, text) / atomic_write_bytes(path, data)  # temp + os.replace
```

### config.py: Playground-wide settings (one file via `pynavis.settings`, tool 'playground')
```python
config.DEFAULTS = {
  'user': '<USERNAME>', 'project_name': '', 'project_number': '', 'company': '',
  'data_mode': 'local',          # 'local' | 'shared' | 'model' (inside the NWF/NWD via docdb)
  'shared_root': '',             # network folder for team data
  'trades': ['Architecture', 'Structure', 'Mechanical', 'Electrical', 'Plumbing',
             'Fire Protection', 'Civil', 'Unassigned'],
  'trade_rules': [],             # [[regex, trade], ...] checked before trades.DEFAULT_RULES
  'report_units': 'auto',        # 'auto' (document units) | 'mm' | 'm' | 'ft' | 'in'
  'date_format': '%Y-%m-%d',
}
config.load() -> dict ; config.save(values) ; config.get(key) ; config.user_name()
```
Must import cleanly outside Navisworks (`pynavis.settings` is stdlib-only).

### session.py
```python
session.holder(key)    # module object under sys.modules['playground_' + key], created once per
                       #   engine life; survives pyNavis' per-run lib cache drop
session.get(key, attr, default=None) ; session.set(key, attr, value)
```

### store.py: per-document and global JSON stores
```python
s = store.Store(name, doc_path=None, scope='doc', mode=None)
    # scope 'doc' (per document) | 'global' (one per user, or per team in shared mode)
    # mode None -> config data_mode; 'local' | 'shared' | 'model' ('model' only for scope 'doc';
    #   falls back to 'local' with a logged warning when docdb is unavailable)
s.load(default=None) -> value ; s.save(value) ; s.update(fn, default=None) -> new value
s.path  (file backends) ; s.mode
r = store.RecordStore(name, doc_path=None, scope='doc', mode=None)
    # one JSON file per record (<root>/<name>/<id>.json) so team members editing different
    #   records never clobber each other; 'model' mode -> docdb records table
r.list() -> [record] (sorted by id) ; r.get(id) ; r.put(record) (needs record['id']) ;
r.delete(id) ; r.next_number(prefix='') -> int (max existing numeric suffix + 1)
store.for_active_doc(name, **kw) -> Store using pynavis.doc.get_filename() (lazy import)
```
Layout: `<root>\docs\<doc_key>\<name>.json` and `<root>\global\<name>.json`. Atomic writes;
a corrupt file is renamed `<file>.corrupt-<timestamp>` and `load` returns the default (and
logs). Never raises on read problems; raises IOError on write problems (callers toast).

### docdb.py: data stored INSIDE the document (Navisworks `Document.Database`, SQLite)
API half only (needs Navisworks). Dump members: `Document::Database : DocumentDatabase`,
`DocumentDatabase::Value : NavisworksConnection`,
`DocumentDatabase::BeginTransaction(DatabaseChangedAction) -> NavisworksTransaction`,
`NavisworksTransaction::Connection`, `Commit()`, `Rollback()`,
`NavisworksConnection::CreateCommand() -> NavisworksCommand`,
`NavisworksCommand::CommandText`, `Parameters`, `ExecuteNonQuery/ExecuteScalar/ExecuteReader`,
`NavisworksParameter(name, value)`, `DatabaseChangedAction.Edited|Reset`.
```python
docdb.available(doc=None) -> bool
docdb.kv_get(key, default=None, doc=None) ; docdb.kv_set(key, value, doc=None)   # JSON values
docdb.kv_delete(key, doc=None) ; docdb.kv_keys(prefix='', doc=None)
docdb.records(collection, doc=None) -> [dict] ; docdb.record_put(collection, id, value, doc=None)
docdb.record_delete(collection, id, doc=None)
```
Tables `playground_kv(key TEXT PRIMARY KEY, value TEXT, updated TEXT)` and
`playground_records(collection TEXT, id TEXT, value TEXT, updated TEXT, PRIMARY KEY(collection, id))`,
created on first write (`CREATE TABLE IF NOT EXISTS`). Writes in a transaction
(`Edited`), parameterised SQL only. The data saves with the NWF/NWD (the document becomes
modified). Keep SQL text in pure helpers so it is unit-testable; note in-app checks.

### naming.py: name templates
```python
naming.render(template, values, counter=None) -> (text, missing_tokens)
    # '{test} - {n:000}' ; '{date:%Y%m%d}' ; '{value}' ; unknown token -> left as '{token}'
    #   and reported in missing_tokens ; '{{' and '}}' escape braces ; counter fills {n}
naming.tokens(template) -> [names]
naming.standard_values(doc=None) -> dict: date, time, datetime, user, project, project_number,
    company, file (doc file stem), title, year, month, day (lazy API import; works without doc)
naming.unique(name, existing, pattern='{name} ({n})') -> name
naming.sanitize(text, for_file=False)
```

### rules.py: one condition engine for every rule-driven tool
```python
cond = {'category': 'Element', 'property': 'Category', 'op': 'equals', 'value': 'Ducts',
        'ignore_case': True}
rules.OPS  # ordered [(op, label, needs_value)]: equals, not_equals, contains, not_contains,
           #   starts_with, ends_with, wildcard, regex, gt, ge, lt, le, between ([lo, hi]),
           #   in_list ([...]), exists, missing, empty, not_empty
rules.evaluate(cond, exists, value) -> bool         # value already read (str/number/bool/None)
rules.matches(conds, getter, mode='all') -> bool    # getter(category, property) -> (exists, value)
rules.to_number(value) -> float or None             # '12.5', '1,234', '12.5 m', '3.2 ft' (number part)
rules.describe(cond) -> 'Element > Category = Ducts'
rules.validate(cond) -> [problem strings]
rules.native_query(conds) -> pynavis sets.query() Builder or None when any op needs Python
    # (lazy-imports pynavis.sets; pure part: rules.native_ops())
rules.parse_cell(text) -> cond   # 'Element > Category = Ducts', 'Item > Name contains PIPE',
                                  #   'Level >= 3' ... for Excel/text driven rules
```

### trades.py
```python
trades.DEFAULT_RULES  # ordered [(regex, trade)] covering common file naming: ARCH/AR/A-, STR/ST/S-,
                      #   MECH/HVAC/M-, ELEC/E-, PLUMB/P-, FP/SPRINK, CIVIL/C-, plus discipline words
trades.trade_of(name, rules=None) -> trade or 'Unassigned'   # name = model/source file name
trades.rules_from_config(cfg) -> config trade_rules then DEFAULT_RULES
```

### textmatch.py: fuzzy search for Quick Find and Command Palette
```python
textmatch.score(query, text) -> float      # 0.0 = no match; subsequence match with bonuses for
                                           #   word starts, CamelCase humps, prefix, contiguity;
                                           #   case-insensitive; multi-word queries AND each word
textmatch.rank(query, items, key=None, limit=50) -> [(score, item)] best first, stable ties
textmatch.spans(query, text) -> [(start, end)] matched ranges for highlighting
```
Must be fast in IronPython: 20,000 items x short query well under 200 ms (pre-lowercase).

### ifcguid.py
```python
ifcguid.compress(uuid_text) -> 22-char IFC GlobalId ; ifcguid.expand(ifc) -> uuid text
ifcguid.from_revit_unique_id(unique_id) -> IFC GlobalId (Revit's export rule: the episode GUID
    (first 36 chars) with its last 8 hex digits XOR the element id (last 8 hex))
ifcguid.new() -> random GlobalId ; ifcguid.is_valid(text)
```
Test vectors: compress/expand round trip; known Revit pair if you know one.

### templates.py: named saved configurations per tool (Report Templates reads them all)
```python
t = templates.Templates(tool_id)   # file: team_root()\templates\<tool_id>.json
t.names() -> sorted ; t.get(name) -> config or None ; t.save(name, config) ; t.delete(name)
t.rename(old, new) ; t.export(path, names=None) ; t.import_file(path, replace=False) -> count
templates.all_tools() -> [tool_id] that have templates
```

### reports.py: registry for automation-ready reports (the list is fixed; implement helpers)
```python
reports.REGISTRY  # [(id, title, module)] -- see the table below, keep it exactly
reports.module_for(report_id) -> imported namo.rep_<id> module (ImportError if not built yet)
reports.available() -> [(id, title)] whose module exists
reports.run(report_id, config, doc=None, interactive=False, progress=None) -> result dict
reports.output_path(config, default_name, ext) -> path from config['folder'] (default: data_root()\reports)
    + config['name_template'] (naming tokens + {report}) ; folders created
```
Contract every `namo/rep_<id>.py` implements (write this into README):
```python
TITLE = 'Clash Excel Report'
def default_config(): ...            # JSON-serialisable dict; includes 'folder' and 'name_template'
def describe(config): ...            # one line for lists
def run(config, doc=None, interactive=True, progress=None): ...
    # interactive False -> NO dialogs/prompts (pynavis run, schedules, macros)
    # progress(fraction, label) optional, may be None
    # returns {'level': 'success'|'info'|'warning'|'error', 'message': str, 'detail': str,
    #          'paths': [files written]}
```
REGISTRY (id, title, module):
property_export Property Export rep_property_export | model_tree Model Tree Export rep_model_tree |
count_by_property Count by Property rep_count_by_property | data_validation Data Validation rep_data_validation |
clash_excel Clash Excel Report rep_clash_excel | clash_html Clash HTML Dashboard rep_clash_html |
clash_matrix Clash Count Matrix rep_clash_matrix | clash_delta Clash Delta rep_clash_delta |
clash_trends Clash Trends rep_clash_trends | per_trade Per-Trade Reports rep_per_trade |
coordination Coordination Report rep_coordination | kpi_export KPI Export rep_kpi_export |
health_check Model Health Check rep_health_check | session_stats Session Stats rep_session_stats |
stale_files Stale File Alert rep_stale_files | preflight Preflight Checks rep_preflight |
timeliner_export TimeLiner Export rep_timeliner_export | schedule_health Schedule Health rep_schedule_health |
quick_takeoff Quick Takeoff rep_quick_takeoff | zone_takeoff Zone Takeoff rep_zone_takeoff |
viewpoint_images Viewpoints to Images rep_viewpoint_images | batch_pdf Batch PDF Printer rep_batch_pdf

### dates.py
```python
dates.parse(value) -> datetime.datetime or None   # ISO strings, 'dd/mm/yyyy' when unambiguous by
                                                   #   config? (prefer ISO, then y-m-d, d/m/y), Excel
                                                   #   serials (float), .NET DateTime (has .Year)
dates.iso(dt) ; dates.today() ; dates.add_days(dt, n) ; dates.days_between(a, b)
dates.age_bucket(days, buckets=(7, 14, 30)) -> '0-7 days' | '8-14 days' | '15-30 days' | 'Over 30 days'
dates.format(dt, fmt=None)  # config date_format
dates.from_net(net_datetime) ; dates.to_net(dt)    # lazy System import
```

### units.py
```python
units.DOC_UNIT_METERS  # {'Meters':1.0, 'Centimeters':0.01, 'Millimeters':0.001, 'Feet':0.3048,
                       #   'Inches':0.0254, 'Yards':0.9144, 'Kilometers':1000, 'Micrometers':1e-6,
                       #   'Microinches':2.54e-8, 'Mils':2.54e-5, 'Miles':1609.344}
units.to_meters(value, doc_units) ; units.from_meters(value_m, doc_units)
units.convert(value, from_unit, to_unit)   # length, area (m2, ft2, sqft...), volume (m3, ft3, cuyd, l),
                                           #   mass (kg, t, lb); ValueError across kinds
units.parse_quantity(text) -> (value, unit, kind) or None
    # '12.5 m', '1 250 mm', '3.5 m³', '12.5 m2', '250 sqft', "12' - 6 1/2\"" (via ft-in rules),
    #   Revit DisplayStrings, comma decimal when unambiguous
units.format(value, unit, decimals=2) ; units.KINDS ; units.ALIASES
units.parse_conversion(text) -> (value, from_unit, to_unit)   # "12' 6\" to mm", "250 sqft in m2"
```

---------------------------------------------------------------------------------------

## F3 Navisworks core (API halves + pure helpers; read pynavis sources first)

Study first: `pynavislib/pynavis/{_api,_com,_util,props,sets,selection,view,viewpoints,
viewstate,section,geometry,memory,clash,_clashsnap,_clashapply,export,overlay,pick,forms}.py`
and the shipped lib modules (`vptrackerlive.py`, `tabhider.py`, `coords.py`, `facemove.py`).
Reuse pynavis wherever it already solves a problem.

### items.py
```python
items.Cancelled  # raised when a tick callback returns False
items.selected(doc=None) -> [ModelItem]
items.roots(doc=None) -> [ModelItem] model root items
items.walk(roots, max_depth=None) -> generator of (item, depth), depth-first, children in order
items.geometry_items(roots, tick=None, budget=None) -> [ModelItem] with HasGeometry
    # tick(done, total_or_None) every ~500 items; returning False raises Cancelled;
    #   budget caps the count (caller says "sampled")
items.objects(roots_or_items, tick=None, budget=None) -> [ModelItem]  # element level:
    #   FindFirstObjectAncestor() of geometry items, deduped in order (falls back to the item)
items.visible(item) -> bool   # not hidden itself nor any ancestor
items.key(item, doc=None) -> str   # '<source file lower>|<PathId>' stable across sessions
items.entries(items, doc=None) / items.resolve(entries, doc=None) -> (found, missing_count)
    # wraps pynavis.memory.encode_items / resolve_entries
items.model_of(item) -> Model or None ; items.model_name(item) -> source file name (basename)
items.models(doc=None) -> [{'index','model','name','file','source','units','root'}]
items.tree_path(item, sep=' > ') -> 'file.nwc > Level 1 > Walls > Basic Wall'
items.bbox(items_or_item) -> ((x0,y0,z0),(x1,y1,z1)) or None (union, ignores empty)
items.center(item) ; items.size(item)
items.revit_ids(item) -> {'element_id','unique_id','ifc_guid','category','family','type'} values
    or None per key; checks the object ancestor too; documented property names it tries
items.category(item) -> str  (Revit/IFC category when present, else ClassDisplayName)
items.prop(item, category, prop, fallback_to_object=True) -> value or None
items.sample_properties(items, limit=200) -> [(category, property, count)] sorted
items.distinct_values(items, category, prop, tick=None) -> [(value_text, count)] by count desc
items.collection(items) -> ModelItemCollection ; items.select(items, zoom=False) ; items.zoom(items)
items.isolate(items) / items.hide(items, hidden=True) ; items.unhide_all()
```

### clashdata.py: one reader for every clash tool
```python
clashdata.STATUSES = ['New', 'Active', 'Reviewed', 'Approved', 'Resolved']
clashdata.tests(doc=None) -> [ClashTest] ; clashdata.test_by_name(name, doc=None)
clashdata.snapshot(test, doc=None, progress=None) -> [row]
    # row = pynavis clash.snapshot_results keys (id, name, center, item_a, item_b, item_a_name,
    #   item_b_name, level, grid, model_a, model_b, status, assigned, group) PLUS: 'test',
    #   'test_guid', 'guid' (result Guid text), 'distance' (model units), 'distance_m',
    #   'created' (ISO or None), 'approved_by', 'approved_time', 'description', 'priority',
    #   'comments' (count), 'trade_a', 'trade_b' (namo.trades of model names), 'group_guid',
    #   'key' (pair_key). Enrich by walking clash.walk_results(test) in the SAME order as the
    #   snapshot ids (verify that order claim in pynavis source).
clashdata.snapshot_all(tests, doc=None, progress=None) -> {test_name: [row]}
clashdata.pair_key(row) -> stable text for matching a clash across runs (sorted element keys +
    centre rounded to 0.1 m)
clashdata.results(test) -> [ClashResult] leaves in walk order ; clashdata.groups(test) ->
    [{'name','guid','result','count','statuses'}] top-level groups
clashdata.compare(old_rows, new_rows) -> {'new': [...], 'fixed': [...], 'persisting': [...],
    'status_changed': [(old, new)]}   # PURE, by pair_key; resolved/approved count as fixed
clashdata.save_history(doc_path, rows_by_test, label=None) / list_history(doc_path) ->
    [{'id','label','time','counts'}] / load_history(doc_path, history_id) -> rows_by_test
    # compact rows (key, test, status, distance_m, created, trade_a, trade_b, name, grid, level)
    #   in a namo.store 'clash-history' global-per-doc store
clashdata.image(result, path, width=640, height=360, doc=None) -> path   # TestsImageForResult
clashdata.viewpoint(result, doc=None) -> Viewpoint                    # TestsViewpointForResult
clashdata.set_assigned(results, name, doc=None) ; set_description ; set_priority ;
clashdata.add_comment(result, text, doc=None)     # TestsEditResultComments with the existing
                                                  #   comments plus one new Comment
clashdata.resolve_guid(test, guid_text) -> ClashResult or None
```

### camera.py
Pure: `quat_to_axes(a, b, c, d) -> (direction, up, right)` with Navisworks conventions
(the camera looks along local -Z with +Y up; VERIFY against how pynavis/viewstate or the
API docs treat Rotation3D (A,B,C,D components) and write the convention down),
`axes_to_quat(direction, up)`, `bearing_pitch(direction) -> (deg_from_north_clockwise,
deg_pitch)`, `fov_degrees(height_field, projection)`, `to_bcf(cam, unit_to_m)` /
`from_bcf(bcf_cam, m_to_unit)` (BCF: CameraViewPoint, CameraDirection, CameraUpVector,
FieldOfView degrees vertical, ViewToWorldScale for ortho), `look_at_axes(eye, target, up)`.
API: 
```python
camera.capture(doc=None) -> cam dict {'position','rotation'(a,b,c,d),'direction','up',
    'projection':'persp'|'ortho','height_field','focal_distance','aspect','json'}  # json = Viewpoint.GetCamera()
camera.apply(cam, doc=None)            # CurrentViewpoint.CopyFrom a copy with the camera set
camera.to_viewpoint(cam, base=None) -> Viewpoint
camera.look_at(eye, target, up=(0, 0, 1), fov_deg=None, doc=None)
camera.zoom_to(items_or_bbox, doc=None)          # Viewpoint.ZoomBox on a copy, then CopyFrom
camera.folder(path, doc=None) -> FolderItem      # 'A/B/C' in saved viewpoints, created as needed
camera.save_view(name, folder=None, cam=None, comments=None, doc=None) -> SavedViewpoint
    # tree-resident (re-resolved after AddCopy), name deduped within the folder
camera.saved_views(doc=None) -> [(folder_path, SavedViewpoint)]  (wraps doc.walk_saved_viewpoints)
camera.clip_json(doc=None) / camera.set_clip_json(text, doc=None)  # View.GetClippingPlanes/Set...
camera.horizontal_section(z_top, z_bottom=None, doc=None)   # top plane cutting at z_top (and a
    # bottom plane), one undo step; reuse pynavis.section/viewstate's proven plane code
camera.clear_section(doc=None)
```

### images.py
```python
images.capture(path, width=1920, height=1080, doc=None, style='scene', sectioning=True,
               quality=90) -> path      # Document.GenerateImage -> Bitmap.Save (.png/.jpg/.bmp)
images.capture_saved(saved_viewpoint, path, **kw) -> path   # makes it current, then capture
images.clash(result, path, width=640, height=360, doc=None) -> path  # TestsImageForResult
images.thumbnail(src, dst, max_width=320, quality=85) -> dst  # System.Drawing resize
images.ViewKeeper(doc=None)   # context manager: remembers the current viewpoint copy and current
                              #   saved viewpoint, restores both on exit (batch exports)
images.STYLES  # {'scene': ImageGenerationStyle.Scene, 'overlay': ScenePlusOverlay}
```
Dispose every Bitmap. JPEG quality via EncoderParameters.

### colors.py (pure) and paint.py (API)
```python
colors.PALETTE  # 12 categorical hex colours, distinguishable, readable in both themes
colors.for_values(values, palette=None) -> [(value, hex)] in the given order (stable)
colors.sequential(t) -> hex   # 0..1 light-to-strong ramp ; colors.bands(n) ; colors.diverging(t)
colors.hex_to_rgb(h) -> (r,g,b) 0..255 ; colors.rgb_to_hex ; colors.rgb01(h) -> 0..1 floats
colors.contrast_text(hex) -> '000000' | 'FFFFFF'
colors.STATUS  # clash statuses and construction statuses -> hex

paint.nw_color(hex) -> Api.Color
paint.apply(groups, doc=None, name='Color items') -> count   # groups: [(items, hex_or_None,
    # transparency_or_None)] ; ONE transaction ; skips empty groups
paint.ghost(keep_items, transparency=0.85, hex=None, doc=None) -> ghosted count
    # everything visible except keep_items: compute by model roots minus keep (cheap: apply to
    #   roots, then reset materials on keep items) -- measure the cheapest correct way and doc it
paint.reset(items=None, doc=None)        # permanent materials (all when None)
paint.remember_scheme(scheme) ; paint.last_scheme() -> scheme or None
    # scheme = {'title','property':{'category','property'},'entries':[{'value','hex','count'}],
    #           'ghost': transparency or None, 'time'}; global store 'last-color-scheme'
paint.read_color(item) -> (hex, transparency) best effort from item.FindFirstGeometry()
    # ActiveColor/ActiveTransparency (unverified in-app: say so)
```

### mesh.py (pure) + triangle source
```python
mesh.area(tris) ; mesh.volume(tris) (signed tetrahedra; abs) ; mesh.centroid(tris) -> solid
    centroid when volume is meaningful else area centroid ; mesh.bbox(tris) ;
mesh.is_closed(tris, tol=1e-6) -> bool (every edge shared by exactly two triangles, by rounded keys)
mesh.weld(tris, tol=1e-6) -> (vertices, faces) ; mesh.translate(tris, v) ; mesh.count(tris)
mesh.item_triangles(item, budget=200000) -> {'tris': [...], 'note': str or None, 'noise': float}
    # wraps pynavis.geometry.world_triangles (IronPython only; returns note when empty)
```
Tests: unit cube volume 1, area 6, centroid; open box not closed; weld counts.

### ui.py: WPF building blocks (themed by DesignSystem tokens, built in Python)
Study `DesignSystem.cs`, `Pickers.cs`, `Dialogs.cs`, `SettingsDialog.cs` (C# patterns),
`forms.py` and the shipped Console/Tracker window code. Every window: owned by the host
(`FluentChrome.Apply(window)` before showing), themed from
`DesignSystem.Tokens.Current`, Segoe UI Variable, 32px controls, keyboard friendly (Tab
order, Enter = primary, Esc = cancel), resizes sensibly, no hard-coded colours outside
tokens.
```python
ui.tokens() -> DesignSystem tokens (light/dark)
ui.form(title, fields, intro=None, ok='OK', cancel='Cancel', width=460) -> dict or None
  # fields: list of dicts {'kind', 'key', 'label', 'default', ...}:
  #   'text' | 'textarea' (rows) | 'int' | 'number' (min, max) | 'length' (units: doc units,
  #   parsed via pynavis.lengths, returns doc units) | 'choice' (options: [str or (label, value)])
  #   | 'radio' (options) | 'check' | 'multi' (options, checked values; searchable when > 8)
  #   | 'file_open' (filter) | 'file_save' (filter, default_name) | 'folder' | 'color' (hex)
  #   | 'date' | 'label' (text) | 'separator'
  #   common: 'hint' (muted line), 'required', 'enabled_if': (other_key, value)
  # validates inline (red hint under the field), never closes on invalid input;
  # Esc/Cancel -> None. Returns {key: value} for every non-label field.
ui.choose(title, rows, columns, multiselect=True, checked=None, prompt=None, search=True,
          ok='OK') -> [row values] or None
  # rows: [{'value': v, 'cells': [..]}] multi-column, sortable headers, filter box, select-all
ui.table_window(title, headers, rows, actions=None, on_open=None, modeless=False, key=None,
                status=None) -> window
  # rows: [{'cells': [...], 'value': v}] ; actions: [(label, fn(selected_values))] buttons ;
  #   on_open(value) on double-click/Enter ; modeless=True -> single instance per key,
  #   keyboard interop, survives the run (session holder), refreshable via window.Tag/
  #   returned handle .update(rows, status)
ui.Modeless(key, title, content_builder) -> helper: create-or-activate a modeless window,
  # ElementHost.EnableModelessKeyboardInterop BEFORE Show, owner = host, closes cleanly,
  #   stores itself in session holder under key
ui.non_activating(window)   # WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW, ShowActivated False
ui.host_rect() -> (left, top, right, bottom) of the Navisworks main window in screen px
ui.run_later(fn, delay_ms=0) -> cancel callable   # UI-thread deferral (DispatcherTimer one-shot)
ui.Debouncer(delay_ms, fn) -> .trigger(), .cancel()
ui.copy(text) ; ui.open_path(path) (os.startfile) ; ui.show_in_explorer(path)
```
Smoke tests construct each window type (form with every field kind, choose, table window)
with sample data under the IronPython harness WITHOUT showing modally; expose a
`build_*` function for each that returns the Window so smoke tests and callers share it.

---------------------------------------------------------------------------------------

## README (each foundation agent writes its own file)

Tool agents read these to use your modules. Write `lib/namo/README-F1.md` (or F2, F3:
your own file only; three agents run at once). For each module: one paragraph on
purpose, then every public function with signature, return value and one-line
behaviour, then traps and in-app-unverified assumptions. Keep it accurate to the code.
The lead merges the three into `lib/namo/README.md` afterwards.
