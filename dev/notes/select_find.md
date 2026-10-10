# G1 select_find: Select and Find panels (Model tab)

Built by agent G1. Everything below is verified headlessly only (unit tests on CPython and
IronPython 3.4, WPF smoke builds, the real pyNavis BundleParser). Nothing has been clicked
in Navisworks yet.

## 1. Tools

### Select panel
| Tool | What it does |
|---|---|
| Select Similar | Lists the first selected element's properties (identity ones such as GUIDs, ids and unique names hidden behind "Show identity properties"), you tick the ones a match must share and the scope (whole model, same model, current selection); one native search, pruned below matches, selects them. Remembers the ticked property names and scope. |
| Filter Selection | Prunes the current selection without a new search: pick a property (sampled from the selection and its elements), a test from namo.rules (equals, contains, between, is missing...), a value from the observed ones or typed; keep or remove the items that pass. Progress and cancel past 2,000 items. |
| Invert (stack) | ModelItemCollection.Invert, then leaves hidden items out (one native Item > Hidden search plus a frontier walk over the hidden items' ancestors only). Nothing selected selects everything visible. Shift+Click: include hidden items. |
| Select by File (stack) | Chooser of the appended files (file, type, units, item count up to 20,000) and selects the ticked files' roots. Remembers the ticked files by name. Shift+Click: zoom after selecting. |
| Save as Set (stack) | The selection becomes a selection set named from a template ({category} - {count} items - {date}) in folder Playground, in one click. Shift+Click: template and folder. |
| Back / Forward (stack, Alt+Left / Alt+Right) | Steps through the recorded selections of this model and restores them. |
| History (stack) | Lists the recorded selections (time, items, main category) and restores the chosen one. Shift+Click: recording on/off, record clearing, clear this model's history. |
| Pick Order (toggle) | While on, every newly clicked item (or each item of a Ctrl/Shift-added set of up to 20) is appended to the model's pick list, repeats ignored. Asks "continue or start a new list" when one exists. The list is kept on disk per model. |
| Picked (pulldown) | Select Picked; Number Picked (Playground > Sequence = 1..N, start, step, prefix, zero padding, merged into the existing Playground tab, one undo step); Export Picked (xlsx or CSV: order, name, category, Element ID, GUID, source file, centre XYZ in model units); Color Picked (light to strong blue along the order, one undo step); Clear Picked (asks above 20). |

### Find panel
| Tool | What it does |
|---|---|
| Quick Find (Ctrl+Alt+F) | Type-ahead search over every element by name, class, Element ID, category, family, type, mark, comments, IFC GlobalId and name, system, level. The first search per model builds an index (counted progress, cancel) saved to %APPDATA%\pyNavis\playground\index\<doc_key>.json and keyed by the appended files' names, sizes and dates, so later sessions open instantly and a changed model rebuilds it. Fuzzy ranking (namo.textmatch) with highlighted matches; numbers of 3+ digits match as written. Enter selects and zooms, Shift+Enter selects every match, Ctrl+Enter adds to the selection, Esc closes. Shift+Click: fields, results listed, index size cap, rebuild. |
| Search Set Wizard | One window: (1) search in whole model / chosen models / current selection; (2) condition rows (category, property, native operator, value picked from observed values with counts, ignore case), OR sets explained and each saved as its own set; (3) Count matches (count and time); (4) name, folder, select now. Values keep the observed kind (numbers searched as numbers). Remembers the last query. |
| Batch Sets | One search set per value of a property: pick the property, collect values from the selection or a full search of the items carrying it, tick values, name template ({value}, {property}, {category}, {count}), folder template (By {property}), optional extra condition (Element > Category = Ducts), skip or replace existing sets. One undo step; Cancel keeps what was written and says so. |
| Sets Library | Publish search sets to a JSON library in <team root>\libraries\sets (shared folder when Playground settings name one), import a library's sets (add beside or replace same-named), manage libraries (rename, delete, open folder). |
| Export Sets (stack) | Chosen sets to a Playground XML file: search sets as their conditions, static sets as portable item references (model file, PathId, Element ID, UniqueId, IFC GlobalId, InstanceGuid). |
| Import Sets (stack) | Recreates folders and sets from that XML. Static sets resolve by PathId first, then in one walk of the matching models' elements by InstanceGuid, UniqueId, IFC GlobalId and Element ID (within its model). Asks before creating empty static sets (default skip). Per-set results in the output window. |
| Repair Search In (stack) | Lists search sets whose Search In scope is empty or points at models/items that no longer resolve, with what they pointed at and the models matched by file name; re-scope them to the matched models, to models you choose, or to the whole model (copy, new Selection, ReplaceWithCopy in place: same name, position and Guid; one undo step per click). Before/after table in the output window. |

### Library modules (lib\namo)
`selecttools` (Select Similar, Filter, Invert, Select by File, Save as Set), `sel_history`
+ `hk_selhistory`, `sel_pickorder` + `hk_pickorder`, `quickfind`, `setwizard`,
`setexchange`, `find_query` (typed native conditions shared by the Find tools),
`find_sets` (set tree paths and creating sets with folder-local names and an optional
Search In scope), `find_batch`, `find_library`, `find_repair`.

## 2. In-app checks (please click these, in this order)

Setup: Reload pyNavis; open a federated model with at least one Revit NWC and, ideally, an
IFC and some hidden items.

1. Ribbon: Model tab shows Select (Select Similar, Filter Selection, Invert/Select by
   File/Save as Set, Back/Forward/History, Pick Order, Picked) and Find (Quick Find, Search
   Set Wizard, Batch Sets, Sets Library, Export Sets/Import Sets/Repair Search In) with
   their icons in light and dark theme. Back/Forward tooltips show Alt+Left/Alt+Right,
   Quick Find shows Ctrl+Alt+F, and the three chords work.
2. Select Similar on a duct: the window lists its properties with Category/Family/Type
   ticked; the scope radios read "Whole model", "Same model as the item", "Current
   selection"; "Show identity properties" adds GUID, Element ID, Mark rows. Select gives
   "Selected N similar items". Then tick ONLY a length property (e.g. Element > Width or
   Length): it must still find at least the duct itself. If the toast says "Left out (no
   native match)" or "These properties cannot be searched", tell me which property (float
   equality is searched as >= and <= around the value; DoubleLength comparison is
   UNVERIFIED).
3. Filter Selection on 1,000+ selected items: Element > Category equals Ducts, Keep: "Kept N
   of M". Repeat with "is missing" and with "greater than" on a numeric property; above
   2,000 items a progress window with Cancel appears.
4. Invert: hide a level, select one wall, Invert. The hidden level must NOT be selected
   (Selection Tree). This rests on a native search for Item > Hidden = true by internal
   names (PropertyCategoryNames.Item, DataPropertyNames.ItemHidden; UNVERIFIED). If the
   toast ends "Hidden items inside visible branches may still be selected", that search
   failed: please send the pyNavis log line "Invert: hidden-item search failed". Also
   Invert with nothing selected: "Selected everything visible".
5. Select by File: rows show file name, type (RVT/NWC/IFC), units and item counts (20,000+
   for big files); ticking two selects them; Shift+Click turns zoom on.
6. Save as Set: creates e.g. "Ducts - 412 items - 2026-10-05" in folder Playground; Ctrl+Z
   removes it in ONE step.
7. History: make three different selections, Alt+Left twice ("Selection 2 of 3", then "1 of
   3"), Alt+Right ("2 of 3"). Open History: still exactly 3 rows (Back/Forward must not
   record their own restores; this relies on the debounced selection-changed event firing
   after the command ends). Make a new selection after going back: Forward then says "No
   later selection". Shift+Click History, untick recording: Back says "Selection History is
   off".
8. Pick Order: click it (caption becomes Stop Picking), click 5 items one at a time,
   Ctrl+click one more, box-select 50 items (must NOT be added), click Stop Picking: "Pick
   order off: 6 picked". Click Pick Order again: it asks to continue or start a new list.
   Restart Navisworks: Picked > Select Picked still selects the 6 (list kept on disk).
9. Picked > Number Picked: Playground tab shows Sequence 1..6 in pick order and keeps any other
   Playground properties already there. Ctrl+Z ONCE should undo all six (the writes go through
   COM inside one .NET transaction: UNVERIFIED whether they join it). Export Picked to xlsx
   and CSV (CSV opens in Excel with accents intact; centre values in model units).
   Color Picked: light to strong blue, Ctrl+Z once undoes it. Clear Picked.
10. Quick Find (Ctrl+Alt+F) on the big model: "Indexing the model" progress with counts;
    Cancel closes silently. Run again and let it finish (note the time). Type a name, an
    Element ID, a level: results show the matched field highlighted ("Element ID: 312045").
    Enter selects and zooms; Shift+Enter selects every match; Ctrl+Enter adds. Restart
    Navisworks and reopen: Quick Find opens with no indexing. Please confirm the field
    values are real: Element ID ('Element ID > Value' or 'Element > Id'), Category, Type,
    Level and IFC GlobalId are read by DISPLAY names guessed for Revit/IFC exports.
11. Search Set Wizard: Category = Ducts AND Level = Level 3 (values from the drop-downs),
    Count matches, Create: set in folder Playground with the matches selected; open it in Find
    Items to see the conditions. Repeat with "Chosen models" (Search In must show those
    models when the set is loaded in Find Items) and with an OR set (two sets "(set 1)",
    "(set 2)"). A numeric property with "at least" must count correctly.
12. Batch Sets on Element > Level, whole model: one set per level in "By Level"; run again:
    "already existed and were skipped"; with Replace ticked: replaced in place. Add the extra
    condition "Element > Category = Ducts" and check the sets hold two conditions.
13. Sets Library: Publish two search sets (file appears in %APPDATA%\pyNavis\playground\libraries\sets,
    or the shared folder when set); Import them into another model (add beside / replace);
    Manage: rename, delete, Open folder.
14. Export Sets with a static set, then Import Sets into (a) the same model with the sets
    deleted (static items resolve by path) and (b) a model re-exported from Revit (resolve
    by InstanceGuid/UniqueId/Element ID). A static set that finds nothing triggers the
    "skip or create empty" question. The output window lists each set's result.
15. Repair Search In on a model whose sets all work: it must say "Every search set has a
    working Search In scope". If healthy sets are listed instead, send me their "Pointed
    at" text (SelectionSource.ToString, TryGetSelectedItems and Selection.GetSelectedItems
    are UNVERIFIED for a whole-model scope). Then import, from another project, search sets
    whose Search In names models: they are listed with the matched models; "Use matched
    models", "Choose models" and "Whole model" rewrite them in place (ReplaceWithCopy,
    UNVERIFIED) and the After column says so. Ctrl+Z undoes one click's repairs.
16. Cancel inside a write: start Number Picked on 100+ items or a large library import and
    press Cancel. Whether Navisworks rolls back the edits already made in the open
    transaction is UNVERIFIED; please report what remains.

## 3. Requests for shared modules (none blocking; all worked around locally)

1. `namo.ui`: please make the helpers custom windows need public and stable:
   `_thickness` -> `thickness(*values)`, `_close_with` -> `close_with(win, result)`,
   `_wpf` -> `load_wpf()`, `_Bag` -> `Bag`. selecttools, quickfind and setwizard call the
   underscored names today. Exact fix: add `thickness = _thickness`,
   `close_with = _close_with`, `load_wpf = _wpf`, `Bag = _Bag` at the end of ui.py and list
   them in the README "Parts" section.
2. `namo.textmatch.Index`: a public way to rank a subset, e.g.
   `def subset(self, indices): sub = Index([]); sub.items = [self.items[i] for i in indices];
   sub.texts = [self.texts[i] for i in indices]; sub.lows = [self.lows[i] for i in indices];
   return sub`. quickfind.QuickIndex sets those three attributes on an empty Index itself.
3. `namo.textmatch` (optional): digit runs match as a scattered subsequence ('900003' matches
   '900001 ... Level 3'). quickfind filters ids of 3+ digits to contiguous matches; the
   Command Palette and other filter boxes may want the same rule in rank().
4. `namo.items.resolve` (optional): a per-entry variant, `resolve_each(entries, doc) ->
   [item or None]`, so callers can keep positions; setexchange resolves one entry per call.

## Refit pass

Every bundle of both panels was read and run by hand on every branch; nothing was clicked in
Navisworks. "Proven" = only mechanisms a shipped pyNavis tool already uses in the field.

### 1. Tools

| Tool | Verdict | What was wrong, what changed | Proven or unproven |
|---|---|---|---|
| Select Similar | fixed (small) | Values pynavis returns as `NamedConstant:...` text were offered although a search can never match them; they are no longer listed (`find_query.kind_of`). Search route (sets.run, scoped preflight, prune) is sound. | Proven (sets.run + scope). Float "equals" as >= / <= on DoubleLength is unproven; the preflight drops and names such a row instead of finding nothing |
| Filter Selection | fixed | Picking a number from the value list kept nothing: the list shows 12.333333, the item holds 12.3333333333, and they were compared as numbers. A picked number or Yes/No is now matched by how it reads in the list (`selecttools.picked_condition`). | Proven (props reads, selection CopyFrom) |
| Invert | ok as built | Tooltip gained "Shift+Click for settings." | Unproven: `ModelItemCollection.Invert`, and the Item > Hidden search by internal names (`PropertyCategoryNames.Item`, `DataPropertyNames.ItemHidden`). A failed search falls back to a per-item check and the toast says so |
| Select by File | ok as built | Tooltip only | Proven |
| Save as Set | ok as built | Tooltip only | Proven (same AddCopy route as pynavis.sets.create) |
| Back / Forward | fixed | After clearing the selection, Back skipped the selection you just had and went one further. It now brings the last one back (`sel_history.target(at_cursor)`). | Proven (pynavis.memory path ids, selection-changed hook) |
| History | ok as built | Tooltip only | Proven |
| Selection History hook | fixed (speed) | Per item it asked the model for its file name again (three extra interop calls, up to 5,000 items per selection change); names are now read once per model. `namo.paths` is no longer imported per event. | Proven. Cost of a 5,000 item selection is still unmeasured |
| Pick Order | fixed | Now follows the shipped Hide Tabs toggle: what is really recording decides, not the button state, so they cannot disagree after a Reload. The prompt and a running count ("3 items picked. Last: ...") sit on `pynavis.banner` while it is on, as True Distance does, so every click is visibly registered. The hook reads its flag without importing the tool when off. | Proven (toggle state, banner, hook). Banner updated from a hook is new |
| Select / Clear Picked | ok as built | none | Proven |
| Number Picked | ok as built | none | Unproven: whether COM `SetUserDefined` writes join the one undo step (pynavis.props says the same) |
| Export Picked | ok as built | none | Proven (namo.xlsx, props reads) |
| Color Picked | ok as built | none | Proven as far as `namo.paint.apply` is (foundation) |
| Quick Find | fixed | (1) Non-text fields were indexed as `Int32:312045` (ToDisplayString raises on anything but a display string). (2) Nested family parts carry the TYPE's Element ID (field trap); they were indexed under it, so a type id listed parts of unrelated fixtures. Type ids are now left out in models that mark their elements. Index version bumped to 2, so old index files rebuild themselves. | Proven (DescendantsAndSelf walk, CreatePathId, memory resolve, zoom_selected). `FindCategoryByName('LcRevitData_Element')` is unproven; if it fails ids are simply all kept |
| Search Set Wizard | fixed | The property and value lists came from the FIRST 600 elements of each file (one level, one category). Samples are now spread over about 48 tree branches (`find_query.branches`). | Proven for whole model. Unproven: a saved search set carrying a Search In scope (chosen models / selection) |
| Batch Sets | fixed | Same sampling fix (a property missing from the first 300 elements could not be chosen at all). | Proven (sets.run, AddCopy). Replace uses `sets.update` (RemoveAt + InsertCopy), unproven; failures are listed per set |
| Sets Library | fixed | (1) Publish lost each condition's Ignore case option, and wrote negated or OR-grouped conditions back as plain AND conditions, silently changing what the set finds. Options are now read (`find_sets.set_conditions`); negated / OR conditions are marked unreadable and reported. (2) One unreadable set blocked the import of the whole library; the rest now import and the output window lists what was left out. Still round-trips through `sets.to_dict` / `sets.import_dict`. | Proven route (shipped Excel Sets). `SearchCondition.Options` read is unproven and guarded (falls back to pynavis' own output) |
| Export Sets | fixed | Same condition options fix. | Proven (sets.to_dict, memory path ids) |
| Import Sets | fixed | (1) A PathId hit was trusted blindly; in a re-exported model another element can sit at that path. A hit is kept only while the item still carries the reference's id (or name when it has no id). (2) Up to 20 missing Element IDs are now found the way shipped Select by IDs does (`sets.find_first`, text id AND the Element category, scoped to the file) instead of a walk of the whole model. (3) The fallback walk reads only the ids it needs, goes file by file, and returns the real Revit element instead of a nested part. | Proven for (2). The walk is plain property reads; its duration on a huge model is unmeasured (progress and Cancel are live) |
| Repair Search In | fixed | (1) A healthy whole-model set was judged by what its scope "resolves to", an unverified call; if that returns nothing every set would be listed as broken. Whole-model scopes are now recognised by `Selection.ValueEquals` against a fresh SelectAll and always count as working. (2) The set's folder was told from the root by comparing Guids; two empty Guids would have replaced the wrong set. Now compared as the same item, and the position check also needs the name. | Unproven: `DocumentSelectionSets.ReplaceWithCopy`, `SelectionSource.TryGetSelectedItems` / `ToString`, `Selection.ValueEquals`. A failed rewrite is reported per set with the manual step |

### 2. Foundation requests

* `namo/__init__.py`: the package body (seven `clr.AddReference` calls) re-runs on every hook
  run, about 27 ms of every selection change (measured under IronPython, outside
  Navisworks). Guard it with a session holder flag so it runs once per session.
* `namo.items.revit_element`: walks up to 64 ancestors enumerating every property category.
  `PropertyCategories.FindCategoryByName('LcRevitData_Element')` would be one call per
  level once it is confirmed in the field (Quick Find now tries it, guarded).
* `pynavis.sets._condition_to_dict` (pyNavis, not Playground): drops `SearchCondition.Options`
  (ignore case, negate, OR group) and returns `DisplayString:Ducts` style values, so the
  shipped Excel Sets round trip has the same losses Playground now works around locally.
* No foundation file was edited.

### 3. First three things to click

1. Pick Order: click it, then click five items one at a time. Correct: the button reads Stop
   Picking and the blue bar along the bottom says "Pick order on: 1 item picked", then 2, 3...
   with the last item's name. Stop Picking toasts "Pick order off: 5 picked" and the bar goes.
   Picked > Select Picked selects the five.
2. Select three different things one after another, press Esc, then Alt+Left. Correct: the
   third selection comes back ("Selection 3 of 3"); Alt+Left again gives "Selection 2 of 3",
   Alt+Right "Selection 3 of 3", and History still lists exactly three rows.
3. Quick Find (Ctrl+Alt+F): let it index, type an Element ID copied from the Properties
   window of a light fixture. Correct: one result, the fixture itself, with "Element ID:
   <id>" highlighted and no "Int32:" in front; Enter selects and zooms to it. Then select
   about 50 ducts, run Filter Selection, pick a Length value from the list and Keep: the
   toast count matches the count shown beside that value.

### 4. Verify

`=== summary: check ok, pytest ok, ipy compile ok, ipy test ok, ipy smoke ok, parse ok, fresh ok, names ok`
(IronPython: 1603 passed, 0 failed, 35 skipped; WPF smoke 115 passed; 13 new regression tests
in `dev\tests\test_select_find_refit.py`).
