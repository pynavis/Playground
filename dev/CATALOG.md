# Playground tool catalog

The spec for every Playground tool, grouped by build assignment. Each group owns its panels
(folder + `bundle.yaml` layout + every bundle inside), the `lib\namo` modules named in its
section, its `rep_*`/`hk_*` modules, `dev\icons\<group>.py`, its tests and
`dev\notes\<group>.md`. `#N` is the row in the user's feature list
(`<pyNavis checkout>\docs\feature-ideas-100.csv`, read-only).

Paths are relative to `Playground.extension\`. "large" = top-level pushbutton (big icon);
"stack" = 2-3 small rows; "pulldown" = menu. Titles in bundle.yaml use `\n` for two-line
large captions. Shortcuts: ONLY the ones listed here (all checked free against pyNavis).

Shared expectations for every tool (on top of BRIEF.md):
* Every tool works on the ACTIVE document, says plainly when there is nothing to work on,
  and finishes with a toast (or output window when there is a table/report).
* Scope choices, where offered, are: current selection / visible items / whole model,
  defaulting to the selection when one exists (remember the last choice in config).
* Huge models: budget + progress + cancel; say "sampled N of M" when sampling.
* Lengths shown to users in document units via `pynavis.lengths` / `namo.units`.
* Files: default folder = the document's folder when saved, else Documents; default
  names from `namo.naming` templates, e.g. `{file} - Clash report - {date}.xlsx`.
* Everything that writes the document is ONE undo step.
* Team data (templates, presets, rules, libraries) goes through `namo.templates` /
  `namo.store` scope 'global' so `namo.config` shared mode moves it to the team folder.

---------------------------------------------------------------------------------------

## G1 select_find: tab Model, panels `Select.panel`, `Find.panel`

Owns modules: `namo/selecttools.py` (pure planning + API), `namo/quickfind.py`,
`namo/setwizard.py`, `namo/setexchange.py`, handlers `hk_selhistory.py`, `hk_pickorder.py`.

### Select.panel  layout: Select_Similar, Filter_Selection, Quick (stack), History (stack), Pick_Order, Pick_Order_Actions

* **#4 Select Similar** `Select.panel/Select_Similar.pushbutton` (large, context: selection).
  Uses the first selected item (its object-level ancestor when the pick is a sub-part).
  Lists its properties as "Category > Property = value" in `namo.ui.choose` (multi,
  searchable), pre-checking the property NAMES chosen last time; hides volatile ones by
  default (GUIDs, ids, Item > Name when unique) behind a "Show identity properties"
  filter. Options row: scope Whole model / Same model as the item / Current selection.
  Builds an AND query via `pynavis.sets.query()` (equals, ignore case for text) and runs
  it (scope via `sets.run(scope=...)`), selects the matches, toasts "Selected 1,204
  similar items" with the property list as detail. Config: remember choices.
* **#5 Filter Selection** `Select.panel/Filter_Selection.pushbutton` (large, context:
  selection). Prunes the CURRENT selection without a new search: `namo.ui.form` with
  property (from `items.sample_properties` of the selection), operator (namo.rules OPS),
  value (choice from `items.distinct_values` plus free text), Keep matching / Remove
  matching, "Test each item's element (object) properties" check. Evaluates in Python
  with `namo.rules.matches`, counted progress + cancel past 2,000 items, replaces the
  selection, toasts "Kept 312 of 1,040".
* `Select.panel/Quick.stack` (layout: Invert, Select_by_File, Save_as_Set)
  * **#6 Invert** `Invert.pushbutton` (context: doc). `ModelItemCollection.Invert(doc)` on
    the current selection, then drops hidden items (item or any ancestor hidden) unless
    Shift+Click config says otherwise; empty selection inverts to "everything visible".
    Toast count.
  * **#8 Select by File** `Select_by_File.pushbutton` (context: doc). `namo.ui.choose` of
    appended models (columns: file, source type, units, items), multi, remembers the last
    ticked files by name. Selects their root items; optional zoom (config). Toast.
  * **#9 Save as Set** `Save_as_Set.pushbutton` (title: Save as Set, context: selection).
    Current selection -> static selection set named from a `namo.naming` template
    (default `{category} - {count} items - {date}`, tokens: category = most common
    category in the selection, count, date, time, user, file, model) into a folder
    (default "Playground"); Shift+Click config edits template + folder. Uses
    `pynavis.sets.create(name, items, folder=...)` (names deduped). Toast the final name.
    (Distinct from pyNavis' Save as Set, which saves the selection MEMORY.)
* `Select.panel/History.stack` (layout: Back, Forward, History_List): **#7 Selection History**
  * `hk_selhistory.handle`: on 'selection-changed' records the selection (as
    `items.entries`, capped at 5,000 items per state; states capped at 50) into a
    per-document session history with a cursor; skips the change when its signature
    equals the "expected" signature Back/Forward stored (their own restore fires the
    debounced event after the command ends); skips empty selections unless configured.
  * **Back** `Back.pushbutton` (shortcut Alt+Left, context: doc) and **Forward**
    `Forward.pushbutton` (shortcut Alt+Right, context: doc): move the cursor and restore
    (`items.resolve`), toast "Selection 3 of 12" + count; "No earlier selection" info.
  * **History list** `History_List.pushbutton` (title: History): choose any recorded state
    (time, count, top category) and restore it.
* **#102 Pick Order** `Select.panel/Pick_Order.toggle` (large toggle, title Pick\nOrder,
  title_on Stop\nPicking). On = `hk_pickorder` appends each newly selected single item
  (or each item of a small added set, in the order they appear) to an ordered pick list
  (session + per-document store 'pick-order'), ignoring repeats; toggling on asks "Start
  a new list or continue?" when one exists; toasts only on toggle on/off ("Pick order
  on: click items in order", "Pick order off: 7 picked"). The list survives the session
  in the store.
* **Pick Order actions** `Select.panel/Pick_Order_Actions.pulldown` (title Picked, tooltip
  required, layout: Select_Picked, Number_Picked, Export_Picked, Color_Picked, Clear_Picked):
  * Select Picked: select the list in order.
  * Number Picked: writes `Playground > Sequence` = 1..N (merge into the existing custom tab
    with `props.get_custom` + `props.set_custom`, one undo step); start/step/prefix via form.
  * Export Picked: xlsx/CSV (order, name, category, Element ID, GUID, source file,
    centre X/Y/Z in doc units) via `namo.xlsx`.
  * Color Picked: gradient along the order (`namo.colors.sequential`, `namo.paint.apply`).
  * Clear Picked: empties the list (confirm when > 20).

### Find.panel  layout: Quick_Find, Search_Set_Wizard, Batch_Sets, Sets_Library, Set_Exchange (stack)

* **#12 Quick Find** `Find.panel/Quick_Find.pushbutton` (large, shortcut Ctrl+Alt+F,
  context: doc). Type-ahead search over every object in the model by name and key
  property values. First use per document builds an index with counted progress + cancel
  (object-level items; fields: Item Name, class, Element Id, Element Category/Family/
  Type/Mark/Comments, IFC GlobalId/Name, System Name, Level: the list is configurable),
  persisted to `%APPDATA%\pyNavis\playground\index\<doc_key>.json` keyed by model file names + sizes
  + mtimes so the next session opens instantly; stale index rebuilt automatically.
  Window (`namo.ui` modal search window: a search box and a results list, 200 best via
  `namo.textmatch.rank`, matched field and value shown, highlight spans): Enter = select
  + zoom the highlighted result and close; Shift+Enter = select ALL results; Ctrl+Enter =
  add to selection; Esc closes. Results resolve via stored entries. Config: fields, cap.
* **#1 Search Set Wizard** `Find.panel/Search_Set_Wizard.pushbutton` (large, context: doc).
  A real guided builder (custom `namo.ui` window, one page with steps): 1 scope (whole
  model / selected models / current selection); 2 conditions list: add/remove rows, each
  row = category (from a property sample of the scope; searchable), property, operator
  (native-search ops only: equals, not equals, contains, wildcard, >, >=, <, <=, exists,
  missing), value (choice of observed values with counts + free text), ignore case;
  AND within the set, optional OR groups (become one set per group, explained inline);
  3 "Count matches" (runs `sets.run`, shows count, timing); 4 save: name, folder, and
  "Select now". Creates with `pynavis.sets.create(name, query, folder)`. Remembers the
  last query. Toast "Created search set 'Ducts on L3' (412 items)".
* **#2 Batch Sets** `Find.panel/Batch_Sets.pushbutton` (title Batch\nSets, large,
  context: doc). Pick a property (sampled from selection or model), collect distinct
  values (from the selection, or a full counted scan), choose values (all ticked, with
  counts), set-name template (`{value}`, `{property}: {value}`), folder template
  (default `By {property}`), optional extra fixed condition (e.g. Category = Ducts).
  Creates one SEARCH set per value (equals) in one transaction (`sets.create` per value
  inside `viewpoints.transaction`), skipping names that exist unless "replace" is
  chosen (`sets.update`). Toast "Created 14 search sets in 'By Level'".
* **#74 Sets Library** `Find.panel/Sets_Library.pushbutton` (large, context: doc).
  Libraries are JSON files in `namo.paths.team_root()\libraries\sets\` (shared in team
  mode). Actions (`forms.ask_options`): Publish to library (choose search sets from
  `sets.export_all()`, name the library, merge or replace), Import from library (choose
  library, tick sets, replace same-named or add), Manage (rename/delete/open folder).
  Import via `sets.import_dict` with progress; report problems in the output window.
* `Find.panel/Set_Exchange.stack` (layout: Export_Sets, Import_Sets, Search_In_Repair):
  * **#10 Export Sets** `Export_Sets.pushbutton` (context: selection-sets): choose sets
    (tree order, folders) -> Playground XML (`<playground-sets version="1">`): search sets as
    their conditions (`sets.to_dict`), STATIC sets as portable item references (per item:
    model file name, PathId, plus Revit Element ID, UniqueId, IFC GlobalId and
    InstanceGuid when present) so they survive into another file or session. Toast.
  * **#10 Import Sets** `Import_Sets.pushbutton` (context: doc): reads that XML, recreates
    folders/sets; static sets resolve by PathId first (`items.resolve`), then by GUID/
    Element ID searches (batched, progress); reports per set how many items resolved;
    never creates an empty static set silently (asks, default skip).
  * **#11 Search-In Repair** `Search_In_Repair.pushbutton` (title Repair Search In: stack
    rows are one line, context: selection-sets). Finds
    search sets whose "Search In" scope (the search's own Selection / locations) is empty
    or points at items/models that no longer resolve after an export/import between
    projects. Lists them with what they pointed at; per set, re-scope to models matched
    by file name automatically or chosen by hand, then rewrites the set's search with the
    new scope (copy the SelectionSet, set its Search's selection scope, replace in place;
    investigate `SelectionSet.Search`, `Search.Selection`, `Search.Locations`,
    `DocumentSelectionSets.ReplaceWithCopy`/`EditDisplayName` in the dump). Shows a
    before/after table. If the API cannot rewrite a scope, report exactly what manual
    step remains (and note it).

---------------------------------------------------------------------------------------

## G2 inspect_data: tab Model, panels `Inspect.panel`, `Data.panel`

Owns modules: `namo/inspect.py`, `namo/propindex.py` (scan/index shared by Explorer,
Count, Validator), `namo/propwrite.py` (bulk writer, find/replace, mapper, data link),
`namo/validator.py`, `namo/hud.py`, reports `rep_property_export.py`, `rep_model_tree.py`,
`rep_count_by_property.py`, `rep_data_validation.py`.

### Inspect.panel  layout: What_Is_It, Properties_Plus, Selection_HUD, Inspect_Tools (stack)

* **#105 What Is It** `What_Is_It.pushbutton` (large, title What\nIs It, shortcut Ctrl+Alt+I,
  context: doc). Target = first selected item, else `namo.picking.point(prompt,
  want_item=True)` (None on Esc: silent). Output window card (`output.print_html`, hand-built HTML with the
  window's CSS variables): name, class, Revit category/family/type, source file (+ full
  path), tree path with parent links (`output.element_link`), Element ID / UniqueId / IFC
  GlobalId / InstanceGuid, model index + PathId, bounding box min/max/size in document
  units (+ meters), centre, geometry: primitive count, fragment count, solid?, original/
  active colour swatch + transparency, transform non-identity?, hidden/required/frozen,
  then property tabs with counts (collapsible list of every category and its
  properties). Also copies a plain-text summary to the clipboard and says so in a toast.
* **#65 Properties Plus** `Properties_Plus.pushbutton` (large, title Properties\nPlus).
  Modeless window (`namo.ui.Modeless`, key 'properties-plus') that follows the
  selection live (subscribe `doc.CurrentSelection.Changed` directly with a 200 ms
  `ui.Debouncer`; unsubscribe on close; survive document switch by re-subscribing on
  `Application.ActiveDocumentChanged` if present in the dump). Shows pinned properties
  ("Category > Property", pinned list in config, add/remove via a picker of the current
  item's properties) for the selection: one row per pinned property, value when all
  selected items agree, otherwise "Varies (N values)" with a tooltip of the first values;
  plus a "This item" expander with every tab. Row actions: copy value, "Select items
  with this value" (search). Second click on the button focuses the open window.
* **#124 Selection HUD** `Selection_HUD.toggle` (large toggle, title Selection\nHUD).
  On: a small non-activating, borderless, topmost-over-host window anchored to the
  bottom-left of the Navisworks main window (`ui.host_rect`, re-anchored on a 1 s
  `DispatcherTimer` if the host moved) showing: "N items selected (M objects)", models
  involved, top 3 categories with counts, and when configured a summed numeric property
  (e.g. Length). Updates via selection Changed (debounced). Off: closes, unsubscribes.
  Session-only like every pyNavis toggle.
* `Inspect.panel/Inspect_Tools.stack` (layout: Copy_IDs, Open_in_Explorer)
  * **#114 Copy IDs** `Copy_IDs.pushbutton` (context: selection). One row per selected
    object: name, Element ID, UniqueId, IFC GlobalId, InstanceGuid, source file, tree
    path; tab-separated with a header, to the clipboard (`script.clipboard_copy`). Shift+
    Click: choose columns. Toast "Copied 12 rows".
  * **#115 Open in Explorer** `Open_in_Explorer.pushbutton` (context: doc). For the first
    selected item: its model's cache file (`Model.FileName`) and source file
    (`Model.SourceFileName`); if both exist and differ ask which (ask_options), then
    `script.show_in_explorer`. Nothing selected: the document's own file. Missing file:
    toast which path is gone.

### Data.panel  layout: Property_Explorer, Count_by_Property, Property_Exporter, Data_Validator, Write_Data (pulldown), Data_Tools (stack), Property_Labels

* **#57 Property Explorer** `Property_Explorer.pushbutton` (large, context: doc). Scans the
  scope (selection / visible / whole model; objects or every geometry item) with
  progress + cancel + budget (default 200,000 items, sampling noted), building category
  -> property -> value -> count (`namo.propindex`, cached per document in the session).
  Window: three linked lists (categories with item counts; properties with item counts
  and distinct-value counts; values with counts, searchable) + actions: Select items with
  value (search), Create search set, Copy, Export the index to xlsx. Fast for 50k objects.
* **#63 Count by Property** `Count_by_Property.pushbutton` (large, context: doc,
  report: count_by_property). Property (one, optional second for a two-level pivot) +
  scope; output window: sorted table with counts and %, top-20 bar chart
  (`output.chart_bar`), then `namo.ui.choose` offers "Select a group" (selects that
  group's items). Export xlsx option. Config remembers property.
* **#58 Property Exporter** `Property_Exporter.pushbutton` (large, context: selection,
  report: property_export). Choose properties (union of the selection's properties,
  pre-ticked from the last run, saved as named templates via `namo.templates`
  'property_export'); rows = selected objects (or their geometry descendants); extra
  identity columns (name, file, Element ID, GUID); writes a styled xlsx (`namo.xlsx`:
  header, widths, freeze, autofilter; numbers as numbers) or CSV; toast + open option.
* **#62 Data Validator** `Data_Validator.pushbutton` (large, context: doc, report:
  data_validation). Rule sets (BEP checks) as JSON in `team_root()\rules\validation\*.json`
  (ship a documented starter set: e.g. every Ducts object has System Name; every
  element has Level; Mark not empty; Comments matches a pattern). Rule = name, applies-to
  conditions (namo.rules), requirements (exists / not empty / regex / in list / numeric
  range). Run on scope: output summary per rule (checked, passed, failed, % bar),
  failures table with element links (first 500), xlsx export, optional selection set per
  failing rule ("Validation/<rule>"). Shift+Click: open rules folder / validate rule
  files (clear error messages with line context).
* **Write data** `Write_Data.pulldown` (title Write\nData, layout: Bulk_Property_Writer,
  Find_and_Replace, Property_Mapper, External_Data_Link):
  * **#59 Bulk Property Writer** (context: doc): mode 1 "Write to selection": form with tab
    name (default 'Playground') and up to 10 name/value rows (types inferred), merges into
    existing custom tabs (`props.get_custom` + `props.set_custom`). Mode 2 "From Excel":
    workbook whose header row names a key column ('Element ID', 'GUID', or
    'Category > Property') and value columns; matches rows to objects in scope (index the
    key once), preview (matched, unmatched rows, ambiguous keys), writes one custom tab,
    one undo step; unmatched rows exported back to xlsx.
  * **#60 Find and Replace** (context: doc): find text or regex in property values (all or
    chosen category/property, scope); preview table (item, tab, property, old, new);
    native properties are read-only in Navisworks, so replacing writes the corrected value
    into a custom tab ('Playground Corrected', property named "<Category> - <Property>"),
    while matches already inside custom tabs are edited in place (merge). Explain this in
    the dialog's intro line.
  * **#61 Property Mapper** (context: doc): mapping profiles (`namo.templates`
    'property_mapper'): target fields (e.g. System, Level, Mark), each an ordered list
    of source candidates ("Element > System Name", "IFC > SystemName", "Item > Layer")
    with optional regex extract/replace and per-model overrides; preview coverage % per
    field per model; apply writes a standard custom tab (default 'Standard'). Import/
    export profiles as JSON.
  * **#67 External Data Link** (context: doc): saved links per document (namo.store
    'data-links'): source file (xlsx/csv), sheet, key column <-> model property, columns
    to bring in, target tab. Actions: New link, Refresh all links (re-read files, rewrite
    tabs, report matched/unmatched/changed), Remove link (optionally strip the tab),
    Select unmatched objects. Shows last refresh time and file timestamp.
* `Data.panel/Data_Tools.stack` (layout: Model_Tree_Export, Clear_Labels)
  * **#68 Model Tree Export** `Model_Tree_Export.pushbutton` (context: doc, report:
    model_tree): tree to depth N (default 4), per node: depth, name, class, descendants,
    geometry items, hidden?; xlsx with outline indentation (indent column + one column
    per level) and per-model sheets; toast path.
  * Clear Labels `Clear_Labels.pushbutton`: removes Property Labels (overlay tag).
* **#66 Property Labels** `Property_Labels.pushbutton` (large, title Property\nLabels,
  context: selection): choose a property (or name), draws `pynavis.overlay` labels at each
  selected object's bbox top-centre (short leader segment), value text (units from the
  property's display string), capped at 500 with a note; tag 'playground-labels'; toasts
  how many and that Clear Labels removes them. Overlay unavailable -> warning toast.

---------------------------------------------------------------------------------------

## G3 look: tab Model, panel `Look.panel`

Owns modules: `namo/colorize.py` (property colouring engine, presets, legend data),
`namo/legend.py` (WPF legend render to PNG), `namo/explode.py`, `namo/presentation.py`.

`Look.panel` layout: Color_by_Property, Color_Presets, Trade_Ghost, Status_Painter,
Look_Tools (stack), View_Tools (stack), Presentation_Mode

* **#76 Color by Property** `Color_by_Property.pushbutton` (large, context: doc). Property
  + scope (default visible model); distinct values with counts (counted progress);
  `namo.colors.for_values` (stable: the same value keeps its colour between runs within
  a scheme; top N values (default 12) coloured, the rest "Other" in grey or untouched);
  option "Ghost everything else" (transparency); applies via `namo.paint.apply` (one
  undo step, items grouped per value, searches per value preferred over walking when the
  property is search-friendly); shows a legend in the output window (swatch, value,
  count) and stores the scheme with `paint.remember_scheme` for Legend Maker / Presets.
* **#77 Color Presets** `Color_Presets.pushbutton` (large, context: doc). Named presets in
  `team_root()\presets\colors\*.json` (property, value -> colour, ghost setting, other
  colour). Actions: Save last scheme as preset, Apply preset (search per value, paint,
  legend), Manage (rename/delete/export/import, open folder). Applying reports values
  with no matches.
* **#78 Trade Ghost** `Trade_Ghost.pushbutton` (large, title Trade\nGhost, context: doc).
  Choose focus trades (models grouped by `namo.trades.trade_of`, multi, remembered) or
  "Use current selection as focus"; everything else gets transparency (config default
  85%) and optional neutral grey via `paint.ghost`; second click while ghosted offers
  Change focus / Clear ghost (clear = reset those overrides only if Playground applied them:
  record ghosted items in session; otherwise full reset after confirm).
* **#79 Status Painter** `Status_Painter.pushbutton` (large, title Status\nPainter,
  context: doc). Construction status lives in a property (default custom tab
  'Playground > Status', configurable to any property). Actions: Paint by status (status ->
  colour map, editable, defaults: Installed green, In progress amber, Planned grey,
  On hold purple, Issue red, Not started untouched), Set status of selection (choose a
  status; merges into the custom tab; repaints), Legend. One undo step each.
* `Look.panel/Look_Tools.stack` (layout: Legend_Maker, Match_Appearance, Exploded_View)
  * **#83 Legend Maker** `Legend_Maker.pushbutton` (context: doc): renders the last
    scheme (`paint.last_scheme`) as a PNG legend with WPF (DrawingVisual +
    RenderTargetBitmap: title, swatches, labels, counts, theme-neutral white background
    for print) saved where the user chooses and shown in the output window
    (`output.print_image`); option "Also save a viewpoint 'Legend - <title>'" with the
    legend text as its comment. No scheme yet: info toast pointing at Color by Property.
  * **#103 Match Appearance** `Match_Appearance.pushbutton` (context: doc): source = first
    selected item (or pick one); reads colour/transparency (`paint.read_color`; note
    best-effort); then either applies to the rest of the selection (if 2+ selected) or
    enters a pick loop (`namo.picking.point` repeatedly; Esc ends) painting each clicked
    object (its object-level ancestor), each click one undo step; toast count at the end.
  * **#80 Exploded View** `Exploded_View.pushbutton` (context: selection): explodes the
    selected objects (or chosen models) away from their common centre by a factor
    (ask_number, default 1.5; mode: radial / vertical only / along X/Y), via permanent
    transforms in ONE transaction (`doc.Models.OverridePermanentTransform` per item with
    a translation `Transform3D`; grep the dump for constructors); remembers what it moved
    (session + doc store) so a second click offers Collapse (reset those transforms) or
    Explode more. Never touches source files.
* `Look.panel/View_Tools.stack` (layout: Reset_All_Overrides, Background)
  * **#56 Reset All Overrides** `Reset_All_Overrides.pushbutton` (title Reset Overrides,
    context: doc): choose what to reset (multi, remembered; default colours +
    transparency + hidden): permanent colours/transparency, temporary colours, hidden
    items, permanent transforms (warn: includes deliberate moves), required/frozen flags.
    One transaction. Toast lists what was reset.
  * **#118 Background** `Background.pushbutton` (context: doc): click cycles presets
    (White, Light gradient, Dark gradient, Black, Horizon) with `Document.
    SetPlainBackground / SetGraduatedBackground / SetHorizonBackground`; Shift+Click picks
    one from a list (with a custom colour pair option). Toast the preset name.
* **#119 Presentation Mode** `Presentation_Mode.toggle` (large toggle, title
  Presentation\nMode, title_on Exit\nPresentation): On hides the ribbon (AdWindows
  `ComponentManager.Ribbon`: study `tabhider.py`; minimise or collapse, whichever the
  dump supports cleanly), hides Navisworks dock panes if an API exists (else leaves them),
  maximises the main window, optionally switches background to the presentation preset;
  stores everything it changed in a session holder; Off restores exactly. Must be
  impossible to get stuck: Esc? (no key hook available) so also add a nobutton
  `Look.panel/Exit_Presentation.nobutton` with shortcut Ctrl+Alt+F11 that restores.
  (List the nobutton in the panel layout after Presentation_Mode.)

---------------------------------------------------------------------------------------

## G4 clash_setup_results: tab Coordinate, panels `Clash_Setup.panel`, `Clash_Results.panel`

Owns modules: `namo/clashmatrix.py`, `namo/clashtemplates.py`, `namo/clashrules.py`,
`namo/clashassign.py`, `namo/clashname.py`, `namo/clashheat.py`, `namo/revitlink.py`,
`namo/scanvsmodel.py`; companion pyRevit extension under `companions\`.
Reads clash data ONLY through `namo.clashdata` / `pynavis.clash` / `pynavis.clashtest`.

### Clash_Setup.panel  layout: Clash_Matrix, Clash_Templates, Scan_vs_Model

* **#22 Clash Matrix** `Clash_Matrix.pushbutton` (large, title Clash\nMatrix, context:
  doc). Workbook-driven test battery: sheet "Trades" (Trade, Selection set path or a
  `namo.rules.parse_cell` condition), sheet "Matrix" (trades across and down; a cell is
  blank = no test, `H` / `H 10mm` = hard with tolerance, `C 50mm` = clearance, `D` =
  duplicates). Actions: Write template (pre-filled with every selection set and the
  model files as trades), Build tests (creates "A vs B" tests named by a template,
  tolerance via `namo.units`, selections referencing the SETS when the API allows a
  selection-source reference (investigate `SelectionSourceCollection`,
  `SelectionSource`, `DocumentSelectionSets.CreateSelectionSource` / `Selection`
  members in the dump) so tests follow set changes, else explicit items with a note),
  skip/replace existing names, optional Run all. Report table of created tests.
* **#34 Clash Templates** `Clash_Templates.pushbutton` (large, title Clash\nTemplates,
  context: doc). Save chosen tests' definitions to a named template (`namo.templates`
  'clash_tests'): name, type, tolerance (stored in metres), selections as set references
  (names/paths) or search conditions, self-intersect, primitive types, merge composites.
  Apply a template in another project: resolves set names, lists missing ones, creates
  tests (clashtest.create + edits), optional run. Export/import template files.
* **#97 Scan vs Model** `Scan_vs_Model.pushbutton` (large, title Scan vs\nModel, context:
  multi-model). Choose scan models (auto-suggest models whose geometry primitive types
  include points / file extensions .rcp .rcs .e57 .pts) and design scope (other models or
  a set). Creates a clearance test with point primitives enabled on the scan side
  (`ClashSelection.PrimitiveTypes`, grep `PrimitiveTypes` enum) and a tolerance =
  largest deviation band (bands default 25/50/100 mm), runs it, then buckets results by
  distance band per design element, colours elements by worst band (`namo.paint`), and
  reports counts per band + top deviating elements (output). Note clearly in notes what
  needs in-app confirmation (point-cloud clash behaviour).

### Clash_Results.panel  layout: Clash_Namer, Status_Rules, Clash_Assigner, Clash_to_Viewpoints, Clash_Heatmap, Revit_Link (stack)

* **#24 Clash Namer** `Clash_Namer.pushbutton` (large, title Clash\nNamer, context:
  clash-results). Rename results and/or groups of chosen tests by template:
  `{test} {n:000} {grid} {level} {model_a} {model_b} {trade_a} {trade_b} {cat_a} {cat_b}
  {status} {distance}` (distance in doc units, tokens documented in the form); preview the
  first 25 before/after; apply per test with `TestsEditDisplayName` inside one
  transaction for up to a few thousand results; above a threshold (config, default
  3,000) use a single rebuild via a detached `test.CreateCopy()` with renamed copies and
  `TestsReplaceWithCopy` (study `pynavis/_clashapply.py` and `clash.apply_plan` and
  mirror their structure; keep groups). Toast "Renamed 1,240 clashes in 3 tests".
* **#32 Status Rules** `Status_Rules.pushbutton` (large, title Status\nRules, context:
  clash-results). Ordered rules (JSON per team via `namo.templates` 'clash_status_rules',
  plus an editor form): conditions on clash fields (distance < x, model/trade pair,
  categories, element property via item A/B, age in days, name/description contains,
  current status) -> new status (+ optional assignee/description note). Preview counts
  per rule (first match wins), apply via `pynavis.clashtest.set_status` and
  `namo.clashdata` edits, one undo step per test. Ships 3 example rules.
* **#30 Clash Assigner** `Clash_Assigner.pushbutton` (large, title Clash\nAssigner,
  context: clash-results). Assign groups (top-level) or ungrouped results to trades with
  ball-in-court: Auto mode uses a "who moves" priority list (config, default:
  Structure > Architecture > Mechanical (duct) > Plumbing > Electrical > Fire Protection;
  the LOWER priority trade of the pair moves) and `namo.trades`; Manual mode picks a trade
  for chosen groups. Writes AssignedTo (`clashdata.set_assigned`) and records the
  ball-in-court history (who/when/from/to) in the document database
  (`namo.docdb` via `namo.store` mode 'model', fallback local) so it travels with the
  NWF. Dashboard in the output window: open items per trade, oldest first, aging.
* **#33 Clash to Viewpoints** `Clash_to_Viewpoints.pushbutton` (large, title Clash to\n
  Viewpoints, context: clash-results). Chosen tests + statuses + "one per group or one per
  clash" -> saved viewpoints under "Clashes/<test>/<group>/<clash>" (folder template),
  camera from `clashdata.viewpoint(result)` (`TestsViewpointForResult`), comments with
  status, distance, items, grid/level; one transaction; skips existing names unless
  replacing. Cap with confirm above 500.
* **#35 Clash Heatmap** `Clash_Heatmap.pushbutton` (large, title Clash\nHeatmap,
  context: clash-results). Counts active clashes per element across chosen tests,
  colours elements by count band (`colors.sequential`, 5 bands, legend), optional ghost
  of the rest, top-20 hotspot table with element links; plus optional 3D density markers:
  clash centres binned into cells (default 2 m) drawn with `pynavis.overlay` as crosses
  sized by count with count labels (tag 'playground-heat'); second run clears/replaces.
* `Clash_Results.panel/Revit_Link.stack` (layout: Show_in_Revit, Show_from_Revit)
  * **#36 Show in Revit** `Show_in_Revit.pushbutton` (context: selection): reads Element
    IDs + UniqueIds + source Revit file names of the selected objects (`items.revit_ids`,
    `Model.SourceFileName`), writes `%APPDATA%\pyNavis\playground\revit-link\to-revit.json`
    ({version, sent, from: doc title, elements: [{file, element_id, unique_id}]}) and
    toasts "Sent 2 elements to Revit". Companion pyRevit extension
    `companions\PlaygroundLink.extension\Playground.tab\Navisworks.panel\`:
    **Show from Navisworks** pushbutton (reads to-revit.json, matches the open Revit
    document by file name, selects + `uidoc.ShowElements`, reports missing ids) and
    **Send to Navisworks** pushbutton (writes to-navisworks.json from the Revit selection:
    element ids, unique ids, file). Follow pyRevit conventions (script.py, bundle.yaml
    title/tooltip, `from pyrevit import revit, forms, script`), CPython-free IronPython 2.7
    compatible syntax for pyRevit's default engine (no f-strings, no print status, use
    forms.alert / forms.toast if present).
  * **Show from Revit** `Show_from_Revit.pushbutton` (context: doc): reads
    to-navisworks.json, finds the objects by Element ID within models whose source file
    matches (scoped `sets.find_first`/`sets.run` with the LcRevitData_Element category
    rule), selects + zooms, toasts found/missing.

---------------------------------------------------------------------------------------

## G5 models_quality: tab Project, panels `Models.panel`, `Quality.panel`, `Publish.panel`

Owns modules: `namo/modelmgmt.py`, `namo/sourcefiles.py` (pane logic), `namo/folderwatch.py`,
`namo/transforms.py`, `namo/health.py`, `namo/duplicates.py`, `namo/modelcompare.py`,
`namo/preflight.py`, `namo/publish.py`, `namo/wipe.py`, handlers `hk_stalecheck.py`,
`hk_folderwatch.py`, `hk_sessionstats.py`, `hk_transformpresets.py`, reports
`rep_health_check.py`, `rep_session_stats.py`, `rep_stale_files.py`, `rep_preflight.py`.

### Models.panel  layout: Batch_Append, Source_Files, Link_Navigator, Transform_Fixer, Folder_Watch, Stale_File_Alert

* **#47 Batch Append** `Batch_Append.pushbutton` (large, title Batch\nAppend). Source: a
  folder (recursive option, type filter: nwc nwd nwf rvt ifc dwg dgn fbx rcp... editable)
  or a manifest (txt/csv/xlsx: one path per row, optional order and trade columns).
  Preview list (`ui.choose`: file, size, modified, already appended?) with new files
  ticked; appends with `Document.TryAppendFile` per file under counted progress (cancel
  between files), collecting failures; or `AppendFiles` when all are fine (measure which
  is better and document). Toast "Appended 12 files, 1 failed" with the failure.
  Remembers the last folder/manifest.
* **#51 Source Files** `Source_Files.dockpane` (dock pane; title Source Files). Live list
  of appended models: visibility checkbox (hide/unhide the model root via
  `doc.Models.SetHidden` in a transaction), name, type, units, modified time and a stale
  marker (source newer than cache), item count (lazy). Buttons: Isolate, Show all,
  Select, Zoom, Open folder, Refresh changed (`Document.UpdateFiles()`), Remove
  (`Document.RemoveFile(index)` after confirm; index re-resolved at click time). Rebuild
  on `doc.Models.CollectionChanged` and active document change; all handlers wrapped and
  logged. Pane XAML uses theme-following defaults like the shipped Viewpoint Tracker plus
  DesignSystem brushes set from script.
* **#117 Link Navigator** `Link_Navigator.pushbutton` (large, title Link\nNavigator,
  context: selection). From the selected element to its model: info card (output window:
  file, source, created by, units, transform, file size/date, items) then actions
  (`forms.ask_options`): Select model, Isolate model, Hide model, Open folder, Refresh
  files, Remove model, Show in Source Files pane (`pynavis.panes.show(<pane bundle key>)`).
* **#55 Transform Fixer** `Transform_Fixer.pushbutton` (large, title Transform\nFixer,
  context: doc). Pick models; shows current units and transform (translation, rotation
  about Z in degrees, scale, decomposed from `Model.Transform`); form for translation
  X/Y/Z (`ask_length` style fields via `namo.ui` 'length'), rotation about Z with origin,
  or "Move by two points" (pick from, pick to via `namo.picking.points`). Applies with
  `doc.Models.SetModelUnitsAndTransform(model, units, transform, reflected)` (grep
  `Transform3D` builders/constructors in the dump) as one undo step. Presets per model
  file name (`namo.templates` 'transform_presets'): save current, apply, auto-apply when
  that file is appended (`hk_transformpresets`, off by default, toast when applied).
* **#50 Folder Watch** `Folder_Watch.toggle` (large toggle, title Folder\nWatch, title_on
  Watching). On: folders from config (Shift+Click config edits; default = folders of the
  appended NWCs); a `DispatcherTimer` (30 s, config) compares mtimes/sizes of watched
  model files (no FileSystemWatcher threads); when an appended file changes (stable for
  two polls), shows a small non-activating notification window (`namo.ui`) "3 models
  updated: Refresh now / Later / Show"; Refresh = `Document.UpdateFiles()`. Session
  holder keeps timer; `hk_folderwatch` re-arms on doc-opened when on, stops on
  app-closing; startup restores only if config says "remember on".
* **#49 Stale File Alert** `Stale_File_Alert.pushbutton` (large, title Stale\nFiles,
  context: doc, report: stale_files). For each model: cache file vs source file mtimes
  (`Model.FileName`, `Model.SourceFileName`, os.stat), missing sources, unreadable paths;
  output table (model, cache time, source time, age difference, status) + toast summary.
  `hk_stalecheck` (config "check on open", default off) does the same fast check on
  doc-opened and toasts only when something is stale.

### Quality.panel  layout: Model_Health_Check, Duplicate_Finder, Model_Compare, Preflight, Session_Stats

* **#48 Model Health Check** `Model_Health_Check.pushbutton` (large, title Health\nCheck,
  context: doc, report: health_check). Per model scorecard: units vs document units,
  origin offset (model bbox centre distance from origin; > 10 km warn (float precision),
  > 100 km fail), far-away outliers (objects whose centre is > 20x the model's median
  object distance from the model centre: sampled, listed with links), empty models,
  identity coverage (% of geometry objects with Element ID / IFC GlobalId: sampled),
  duplicate appends (same file twice), non-identity transforms, file age, item counts.
  Health score 0-100 per model. Output report (`htmlreport`-like cards in the output
  window via `output.print_html`) + xlsx/html export.
* **#54 Duplicate Finder** `Duplicate_Finder.pushbutton` (large, title Duplicate\nFinder,
  context: doc). Scope selection/models; candidate key = class + primitive count +
  bbox min/max rounded to a tolerance (default 1 mm in doc units); groups of size > 1;
  optional deep check (`namo.mesh` volume + centroid within tolerance); distinguishes
  same-model vs cross-model duplicates; output table with links + creates a selection
  set "Playground/Duplicates <date>" of all-but-first per group + selects them.
* **#53 Model Compare** `Model_Compare.pushbutton` (large, title Model\nCompare, context:
  doc). Mode A (two appended versions): choose Old and New models; mode B (snapshot):
  save a snapshot of a model now (keys, bbox, chosen-property hash) / compare the current
  model with a saved snapshot. Matching by Revit UniqueId -> IFC GlobalId -> Element ID ->
  InstanceGuid -> name+bbox fallback. Results: added, removed, changed (moved beyond
  tolerance, resized, or property hash changed; reasons listed), unchanged. Colours (new
  green, changed amber, removed red on the OLD model, unchanged ghosted) via
  `namo.paint`, selection sets "Compare/Added|Changed|Removed", output summary + xlsx.
  Progress + cancel + budget.
* **#107 Preflight** `Preflight.pushbutton` (large, context: doc, report: preflight).
  Profiles (`namo.templates` 'preflight', default profile shipped): checks with pass/
  warn/fail + detail: document saved, units consistent, expected models present (list
  in profile), no stale files, required selection sets exist, clash tests exist and were
  run after the newest model update (`ClashTest.LastRun` vs model file times), no
  "New" clashes over N, saved viewpoints present, no hidden items, no leftover
  overrides (best effort), section off, TimeLiner tasks attached (optional). Output
  checklist; NWD Publisher can run it first.
* **#75 Session Stats** `Session_Stats.pushbutton` (large, title Session\nStats,
  context: doc, report: session_stats). Per model: cache/source file sizes, items,
  geometry items, primitives (sum `Geometry.PrimitiveCount`, sampled above budget with
  extrapolation clearly marked), fragments, bbox size, units, load time (from
  `hk_sessionstats`, which stamps model-appended times in a session holder; doc-opened
  start time via the same handler if available, else "not recorded"). Output table +
  bar chart (primitives per model) + xlsx.

### Publish.panel  layout: NWD_Publisher, Model_Wipe

* **#52 NWD Publisher** `NWD_Publisher.pushbutton` (large, title NWD\nPublisher, context:
  doc). Profile: target folder, name template (`{project}_{file}_{date:%Y%m%d}_v{version:00}
  .nwd`, version auto-increments by scanning the folder), archive (move older versions
  into `Archive\`), publish properties (title, author, comments, copyright, expiry days,
  password? no), run Preflight first (block on fail unless overridden). Uses
  `pynavis.export.publish_nwd` or `save_nwd` (choice). Logs history (store). Toast + open
  folder option.
* **#108 Model Wipe** `Model_Wipe.pushbutton` (large, title Model\nWipe, context: doc;
  THE one alert-red icon in Playground). Choose what to purge (counts shown per option):
  saved viewpoints, selection sets, clash tests, comments on viewpoints, redlines (if an
  API path exists), appearance overrides, hidden state, permanent transforms, TimeLiner
  tasks, Playground data stored in the document (docdb). Second confirm naming exact counts.
  One transaction where the API allows; report what was removed and what could not be.

---------------------------------------------------------------------------------------

## G6 views: tab Views, panels `Viewpoints.panel`, `Capture.panel`, `Navigate.panel`

Owns modules: `namo/vpbatch.py`, `namo/vpexcel.py`, `namo/vpexport.py` (Navisworks
viewpoint XML + Playground package), `namo/levels.py`, `namo/camsync.py`, `namo/spotter.py`,
`namo/dxf.py` + `namo/sheetoverlay.py`, `namo/capture.py`, handler `hk_camsync.py`,
reports `rep_viewpoint_images.py`, `rep_batch_pdf.py`.

### Viewpoints.panel  layout: Batch_Viewpoints, Viewpoints_from_Excel, Export_Viewpoints, Viewpoint_Sync, Where_Am_I

* **#13 Batch Viewpoints** `Batch_Viewpoints.pushbutton` (large, title Batch\nViewpoints,
  context: doc). Generators: per level (grid levels: top-down plan at each level with a
  section at level + cut height (default 1.2 m) and optional floor clip, framed to the
  model extents on that level; or eye-level perspective), per grid intersection (plan
  zoom or eye-level looking along a chosen axis), per selection/search set (zoom to set;
  option to hide everything else while saving, restored after), per model. Folder and
  name templates (`namo.naming`); one transaction; progress; restores the user's view.
* **#18 Viewpoints from Excel** `Viewpoints_from_Excel.pushbutton` (large, title
  Viewpoints\nfrom Excel, context: doc). Export current viewpoints to a template workbook
  (Folder, Name, Eye X/Y/Z, Target X/Y/Z, Up X/Y/Z, Projection, FOV/Height, Comment) in
  document units; import creates or updates viewpoints by Folder+Name (camera via
  `namo.camera`), reports created/updated/skipped with row errors.
* **#15 Export Viewpoints** `Export_Viewpoints.pushbutton` (large, title Export\nViewpoints,
  context: viewpoints). Tree picker of saved viewpoints/folders (`namo.ui.choose` with
  folder paths, or a tree) -> Navisworks viewpoint exchange XML for ONLY the chosen ones
  (`<exchange><viewpoints><viewfolder><view><viewpoint><camera>...`; write it from your
  best knowledge of the nw-exchange schema: camera projection/near/far/aspect/height,
  position pos3f, rotation quaternion a b c d, comments; mark the exact schema as an
  in-app check: the user re-imports it with Navisworks' own Import Viewpoints) and/or a
  Playground package JSON (`.nvp.json`: folders, cameras, comments) for Viewpoint Sync.
* **#21 Viewpoint Sync** `Viewpoint_Sync.pushbutton` (large, title Viewpoint\nSync,
  context: doc). Copy viewpoint folders between files through a package: Export package
  (choose folders) / Import package (choose folders from the package, target folder,
  conflict policy: skip / replace / keep both); cameras + comments (+ clip planes when
  stored via `camera.clip_json`). Report table.
* **#106 Where Am I** `Where_Am_I.pushbutton` (large, title Where\nAm I, context: doc).
  One popup (`forms.alert(text, copy=text)`): current saved viewpoint (when the camera
  still matches it), camera eye in document units, look direction as compass bearing +
  pitch, nearest level and grid intersection (`Grids.ActiveSystem.ClosestIntersection`),
  projection + FOV, sectioning (planes/box and how many), models loaded (count, total
  objects), document units, file name, selection count.

### Capture.panel  layout: Viewpoints_to_Images, Batch_Image_Export, Batch_PDF

* **#16 Viewpoints to Images** `Viewpoints_to_Images.pushbutton` (large, title Viewpoints\n
  to Images, context: viewpoints, report: viewpoint_images). Choose viewpoints (all /
  folders / ticked), size preset (1280x720, 1920x1080, 3840x2160, custom), format PNG/JPG,
  filename template (`{folder}_{name}`, `{n:00} {name}`), output folder, optional
  overlay (ScenePlusOverlay); renders each via `namo.images.capture_saved` inside
  `images.ViewKeeper` with counted progress + cancel; writes an index.html contact sheet.
* **#73 Batch Image Export** `Batch_Image_Export.pushbutton` (large, title Batch\nImages,
  context: doc). One run, three sources (each optional): saved viewpoints, clash results
  (chosen tests/statuses, `images.clash`, capped with confirm), Playground issues (camera
  restore + capture, via `namo.issues` when available: guarded import). Folder layout
  Viewpoints\ Clashes\<test>\ Issues\ + one index.html.
* **#120 Batch PDF** `Batch_PDF.pushbutton` (large, title Batch\nPDF, context: viewpoints,
  report: batch_pdf). Ordered viewpoint set (folder order or hand-ordered list) -> one PDF
  handout via `namo.pdf`: title page (project, file, date, author from `namo.config`),
  optional contents page, one page per viewpoint (image, title, comments, page footer),
  A4/A3/Letter/Tabloid landscape, JPEG quality option. Opens the PDF when done (option).

### Navigate.panel  layout: Level_Sectioner, Level_Up, Level_Down, Camera_Sync, Spotter (stack), Sheet (stack)

* **#20 Level Sectioner** `Level_Sectioner.pushbutton` (large, title Level\nSectioner,
  context: doc). Levels from the active grid system (else from a level property found in
  the model: Element > Level / IFC storey, with elevations from object bboxes, marked
  approximate); choose a level; section top plane at level + cut height (config, default
  1.2 m) and optional bottom plane (slab view), via `namo.camera.horizontal_section`;
  optional switch to top plan view framed on the level. Remembers the current level.
* **Level Up / Level Down** `Level_Up.nobutton` (shortcut Alt+PgUp), `Level_Down.nobutton`
  (shortcut Alt+PgDn): move the section to the next level up/down; toast the level name.
* **#116 Camera Sync** `Camera_Sync.toggle` (large toggle, title Camera\nSync, title_on
  Syncing). Mirrors the camera live between two Navisworks sessions on this machine
  (e.g. two model versions side by side): each session writes its camera
  (`Viewpoint.GetCamera()` json + position/rotation, session id, sequence, time) to
  `%APPDATA%\pyNavis\playground\camsync\<pid>.json` on `CurrentViewpoint.Changed` (debounced 80 ms,
  direct subscription) and polls the newest OTHER session file with a 120 ms
  `DispatcherTimer`, applying newer cameras (`SetCamera` json on a copy, then CopyFrom)
  with an applying flag + sequence check to stop echo loops. Toasts "Syncing with
  Navisworks (PID 1234)" or "Waiting for another session". `hk_camsync` removes this
  session's file on app-closing.
* `Navigate.panel/Spotter.stack` (layout: Coordinate_Spotter, Clear_Spots)
  * **#81 Coordinate Spotter** `Coordinate_Spotter.pushbutton` (context: doc): repeated
    picks (`namo.picking.point` loop, which shows the banner prompt; Esc ends) dropping numbered markers
    with `pynavis.overlay` (cross + label "P3  X 12' 4" ..."); optional local origin
    (pick or enter) so coordinates are relative; at the end an output table (point,
    X, Y, Z in doc units and metres, snapped to what, object name) + CSV/xlsx export +
    clipboard. Markers stay until Clear Spots.
  * Clear Spots `Clear_Spots.pushbutton`: clears the spotter overlay tag.
* `Navigate.panel/Sheet.stack` (layout: Sheet_Overlay, Clear_Sheet)
  * **#82 Sheet Overlay** `Sheet_Overlay.pushbutton` (context: doc): overlays a 2D CAD
    sheet/plan (DXF: LINE, LWPOLYLINE, POLYLINE, ARC, CIRCLE tessellated, INSERT blocks
    expanded one level, TEXT/MTEXT as labels capped) onto the model at a chosen elevation
    (level picker or typed), placed by units scale + rotation + translation or by two
    reference points (DXF coordinates typed, model points picked); draws with
    `pynavis.overlay` (tag 'playground-sheet', cap 30,000 segments with a note); saves the
    placement per document so re-applying is one click. Pure DXF parser `namo/dxf.py`
    with tests (write sample DXFs in tests).
  * Clear Sheet `Clear_Sheet.pushbutton`: removes the overlay.

---------------------------------------------------------------------------------------

## G7 clash_reports: tab Coordinate, panel `Clash_Reports.panel`

Owns modules: `namo/clashreport.py` (shared row shaping), reports `rep_clash_excel.py`,
`rep_clash_html.py`, `rep_clash_matrix.py`, `rep_clash_delta.py`, `rep_clash_trends.py`,
`rep_per_trade.py`, handler `hk_clashhistory.py`. All data via `namo.clashdata`
(snapshot, history, compare, image).

`Clash_Reports.panel` layout: Clash_Excel_Report, Clash_Dashboard, Clash_Count_Matrix,
History (stack), Per_Trade_Reports

* **#25 Clash Excel Report** `Clash_Excel_Report.pushbutton` (large, title Clash\nExcel,
  context: clash-tests). Chosen tests (+ status filter) -> styled workbook: Summary sheet
  (test x status counts with status fills, totals, last run, tolerance), one sheet per
  test (row per clash: image thumbnail (optional, 160x90 via `images.clash`, capped with
  confirm, default on up to 300 per test), name, group, status (fill), distance in report
  units, grid, level, item A/B names, models, trades, categories, assigned, created,
  approved by, description, comments count), autofilter, frozen header, widths. Saved as
  a template-capable report.
* **#26 Clash Dashboard** `Clash_Dashboard.pushbutton` (large, title Clash\nDashboard,
  context: clash-tests, report: clash_html). Standalone HTML via `namo.htmlreport`: KPIs
  (total, new, active, reviewed, approved, resolved, oldest open), donut by status, bar by
  test, model-vs-model heatmap, by-level and by-grid bars, filterable table with
  thumbnails (optional), group view; opens in the default browser.
* **#27 Clash Count Matrix** `Clash_Count_Matrix.pushbutton` (large, title Count\nMatrix,
  context: clash-tests, report: clash_matrix). Trade-vs-trade (or model-vs-model) matrix
  of open (new+active+reviewed) and new counts across chosen tests; output window heatmap
  table (hand-built HTML using the window's CSS variables, fill intensity by count) +
  xlsx with dynamic fills.
* `Clash_Reports.panel/History.stack` (layout: Snapshot_Clashes, Clash_Delta, Clash_Trends)
  * **Snapshot** `Snapshot_Clashes.pushbutton` (context: clash-tests): records a labelled
    history snapshot of chosen tests (`clashdata.save_history`); `hk_clashhistory` does it
    automatically on doc-saved when enabled in config (default off; size cap 50,000
    results; quick).
  * **#28 Clash Delta** `Clash_Delta.pushbutton` (context: clash-tests, report:
    clash_delta): compare now vs a chosen snapshot (default the latest older than today):
    new / fixed / persisting / status changed per test; output summary + table + xlsx;
    "Select items of new clashes" action.
  * **#29 Clash Trends** `Clash_Trends.pushbutton` (context: clash-tests, report:
    clash_trends): line chart over snapshots (open vs resolved, per test or total) in the
    output window (`output.chart_line`) + burn-down table + xlsx/csv export.
* **#31 Per-Trade Reports** `Per_Trade_Reports.pushbutton` (large, title Per-Trade\n
  Reports, context: clash-tests, report: per_trade). Responsible trade per clash =
  AssignedTo when set, else rule (`namo.trades` of the moving side per the Clash Assigner
  priority list in `namo.config`/templates, else both trades). One workbook (and optional
  HTML) per trade into a chosen folder with only that trade's clashes; summary index;
  opens the folder.

---------------------------------------------------------------------------------------

## G8 issues_bcf: tab Coordinate, panels `Issues.panel`, `BCF.panel`

Owns modules: `namo/issues.py` (pure issue model: fields, statuses, priorities, numbering,
filters, aging, validation, BCF mapping), `namo/issuestore.py` (RecordStore 'issues' per
document, team/model modes), `namo/issueapi.py` (capture camera/selection/snapshot,
go-to), `namo/issueui.py` (pane + dialogs), `namo/bcf.py` (pure BCF 2.1/3.0 read/write),
handler `hk_issuepins.py`, reports `rep_coordination.py`, `rep_kpi_export.py`.

Issue record: id (number, display 'ISS-012' or template prefix), guid, title, type
(template name), status (Open, In progress, Resolved, Closed, Void), priority (Low,
Normal, High, Critical), trade, assignee, due, created/by, modified/by, description,
location (x,y,z doc units) + level/grid labels, camera (`namo.camera.capture`), elements
(`items.entries` + revit ids), images (paths under the store's media folder), comments
[{author, date, text, status_change}], source ({kind: 'clash'|'bcf'|'stamp'|'manual',
ref}), labels.

### Issues.panel  layout: Issues, Issue_Stamps, Issue_Pins, Meeting_Mode, Issue_Tools (stack), Coordination_Report, KPI_Export

* **#41 Issues** `Issues.dockpane` (dock pane, title Issues). The register: filter row
  (status, trade, assignee, text), sortable list (id, title, status chip, priority,
  trade, due with overdue marker), detail editor (all fields, comments thread, images
  strip), buttons: New from current view (captures camera, selection, snapshot image),
  Go to (camera + select elements), Update view (re-capture), Add comment, status
  change, Delete (confirm). Storage `namo.issuestore` (local / shared folder / in the
  model per `namo.config` data_mode). Refreshes on store changes made by other tools in
  this session (session event list) and on a manual Refresh (shared mode: other users).
  All handlers wrapped + logged.
* **#40 Issue Stamps** `Issue_Stamps.pulldown` (title Issue\nStamps, layout: RFI, Hold,
  Verify, Safety, Stamp_from_Template): each child picks a point (`namo.picking.point`), creates
  an issue from its template (type, default title pattern `{type} {n:000}`, priority,
  trade from the clicked object's model, due in N days), elements = clicked object,
  camera + snapshot, then toasts "RFI 012 created" and redraws pins if on.
* **#39 Issue Pins** `Issue_Pins.toggle` (large toggle, title Issue\nPins, title_on Hide\n
  Pins): draws every open issue with a location via `pynavis.overlay` (stem + diamond
  head sized by view-independent world size from model extents, label "#12 RFI: title"),
  tag 'playground-issues'; `hk_issuepins` redraws on doc-opened when on (session flag).
* **#43 Meeting Mode** `Meeting_Mode.pushbutton` (large, title Meeting\nMode, context:
  doc). Filter (status/trade/priority/due), then a modeless meeting window: issue N of M,
  details, big Prev/Next, status buttons, decision note (adds a comment "Meeting
  <date>: ..."), assignee/due edit, Take screenshot (adds image), Mark discussed; going
  to an issue restores its camera and selects elements. End meeting writes minutes
  (HTML via `namo.htmlreport` + xlsx: decisions, changes, new due dates) and opens them.
* `Issues.panel/Issue_Tools.stack` (layout: Issue_Templates, Clash_to_Issues)
  * **#42 Issue Templates** `Issue_Templates.pushbutton`: manage templates
    (`namo.templates` 'issue_templates', shared in team mode): type, prefix, title
    pattern, default priority, trade, assignee, due days, description boilerplate,
    labels, stamp label. Ships defaults: RFI, Hold, Verify, Safety, Clash, Design change.
  * **#45 Clash to Issues** `Clash_to_Issues.pushbutton` (context: clash-results):
    chosen tests, unit = top-level group or ungrouped clash, filter by status; fields by
    rules (trade from AssignedTo or `namo.trades` of the moving side, priority from
    distance bands, due from priority); camera = `clashdata.viewpoint`, snapshot =
    `images.clash`, elements both sides, source ref (test guid + result guid); skips
    clashes already converted (source ref lookup); toast counts.
* **#44 Coordination Report** `Coordination_Report.pushbutton` (large, title
  Coordination\nReport, context: doc, report: coordination). HTML + xlsx: KPIs (open,
  overdue, due this week, closed last 7 days), open by trade and by priority, aging
  buckets (`dates.age_bucket`), overdue list, per-trade sections with thumbnails,
  recently closed.
* **#46 KPI Export** `KPI_Export.pushbutton` (large, title KPI\nExport, context: doc,
  report: kpi_export). CSV (UTF-8 with BOM) + JSON tables shaped for Power BI into a
  folder (fixed folder option for scheduled refresh): issues, issue_comments,
  clash_results (from `clashdata.snapshot_all`), clash_tests, clash_history (from
  `clashdata.list_history`/`load_history`), with ISO dates, stable keys, a README.txt
  describing every column, and a `snapshot_time` column.

### BCF.panel  layout: BCF_Export, BCF_Import

* **#37 BCF Export** `BCF_Export.pushbutton` (large, title BCF\nExport, context: doc).
  Source: Playground issues (filtered) or clash groups/results directly. Writes BCF 2.1
  (default) or 3.0 `.bcfzip`: `bcf.version`, `project.bcfp`, per topic `markup.bcf`
  (Topic Guid, TopicType, TopicStatus, Title, Priority, Labels, CreationDate/Author,
  ModifiedDate, AssignedTo, DueDate, Description, Comments with Viewpoint refs),
  `viewpoint.bcfv` (PerspectiveCamera or OrthogonalCamera in METRES via `namo.camera.to_bcf`
  and `namo.units`, Components/Selection with IfcGuid from the IFC GlobalId property or
  `namo.ifcguid.from_revit_unique_id(UniqueId)`, AuthoringToolId = Element ID,
  OriginatingSystem), `snapshot.png`. Validate structure against the BCF XSDs from
  memory (element order matters).
* **#38 BCF Import** `BCF_Import.pushbutton` (large, title BCF\nImport, context: doc). Reads
  BCF 2.0/2.1/3.0 zips: topics -> issues (merge by Topic Guid: update status, comments,
  fields; new ones created), viewpoints -> saved viewpoints under "BCF/<file name>/<topic>"
  (camera from metres to document units), components -> elements resolved by IFC GlobalId
  (property search) / AuthoringToolId (Element ID) with progress; report created/updated/
  unresolved.

---------------------------------------------------------------------------------------

## G9 fourd_qty_field: tab Project, panels `4D.panel`, `Quantities.panel`, `Field.panel`

Owns modules: `namo/timeliner.py` (all Timeliner API access + pure schedule logic),
`namo/movie.py`, `namo/takeoff.py` (+ zones), `namo/cog.py`, `namo/qr.py` (pure QR
encoder), `namo/photopins.py`, `namo/checklists.py`, handler `hk_photopins.py`, reports
`rep_timeliner_export.py`, `rep_schedule_health.py`, `rep_quick_takeoff.py`,
`rep_zone_takeoff.py`. Timeliner: `DocumentTimeliner` via `doc.Timeliner` /
`DocumentTimeliner.TimelinerInstance(doc)` (grep the Timeliner dump: TaskAddCopy,
TasksCopyFrom, TaskEdit, TimelinerTask fields, TimelinerSelection, ProgressPercent,
SimulationTaskTypeName, PlannedStartDate etc.).

### 4D.panel  layout: TimeLiner_from_Excel, Auto_Attach, Progress_Painter, Movie_Maker, Schedule_Tools (stack)

* **#84 TimeLiner from Excel** `TimeLiner_from_Excel.pushbutton` (large, title TimeLiner\n
  from Excel, context: doc). Template export (Task ID, Parent ID, Name, Start, End, Actual
  start, Actual end, Task type (Construct/Demolish/Temporary...), Attach (selection set
  path or a `namo.rules.parse_cell` condition), Progress %, User1..3). Import: validates
  rows (dates via `namo.dates`, parents exist, no cycles), builds the hierarchy detached
  and commits once (`TasksCopyFrom` or `TaskAddCopy` per root with children: choose the
  measured-safe path), modes Replace all / Merge by Task ID (DisplayId), attaches sets
  (`TimelinerSelection`), reports created/updated/attach misses.
* **#85 Auto Attach** `Auto_Attach.pushbutton` (large, title Auto\nAttach, context: doc).
  Rules mapping tasks to model items: pattern on a task field (name/DisplayId/User1-10)
  with captures, e.g. `L(?P<level>\d+) (?P<trade>\w+)`, to a condition template
  `Element > Level = Level {level}` AND `trade = {trade}`; or a simple table (task name
  contains X -> set Y). Preview per task (matches, already attached), apply attaches
  explicitly found items (one undo step), report unmatched tasks.
* **#88 Progress Painter** `Progress_Painter.pushbutton` (large, title Progress\nPainter,
  context: doc). Set % complete for the selection (0-100) -> custom property
  'Playground > Progress' (merge), and updates `TimelinerTask.ProgressPercent` of tasks whose
  attachments contain those items (average of their items' progress); Paint mode colours
  by bands (0 grey, 1-49 amber, 50-99 blue, 100 green) with a legend.
* **#86 4D Movie Maker** `Movie_Maker.pushbutton` (large, title 4D Movie\nMaker, context:
  doc). Self-driven simulation (no Timeliner playback API needed): from tasks' planned
  (or actual) dates and types, for each frame date (range + step in days/weeks) compute
  each attached item's state (not started: hidden; in progress: green tint; complete:
  normal; demolish: red tint then hidden; temporary: yellow then hidden), apply hide +
  temporary colours in bulk, render with `namo.images.capture` (camera: current or a
  saved viewpoint), stamp the date on the frame (System.Drawing), save PNG frames + an
  HTML player (slider, play/pause) + MP4 when `ffmpeg` is on PATH (Popen; never
  required). Restores visibility/colours afterwards. Progress + cancel.
* `4D.panel/Schedule_Tools.stack` (layout: TimeLiner_Export, Schedule_Health)
  * **#87 TimeLiner Export** `TimeLiner_Export.pushbutton` (context: doc, report:
    timeliner_export): tasks -> styled xlsx (ID, WBS path, name, planned/actual dates,
    durations, type, progress, attached item count, status, User1..10) with outline
    indentation.
  * **#89 Schedule Health** `Schedule_Health.pushbutton` (context: doc, report:
    schedule_health): unattached tasks, missing/invalid dates, end before start, zero
    duration, items attached to more than one task, geometry objects not in any task
    (count + set "Playground/Not scheduled"), score; output report.

### Quantities.panel  layout: Quick_Takeoff, Zone_Takeoff, Takeoff_Templates, COG_Calculator

* **#90 Quick Takeoff** `Quick_Takeoff.pushbutton` (large, title Quick\nTakeoff, context:
  doc, report: quick_takeoff). Scope + group by (1-2 properties) + measures: count,
  length/area/volume/weight from properties (auto-detect common names across Revit
  'Element'/'Element Type'/'Revit Type', IFC Qto/BaseQuantities, with
  `namo.units.parse_quantity` on display strings and unit normalisation) and/or geometric
  (`namo.mesh` volume/area, budgeted, flagged "geometric"). Output table with subtotals,
  totals, units; xlsx export; save as template.
* **#91 Zone Takeoff** `Zone_Takeoff.pushbutton` (large, title Zone\nTakeoff, context:
  doc, report: zone_takeoff). Zones from: level bands (between consecutive grid levels),
  zone objects (rooms/areas/spaces or any set: their bboxes), or an XY grid tiling (grid
  lines or fixed spacing). Each object assigned by bbox centre (ties: largest overlap);
  pivot zone x group -> quantities; xlsx with one sheet per zone + pivot.
* **#93 Takeoff Templates** `Takeoff_Templates.pushbutton` (large, title Takeoff\n
  Templates): manage saved takeoff configurations (`namo.templates` 'quick_takeoff' and
  'zone_takeoff'): run, rename, delete, duplicate, export/import; running shows results
  like Quick Takeoff.
* **#92 COG Calculator** `COG_Calculator.pushbutton` (large, title COG\nCalculator,
  context: selection). Per object: closed-mesh volume + solid centroid (`namo.mesh`;
  open meshes fall back to bbox centre + bbox volume x fill factor, flagged), density from
  a material table (config: steel 7850, concrete 2400, aluminium 2700, timber 500, glass
  2500 kg/m3; matched by material/category properties) or an explicit weight property;
  combined centre of gravity + total weight; overlay marker at the COG (3-axis cross +
  label "COG  12.4 t"), output table (object, weight, centroid, method), copy coords.

### Field.panel  layout: QR_Tagger, Photo_Pins, Photo_Browser, Field_Checklists

* **#94 QR Tagger** `QR_Tagger.pushbutton` (large, title QR\nTagger, context: selection).
  Payload template (`{project}|{file}|{element_id}|{guid}` or a URL template
  `https://.../?guid={guid}`); pure QR encoder `namo/qr.py` (byte mode, ECC M/Q, versions
  1-10+, masks, format/version info; tests decode-free: compare against known vectors and
  validate structure; if `qrcode`/`segno` are importable under CPython use them to
  cross-check matrices) + `namo.png` output; writes one PNG per object, a printable
  HTML label sheet (QR + name + ID, A4 grid) and the payload into 'Playground > QR'.
* **#95 Photo Pins** `Photo_Pins.pushbutton` (large, title Photo\nPins, context: doc):
  pick a point -> choose photo file(s) -> caption -> pin stored (per-document
  RecordStore 'photo-pins': location, level/grid labels, linked object, camera, photo
  copies in the store's media folder, date taken from file or EXIF DateTimeOriginal when
  cheap) and drawn with `pynavis.overlay` (tag 'playground-photos'); `hk_photopins` redraws
  on doc-opened when pins are shown.
* **Photo Browser** `Photo_Browser.pushbutton` (large, title Photo\nBrowser, context:
  doc): window with thumbnails grouped by area (level / grid / zone), filter, Go to (camera
  + select), open photo, delete pin; export an HTML photo report.
* **#96 Field Checklists** `Field_Checklists.pushbutton` (large, title Field\nChecklists,
  context: viewpoints). Checklist templates (team: `namo.templates` 'checklists'; ships
  QA and safety examples) attached to saved viewpoints (location context); a checklist
  window for the current/selected viewpoint: items with Pass/Fail/NA + note, inspector,
  date, sign-off; progress per viewpoint stored per document (RecordStore 'checklists');
  Next/Prev viewpoint; report (HTML + xlsx) with completion % and failures.

---------------------------------------------------------------------------------------

## G10 exchange_reports: tab Project panel `Exchange.panel` + tab Dev panel `Reports.panel`

Owns modules: `namo/meshexport.py` (OBJ/MTL, binary STL, glTF 2.0 .glb, DXF 3DFACE; pure
writers + API collection), `namo/ifc.py` (pure IFC4 STEP writer), `namo/ifcexport.py`
(API collection + class mapping), `namo/reportrunner.py`, `namo/schedule.py`
(Windows Task Scheduler + mail).

### Exchange.panel  layout: Geometry_Exporter, IFC_Exporter

* **#72 Geometry Exporter** `Geometry_Exporter.pushbutton` (large, title Geometry\n
  Exporter, context: selection). Selected objects -> triangles (`namo.mesh.item_triangles`
  per item, budget per item and total, progress + cancel, skipped items listed) ->
  formats: glTF binary (.glb: one node+mesh per object, materials from item colours,
  metres, Y-up conversion, `extras` with chosen properties), OBJ+MTL (groups per object,
  colours), binary STL, DXF 3DFACE (layers per model or category, true colour; opens in
  AutoCAD, the DWG path). Option: shift to local origin (offset written to a sidecar
  .txt). Pure writers tested (glb parsed back: JSON chunk + buffer lengths; OBJ/STL/DXF
  parsed back).
* **#71 IFC Exporter** `IFC_Exporter.pushbutton` (large, title IFC\nExporter, context:
  selection). Selected objects -> IFC4 Reference View flavoured STEP: IfcProject (units
  from the document), IfcSite, IfcBuilding, IfcBuildingStorey per level (grid levels or
  Level property), elements mapped by Revit/IFC category to IFC classes (Walls->IfcWall,
  Floors->IfcSlab, Ducts->IfcDuctSegment, Pipes->IfcPipeSegment, Structural
  Framing->IfcBeam, Columns->IfcColumn, Doors->IfcDoor, Windows->IfcWindow, Cable Trays->
  IfcCableCarrierSegment ... else IfcBuildingElementProxy), geometry as
  IfcTriangulatedFaceSet (IfcCartesianPointList3D) under IfcShapeRepresentation 'Body'
  'Tessellation' with local placements, colours via IfcStyledItem/IfcSurfaceStyle,
  GlobalId from the IFC GlobalId property or `namo.ifcguid` from UniqueId/InstanceGuid,
  property sets per Navisworks property category (IfcPropertySingleValue with IfcLabel/
  IfcReal/IfcInteger/IfcBoolean), IfcRelContainedInSpatialStructure,
  IfcRelDefinesByProperties, IfcRelAggregates. Pure writer `namo/ifc.py` with tests
  (header, entity numbering, references resolve, string escaping per ISO 10303-21 incl.
  \X2\ for non-ASCII; if `ifcopenshell` imports under CPython, open the file with it).

### Reports.panel (tab Dev)  layout: Report_Templates, Scheduled_Reports

* **#69 Report Templates** `Report_Templates.pushbutton` (large, title Report\nTemplates,
  context: doc). Lists every saved template of every report in `namo.reports.REGISTRY`
  (via each report's `namo.templates` tool id = report id) plus "New template from
  defaults" (form generated from `default_config()` keys: folder, name template and
  simple typed fields; complex fields edited as JSON with validation); Run selected
  (interactive=False, progress, toast with result + open), Edit, Duplicate, Delete,
  Export/Import. Must work with reports that are not built yet (shows them disabled).
* **#70 Scheduled Reports** `Scheduled_Reports.pushbutton` (large, title Scheduled\n
  Reports). Creates Windows scheduled tasks (`schtasks.exe` via Popen, current user, no
  admin) that run the pyNavis headless runner: `%APPDATA%\pyNavis\cli\pynavis.exe run
  <Playground runner script> <model path> --timeout N -- --templates "<id>:<name>;..."
  --mail <profile>` daily/weekly at a time. Ship the runner script inside the bundle
  (`scheduled_runner.py`; checks `__runner__`, loads templates, runs reports
  interactive=False, writes a run log, then mails results via SMTP (smtplib under
  IronPython: verify availability in the harness) or copies them to a share). Mail
  profile: server, port, TLS, from, to list; password stored with Windows DPAPI
  (`System.Security.Cryptography.ProtectedData`, CurrentUser) in the data root, never
  plain text. List/Run now/Delete tasks (only tasks in a 'Playground' task folder). Detect a
  missing `pynavis.exe` and explain (needs pyNavis with the runner). Never run a task
  yourself during development; test command-line building purely.

---------------------------------------------------------------------------------------

## G11 dev_team: tab Dev, panels `Automate.panel`, `Build.panel`, `Team.panel`, `Tools.panel`

Owns modules: `namo/ribbon.py` (enumerate pyNavis bundles via
`PyNavis.Runtime.RuntimeHost.Extensions` and native ribbon commands via AdWindows
`ComponentManager.Ribbon` tabs/panels/items; run a pyNavis bundle deferred with
`ScriptExecutor.Run(model)` after the current run releases the RunGate (Dispatcher
deferral; investigate `PyNavis.Runtime.Execution.RunGate` public members in
`<pyNavis checkout>\src\PyNavis.Runtime`), execute a native ribbon item via its command
handler), `namo/palette.py`, `namo/macros.py`, `namo/buttonmaker.py`, `namo/editor.py`,
`namo/hotkeys.py`, `namo/extmanager.py`, `namo/teamsync.py`, `namo/usage.py`,
`namo/doctor.py`, `namo/converter.py`, handlers `hk_macro.py`, `hk_usage.py`,
`hk_teamsync.py`.

### Automate.panel  layout: Command_Palette, Macro_Record, Macros

* **#100 Command Palette** `Command_Palette.pushbutton` (large, title Command\nPalette,
  shortcut Ctrl+Shift+P). Keyboard-first modal window: search box + ranked list
  (`namo.textmatch`) over: every pyNavis/Playground button (title, tab > panel, tooltip,
  shortcut), native Navisworks ribbon commands (tab > panel > label), saved viewpoints
  ("Go to view: ..."), selection sets ("Select set: ..."), recently used first (MRU in
  the global store). Enter runs after the window closes: pyNavis bundles deferred through
  `namo.ribbon`, native commands through their ribbon command handler, viewpoints/sets
  directly. Up/Down, PgUp/PgDn, Esc. Shows the shortcut beside each command.
* **#99 Macro Recorder** `Macro_Record.toggle` (large toggle, title Record\nMacro, title_on
  Stop\nRecording) + `Macros.pulldown` (title Macros, layout: Play_Macro, Manage_Macros,
  Macro_to_Button). Recording: `hk_macro` appends each pyNavis command run
  (`__event__['command']` bundle key + title + time gap) while recording is on (session
  flag), ignoring the recorder's own buttons; on stop, name the macro (team store
  'macros'). Play: steps run in order via `namo.ribbon` (each after the previous
  releases the RunGate; dialogs inside steps still ask the user: say so in the tooltip),
  with optional pause steps and a Stop on error setting. Manage: rename, edit steps
  (reorder/delete/insert a wait or a confirm step), delete, export/import. Macro to
  Button: generates a pushbutton in the user tools extension (see Button Maker) whose
  script plays the macro.
* Native commands cannot be recorded (no event); say so in Manage.

### Build.panel  layout: Button_Maker, Script_Editor, Hotkey_Manager

* **#109 Button Maker** `Button_Maker.pushbutton` (large, title Button\nMaker). Wizard
  (`namo.ui.form`): script (.py file, or a template: selection tool / report /
  toggle), target user extension `%APPDATA%\pyNavis\extensions\MyTools.extension` (the
  installed pyNavis scans that root automatically; create extension.yaml + tab/panel
  with layout lists as needed; existing tab/panel choosable), title, tooltip, optional
  shortcut (validated with the pyNavis chord grammar; conflicts checked against every
  bundle via `namo.ribbon`), icon: generated (2 letters or a simple glyph on the accent
  colour, rendered with WPF to all four sizes/themes) or a chosen PNG; writes the bundle,
  updates layout lists, then `pynavis.script.reload_pynavis()` and toasts where it is.
* **#110 Script Editor** `Script_Editor.pushbutton` (large, title Script\nEditor).
  Modeless editor window (keyboard interop): left, the bundles of user-writable
  extensions (MyTools, Playground dev root) as a tree; right, a code editor (monospace
  TextBox with line numbers gutter, tab = 4 spaces, auto-indent, Ctrl+S save, Ctrl+F
  find, Ctrl+G go to line, F5 run), completion popup on Ctrl+Space and after '.'
  (python keywords, builtins, identifiers in the file, `pynavis` module members via
  dir(), Navisworks API type members via reflection on loaded `Autodesk.Navisworks.Api`
  types with a small cache), syntax check on save (`compile`, error line highlighted in
  the gutter), Run = save then run that bundle (deferred via `namo.ribbon`).
* **#111 Hotkey Manager** `Hotkey_Manager.pushbutton` (large, title Hotkey\nManager). One
  list of every command (pyNavis/Playground bundles with current binding from config.json
  `shortcuts.bindings` and author default; native ribbon commands). Assign/clear chords
  (validated: grammar, Ctrl-or-Alt rule unless allowBareKeys, conflicts). pyNavis
  bundles: write config.json bindings (atomic JSON edit preserving every other key and
  formatting as pyNavis writes it). Native commands: generate a `.nobutton` bundle in
  `MyTools.extension\MyTools.tab\Hotkeys.panel\` whose script runs that ribbon command,
  with `shortcut:` in its bundle.yaml (the panel also gets one visible pushbutton
  "Hotkeys" that opens Hotkey Manager, so it is never an empty panel). Then Reload.

### Team.panel  layout: Extension_Manager, Team_Sync, Usage_Analytics, Team_Tools (stack)

* **#122 Extension Manager** `Extension_Manager.pushbutton` (large, title Extension\n
  Manager). Registry = JSON (URL or file path in config; default: a file in
  `team_root()` if present, else a placeholder URL that is expected to fail gracefully)
  listing extensions {name, description, author, version, homepage, download (zip URL)}.
  Lists available vs installed (scan `%APPDATA%\pyNavis\extensions` + config roots),
  Install (download via .NET WebClient/HttpClient with TLS 1.2, verify optional sha256,
  extract to `%APPDATA%\pyNavis\extensions\<name>.extension`, Reload), Update (version
  compare), Uninstall (move to `%APPDATA%\pyNavis\playground\trash\` with timestamp), Open folder.
  Never touches the pyNavis or Playground extensions themselves.
* **#125 Team Sync** `Team_Sync.pushbutton` (large, title Team\nSync). Team folder (UNC
  path or a local clone folder) with a `playground-team\` layout: config (trades, trade
  rules, project info), templates\*.json, presets\, libraries\, rules\, shortcuts.json
  (pyNavis bindings), extensions.json (roots). Pull: diff summary (added/changed/
  removed per area) then copy into the local data root with a backup folder; Push (BIM
  manager): export local content to the team folder. `hk_teamsync` on startup: if
  "auto pull" is on, compare a version stamp and toast "Team settings updated" (fast,
  never blocks: just stat files).
* **#112 Usage Analytics** `Usage_Analytics.pushbutton` (large, title Usage\nAnalytics).
  Opt-in (first click explains and asks; config flag). `hk_usage` (before-command stamps
  time; after-command appends {time, user, machine, bundle key, title, duration ms} to a
  monthly CSV in the data root, or a per-user file in the team root in shared mode).
  Report: top tools, per day line chart, per user, never-used tools (all bundles from
  `namo.ribbon` minus used), export xlsx. No document names recorded.
* `Team.panel/Team_Tools.stack` (layout: Environment_Doctor, Playground_Settings)
  * **#121 Environment Doctor** `Environment_Doctor.pushbutton`: pass/warn/fail report
    in the output window + "Copy report": Navisworks product/year/API version, pyNavis
    version and runtime path, engines (IronPython version; CPython configured? found?),
    extension roots and every extension (`RuntimeHost.Extensions`: name, folder, tab/
    button counts, problems), *.lib folders, hooks, startup scripts, shortcut count and
    conflicts (scan bundle models), panel slots (`pynavis.panes.slot_count`) and claims,
    WebView2 runtime present, runner `pynavis.exe` present, other add-ins loaded
    (`Application.Plugins` records: name, developer, version; duplicate pyNavis loaders),
    config.json parse, recent ERROR lines in `%APPDATA%\pyNavis\logs\pyNavis.log` (last
    session, capped), writable data folders, overlay/pick plugins available.
  * **Playground Settings** `Playground_Settings.pushbutton` (title Playground Settings): `namo.ui.form`
    over `namo.config`: user name, project name/number, company, data mode (local /
    shared folder / inside the model) + shared folder, trades list, trade rules (one per
    line `regex = Trade`), report units, date format. Validates the shared folder.

### Tools.panel  layout: Unit_Converter

* **#113 Unit Converter** `Unit_Converter.pushbutton` (large, title Unit\nConverter). A
  small calculator window: one input ("12' 6\" to mm", "250 sqft in m2", "3.5 m3 cuyd",
  "1200 kg lb", or a bare value + from/to dropdowns), live result as you type
  (`namo.units.parse_conversion`), copy button, history of the last 10, and "Insert
  document units" shortcut. Keyboard: Enter copies the result.
