# u1-enhanced-rfid

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

Bump `rfid-ntag/manifest.json` `version` and push to `main`. CI runs the `Bespok3d/b3-builder`
Action, which packs the `.b3` and cuts a release; the `register-atoms` action from
`Bespok3d/main-index` then registers the atom. This repo contributes atoms only and
publishes no list of its own. Secrets: `MAIN_INDEX_TOKEN` (contents:write on main-index) and
`REGISTRY_SIGNING_KEY` (the org registry key the `b3-builder` Action signs each `.b3` and atom with).

## Maintainership

These plugins are published and maintained by the Bespok3d org, and several of them repackage or
build on upstream source material. If you own the source material a plugin is based on and would
rather manage it yourself, you are welcome to contact the org to claim it back. The one condition is
that it stays actively maintained: a claimed plugin left to rot will be reclaimed so users are never
stranded on an abandoned package.
