# pyNavis Playground: charter and contracts

Status: binding for every agent on this project. Written 2026-10-09.

## What this is

pyNavis Playground is a second, separately installed extension for pyNavis (the open-source
pyRevit-style add-in for Autodesk Navisworks, https://github.com/pynavis/pyNavis). It holds
about 140 tools that were built from a list of real user asks collected from public forums
and product boards, verified headlessly, and only partly run inside Navisworks. Nothing here
is a finished pyNavis tool. Every tool is published with an honest status so people can
install one, try it, tweak it, and report back. Tools that prove themselves graduate into
pyNavis proper.

Two ways to get a tool:

1. Download the release zip of the whole extension and drop `Playground.extension` into
   `%APPDATA%\pyNavis\extensions\`, then click pyNavis > Reload.
2. Inside Navisworks, pyNavis > Playground opens a browser over the online catalog: search,
   read the user ask that motivated each tool, tick the ones you want, Install. It downloads
   only those bundles (plus the shared library) into
   `%APPDATA%\pyNavis\extensions\Playground.extension\` and reloads.

## Repos and folders

| Path | Role |
|---|---|
| this repo | Published as GitHub `pynavis/Playground`. Commit when a wave is green. |
| a pyNavis checkout, beside this repo or at `PYNAVIS_SRC` | The pyNavis source (loader, runtime, shipped extension, docs). Changes there follow pyNavis' own contributing rules. |
| the original showcase extension | The private, frozen origin of this code. Not published. |

## Naming (final)

* Product name: **pyNavis Playground**. Extension folder: `Playground.extension`
  (`extension.yaml`: `name: Playground`, `engine: ironpython`).
* Tab folders and titles (pyNavis derives the title from the folder name, `_` becomes a
  space): `Model.tab`, `Views.tab`, `Coordinate.tab`, `Project.tab`, `Dev.tab`. No name of the
  original showcase anywhere a user can see it: titles, tooltips, toasts, config keys, window titles, docs.
* Shared library stays `lib\namo` and `import namo` (a rename is pure risk).
  In docs call it "namo, the Playground library". Per-document and per-user stores live
  under `%APPDATA%\pyNavis\playground\`. Custom property tabs written into models are
  called `Playground`.
* Bundle key = extension-relative path, e.g. `Model.tab/Select.panel/Select_Similar.pushbutton`.
  It is the tool id in the catalog, the status ledger and the installer's installed.json.

## Status ladder (honest, machine-readable)

| status | meaning |
|---|---|
| `untested` | Never executed inside Navisworks. Passed the headless gates only. |
| `launched` | Ran inside Navisworks at least once with no error logged; the result was not checked by a person. |
| `verified` | A person confirmed it does what its description says, on a real model. |
| `known-issue` | Ran and misbehaved; `note` says how. Still installable. |

The ledger is `status.yaml` at the repo root: one entry per bundle key with `status`,
`note` (one sentence, optional), `date` (YYYY-MM-DD), `by` (`log`, `runner`, `person`).
`tools/build_catalog.py` merges it into `catalog.json` (`status`, `status_note`,
`status_date`, `status_by`); a tool missing from the ledger is
`untested`. Statuses only go up through evidence: a log line, a runner transcript, or a
named person's check. Never set `verified` without a person.

## catalog.json (schema 1)

```json
{
  "schema": 1,
  "name": "pyNavis Playground",
  "version": "0.1.0",
  "generated": "2026-10-09",
  "min_pynavis": "1.3.0",
  "repo": "https://github.com/pynavis/Playground",
  "download": {"zip": "https://github.com/pynavis/Playground/releases/download/v0.1.0/Playground.extension.zip",
               "sha256": "<hex, lower-case>"},
  "extension": "Playground.extension",
  "shared": ["extension.yaml", "startup.py", "lib/namo/**", "hooks/*.py"],
  "containers": [
    {"id": "Model.tab", "title": "Model", "kind": "tab", "files": ["Model.tab/bundle.yaml"]},
    {"id": "Model.tab/Select.panel", "title": "Select", "kind": "panel", "files": ["Model.tab/Select.panel/bundle.yaml"]},
    {"id": "Model.tab/Select.panel/Quick.stack", "title": "Quick", "kind": "stack", "files": ["..."]}
  ],
  "tools": [
    {
      "id": "Model.tab/Select.panel/Select_Similar.pushbutton",
      "title": "Select Similar",
      "kind": "pushbutton",
      "tab": "Model", "panel": "Select", "container": "Model.tab/Select.panel",
      "summary": "Selects every item that shares the property values you tick with the first selected item.",
      "status": "launched", "status_note": "", "status_date": "2026-10-05", "status_by": "log",
      "feature": 4,
      "shortcut": null, "context": "selection",
      "hooks": [],
      "files": ["Model.tab/Select.panel/Select_Similar.pushbutton/bundle.yaml", ".../script.py", ".../icon.png", "..."],
      "icon": "Model.tab/Select.panel/Select_Similar.pushbutton/icon.png",
      "source": {"quote": "verbatim words of the user ask, 40 words or fewer",
                 "url": "https://...", "site": "Autodesk Community", "date": "2019-03",
                 "via": "page"},
      "leads": ["https://..."],
      "siblings": []
    }
  ]
}
```

Rules:

* Paths are forward-slash, relative to `Playground.extension/`. `files` lists every file in
  the bundle folder (a dockpane includes `pane.xaml`; a toggle its on/off icons).
* `hooks` names the event files (`selection-changed`, `doc-opened`, ...) a tool needs,
  derived from which `hk_*` handler the tool depends on. The installer copies `hooks/*.py`
  whenever any installed tool needs any hook (the dispatcher tolerates absent listeners).
* `siblings` lists the other bundle ids in the same stack, so the installer can keep a
  stack valid (pyNavis skips a stack with fewer than 2 buttons): installing one member of
  a stack installs the stack; the catalog says so in the UI ("installs with X and Y").
* `source` is `null` when no real public ask was found. A `source` is NEVER invented. The
  quote is verbatim and the url was actually seen by the agent that wrote it. `via` says how:
  `page` (the agent opened the page) or `search snippet` (the page would not open to an
  automated fetch, so the quote is the search engine's own snippet, as shown). Sites that
  block automated fetches are never worked around. `leads` lists URLs that looked relevant
  but could not be opened, for a person to check in a normal browser.
  `feature` is the row in the maintainers' feature-ask list (not published); `dev/CATALOG.md`
  carries each row number as `**#N Title**`.
* `summary` is the bundle tooltip, sentence case, no em dashes.
* The catalog is generated, never hand-edited: `python tools/build_catalog.py` writes
  `catalog.json`; `--check` fails when it is stale (publish and CI use it).

## In-app browser (lives in pyNavis, ships with pyNavis 1.3.0)

* Bundle: `extensions/pyNavis.extension/pyNavis.tab/pyNavis.panel/Playground.pushbutton`
  (listed in the panel layout after Reload; `ShippedExtensionTests` updated to match).
* Pure logic in `extensions/pyNavis.extension/lib/playground.py` (catalog parse, install plan
  = set of zip entries to extract for a selection incl. shared files, containers, hooks,
  stack siblings; installed-state read/write; removal plan with empty-container pruning),
  unit-tested through the IronPython-in-xunit pattern used for the other lib modules.
* `script.py` = WPF window (pynavis.forms / Forms design tokens, themed light and dark):
  search box, status filter, rows with title, tab > panel, status chip, summary, "Ask"
  link opening `source.url`, checkbox; buttons Install, Remove, Open folder, Refresh.
* Catalog URL default `https://raw.githubusercontent.com/pynavis/Playground/main/catalog.json`;
  config.json `playground.catalog` overrides it and accepts a local file path (dev and
  offline). Zip cached at `%APPDATA%\pyNavis\playground\<version>.zip`, SHA-256 checked.
* HTTP like `UpdateService.Client`: TLS 1.2, default proxy credentials, `pyNavis/<ver>`
  user agent, 15 s timeout, friendly "GitHub could not be reached" failure.
* Writes go to a temp folder then move into place (see `GeneratedExtensionWriter.Create`).
  Then `script.reload_pynavis()`. First install writes `extension.yaml` and may need to tell
  the user that a `*.lib` folder would need a restart (there is none; lib is inside).
* Every installed bundle's `bundle.yaml` carries `status: experimental` (the catalog build
  stamps it in the shipped zip), which pyNavis shows as a caption marker and tooltip
  prefix (new `status:` key, this project).

## House rules (inherited from pyNavis, enforced)

* IronPython 3.4: no f-strings, no `print()`, no `__main__`, toast one-line statuses.
* Sentence-case UI text, no em dashes anywhere (code, docs, yaml, posts).
* No invented claims: no numbers that were not measured, no "tested" that was not run.
* Icons only via the icon generators (`dev/make_icons.py` here, `tools/make_icons.py` in pyNavis).
* Tests first. Every wave ends with `python dev/verify.py` green here and
  `dotnet test src\PyNavis.Tests\PyNavis.Tests.csproj -p:NavisVersion=2026` green in pyNavis.
  Agents working in pyNavis in parallel MUST build to their own scratch output:
  `-p:PyNavisBinRoot=<scratch folder>\<agent-name>\bin\` to avoid DLL lock collisions.
* Nothing in pyNavis or here may mention private machine paths, user names or email
  addresses (pyNavis' publish.py runs a forbidden-string scan). This repo may say "built
  with Claude".
