# AGENTS.md

This repo's contributor rules for AI assistants live in [CLAUDE.md](CLAUDE.md). They are tool-agnostic:
read that file and follow it, whatever assistant you are.

Short version: a Bespok3d plugin declares WHAT the printer should end up with, never a script that runs
on the printer. Before you propose a change, run `bash scripts/check.sh` and make it green (fix a real
failure, never mute it), and keep every identifier meaningful, nesting shallow, and em-dashes out.
