#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (C) 2026 unlucio and the Bespok3d contributors
# SPDX-License-Identifier: GPL-3.0-only
# This plugin's own gate: it must pass from this repo's root, with no sibling repo cloned except
# lib_bespok3d. Exits non-zero on any failure.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# The shared gate helpers and the detectors that enforce a workspace-wide rule live in one place.
# See lib_bespok3d/tooling/README.md. This is the only line that knows where they are.
B3D_TOOLING="${B3D_TOOLING:-$REPO_ROOT/lib_bespok3d/tooling}"
# lib_bespok3d is a submodule. A clone made without it leaves an empty directory here, so say what
# is actually wrong instead of letting every check below fail on a missing file.
if [ ! -f "$B3D_TOOLING/gate-lib.sh" ] || [ ! -f "$B3D_TOOLING/release-trigger-detector.mjs" ]; then
    echo "The shared gate helpers are missing or older than the checks this gate runs:" >&2
    echo "the lib_bespok3d submodule is not checked out, or is pinned to an older commit." >&2
    echo "Run this once from the repo root, then try again:" >&2
    echo "  git submodule sync --recursive && git submodule update --init --recursive" >&2
    echo "See CONTRIBUTING.md for the full environment setup." >&2
    exit 1
fi

# shellcheck source=/dev/null
. "$B3D_TOOLING/gate-lib.sh"

cd "$REPO_ROOT" || exit 1

PLUGIN_DIR="$REPO_ROOT/rfid-ntag"
RFID_SUPPORT="files/klipper/klippy/extras/rfid-support"

echo ""
echo "u1-enhanced-rfid gate"

b3d_python_tools

run_check "pytest"  pytest_in_dir "$PLUGIN_DIR" tests
run_check "ruff"    ruff_in_dir "$PLUGIN_DIR" files tests
# The reader driver talks to Klipper objects mypy cannot resolve; the pure decode path carries the
# type coverage.
run_check "mypy"    mypy_in_dir "$PLUGIN_DIR" \
    "$RFID_SUPPORT/chips/ndef_parser.py" "$RFID_SUPPORT/chips/mifare_classic.py" \
    "$RFID_SUPPORT/payload_mapper.py"

release_trigger_check "$REPO_ROOT"
workflow_pinning_check "$REPO_ROOT"
em_dash_check "$REPO_ROOT"
shellcheck_repo "$REPO_ROOT"

gate_summary || exit 1
