# namo data core (F2): paths, config, session, store, docdb, naming, rules, trades, textmatch, ifcguid, templates, reports, dates, units

Everything here is pure stdlib and runs on IronPython 3.4 and CPython 3.11, except the
Navisworks half of `docdb` (lazy `pynavis._api` import) and `dates.to_net` (lazy `System`).
Every module imports cleanly outside Navisworks. Tests: `dev/tests/test_<module>.py`.

Shared conventions:

* **Reads never raise, writes raise `IOError`.** Missing file: the default. Damaged JSON:
  renamed `<file>.corrupt-<YYYYmmdd-HHMMSS>`, logged, the default. A failed write leaves
  the old file untouched and raises `IOError` naming the file; toast it.
* **All writes are atomic** (temp file beside the target, then `os.replace`, with short
  retries for antivirus locks). JSON files are `indent=2`, sorted keys, UTF-8, final newline.
* **Logging:** `session.log(level, message)` writes to the pyNavis log (never opens the output
  window). `session.recent_log()` returns the last 200 lines (tests assert on it).
* **Tests must never touch the real `%APPDATA%`:** call `paths.redirect(folder)` (redirects
  `data_root()` AND the settings file) and restore with `paths.redirect(previous)` in a
  `finally`. Use `docdb.use_backend(docdb.SqliteBackend())` to exercise model mode offline.
* **Never rely on dict order.** Every function that returns a list sorts it (natural order
  for names and ids: 'RFI-9' before 'RFI-10'; see `naming.natural_key`).

---------------------------------------------------------------------------------------

## paths

Where Playground keeps files and how it writes them. `data_root()` is `%APPDATA%\pyNavis\playground`;
`team_root()` is the configured shared folder when set and reachable, else `data_root()`.
Document keys follow `pynavis.memory`'s identity rule exactly (tested against it).

```python
paths.appdata() -> str                       # %APPDATA% (or the redirect folder)
paths.redirect(folder) -> previous_folder    # TEST SEAM: data_root() and config file under folder; None restores
paths.data_root() -> str                     # <appdata>\Playground, created on demand
paths.shared_root() -> str                   # config 'shared_root' stripped, '' when unset
paths.team_available() -> bool               # shared root set AND reachable now
paths.team_root() -> str                     # shared root when reachable, else data_root()
paths.is_reachable(folder) -> bool           # os.path.isdir, cached per session (60 s ok / 15 s not); logs nothing (team_root logs an unreachable share once)
paths.forget_reachability()                  # drop that cache (after the user edits shared_root)
paths.doc_key(doc_path, shared=False) -> str # '<stem, 40 chars>-<sha1[:8]>' of the LOWERCASED full path
                                             #   (shared=True: of the lowercased BASENAME only); ''/None -> 'untitled'
paths.safe_filename(text, max_len=80, replacement='_') -> str
    # Windows-safe: <>:"/\|?* and control chars replaced, runs collapsed, no trailing dots/spaces,
    # CON/PRN/AUX/NUL/COM1-9/LPT1-9 (also 'con.txt') prefixed, cut to max_len keeping a short
    # extension; '' or nothing left -> 'untitled'
paths.unique_path(path) -> str               # path, or 'name (2).ext', 'name (3).ext' ...
paths.ensure_dir(path) -> path               # makedirs when missing (race-safe)
paths.atomic_write_text(path, text, encoding='utf-8', retries=None) -> path   # exact text, no newline translation; retries=1 fails fast (no sleeping retries) for UI-thread callers
paths.atomic_write_bytes(path, data) -> path
paths.read_text(path, default=None) -> str   # UTF-8 (BOM tolerated) or default
paths.load_json(path, default=None, move_aside=True) -> value   # never raises (see conventions)
paths.write_json(path, value) -> path        # atomic; TypeError/ValueError if not serialisable
paths.dumps(value) -> str                    # the JSON text every Playground file uses
paths.quarantine(path) -> new_path or None   # rename to <file>.corrupt-<timestamp>, logged
paths.FileLock(path, timeout=3.0, stale=30.0)    # context manager on '<path>.lock' (O_EXCL)
    # .held says whether it was obtained. After timeout the block RUNS ANYWAY (logged): a
    # stuck lock must never stop a save. Locks older than `stale` seconds are broken.
```

Traps: `team_root()` ignores `data_mode` (templates are team-wide whenever a shared folder
is set); `store` decides per data mode. Probing an offline UNC share can block for seconds;
the cache keeps that to once per 15 s.

## config

Playground-wide settings in one file through `pynavis.settings` (tool key `'playground'`, i.e.
`%APPDATA%\pyNavis\settings\playground.json`). Per-tool options belong in the bundle's own
`script.get_config()`; this holds what several tools share.

```python
config.DEFAULTS = {'user': <Windows USERNAME>, 'project_name': '', 'project_number': '',
    'company': '', 'data_mode': 'local', 'shared_root': '',
    'trades': ['Architecture', 'Structure', 'Mechanical', 'Electrical', 'Plumbing',
               'Fire Protection', 'Civil', 'Unassigned'],
    'trade_rules': [], 'report_units': 'auto', 'date_format': '%Y-%m-%d'}
config.MODES = ('local', 'shared', 'model') ; config.REPORT_UNITS = ('auto', 'mm', 'm', 'ft', 'in')
config.DEFAULT_TRADES ; config.TOOL = 'playground'
config.load() -> dict          # DEFAULTS overlaid with the file, normalised; NEVER raises
config.save(values) -> dict    # writes the given keys (any subset; unknown keys ignored) over the
                               #   current values; returns the saved dict; raises IOError/OSError
config.get(key, default=None)  # one normalised value; default for a non-Playground key
config.user_name() -> str      # config 'user', else Windows user; never empty
config.defaults() -> dict      # deep copy of DEFAULTS
config.normalise(values) -> dict   # bad mode/units -> defaults, trades deduped, trade_rules keep
                                   #   only [regex, trade] pairs that compile, bad date_format -> ISO
config.path() -> str
```

Traps: values are re-read from disk on every call (no cache; module globals reset per run
anyway). Outside the pyNavis runtime an identical built-in reader/writer is used (same
file), so CPython tests work without pynavis on the path.

## session

State that outlives a run, and the shared logger. pyNavis drops every lib module from
`sys.modules` before each run, so module globals are fresh on every click.

```python
session.holder(key) -> module        # sys.modules['playground_' + key], created once per engine life
session.get(key, attr, default=None) # holder(key).attr
session.set(key, attr, value) -> value
session.clear(key) -> bool           # forget a holder
session.keys() -> [key]              # sorted
session.log(level, message)          # 'debug'|'info'|'warning'|'error'; pyNavis log; never raises
session.recent_log(level=None) -> [(level, text)]   # last 200 lines, oldest first
```

Store windows, timers, event handlers and caches on a holder; remember that a handler that
fires later is "outside a run" (use `script.bind()` captured during the run for config).

## store

Per-document and global JSON stores in one of three places (mode None = config `data_mode`):

| mode | doc scope | global scope |
|---|---|---|
| `'local'` | `<data_root>\docs\<doc_key>\<name>.json` | `<data_root>\global\<name>.json` |
| `'shared'` | `<team_root>\docs\<doc_key(shared=True)>\<name>.json` | `<team_root>\global\<name>.json` |
| `'model'` | docdb kv key `'store:<name>'` (inside the NWF/NWD) | never: global stays local |

```python
s = store.Store(name, doc_path=None, scope='doc', mode=None, doc=None)
    # ValueError for an empty name, a scope not 'doc'/'global', a mode not in MODES
s.load(default=None) -> value        # never raises
s.save(value)                        # IOError on failure
s.update(fn, default=None) -> new    # locked read-modify-write; new = fn(current or a COPY of
                                     #   default); fn returning None saves the mutated current value
s.exists() -> bool ; s.delete() -> bool
s.name, s.scope, s.doc_path, s.doc
s.mode    # the EFFECTIVE mode after fallbacks
s.path    # the JSON file (None in model mode) ; s.folder
s.note    # None, or a user-facing sentence when a fallback happened:
          #   'The shared folder is unreachable; using local data.' /
          #   'No shared folder is set in Playground settings; using local data.' /
          #   'Model data is unavailable here; using local data.'   (toast it if it matters)

r = store.RecordStore(name, doc_path=None, scope='doc', mode=None, doc=None)
    # one JSON file per record: <root>\docs\<doc_key>\<name>\<id>.json (or <root>\global\<name>\)
    # model mode: docdb records table, collection = name
r.list() -> [record]          # natural id order; damaged files moved aside and skipped; never raises
r.ids() -> [id]
r.get(id) -> record or None
r.put(record) -> record       # record['id'] required (ValueError); replaces that id; IOError on failure
r.delete(id) -> bool
r.next_number(prefix='') -> int   # 1 + largest trailing number among ids starting with prefix
                                  #   (case-insensitive); 1 when none: ['RFI-001','RFI-007'] -> 8
r.add(record, prefix='', width=3) -> record   # assigns prefix + zero-padded next number under a
                                              #   folder lock (no duplicate numbers across users)
r.folder, r.mode, r.note, r.name, r.scope

store.for_active_doc(name, **kw) -> Store           # doc + file name of the active document (Navisworks)
store.records_for_active_doc(name, **kw) -> RecordStore
store.id_to_filename(id) / store.filename_to_id(filename)   # reversible %XX escaping
store.next_number_of(ids, prefix='') ; store.sort_records(records)
```

Traps: **'shared' keys documents by file NAME**, so two different projects' `Model.nwf` on
the same share share data; that is the price of drive-letter independence. **Record ids are
case-insensitive on disk** ('RFI-1' and 'rfi-1' are one file); keep a consistent case. An
unsaved document is `'untitled'` (shared by all unsaved documents). `update()` on a shared
store holds `<file>.lock` for the duration of `fn`: keep `fn` quick and dialog-free.

## docdb

Playground data INSIDE the document: Navisworks' per-document SQLite (`Document.Database`),
saved with the NWF/NWD. Tables (created on the first write):
`playground_kv(key TEXT PRIMARY KEY, value TEXT, updated TEXT)` and
`playground_records(collection TEXT, id TEXT, value TEXT, updated TEXT, PRIMARY KEY(collection, id))`.
Values are JSON text; `updated` is local ISO time.

```python
docdb.available(doc=None) -> bool              # can the database be read here; never raises
docdb.kv_get(key, default=None, doc=None)      # never raises (default when missing/unreadable)
docdb.kv_set(key, value, doc=None)             # JSON value; IOError on failure; document becomes modified
docdb.kv_delete(key, doc=None) -> bool
docdb.kv_keys(prefix='', doc=None) -> [key]    # sorted, case-sensitive prefix
docdb.records(collection, doc=None) -> [dict]  # natural id order; a dict value gets 'id' (setdefault),
                                               #   other values come back as {'id', 'value'}
docdb.record_get(collection, id, doc=None) -> dict or None
docdb.record_put(collection, id, value, doc=None)    # IOError on failure
docdb.record_delete(collection, id, doc=None) -> bool
docdb.collections(doc=None) -> [name]
# pure helpers (unit tested): SQL_* constants, encode(value), decode(text, default),
#   params(**values) -> [('@name', value)], statement(sql, **values), create_statements(present),
#   filter_keys(keys, prefix), rows_to_records(rows), now_text()
docdb.SqliteBackend(path=':memory:')   # same SQL over Python sqlite3 (tests, offline tools)
docdb.use_backend(backend) -> previous # TEST SEAM; None = the active document
docdb.NavisworksBackend(doc)           # the API half
```

How the API half works (all members grepped in the 2026 dump; **unverified in-app**, see
`dev/notes/foundation-F2.md`): reads build `NavisworksCommand(sql, doc.Database.Value)`, bind
`@name` parameters with `Parameters.AddWithValue`, and fill a `DataTable` through
`NavisworksDataAdapter(command).Fill` (Autodesk's documented read route; it opens/closes the
connection itself), falling back to `ExecuteReader` on an explicitly opened connection.
Writes run in `doc.Database.BeginTransaction(DatabaseChangedAction.Edited)`, `Commit()`, with
`Rollback()` on any error; missing tables are created first in a separate
`DatabaseChangedAction.Reset` transaction. Parameterised SQL only (`@name`), `INSERT OR
REPLACE` upserts (works on old SQLite too; tested on 3.7.7 and 3.45).

Traps: writes are NOT undoable (no `EnableTableUndoable`); do not call docdb inside an open
`viewpoints.transaction()` (untested nesting); the user must SAVE the NWF/NWD for the data to
persist; data in an NWD travels to everyone who opens it.

## naming

Name templates for files, viewpoints, sets, tests: `'{test} - {n:000}'`, `'{date:%Y%m%d}'`.

```python
naming.render(template, values, counter=None) -> (text, missing_tokens)
    # {name} or {name:spec}; names are letters/digits/_/. (matched case-insensitively when
    # there is no exact key). spec: all zeros pads a number ('{n:000}' -> 007); a strftime
    # pattern for dates/times (text that reads as a date is parsed); any Python format spec
    # (',', '.2f', '.0%', '>8'). Unknown tokens stay as written and are listed (order, no dups).
    # '{{' and '}}' are braces; a lone brace is text. counter fills {n} unless values has 'n'.
    # Defaults without spec: date 2026-10-05, time 1430, datetime '2026-10-05 1430', True 'Yes',
    # 2.0 '2', None ''.
naming.tokens(template) -> [names]               # first-appearance order, no duplicates
naming.standard_values(doc=None) -> dict         # date, time, datetime (objects), year, month, day
    # (zero-padded text), user, project, project_number, company (config), file (document
    # file stem), title. Without Navisworks/document: file and title are ''.
naming.unique(name, existing, pattern='{name} ({n})') -> name   # case-insensitive; n from 2
naming.sanitize(text, for_file=False) -> str     # control chars/newlines -> space, long dashes
    # -> '-', spaces collapsed, trimmed; for_file=True then paths.safe_filename
naming.natural_key(text) -> tuple                # sort key: 'Level 2' < 'Level 10', case-insensitive
naming.format_value(value, spec=None) -> str     # one token's formatting
```

## rules

One condition engine for every rule-driven tool. A condition is
`{'category', 'property', 'op', 'value', 'ignore_case'}` (`'prop'` accepted for `'property'`).

```python
rules.OPS   # ordered [(op, label, needs_value)]: equals, not_equals, contains, not_contains,
            #   starts_with, ends_with, wildcard, regex, gt, ge, lt, le, between ([lo, hi]),
            #   in_list ([...]), exists, missing, empty, not_empty   (labels are lowercase UI text)
rules.OP_NAMES ; rules.LABELS ; rules.NEEDS_VALUE ; rules.SYMBOLS ; rules.OP_ALIASES
rules.evaluate(cond, exists, value) -> bool
rules.matches(conds, getter, mode='all') -> bool   # getter(category, property) -> (exists, value),
    # called once per distinct pair; a raising getter = missing property; 'all' (True when empty)
    # or 'any' (False when empty)
rules.to_number(value) -> float or None   # number at the START: '12.5 m' 12.5, '1,234' 1234,
                                          #   '3.2 ft' 3.2; bool/None -> None
rules.text_of(value) -> str               # None '', True 'Yes', 3.0 '3', 2.5 '2.5', text trimmed
rules.describe(cond) -> 'Element > Category = Ducts'     # parse_cell() reads it back
rules.validate(cond) -> [sentence]                       # [] when fine
rules.parse_cell(text) -> cond            # ValueError (readable) when no comparison is found
rules.normalise(cond) -> cond ; rules.op_of(spelling) -> op or None
rules.as_list(value) ; rules.bounds(value) -> (lo, hi) ; rules.wildcard_regex(pattern, ignore_case)
rules.native_ops() -> [op]
rules.native_plan(conds, mode='all', numbers_as_text=False, max_groups=4) -> groups or None  # pure
rules.native_query(conds, mode='all', numbers_as_text=False, max_groups=4) -> sets Builder or None
```

Semantics (identical everywhere): `ignore_case` defaults True; text compares trimmed values.
**Every value operator is False when the property does not exist** (like Find Items); use
`missing`. `empty` = missing OR blank; `not_empty` = present and not blank. `equals`,
`not_equals`, `in_list` compare as numbers when BOTH sides read entirely as numbers ('3' equals
3.0 and '3.000'), else as text; booleans match yes/no/true/false/1/0. `gt/ge/lt/le/between`
use `to_number` on both sides (a side without a number makes it False). `wildcard`: `*` and
`?`, whole value. `regex`: `re.search`; a bad pattern is False (validate reports it).
`category ''` means "any category" for getters that support it.

`parse_cell` forms: `Element > Category = Ducts`, `Item > Name contains PIPE`, `Level >= 3`
(category ''), `Element > Mark is empty`, `... exists`, `... is missing`, `... is not empty`,
`... like P-*`, `... matches ^P\d+` (or `/.../`), `... between 1 and 3`, `... is one of A, B`
(`;` separates when values contain commas), `... starts with`, `... ends with`,
`... does not contain`, `!=`/`<>`, `(match case)` at the end. Quote names or values that
contain operator words: `Element > "Phase is" = "a = b"`.

native_query: returns a `pynavis.sets.query()` Builder (run with `sets.run(builder)` /
`sets.find_first`) or None when Python must decide: regex, not_contains, empty, not_empty, a
blank category, no conditions, starts/ends_with values containing `* ? [ ] #`, or more than
`max_groups` OR groups (each is a full model walk; `in_list` expands to one group per value).
**Trap:** equals/not_equals/in_list with number-like values return None unless
`numbers_as_text=True`, because native matching compares display strings: right for text
properties such as `Element ID > Value`, wrong for Int32/Double properties that `evaluate`
would match. Native matching is by display names. Unverified in-app: that DisplayString
wildcard/contains/NotEqual behave exactly like `evaluate` (see notes).

## trades

Trade from a model / source file name.

```python
trades.DEFAULT_RULES        # ordered [(regex, trade)], case-insensitive, searched in the BASENAME
trades.UNASSIGNED = 'Unassigned'
trades.trade_of(name, rules=None) -> trade or 'Unassigned'   # first matching rule wins; memoised
trades.explain(name, rules=None) -> (trade, pattern or None)
trades.rules_from_config(cfg=None) -> [(regex, trade)]       # config trade_rules first, then defaults
trades.classify(names, rules=None) -> {name: trade}
trades.basename_of(name) -> lowercased file name
```

Order of DEFAULT_RULES: discipline words (fire protection/sprinkler, plumb/sanitary/drainage,
mech/hvac/duct, elec/lighting/power/cable tray, struct/steel/rebar/foundation,
arch/interior/facade, civil/landscape/topo/site), then standalone codes (FP FPS SPK, PL PLG,
ME MEC MCH HV MV, EL ELV LT LV, STR STRU ST, AR ARC ARCHI, CIV), then a single-letter prefix
at the very START (`A-`, `S_`, `M `, `E.`, `P-`, `F-`, `C-`). Combined `MEP` models and
mid-name letters ('Tower A', 'Block C') stay Unassigned on purpose; users add
`trade_rules` such as `['\\bmep\\b', 'Mechanical']`.

## textmatch

Fuzzy matching for Quick Find, the Command Palette and filter boxes.

```python
textmatch.score(query, text) -> float      # 0.0 = no match; empty query 0.0
textmatch.rank(query, items, key=None, limit=50) -> [(score, item)]   # best first, ties keep
    # input order; limit None/0 = all; empty query = first `limit` items with score 0.0
textmatch.spans(query, text) -> [(start, end)]   # merged ranges to highlight; [] when no match
textmatch.Index(items, key=None).rank(query, limit=50)   # texts lowercased once (per keystroke use)
```

Each query word (split on spaces) must match as an ordered subsequence, case-insensitively;
all words must match (any order) and their scores add. fzf v1 scoring on three alignments
(best contiguous occurrence, tightest subsequence, word-start/acronym): word starts after
space or `- _ . / \ > :` etc., CamelCase humps and digit runs score high; consecutive runs,
prefix and exact match add bonuses; gaps cost a little (capped, so any match is > 0); longer
texts lose up to 1 point. Measured: 20,000 items, short query: 70 to 150 ms on IronPython
(harness, loaded machine), 30 to 50 ms on CPython (`test_speed_20000_items`). Use `Index`
when the same list is ranked on every keystroke.

## ifcguid

```python
ifcguid.compress(uuid_text) -> 22-char GlobalId      # hyphens/braces/urn:uuid:/case optional; ValueError
ifcguid.expand(ifc) -> '8-4-4-4-12' lowercase         # ValueError when not valid
ifcguid.is_valid(text) -> bool                        # 22 chars of 0-9A-Za-z_$, first 0..3
ifcguid.new() -> random GlobalId
ifcguid.revit_export_guid(unique_id) -> guid text     # episode GUID with last 8 hex XOR element id
ifcguid.from_revit_unique_id(unique_id) -> GlobalId   # compress(revit_export_guid(...))
ifcguid.ALPHABET
```

Vectors: zero GUID -> `0000000000000000000000`, all-F -> `3$$$$$$$$$$$$$$$$$$$$$`; packing
cross-checked against the revit-ifc `ConvertToIFCGuid` byte layout. Trap: an element whose
Revit `IfcGUID` parameter was set carries that value; prefer the property when present.

## templates

Named saved configurations per tool, team-shared when a shared folder is set.

```python
t = templates.Templates(tool_id)        # file <team_root>\templates\<tool_id>.json ; ValueError for ''
t.names() -> [name]                     # natural, case-insensitive order
t.get(name) -> config copy or None      # exact name, else case-insensitive
t.info(name) -> {'name', 'updated', 'user'} or None
t.save(name, config) -> stored_name     # name sanitised; replaces same name in any case;
                                        #   ValueError for empty name / non-dict config
t.delete(name) -> bool
t.rename(old, new) -> new               # ValueError: old missing, new empty, new taken
t.export(path, names=None) -> count     # portable file; unknown names skipped
t.import_file(path, replace=False) -> count   # clashes become 'Name (2)' unless replace;
    # ValueError (sentence) for a missing/unreadable/foreign/other-tool file; never moves it aside
templates.all_tools() -> [tool_id]      # tools with at least one template in the current team root
templates.folder() ; t.path ; t.tool_id
```

File body: `{"format": "playground-templates", "version": 1, "tool": ..., "templates":
{name: {"config": {...}, "updated": ISO, "user": ...}}}`. Every change is a locked
read-modify-write. Trap: switching `shared_root` on or off changes which templates a user
sees (local ones are not merged in).

## reports

> A cancelled run returns `{'level': 'info', 'message': 'Report cancelled', 'cancelled': True, ...}`. Interactive callers check `result.get('cancelled')` and exit with NO toast (cancel is silent).

The fixed registry of automation-ready reports plus shared helpers.

```python
reports.REGISTRY      # [(id, title, module)], exactly the 22 entries below, in this order
reports.ids() ; reports.entry(id) -> (id, title, module) ; reports.title_of(id)   # KeyError if unknown
reports.module_exists(id) -> bool             # lib\namo\rep_<id>.py exists (no import)
reports.module_for(id) -> module              # KeyError unknown id, ImportError not built / broken
reports.available() -> [(id, title)]          # modules that exist, registry order
reports.run(id, config, doc=None, interactive=False, progress=None) -> result
    # config is merged OVER module.default_config(); NEVER raises: unknown id, missing module,
    # crash (logged with traceback) and cancel all come back as results; adds 'report',
    # 'title', 'seconds'
reports.output_path(config, default_name, ext, values=None, unique=False) -> path
    # folder: config['folder'] (%VARS% and ~ expanded) or <data_root>\reports, created;
    # name: config['name_template'] (default '{report} {date}') rendered with
    # naming.standard_values() + {'report': default_name} + values, sanitised; ext with or
    # without the dot; unique=True -> ' (2)' instead of overwriting
reports.base_config(**extra) -> {'folder': '', 'name_template': '{report} {date}', ...}
reports.default_config(id) ; reports.describe(id, config=None) -> str (title on failure)
reports.result(level, message, detail='', paths=None) -> result dict
reports.normalise_result(value) -> result dict
reports.Cancelled         # raise it (or any exception class named Cancelled) to stop
reports.LEVELS = ('success', 'info', 'warning', 'error') ; reports.MODULE_DIR (test seam)
```

| id | title | module |
|---|---|---|
| property_export | Property Export | rep_property_export |
| model_tree | Model Tree Export | rep_model_tree |
| count_by_property | Count by Property | rep_count_by_property |
| data_validation | Data Validation | rep_data_validation |
| clash_excel | Clash Excel Report | rep_clash_excel |
| clash_html | Clash HTML Dashboard | rep_clash_html |
| clash_matrix | Clash Count Matrix | rep_clash_matrix |
| clash_delta | Clash Delta | rep_clash_delta |
| clash_trends | Clash Trends | rep_clash_trends |
| per_trade | Per-Trade Reports | rep_per_trade |
| coordination | Coordination Report | rep_coordination |
| kpi_export | KPI Export | rep_kpi_export |
| health_check | Model Health Check | rep_health_check |
| session_stats | Session Stats | rep_session_stats |
| stale_files | Stale File Alert | rep_stale_files |
| preflight | Preflight Checks | rep_preflight |
| timeliner_export | TimeLiner Export | rep_timeliner_export |
| schedule_health | Schedule Health | rep_schedule_health |
| quick_takeoff | Quick Takeoff | rep_quick_takeoff |
| zone_takeoff | Zone Takeoff | rep_zone_takeoff |
| viewpoint_images | Viewpoints to Images | rep_viewpoint_images |
| batch_pdf | Batch PDF Printer | rep_batch_pdf |

### The rep_<id>.py contract (every report tool implements it)

```python
# lib\namo\rep_clash_excel.py
"""Clash Excel Report: one workbook per run, a sheet per clash test."""
from namo import reports

TITLE = 'Clash Excel Report'               # same as REGISTRY


def default_config():
    """JSON-serialisable; ALWAYS includes 'folder' and 'name_template'."""
    return reports.base_config(tests=[], statuses=['New', 'Active'], images=False)


def describe(config):
    """One line for Report Templates / Scheduled Reports lists."""
    return '%d tests, %s' % (len(config['tests']), ', '.join(config['statuses']))


def run(config, doc=None, interactive=True, progress=None):
    """interactive=False: NO dialogs, prompts, windows or toasts (pynavis run, schedules,
    macros). Decide every option from config; report problems in the result instead.
    progress(fraction 0..1, label) may be None: call it only `if progress:`.
    Raise reports.Cancelled (or let namo.items.Cancelled through) to stop."""
    path = reports.output_path(config, TITLE, 'xlsx')
    ...                                     # write the file (namo.xlsx etc.)
    return reports.result('success', 'Wrote 3 sheets', path, paths=[path])
    # {'level': 'success'|'info'|'warning'|'error', 'message': str, 'detail': str,
    #  'paths': [files written]}
```

Rules: `run` receives the merged config (defaults + caller's keys), may receive `doc=None`
(meaning the active document), and must not toast or open the file itself when
`interactive=False` (the caller decides). The ribbon `script.py` gathers options (dialog or
`script.get_config`), calls `reports.run(id, config, interactive=True, progress=...)` and
toasts `result['message']` / `result['detail']`. Keep nothing in module globals.

## dates

```python
dates.parse(value, day_first=True) -> datetime or None    # never raises; naive LOCAL time
    # ISO (2026-10-05, 2026/10/05, 2026-10-05 14:30, 2026-10-05T14:30:00.123Z: zones converted
    # to local), compact 20261005[T143000], d/m/y or m/d/y (a part over 12 decides, else
    # day_first), 2-digit years 1970..2069, month names (5 Oct 2026, 05-Oct-2026,
    # October 5, 2026, Mon 5 Oct 2026), times with seconds and am/pm, Excel serial numbers
    # (int/float 1..2958465; number-only TEXT only in 20000..80000), datetime/date objects,
    # .NET DateTime (anything with Year/Month/Day)
dates.iso(value, date_only=False) -> 'YYYY-MM-DDTHH:MM:SS' | 'YYYY-MM-DD' | ''
dates.now() ; dates.today() -> datetime at 00:00
dates.add_days(value, n) -> datetime or None
dates.days_between(a, b) -> int or None      # calendar days b - a (times ignored)
dates.age_bucket(days, buckets=(7, 14, 30)) -> '0-7 days' | '8-14 days' | '15-30 days' | 'Over 30 days'
                                             #   (negative -> first band, None -> 'Unknown')
dates.bucket_labels(buckets=(7, 14, 30)) -> [labels in order]
dates.format(value, fmt=None) -> str         # fmt default: config date_format; '' when unparseable
dates.week_start(value) -> Monday 00:00 or None
dates.from_excel(serial) ; dates.to_excel(value)
dates.from_net(net) -> datetime or None      # UTC kind converted to local; MinValue (year 1) -> None
dates.to_net(value) -> System.DateTime (Local kind) or None   # needs .NET
```

## units

```python
units.DOC_UNIT_METERS   # {'Meters':1.0,'Centimeters':0.01,'Millimeters':0.001,'Feet':0.3048,'Inches':0.0254,
                        #  'Yards':0.9144,'Kilometers':1000,'Micrometers':1e-6,'Microinches':2.54e-8,
                        #  'Mils':2.54e-5,'Miles':1609.344}   keys = str(doc.Units)
units.to_meters(value, doc_units) ; units.from_meters(value_m, doc_units)   # doc names or length aliases;
                                                                           #   ValueError when unknown
units.KINDS = ('length', 'area', 'volume', 'mass') ; units.BASE ; units.UNITS {symbol: (kind, SI factor)}
units.ALIASES {unit_key: symbol} ; units.unit_key(text) ; units.resolve(text) -> symbol or None
units.kind_of(text) -> kind or None
units.convert(value, from_unit, to_unit) -> float   # any aliases; ValueError across kinds/unknown;
                                                    #   rounded to 12 significant digits (24 in = 2.0 ft)
units.parse_quantity(text) -> (value, unit, kind) or None   # bare number -> (value, None, None)
units.parse_conversion(text) -> (value, from_unit, to_unit) or None
units.convert_text(text) -> (value, to_unit)        # ValueError with a sentence for a toast
units.format(value, unit, decimals=2, ascii=False) -> '1,250.00 mm' / '3.50 m²'
units.symbol(unit, ascii=False) ; units.DISPLAY
units.parse_number(text) -> float or None ; units.split_number(text) -> (value, rest)
units.parse_length(text, doc_units) -> float or None      # pure port of pynavis.lengths.parse
units.format_length_input(value, doc_units, denominator=16)   # pure port of format_input
units.format_feet_inches(feet, denominator=16) -> "12' 6 1/2\""
units.is_imperial(doc_units) ; units.doc_unit_symbol(doc_units) -> 'ft' | 'mm' | ...
units.report_units_for(report_units, doc_units) -> {'length', 'area', 'volume'}   # metric: m2/m3,
                                                                                  #   imperial: ft2/ft3
```

Canonical symbols: length m mm cm km um in ft yd mi mil uin; area m2 mm2 cm2 km2 ha in2 ft2
yd2 ac; volume m3 mm3 cm3 l ml in3 ft3 yd3 gal (US) gal_uk; mass kg g t (tonne) lb oz ton (US
short ton). Aliases ignore case, spaces, dots and `^`, read superscripts as digits: m², sq m,
sqm, SF, sq ft, ft², CF, cu ft, cuyd, CY, L, litres, gal(US), gal (UK), lbs, tonnes...
`parse_quantity` tries "number + one unit" first (so `250 ft2` is an area, not 250 ft 2 in),
then feet-and-inches (`12' - 6 1/2"`, `12'6"`, `6 1/2"`, `2 ft 3 in`). Numbers: `1,234` and
`1 234` are thousands, `12,5` and `0,250` decimal commas, `1.234,5` / `1,234.5` both work.
`parse_conversion` separators: ` to `, ` in `, ` into `, ` as `, `->`, `=>`, `=` (the last one
that leaves a quantity on the left and a unit on the right wins: `5 in in mm`). Trap:
`parse_length` keeps the pynavis rules exactly (negative lengths refused, the `1 6` space form
only in imperial documents); use `parse_quantity` for signed values.
