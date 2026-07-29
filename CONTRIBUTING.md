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

## Quick start: from clone to pull request

Six steps. A change is ready for review when all six are done and the gate is green.

### 1. Install the tools

| Tool | Why | macOS | Linux |
| --- | --- | --- | --- |
| git 2.23 or newer | `git switch` and cloning submodules in one pass | preinstalled, or `brew install git` | `sudo apt install git` |
| Python 3.11 | the printer's runtime; the gate pins it and refuses to run on another version | `brew install python@3.11`, or `brew install uv` | install `uv` (`curl -LsSf https://astral.sh/uv/install.sh \| sh`) and the gate provisions 3.11 itself |
| Node 20 or newer | runs the shared detectors (the em-dash guard, workflow pinning) | `brew install node` | `nvm install 20`; distro packages are usually older than 20 |
| shellcheck | lints this repo's shell scripts | `brew install shellcheck` | `sudo apt install shellcheck` |
| GitHub CLI (optional) | opens the pull request from the terminal | `brew install gh` | see [cli.github.com](https://cli.github.com) |

You also need an SSH key on your GitHub account (`ssh -T git@github.com` should greet you by name) and
access to the Bespok3d org: these repos are private during the beta, so ask the maintainer to add you
before you clone.

The gate builds its own Python tool venv under `lib_bespok3d/tooling/` the first time you run it.
Nothing is installed into your system Python.

### 2. Clone with the submodule

`lib_bespok3d` carries the shared gate helpers and the workspace detectors, and nothing in this repo
checks out green without it. Changes are made on `dev`, so clone that branch:

```sh
git clone --recurse-submodules --branch dev git@github.com:Bespok3d/u1-enhanced-rfid.git
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

### 3. Branch off `dev`

```sh
git switch dev && git pull
git switch -c <short-name-for-your-change>
```

### 4. Make the change

Only what your user story needs. Keep the plugin's `doc/README.md` and `doc/CHANGELOG.md` current when
behavior or config changes, and add a regression test where the repo has a test layer for it. The rules
the reviewer applies are in [CLAUDE.md](CLAUDE.md), and RULE ZERO (no em-dash, no en-dash) covers your
commit message too.

### 5. Run the gate until it is green

```sh
bash scripts/check.sh
```

It runs the shared workspace detectors (the em-dash guard, workflow pinning, shellcheck) plus whatever
language layer the plugin ships (ruff, mypy and pytest for a plugin that carries Python). On a failure,
fix the cause. If a detector is genuinely wrong about one line, justify that one line at the smell
(`# gate-allow <metric>: <reason>`); never mute a check to make a number go down.

### 6. Commit, push and open the pull request

```sh
git commit -am "<what changed and why>"
git push -u origin <your-branch>
gh pr create --base dev --fill      # or open the link that git push prints
```

The pull request targets `dev`. CI runs this same `scripts/check.sh` on it, so a red gate is not
reviewable and blocks the release.

## Release

Bump a plugin's `manifest.json` `version`. On merge, the `b3-builder` CI Action packs the `.b3`,
signs it, cuts a release, and registers it in the org index. Do not hand-edit `index.json`, the
`.atom.json`, `index.json.sig`, or anything under `dist/`: those are generated and signed by CI.

A version bump also changes what the desktop app bundles offline, and the app keeps a committed
snapshot of that bundle. Once your manifest change is in, run `npm run golden:refresh` in the
`Bespok3d-desktop` checkout and commit the refreshed snapshot with it: the app's gate stays red
until someone does.

## What a good change looks like

- Scoped to a clear user story; only what the story needs.
- Follows the rules in CLAUDE.md; passes the gate green.
- Ships a regression test where the repo has a test layer for the behavior, in the same change.
- Keeps the plugin's `doc/README.md` and `doc/CHANGELOG.md` current when it changes behavior or config.

## Constraints

- The maintainer owns git history and releases; submit changes as a pull request against `dev`.
- Never SSH-mutate or reconfigure a live printer without explicit authorization; a serial port on a
  printer may be a live Klipper MCU link. Read-only diagnosis is fine.

## Signing off your work

Every commit must carry a `Signed-off-by` line. It is your statement that you wrote the change, or
that you otherwise have the right to contribute it, under the terms of the Developer Certificate of
Origin (<https://developercertificate.org/>). Git writes the line for you:

```sh
git commit -s -m "your message"
```

A pull request whose commits are not signed off cannot be merged.

## Licence

This repository is under the GNU General Public License, version 3. The full text is in
[LICENSE](LICENSE).

Most of Bespok3d is under the GNU Affero General Public License. This repository is under the plain
GNU General Public License instead because it ships third-party code released under that licence, and
that code cannot be relicensed. Each unit's `doc/ATTRIBUTIONS.md` records what is shipped and where it
came from.

By contributing you agree that your contribution is licensed under those same terms. You keep the
copyright in what you write. There is no copyright assignment and no contributor licence agreement to
sign.
