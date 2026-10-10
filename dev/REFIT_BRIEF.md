# Playground refit brief (second pass, after the first field click)

Playground was built headless by agents that could not run Navisworks. The owner then clicked
the very first tool, Photo Pins, and it was wrong in the field: the marker under the mouse
and the place the pin landed disagreed. Cause: the builder called `pynavis.pick.point` (the
custom pick tool, documented in the api reference) while every SHIPPED pyNavis tool that picks had
already moved to `pick.measure_point` / `pick.measure_points` (the host's own Measure tool)
with the prompt on `pynavis.banner`. The documentation said one thing, the field-proven
tools did another, and the builder followed the documentation.

That is the failure class you are hunting: **a mechanism chosen from docs or from the API
dump where a shipped, field-proven pyNavis tool already does the same job a different
way.** Your job is to make every tool in your group (a) work on the first click and
(b) behave, read and look like a shipped pyNavis tool. You own the result: fix, do not
just report.

## Read first (in this order)

1. `dev\BRIEF.md` (engine rules, API traps, UX rules; still binding).
2. the pyNavis authoring guide (`docs\authoring\` in a pyNavis checkout): `style-guide`, and the `api-reference`
   sections for the pynavis modules you touch.
3. Your group's section of `dev\CATALOG.md` (the spec) and your group's
   notes in `dev\notes\<group>.md` (the builder's own doubts: treat every
   "unverified" there as a lead).
4. Field-verified Navisworks facts (short, read all of them):
   the maintainers' private notes (not in this repo): `navisworks-search-traps.md`,
   `navisworks-viewpoint-events.md`, `navisworks-view-overlay.md`,
   `navisworks-plugin-assembly-traps.md`, `navisworks-ribbon-tabs.md`,
   `curved-face-tools.md`.
5. The shipped tools nearest to yours: `<pyNavis checkout>\extensions\pyNavis.extension\`
   (bundles and `lib\`). These are the truth about what works in Navisworks.

## Method, per tool (every bundle in your group, no sampling)

1. Read its CATALOG entry, `bundle.yaml`, `script.py`, `config.py`, and follow the imports
   into the `namo` functions it reaches. Execute it in your head as IronPython 3.4 inside
   Navisworks, on every branch: no document, no selection, cancel at each prompt, huge
   model, success.
2. **Find the shipped precedent** for each mechanism and align with it. If a shipped tool
   or a `pynavis` library function does the job, use that route, not a parallel invention:

   | Mechanism | Field-proven route |
   |---|---|
   | Click a point / an object in the view | `namo.picking.point(prompt, want_item=True)` / `picking.points(...)` (new, wraps `pick.measure_point` + banner + `faces.candidates_at`). **`pick.point` and `pick.point_then` are banned in Playground.** `pick.Unavailable` handling goes away with it |
   | Prompt or result while the user works in the view | `pynavis.banner` (see True_Distance, Clear_Clash); toast for a finished one-line result |
   | Drawing in the view | `pynavis.overlay` exactly as True_Distance and `lib\facemove.py` use it |
   | Live state, timers, event subscriptions, modeless windows | `lib\vptrackerlive.py` pattern (session holder, DispatcherTimer, guarded handlers) |
   | Ribbon manipulation | `lib\tabhider.py` |
   | Finding items | `pynavis.sets` / `pynavis.props` (never a raw `Api.Search` when sets does it) |
   | Clash data and edits | `pynavis.clash`, `clashtest`, `clashgroup` and the Clash Grouper bundle |
   | Saved viewpoints | `pynavis.viewpoints`, `viewstate`, `memory` and the Viewpoints panel bundles |
   | Sections, camera, zoom | `pynavis.section`, `view`, `lib\sectionnudge.py`, `lib\coords.py` |
   | Lengths typed by a person | `forms.ask_length` / `pynavis.lengths` |
   | Excel, exports | `pynavis.xl`, `pynavis.export` and the shipped exporters |
   | Tool settings | `pynavis.settings` / `script.get_config` + a `config.py` shaped like the shipped ones |

3. Grep every Navisworks member in `dev\api\*.txt` (exact case, static vs
   instance, overloads) and every `pynavis` member in `<pyNavis checkout>\pynavislib\pynavis\`
   (signature and return shape). The installed 2026 runtime library is identical to that folder.
4. Check the UX against the style guide: lightest surface, every outcome reported, cancel
   silent (`is None`), empty states say what to do, one undo step, counted progress with
   cancel, sentence case, no em or en dashes, no emoji, thousands separators, user words
   not API words. Tooltips read like the shipped ones: what it does, how to use it, then
   "Shift+Click for settings." only when a config.py exists.
5. Make it better where it is thin: a tool that technically runs but would embarrass a
   careful author (wrong default, pointless prompt, a window where a toast would do, a
   toast where a table is needed, a result with no next step) gets fixed. Do not
   re-architect what is sound, and do not add features the catalog does not ask for.

## Field facts worth more than the docs

* The owner's test model sits about 1,370,000 ft from the origin (shared coordinates).
  Float32 noise there is around 0.1 ft: any geometric tolerance must come from
  `pynavis.faces.tolerance_for` / `geometry.float_noise`, never a hard-coded epsilon, and
  nothing may assume coordinates are small.
* Model units are whatever `doc.Units` says (this model: feet). Sizes of things you draw
  (pins, labels, markers) are chosen in real-world terms and converted.
* Navisworks 2026, IronPython 3.4, pyNavis 1.2.0 plus the current repo library. The
  extension is now loaded in the owner's Navisworks, so every tool WILL be clicked.
* A measurement (`pick.measure_point`) carries only a point: no item, normal or snap.

## Boundaries

* Write only under this repo. Never edit anything in a pyNavis checkout, never run git, never touch `%APPDATA%\pyNavis`, never start
  Navisworks or `pynavis run`.
* Nine other agents are refitting the other groups in the same tree right now. Edit only
  your group's bundles, your group's `namo` modules, your tests, your icons module and
  your notes file. Foundation modules (everything indexed in `lib\namo\README-F1.md`,
  `README-F2.md`, `README-F3.md`, plus `picking.py`) are shared: fix one only when the bug
  is local, certain and contract-preserving, re-read the file immediately before the edit,
  and list it in your report. Anything bigger goes in your report as a foundation request.
* Tests: keep them green, add a pure-logic regression test for each real bug. Run only
  what you touched while working: `python dev\verify.py --fast -k <name>` and the smoke
  files for your windows via `powershell -NoProfile -STA -ExecutionPolicy Bypass -File
  dev\ipy.ps1 ...` as verify.py does. Do not run the full verify repeatedly (ten agents
  share the machine); run it once at the end.
* Icons: leave them unless a glyph is plainly misleading; then change the glyph function
  in `dev\icons\<group>.py` and re-run `python dev\make_icons.py --only <group>`.

## Honesty about what cannot be proven here

Nobody can click in Navisworks. For every tool, decide which it is:

* **Proven route**: it only uses mechanisms a shipped pyNavis tool already uses in the field.
* **Unproven**: it depends on an API member or host behaviour no shipped tool exercises
  (the dump says it exists; nobody has seen it work). Keep it only if there is no proven
  alternative, guard it so a failure is a clear toast and never a crash or a silent
  no-op, and list it.

## Final report (your last message; keep it under 90 lines)

1. A table, one row per tool in your group: `tool | verdict (ok as built / fixed) | what
   was wrong and what you changed | proven or unproven (which member)`.
2. Foundation requests (file, function, what and why).
3. The first three things the owner should click to check your group in Navisworks, and
   what a correct result looks like.
4. The verify summary line.

Also append the same content to `dev\notes\<group>.md` under a `## Refit pass` heading.
