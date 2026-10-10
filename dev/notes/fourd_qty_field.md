# G9 fourd_qty_field: 4D, Quantities and Field panels (tab Project)

Built by agent G9. Everything below is verified headlessly only (pure tests on CPython
3.11 and IronPython 3.4, WPF windows built under IronPython, the real pyNavis
BundleParser). Nothing has been clicked in Navisworks.

## 1. The tools

### 4D.panel
* **TimeLiner from Excel** (large). Two choices: *Write a template* (an .xlsx with the
  model's tasks as Task ID / Parent ID rows, attach column filled with set paths, plus a
  Read me and a Task types sheet; three example tasks when TimeLiner is empty) or
  *Import a schedule* (.xlsx or .csv). Rows are checked first (dates via namo.dates, day
  or month first, Excel percent cells, duplicate IDs, missing parents, Parent ID loops,
  children of bad rows; hierarchy from Parent ID, a WBS column or an Outline level
  column) and shown in a review table; Merge (update by Task ID, add the rest, never move
  an existing task) or Replace. Attach cells take selection set paths or rules
  (`Element > Category = Ducts`, `&` to combine, one entry per line); rules are evaluated
  in one pass over the model. Commits once. Misses listed in a table.
* **Auto Attach** (large). One rule per line: `Name ~ L(?P<level>\d+) (?P<trade>\w+) =>
  Element > Level = Level {level} & Item > Layer contains {trade}` or `Name contains Slab
  => set Structure/Slabs`; skip / replace / add for tasks that already have items; leaf
  tasks only by default. Preview table per task, then one undo step. Shift+Click loads or
  deletes saved rule templates (namo.templates 'auto_attach').
* **Progress Painter** (large). Set % complete of the selected objects: writes
  `Playground > Progress` (merged into each object's existing Playground tab) and updates the
  ProgressPercent of every TimeLiner task holding them (mean of its objects, missing
  counting 0), all one undo step. Or paint the model by object progress or by TimeLiner
  task progress in four bands (0 grey, 1-49 amber, 50-99 blue, 100 green) with a modeless
  legend window and Clear paint.
* **4D Movie Maker** (large). Planned or actual dates, a range and a step in days or weeks,
  the current view or a saved viewpoint's camera, frame size, fps. Each frame sets every
  attached item's state (construct: hidden / green / normal; demolish: normal / red /
  hidden; temporary: hidden / yellow / hidden; an item follows its most recently started
  task), renders with Document.GenerateImage, stamps date, tasks under way and a timeline
  bar, saves `frame_NNNN.png`, then writes `index.html` (play, pause, slider, speed, keys)
  and an MP4 when ffmpeg is on PATH. Hidden flags, temporary colours and the camera are
  put back in a try/finally even on cancel or error; the whole run is one transaction.
* **TimeLiner Export** (stack, report `timeliner_export`). Every task to xlsx: Task ID,
  WBS outline, indented names (summary tasks bold), planned/actual dates and days, type,
  progress, status (Complete, In progress, In progress late, Late start, Not started, No
  dates) with washes, attachment kind and item count, user columns that hold anything;
  Summary sheet by status and type.
* **Schedule Health** (stack, report `schedule_health`). Leaf tasks with nothing attached,
  missing dates, end before start, zero duration, objects in several leaf tasks, objects
  in no task (saved as the set `Playground/Not scheduled`), a 0-100 score; HTML report opened
  in the browser. Shift+Click switches the coverage walk and the set off.

### Quantities.panel
* **Quick Takeoff** (large, report `quick_takeoff`). Scope (selection / visible / model),
  group by one or two properties (or Category / Model file), count, length, area, volume,
  weight (property names auto-detected from a 300-object sample: Revit Element tabs, IFC
  Qto/BaseQuantities, net before gross), optional geometric volume (closed meshes) and
  bounding-box length where properties are missing (2,000-object budget, flagged), surface
  area from geometry. Modeless results table with subtotals and totals: Export to Excel
  (Takeoff, Objects, Notes), Select objects, Save as template.
* **Zone Takeoff** (large, report `zone_takeoff`). Zones from grid levels (bands between
  levels), zone objects (a set or the selection: rooms, areas; centre inside, ties by
  largest overlap), grid bays (lines rebuilt from GridSystem.ClosestIntersection probes,
  'A-B / 3-4') or square tiles. Results by zone and group; Excel with a Pivot sheet (one
  measure), a Zones sheet and one sheet per zone (first 60).
* **Takeoff Templates** (large). All Quick and Zone templates (team-shared through
  namo.templates): Run, Rename, Duplicate, Delete, Export (one file per tool), Import.
* **COG Calculator** (large). Per selected object: closed-mesh volume and solid centroid,
  else bounding box centre and box volume x fill factor (flagged estimate); mass from a
  Weight/Mass property or volume x density matched from the material (then category)
  against an editable table (steel 7850, concrete 2400, aluminium 2700, timber 500, glass
  2500 kg/m3). Combined centre of gravity drawn as an overlay cross labelled `COG  12.4 t`;
  modeless table with Copy COG, Select objects, Export to Excel. Shift+Click: densities,
  default density, fill factor, remove the marker.

### Field.panel
* **QR Tagger** (large). Payload template (`{project}|{file}|{element_id}|{guid}` or a URL
  with tokens), error correction L/M/Q/H, module size; one PNG per object, a printable A4
  label sheet (3 x 8, inline SVG codes, name and IDs) and the payload written into
  `Playground > QR` (one undo step). Encoder: namo.qr (see the proof below).
* **Photo Pins** (large). Click a point (pynavis.pick), choose photos (multi-select),
  caption; the pin stores the point, level and grid labels from the active grid, the
  clicked object, the camera, photo copies (in the store's `_media` folder) and the date
  taken (EXIF DateTimeOriginal read in pure Python, else the file time). Drawn with
  pynavis.overlay (tag `playground-photos:<id>`); hk_photopins redraws on doc-opened.
  Shift+Click: show or hide pins, label by caption or pin number.
* **Photo Browser** (large). Modeless window of photo thumbnails grouped by level, grid or
  linked object, filter, Go to (camera + select object), Open photo, Delete pin, Export an
  HTML photo report. Keyboard: arrows, Enter, Delete, Ctrl+F.
* **Field Checklists** (large, context viewpoints). Modeless window: the checklist of one
  saved viewpoint (Pass / Fail / N/A and a note per item, sections), inspector, date,
  sign-off (only when every item is answered), Previous/Next and a viewpoint list that
  also move the view, Attach a template to a viewpoint without one, Report (HTML + Excel
  with completion and failures). Records per document (RecordStore 'checklists'); team
  templates (namo.templates 'checklists') with QA inspection and Safety walk built in;
  Shift+Click edits templates.

### Modules
timeliner (all TimeLiner access + schedule logic), fourd_attach, fourd_progress, fourd_ui,
fourd_common, movie, takeoff (+ zones), qty_ui, qty_run, cog, qr, field_qr, photopins,
field_photobrowser, checklists, field_checklistwin, hk_photopins, rep_timeliner_export,
rep_schedule_health, rep_quick_takeoff, rep_zone_takeoff.

### How TimeLiner is reached and written (decisions, all in timeliner.py)
* `clr.AddReference('Autodesk.Navisworks.Timeliner')` (through pynavis._api.add_reference,
  as pynavis.clash does for Clash), then `TimelinerDocumentExtensions.GetTimeliner(doc)`
  (static), else `DocumentTimeliner.TimelinerInstance(doc)` (static), else `doc.Timeliner`.
* Import: the new tree is built detached and bottom up (fresh `TimelinerTask()` nodes, or
  `CreateCopyWithoutChildren()` of live tasks for a merge, children added before the node
  joins its parent: the shape pynavis.clash verified for clash groups) and committed with
  ONE `TasksCopyFrom(List[SavedItem])`; if refused, `TasksClear()` + `TaskAddCopy(root)`
  per root in the same transaction.
* Edits of existing tasks (attachments, progress): `TaskEdit(parent, index, copy)` (root
  tasks: `TaskEdit(index, copy)`), copy = `CreateCopyWithoutChildren()` with the change,
  all inside one `pynavis.viewpoints.transaction`. Timings go to the pyNavis log.
* Attach a set: `doc.SelectionSets.CreateSelectionSource(set)` into a
  `SelectionSourceCollection`, `task.Selection.CopyFrom(sources)` (live link); rules and
  mixed cells attach explicit items (`CopyFrom(ModelItemCollection)`).

### QR encoder: what is proven
On both engines (dev/tests/test_qr.py): GF(256)/0x11D tables; RS remainders equal the ISO
18004 annex I vector ('01234567' 1-M: A5 24 D4 C1 ED 36 C7 87 2C 55) and the published
'HELLO WORLD' 1-M vector; all 32 format words equal the published table and are pairwise
at Hamming distance >= 7; version words 7..40 match known values and are pairwise >= 8
apart; capacities and alignment centres match the published tables; every symbol read back
(unmask, zigzag, de-interleave) gives zero RS syndromes on every block and the original
payload; finders, timing, alignment, dark module, both format copies and both version
copies sit where ISO puts them. Under CPython with OpenCV 4.12: every symbol (all levels,
versions 1 to 21) decodes with `cv2.QRCodeDetectorAruco` to the exact payload; against
`cv2.QRCodeEncoder` with the same version, level and mask the matrices are identical
except in the remainder bits (ISO masks them, OpenCV does not) or where OpenCV's own
symbol does not decode (it mis-builds 21-H; ours decodes).

## 2. In-app checks (please click through in this order)

Open a federated NWF with Revit models, a grid system with levels, some selection sets and
a few saved viewpoints. Keep the pyNavis log open (%APPDATA%\pyNavis\logs\pyNavis.log); the
TimeLiner calls log their timing as `timeliner: ...`.

**TimeLiner basics**
1. TimeLiner from Excel > Write a template on a model whose TimeLiner is empty. Expect a
   workbook with 3 example rows, a Read me and a Task types sheet listing your task types
   (if it lists only Construct, Demolish, Temporary while TimeLiner has more, reading
   `SimulationTaskTypes` failed: tell me).
2. Fill 5 rows (one with Parent ID, one with Attach = an existing set path, one with
   `Element > Category = Walls`, one with a Progress of 50), Import, Merge. Check in
   TimeLiner: tasks exist, hierarchy right, dates right (time zone: a 2026-10-05 date
   must show as 5 October 2026, not the 4th), Task Type set, % Complete shows 50 (if it shows
   0.5 or 5000, ProgressPercent is not 0..100: tell me), Active ticked, the set task shows
   the set in its Attached column, the rule task shows Explicit Selection.
3. Ctrl+Z once: every imported task disappears in ONE undo (if each task is its own undo
   step, the transaction does not group TimeLiner edits). Ctrl+Y back.
4. Write a template again: the 5 tasks come back as rows with Parent IDs and the set path.
   Change a name, add a row under an existing ID, Import with Merge: the name updates,
   the new task appears under its parent, nothing else moves. Log line says
   `import committed with TasksCopyFrom` (if it says TaskAddCopy, TasksCopyFrom refused:
   tell me the message logged just before).
5. Import the same sheet with Replace: confirm text says it replaces every task; result
   has only the sheet's tasks.
6. Put an error in the sheet (End before Start, an unknown Parent ID): the review table
   lists them, Cancel imports nothing.

**Auto Attach**
7. Tasks named like `L1 Walls`, `L2 Walls`; rule `Name ~ L(?P<lvl>\d+) (?P<cat>\w+) =>
   Element > Level = Level {lvl} & Element > Category = {cat}` (adjust to your level
   names). Preview shows found counts per task; Attach. In TimeLiner each task's
   attachment selects the right items. One Ctrl+Z removes all attachments
   (TaskEdit in a transaction).
8. Rule `Name contains Walls => set <your set>`: attaches the set itself (TimeLiner shows
   the set name, and adding an item to the set later shows in the simulation).
9. Mode Add on a task that already has items: the union is attached.

**Progress Painter**
10. Select 3 objects of a task, Set progress 40. Properties panel: tab `Playground` has
    `Progress 40` and keeps any other Playground property (e.g. QR) already there. The
    task's % Complete updates (mean over its objects). One Ctrl+Z undoes both (the custom
    property write goes through COM: check it is in the same undo step).
11. Paint by object progress, then by TimeLiner task progress: colours by band, legend
    counts match; Clear paint and Ctrl+Z both remove the colours.

**4D Movie Maker**
12. Close TimeLiner's Simulate tab first. Hide one unscheduled item yourself, give one item
    a permanent colour, then make a weekly movie of 6 to 10 frames at 1280 x 720 from a
    saved viewpoint. Frames must DIFFER as dates advance (if every frame looks the same,
    rendering inside the open transaction does not see the hidden/colour changes: set
    `ONE_TRANSACTION = False` at the top of `lib/namo/movie.py` and run again). Stamp shows
    date, weekday, tasks under way and a blue timeline bar.
13. After it finishes: the item you hid is still hidden, everything else as before, your
    permanent colour intact, camera back where it was. Undo history shows one 'Make 4D
    movie' entry (or none).
14. Start another movie and Cancel half way: same exact restore; no toast.
15. With ffmpeg on PATH an MP4 plays in Windows Media Player; without it, the toast says
    so and the HTML player works (Space, arrows, slider, speed).

**Reports**
16. TimeLiner Export: workbook opens with indented names, statuses, item counts.
17. Schedule Health: HTML opens; the set Playground/Not scheduled exists and selects objects
    attached to no task; score plausible.

**Quantities**
18. Quick Takeoff on Revit walls grouped by Category then Element > Level, Volume and Area:
    compare one wall's Volume and Area with the Properties panel. Values that are off by
    a power of 0.3048 mean property doubles are not in the model's units: tell me which
    tab/property and the model units (assumption: DoubleLength/Area/Volume values are in
    the item's Model.Units; bare weights kg for metric models, lb for imperial).
19. Same with Measure the geometry ticked on objects without Volume: Notes column says
    'n geometric'; a closed solid's geometric volume matches its Revit volume closely.
20. Zone Takeoff by grid levels: objects land in the band of their level (check GridLevel
    Elevation is in document units and absolute Z). By grid bays: zone names look like
    `A-B / 3-4` for a rectangular grid (bays come from ClosestIntersection probes on a
    24 x 24 lattice; a grid with very dense lines may miss some lines: tell me).
21. Takeoff Templates: save one from a result, Run it, Rename, Export, Import the file.

**COG**
22. Select a few steel beams and a slab: method 'Closed mesh' for clean solids; centroid
    marker drawn with `COG  x.x t`; Copy COG pastes 'X, Y, Z'. An object with an open mesh
    shows 'Bounding box (estimate)'. Shift+Click > remove marker clears it.

**Field**
23. QR Tagger on 5 objects: PNGs scan with a phone camera (the payload text appears), the
    label sheet prints on A4 at 100% with 24 labels per page, `Playground > QR` holds the
    payload. One Ctrl+Z removes the property.
24. Photo Pins: click a point, pick 2 JPEGs from a phone (with EXIF), caption. Pin drawn
    (stem, diamond, caption). Toast names level and grid (if both are blank with an active
    grid, `ClosestIntersection` or `GridIntersection.Level` behave differently: tell me).
    Close and reopen the NWF: pins redraw (hook). Shift+Click hide/show works.
25. Photo Browser: thumbnails, grouping, filter, Go to restores the camera and selects
    the object, Open photo, Delete pin (pin disappears from the view), Export report.
26. Field Checklists on a model with saved viewpoints: Attach QA inspection, answer items,
    Save, Next (the view moves to the next viewpoint), Previous (answers kept), Sign off
    refused while items are open, Report writes HTML and Excel. Reopen: progress labels in
    the viewpoint list.

## Limits and decisions worth knowing

* Auto Attach rules are edited as text (one rule per line, validated live in the form),
  not in a grid; saved rule sets are namo.templates 'auto_attach'.
* TimeLiner merge never moves an existing task to a new parent (counted and reported).
* Photo Browser groups by level, grid intersection or linked object; there is no
  takeoff-zone grouping. Photos stay local in model data mode (records travel in the NWF).
* QR Tagger encodes byte mode (UTF-8, no ECI); the encoder also has numeric and
  alphanumeric modes, used for the published test vectors. Versions 1 to 40.
* Quick/Zone Takeoff read geometry for at most 2,000 objects per run (flagged and counted
  past that); COG Calculator takes at most 2,000 selected objects.
* 4D Movie Maker frames are capped at 2,000; the camera of a saved viewpoint is applied,
  not its hide/override state.

## 3. Requests for shared modules (not edited; worked around locally)

* **namo.ui**: make `_wpf()` public (e.g. `ui.load_wpf()`). Window builders that import
  `System.Windows` names before calling `ui.window()` fail with "Cannot import name
  Thickness" unless the WPF assemblies were referenced. fourd_ui, field_photobrowser and
  field_checklistwin carry a local `_wpf()` copy.
* **namo.store**: a per-store attachments folder that also works in model mode (photo
  copies). Today `RecordStore.folder` is None in model mode, so photopins keeps media in
  `<data_root>\docs\<doc_key>\photo-pins-media` and the photos do not travel inside the
  NWF (records do). Suggested: `RecordStore.files_folder()` returning `<folder>\_files` in
  file modes and the local per-document folder in model mode.
* **namo.paint**: a `reset_temporary(items)` overload (ResetTemporaryMaterials for some
  items) so movie.py would not call `Models.ResetTemporaryMaterials` directly.
* **dev/tests/test_items.py FakeNav**: add `DocumentModels.ResetAllHidden`,
  `ResetTemporaryMaterials`, a `Grids.ActiveSystem` (None) and `pynavis.props.all_of` so
  more API halves can be tested against the shared fakes (test_movie and test_timeliner
  carry their own small fakes for now).
* **pynavis (read-only, for the pyNavis owner)**: `forms.open_file` has no multi-select;
  photopins opens its own `Microsoft.Win32.OpenFileDialog` with Multiselect.

## Refit pass

G9 fourd_qty_field, second pass. All 14 bundles read end to end with their namo modules. Verified
headlessly only; nothing here has been clicked in Navisworks. (Section 1 above still describes the
tools; where it says Photo Pins uses pynavis.pick or draws a diamond, this section replaces it.)

### 1. Tools

| Tool | Verdict | What was wrong, what changed | Proven or unproven |
|---|---|---|---|
| Photo Pins | fixed | Called the banned `pick.point` (hover marker and hit disagreed). Now `namo.picking.point(prompt, want_item=True)`, no `pick.Unavailable`. Pin head was one diamond in the X/Z plane (a line seen along X, a dash in plan): now an octahedron outline that reads from every angle, stem, foot cross, label at the head top. Size was a fixed 1.2 m: now Small 0.5 m / Medium 1 m / Large 2.5 m in Shift+Click, converted from metres to model units. A "New pin" preview is drawn at the clicked point while the file and caption prompts are up. Thumbnails are made at pin time. Toast says when pins are hidden or could not be drawn. Tooltip in shipped form | Proven: measure pick, banner, overlay, `faces.candidates_at`, `memory.encode_items`, `Grids.ActiveSystem.ClosestIntersection` (pynavis.clash uses it). Unproven: the overlay repainting behind the modal file dialog (preview only) |
| Photo Pins settings (config.py) and hook | fixed | Button, settings, browser and hook each drew or cleared their own way. All four now end in `photopins.refresh(doc)`, so Show pins means the same everywhere. Hook also clears on doc-closed (pins of a closed model used to stay in the view). Clearing no longer trusts only the session's memory: any overlay item under the pin prefix is removed, so pins drawn before a Reload cannot be orphaned | Proven: `pynavis.overlay`, `pynavis.settings`. Reads `overlay.OverlayRegistry.Items` (public runtime member, guarded) |
| Photo Browser | fixed | Go to with no saved camera framed the point plus or minus ONE model unit (a 2 mm cube in a millimetre model): now 2.5 m each way in model units. "Went to" was toasted even when the view did not move. Go to and Delete now refuse (with a toast) when another model was opened since. Delete failure is a toast. The open browser refreshes when Photo Pins adds a pin | Proven: `CurrentViewpoint.CopyFrom`, `ZoomBox` via namo.camera |
| QR Tagger | fixed | Objects with no Element ID or GUID all got the same payload silently: the result toast now counts repeats and says why. Failure toast names the folder. Encoder and PNG writer untouched (pure, tested) | Proven: `props.set_custom` (pynavis notes that one-undo-step for COM custom tabs is itself unverified) |
| Field Checklists | fixed | A viewpoint deleted while the window was open made Previous/Next a silent no-op (logged only): now a warning toast | Proven: `SavedViewpoints.CurrentSavedViewpoint = saved` (vptrackerlive) |
| COG Calculator | fixed | "Closed mesh" needed welded shared vertices; neighbouring faces tessellated separately would send real solids to bounding box x 0.6 (badly wrong for beams). New `takeoff.solid_measure`: geometric closure (area vectors cancel, the three per-axis volume integrals agree), summed about the mesh centre. Combined COG moments taken about the first centroid, not the origin. Remove marker button in the window; toast says if the marker could not be drawn | Proven: `pynavis.geometry.world_triangles`, overlay. No hard-coded epsilon left |
| Quick Takeoff | fixed | Same geometric-volume rule as COG through `solid_measure`; surface area unchanged | Proven: `pynavis.props`, geometry |
| Zone Takeoff | fixed (shared code) | Same volume fix. Zones from grid levels and bays read `GridSystem.Levels`, `GridLevel.Elevation`, `GridIntersection.Line1/Line2/Line1Direction/Position` | Unproven: those grid members (guarded, empty grid gives a toast) |
| Takeoff Templates | ok as built | Read end to end; nothing to change | Proven |
| TimeLiner from Excel | fixed | Any TimeLiner read failure other than "not available" was a traceback: `snapshot` now always raises one sentence (cause in the log). A refused commit was a traceback: now a toast. Added the Autodesk-sample commit route (copy of TasksRoot, `TasksCopyFrom(children)`) between the list route and the destructive clear-and-add | Unproven: all of TimeLiner (list below) |
| Auto Attach | fixed | `edit_tasks` edited summary tasks through `CreateCopyWithoutChildren` and kept live references across edits; if `TaskEdit` replaces children that deletes the branch. Now tasks with children are copied with them, found again by position before each edit, deepest first | Unproven: `TaskEdit`, `TimelinerSelection.CopyFrom` |
| Progress Painter | fixed (shared code) | Same `edit_tasks` fix. Paint and custom tab are proven routes | Unproven: `TaskEdit`, `ProgressPercent` scale (0 to 100 assumed) |
| 4D Movie Maker | ok as built | Read end to end. Restore follows pynavis.viewstate (ResetAllHidden + SetHidden) | Unproven: frames rendered inside the open transaction (`ONE_TRANSACTION` switch in movie.py), `OverrideTemporaryColor`, `ResetTemporaryMaterials(items)` |
| TimeLiner Export | ok as built | Benefits from the snapshot guard | Unproven: TimeLiner read |
| Schedule Health (+ config.py) | ok as built | Benefits from the snapshot guard | Unproven: TimeLiner read; set written with `pynavis.sets` (proven) |

TimeLiner members no shipped tool exercises (all guarded; a failure is a toast plus a `timeliner:` log
line): `TimelinerDocumentExtensions.GetTimeliner`, `DocumentTimeliner.TimelinerInstance`, `Tasks`,
`TasksRoot`, `SimulationTaskTypes`, `TasksCopyFrom` (both overloads), `TasksClear`, `TaskAddCopy`,
`TaskEdit` (both overloads); `TimelinerTask()` and its `DisplayId`, `Planned/ActualStart/EndDate`,
`IsPlannedEnabled`, `IsActualEnabled`, `IsEnabled`, `SimulationTaskTypeName`, `ProgressPercent`,
`User1..10`, `Children`, `CreateCopy`, `CreateCopyWithoutChildren`; `TimelinerSelection.IsClear`,
`HasSelectionSources`, `HasSearch`, `HasExplicitSelection`, `DisplayString`, `SelectionSources`,
`GetSelectedItems`, `CopyFrom`, `Clear`; `SelectionSets.CreateSelectionSource`, `ResolveSelectionSource`.

### 2. Foundation changes and requests

* Edited `lib\namo\hooks.py` (one line): registered `('doc-closed', 'hk_photopins')`.
* Request, `namo.mesh.is_closed` / `summary`: the welded-edge test rejects watertight solids whose
  faces do not share vertices. `takeoff.solid_measure` is the geometric test; other groups reading
  volumes from `mesh.summary` may want it moved into `mesh`.
* Request, `pynavis.overlay`: a public "tags in the overlay" call, so tools need not reach
  `overlay.OverlayRegistry.Items` to clear by prefix.
* Request, G8 Issue Pins: `issues.pin_segments` has no plan-view outline (two vertical diamonds);
  the two pin kinds now look different. Worth aligning one way or the other.

### 3. First three things to click

1. Photo Pins, in a perspective view of the 1.37 million ft model: the banner along the bottom asks
   for the click, the Navisworks measure marker follows the pointer, and after the click an orange
   pin labelled "New pin" stands exactly on the marked point while you choose photos and type a
   caption. Then the pin shows its caption, about 1 m tall, readable from the side and from a top
   view. Shift+Click, untick Show: pins vanish. Reopen the file: still hidden. Tick it again: back.
2. Photo Browser: thumbnails appear at once, Go to restores the camera the pin was taken from and
   selects the object, Delete removes the pin from the view too.
3. COG Calculator on a few steel beams and a slab: Method reads "Closed mesh" (not "Bounding box
   (estimate)") for ordinary Revit solids, the cross sits inside the group with "COG  x.x t", and
   one beam's volume matches its Revit Volume property. Then TimeLiner from Excel > Write a
   template as the first TimeLiner check (a workbook opens; any failure must be a toast).

### 4. Verify

`summary: check ok, pytest ok, ipy compile ok, ipy test ok, ipy smoke ok, parse ok, fresh ok, names ok`
(pytest 1,591 passed, 18 skipped; IronPython 1,575 passed, 0 failed, 35 skipped; smoke 115 passed.)
New regression tests: pin head from every axis, pin far from the origin, real-world sizes, Go to box,
overlay tag clean-up, hook on open and close, no banned pick in the group, repeated QR payloads,
solid_measure (closed, open tube, miswound, unwelded, far from origin), COG far from origin,
edit_tasks under both TaskEdit semantics, TimeLiner failures as sentences.
