# Playground engineering brief (read this first, all of it)

Playground is a second pyNavis extension: ~115 Navisworks tools built as pyNavis bundles, on a
shared Python library (`lib/namo`). It is a showcase: every tool must feel finished,
careful and expert, like the best commercial Navisworks add-ins, while obeying the
pyNavis house rules exactly. There is no Navisworks available to you: you cannot click
anything, so correctness comes from reading the real API surface, pure unit tests, and
the headless harness. Write code you would bet on.

## Where things are

| Path | What |
|---|---|
| `Playground.extension\` | THE EXTENSION. Tabs `*.tab`, panels, bundles, `lib\namo\`, `hooks\`, `startup.py` |
| `Playground.extension\lib\namo\README.md` | Module index and contracts of the shared `namo` library. Read before writing a line |
| `dev\CATALOG.md` | What each tool does, its bundle path, owner. Your section is your spec |
| `dev\api\*.txt` | Reflection dump of the Navisworks 2026 .NET API (one member per line). GREP EVERY API MEMBER YOU USE |
| `dev\tests\` | Tests. `test_*.py` run under CPython pytest AND IronPython 3.4; `smoke_*.py` build WPF under IronPython |
| `dev\icons\<group>.py` | Your icon glyphs (see Icons) |
| `dev\notes\<group>.md` | Your in-app verification notes (see Deliverable) |
| `<pyNavis checkout>\` | The pyNavis framework. READ-ONLY reference. Never edit anything there |
| `<pyNavis checkout>\docs\authoring\` | The pyNavis authoring guide: `bundle-yaml`, `api-reference` (the `pynavis` library), `style-guide`, `cookbook`. Read the style guide and the api-reference sections you use |
| `<pyNavis checkout>\pynavislib\pynavis\*.py` | The `pynavis` library source. Read the module before you use it |
| `<pyNavis checkout>\extensions\pyNavis.extension\` | The 30 shipped tools: the style reference. `lib\` there shows real API patterns (vptrackerlive.py: events, timers, session holders; tabhider.py: AdWindows ribbon; coords.py, facemove.py: picks and overlays) |
| `<pyNavis checkout>\src\PyNavis.Runtime\Forms\DesignSystem.cs` | Public static WPF design system usable from IronPython (Tokens, Text, Primary/Secondary buttons, GroupFrame, InputField, SlimScroll) |

## Hard boundaries

* Write ONLY inside this repo, and only in the paths your assignment owns (your
  panels, your `lib\namo\` modules, your `dev\icons\<group>.py`, your tests, your notes).
  Other agents are working in the same tree at the same time. If you need a change in a
  module you do not own, do not edit it: work around it locally and write the request in
  your notes file.
* Never touch a pyNavis checkout, `%APPDATA%\pyNavis\config.json` or the
  installed pyNavis. Never run git. Never commit.
* Never start Navisworks (`Roamer.exe`) or `pynavis run`.
* Python for dev scripts: plain `python` (CPython 3.11 with pytest, Pillow, openpyxl).

## The engine: IronPython 3.4.2 (non-negotiable rules)

Every file under `Playground.extension` runs on IronPython 3.4 inside Navisworks. The harness
proves it compiles and that pure code behaves the same on both engines.

* **Dicts are NOT insertion ordered on IronPython 3.4** (measured: keys 'zyxabc' iterate
  as 'zacbyx'). Never depend on dict order for output, UI or files: sort, or keep lists of
  pairs, or `collections.OrderedDict`. `json.dumps(..., sort_keys=True)` for stable files.
* No f-strings (house style), no type annotations, no walrus, no async, no `{**a}` /
  `[*a]` unpacking in literals, no `math.isclose`, no `subprocess.run` (use `Popen` /
  `check_output`), no `bytes.hex()` (use `binascii.hexlify`), no `typing`, no `secrets`,
  no `os.scandir`. `%` formatting everywhere.
* `str` is a .NET string (unicode). Write files with `io.open(path, 'w', encoding='utf-8')`
  or binary `'wb'` with bytes. JSON: `json.dump(..., indent=2, sort_keys=True)`.
* .NET interop: `import clr; clr.AddReference('System.Drawing')`; `List[T]` uses `.Add`;
  events `obj.Changed += handler` with `handler(sender, args)`; delegates via
  `from System import Action`; enums as `Api.ImageGenerationStyle.Scene`; .NET
  exceptions are caught by `except Exception`. Iterate collections directly
  (`for item in collection`), use `.Count` for size.
* `from pynavis._api import Api, Application` is how shipped pyNavis code reaches the API
  (also `ComApi`, `ComApiBridge` via `pynavis._com`). Clash: `from pynavis import clash`
  (it binds `Document.GetClash()`). Timeliner: see `namo/` README or the dump
  (`DocumentTimeliner.TimelinerInstance(doc)` / `doc.Timeliner`).
* Module globals in `lib\` are reset before EVERY run (pyNavis drops lib modules from
  `sys.modules` so edits apply without Reload). State that must outlive a run (open
  windows, timers, event subscriptions, caches) lives in a session holder:
  `namo.session.holder('<thing>')` (a module object under a `sys.modules` key that
  is not under lib).
* A handler that fires after `script.py` returned (modeless window click, timer, event)
  is "outside a run": use `me = script.bind()` captured during the run for
  config/data, never `script.get_config()` inside the late callback.
* `__name__` is never `'__main__'`. Put work at module level in `script.py`, or define
  `run()` and call it at module level.
* Never touch the Navisworks API from a worker thread. Polling = `DispatcherTimer` on the
  UI thread. Long loops = `forms.progress` with `p.check()` for cancel.
* A .NET exception escaping an event handler on the UI thread can take Navisworks down:
  wrap every late callback body in try/except and log via a pinned logger.

## The Navisworks API: rules that cost real debugging time

* **Grep the dump for every member before using it**:
  `grep -n "ModelGeometry::ActiveColor" dev/api/Autodesk.Navisworks.Api.txt`. Exact case.
  If it is not in the dump it does not exist. Note static vs instance and the overload
  signatures shown.
* Prefer `pynavis` library functions where they exist (`sets`, `props`, `clash`,
  `clashtest`, `viewpoints`, `viewstate`, `section`, `geometry`, `export`, `memory`,
  `view`, `selection`, `overlay`, `pick`, `xl`, `lengths`). They encode field-measured
  traps. Read the api reference for each.
* One undo step per user action: wrap document edits in
  `pynavis.viewpoints.transaction(name)` (a `Document.BeginTransaction` context manager)
  unless the library call already does.
* `SavedItemCollection.Remove(item)` DISPOSES the removed item (move = remove+add breaks).
* Clash results: never edit the results tree per item for large counts (TestsMove ~1-3 s
  each). Read with `clash.snapshot_results` / `namo.clashdata`. Restructure only via
  `clash.apply_plan` style rebuild + `TestsReplaceWithCopy`. `TestsEditTestFromCopy` is
  definition-only (ignores results). Per-result field edits that DO exist:
  `TestsEditResultStatus/AssignedTo/Description/Priority/Comments/...`,
  `TestsEditDisplayName` (fine for hundreds; for tens of thousands measure your design).
  `TestsImageForResult(result, style, w, h)` returns a System.Drawing.Bitmap and
  `TestsViewpointForResult(result)` a Viewpoint: use them.
* A fresh `Api.Search` matches nothing until `search.Selection.SelectAll()`; use
  `pynavis.sets` instead of raw searches. OR = one full model walk per group. FindAll
  always walks the whole model (~3 s on 1.75 M items).
* `Document.GenerateImage(ImageGenerationStyle, w, h, sectioning)` and
  `View.GenerateImage(...)` return System.Drawing.Bitmap. This is THE image route
  (`namo.images` wraps it). `pynavis.export.viewpoint_image` is an unverified COM guess.
* `ModelItem.FindFirstObjectAncestor()` gives the "object" level users think of as an
  element. Revit IDs live in properties: categories 'Element ID' (Value), 'Element'
  (Id, UniqueId, Category...), 'Revit Element'... read with `pynavis.props`, use
  `namo.items.revit_ids`.
* Element ID searches: the nested parts under a family instance carry the TYPE's id;
  AND in `has_category('LcRevitData_Element', by_display=False)` to match real elements
  (see `pynavis.sets.find_first` notes).
* Float32 geometry: COM vertices are single precision; positions far from origin carry
  noise (`pynavis.faces.tolerance_for`).
* Units: `doc.Units` (enum name like 'Feet', 'Millimeters'). Every user-facing length goes
  through `pynavis.lengths` / `forms.ask_length` (people type 1' 6 1/2", 25mm...).
  `namo.units` converts. Never assume meters.
* Permanent overrides: `doc.Models.OverridePermanentColor(items, Api.Color(r,g,b))`
  (0..1 floats), `OverridePermanentTransparency(items, 0..1)`, `ResetAllPermanentMaterials`.
  Reading per-item colour: `item.Geometry.ActiveColor` / `PermanentColor` exist in the
  dump but are UNVERIFIED in-app (older field notes say overrides were unreadable via
  COM). Treat as best-effort and say so in notes.
* Hidden: `doc.Models.SetHidden(items, bool)`, `ResetAllHidden()`, item `.IsHidden`
  (own flag only: check ancestors).
* Per-document data INSIDE the NWF/NWD: `doc.Database` (SQLite) via `namo.docdb`.
* Never assume a clash test, grid system, level, Timeliner task or model exists: every
  empty case gets a toast that says what to do.

## UX rules (pyNavis design system, enforced by review)

Read the pyNavis style guide. The non-negotiables:

* Lightest surface that carries the information: toast (one line + optional detail) >
  forms prompt > output window (tables, charts, links) > custom WPF window/dock pane.
* Report every outcome (success, failure, nothing-to-do). Cancel is silent: `None` from
  prompts / `False` from confirm -> return with no toast. Test `is None`, not falsiness.
* NEVER `print()` in bundle scripts (opens an empty output window). Status = `toast`.
* Copy: sentence case; no em dashes or en dashes ANYWHERE (strings, tooltips, comments
  shown to users); no emoji; plain verbs; thousands separators (`'{:,}'.format(n)`); say
  what the user sees ("3 viewpoints", not "3 SavedItems"); name what failed and what to
  do next in one sentence.
* Counted progress (`forms.progress`) with cancel for anything that can take more than a
  couple of seconds. Budget and sample huge models rather than freezing for minutes, and
  tell the user when results are sampled.
* Custom windows: build with `namo.ui` (form builder, table window, modeless windows with
  keyboard interop) which follows DesignSystem tokens: solid surfaces, 32px controls,
  8px gaps, 24px padding (16px data-dense), accent only on primary action / selection
  rail / focus ring, no gradients/glass/emoji/pill soup. Light and dark theme.
* Shortcuts: only the chords assigned in CATALOG.md. Never invent others.
* Settings: Shift+Click `config.py` where a tool has real options (use
  `script.get_config/save_config` or `namo.config` for Playground-wide settings). A bundle
  with config.py shows a Shift marker on the ribbon, so only add one when it earns it.

## Bundle rules (checked by dev/check.py and the real parser)

* Folder names: `Title_Words.pushbutton` (underscores become spaces; no numeric prefix).
  The bundle path in CATALOG.md is authoritative; ask (in notes) before renaming.
* Every container (panel, stack, pulldown, slideout) has `bundle.yaml` with a `layout:`
  list naming EVERY child, in ribbon order. Stacks: exactly 2 or 3 pushbuttons.
  Pulldowns: title, tooltip, the four icons, and only `*.pushbutton` children.
* Every pushbutton-shaped bundle: `script.py` with a one-sentence module docstring,
  `bundle.yaml` with `title:` (use `\n` to break long large-button captions onto two
  lines, like `title: Select\nSimilar`) and `tooltip:` (one or two specific sentences:
  what it does and to what), `context:` when it needs a document/selection/etc
  (`doc`, `selection`, `clash-tests`, `clash-results`, `viewpoints`, `selection-sets`,
  `multi-model`, combined with `& | !`).
* Keep script.py thin: gather input, call your lib module, toast the result. Logic lives in
  `lib\namo\<module>.py`, split into a pure half (unit tested) and an API half.
* Report tools (CATALOG marks them `report: <id>`) implement `lib\namo\rep_<id>.py` with
  the contract in `namo/reports.py` so Report Templates, Scheduled Reports and macros can
  run them without dialogs.
* Hooks: do not create `hooks\*.py` files. If your tool needs an event, implement
  `lib\namo\hk_<name>.py` with `handle(name, event)` for the handler name already
  registered for you in `lib\namo\hooks.py` (CATALOG lists yours). Fast, guarded, never
  raises.

## Icons

Your glyphs go in `dev\icons\<group>.py` (group = your assignment id, e.g. `select_find`):

```python
# -*- coding: utf-8 -*-
"""Glyphs for the Select and Find panels."""
import math
import make_icons as pn          # pyNavis' generator: Ctx helpers and shared marks

def ic_select_similar(c):
    if c.small:
        ...                      # simplified 32 px drawing, heavier stroke (c.w is already heavier)
        return
    c.rrect(14, 18, 50, 54, rad=6)                  # the THING in ink
    c.rrect(46, 42, 82, 78, rad=6, color=c.t['accent'])   # the ACTION in accent
ICONS = {'Model.tab/Select.panel/Select_Similar.pushbutton': ic_select_similar}
TOGGLES = {}        # '<path>.toggle': (off_fn, on_fn)
DOCKPANE_ON = {}    # '<path>.dockpane': on_fn
```

Canvas 0..96, drawn at 4x. `c.line(pts, color=None, w=None)`, `c.circle(cx, cy, r, color,
w, fill)`, `c.disc(cx, cy, r, color)`, `c.rrect(x0, y0, x1, y1, rad, color, w, fill)`,
`c.poly(pts, color, fill, w)`, `c.arrow_v(x, y0, y1)`, colours `c.t['ink']`,
`c.t['accent']`, `c.t['paper']` (and `c.t['alert']`, reserved for Model Wipe only).
Shared marks from `pn`: `tray`, `spark` (collision), `plus`, `dots`, `eye`, `brackets`,
`sight`, `gauge`, `needle`, `tilted_box`, `sparkle`, `_pin`... read
`<pyNavis checkout>\tools\make_icons.py` for the vocabulary and match its weight and
restraint: one idea per glyph, ink = the thing, accent = what the tool does to it. Small
(32 px) variants are separate simplified drawings. Pulldowns need icons too.
Generate with `python dev/make_icons.py --only <group>`; review your glyphs with
`python dev/make_icons.py --only <group> --sheet dev/notes/<group>-icons.png` and LOOK at
the sheet (Read the PNG) before you finish. Never hand-edit a PNG.

## Testing and verification (all must pass before you report)

1. Pure modules: tests in `dev\tests\test_<module>.py`, plain `def test_...():` + bare
   asserts, helpers from `_compat` (`raises`, `approx`, `tmpdir`, `SkipTest`). Cover the
   logic that decides results (parsing, planning, grouping, formatting, file writers).
   Writers (xlsx, pdf, bcf, ifc, html, png) get round-trip/structure tests (openpyxl,
   Pillow, zipfile, xml parsing under CPython; skip those on IronPython via `_compat`).
2. Every WPF window/pane you build gets `dev\tests\smoke_<thing>.py` that constructs it
   with sample data under IronPython (never `ShowDialog()`); proves XAML parses and the
   Python wiring holds.
3. `python dev/verify.py` (or `-k <your test prefix>` while iterating): check.py,
   pytest, IronPython compile, IronPython tests, WPF smoke, real BundleParser. Your
   files must produce zero problems. Problems in other agents' areas are not yours.
4. Re-read each script.py top to bottom as Navisworks would execute it: imports exist,
   every name is defined, every API member is in the dump with the right
   static/instance and arguments, every branch toasts or exits silently on cancel.

## Deliverable

* The bundles, modules, tests and icons for your assignment, all verified.
* `dev\notes\<group>.md`: (1) every tool with one line on what it does; (2) a checklist
  of things only an in-app click can confirm (API behaviours you inferred, option names,
  enum values you could not test), phrased as steps for the user; (3) requests for
  shared modules you do not own, if any.
* Final message: the notes file content plus test counts. Be honest about anything
  unfinished; never claim something works in Navisworks, only that it is verified
  headlessly.
