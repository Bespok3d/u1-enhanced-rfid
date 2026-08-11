# u1-enhanced-rfid

[![licence](https://img.shields.io/badge/licence-GPL--3.0-blue)](LICENSE)
[![release](https://img.shields.io/github/v/release/Bespok3d/u1-enhanced-rfid)](https://github.com/Bespok3d/u1-enhanced-rfid/releases)
[![version](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fraw.githubusercontent.com%2FBespok3d%2Fu1-enhanced-rfid%2Fmain%2Frfid-ntag%2Fmanifest.json&query=%24.version&label=version&color=blue)](rfid-ntag/manifest.json)
![printer](https://img.shields.io/badge/printer-Snapmaker%20U1-informational)
![stock firmware](https://img.shields.io/badge/stock%20firmware-no%20flashing-brightgreen)

NTAG215/OpenSpool RFID: your filament knows what it is.

A solo Bespok3d plugin repo: it ships one plugin (`rfid-ntag`) and publishes a single index atom into `Bespok3d/main-index/atoms/`.

## Layout

```text
u1-enhanced-rfid/
  rfid-ntag/                  # the plugin; its dir name is the manifest .name
    manifest.json
    files/              # payload the daemon places on the printer
    doc/README.md       # rendered in-app; not deployed
  .github/workflows/release.yml
  dist/                 # build output (gitignored)
```

The plugin declares WHAT (destination classes + restart hooks), never paths or raw commands; the
printer-side adapter realizes it.

## Build locally

Needs Node.js 20+. Builds run through the shared `Bespok3d/b3-builder` tool:

```sh
npm install github:Bespok3d/b3-builder
npx b3-builder build --source ./rfid-ntag --atom-repo Bespok3d/u1-enhanced-rfid
# -> dist/rfid-ntag-<ver>.b3 + dist/rfid-ntag.atom.json
```

## Releasing

Bump `rfid-ntag/manifest.json` `version` and push the tag `plugin-<name>-v<version>` naming that
plugin and that exact number. A push to `main` publishes nothing, and the run is refused if the tag
and the manifest disagree. CI runs the `Bespok3d/b3-builder` Action, which packs the `.b3` and cuts
a release; the `register-atoms` action from `Bespok3d/main-index` then registers the atom. This repo
contributes atoms only and publishes no list of its own. Secrets: `MAIN_INDEX_TOKEN` (contents:write
on main-index) and `REGISTRY_SIGNING_KEY` (the org registry key the `b3-builder` Action signs each
`.b3` and atom with).

## Maintainership

These plugins are published and maintained by the Bespok3d org, and several of them repackage or
build on upstream source material. If you own the source material a plugin is based on and would
rather manage it yourself, you are welcome to contact the org to claim it back. The one condition is
that it stays actively maintained: a claimed plugin left to rot will be reclaimed so users are never
stranded on an abandoned package.

## Licence

Copyright (C) 2026 unlucio and the Bespok3d contributors

This repo ships code from other projects offered under version 3 of the GNU General Public License,
with no option to use a later version, so version 3 of that licence covers every file in this repo.

This program is free software: you can redistribute it and/or modify it under the terms of version 3
of the GNU General Public License as published by the Free Software Foundation.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without
even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General
Public License for more details.

You should have received a copy of the GNU General Public License along with this program. If not,
see <https://www.gnu.org/licenses/>. The full text is in [LICENSE](LICENSE).

Bespok3d's own code elsewhere is AGPL-3.0-or-later. One licence covering this whole repo is a clarity
choice, so that nobody has to work out which file carries which terms. Version 3 of the GPL and
version 3 of the AGPL may be combined in a single work, and section 13 of each licence says so; what
cannot happen is code offered under version 3 of the GPL alone being re-offered under the AGPL.

Bespok3d is a project of the Bespok3d Organisation, which is not a legal entity. Copyright is held by
the individual authors named above.
