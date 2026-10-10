# G11 dev_team: the Dev tab's Automate, Build, Team and Tools panels

Built by agent G11. Everything here is verified headlessly only (CPython pytest,
IronPython 3.4 tests, IronPython WPF smoke builds, the real pyNavis BundleParser, and
round trips through pyNavis' own `PyNavisConfig.Load`, `ChordParser`, `ShortcutMap`,
`BundleKeys` and `BundleParser` under IronPython). Nothing has been clicked in
Navisworks yet.

Ribbon order (tab Dev): Automate (Command Palette, Record Macro toggle, Macros
menu: Play Macro, Manage Macros, Macro to Button), [Reports, G10], Build (Button Maker,
Script Editor, Hotkey Manager), Team (Extension Manager, Team Sync, Usage Analytics,
stack: Environment Doctor, Playground Settings), Tools (Unit Converter).

## 1. Tools

| Tool | What it does |
|---|---|
| Command Palette (#100, Ctrl+Shift+P) | Modal, keyboard-first. Ranks (title matches first, then path and tooltip, recently used first) every pyNavis button of every extension incl. shortcut-only ones, dock panels, url/link buttons, every native ribbon command (AdWindows walk), saved viewpoints ("Go to view: ...") and selection sets ("Select set: ..."). Shows each chord. Enter closes, then runs: bundles and native commands are deferred until the palette's run released the RunGate; views and sets apply at once. A button the ribbon greys out (`context:` false) is listed but refused with "X needs a selection." in the status line. MRU in the local global store `palette-mru`. While a macro records, native commands, views and sets run from here are recorded too. |
| Record Macro (#99, toggle) | On: a session flag; `hk_macro` (after-command) appends each pyNavis command with its gap, ignoring the macro tools and the palette. Off: asks a name (Cancel keeps the steps as "last recording", saved later from Manage Macros), confirms a replace, saves to `namo.templates` tool `macros` (team-shared when a shared folder is set). Title/tooltip switch to Stop Recording while on. |
| Play Macro | Picks a macro and plays it: each step starts once no pyNavis script holds the RunGate, command steps run through `namo.ribbon` like a click, waits and questions are their own steps. Stop on error per macro (default on; a step that raised leaves a traceback in pyNavis' FailureLog). Clicking it again while playing offers Stop. One toast at the end (finished / finished with N errors / stopped at step N). |
| Manage Macros | Window: macros (rename, duplicate, delete, export, import, save last recording) and their steps (move up/down, remove, add a pause, add a question, add any command: pyNavis button, native command, view or set); "Stop at the first step that fails"; Play. Edits save at once. Says native commands cannot be recorded from the ribbon. |
| Macro to Button | Picks a macro, then a short form (name, tooltip, tab, panel, shortcut checked for clashes, icon), writes a pushbutton in `%APPDATA%\pyNavis\extensions\MyTools.extension` whose script plays the macro by name, then Reloads. |
| Button Maker (#109) | Form: name (`\n` allowed), tooltip, script (selection tool, report, toggle templates, or your own .py), tab and panel (existing ones reused case-insensitively, new ones created with `layout:` lists), shortcut (pyNavis grammar, Ctrl-or-Alt rule unless allowBareKeys, clash check against every resolved chord), icon (two letters or a glyph on the accent colour rendered with WPF in all four sizes/themes, eight for a toggle, or a PNG you pick). Writes extension.yaml/tab/panel/bundle files atomically, Reloads, toasts where it went. |
| Script Editor (#110) | Modeless, single instance, survives Reload. Left: every loaded extension you can write to (pyNavis' own extension excluded) as a keyboard tree with a filter. Right: Consolas editor with a line-number gutter, Tab/Shift+Tab (block indent), Enter keeps indent (+4 after a colon, -4 after return/pass/...), Ctrl+S save (keeps the file's line endings; .py compiled on save, the error line marked red in the gutter), Ctrl+F/F3 find, Ctrl+G go to line, F5 save + run the bundle (config.py runs the Shift+Click action), Ctrl+Space or "." completion (keywords, builtins, names in the file, imported pynavis modules via dir(), Navisworks API types by reflection: `doc.`, `item.`, `Api.`, `Application.ActiveDocument.Models.` resolved member by member, cached for the session). Asks before discarding unsaved edits. |
| Hotkey Manager (#111) | One table of every pyNavis bundle (current chord resolved like pyNavis, author default, Custom / Turned off / Changed / Taken by X) and every native ribbon command. Chords are recorded with pyNavis' own ChordRecorder (Backspace clears), Clear, Reset to default, a "with a shortcut" filter. Save is enabled only when something changed and no CHANGED row is in a conflict (old conflicts between untouched commands are shown, never block). Bundles: config.json `shortcuts.bindings` changed for exactly those keys (NN_ spellings of the same key replaced, default-equal chords removed, null for a disabled default, empty sections removed, order and every other key kept, JsonPretty's layout). Native commands: generated `*.nobutton`s in `MyTools.extension\MyTools.tab\Hotkeys.panel` (plus a visible Hotkeys button that opens this manager); cleared ones move to `%APPDATA%\pyNavis\playground\trash`. Then Reload. |
| Extension Manager (#122) | Registry JSON (Shift+Click: URL or file; default `playground-team\extension-registry.json` or `extension-registry.json` in the team folder, else a message saying how to set one). Table of registry and installed extensions (Not installed / Installed / Update available / Not in the registry / Managed by its installer). Install/Update: counted download (TLS 1.2, Cancel works), optional SHA-256 check, the `*.extension` found inside the zip (top, GitHub-style single folder, or loose tabs), every path checked against zip-slip, staged then swapped in; the old copy goes to trash first, a failed extract leaves it in place; `.playground-install.json` records the version. Remove moves to trash. pyNavis and Playground are never touched. Reload once, when the window closes. |
| Team Sync (#125) | Team folder (default: Playground's shared folder) with `playground-team\`. Window shows what a Pull would change per area (added/changed/removed), Pull at startup check, Pull, Push, Change folder. Pull copies templates/presets/libraries/rules into `%APPDATA%\pyNavis\playground`, backs up what it replaces or removes, never deletes files you made yourself, merges project settings (team keys only), team shortcuts (only the keys it names) and extension roots (adds, never removes) into config.json, then Reloads when needed. Push writes your content, backs up the team files it replaces in `playground-team\.backup\<stamp>`, writes `version.json`. `hk_teamsync` at startup: off by default; when on, a worker thread reads the stamp and pulls when it changed, toast posted back to the UI thread. |
| Usage Analytics (#112) | Opt-in: the first click explains exactly what is recorded and asks. `hk_usage` stamps before-command and appends time, user, machine, extension, bundle key, title, ms on after-command to `%APPDATA%\pyNavis\playground\usage\usage-YYYY-MM.csv` (or `<team>\usage\<user> YYYY-MM.csv` with "team folder"). No document names. Report in the output window: totals, most used tools chart, runs per day (60 days), every tool used, per person, never-used tools. Shift+Click: on/off, where to write, export to Excel. |
| Environment Doctor (#121, stack) | Pass/warning/fail report in the output window: Navisworks product and API, pyNavis runtime and library versions and path, IronPython, CPython (configured, found, buttons that need it), extension roots, every extension (tabs, buttons, problems, hooks, startup.py), duplicates, *.lib folders, shortcut count and problems (resolved like ShortcutMap), panel slots vs dock panels, WebView2, `pynavis.exe`, add-ins (failed ones, duplicate pyNavis loader ids, third-party list), config.json parse, this session's [ERROR] log lines (last 20), writable folders (real write probes), overlay and pick plugins. Shift+Click copies a plain-text report. |
| Playground Settings (stack) | `namo.ui.form` over `namo.config`: name, company, project name/number, where data lives (this computer / shared folder / inside the model) and the shared folder (must be reachable), trades (one per line), trade rules (`pattern = Trade`, each must compile), report units, date format (with examples). |
| Unit Converter (#113) | Modeless calculator, survives Reload. Converts as you type: sentences with their own units ("12' 6\" to mm", "250 sqft in m2", "3.5 m3 cuyd", "1200 kg lb"), or a bare value with From/To lists. Feet-and-inches shown for ft/in results. Enter copies (ASCII unit), Copy button, last 10 in history (double-click or Enter reloads one), Ctrl+D "Document units" points the target at the model's unit (squared/cubed for areas and volumes). |

Shared infrastructure: `namo.ribbon` (documented at the top of ribbon.py): pure chord
parser identical to pyNavis' (cross-checked against ChordParser on IronPython), key
normalising, binding resolution identical to ShortcutMap (cross-checked), context
rules in words, the deferred-run `Job` state machine; runtime half listing buttons,
dock panels, url/link buttons and native commands, finding a button by key, running a
bundle deferred until the RunGate is free (ScriptExecutor.Run handed to the dispatcher
as a .NET delegate, the DispatcherOperation polled; tested end to end on a real WPF
dispatcher in the harness), running a native command (CanExecute first).

Deviations and decisions:
* The Settings button is titled "Playground Settings", not "Playground Settings": dev/check.py
  refuses a caption that starts with a lowercase letter. The window is titled "Playground
  Settings". To use the catalog title, check.py needs an exception for brand names.
* Native commands CAN be recorded when run from the Command Palette (the palette tells
  the recorder), and inserted by hand in Manage Macros; from the ribbon they cannot
  (no event), and Manage Macros says so.
* Usage and Team Sync keep their settings in `%APPDATA%\pyNavis\playground\usage\settings.json` and
  `%APPDATA%\pyNavis\playground\team-sync.json` (their hooks have no bundle, so `script.get_config`
  cannot serve them).
* Generated scripts that need Playground (macro buttons, native hotkeys, the Hotkeys
  button) find Playground's lib through `RuntimeHost.Extensions` (extension named Playground),
  falling back to the path recorded when they were made, and toast "The Playground extension is not
  installed" when neither exists. Button Maker's own templates use only `pynavis`.
* Hotkey Manager keeps config.json overrides for bundles that no longer exist (pyNavis'
  Shortcuts editor drops them); the Environment Doctor lists them as problems.

## 2. In-app checks (please click these, in order)

Setup: Reload pyNavis. The log should end with `Ribbon built: ...` and no `Bundle`
problem for Dev; the Dev tab shows Automate, Reports, Build, Team, Tools.

1. **Ctrl+Shift+P** with a model open. The palette opens with the cursor in the box.
   Type `clash`: pyNavis/Playground clash tools AND native "Clash Detective" appear, each
   with its tab > panel path and chord. Up/Down/PgUp/PgDn move; Esc closes silently.
2. Pick a Playground button with Enter (e.g. Health Check): the palette closes and the tool
   starts by itself a moment later (deferred run). Reopen the palette: it is first.
3. Pick a NATIVE command (e.g. Clash Detective, Select All, Hide). It should run as if
   clicked. **UNVERIFIED: that AdWindows hands Navisworks' handler the RibbonItem and
   that CanExecute/Execute work from code.** If nothing happens, tell me the command and
   what the log says (`Playground: ribbon: ...`); if "X cannot be run from here" appears,
   the item has no handler reachable from AdWindows.
4. Type a saved viewpoint name: "Go to view: ..." recalls it ("Showing X" toast). Type
   a selection set: "Select set: ..." selects it with a count.
5. With nothing selected, type `select similar`: it is listed muted with "needs a
   selection"; Enter keeps the palette open and the status line says why.
6. Record Macro: click; the caption becomes Stop Recording. Run two Playground buttons from
   the ribbon and one native command from the palette, then Stop Recording: it asks a
   name; save it. Manage Macros shows 3 steps (the native one "Navisworks: ...") with
   recorded gaps.
7. Play Macro: pick it. Steps run one after another; a step's own dialogs still appear;
   final toast "Macro X finished". Start it again and click Play Macro mid-way: Stop.
8. Make a step fail (add a command whose script raises, e.g. a Button Maker button with
   a typo): with "Stop at the first step that fails" on, play stops with "stopped at
   step N"; **UNVERIFIED: that pyNavis' FailureLog marks the failure** (if the macro
   carries on, tell me).
9. Macro to Button: pick the macro, accept the defaults: a MyTools tab appears after the
   automatic Reload with a "play" icon button; clicking it plays the macro.
10. Button Maker: name "Count doors", Selection tool, shortcut Ctrl+Alt+D, Letters icon.
    After Reload: MyTools > Tools has a CD button (check the icon in light and dark
    theme, large and in a stack if you move it), Ctrl+Alt+D runs it. Try Ctrl+Shift+P
    as the shortcut: the form refuses it naming Command Palette.
11. Script Editor: the tree lists MyTools (and Playground when its folder is writable, not
    pyNavis). Open Count Doors > script.py, type `doc = Application.ActiveDocument` on a
    new line then `doc.` : a completion list of Document members should appear
    (**UNVERIFIED reflection on the live API types**). Ctrl+Space after `toast.` lists
    pynavis.toast functions. Break the syntax and Ctrl+S: status names the line, gutter
    number turns red. Fix, F5: the button runs. Close with unsaved edits: it asks.
12. Hotkey Manager: filter `clash`, select a pyNavis row, press Ctrl+Alt+K in the field;
    Save and reload. config.json now holds only that key changed (compare with a copy
    taken before; every other key, including runtime2026, unchanged). Give a NATIVE
    command (e.g. Select All) Ctrl+Alt+A: MyTools gets a Hotkeys panel with a Hotkeys
    button; Ctrl+Alt+A runs Select All (**UNVERIFIED native execution, as in step 3**).
    Clear it again: the nobutton moves to %APPDATA%\pyNavis\playground\trash.
13. Extension Manager: with no registry it opens with "No registry is set". Shift+Click,
    point it at a local `registry.json` listing a zip of any small extension; Install,
    close: pyNavis reloads and the extension's tab appears; Update and Remove behave;
    with a sha256 that does not match, Install refuses. Then try a real https URL
    (**UNVERIFIED: TLS/proxy on your network; a proxy that needs credentials will fail
    with the server's sentence**).
14. Team Sync: pick an empty folder; Push. Check `playground-team\` holds config.json,
    shortcuts.json, extensions.json, version.json, templates\. On a second machine (or
    after renaming %APPDATA%\pyNavis\playground\templates), Pull shows the per-area summary and
    restores them. Turn on "Pull at startup", Push again from the first machine, restart
    Navisworks on the second: a "Team settings updated" toast arrives a moment after
    startup (**UNVERIFIED: the worker thread and the dispatcher hand-off**).
15. Usage Analytics: first click asks; say Yes. Run a few tools, click again: the report
    shows them, never-used tools listed. Shift+Click: export to Excel opens in Excel.
    Turn it off: no more lines in usage-YYYY-MM.csv.
16. Environment Doctor: the report lists every extension, the shortcut count, panel
    slots, add-ins. Shift+Click: paste the clipboard into Notepad. Check the
    product/API line (**UNVERIFIED ApplicationVersion.RuntimeProductName text**) and the
    WebView2 version (registry probe).
17. Playground Settings: set Shared folder mode with an unreachable path: refused with "That
    folder cannot be reached right now." A trade rule without "=" is refused with its
    line number. Save a valid set: toast summary.
18. Unit Converter: type `12' 6" to mm` (3,810 mm), `3.5 m3 cuyd`, `1200 kg lb`, Enter
    copies; type `12 m2` then Ctrl+D in a feet model: becomes `12 m2 to ft2`. Reload
    pyNavis with the window open: it stays and keeps working.

## 3. Requests for shared modules (not edited; worked around locally)

1. **lib/namo/README.md (foundation)**: add my modules to the module index:
   `ribbon` (pyNavis buttons, native ribbon commands, chord grammar, deferred runs via
   the RunGate; API+pure), `palette`, `macros`, `buttonmaker` (writes bundles into
   MyTools; pure+WPF icons), `editor`, `hotkeys` (config.json binding edits, JsonPretty
   layout; pure+WPF), `extmanager`, `teamsync`, `usage`, `doctor`, `converter`,
   `team_settings`, and handlers `hk_macro`, `hk_usage`, `hk_teamsync`. Worth adding
   to "Conventions": **late callbacks must not lazily import namo modules**: after a
   run the engine resets sys.path to its base paths and Playground's lib is no longer on
   it, so `from namo import x` inside a timer or window handler fails unless x was
   already imported (every module of mine imports its namo dependencies at the top).
2. **namo.ui.Table**: a public `scroll_to_selection()` (or have `select_values` call
   `ScrollIntoView`). Hotkey Manager reaches `table.grid.ScrollIntoView` itself
   (guarded) so an edited row stays in view after `update()`.
3. **namo.units.parse_conversion**: accept a target unit with no separator word
   ("3.5 m3 cuyd", "1200 kg lb", which the catalog lists). converter.py does it in
   `_implicit()` (tries the last one or two words as the target): fold it into units.
4. **dev/check.py**: allow a caption that starts with a lowercase brand name
   (`Playground Settings`), e.g. a whitelist of `pyNavis`, `Playground`.

## Refit pass

Second pass after the first field click (2026-10-05). Every bundle of the Automate, Build,
Team and Tools panels was read end to end with its `namo` modules, plus `startup.py`,
`hooks\*.py` and `lib\namo\hooks.py`. Runtime members were checked against the pyNavis
source (the installed runtime is the same build), Navisworks and AdWindows members against
`dev\api`. Field evidence from the owner's pyNavis.log: the 9 Playground hooks are configured,
`startup.py` and the before/after-command hooks ran around Photo Pins with no failure or
over-budget line.

| Tool | Verdict | What was wrong, what changed | Proven or unproven |
|---|---|---|---|
| Button Maker | fixed | First click failed: the form options were written (value, label), so the form handed back `Selection tool` and the make step answered "unknown template"; the icon choice was ignored and the script-file, letters and PNG fields could never enable. Options are (label, value) now; generated templates use real plurals. | Proven: flat yaml + layout lists read back by the real BundleParser; Reload as the shipped Settings tool |
| Command Palette | fixed | A saved viewpoint with a slash in its name ("Level 1/2") was "gone", and a set sharing its name with a folder raised: lookups split on `/` and `sets.find` may return a folder. Views and sets are now found by their exact stored path, folders never. | Proven: listing, views (`CurrentSavedViewpoint`), sets (`pynavis.sets`). Unproven: starting a bundle with `ScriptExecutor.Run` from `Dispatcher.BeginInvoke`; native commands through `RibbonCommandItem.CommandHandler.Execute` |
| Record Macro | fixed | Shift+Click runs (config.py) were recorded as steps and would replay the tool itself; skipped now. | Proven: after-command hook, toggle state as Hide Tabs |
| Play Macro | fixed | Same view/set lookup fix. | Unproven: the deferred run above |
| Manage Macros | fixed | A failed save (shared folder gone) was only logged: it toasts now. Empty state says how to get a macro. | Proven (modal window, pynavis.forms) |
| Macro to Button | ok as built | Inherits the Button Maker writer. | Proven writer; plays through the unproven deferred run |
| Script Editor | fixed | Probed the shipped pyNavis folder with a temp file; kept a stale extension list (MyTools made later never showed); Reload could fire while a script ran. Now skips pyNavis, refreshes on every click and after Reload, refuses Reload while the RunGate is held, reloads through `script.reload_pynavis`. | Proven: modeless window as the shipped Console. Unproven: F5 (deferred run) |
| Hotkey Manager | fixed | config.json bindings are now saved by pyNavis' own `PyNavisConfig.SaveShortcutBindings` (what the shipped Shortcuts editor calls), Python writer kept as fallback and byte-compared in a test. Ctrl+S and Ctrl+F could not be recorded as chords (the window ate them). Tooltip said "clashes". | Proven for pyNavis buttons. Unproven: native-command hotkeys (AdWindows execute) |
| Extension Manager | fixed | Status read "1 entry skipped: No registry is set"; cancelling the registry read still opened the window; removing a folder in use gave a raw error; proxies now get Windows credentials. | Unproven: `WebRequest` on the office network (guarded, the server's sentence is toasted) |
| Team Sync | fixed | An offline folder read as "there is no playground-team folder"; Push stayed enabled. Team shortcuts go through pyNavis' saver. The startup check no longer imports the UI library to learn it is off. | Unproven: worker thread + DispatcherTimer hand-off at boot, only with "Pull at startup" on |
| Usage Analytics | fixed | With recording turned off, a click asked to opt in again instead of showing the data; the settings toast claimed the team folder when it was unreachable (and toasted twice); "1 tools"; no runner guard. | Proven: before/after-command hooks, output charts |
| Environment Doctor | ok as built | Every member checked (ApplicationVersion, PluginRecord, PyNavisVersion, CPythonLocator, plugin ids, log marker). | Proven, except the exact `RuntimeProductName` text |
| Playground Settings | ok as built | | Proven |
| Unit Converter | ok as built | | Proven (modeless as Console) |
| hooks\*.py, startup.py, hooks.py | fixed | A failing `from namo import hooks` escaped the file: pyNavis disables a hook after 3 failures and toasts "startup.py failed" on every Reload. Each file now swallows and logs. The dispatcher names any handler slower than 250 ms in the log. | Proven (field log) |

Foundation requests:
1. `namo/ui.py` `FormState.refresh`: the form-level `validate` and the `folder` / `file_open`
   existence checks run on every keystroke. Typing a UNC path probes the network per
   character. Validate paths on OK (or debounce).
2. `namo/ui.py` `normalize_fields`: raise when a choice/radio `default` or an `enabled_if`
   value is not among the option VALUES. It would have caught the Button Maker bug at build.
3. `namo/camera.py` `find_view` / `split_path`: a viewpoint name holding `/` can never be
   found. Worked around in `macros.find_saved_view`; other callers still have it.
4. Still open from the first pass: `ui.Table.scroll_to_selection`, `units.parse_conversion`
   without a separator word, `check.py` brand captions, README module index.

Click these first:
1. Button Maker: name `Count doors`, keep Selection tool, shortcut Ctrl+Alt+D, Make button.
   Correct: toast "Added Count doors", a MyTools tab with a CD button; with items selected
   it toasts "N items selected".
2. Ctrl+Shift+P, type a Playground tool, Enter. Correct: the palette closes and the tool starts
   a moment later (this is the unproven deferred run). Then a native command such as
   Select All: it runs, or a toast says "Select All cannot be run from here" (tell me which).
3. Hotkey Manager: pick a pyNavis row, click the field, press Ctrl+Alt+K, Save and reload.
   Correct: toast "Shortcuts saved", config.json differs only in that one binding.

Verify (full run, once): check ok, pytest ok (1,619 passed, 19 skipped), ipy compile ok,
ipy test 1,602 passed and 1 failed (`test_preflight.test_report_writes_html_and_xlsx`,
another group's file being edited at the time: it passes when re-run alone, 24 of 24),
ipy smoke ok (115 passed), parse ok, fresh ok, names ok. New: `dev\tests\test_dev_refit.py`
(12 regression tests, 12 pass under IronPython, 11 plus 1 IronPython-only skip under CPython).
