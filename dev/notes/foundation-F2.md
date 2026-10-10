# Foundation F2: data core (notes)

Modules in `Playground.extension/lib/namo/`, documented for tool agents in `README-F2.md`.
Everything is verified headlessly only (CPython 3.11 pytest + IronPython 3.4.2 harness);
nothing here has run inside Navisworks yet.

## 1. Modules

* `paths`: data_root/team_root, document keys (identical to pynavis.memory, tested),
  Windows-safe names, atomic writes, JSON files that move damaged copies aside, FileLock,
  and `redirect()`, the test seam for both the data root and the settings file.
* `config`: Playground-wide settings through pynavis.settings (tool 'playground'), normalised on load.
* `session`: holders under `sys.modules['playground_<key>']` that survive the per-run lib sweep;
  the shared `log()` / `recent_log()`.
* `store`: Store (one JSON value) and RecordStore (one file per record) in local, shared
  or model mode, with logged fallbacks and a user-facing `.note`.
* `docdb`: Playground tables inside the document's SQLite database. Pure SQL/JSON half tested
  against real SQLite (3.45 on CPython, 3.7.7 on IronPython); Navisworks half untested.
* `naming`: `{token:spec}` templates, standard tokens, unique names, sanitising, natural sort.
* `rules`: condition engine (18 ops), text rules (`parse_cell`/`describe` round-trip),
  validation, and a native search plan for pynavis.sets.
* `trades`: trade from model file names (ordered regex rules, config rules first).
* `textmatch`: fzf-style fuzzy ranking; 20,000 items in 70 to 150 ms on IronPython in the
  harness (machine shared with other agents), 30 to 50 ms on CPython.
* `ifcguid`: IFC GlobalId compress/expand/new/valid and Revit's export GUID rule.
* `templates`: named configs per tool in the team root, locked writes, import/export.
* `reports`: the fixed 22-entry REGISTRY, `run()` that never raises, `output_path()`, the
  rep_<id>.py contract (README-F2.md).
* `dates`: parse anything (ISO, typed, Excel serial, .NET DateTime), buckets, formatting.
* `units`: length/area/volume/mass conversion with aliases, quantities, Revit feet-inches,
  conversion sentences, and a pure port of PyNavis.Runtime.Units.Lengths.

## 2. In-app checks (only a Navisworks session can confirm these)

Run these from the pyNavis Console (IronPython) with a document open. Expected results are
what the code assumes; anything else, note it and tell the lead.

### docdb (the one module whose Navisworks half is unverified)

```python
from namo import docdb, session
print(docdb.available())                          # D1
docdb.kv_set('f2-check', {'a': 1, 'list': [1, 2]})   # D2
print(docdb.kv_get('f2-check'))                   # D3
print(session.get('docdb', 'read_route'))         # D4
print(docdb.kv_keys('f2'))                        # D5
docdb.record_put('f2-records', 'R-10', {'t': 'ten'}); docdb.record_put('f2-records', 'R-9', {'t': 'nine'})
print(docdb.records('f2-records'))                # D6
print(docdb.kv_delete('f2-check'), docdb.record_delete('f2-records', 'R-9'))   # D7
```

1. **D1** `available()` prints True for an empty new document AND for an opened NWF.
   Assumes `Document.Database.Value` gives a usable `NavisworksConnection` and that a
   `SELECT ... FROM sqlite_master` works on it.
2. **D2** the first `kv_set` raises nothing. Assumes: tables can be created with
   `CREATE TABLE IF NOT EXISTS` inside `doc.Database.BeginTransaction(DatabaseChangedAction.Reset)`
   + `Commit()`, then the row written inside a separate `...(DatabaseChangedAction.Edited)`
   transaction; commands made with `transaction.Connection.CreateCommand()`; the
   best-effort `command.Transaction = transaction` assignment is harmless (it is wrapped in
   try/except). If D2 fails, the IOError text carries the Navisworks message: paste it.
3. **D3** prints `{'a': 1, 'list': [1, 2]}`. Assumes `@key`-style named parameters bound
   with `Parameters.AddWithValue('@key', value)` work for BOTH reads and writes. If D2 passes
   but D3 prints None, parameter naming is the suspect: retry with names without '@'
   (change `docdb.params`) and tell the lead.
4. **D4** prints `adapter` (the documented `NavisworksDataAdapter(command).Fill(DataTable)`
   read route). `reader` means the adapter failed and the fallback (`ExecuteReader` on a
   connection opened by us when `State != Open`, closed afterwards) is in use: check that
   Navisworks still behaves normally afterwards (we may have closed its connection).
5. **D5** prints `['f2-check']`; **D6** lists R-9 before R-10 with 'id' filled in.
6. **D7** prints `True True`; running it again prints `False False`.
7. The document title shows it as modified after D2 (unsaved changes). Save the NWF, close,
   reopen, and `docdb.kv_get('f2-check')` (rerun D2 first if you ran D7) returns the value:
   the data travels with the file. Publish an NWD and check the same in the NWD.
8. Ctrl+Z right after a `kv_set`: the value should stay (we never call
   `EnableTableUndoable`). Record what actually happens.
9. Inside `with pynavis.viewpoints.transaction('x'):` call `docdb.kv_set('n', 1)`: does a
   Database transaction nest inside a Document transaction? (Tools are told not to do this
   until confirmed.)
10. Open an NWD from a read-only folder, run D2: expect an IOError (toastable), not a crash.
11. After appending a model (which may reset the database), D3 still reads.

### store / paths / config

12. Shift+Click any future Playground settings tool or run `from namo import config;
    print(config.path())`: the file is `%APPDATA%\pyNavis\settings\playground.json`, and
    `config.save({'company': 'X'})` writes it (atomic through pynavis._atomic).
13. Set `shared_root` to a real UNC share, then `store.Store('f2', doc_path, mode='shared')`:
    `.mode == 'shared'`, `.path` under `<share>\docs\<name-key>\`. Unplug or point it at a
    dead server: construction takes at most one probe per 15 s and `.note` says the shared
    folder is unreachable. FileLock (O_EXCL create) works on that share (two machines
    saving the same template both keep their entry).
14. `store.for_active_doc('f2')` on an unsaved document uses the 'untitled' key; on a
    saved one the key matches `pynavis.memory`'s file stem for that document.

### rules.native_query (needs a model)

15. For each, compare `sets.run(rules.native_query([cond]))` count with a Python walk using
    `rules.evaluate` (ignore_case True):
    `Element > Category = Ducts`; `Item > Name != X`; `Item > Name contains duct`;
    `Item > Name like P-*` and `Item > Name starts with P-` (DisplayStringWildcard with
    IgnoreStringValueCase); `Element > Width >= 1` on a Double property (NumericGreaterThan
    with a Double VariantData); `Element > Mark is missing` (pynavis notes not_has_property
    is unverified); `Level between 1 and 3`. Expect equal counts. Known gap by design:
    `numbers_as_text=True` with a numeric (Double/Int32) property finds nothing natively.

### dates / units / naming / textmatch

16. `dates.parse(result.CreatedTime)` on a clash result: a datetime (Nullable<DateTime>
    arrives as DateTime or None); `dates.from_net(System.DateTime.MinValue)` is None; a UTC
    kind value is converted to local time.
17. `str(doc.Units)` is one of the `units.DOC_UNIT_METERS` keys for metric and imperial
    documents ('Feet', 'Millimeters', ...).
18. `naming.standard_values()` with a saved document: `file` is the file stem, `title`
    the document title.
19. `textmatch.rank` over ~20,000 strings inside Navisworks stays under 200 ms (70 to
    150 ms in the harness depending on load; the busiest query is a one-letter one).

## 3. Requests for modules I do not own

* `dev/tests/_compat.py` (lead): CPython tests that want the real `pynavis.settings`,
  `pynavis.sets` or `pynavis.memory` must add `<pyNavis checkout>\pynavislib` to `sys.path`
  themselves (test_config/test_rules do; IronPython already has it). A `_compat.use_pynavislib()`
  helper would remove that boilerplate. Not required: namo.config works without pynavis.
* Lead: merge `README-F2.md` into `lib/namo/README.md`.
* F3 (advice, not a change): `clashdata.save_history` fits `store.RecordStore('clash-history',
  doc_path)` with one record per snapshot (id = timestamp) better than one growing JSON value;
  `paint.remember_scheme` fits `store.Store('last-color-scheme', scope='global')`;
  `items.revit_ids()['ifc_guid']` can fall back to `ifcguid.from_revit_unique_id(unique_id)`
  when no IfcGUID property exists.

## 4. Deviations from FOUNDATION.md (all additive or clarifying)

* `config.DEFAULTS['user']` holds the actual Windows user name (the contract's '<USERNAME>').
  Added `defaults()`, `normalise()`, `path()`, `MODES`, `REPORT_UNITS`, `get(key, default)`.
* `session.set` returns the value; added `clear`, `keys`, `log`, `recent_log`.
* `store`: Store/RecordStore take an extra `doc=None`; `.note` reports fallbacks; 'model' with
  scope 'global' quietly means 'local'; `RecordStore.list()` sorts ids in NATURAL order;
  added `exists`, `delete`, `ids`, `add`, `records_for_active_doc`.
* `docdb`: added `record_get`, `collections`, `SqliteBackend`, `use_backend`; table creation
  runs in a `Reset` transaction, data writes in `Edited`.
* `naming.standard_values` gives date/time/datetime as objects so `{date:%Y%m%d}` works;
  added `natural_key`, `format_value`.
* `rules`: `ignore_case` defaults True; 'empty' is True for missing properties;
  `native_query` gained `mode`, `numbers_as_text`, `max_groups`; added `native_plan`,
  `normalise`, `text_of`, `op_of`, `as_list`, `bounds`. `parse_cell` keeps values as text
  (`between` -> ['1', '3']).
* `trades.rules_from_config(cfg=None)` loads config when cfg is omitted; added `explain`,
  `classify`.
* `textmatch`: added `Index`.
* `ifcguid`: added `revit_export_guid`, `ALPHABET`.
* `templates`: `export` returns the count; added `info`, `folder`.
* `reports.output_path` gained `values`, `unique`; a missing name_template means
  '{report} {date}'; added `Cancelled`, `result`, `normalise_result`, `base_config`,
  `default_config`, `describe`, `ids`, `entry`, `title_of`, `module_exists`, `MODULE_DIR`.
* `dates.parse` gained `day_first`; `today()` is a datetime at 00:00; added `now`,
  `bucket_labels`, `week_start`, `from_excel`, `to_excel`.
* `units.KINDS` is a tuple of kind names; `ALIASES` keys are normalised lookup keys (use
  `resolve`); `parse_quantity` returns `(value, None, None)` for a bare number; added
  `parse_length`, `format_length_input`, `format_feet_inches`, `convert_text`, `resolve`,
  `kind_of`, `symbol`, `parse_number`, `split_number`, `report_units_for`, `doc_unit_symbol`.

## 5. Test counts (my 14 files: dev/tests/test_{paths,config,session,store,docdb,naming,rules,trades,textmatch,ifcguid,templates,reports,dates,units}.py)

* CPython 3.11: 147 passed, 1 skipped (dates.to_net needs .NET).
* IronPython 3.4.2: 148 passed, 0 skipped.
* Full `python dev/verify.py`: pytest, IronPython compile/tests/smoke and the parser pass;
  check.py reports only the 25 pre-existing "layout entry names no folder" problems of the
  empty tabs. My files add zero problems.
