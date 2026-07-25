# u1-enhanced-rfid: instructions for AI assistants

You are working in a Bespok3d plugin repo. Bespok3d is a printer-agnostic plugin manager for Klipper
printers that runs on stock firmware, with no custom-firmware flashing. This repo publishes one or more
plugins as signed `.b3` packages that the Bespok3d desktop app installs onto a printer through the
on-printer daemon. This file is the contract for any LLM or agent that edits this repo. Contributors
here often work with AI assistance, so the rules and the design intent are written down and enforced in
the gate, not left implicit. The human reviewer rejects a PR that ignores them.

If you are a non-Claude tool, `AGENTS.md` points you here.

## What this repo ships

This is a solo Bespok3d plugin repo: it ships one plugin and publishes a single index atom into
`Bespok3d/main-index/atoms/`.

- `rfid-ntag`: NTAG215/OpenSpool RFID, your filament knows what it is.

It carries Python (Klipper extras under `files/klipper/klippy/extras/rfid-support`), not just config,
patches, and assets.

Read `README.md` for the repo's layout, build, and release mechanics before you change anything.

## The model: a plugin declares WHAT, never HOW

A Bespok3d plugin is declarative. Each plugin's `manifest.json` declares WHAT the printer should end up
with (files placed at a destination `class`, plus a `restart` hook), never a path, a raw shell command,
or a setup script that runs on the printer. The on-printer daemon reads the manifest and realizes it: it
templates and places the files, wires the symlinks, and restarts the named service.

- **No plugin scripts.** Do not add a shell script, a `postinstall`, or any code meant to run on the
  printer to do setup. If the daemon cannot express what a plugin needs declaratively, that is a
  daemon or adapter change, not a script smuggled into a plugin.
- **Plugin isolation.** A plugin owns its own `/userdata/bespok3d/<plugin>` directory and integrates by
  symlink. Teardown removes the plugin's own files and leaves the user's data intact.
- **The printer is never left broken.** Every change keeps the printer usable. The daemon's
  auto-deactivate safety net peels off a plugin that breaks Klipper or Moonraker; do not defeat it.
- **`manifest.json` is the release contract.** Bump its `version` to cut a release. Do not hand-edit
  `index.json`, the `.atom.json`, `index.json.sig`, or anything under `dist/`: those are generated and
  signed by the `b3-builder` CI Action.

## The non-negotiables

1. **RULE ZERO: no em-dash or en-dash, anywhere** (code, comments, docs, commit messages). Use a comma,
   colon, semicolon, parentheses, or two sentences. A hyphen in a compound word is fine. The gate's
   em-dash guard fails the build on a violation.
2. **Every identifier carries domain meaning.** A name says what the thing *is* in the domain, never its
   type, its position, or a role-free abbreviation. No `a`/`b`, `tmp`, `data`, single letters.
3. **Nesting beyond one level is suspicious.** Flatten by default: guard clauses, early returns, an
   extracted named function, a named lookup instead of a nested ternary.
4. **Rule of three.** The third copy of a block, shape, or constant gets extracted. Duplication is a bug;
   "no premature abstraction" forbids generalizing for one caller, it does not excuse copy-paste.
5. **Extend upstream minimally and additively.** Several plugins repackage or patch upstream source
   (Klipper, Moonraker, a web UI). Never delete or rewrite an upstream method; add alongside it, so the
   change survives a re-vendor of the upstream code.
6. **Never commit a real secret or a real LAN value.** Tokens, keys, real IP addresses, and real UUIDs
   stay out of the tree. Fixtures are obviously fake.

## How to work a change

1. **Understand first.** Read the plugin's `manifest.json`, its `files/`, and its `doc/README.md`. Do
   not invent structure; if the intent is unclear, ask one specific question and stop.
2. **Scope it to a user story.** "As a [role], I want [capability] so that [value]." Implement only what
   the story needs: no speculative features, no defensive code for cases that cannot happen.
3. **Write the change** to the rules above.
4. **Run the gate and make it green:** `bash scripts/check.sh`. The gate needs the `lib_bespok3d`
   submodule; if you cloned without it, run `git submodule update --init` first.
   This repo ships config, patches, assets, and shell, so the gate runs the shared workspace detectors:
   workflow-pinning, the em-dash guard, and shellcheck. It also runs ruff, mypy, and pytest over the
   plugin's Python (see `scripts/check.sh` for the exact targets).
5. **On a gate failure, fix the cause.** Never hand-wave a real smell away. If a detector is genuinely
   wrong about a line, the fix is a per-instance justified allow at the smell
   (`# gate-allow <metric>: <reason>`, with a reason that survives "why is THIS one ok?"), never a
   blanket mute to make a number go down.
6. **Add a regression test** where the repo has a Python test layer for the behavior, in the same change:
   it fails on the old behavior and passes on the fix.
7. **Keep the docs current.** If the change alters what a plugin does or how it is configured, update
   that plugin's `doc/README.md` and its `doc/CHANGELOG.md`.

## Hard constraints

- **Never run git.** The maintainer commits. Leave the tree green and hand over exact commands if a git
  action is needed.
- **Never SSH-mutate or reconfigure a live printer** without explicit per-action authorization. A serial
  port or GPIO on a printer may be a live Klipper MCU link; read-only diagnosis is fine, but propose any
  device-changing step and wait for a yes.
- **The gate must be green** before a change is considered done.

## When you are unsure

Ask one specific question and stop. Do not guess and implement, and do not "try something reasonable."
The architecture is the maintainer's; your job is to implement it to the rules above.
