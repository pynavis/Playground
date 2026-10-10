# Headless runner results, 2026-10-09

Every row below comes from a real, hidden Navisworks Manage 2026 driven by pyNavis'
`pynavis run`, against copies of two small sample models (`a.nwd`, `b.nwd`: one avatar
model, 17 geometry parts under one element, one saved viewpoint, one clash test with no
results, no Revit properties, no levels or grids). The runner never saved a model. Run
folder ids are the folders under `%APPDATA%\pyNavis\runs\` holding each run's transcript
and `results.json`.

Outcome of the 140 tools: 60 `ok` (21 did their real work, 39 stopped early on a missing
precondition and said so), 77 `needs-dialog`, 0 `failed` after the fixes below, 1
`skipped-unsafe`, 2 `not-runnable` (dock panes). The 21 that did their real work, plus
Level Sectioner (fixed), are `launched` in `status.yaml`.

Every runnable tool ran twice, once with nothing selected and once with every geometry
part selected (`--select-all`). The Model tab's selected pass was run again after the
property fix below; the table shows the last run of each pass. To repeat the pass:

    python dev\runner\batch.py --file <keys.txt>
    python dev\runner\batch.py --select-all --file <keys.txt>
    python dev\runner\report.py            # this table
    python dev\runner\apply_status.py      # status.yaml, by the rules below

`batch.py` pauses (exit 3) before starting Navisworks when free memory is under 2 GB.

## What the sample model can and cannot show

The sample is one small avatar model: 17 geometry parts under one element, one saved
viewpoint, one clash test with no results, no Revit properties, no levels or grids, no
search sets, no TimeLiner tasks, no issues. So:

* A `launched` from this pass means the tool's code ran inside a real Navisworks on that
  path without raising, and what it reported is in the run's transcript. It does not
  mean the result is right: nobody looked at the colours, files or numbers, and on this
  model most "results" are a single element or an empty list.
* Most tools never reached their real work here. Anything about clash results, levels,
  Revit ids, sets, viewpoints beyond one, 4D or issues stopped at "No ... found" or at
  its first dialog. Those are `ok` (early exit) or `needs-dialog` and keep their status.
* Every tool that asks the user something is `needs-dialog`: the runner cannot answer a
  dialog, so its main path is still untested.
* Units, large models, multi-model federations, Revit data, performance and anything
  visual (overlays, windows, colours seen on screen) are out of reach of this pass.

## How a tool is run

* `dev\runner\run_tool.py` (driver) runs one bundle's `script.py` with the globals a ribbon
  click gives it (`__file__`, `__commandpath__`, `__title__`, `__selfinit__` False,
  `__pynavis__`, plus the runner's `__runner__` True) and sets the host's command context
  to the bundle key. `--select-all` first selects every geometry part.
* `dev\runner\_bootstrap.py` puts `Playground.extension\lib` first on `sys.path` and drops
  any `namo` already imported (pyNavis runs every configured extension's `startup.py`
  before a run, and another extension on this machine ships its own `namo`).
* Sandbox: `APPDATA`, `LOCALAPPDATA`, `TEMP`, `TMP`, `USERPROFILE` and `HOME` point at
  `D:\Temp\pg-runner\sandbox` for the run, with `namo.paths.redirect` and
  `pynavis.settings` following. Shell side effects (`os.startfile`, `subprocess`,
  `webbrowser`, Explorer, the clipboard, Reload, `namo.ui.open_path`/`show_in_explorer`/
  `copy`) are recorded no-ops; the Note column says when a run hit one. Writes that
  remain go to the sandbox or next to the model copy in `D:\Temp\pg-runner\models`.
* Before running, every script was read along the path it takes headless (empty and full
  selection) into namo and pynavis, looking for writes outside the sandbox, process
  launches, network, schtasks, registry writes, model save/publish/append and C#-side
  persistent state. One tool was skipped as unsafe; see the table.
* `dev\runner\batch.py` runs one hidden Navisworks session per tool (the runner takes one
  script per invocation), `--timeout 120`, and appends to `D:\Temp\pg-runner\ledger.jsonl`.

Outcomes: `ok` (exit 0, no traceback in the transcript), `needs-dialog` (the runner's
dialog refusal, or the tool's own runner guard toast saying it needs the Navisworks
window), `failed`, `skipped-unsafe`, `not-runnable` (dock panes: their script needs the
real panel as `__pane__`), `not-run` (still to do). In "Path run", "ran to the end" means
the tool did its real work; "early exit" means it stopped on a missing precondition
(nothing selected, no levels, no clash results) and says so.

Status rules applied to `status.yaml`: `ok` that ran to the end becomes `launched`
(`by: runner`; an existing log-backed `launched` keeps its status and gets the note
merged); `failed` becomes `known-issue`; everything else is unchanged.

## Gate checks (dev\runner\gates.py, run 20261009-005438)

Both models gave the same numbers.

| # | Check | a.nwd | b.nwd | Numbers |
|---|---|---|---|---|
| G0 | `namo` imports (camera, items, paint, images, clashdata, ui, docdb) from this repo | pass | pass | |
| G1 | Camera axes round trip: apply direction/up, read back | pass | pass | front (0,1,0)/(0,0,1) and top (0,0,-1)/(0,1,0) read back exactly (gap 0.0). This checks namo's quaternion convention against Navisworks' own read-back, not against the ViewCube; the ViewCube half of G1 still needs a person. |
| G2 | `camera.capture` / `apply` round trip | pass | pass | moved 10.0 units away, came back with position, direction and up gaps of 0.0 |
| G3 | `images.capture` to a temp PNG | pass | pass | 1280x720 PNG, 163,745 and 164,747 bytes; 1 saved viewpoint (capture_saved not exercised) |
| G4 | `clashdata.tests()` | pass | pass | 1 test, 0 results; snapshot rows 0 = results 0 (a grouped test with results still needs a real model) |
| G5 | `paint.apply` + one undo | pass | pass | 17 of 17 parts red; `NextUndo` "Color items"; one `TryUndo` back to 0 red and `NextUndo` "Current View" |
| G6 | `items.revit_ids` | pass | pass | returns the dict; every field None (no Revit data in the sample; the family-instance case needs a Revit model) |
| G7 | `docdb` kv set/get | pass | pass | available True; `{'a': 1}` read back (save and reopen not tested: the runner never saves) |
| | Quick Find index build | pass | pass | 1 row (one element), saved to the sandbox index folder |
| | `pynavis.sets.create` | pass | pass | selection sets 0 to 1, "Runner gate set" |

## Bugs found and fixed

* Level Sectioner `NameError: free variable 'refresh_footer' referenced before
  assignment` (`namo/ui.py` `build_choose`): a single-select chooser opened on a row fires
  the table's change callback while the window is still being built, before
  `refresh_footer` is defined. `changed()` now calls the footer refresh through the
  `holder` dict, filled once `refresh_footer` exists. Pinned by
  `smoke_ui.test_choose_single_checked_runs_no_callback_before_its_def`, and the
  IronPython smoke harness (`dev\ipy_driver.py smoke`) now fails any smoke test during
  which a window callback logs a NameError or UnboundLocalError (`ui.safe` swallows them,
  which is how this one hid). A static scan of every nested function that reads a name
  its enclosing function binds later found no other case that can fire during
  construction; the rest run only after a click.
* `namo.picking.point` / `points` under `pynavis run`: `pynavis.pick.measure_point` has no
  runner check, so a pick switched the hidden Navisworks to the Measure tool and waited
  for a click until the run timed out (and reacted to Esc or a right-click anywhere on the
  desktop). Both now raise the runner's dialog refusal first (Match Appearance with nothing selected, and
  Coordinate Spotter now stop as `needs-dialog`). Pinned by `dev\tests\test_picking.py`.

* Typed doubles in property reads (new `namo/variants.py`). `pynavis.props.get` and
  `all_of` call `VariantData.ToDouble()` for every IsDouble kind, but Navisworks only
  allows it on a plain double: any length, area, volume or angle raises "Not supported
  if '!IsDouble'". Select Similar failed on that under `--select-all`
  (run 20261009-013656), and `namo.items.prop` silently returned None for every length.
  `namo.variants.get` / `all_of` / `to_python` read the four typed kinds through their
  own readers (`ToDoubleLength` and so on) and fall back from pynavis only when it raises;
  every Playground call site of `pynavis.props.get`, `all_of` and `_variant_to_python`
  now uses them. Pinned by `dev\tests\test_variants.py`. Select Similar then reached its
  dialog (run 20261009-020147). The same bug is in pyNavis' own `pynavis/props.py`
  (`_variant_to_python`); it is not fixed there from this repo.

## Per tool

| Bundle key | Outcome | Path run | Note | Run folder |
|---|---|---|---|---|
| `Model.tab/Select.panel/Select_Similar.pushbutton` | ok | no selection: early exit: "Nothing selected"; 17 parts selected: stopped at its first dialog |  | 20261009-010230, 20261009-020147 |
| `Model.tab/Select.panel/Filter_Selection.pushbutton` | ok | no selection: early exit: "Nothing selected"; 17 parts selected: stopped at its first dialog |  | 20261009-010242, 20261009-020201 |
| `Model.tab/Select.panel/Quick.stack/Invert.pushbutton` | ok | no selection: ran to the end: "Selected everything visible"; 17 parts selected: early exit: "Nothing left to select" |  | 20261009-010255, 20261009-020214 |
| `Model.tab/Select.panel/Quick.stack/Select_by_File.pushbutton` | needs-dialog | no selection: stopped at its first dialog; 17 parts selected: stopped at its first dialog |  | 20261009-010307, 20261009-020226 |
| `Model.tab/Select.panel/Quick.stack/Save_as_Set.pushbutton` | ok | no selection: early exit: "Nothing selected"; 17 parts selected: ran to the end: "Saved set 'Object Material - 17 items - 2026-10-09'" |  | 20261009-010320, 20261009-020239 |
| `Model.tab/Select.panel/History.stack/Back.pushbutton` | ok | no selection: early exit: "No selection history yet"; 17 parts selected: early exit: "No earlier selection" |  | 20261009-010332, 20261009-020251 |
| `Model.tab/Select.panel/History.stack/Forward.pushbutton` | ok | no selection: early exit: "No selection history yet"; 17 parts selected: early exit: "No later selection" |  | 20261009-010344, 20261009-020302 |
| `Model.tab/Select.panel/History.stack/History_List.pushbutton` | ok | no selection: early exit: "No selection history yet"; 17 parts selected: stopped at its first dialog |  | 20261009-010356, 20261009-020314 |
| `Model.tab/Select.panel/Pick_Order.toggle` | ok | no selection: ran to the end (wrote output); 17 parts selected: ran to the end (wrote output) |  | 20261009-010408, 20261009-020327 |
| `Model.tab/Select.panel/Pick_Order_Actions.pulldown/Select_Picked.pushbutton` | ok | no selection: early exit: "No picked items"; 17 parts selected: early exit: "No picked items" |  | 20261009-010419, 20261009-020339 |
| `Model.tab/Select.panel/Pick_Order_Actions.pulldown/Number_Picked.pushbutton` | ok | no selection: early exit: "No picked items"; 17 parts selected: early exit: "No picked items" |  | 20261009-010431, 20261009-020351 |
| `Model.tab/Select.panel/Pick_Order_Actions.pulldown/Export_Picked.pushbutton` | ok | no selection: early exit: "No picked items"; 17 parts selected: early exit: "No picked items" |  | 20261009-010443, 20261009-020403 |
| `Model.tab/Select.panel/Pick_Order_Actions.pulldown/Color_Picked.pushbutton` | ok | no selection: early exit: "No picked items"; 17 parts selected: early exit: "No picked items" |  | 20261009-010455, 20261009-020415 |
| `Model.tab/Select.panel/Pick_Order_Actions.pulldown/Clear_Picked.pushbutton` | ok | no selection: early exit: "The pick list is already empty"; 17 parts selected: early exit: "The pick list is already empty" |  | 20261009-010507, 20261009-020426 |
| `Model.tab/Find.panel/Quick_Find.pushbutton` | needs-dialog | no selection: stopped at its first dialog; 17 parts selected: stopped at its first dialog |  | 20261009-010519, 20261009-020438 |
| `Model.tab/Find.panel/Search_Set_Wizard.pushbutton` | needs-dialog | no selection: stopped at its first dialog; 17 parts selected: stopped at its first dialog |  | 20261009-010532, 20261009-020451 |
| `Model.tab/Find.panel/Batch_Sets.pushbutton` | needs-dialog | no selection: stopped at its first dialog; 17 parts selected: stopped at its first dialog |  | 20261009-010545, 20261009-020504 |
| `Model.tab/Find.panel/Sets_Library.pushbutton` | needs-dialog | no selection: stopped at its first dialog; 17 parts selected: stopped at its first dialog |  | 20261009-010558, 20261009-020517 |
| `Model.tab/Find.panel/Set_Exchange.stack/Export_Sets.pushbutton` | ok | no selection: early exit: "No sets to export"; 17 parts selected: early exit: "No sets to export" |  | 20261009-010610, 20261009-020529 |
| `Model.tab/Find.panel/Set_Exchange.stack/Import_Sets.pushbutton` | needs-dialog | no selection: stopped at its first dialog; 17 parts selected: stopped at its first dialog |  | 20261009-010623, 20261009-020542 |
| `Model.tab/Find.panel/Set_Exchange.stack/Search_In_Repair.pushbutton` | ok | no selection: early exit: "No search sets"; 17 parts selected: early exit: "No search sets" |  | 20261009-010637, 20261009-020555 |
| `Model.tab/Inspect.panel/What_Is_It.pushbutton` | ok | no selection: runner guard: "Nothing selected"; 17 parts selected: ran to the end (wrote output) | stubbed: namo.ui.copy | 20261009-010648, 20261009-020607 |
| `Model.tab/Inspect.panel/Properties_Plus.pushbutton` | needs-dialog | no selection: runner guard: "Properties Plus needs the Navisworks window"; 17 parts selected: runner guard: "Properties Plus needs the Navisworks window" |  | 20261009-010700, 20261009-020619 |
| `Model.tab/Inspect.panel/Selection_HUD.toggle` | needs-dialog | no selection: runner guard: "The Selection HUD needs the Navisworks window"; 17 parts selected: runner guard: "The Selection HUD needs the Navisworks window" |  | 20261009-010712, 20261009-020630 |
| `Model.tab/Inspect.panel/Inspect_Tools.stack/Copy_IDs.pushbutton` | ok | no selection: early exit: "Nothing selected"; 17 parts selected: ran to the end: "Copied 1 row" | stubbed: namo.ui.copy | 20261009-010724, 20261009-020642 |
| `Model.tab/Inspect.panel/Inspect_Tools.stack/Open_in_Explorer.pushbutton` | ok | no selection: ran to the end: "Opened in Explorer"; 17 parts selected: ran to the end: "Opened the cache file" | stubbed: namo.ui.show_in_explorer; stubbed: namo.ui.show_in_explorer | 20261009-010736, 20261009-020655 |
| `Model.tab/Data.panel/Property_Explorer.pushbutton` | needs-dialog | no selection: runner guard: "Property Explorer needs the Navisworks window"; 17 parts selected: runner guard: "Property Explorer needs the Navisworks window" |  | 20261009-010748, 20261009-020707 |
| `Model.tab/Data.panel/Count_by_Property.pushbutton` | ok | no selection: ran to the end: "Counted 1 value over 1 object"; 17 parts selected: ran to the end: "Counted 1 value over 1 object" |  | 20261009-010800, 20261009-020718 |
| `Model.tab/Data.panel/Property_Exporter.pushbutton` | ok | no selection: early exit: "Nothing selected"; 17 parts selected: ran to the end: "Exported 1 row" |  | 20261009-010812, 20261009-020731 |
| `Model.tab/Data.panel/Data_Validator.pushbutton` | ok | no selection: early exit: "No rule applied to the 1 object"; 17 parts selected: early exit: "No rule applied to the 1 object" |  | 20261009-010824, 20261009-020743 |
| `Model.tab/Data.panel/Write_Data.pulldown/Bulk_Property_Writer.pushbutton` | needs-dialog | no selection: runner guard: "Bulk Property Writer needs the Navisworks window"; 17 parts selected: runner guard: "Bulk Property Writer needs the Navisworks window" |  | 20261009-010837, 20261009-020756 |
| `Model.tab/Data.panel/Write_Data.pulldown/Find_and_Replace.pushbutton` | needs-dialog | no selection: runner guard: "Find and Replace needs the Navisworks window"; 17 parts selected: runner guard: "Find and Replace needs the Navisworks window" |  | 20261009-010849, 20261009-020808 |
| `Model.tab/Data.panel/Write_Data.pulldown/Property_Mapper.pushbutton` | needs-dialog | no selection: runner guard: "Property Mapper needs the Navisworks window"; 17 parts selected: runner guard: "Property Mapper needs the Navisworks window" |  | 20261009-010901, 20261009-020819 |
| `Model.tab/Data.panel/Write_Data.pulldown/External_Data_Link.pushbutton` | needs-dialog | no selection: runner guard: "External Data Link needs the Navisworks window"; 17 parts selected: runner guard: "External Data Link needs the Navisworks window" |  | 20261009-010912, 20261009-020831 |
| `Model.tab/Data.panel/Data_Tools.stack/Model_Tree_Export.pushbutton` | ok | no selection: ran to the end: "Exported 25 tree nodes from 1 model"; 17 parts selected: ran to the end: "Exported 25 tree nodes from 1 model" |  | 20261009-010924, 20261009-020843 |
| `Model.tab/Data.panel/Data_Tools.stack/Clear_Labels.pushbutton` | ok | no selection: early exit: "No labels to clear"; 17 parts selected: early exit: "No labels to clear" |  | 20261009-010937, 20261009-020856 |
| `Model.tab/Data.panel/Property_Labels.pushbutton` | needs-dialog | no selection: runner guard: "Property Labels needs the Navisworks window"; 17 parts selected: runner guard: "Property Labels needs the Navisworks window" |  | 20261009-010949, 20261009-020907 |
| `Model.tab/Look.panel/Color_by_Property.pushbutton` | needs-dialog | no selection: stopped at its first dialog; 17 parts selected: stopped at its first dialog |  | 20261009-011001, 20261009-020919 |
| `Model.tab/Look.panel/Color_Presets.pushbutton` | needs-dialog | no selection: stopped at its first dialog; 17 parts selected: stopped at its first dialog |  | 20261009-011014, 20261009-020932 |
| `Model.tab/Look.panel/Trade_Ghost.pushbutton` | needs-dialog | no selection: stopped at its first dialog; 17 parts selected: stopped at its first dialog |  | 20261009-011026, 20261009-020944 |
| `Model.tab/Look.panel/Status_Painter.pushbutton` | needs-dialog | no selection: stopped at its first dialog; 17 parts selected: stopped at its first dialog |  | 20261009-011039, 20261009-020957 |
| `Model.tab/Look.panel/Look_Tools.stack/Legend_Maker.pushbutton` | ok | no selection: early exit: "No color scheme yet"; 17 parts selected: early exit: "No color scheme yet" |  | 20261009-011052, 20261009-021010 |
| `Model.tab/Look.panel/Look_Tools.stack/Match_Appearance.pushbutton` | ok | no selection: stopped at its first dialog; 17 parts selected: ran to the end: "Painted 16 items like Wire Color Material" |  | 20261009-011107, 20261009-021021 |
| `Model.tab/Look.panel/Look_Tools.stack/Exploded_View.pushbutton` | ok | no selection: early exit: "Nothing selected"; 17 parts selected: stopped at its first dialog |  | 20261009-011121, 20261009-021033 |
| `Model.tab/Look.panel/View_Tools.stack/Reset_All_Overrides.pushbutton` | needs-dialog | no selection: stopped at its first dialog; 17 parts selected: stopped at its first dialog |  | 20261009-011143, 20261009-021046 |
| `Model.tab/Look.panel/View_Tools.stack/Background.pushbutton` | ok | no selection: ran to the end: "Background"; 17 parts selected: ran to the end: "Background" |  | 20261009-011158, 20261009-021059 |
| `Model.tab/Look.panel/Presentation_Mode.toggle` | skipped-unsafe |  | Not run: it has no runner guard and calls user32 ShowWindow(SW_MAXIMIZE) on the Navisworks main window (presentation.py:271), which would show the hidden runner instance on the desktop, and it hides the ribbon and every add-in's dock panels. |  |
| `Model.tab/Look.panel/Exit_Presentation.nobutton` | ok | no selection: early exit: "Presentation mode is not on"; 17 parts selected: early exit: "Presentation mode is not on" |  | 20261009-011213, 20261009-021111 |
| `Views.tab/Viewpoints.panel/Batch_Viewpoints.pushbutton` | needs-dialog | no selection: stopped at its first dialog; 17 parts selected: stopped at its first dialog |  | 20261009-011225, 20261009-014641 |
| `Views.tab/Viewpoints.panel/Viewpoints_from_Excel.pushbutton` | needs-dialog | no selection: stopped at its first dialog; 17 parts selected: stopped at its first dialog |  | 20261009-011239, 20261009-014653 |
| `Views.tab/Viewpoints.panel/Export_Viewpoints.pushbutton` | needs-dialog | no selection: stopped at its first dialog; 17 parts selected: stopped at its first dialog |  | 20261009-011252, 20261009-014706 |
| `Views.tab/Viewpoints.panel/Viewpoint_Sync.pushbutton` | needs-dialog | no selection: stopped at its first dialog; 17 parts selected: stopped at its first dialog |  | 20261009-011305, 20261009-014718 |
| `Views.tab/Viewpoints.panel/Where_Am_I.pushbutton` | ok | no selection: ran to the end (wrote output); 17 parts selected: ran to the end (wrote output) |  | 20261009-011317, 20261009-014731 |
| `Views.tab/Capture.panel/Viewpoints_to_Images.pushbutton` | needs-dialog | no selection: stopped at its first dialog; 17 parts selected: stopped at its first dialog |  | 20261009-011330, 20261009-014742 |
| `Views.tab/Capture.panel/Batch_Image_Export.pushbutton` | needs-dialog | no selection: stopped at its first dialog; 17 parts selected: stopped at its first dialog |  | 20261009-011343, 20261009-014755 |
| `Views.tab/Capture.panel/Batch_PDF.pushbutton` | needs-dialog | no selection: stopped at its first dialog; 17 parts selected: stopped at its first dialog |  | 20261009-011356, 20261009-014808 |
| `Views.tab/Navigate.panel/Level_Sectioner.pushbutton` | ok | no selection: early exit: "No levels found"; 17 parts selected: early exit: "No levels found" |  | 20261009-011409, 20261009-014821 |
| `Views.tab/Navigate.panel/Level_Up.nobutton` | ok | no selection: early exit: "No levels found"; 17 parts selected: early exit: "No levels found" |  | 20261009-011421, 20261009-014833 |
| `Views.tab/Navigate.panel/Level_Down.nobutton` | ok | no selection: early exit: "No levels found"; 17 parts selected: early exit: "No levels found" |  | 20261009-011433, 20261009-014845 |
| `Views.tab/Navigate.panel/Camera_Sync.toggle` | needs-dialog | no selection: runner guard: "Waiting for another session"; 17 parts selected: runner guard: "Waiting for another session" |  | 20261009-011445, 20261009-014857 |
| `Views.tab/Navigate.panel/Spotter.stack/Coordinate_Spotter.pushbutton` | needs-dialog | no selection: stopped at its first dialog; 17 parts selected: stopped at its first dialog |  | 20261009-011457, 20261009-014909 |
| `Views.tab/Navigate.panel/Spotter.stack/Clear_Spots.pushbutton` | ok | no selection: early exit: "No spots to clear"; 17 parts selected: early exit: "No spots to clear" |  | 20261009-011509, 20261009-014921 |
| `Views.tab/Navigate.panel/Sheet.stack/Sheet_Overlay.pushbutton` | needs-dialog | no selection: stopped at its first dialog; 17 parts selected: stopped at its first dialog |  | 20261009-011521, 20261009-014933 |
| `Views.tab/Navigate.panel/Sheet.stack/Clear_Sheet.pushbutton` | ok | no selection: early exit: "No sheet on the view"; 17 parts selected: early exit: "No sheet on the view" |  | 20261009-011533, 20261009-014945 |
| `Coordinate.tab/Clash_Setup.panel/Clash_Matrix.pushbutton` | needs-dialog | no selection: runner guard: "This tool asks questions, so it cannot run under pynavis run"; 17 parts selected: runner guard: "This tool asks questions, so it cannot run under pynavis run" |  | 20261009-011545, 20261009-014957 |
| `Coordinate.tab/Clash_Setup.panel/Clash_Templates.pushbutton` | needs-dialog | no selection: runner guard: "This tool asks questions, so it cannot run under pynavis run"; 17 parts selected: runner guard: "This tool asks questions, so it cannot run under pynavis run" |  | 20261009-011557, 20261009-015009 |
| `Coordinate.tab/Clash_Setup.panel/Scan_vs_Model.pushbutton` | needs-dialog | no selection: runner guard: "This tool asks questions, so it cannot run under pynavis run"; 17 parts selected: runner guard: "This tool asks questions, so it cannot run under pynavis run" |  | 20261009-011610, 20261009-015021 |
| `Coordinate.tab/Clash_Results.panel/Clash_Namer.pushbutton` | needs-dialog | no selection: runner guard: "This tool asks questions, so it cannot run under pynavis run"; 17 parts selected: runner guard: "This tool asks questions, so it cannot run under pynavis run" |  | 20261009-011623, 20261009-015033 |
| `Coordinate.tab/Clash_Results.panel/Status_Rules.pushbutton` | needs-dialog | no selection: runner guard: "This tool asks questions, so it cannot run under pynavis run"; 17 parts selected: runner guard: "This tool asks questions, so it cannot run under pynavis run" |  | 20261009-011636, 20261009-015045 |
| `Coordinate.tab/Clash_Results.panel/Clash_Assigner.pushbutton` | needs-dialog | no selection: runner guard: "This tool asks questions, so it cannot run under pynavis run"; 17 parts selected: runner guard: "This tool asks questions, so it cannot run under pynavis run" |  | 20261009-011649, 20261009-015056 |
| `Coordinate.tab/Clash_Results.panel/Clash_to_Viewpoints.pushbutton` | needs-dialog | no selection: runner guard: "This tool asks questions, so it cannot run under pynavis run"; 17 parts selected: runner guard: "This tool asks questions, so it cannot run under pynavis run" |  | 20261009-011702, 20261009-015108 |
| `Coordinate.tab/Clash_Results.panel/Clash_Heatmap.pushbutton` | needs-dialog | no selection: runner guard: "This tool asks questions, so it cannot run under pynavis run"; 17 parts selected: runner guard: "This tool asks questions, so it cannot run under pynavis run" |  | 20261009-012602, 20261009-015120 |
| `Coordinate.tab/Clash_Results.panel/Revit_Link.stack/Show_in_Revit.pushbutton` | ok | no selection: early exit: "Nothing selected"; 17 parts selected: early exit: "The selection has no Revit elements" |  | 20261009-012617, 20261009-015132 |
| `Coordinate.tab/Clash_Results.panel/Revit_Link.stack/Show_from_Revit.pushbutton` | ok | no selection: early exit: "Nothing has been sent from Revit yet"; 17 parts selected: early exit: "Nothing has been sent from Revit yet" |  | 20261009-012629, 20261009-015144 |
| `Coordinate.tab/Clash_Reports.panel/Clash_Excel_Report.pushbutton` | ok | no selection: early exit: "No clash results to report"; 17 parts selected: early exit: "No clash results to report" |  | 20261009-012641, 20261009-015156 |
| `Coordinate.tab/Clash_Reports.panel/Clash_Dashboard.pushbutton` | ok | no selection: early exit: "No clash results to report"; 17 parts selected: early exit: "No clash results to report" |  | 20261009-012653, 20261009-015208 |
| `Coordinate.tab/Clash_Reports.panel/Clash_Count_Matrix.pushbutton` | ok | no selection: early exit: "No clash results to count"; 17 parts selected: early exit: "No clash results to count" |  | 20261009-012706, 20261009-015219 |
| `Coordinate.tab/Clash_Reports.panel/History.stack/Snapshot_Clashes.pushbutton` | ok | no selection: early exit: "No clash results yet"; 17 parts selected: early exit: "No clash results yet" |  | 20261009-012718, 20261009-015231 |
| `Coordinate.tab/Clash_Reports.panel/History.stack/Clash_Delta.pushbutton` | ok | no selection: early exit: "No clash snapshots yet"; 17 parts selected: early exit: "No clash snapshots yet" |  | 20261009-012730, 20261009-015243 |
| `Coordinate.tab/Clash_Reports.panel/History.stack/Clash_Trends.pushbutton` | ok | no selection: early exit: "No clash snapshots yet"; 17 parts selected: early exit: "No clash snapshots yet" |  | 20261009-012742, 20261009-015256 |
| `Coordinate.tab/Clash_Reports.panel/Per_Trade_Reports.pushbutton` | ok | no selection: early exit: "No clash results to report"; 17 parts selected: early exit: "No clash results to report" |  | 20261009-012756, 20261009-015308 |
| `Coordinate.tab/Issues.panel/Issues.dockpane` | not-runnable |  | Not runnable headless: a dock pane script receives its panel as __pane__, which only a real Navisworks dock panel provides. |  |
| `Coordinate.tab/Issues.panel/Issue_Stamps.pulldown/RFI.pushbutton` | needs-dialog | no selection: runner guard: "Issue Stamps needs the Navisworks window"; 17 parts selected: runner guard: "Issue Stamps needs the Navisworks window" |  | 20261009-012808, 20261009-015320 |
| `Coordinate.tab/Issues.panel/Issue_Stamps.pulldown/Hold.pushbutton` | needs-dialog | no selection: runner guard: "Issue Stamps needs the Navisworks window"; 17 parts selected: runner guard: "Issue Stamps needs the Navisworks window" |  | 20261009-012821, 20261009-015332 |
| `Coordinate.tab/Issues.panel/Issue_Stamps.pulldown/Verify.pushbutton` | needs-dialog | no selection: runner guard: "Issue Stamps needs the Navisworks window"; 17 parts selected: runner guard: "Issue Stamps needs the Navisworks window" |  | 20261009-012833, 20261009-015345 |
| `Coordinate.tab/Issues.panel/Issue_Stamps.pulldown/Safety.pushbutton` | needs-dialog | no selection: runner guard: "Issue Stamps needs the Navisworks window"; 17 parts selected: runner guard: "Issue Stamps needs the Navisworks window" |  | 20261009-012845, 20261009-015357 |
| `Coordinate.tab/Issues.panel/Issue_Stamps.pulldown/Stamp_from_Template.pushbutton` | needs-dialog | no selection: runner guard: "Issue Stamps needs the Navisworks window"; 17 parts selected: runner guard: "Issue Stamps needs the Navisworks window" |  | 20261009-012856, 20261009-015409 |
| `Coordinate.tab/Issues.panel/Issue_Pins.toggle` | ok | no selection: ran to the end: "Issue pins are on"; 17 parts selected: ran to the end: "Issue pins are on" |  | 20261009-012912, 20261009-015421 |
| `Coordinate.tab/Issues.panel/Meeting_Mode.pushbutton` | needs-dialog | no selection: runner guard: "Meeting mode needs the Navisworks window"; 17 parts selected: runner guard: "Meeting mode needs the Navisworks window" |  | 20261009-012927, 20261009-015433 |
| `Coordinate.tab/Issues.panel/Issue_Tools.stack/Issue_Templates.pushbutton` | needs-dialog | no selection: runner guard: "Issue Templates needs the Navisworks window"; 17 parts selected: runner guard: "Issue Templates needs the Navisworks window" |  | 20261009-012941, 20261009-015445 |
| `Coordinate.tab/Issues.panel/Issue_Tools.stack/Clash_to_Issues.pushbutton` | needs-dialog | no selection: stopped at its first dialog; 17 parts selected: stopped at its first dialog |  | 20261009-012956, 20261009-015457 |
| `Coordinate.tab/Issues.panel/Coordination_Report.pushbutton` | ok | no selection: early exit: "No issues to report"; 17 parts selected: early exit: "No issues to report" |  | 20261009-013011, 20261009-015510 |
| `Coordinate.tab/Issues.panel/KPI_Export.pushbutton` | needs-dialog | no selection: stopped at its first dialog; 17 parts selected: stopped at its first dialog |  | 20261009-013030, 20261009-015522 |
| `Coordinate.tab/BCF.panel/BCF_Export.pushbutton` | needs-dialog | no selection: stopped at its first dialog; 17 parts selected: stopped at its first dialog |  | 20261009-013044, 20261009-015534 |
| `Coordinate.tab/BCF.panel/BCF_Import.pushbutton` | needs-dialog | no selection: stopped at its first dialog; 17 parts selected: stopped at its first dialog |  | 20261009-013057, 20261009-015547 |
| `Project.tab/Models.panel/Batch_Append.pushbutton` | needs-dialog | no selection: stopped at its first dialog; 17 parts selected: stopped at its first dialog |  | 20261009-013111, 20261009-015600 |
| `Project.tab/Models.panel/Source_Files.dockpane` | not-runnable |  | Not runnable headless: a dock pane script receives its panel as __pane__, which only a real Navisworks dock panel provides. |  |
| `Project.tab/Models.panel/Link_Navigator.pushbutton` | ok | no selection: early exit: "Nothing selected"; 17 parts selected: stopped at its first dialog |  | 20261009-013126, 20261009-015612 |
| `Project.tab/Models.panel/Transform_Fixer.pushbutton` | needs-dialog | no selection: stopped at its first dialog; 17 parts selected: stopped at its first dialog |  | 20261009-013140, 20261009-015625 |
| `Project.tab/Models.panel/Folder_Watch.toggle` | ok | no selection: ran to the end: "Folder Watch is on"; 17 parts selected: ran to the end: "Folder Watch is on" |  | 20261009-013153, 20261009-015638 |
| `Project.tab/Models.panel/Stale_File_Alert.pushbutton` | ok | no selection: ran to the end (wrote output); 17 parts selected: ran to the end (wrote output) |  | 20261009-013205, 20261009-015649 |
| `Project.tab/Quality.panel/Model_Health_Check.pushbutton` | ok | no selection: ran to the end (wrote output); 17 parts selected: ran to the end (wrote output) |  | 20261009-013217, 20261009-015701 |
| `Project.tab/Quality.panel/Duplicate_Finder.pushbutton` | needs-dialog | no selection: stopped at its first dialog; 17 parts selected: stopped at its first dialog |  | 20261009-013230, 20261009-015714 |
| `Project.tab/Quality.panel/Model_Compare.pushbutton` | needs-dialog | no selection: stopped at its first dialog; 17 parts selected: stopped at its first dialog |  | 20261009-013243, 20261009-015726 |
| `Project.tab/Quality.panel/Preflight.pushbutton` | ok | no selection: ran to the end (wrote output); 17 parts selected: ran to the end (wrote output) |  | 20261009-013255, 20261009-015739 |
| `Project.tab/Quality.panel/Session_Stats.pushbutton` | ok | no selection: ran to the end (wrote output); 17 parts selected: ran to the end (wrote output) |  | 20261009-013307, 20261009-015751 |
| `Project.tab/Publish.panel/NWD_Publisher.pushbutton` | needs-dialog | no selection: stopped at its first dialog; 17 parts selected: stopped at its first dialog |  | 20261009-013320, 20261009-015804 |
| `Project.tab/Publish.panel/Model_Wipe.pushbutton` | needs-dialog | no selection: stopped at its first dialog; 17 parts selected: stopped at its first dialog |  | 20261009-013332, 20261009-015817 |
| `Project.tab/4D.panel/TimeLiner_from_Excel.pushbutton` | needs-dialog | no selection: runner guard: "TimeLiner from Excel asks for a file"; 17 parts selected: runner guard: "TimeLiner from Excel asks for a file" |  | 20261009-013345, 20261009-015829 |
| `Project.tab/4D.panel/Auto_Attach.pushbutton` | needs-dialog | no selection: runner guard: "Auto Attach needs a person at the screen"; 17 parts selected: runner guard: "Auto Attach needs a person at the screen" |  | 20261009-013357, 20261009-015841 |
| `Project.tab/4D.panel/Progress_Painter.pushbutton` | needs-dialog | no selection: runner guard: "Progress Painter needs a person at the screen"; 17 parts selected: runner guard: "Progress Painter needs a person at the screen" |  | 20261009-013409, 20261009-015853 |
| `Project.tab/4D.panel/Movie_Maker.pushbutton` | needs-dialog | no selection: runner guard: "4D Movie Maker needs a person at the screen"; 17 parts selected: runner guard: "4D Movie Maker needs a person at the screen" |  | 20261009-013421, 20261009-015905 |
| `Project.tab/4D.panel/Schedule_Tools.stack/TimeLiner_Export.pushbutton` | ok | no selection: early exit: "No TimeLiner tasks"; 17 parts selected: early exit: "No TimeLiner tasks" |  | 20261009-013433, 20261009-015917 |
| `Project.tab/4D.panel/Schedule_Tools.stack/Schedule_Health.pushbutton` | ok | no selection: early exit: "No TimeLiner tasks"; 17 parts selected: early exit: "No TimeLiner tasks" |  | 20261009-013444, 20261009-015929 |
| `Project.tab/Quantities.panel/Quick_Takeoff.pushbutton` | ok | no selection: ran to the end: "Takeoff of 1 object"; 17 parts selected: ran to the end: "Takeoff of 1 object" |  | 20261009-013456, 20261009-015941 |
| `Project.tab/Quantities.panel/Zone_Takeoff.pushbutton` | ok | no selection: early exit: "No zones to take off by"; 17 parts selected: early exit: "No zones to take off by" |  | 20261009-013509, 20261009-015953 |
| `Project.tab/Quantities.panel/Takeoff_Templates.pushbutton` | needs-dialog | no selection: runner guard: "Takeoff Templates needs a person at the screen"; 17 parts selected: runner guard: "Takeoff Templates needs a person at the screen" |  | 20261009-013521, 20261009-020005 |
| `Project.tab/Quantities.panel/COG_Calculator.pushbutton` | needs-dialog | no selection: runner guard: "COG Calculator works on the selection"; 17 parts selected: runner guard: "COG Calculator works on the selection" |  | 20261009-013532, 20261009-020017 |
| `Project.tab/Field.panel/QR_Tagger.pushbutton` | needs-dialog | no selection: runner guard: "QR Tagger works on the selection"; 17 parts selected: runner guard: "QR Tagger works on the selection" |  | 20261009-013544, 20261009-020028 |
| `Project.tab/Field.panel/Photo_Pins.pushbutton` | needs-dialog | no selection: runner guard: "Photo Pins needs a person at the screen"; 17 parts selected: runner guard: "Photo Pins needs a person at the screen" |  | 20261009-013556, 20261009-020040 |
| `Project.tab/Field.panel/Photo_Browser.pushbutton` | needs-dialog | no selection: runner guard: "Photo Browser is a window"; 17 parts selected: runner guard: "Photo Browser is a window" |  | 20261009-013608, 20261009-020052 |
| `Project.tab/Field.panel/Field_Checklists.pushbutton` | needs-dialog | no selection: runner guard: "Field Checklists is a window"; 17 parts selected: runner guard: "Field Checklists is a window" |  | 20261009-013620, 20261009-020104 |
| `Project.tab/Exchange.panel/Geometry_Exporter.pushbutton` | needs-dialog | no selection: runner guard: "This tool asks questions, so it cannot run under pynavis run"; 17 parts selected: runner guard: "This tool asks questions, so it cannot run under pynavis run" |  | 20261009-013632, 20261009-020116 |
| `Project.tab/Exchange.panel/IFC_Exporter.pushbutton` | needs-dialog | no selection: runner guard: "This tool asks questions, so it cannot run under pynavis run"; 17 parts selected: runner guard: "This tool asks questions, so it cannot run under pynavis run" |  | 20261009-013644, 20261009-020128 |
| `Dev.tab/Automate.panel/Command_Palette.pushbutton` | needs-dialog | no selection: runner guard: "The Command Palette needs the Navisworks window"; 17 parts selected: runner guard: "The Command Palette needs the Navisworks window" |  | 20261009-005538, 20261009-005912 |
| `Dev.tab/Automate.panel/Macro_Record.toggle` | ok | no selection: ran to the end: "Recording a macro"; 17 parts selected: ran to the end: "Recording a macro" |  | 20261009-005553, 20261009-005924 |
| `Dev.tab/Automate.panel/Macros.pulldown/Play_Macro.pushbutton` | ok | no selection: early exit: "There are no macros yet"; 17 parts selected: early exit: "There are no macros yet" |  | 20261009-005608, 20261009-005935 |
| `Dev.tab/Automate.panel/Macros.pulldown/Manage_Macros.pushbutton` | needs-dialog | no selection: runner guard: "Manage Macros needs the Navisworks window"; 17 parts selected: runner guard: "Manage Macros needs the Navisworks window" |  | 20261009-005622, 20261009-005948 |
| `Dev.tab/Automate.panel/Macros.pulldown/Macro_to_Button.pushbutton` | ok | no selection: early exit: "There are no macros yet"; 17 parts selected: early exit: "There are no macros yet" |  | 20261009-005636, 20261009-010000 |
| `Dev.tab/Reports.panel/Report_Templates.pushbutton` | needs-dialog | no selection: runner guard: "This tool asks questions, so it cannot run under pynavis run"; 17 parts selected: runner guard: "This tool asks questions, so it cannot run under pynavis run" |  | 20261009-005650, 20261009-010012 |
| `Dev.tab/Reports.panel/Scheduled_Reports.pushbutton` | needs-dialog | no selection: runner guard: "This tool asks questions, so it cannot run under pynavis run"; 17 parts selected: runner guard: "This tool asks questions, so it cannot run under pynavis run" |  | 20261009-005702, 20261009-010023 |
| `Dev.tab/Build.panel/Button_Maker.pushbutton` | needs-dialog | no selection: runner guard: "Button Maker needs the Navisworks window"; 17 parts selected: runner guard: "Button Maker needs the Navisworks window" |  | 20261009-005715, 20261009-010036 |
| `Dev.tab/Build.panel/Script_Editor.pushbutton` | needs-dialog | no selection: runner guard: "The Script Editor needs the Navisworks window"; 17 parts selected: runner guard: "The Script Editor needs the Navisworks window" |  | 20261009-005729, 20261009-010048 |
| `Dev.tab/Build.panel/Hotkey_Manager.pushbutton` | needs-dialog | no selection: runner guard: "The Hotkey Manager needs the Navisworks window"; 17 parts selected: runner guard: "The Hotkey Manager needs the Navisworks window" |  | 20261009-005744, 20261009-010100 |
| `Dev.tab/Team.panel/Extension_Manager.pushbutton` | needs-dialog | no selection: runner guard: "The Extension Manager needs the Navisworks window"; 17 parts selected: runner guard: "The Extension Manager needs the Navisworks window" |  | 20261009-005757, 20261009-010112 |
| `Dev.tab/Team.panel/Team_Sync.pushbutton` | needs-dialog | no selection: runner guard: "Team Sync needs the Navisworks window"; 17 parts selected: runner guard: "Team Sync needs the Navisworks window" |  | 20261009-005810, 20261009-010124 |
| `Dev.tab/Team.panel/Usage_Analytics.pushbutton` | ok | no selection: early exit: "Usage Analytics is off"; 17 parts selected: early exit: "Usage Analytics is off" |  | 20261009-005822, 20261009-010136 |
| `Dev.tab/Team.panel/Team_Tools.stack/Environment_Doctor.pushbutton` | ok | no selection: ran to the end (wrote output); 17 parts selected: ran to the end (wrote output) |  | 20261009-005835, 20261009-010148 |
| `Dev.tab/Team.panel/Team_Tools.stack/Playground_Settings.pushbutton` | needs-dialog | no selection: runner guard: "The settings window needs Navisworks"; 17 parts selected: runner guard: "The settings window needs Navisworks" |  | 20261009-005847, 20261009-010200 |
| `Dev.tab/Tools.panel/Unit_Converter.pushbutton` | needs-dialog | no selection: runner guard: "The Unit Converter needs the Navisworks window"; 17 parts selected: runner guard: "The Unit Converter needs the Navisworks window" |  | 20261009-005859, 20261009-010212 |

needs-dialog 77, not-runnable 2, ok 60, skipped-unsafe 1
