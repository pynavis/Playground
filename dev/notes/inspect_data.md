# G2 inspect_data: Inspect and Data panels (tab Model)

Verified headlessly only (CPython 3.11 pytest, IronPython 3.4 tests and WPF smoke
builds, check.py, the real pyNavis BundleParser). Nothing here has run inside
Navisworks yet. Icons: `dev/notes/inspect_data-icons.png`.

## 1. The tools

Inspect panel (layout: What_Is_It, Properties_Plus, Selection_HUD, Inspect_Tools)

* **What Is It** (Ctrl+Alt+I): one output-window card for the selected item (or the item
  you click when nothing is selected): name, class, Revit category/family/type, element
  link, source file and path, tree path with a link per ancestor, Element ID, UniqueId,
  IFC GlobalId (marked when derived from the UniqueId), InstanceGuid, model index and
  PathId, box min/max/centre/size in document units and metres, geometry (items,
  primitives, fragments, types, solid), original and active colour swatches and
  transparency, transform and override flags, hidden/required/frozen, then every property
  tab as a collapsible list with counts. A plain-text summary goes to the clipboard.
* **Properties Plus**: modeless window following the selection live (200 ms debounce).
  Pinned properties summarised over the selection ("Varies (N values)" when they differ;
  picking a row shows the most common values on a line underneath), plus a filterable
  "This item" list. Copy value, Select items with this value (native search where exact,
  confirmed in Python), Pin, Unpin. Pins are remembered.
* **Selection HUD** (toggle, Shift+Click: property to sum): small borderless,
  non-activating readout at the bottom left of the Navisworks window: item and object
  counts, models, top three categories, an optional summed property. Re-anchors every
  second; reads the first 2,000 selected items for the details and says so.
* **Copy IDs** (Shift+Click: columns): one tab-separated row per selected element (name,
  Element ID, UniqueId, IFC GlobalId, InstanceGuid, source file, tree path) with a header.
* **Open in Explorer**: the selected item's source file or cache file (asks when both
  exist, warns which path is gone), or the document's own file with nothing selected.

Data panel (layout: Property_Explorer, Count_by_Property, Property_Exporter,
Data_Validator, Write_Data, Data_Tools, Property_Labels)

* **Property Explorer**: scans a scope (selection / visible / whole model; objects or
  geometry items; budget 200,000, sampling reported) once, then three linked, filterable
  lists: categories (items), properties (items, distinct values), values (count, share).
  Select items (within the scan), Create search set (live search for text, whole-number
  and yes/no values, a fixed set otherwise; the toast says which), Copy, Export the index
  to Excel, Rescan. The last scan per document is cached for the session.
* **Count by Property** (report `count_by_property`): one property, or two for a
  two-level pivot, over a scope; output-window table with shares, top 20 bar chart, then
  "Select a group". Optional Excel workbook.
* **Property Exporter** (report `property_export`): tick properties (pre-ticked from the
  last run or a named template), rows per object or geometry item, identity columns, Excel
  (styled, numbers as numbers, quantity units in the headers) or CSV, optional open.
* **Data Validator** (report `data_validation`, Shift+Click: open folder / check files /
  restore starter): JSON rule files in `<team root>\rules\validation` (a documented
  starter file is written on first use). Per-rule summary with pass-rate bars, failures
  with element links (first 500), Excel export of every failure, optional selection set
  per failing rule in a "Validation" folder (replaced on re-run).
* **Write Data** pulldown:
  * **Bulk Property Writer**: up to 10 "Name = Value" lines (types inferred) into a custom
    tab on the selection (merged, or replace the tab), or from Excel/CSV: key column
    (Element ID, GUID, or Category > Property) matched in a scope, preview (matched, not
    found, ambiguous, repeated keys), one undo step, unmatched rows saved beside the source
    as "<name> - unmatched.xlsx".
  * **Find and Replace**: text or regex (match case, whole value) in every property or one;
    preview of every change; native values go to the "Playground Corrected" tab as
    "<Category> - <Property>", custom-tab values are edited in place.
  * **Property Mapper**: profiles (team-shareable templates, JSON import/export) written as
    one line per field: `System: Element > System Name | IFC > SystemName | Item > Layer`,
    `~ /regex/` to extract, `~ /regex/replacement/` to rewrite, `Field [ARCH*.rvt]: ...` per
    model, `tab: Name`. Coverage per field and model before writing the tab (default
    Standard).
  * **External Data Link**: links saved with the document's Playground data (namo.store
    'data-links'): spreadsheet, sheet, key, columns, tab. New link, Refresh all, Refresh,
    Remove (optionally strip the tab), Select unmatched (objects with a key but no row).
    Shows last refresh, file time and whether the file changed.
* **Model Tree Export** (report `model_tree`): the tree to depth N (default 4), a sheet per
  model plus a summary: depth, one column per level, indented name, class, descendants,
  geometry items, hidden.
* **Clear Labels**: removes the Property Labels labels.
* **Property Labels**: a chosen property's value above each selected object (overlay
  label on a short leader from the box top centre), capped at 500 with a note.

Modules: `namo/propindex.py` (scopes, fast VariantData reading, the index, pivots,
model-wide value search, session cache), `inspect.py`, `hud.py`, `validator.py`,
`propwrite.py`, `insp_propsplus.py` (Properties Plus window), `data_explorer.py`
(Explorer window), `data_write.py` (Write Data dialogs), `data_labels.py`,
`data_common.py` (progress stages, default file paths, scope fields), reports
`rep_count_by_property.py`, `rep_property_export.py`, `rep_model_tree.py`,
`rep_data_validation.py`. Tests: `dev/tests/test_{propindex,inspect,hud,validator,
propwrite,data_common,data_explorer,data_labels,data_write,insp_propsplus,
rep_count_by_property,rep_property_export,rep_model_tree,rep_data_validation}.py`,
smoke `dev/tests/smoke_{data_explorer,insp_propsplus,hud}.py`. `test_propindex.py`
carries a typed VariantData fake layer other agents can reuse (`import test_propindex as pf`).

## 2. In-app checks (in this order; each says what to look for)

Use a federated Revit-based model (NWC/NWD) with ducts, pipes, walls and doors.

1. **Ribbon**: Model tab shows Inspect (4 items) and Data (7 items) with icons in
   light and dark; Write Data opens a 4-item menu; Ctrl+Alt+I runs What Is It.
2. **Property value types (the key assumption)**: select one duct, open Properties Plus,
   look at "This item": a Length the Revit Properties call 3000 mm must read `3,000 mm` in a
   millimetre document (`9' 10 1/8"` in a feet one). If it reads 0.003, 9,843 or a bare
   number, quantities are not stored in SI and `propindex.quantity_value` needs the real
   factor: report what you see. Check an Area, a Volume and an angle (Slope) the same
   way, a date property, and a yes/no property (shows Yes/No).
3. **What Is It**: with a duct selected, compare Element ID, UniqueId, category, family,
   type with the Revit properties; click an ancestor in the tree path and the element
   link (each selects that node); size in document units and metres matches a measure.
   Override the duct's colour (Appearance Profiler or Override Colour) and run again:
   report whether "Active colour" shows the override (read-back is unverified). Hide its
   parent in the Selection Tree and select the duct: Hidden reads "By a parent". Deselect
   everything and press Ctrl+Alt+I: the pick cursor appears; Esc cancels silently;
   clicking empty sky toasts "Nothing under that point". Paste the clipboard into Notepad.
4. **Properties Plus**: open it, select walls, then ducts, then nothing: the window
   follows within a moment, never steals keyboard focus from the model while you click
   in the view. Pin properties through the dialog; pick a "Varies" row and read the line
   under it. "Select items with this value" on a text value (fast) and on a Length value
   (progress window, model read in Python): both select the right items. Open a second
   document (File > Open) and back: it still follows. Close the window: the pyNavis log
   shows no errors afterwards when you change the selection. Click the button twice: the
   second click brings the window forward.
5. **Selection HUD**: toggle on: it appears bottom-left above the status bar, the toggle
   icon changes, typing shortcuts still reach Navisworks. Move and resize the Navisworks
   window: the HUD follows within a second. Minimize and restore. Select 10,000+ items:
   "Details from the first 2,000 items" shows. Shift+Click, choose Element > Length: the
   HUD sums it with a unit. At 125 or 150 percent Windows scaling, check its position.
   Toggle off: it disappears. After Reload, toggle state and HUD agree (click twice if
   not, and report).
6. **Copy IDs**: paste into Excel: one row per element with the header; Shift+Click,
   untick columns, run again; a 5,000+ element selection shows a progress window.
7. **Open in Explorer**: with an element from an appended NWC whose RVT still exists: it
   asks Source or Cache file; rename the RVT away: it opens the cache file and warns the
   source is gone. Nothing selected: shows the NWF/NWD.
8. **Property Explorer**: scan the whole model (objects). Note the seconds it takes for
   your object count (target: under 30 s for 50,000 objects). Click through categories,
   properties, values; filter each list. Select items for a value; Create search set for
   Element > Category = Ducts (a live search set appears under "Property Explorer" in the
   Sets window and matches the ducts); Create search set for a Length value (a fixed set,
   and the toast says why); Copy; Export to Excel (check the default folder is the
   document's folder); Rescan with Visible items. Close and click again: it reopens
   instantly from the cache. Write a property with Bulk Property Writer, click Property
   Explorer again: it asks to rescan (the cache was invalidated).
9. **Count by Property**: Element > Category over the whole model: table, shares, chart;
   pick a group in "Select a group": those items are selected. Two levels (Category then
   Level). Tick Excel and check the workbook (Counts, Totals sheets).
10. **Property Exporter**: select elements, tick a few properties including a Length,
    save as template "Test"; check the xlsx (frozen header, filter, numbers as numbers,
    "(mm)" in the Length header) and the CSV in Excel. Run again: "Test" is offered.
11. **Data Validator**: first run writes `Playground starter rules.json` into
    `%APPDATA%\pyNavis\playground\rules\validation` (or the team folder). Run on the whole model:
    summary bars, failures with element links that select. Tick Excel and selection sets:
    sets appear in a "Validation" folder; run again: the sets are replaced, not doubled.
    Break a rule file (delete a comma), Shift+Click > Check the rule files: the output
    lists the file, line number and the line itself.
12. **Bulk Property Writer**: Write to selection `Status = Open` and `Phase = 2`: a Playground
    tab appears with Phase as a number. Write `Owner = MEP` again with merge: Status and
    Phase stay. Then ONE Ctrl+Z must undo the whole write (COM writes inside one .NET
    transaction is pynavis' unverified assumption: report how many undo steps it takes).
    From Excel: a sheet with an "Element ID" column and two value columns, including one
    id that is not in the model: the preview shows matched/not found; after writing, an
    "<name> - unmatched.xlsx" sits beside the source.
13. **Find and Replace**: replace text in Element > Mark: the preview shows tab "Playground
    Corrected" and property "Element - Mark"; after Apply the tab holds the new values.
    Replace in a value inside the Playground tab from step 12: the preview must show tab
    "Playground" (edited in place). If it shows "Playground Corrected" instead, custom-tab
    detection (`PropertyCategory.IsEditable`, internal name `LcOaPropOverrideCat`) is wrong:
    report the custom tab's PropertyCategory.Name and IsEditable from the console.
14. **Property Mapper**: the first click opens the profile editor with the example; save
    it, run it: the coverage preview per model and field; write: a Standard tab appears.
    Add `Level [ARCH*.rvt]: Element > Base Constraint` and check the override applies to
    that model only. Export the profiles, delete one, import it back.
15. **External Data Link**: New link from a spreadsheet keyed on Element ID; refresh: the
    tab appears; edit and save the spreadsheet: the State column says the file changed;
    Refresh all; Select unmatched; Remove and strip the tab. With Playground data mode
    "model", the links travel with the NWF after saving it.
16. **Model Tree Export**: depth 4: the counts on the model rows match the Selection Tree
    (spot check one level's children count), names are indented in the Name column.
17. **Property Labels**: select 20 ducts, label with System Name: a leader and a label
    above each, following orbit and zoom; select 600 objects: 500 labels and a warning
    toast. Clear Labels removes them all; label again, click Reload, Clear Labels: they
    still clear.
18. **Save dialogs**: every save dialog opens in the document's folder with the default
    name filled in (the full path is passed as the dialog's file name: unverified).

## 3. Assumptions recorded (decided without an answer)

* DoubleLength / Area / Volume / Angle values arrive in SI (metres, m2, m3, radians); they
  are shown in Playground report units with the unit symbol (check 2 confirms or refutes).
* Properties Plus: the "tooltip of the first values" became a line under the pinned list
  that follows the picked row (the design rules ban hover-only information, and
  `ui.Table` has no per-row tooltips).
* Bulk Property Writer: the "up to 10 name/value rows" are a 10-line `Name = Value`
  text box (types inferred, quotes force text), validated live.
* Data links refresh against every object in the model, replace the link's whole tab on
  the matched objects, and do not clear the tab from objects that stop matching (Remove
  with strip does). Property Mapper also replaces its tab, only on items that map at
  least one field.
* Excel dates read through `pynavis.xl` arrive as serial numbers and are written as
  numbers.
* The Explorer keeps at most 10,000 distinct values per property (the rest are counted
  as "(other values)", and the property is marked capped), to bound memory on huge scans.

## 4. Requests for shared modules (not edited; worked around locally)

1. `namo.reports.output_path` (F2): honour an explicit `config['path']` so every report
   accepts the file the user picked. Exact fix, first lines of `output_path`:
   ```python
   explicit = str((config or {}).get('path') or '').strip()
   if explicit:
       paths.ensure_dir(os.path.dirname(explicit) or '.')
       return explicit
   ```
   Workaround: my four `rep_*` modules read `config['path']` first themselves.
2. `namo.ui.Table` (F3): optional per-row tooltip (`row['tip']` bound as the row's
   ToolTip) for read-only detail; Properties Plus would use it beside its detail line.
3. Cross-module convention for the README: any tool that writes custom properties should
   call `namo.propindex.invalidate()` afterwards (my writers do), so Property Explorer's
   cached scan never shows stale values.
4. For pyNavis itself (read-only here, noted for the lead): `pynavis.props._is_double_kind`
   scans `dir(variant)` on every value, which is slow for bulk reads; `VariantData`
   has `DataType`, `IsAnyDouble` and `ToAnyDouble`. Playground reads through
   `namo.propindex.coerce` instead.

## Refit pass

Second pass after the first field click (2026-10-05). Verified headlessly only; nothing here ran in Navisworks.

| Tool | Verdict | What was wrong, what changed | Proven or unproven |
|---|---|---|---|
| What Is It | fixed | Called the banned `pick.point` (and handled `pick.Unavailable`). Now `namo.picking.point('Click the item to inspect', want_item=True)`, prompt on the banner, cancel silent. A click lands on a geometry leaf, so the card now describes its element (`items.object_of`), where the Revit tabs live. Tooltip says how to use it | Proven route (measure_point + banner + faces.candidates_at, output window). Unproven: colour read-back (`ModelGeometry.ActiveColor`), already labelled best effort on the card |
| Properties Plus | ok as built | Follows the vptrackerlive pattern (session holder, guarded handlers, re-subscribe on ActiveDocumentChanged, FluentChrome + modeless keyboard interop before Show). Quantities now read in model units (see below) | Proven route |
| Selection HUD | fixed | The toggle trusted its own on/off state, which Reload forgets while the HUD window lives on: one click then did nothing visible. Now the window decides (`hud.is_running()`), as Hide Tabs does. Read budget 5,000 to 2,000 items (every selection change pays for it on the UI thread). The HUD no longer flashes at screen centre before it is anchored. Tooltips end "Shift+Click for settings." | Proven: selection Changed, DispatcherTimer, owner via FluentChrome. Unproven: borderless non-activating window (WS_EX_NOACTIVATE through ctypes; the ctypes calls were checked under IronPython 3.4 outside Navisworks) |
| Copy IDs | ok as built | Tooltip ending only | Proven route |
| Open in Explorer | ok as built | Nothing | Proven route |
| Property Explorer | fixed (shared reader) | Lengths, areas and volumes were assumed to arrive in SI. Now read in the units of the item's own model (`Model.Units`), the same reading namo.takeoff uses; one switch, `propindex.QUANTITY_SOURCE` | Proven route (pynavis.sets for search sets). Unproven: the stored units of DoubleLength/Area/Volume values |
| Count by Property | fixed (shared reader) | Same unit fix | Proven route |
| Property Exporter | fixed (shared reader) | Same unit fix (numbers and the unit in the header) | Proven route |
| Data Validator | fixed (shared reader) | Same unit fix (numeric ranges compare in report units). Tooltip ending | Proven route |
| Bulk Property Writer | fixed | Toasts promised "One undo step", which nobody has seen work for tabs written through COM: the promise is gone, the single transaction stays. Element ID keys now index only real Revit elements where a model has them (nested family parts repeat the TYPE id: field fact). Progress window moves every 25 items instead of every item | Unproven: `pynavis.props.set_custom` (COM SetUserDefined, the route pyNavis itself ships, not used by any shipped tool), and whether one Ctrl+Z undoes it |
| Find and Replace | fixed | Same toast and progress fixes; quantity text now in model units | Unproven: same write route; custom-tab detection (`PropertyCategory.IsEditable`) |
| Property Mapper | fixed | Same toast and progress fixes | Unproven: same write route |
| External Data Link | fixed | Same Element ID and progress fixes | Unproven: same write route |
| Model Tree Export | ok as built | Nothing | Proven route |
| Property Labels | fixed | Leader length was 3% of the selection box with a 0.001 unit floor, so one small object got an invisible stub and a whole building got masts. Now a real length (0.15 m to 1.5 m, converted to model units). A value missing on the element is read from the item as selected. Nothing is left in the overlay when its plugin is not loaded | Proven route (`overlay.add` + `redraw`, as Go to Coordinates and True Distance). Unproven: 500 labels at once (shipped tools draw one; each label is measured every frame) |
| Clear Labels | ok as built | Nothing | Proven route |

Evidence for the unit change: the API dump has `LcOaData.ConvertAndPrettyPrint(VariantData value, Units input_linear, LcOaUnitAngular input_angular, ...)`, so a stored value needs its input units named (it is not SI by definition), and angles may not always be radians either (still assumed).

Foundation requests

1. `namo/items.py` `objects()` and `geometry_items()`: a whole-model walk is one Python step per item (about 1.75 million on the owner's federation) before any tool starts reading. Fine with the counted progress it has, but worth a native route if one exists.
2. `namo/ui.py` `non_activating()` and `host_rect()`: the only users of ctypes in my group. They work under IronPython 3.4 outside Navisworks; if the HUD ever steals focus, this is where to look.
3. No foundation file was edited in this pass.

First three things to click

1. Select nothing, press Ctrl+Alt+I, click a duct. Correct: the bottom banner says "Click the item to inspect", the native measure marker snaps under the pointer, one click opens the card for the DUCT (not a nameless solid) with its Element tab, and Esc instead cancels with no message.
2. Select that duct, open Properties Plus, find Element > Length under "This item". Correct: it equals what the Navisworks Properties window shows (for example 10' 0"). Wrong by a factor of 3.28 means the values are SI after all: set `QUANTITY_SOURCE = 'si'` in `lib/namo/propindex.py`.
3. Select 20 ducts, Property Labels, pick Element > System Name. Correct: 20 orange labels on short leaders (about half a foot) above the ducts that follow orbit; Clear Labels removes them. Then toggle Selection HUD on, click Reload, click the toggle once: the HUD closes on that first click.

Still worth a look afterwards: Bulk Property Writer `Status = Open` on a few items, then Ctrl+Z, and report how many undo steps it takes (possibly none).

Verify: `summary: check ok, pytest ok, ipy compile ok, ipy test ok, ipy smoke ok, parse ok, fresh ok, names ok` (my 14 test files: 85 CPython tests, all also green under IronPython; 3 smoke files green).
