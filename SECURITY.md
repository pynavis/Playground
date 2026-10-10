# Security

Playground tools are Python scripts that pyNavis runs inside Navisworks with your own
Windows rights: they can read and write any file you can. Install only tools you are
willing to run, and read a tool's `script.py` first if in doubt. Every tool is experimental.

## What the in-app installer does

pyNavis > Playground reads `catalog.json` from this repo (or from the location set in
`playground.catalog` in your pyNavis `config.json`). To install, it:

* downloads the release zip the catalog names, into `%APPDATA%\pyNavis\playground\`, and
  uses it only when its SHA-256 equals the `download.sha256` in that same catalog;
* extracts only the files of the tools you ticked (plus the shared library, hooks and
  their panels), refuses any path that would leave the extension folder, and moves them
  into `%APPDATA%\pyNavis\extensions\Playground.extension\`, the only folder it installs
  into or removes from.

The checksum catches a broken or mismatched download. It does not protect against a
change to this repo itself, since the catalog and the zip come from the same place.

## Reporting a problem

For a vulnerability, use **Report a vulnerability** on this repo's Security tab rather
than a public issue. Anything else goes in a normal issue.
