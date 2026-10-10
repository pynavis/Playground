# G3 look: the Look panel (tab Model)

Built by agent G3. Everything here is verified headlessly only (CPython pytest,
IronPython 3.4 tests, IronPython WPF smoke, the real pyNavis BundleParser). Nothing
has been clicked in Navisworks yet.

Ribbon order: Color by Property, Color Presets, Trade Ghost, Status Painter,
Look Tools (stack: Legend Maker, Match Appearance, Exploded View), View Tools (stack:
Reset Overrides, Background), Presentation Mode (toggle), Exit Presentation
(nobutton, Ctrl+Alt+F11, no ribbon presence).

## 1. Tools

| Tool | What it does |
|---|---|
| Color by Property (#76) | Form (scope, how many values get a color, grey or untouched for the rest, clear earlier colors, ghost the rest), counted walk of the scope, property picker sampled from 300 items, counted read, then ONE undo step paints value groups; the legend (swatch, value, count, share) goes to the output window and the scheme is remembered for Legend Maker and Presets. A value keeps its color between runs (per-property memory). |
| Color Presets (#77) | Quick switch: Apply a preset (one native search per value when the values are plain text, else one model walk; repaints in one undo step, names values with no match), Save the last scheme (asks a name, confirms a replace), Manage presets (table: Rename, Delete, Export, Import, Open folder). Presets are JSON files in `<team_root>\presets\colors`. |
| Trade Ghost (#78) | Chooser of trades (models grouped by file name rules) plus "Current selection"; everything else fades (config 85%, optional grey) in one undo step. A second click offers Change focus (resets exactly what it ghosted, then ghosts the new rest) or Clear ghost (resets exactly those items). Shift+Click: transparency and grey. |
| Status Painter (#79) | Quick switch: Paint by status (one native search for the status property, then paints each status's color, Not started back to model colors, reports values that are no status), Set status of selection (merges into the custom tab, repaints, chunked with cancel above 250 items), Legend (counts per status into the output window). Shift+Click: tab, property, colors per status, extra statuses. |
| Legend Maker (#83) | Renders the last scheme as a 2x PNG legend (white paper, swatches, labels, counts, shares, total) where you choose, shows it in the output window, and optionally saves a viewpoint "Legend - <title>" holding the colors (override snapshot) with the legend text as its comment. |
| Match Appearance (#103) | Source = first selected item (or pick one). Reads its color and transparency from the override snapshot (nearest overriding ancestor per part), filling gaps from the geometry's own look; asks with a small form when it cannot tell. 2+ selected: paints the rest in one step. Otherwise a pick loop paints each clicked object (one undo step each) until Esc. |
| Exploded View (#80) | Form (spread 1.05 to 10x, direction: all / up and down / X / Y, move the selected items or their whole models), one transaction of permanent translations. Records offsets and read-back centers per document. A second click offers Collapse (moves back only items still where it left them) or Explode more. A record that no longer matches the model (undone) is dropped and the click starts afresh. |
| Reset Overrides (#56) | Multi-pick (remembered): colors and transparency, temporary colors, hidden items, moved items (asks to confirm), required and frozen flags; one transaction; toasts what was reset. |
| Background (#118) | Click steps White, Light gradient, Dark gradient, Black, Horizon (from the current one when Navisworks reports it). Shift+Click: pick a preset, a custom color or a custom gradient. |
| Presentation Mode (#119) | Toggle. On: ribbon minimized to its tabs, add-in dock panels closed, window maximized, optional background preset (Shift+Click). Off, Exit Presentation (Ctrl+Alt+F11) or a click on the tab's Exit Presentation button: each change put back, only what it changed. State in an AppDomain slot, so it survives Reload. |

Deviation from the catalog: Exploded View uses `context: doc`, not `selection`. With
`selection` the button greys out when nothing is selected, so a user could not reach
Collapse after deselecting. The script says "Select the objects to spread apart" when
there is no selection and no explode to collapse.

Modules (all mine): `colorize` (engine, presets, legend HTML, preset manager window),
`legend` (pure layout + WPF PNG render + legend viewpoint), `explode`, `presentation`,
`look_status`, `look_ghost`, `look_tools` (Match Appearance, Reset Overrides,
Background). Pure halves are unit tested on both engines; the API halves are tested
through the shared fake Navisworks layer.

Data kept: color memory (global store `colorize-memory`), last scheme
(`paint.remember_scheme`), presets (`<team_root>\presets\colors\*.json`), ghost record
(session + document store `trade-ghost`), explode record (session + document store
`exploded-view`), Presentation state (AppDomain slot `Playground.PresentationMode`), per-tool
settings through `script.get_config`.

## 2. In-app checks (please click these, in this order)

Use a federated model with several trades (file names like `...MECH...`, `...STR...`),
saved as an NWF, with some items hidden.

1. **Color by Property, visible items.** Hide one model. Run it, scope Visible items,
   pick `Element > Category` (Revit) or `Item > Layer`. Expect a counted progress
   window, the property picker with "Found on" counts, colors on the visible model only,
   the legend in the output window, a toast "Colored N items by Category". One Ctrl+Z
   must remove all of it (check the Undo list shows one "Color by property" entry).
2. Run it again on the same property: every value keeps the color it had.
3. Run it with Current selection and "Clear earlier colors first": colors outside the
   selection must survive. Then with "Ghost everything that is not colored": the rest
   turns 85% transparent.
4. Big model timing: Whole model on the largest federation you have. Note the seconds
   for "Collecting items" and "Reading" (both cancellable). This walk reads one
   property per object in Python; if it is too slow, tell me the item count and time.
5. **Color Presets > Save the last scheme**, then Reset Overrides, then **Apply a
   preset**: the same colors come back. Confirm in the log whether the native search
   path found the values (a text property like Category should; a numeric property
   falls back to the walk). Check a value missing from the model is named in the toast.
6. **Manage presets**: rename, export to Desktop, import it back (gets " (2)"), delete,
   Open folder.
7. **Trade Ghost**: tick one trade. Others go grey and 85% transparent, one undo step.
   Click again > Change focus to another trade: the first trade must become solid
   again. Click again > Clear ghost. Repeat with "Current selection" ticked. UNVERIFIED:
   whether resetting a model root (what Clear does) also clears colors that Color by
   Property put on that model's elements. Tell me what you see.
8. **Status Painter > Set status of selection** on a few items, choose Issue: they turn
   red and the Properties panel shows a `Playground` tab with `Status = Issue` (other
   properties already on that tab must survive). Undo: check whether it is ONE undo
   step (the write goes through COM; pyNavis notes this is unverified). Then select
   300+ items and set Installed: a progress window appears; try Cancel mid-way.
9. **Status Painter > Paint by status** and **Legend**. Then Shift+Click, point it at a
   Revit tab property (e.g. `Element > Phase Created`): Set status must refuse with
   "is a tab from the model" (relies on user tabs having the internal name from
   `LcOaPropOverrideCategory.GetInternalCatName()`, fallback `LcOaPropOverrideCat`).
10. **Legend Maker** after a coloring: save the PNG, open it (white, crisp at 2x), check
    the output window shows it at normal size. Tick "Also save a viewpoint": a viewpoint
    "Legend - <title>" appears with the legend text as its comment. UNVERIFIED: that
    the viewpoint made from `CaptureRuntimeOverrides()` brings the colors back when
    recalled after a Reset Overrides; and that `DisplayName` can be set on it.
11. **Match Appearance**: color one object with Color by Property, select it plus
    three others, run: the three take its color (toast names the color). UNVERIFIED:
    `SavedViewpoint.GetAppearanceOverrides().MaterialOverrides` returning the live
    overrides (Item, Color, Transparency). Then select only an uncolored object and run:
    you get its own model color (`ModelGeometry.ActiveColor`, unverified) or the small
    form if Navisworks reports nothing. Then the pick loop: click several objects, Esc.
12. **Exploded View**: select 6 objects, spread 2x, all directions. They move apart in
    one undo step. UNVERIFIED and important: whether `ModelItem.BoundingBox()` reflects
    a permanent transform (the record stores `tracks`; if it does, Collapse refuses to
    move items that were moved or undone since). Click again > Collapse: everything goes
    back. Explode, Ctrl+Z, click again: it must start a fresh explode, not offer
    Collapse (needs the bounding box to follow the move). Try "Their whole models"
    with one item selected from each of two models (model roots are moved).
13. **Reset Overrides** with each kind; "Moved and rotated items" asks first. Check the
    toast wording and that one Ctrl+Z undoes it (temporary colors excepted).
14. **Background**: click five times, it cycles; check whether it starts after the
    background already showing (that needs the Interop read `LcOpState.GetActiveInstance`
    + `LcOpBackgroundElement.Get(state).GetSettings()`; if it always starts at White the
    read fails and only this session's last preset is used). Shift+Click a custom
    gradient.
15. **Presentation Mode**: open a pyNavis dock panel first. Click: ribbon minimizes to
    its tabs (`RibbonControl.AutoHideMode = HidePanelBar`, unverified that Navisworks
    keeps it and does not reset it on idle), the panel closes
    (`Application.Gui.SetDockPanePluginVisibility(record.Id, False)`, unverified that
    it takes `PluginRecord.Id`), the window maximizes. Then: press Ctrl+Alt+F11 and
    everything returns; enter again, click the Model tab and press Exit
    Presentation on the pop-up panel; enter again and click Reload while presenting,
    then Ctrl+Alt+F11 must still restore (the state survives in the AppDomain).
    Shift+Click, set Background "Dark gradient", enter and leave: the original
    background must return (needs the Interop read in step 14; if it fails the toast
    says the background stayed).
16. Close Navisworks while presenting, reopen: the ribbon may start minimized (see the
    request below). Double-click any ribbon tab restores it.

## 3. Requests for modules I do not own

1. **hooks.py (foundation):** add `('app-closing', 'hk_presentation')` to `HANDLERS`
   and let G3 own `lib/namo/hk_presentation.py`:

   ```python
   def handle(name, event):
       """Puts the ribbon, panels, window and background back if Navisworks closes
       while Presentation Mode is on."""
       try:
           from namo import presentation
           if presentation.is_on():
               presentation.leave()
       except Exception:
           pass
   ```

   Without it a session closed while presenting can start the next one with a
   minimized ribbon and closed add-in panels (Navisworks remembers both).
2. **README.md (foundation):** add my modules to the index: `colorize` (color by
   property engine, presets, legend data; API+pure), `legend` (PNG legend; WPF+pure),
   `explode` (exploded view; API+pure), `presentation` (presentation mode; API+pure),
   `look_status`, `look_ghost`, `look_tools` (API+pure).
3. **paint.ghost (F3), optional:** return the ghosted items (or offer
   `ghost_items(keep)`), so a caller can record exactly what it ghosted. Trade Ghost
   works around it by calling `items.complement` + `paint.apply` itself.
4. **dev/tests/test_items.py FakeNav (F3), optional:** its fake `transaction` records
   every nested call, while the real `pynavis.viewpoints.transaction` ignores a
   transaction opened inside another. My tests patch in a nesting-aware fake
   (`test_colorize.fake`); folding that into FakeNav would let other agents assert
   "one undo step" directly.

## Refit pass

Second pass after the first field click (2026-10-05). Every bundle in the Look panel was
re-read against the shipped pyNavis tools and library. Still headless: nothing below has
been clicked in Navisworks.

| Tool | Verdict | What was wrong, what changed | Proven or unproven |
|---|---|---|---|
| Color by Property | fixed | Scope now defaults to the selection whenever one exists (catalog rule) and still remembers Visible or Whole model for the other runs. A whole-model "Clear earlier colors" also wiped Trade Ghost's fade but left its record, so the next Trade Ghost click offered to clear nothing: the record is now dropped. Empty Visible scope wording no longer claims everything is hidden. | Proven (transaction, OverridePermanentColor family, props.get). The Visible scope trusts `IsHidden` on the item and its ancestors (BRIEF rule): see check 2. |
| Color Presets | ok as built (same ghost-record fix through `colorize.apply`) | Finds values with `pynavis.sets`, falls back to a walk. | Proven |
| Trade Ghost | fixed (tooltip) | Tooltip ends "Shift+Click for settings." like the shipped ones. | Proven. Unverified behaviour: whether resetting a model root also clears colors on its elements. |
| Status Painter | fixed (tooltip) | Same tooltip ending. Writes through `pynavis.props.set_custom`. | Proven route; one undo step over the COM write is unverified in pynavis itself. |
| Legend Maker | ok as built | Viewpoint route is the shipped Copy State one (`CaptureRuntimeOverrides`, `DisplayName`, `AddCopy`). | Proven |
| Match Appearance | fixed | KNOWN DEFECT: called the banned `pick.point` twice. Both clicks now go through `namo.picking.point(prompt, want_item=True)` (Measure tool, prompt on the banner); `pick.Unavailable` handling is gone. A click on nothing or on the source says so in the next banner prompt instead of silently looping. The toast now says where the look was read from ("its color override" / "its own model color") so a wrong read shows. The override snapshot is filtered to the item's own chain instead of indexing every colored object. | Click: proven. Color read: UNPROVEN (`SavedViewpoint.GetAppearanceOverrides().MaterialOverrides`, then `ModelGeometry.ActiveColor/ActiveTransparency`). pyNavis measured that no per-item API exposes overrides and that the snapshot is the only readable form, so this is the right route, but nobody has read its contents in the field. When neither answers, a small form asks for the look: never a crash or a silent no-op. |
| Exploded View | fixed | (1) The drift tolerance was a 16x world-magnitude guess: 1.3 ft on the owner's model, so a small explode or an undo went unseen. Now one float32 step at the largest coordinate (the `geometry.float_noise` worst case, about 2 in there). (2) When bounding boxes do not follow a move (`tracks` not True) an undo cannot be detected, and Collapse by inverse offsets after Ctrl+Z would have thrown the items somewhere new: Collapse then resets those items' transforms instead (`ResetPermanentTransform`, the `pynavis.geometry.reset_transform` call), which is right whether or not the explode was undone. (3) "Spread 1.05x" printed as "1.1x". | Move and undo: proven (`OverridePermanentTransform` in one transaction, exactly `pynavis.geometry.translate`). UNPROVEN: `ModelItem.BoundingBox()` following a permanent transform; moving a model root with it. |
| Reset Overrides | ok as built | One transaction, clears the ghost and explode records. | Unproven members with no shipped user: `ResetAllTemporaryMaterials`, `ResetAllPermanentTransforms`, `ResetAllRequired`, `ResetAllFrozen` (documented API, plain calls) |
| Background | ok as built | | UNPROVEN: `Document.SetPlainBackground/SetGraduatedBackground/SetHorizonBackground` (documented API; failure is a toast) and the Interop read of the current background (failure falls back to this session's last preset). |
| Presentation Mode | fixed | Dock panels were closed with `Application.Gui.SetDockPanePluginVisibility`, which no shipped code uses; now `DockPanePlugin.Visible` on the loaded plugin, the switch pyNavis' own panel buttons use (PaneRegistry), and a plugin nobody loaded is never loaded. The ribbon mode is read back after it is set and the toast says so if it did not take; a failed maximize is now said too. Tooltip had a colon inside a YAML value and no settings sentence. | Panels: proven. UNPROVEN: `RibbonControl.AutoHideMode = HidePanelBar` (no shipped tool minimizes the ribbon; `tabhider.py` only removes tabs, which cannot clear the panel bar), `user32.ShowWindow` through ctypes with a window handle. All guarded; state lives in an AppDomain slot like Hide Tabs, and the app-closing hook restores. |
| Exit Presentation | ok as built | | Same as Presentation Mode |

### Foundation requests

1. `namo/items.py` `visible()` and the BRIEF rule "IsHidden is the item's own flag, check ancestors":
   `pynavis.view.isolate` (shipped, field-proven) hides every model root and then unhides the
   kept items, and its docstring says Navisworks resolves visibility at the leaf. If a kept
   item's root still reports `IsHidden` True after that, every "visible items" scope in
   Playground (mine is `colorize.visible_objects`) finds nothing after an Isolate. Needs one
   in-app probe (check 2 below), then one shared rule.
2. `namo/paint.py` `read_color`: its docstring still calls COM the doubt; the real doubt is
   whether `ActiveColor` reflects an override. No code change asked.
3. `dev/tests/test_items.py` FakeNav: give the fake `transaction` nesting awareness and add
   `pynavis.geometry` and `pynavis.memory` fakes (I patch them per test).

### First three clicks

1. **Match Appearance.** Color something with Color by Property, select one colored object,
   click Match Appearance. Correct: Navisworks switches to its own Measure tool with its own
   snap marker, the prompt "Click an object to paint it #RRGGBB" sits on the bar along the
   bottom, each clicked object takes the color exactly where the marker was, the prompt
   counts up, Esc ends with a toast "Painted N objects like <name>" whose second line ends
   "read from its color override". If a form asks for the color instead, the override read
   failed: tell me.
2. **Color by Property after an Isolate.** Isolate a few objects with pyNavis Isolate, then
   Color by Property with Visible items. Correct: only the isolated objects are colored, one
   "Color by property" entry in Undo. If it says "No visible item was found", foundation
   request 1 is real.
3. **Exploded View, then Ctrl+Z, then Exploded View again.** Select six objects, spread
   1.5x. Correct: they move apart, one Undo entry. After Ctrl+Z the next click must open the
   explode form again (not Collapse / Explode more). Then explode and click again, Collapse:
   everything returns, one Undo entry. If Collapse is offered after the Ctrl+Z, bounding
   boxes do not follow moves; Collapse is still safe (it resets those items' transforms).

Then Presentation Mode: ribbon shrinks to its tab row, open pyNavis panels close, window
maximizes; Ctrl+Alt+F11 puts all three back.

### Verify (full run, end of the refit pass)

`check ok (0 problems), pytest 1,568 passed / 1 failed / 18 skipped, ipy compile ok, ipy
tests 1,574 passed / 0 failed, WPF smoke 115 passed / 0 failed, BundleParser ok, fresh
imports ok, pyflakes ok`. The one CPython failure is
`test_publish.py::test_history_record_and_toast_text` (the Publish panel, another group,
being edited at the time); every Look test passes on both engines.
