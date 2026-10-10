# pyNavis Playground

Experimental tools for [pyNavis](https://github.com/pynavis/pyNavis), the open-source
pyRevit-style add-in for Autodesk Navisworks. Playground is a second extension you install
next to pyNavis: 140 tools in five ribbon tabs (Model, Views, Coordinate, Project, Dev).
They started from a list of 100-plus feature asks compiled from public Navisworks forums,
idea boards and the gaps that paid add-ins fill.

Nothing here is a finished pyNavis tool. Every tool carries an honest status, and most
have never run inside Navisworks. Install the ones you need, try them on a real model,
tweak them, and tell us what happened. Tools that prove themselves graduate into pyNavis.

Browse the catalog online: https://playground.pynavis.com/

## Install

You need pyNavis 1.3.0 or later.

**The whole extension.** Download `Playground.extension.zip` from the latest release, unzip
it, put the `Playground.extension` folder in `%APPDATA%\pyNavis\extensions\`, and click
pyNavis > Reload. To remove it, delete the folder and Reload.

**Only the tools you want.** In Navisworks, click pyNavis > Playground. It opens a browser
over `catalog.json`: search, read the user ask behind each tool, tick the ones you want,
and click Install. It downloads only those tools, plus the shared library they all use,
into `%APPDATA%\pyNavis\extensions\Playground.extension\` and reloads. Remove works the
same way.

Every installed Playground tool is marked experimental on the ribbon: a beta sign in its
caption and "Experimental:" at the start of its tooltip.

## Status ladder

| status | meaning |
|---|---|
| `untested` | Never executed inside Navisworks. Passed the headless checks only. |
| `launched` | Ran inside Navisworks at least once with no error logged; nobody checked the result yet. |
| `verified` | A person confirmed it does what its tooltip says, on a real model. |
| `known-issue` | Ran and misbehaved. The note says how. Still installable. |

Today (version 0.1.0): 40 tools `launched`, 100 `untested`, none `verified` and no open
`known-issue`. Eighteen of the launches come from one headless `pynavis run` pass on a
small sample model, which shows the code runs inside Navisworks, not that its results are
right; `dev\runner\RESULTS.md` says what that pass can and cannot show.
The ledger is `status.yaml`; `catalog.json` carries each tool's status, note and date.
A status only goes up with evidence: a log excerpt, a `pynavis run` transcript,
or a named person's check.

## Report back

Tried a tool? Open a **Tried a tool** issue, whether it worked or not, with the lines from
`%APPDATA%\pyNavis\logs\pyNavis.log` around the time you clicked it (Playground's own lines
start with `Playground:`). Remove file paths, project names and anything else you would
not post in public. That report is what moves a tool from `untested` to `launched` or
`verified`, or marks a `known-issue`. Want a tool that is not here? Open a **Tool request**
with a link to where it was asked. [CONTRIBUTING.md](CONTRIBUTING.md) has the details.

## How a tool graduates

A tool that people other than its author have `verified`, with no open known issue, is a
candidate for pyNavis itself. It moves there through a pull request to the pyNavis repo,
under pyNavis' own rules and review, and its Playground copy is retired.

## How it was built

Playground was built with Claude, the AI model from Anthropic, working from that list
of 100-plus feature asks. Each tool was specified, then written with unit tests against a
shared library (`lib\namo`, "namo, the Playground library"), then read by a separate
review pass that looked up the Navisworks API members it uses in a reflection dump of the
Navisworks 2026 API (`dev\api`). That lookup was done by reading, not by a tool.

The list says what was asked, not where. A later search for the public ask behind each
tool found a confirmed quote for 5 of the 140: `catalog.json` gives it word for word with
its link (`source`). Another 40 have `leads`, threads that look relevant but that a person
still has to open and read. The other 95 have no public source on record. A quote is
never made up or reworded.

Being built this way is why the statuses matter. Passing every headless check proves the
code parses, imports, follows the pyNavis bundle contract and does what its unit tests say
with the Navisworks API replaced by fakes. It does not prove a tool works in Navisworks.

## Headless verification

`python dev\verify.py` runs nine stages without Navisworks. The last full run, on this
tree, was green on all of them:

| Stage | Result |
|---|---|
| `dev\check.py`: pyNavis bundle contract (layouts, stacks, icons, yaml grammar, contexts, shortcuts and their collisions with pyNavis) and house rules (no print, no f-strings, no `__main__`, no em dashes, sentence case) | 140 bundles, 370 Python files, 0 problems |
| pytest under CPython 3.11 | 1,699 passed, 19 skipped |
| Every extension file compiled by the IronPython 3.4 that pyNavis ships | ok |
| The same tests under IronPython 3.4 | 1,645 passed, 39 skipped |
| WPF windows built (not shown) under IronPython with the real PyNavis.Runtime; fails when a window callback raises a NameError while building | 118 passed |
| The real pyNavis `BundleParser` over this root | 5 tabs, 138 buttons (plus 2 dock panes) |
| Every namo module imported in a fresh IronPython engine | 184 of 184 |
| pyflakes: undefined names | none |
| `catalog.json` and the release zip match `status.yaml` and the bundles, and the site in `docs\` matches `catalog.json` (`build_catalog --check`, `package --check`, `build_site --check`) | current |

The IronPython stages need a pyNavis runtime for Navisworks 2026: the one an installed
pyNavis keeps in `%APPDATA%\pyNavis\2026\runtime`, or else the build output
(`bin\2026\runtime`) of a pyNavis checkout beside this repo or at `PYNAVIS_SRC`. The
CPython tests take `pynavislib` from that checkout. Navisworks itself never runs.

## Layout

| Path | What |
|---|---|
| `Playground.extension\` | The extension: five tabs, 25 panels, 140 tools, `lib\namo`, `hooks\`, `startup.py` |
| `Playground.extension\lib\namo\README.md` | Library contracts, conventions, and an index of every tool module |
| `status.yaml` | The status ledger |
| `catalog.json` | Every tool, generated by `tools\build_catalog.py` (never edit by hand) |
| `tools\build_catalog.py`, `tools\package.py` | Catalog and release zip builders |
| `docs\` | The public catalog site for GitHub Pages, generated from `catalog.json` by `tools\build_site.py` (never edit by hand) |
| `tools\build_site.py`, `tools\site\` | Site builder and its styles and script, copied from the pyNavis sites |
| `companions\PlaygroundLink.extension\` | A pyRevit companion for Show in Revit and Send to Navisworks |
| `dev\CHARTER.md` | The project's rules: naming, statuses, catalog schema |
| `dev\CATALOG.md`, `dev\BRIEF.md`, `dev\FOUNDATION.md` | Tool specs, the engineering brief, the library contracts |
| `dev\IN_APP_CHECKS.md`, `dev\notes\` | In-app test steps, per group build notes |
| `dev\verify.py` and its helpers | Headless verification |
| `dev\make_icons.py`, `dev\icons\` | Icon generator (pyNavis' drawing language) |

## License

Apache-2.0. See [LICENSE](LICENSE).
