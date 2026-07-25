# Contributing

Thanks for working on a Bespok3d plugin. Bespok3d is a printer-agnostic plugin manager for Klipper
printers that runs on stock firmware, with no custom-firmware flashing. This repo publishes one or
more plugins as signed `.b3` packages that the desktop app installs onto a printer through the
on-printer daemon. See [README.md](README.md) for this repo's layout, build, and release mechanics.

## Before you write code

Read [CLAUDE.md](CLAUDE.md). It is the contract for changes here: the plugin model (a plugin declares
WHAT the printer should end up with, never a script that runs on the printer), the non-negotiables
(RULE ZERO: no em-dash or en-dash; every identifier carries domain meaning; nesting beyond one level
is suspicious; rule of three; extend upstream additively; never commit a real secret or LAN value),
and the working procedure. If you use an AI assistant (many contributors do), point it at that file;
`AGENTS.md` sends non-Claude tools there too.

## Develop

```sh
bash scripts/check.sh
```

The gate needs the `lib_bespok3d` submodule; if you cloned without it, run
`git submodule update --init` first. It runs the shared workspace detectors (the em-dash guard,
workflow-pinning, shellcheck) plus whatever language layer the plugin ships (ruff, mypy, and pytest
for a plugin that carries Python). Run it before every push; CI runs the same gate and blocks a
release on failure.

## Release

Bump a plugin's `manifest.json` `version`. On merge, the `b3-builder` CI Action packs the `.b3`,
signs it, cuts a release, and registers it in the org index. Do not hand-edit `index.json`, the
`.atom.json`, `index.json.sig`, or anything under `dist/`: those are generated and signed by CI.

## What a good change looks like

- Scoped to a clear user story; only what the story needs.
- Follows the rules in CLAUDE.md; passes the gate green.
- Ships a regression test where the repo has a test layer for the behavior, in the same change.
- Keeps the plugin's `doc/README.md` and `doc/CHANGELOG.md` current when it changes behavior or config.

## Constraints

- The maintainer owns git history and releases; submit changes as a pull request against `dev`.
- Never SSH-mutate or reconfigure a live printer without explicit authorization; a serial port on a
  printer may be a live Klipper MCU link. Read-only diagnosis is fine.
