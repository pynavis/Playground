# Contributing to pyNavis Playground

Three kinds of help move Playground forward, from least to most effort: telling us how a
tool behaved when you tried it, asking for a tool with the original public ask, and
changing or adding a tool yourself.

## Report a tool you tried

Open a **Tried a tool** issue (the template asks for everything below). Report it whether
the tool worked or not: a "worked" report is the evidence that moves a tool up the status
ladder.

1. Note the tool id. It is the bundle path, shown in `catalog.json` and in the in-app
   browser, e.g. `Model.tab/Select.panel/Select_Similar.pushbutton`. The tab, panel and
   button title are fine too.
2. Say what you did and what you saw: the kind and size of model (not its name), what you
   clicked, what you expected, what you got.
3. Paste the pyNavis log excerpt from `%APPDATA%\pyNavis\logs\pyNavis.log` around the time
   you clicked. Playground's own lines start with `Playground:`. Paste it even when the tool
   worked, because no error in the log is part of the evidence.
4. Remove file paths, project names, people's names and anything else you would not post
   in public.

## Move a status up, with evidence

Statuses live in `status.yaml` at the repo root, one entry per tool id:

```yaml
Model.tab/Select.panel/Select_Similar.pushbutton:
  status: launched
  note: "One sentence, optional."
  date: 2026-10-05
  by: log
```

| status | needs |
|---|---|
| `untested` | nothing: a tool missing from `status.yaml` is untested |
| `launched` | it ran inside Navisworks at least once with no error logged (`by: log` or `by: runner`) |
| `verified` | a named person confirmed it does what its tooltip says on a real model (`by: person`) |
| `known-issue` | it ran and misbehaved; `note` says how |

Rules:

* A status only goes up with evidence: a log excerpt (`by: log`), a `pynavis run`
  transcript (`by: runner`), or a named person's check (`by: person`). Link the issue or
  paste the evidence in the pull request.
* `verified` always needs a person. `tools/build_catalog.py` refuses `verified` with any
  other `by:`.
* `known-issue` beats `launched`: if a tool ran and misbehaved, say so even when it also
  ran fine once.
* After editing `status.yaml`, run `python tools/build_catalog.py` and commit the updated
  `catalog.json` with it.

## Ask for a tool

Open a **Tool request with the original ask** issue. Playground tools start from real,
public asks, so link the page where the need was asked and quote it word for word (40
words or fewer). Never invent or reword a quote; if it is your own need, say so.

## Change or add a tool

You need Windows, CPython 3.11 with pytest, openpyxl and Pillow (pyflakes optional), and
a pyNavis checkout beside this repo (a folder named `pyNavis` next to this one, or set
`PYNAVIS_SRC`): the checks use its `pynavislib` and its icon generator. The IronPython
stages also need a pyNavis runtime for Navisworks 2026, from an installed pyNavis
(`%APPDATA%\pyNavis\2026\runtime`) or from that checkout's build (`bin\2026\runtime`).
Navisworks itself never runs during a check.

A tool is a pyNavis bundle under `Playground.extension\<Tab>.tab\<Panel>.panel\`:

1. **Write the spec first.** Add or update its entry in `dev\CATALOG.md` under its panel,
   with the feature-list row as `**#N Title**` and the bundle name in backticks. The catalog
   build reads the row number from there.
2. **Keep the logic in `lib\namo`.** `script.py` stays thin: it gathers input, calls a pure
   function in a `namo` module, and toasts the result. The pure half is what the tests reach.
3. **Write the tests first** in `dev\tests\test_<module>.py`: plain `def test_x():` functions
   with bare asserts, using `dev\tests\_compat.py` helpers, so the same file runs under
   CPython and under the IronPython 3.4 that pyNavis ships. WPF windows get a
   `dev\tests\smoke_<name>.py` that builds them without showing them.
4. **Add the bundle.** `bundle.yaml` with `title` and `tooltip` (sentence case, no dashes),
   `context:` when the tool needs a document or a selection, and a `layout:` entry in the
   parent container's `bundle.yaml`. pyNavis skips a stack with fewer than two buttons.
5. **Draw the icon** in `dev\icons\<group>.py` and run `python dev\make_icons.py`. Never
   hand-edit a PNG.
6. **If it listens for an event**, write `lib\namo\hk_<name>.py` with `handle(name, event)`
   and add a row to `HANDLERS` in `lib\namo\hooks.py`, with the tool's title in the comment.
7. **Run the checks:** `python dev\verify.py` must end with every stage ok, then
   `python tools\build_catalog.py` to refresh `catalog.json`.

House rules, checked by `dev\check.py`: IronPython 3.4 code only (no f-strings, no
`print()`, no `if __name__ == '__main__'`), one-line statuses through `pynavis.toast`,
sentence-case UI text, no em or en dashes anywhere, every write to the document is one undo
step, and no numbers in docs or UI that were not measured.

A new tool enters as `untested`. Do not add it to `status.yaml` until it has run inside
Navisworks.

## How a tool graduates into pyNavis

A tool that is `verified` by people other than its author, has no open known issue, and
answers an ask many people share is a candidate for pyNavis itself. Graduation is a pull
request to https://github.com/pynavis/pyNavis that moves the tool into the shipped
extension under pyNavis' own rules and review; the Playground copy is then retired.

## Releases

`VERSION` holds the release number. `python tools\package.py` builds
`dist\Playground.extension.zip` (every tool's `bundle.yaml` stamped `status: experimental`
inside the zip only) and writes its SHA-256 into `catalog.json`. `python tools\package.py
--check` and `python tools\build_catalog.py --check` fail when the committed catalog is
stale.
