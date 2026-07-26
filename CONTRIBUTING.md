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

## Set up your environment

Clone with the submodule. `lib_bespok3d` carries the shared gate helpers and the workspace
detectors, and nothing in this repo checks out green without it:

```sh
git clone --recurse-submodules git@github.com:Bespok3d/u1-enhanced-rfid.git
cd u1-enhanced-rfid
```

Already cloned, or seeing `lib_bespok3d/tooling/gate-lib.sh: No such file or directory`? Run this
once from the repo root:

```sh
git submodule sync --recursive && git submodule update --init --recursive
```

The `sync` half matters on an existing clone: it repoints the submodule at the relative URL, so the
submodule is fetched over whatever protocol you cloned this repo with. Without it, a clone made over
SSH still tries to fetch the submodule over HTTPS and stops at a `Username for 'https://github.com':`
prompt.

You also need these on your machine:

| Tool | Why | Install on macOS |
| --- | --- | --- |
| Python 3.11 | the printer's runtime; the gate refuses to lint or test on any other version | `brew install python@3.11`, or `brew install uv` and the gate provisions one for you |
| Node 20 or newer | runs the shared detectors (em-dash guard, workflow pinning) | `brew install node` |
| shellcheck | lints this repo's shell scripts; the gate skips it with a note if it is absent | `brew install shellcheck` |

The gate builds its own Python tool venv under `lib_bespok3d/tooling/` the first time you run it.
Nothing is installed into your system Python.

## Develop

```sh
bash scripts/check.sh
```

The gate runs the shared workspace detectors (the em-dash guard, workflow-pinning, shellcheck) plus
whatever language layer the plugin ships (ruff, mypy, and pytest for a plugin that carries Python).
Run it before every push; CI runs the same gate and blocks a release on failure.

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
